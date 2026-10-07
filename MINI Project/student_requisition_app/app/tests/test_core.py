"""Run with:  pytest -q"""
import io
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                      # noqa: E402
import database as db              # noqa: E402
import validators as V             # noqa: E402
from pdf_generator import build_pdf  # noqa: E402


def good_form(**over):
    f = dict(department="Computer Engineering", student_name="Aarav Sharma",
             roll_no="CMPN2301", semester=5, division="B", email="aarav@example.com",
             mobile="9876543210", app_type="Bonafide",
             purpose="Bonafide required for education loan.", docs_attached=False,
             doc_names="", uploaded_names=[], form_date=date.today(), declaration=True)
    f.update(over)
    return f


def record(**over):
    r = dict(department="Computer Engineering", student_name="Aarav Sharma",
             roll_no="CMPN2301", semester=5, division="B", email="aarav@example.com",
             mobile="+91 9876543210", app_type="Bonafide", other_details="",
             purpose="Bonafide required for education loan.", docs_attached=True,
             doc_names="Fee receipt", form_date="07/10/2026")
    r.update(over)
    return r


@pytest.fixture()
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return tmp_path


# ------------------------------------------------------------ validation
def test_valid_form_passes():
    assert V.validate_application(good_form()) == []


@pytest.mark.parametrize("field", ["department", "student_name", "roll_no", "division",
                                   "email", "mobile", "purpose", "app_type", "semester"])
def test_mandatory_fields(field):
    assert V.validate_application(good_form(**{field: ""})) != []
    assert V.validate_application(good_form(**{field: None})) != []


@pytest.mark.parametrize("raw,expected", [
    ("9876543210", "9876543210"), ("+91 98765 43210", "9876543210"),
    ("098765-43210", "9876543210"), ("919876543210", "9876543210"),
    ("5876543210", None), ("98765", None), ("98765abcde", None), ("", None),
    ("98765432101", None)])
def test_mobile_normalisation(raw, expected):
    assert V.normalize_mobile(raw) == expected


@pytest.mark.parametrize("email,ok", [
    ("a@b.com", True), ("first.last+tag@college.edu.in", True),
    ("bad@email", False), ("no-at.com", False), ("a b@c.com", False), ("@x.com", False)])
def test_email(email, ok):
    assert (V.validate_application(good_form(email=email)) == []) is ok


def test_declaration_required():
    errs = V.validate_application(good_form(declaration=False))
    assert any("Declaration" in e for e in errs)


def test_docs_yes_needs_names():
    assert V.validate_application(good_form(docs_attached=True)) != []
    assert V.validate_application(good_form(docs_attached=True, doc_names="ID card",
                                            all_doc_names="ID card")) == []


def test_other_requires_details():
    assert V.validate_application(good_form(app_type=config.OTHER_TYPE)) != []
    assert V.validate_application(good_form(app_type=config.OTHER_TYPE,
                                            other_details="Library NOC")) == []


def test_future_date_rejected():
    assert V.validate_application(good_form(form_date=date.today() + timedelta(days=1))) != []


def test_purpose_limits():
    assert V.validate_application(good_form(purpose="short")) != []
    assert V.validate_application(good_form(purpose="x" * 501)) != []
    # wide characters / many line breaks cannot silently overflow the form
    assert V.validate_application(good_form(purpose="\n".join(["line"] * 9))) != []


# -------------------------------------------------------------- database
def test_sequential_requisition_numbers(tmpdb):
    a = db.create_requisition(record(), lambda r: build_pdf(r))
    b = db.create_requisition(record(roll_no="X2"), lambda r: build_pdf(r))
    year = date.today().year
    assert a["req_no"] == f"REQ-{year}-0001" and b["req_no"] == f"REQ-{year}-0002"


def test_failed_pdf_rolls_back(tmpdb):
    def boom(_):
        raise RuntimeError("pdf failed")
    with pytest.raises(RuntimeError):
        db.create_requisition(record(), boom)
    assert db.search() == []
    ok = db.create_requisition(record(), lambda r: build_pdf(r))
    assert ok["req_no"].endswith("0001")           # no number was burned


def test_track_needs_matching_roll(tmpdb):
    r = db.create_requisition(record(), lambda x: build_pdf(x))
    assert db.track(r["req_no"], "cmpn2301")["status"] == "Submitted"   # case-insensitive
    assert db.track(r["req_no"], "WRONG") is None
    assert db.track("REQ-0000-0000", "CMPN2301") is None


def test_status_update_and_history(tmpdb):
    r = db.create_requisition(record(), lambda x: build_pdf(x))
    db.update_status(r["req_no"], "Approved", "Collect from office")
    t = db.track(r["req_no"], "CMPN2301")
    assert t["status"] == "Approved" and t["remarks"] == "Collect from office"
    assert [h["status"] for h in t["history"]] == ["Submitted", "Approved"]
    with pytest.raises(ValueError):
        db.update_status(r["req_no"], "Nonsense", "")


def test_search_and_stats(tmpdb):
    db.create_requisition(record(), lambda x: build_pdf(x))
    db.create_requisition(record(student_name="Riya Patel", roll_no="IT55",
                                 app_type="NOC"), lambda x: build_pdf(x))
    assert len(db.search("riya")) == 1
    assert len(db.search("", app_type="NOC")) == 1
    assert len(db.search("'; DROP TABLE requisitions;--")) == 0     # injection-safe
    s = db.stats()
    assert s["total"] == 2 and s["by_type"]["NOC"] == 1


# ------------------------------------------------------------------- PDF
def text_of(pdf: bytes) -> str:
    r = PdfReader(io.BytesIO(pdf))
    assert len(r.pages) == 1
    return r.pages[0].extract_text()


def test_pdf_contains_all_fields_and_form_structure():
    t = text_of(build_pdf({**record(), "req_no": "REQ-2026-0007"}))
    for needle in ["STUDENT ACADEMIC REQUISITION", "Aarav Sharma", "CMPN2301",
                   "Computer Engineering", "aarav@example.com", "9876543210",
                   "Bonafide", "education loan", "Fee receipt", "07/10/2026",
                   "REQ-2026-0007", "1. STUDENT DETAILS", "2. PURPOSE", "3. SUPPORTING",
                   "4. STUDENT DECLARATION", "I certify that the information",
                   "5. HoD Signature", "Forwarded to", "6. PRINCIPAL OFFICE USE ONLY",
                   "Decision by Principal", "Clarification Required", "Principal Signature"]:
        assert needle in t, needle


def test_pdf_handles_unicode_other_and_signature():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (200, 80), "white").save(buf, "PNG")
    pdf = build_pdf({**record(student_name="Zoë Müller", app_type="Other request",
                              other_details="Library NOC"), "req_no": "REQ-1"}, buf.getvalue())
    assert "Library NOC" in text_of(pdf)


def test_pdf_ignores_garbage_signature():
    assert build_pdf({**record(), "req_no": "R"}, b"not an image").startswith(b"%PDF")
