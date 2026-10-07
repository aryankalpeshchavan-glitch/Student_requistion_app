"""Tests for the second-round features: SLA, duplicates, withdraw, auth, uploads, e-mail."""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                       # noqa: E402
import database as db               # noqa: E402
import notifications as N           # noqa: E402
import validators as V              # noqa: E402
from pdf_generator import build_pdf  # noqa: E402
from test_core import record, tmpdb  # noqa: E402,F401


def make(**over):
    return db.create_requisition(record(**over), lambda r: build_pdf(r))


def backdate(req_no, days):
    """Pretend the request was submitted `days` calendar days ago."""
    when = (config.now() - timedelta(days=days)).strftime("%Y-%m-%d 10:00:00")
    with db._db() as c:
        c.execute("UPDATE requisitions SET created_at=? WHERE req_no=?", (when, req_no))


# ------------------------------------------------------------ SLA / working days
def test_working_days_skip_weekends_and_holidays(monkeypatch):
    fri, mon, next_fri = date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 9)
    assert db.working_days_elapsed(fri, mon) == 1          # Sat/Sun not counted
    assert db.working_days_elapsed(fri, next_fri) == 5
    assert db.working_days_elapsed(fri, fri) == 0
    monkeypatch.setattr(config, "HOLIDAYS", {date(2026, 10, 6)})
    assert db.working_days_elapsed(fri, next_fri) == 4


def test_overdue_flag_and_filter(tmpdb):
    old = make(); new = make(roll_no="N2")
    backdate(old["req_no"], 14)
    assert [r["req_no"] for r in db.search(overdue_only=True)] == [old["req_no"]]
    assert db.stats()["overdue"] == 1
    db.update_status(old["req_no"], "Approved", "")        # finished -> no longer overdue
    assert db.stats()["overdue"] == 0 and new["req_no"]


# ------------------------------------------------------------ duplicates / withdraw
def test_duplicate_detection(tmpdb):
    assert db.find_open_duplicate("CMPN2301", "Bonafide") is None
    first = make()
    assert db.find_open_duplicate("cmpn2301", "Bonafide")["req_no"] == first["req_no"]
    assert db.find_open_duplicate("CMPN2301", "NOC") is None              # other purpose
    db.update_status(first["req_no"], "Approved", "")
    assert db.find_open_duplicate("CMPN2301", "Bonafide") is None         # finished


def test_withdraw_rules(tmpdb):
    a = make()
    with pytest.raises(ValueError):
        db.withdraw(a["req_no"], "WRONGROLL")
    db.withdraw(a["req_no"], "CMPN2301")
    assert db.track(a["req_no"], "CMPN2301")["status"] == "Withdrawn"
    assert db.history(a["req_no"])[-1]["changed_by"] == "student"
    b = make(roll_no="B2")
    db.update_status(b["req_no"], "Under Review (HoD)", "")
    with pytest.raises(ValueError):                                       # already in process
        db.withdraw(b["req_no"], "B2")


def test_audit_trail_records_staff_name(tmpdb):
    a = make()
    db.update_status(a["req_no"], "Forwarded", "to accounts", by="hod_comp")
    assert db.history(a["req_no"])[-1]["changed_by"] == "hod_comp"


# ------------------------------------------------------------ staff auth
def test_login_throttle(tmpdb):
    assert not db.login_locked()
    for _ in range(10):
        db.record_failed_login()
    assert db.login_locked()


def test_staff_users_sources(monkeypatch):
    monkeypatch.setenv("ADMIN_USERS", "alice:pw1,bob:pw:with:colons")
    monkeypatch.setenv("ADMIN_PASSWORD", "root")
    u = config.staff_users()
    assert u["alice"] == "pw1" and u["bob"] == "pw:with:colons" and u["admin"] == "root"
    assert not config.using_demo_credentials()
    monkeypatch.delenv("ADMIN_USERS"); monkeypatch.delenv("ADMIN_PASSWORD")
    assert config.using_demo_credentials()


# ------------------------------------------------------------ uploads
def fake(name, content):
    return SimpleNamespace(name=name, size=len(content), getvalue=lambda: content)


def test_upload_content_must_match_extension():
    ok = fake("fee.pdf", b"%PDF-1.7 ...")
    spoof = fake("virus.pdf", b"MZ\x90\x00 executable")
    assert V.validate_uploads([ok]) == []
    assert V.validate_uploads([spoof]) != []
    assert V.validate_uploads([fake("a.png", b"\x89PNG\r\n")]) == []
    assert V.validate_uploads([fake("a.docx", b"PK\x03\x04..")]) == []
    assert V.validate_uploads([fake("big.pdf", b"%PDF" + b"0" * (6 * 1024 * 1024))]) != []
    assert V.validate_uploads([ok] * 6) != []


# ------------------------------------------------------------ e-mail
def test_email_disabled_without_smtp(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert not N.enabled()
    assert N.send_email("a@b.com", "s", "b") is False


def test_email_sent_with_attachment(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.test"); monkeypatch.setenv("SMTP_FROM", "portal@test")
    monkeypatch.setenv("SMTP_PORT", "587")
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None): sent["host"] = host
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): sent["tls"] = True
        def login(self, u, p): sent["login"] = True
        def send_message(self, msg): sent["msg"] = msg

    monkeypatch.setattr(N.smtplib, "SMTP", FakeSMTP)
    rec = {**record(), "req_no": "REQ-2026-0009"}
    assert N.notify_submission(rec, b"%PDF-fake", "x.pdf") is True
    msg = sent["msg"]
    assert msg["To"] == "aarav@example.com" and "REQ-2026-0009" in msg["Subject"]
    assert [p.get_filename() for p in msg.iter_attachments()] == ["x.pdf"]


def test_email_failure_never_raises(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.test"); monkeypatch.setenv("SMTP_FROM", "p@t")
    monkeypatch.setattr(N.smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert N.send_email("a@b.com", "s", "b") is False


# ------------------------------------------------------------ timezone / preview
def test_uses_institute_timezone(monkeypatch):
    monkeypatch.setattr(config, "TIMEZONE", "Pacific/Kiritimati")          # UTC+14
    ahead = config.now()
    monkeypatch.setattr(config, "TIMEZONE", "Etc/GMT+12")                  # UTC-12
    assert ahead - config.now() > timedelta(hours=25)


def test_draft_preview_renders():
    pdf = build_pdf({**record(), "req_no": "To be assigned"}, draft=True)
    assert pdf.startswith(b"%PDF")
