"""SQLite persistence for requisitions, status history and generated PDFs."""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Callable

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS counters (
    year INTEGER PRIMARY KEY,
    last INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS requisitions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    req_no        TEXT UNIQUE NOT NULL,
    created_at    TEXT NOT NULL,
    form_date     TEXT NOT NULL,
    department    TEXT NOT NULL,
    student_name  TEXT NOT NULL,
    roll_no       TEXT NOT NULL,
    semester      INTEGER NOT NULL,
    division      TEXT NOT NULL,
    email         TEXT NOT NULL,
    mobile        TEXT NOT NULL,
    app_type      TEXT NOT NULL,
    other_details TEXT DEFAULT '',
    purpose       TEXT NOT NULL,
    docs_attached INTEGER NOT NULL,
    doc_names     TEXT DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'Submitted',
    remarks       TEXT DEFAULT '',
    updated_at    TEXT NOT NULL,
    pdf           BLOB
);
CREATE TABLE IF NOT EXISTS status_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    req_no     TEXT NOT NULL,
    status     TEXT NOT NULL,
    remarks    TEXT DEFAULT '',
    changed_at TEXT NOT NULL,
    changed_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_req_roll ON requisitions(roll_no);
CREATE INDEX IF NOT EXISTS idx_req_status ON requisitions(status);
"""

LIST_COLS = ("req_no, created_at, form_date, department, student_name, roll_no, semester, "
             "division, email, mobile, app_type, other_details, purpose, docs_attached, "
             "doc_names, status, remarks, updated_at")


def _now() -> str:
    return config.now().strftime("%Y-%m-%d %H:%M:%S")


def _connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=15, isolation_level=None)  # manual txns
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript(SCHEMA)


def create_requisition(data: dict, pdf_builder: Callable[[dict], bytes]) -> dict:
    """Atomically allocate a requisition number, build the PDF and save everything.

    `pdf_builder(record)` receives the data including the new `req_no`. If PDF
    generation fails the whole transaction is rolled back, so no orphan record
    (and no skipped number) is left behind.
    """
    with _db() as conn:
        conn.execute("BEGIN IMMEDIATE")          # serialises concurrent submissions
        try:
            year = config.now().year
            row = conn.execute("SELECT last FROM counters WHERE year=?", (year,)).fetchone()
            seq = (row["last"] if row else 0) + 1
            conn.execute("INSERT INTO counters(year,last) VALUES(?,?) "
                         "ON CONFLICT(year) DO UPDATE SET last=excluded.last", (year, seq))
            req_no = f"REQ-{year}-{seq:04d}"
            record = {**data, "req_no": req_no}
            pdf_bytes = pdf_builder(record)
            now = _now()
            conn.execute(
                """INSERT INTO requisitions(req_no, created_at, form_date, department,
                   student_name, roll_no, semester, division, email, mobile, app_type,
                   other_details, purpose, docs_attached, doc_names, status, remarks,
                   updated_at, pdf)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (req_no, now, data["form_date"], data["department"], data["student_name"],
                 data["roll_no"], data["semester"], data["division"], data["email"],
                 data["mobile"], data["app_type"], data.get("other_details", ""),
                 data["purpose"], int(bool(data["docs_attached"])), data.get("doc_names", ""),
                 "Submitted", "", now, pdf_bytes))
            conn.execute("INSERT INTO status_history(req_no,status,remarks,changed_at,changed_by)"
                         " VALUES(?,?,?,?,?)", (req_no, "Submitted", "Application submitted",
                                                now, "student"))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {**record, "pdf": pdf_bytes, "created_at": now, "status": "Submitted"}


def get_pdf(req_no: str) -> bytes | None:
    with _db() as conn:
        row = conn.execute("SELECT pdf FROM requisitions WHERE req_no=?", (req_no,)).fetchone()
    return row["pdf"] if row else None


def track(req_no: str, roll_no: str) -> dict | None:
    """Student-facing lookup: requires BOTH requisition number and roll number."""
    req_no = (req_no or "").strip().upper()
    roll_no = (roll_no or "").strip()
    with _db() as conn:
        row = conn.execute(f"SELECT {LIST_COLS} FROM requisitions "
                           "WHERE req_no=? AND LOWER(roll_no)=LOWER(?)",
                           (req_no, roll_no)).fetchone()
        if not row:
            return None
        hist = conn.execute("SELECT status, remarks, changed_at FROM status_history "
                            "WHERE req_no=? ORDER BY id", (req_no,)).fetchall()
    return {**dict(row), "history": [dict(h) for h in hist]}


def working_days_elapsed(start: date, end: date) -> int:
    """Working days (Mon-Fri, excluding config.HOLIDAYS) after `start` up to `end`."""
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in config.HOLIDAYS:
            n += 1
    return n


def _enrich(row: dict) -> dict:
    """Add SLA info: age in working days and whether the 4-day promise is breached."""
    created = datetime.strptime(row["created_at"][:10], "%Y-%m-%d").date()
    age = working_days_elapsed(created, config.today())
    row["age_days"] = age
    row["overdue"] = row["status"] not in config.FINAL_STATUSES and age > config.SLA_WORKING_DAYS
    return row


def search(text: str = "", status: str | None = None, app_type: str | None = None,
           date_from: str | None = None, date_to: str | None = None,
           department: str | None = None, overdue_only: bool = False) -> list[dict]:
    """Admin search over name / roll / requisition no. / email / mobile / dept / purpose."""
    sql, params = [f"SELECT {LIST_COLS} FROM requisitions WHERE 1=1"], []
    if text.strip():
        like = f"%{text.strip()}%"
        sql.append("AND (req_no LIKE ? OR student_name LIKE ? OR roll_no LIKE ? OR email LIKE ? "
                   "OR mobile LIKE ? OR department LIKE ? OR purpose LIKE ?)")
        params += [like] * 7
    if status and status != "All":
        sql.append("AND status=?")
        params.append(status)
    if app_type and app_type != "All":
        sql.append("AND app_type=?")
        params.append(app_type)
    if department and department != "All":
        sql.append("AND department=?")
        params.append(department)
    if date_from:
        sql.append("AND substr(created_at,1,10) >= ?")
        params.append(date_from)
    if date_to:
        sql.append("AND substr(created_at,1,10) <= ?")
        params.append(date_to)
    sql.append("ORDER BY id DESC")
    with _db() as conn:
        rows = [_enrich(dict(r)) for r in conn.execute(" ".join(sql), params).fetchall()]
    return [r for r in rows if r["overdue"]] if overdue_only else rows


def find_open_duplicate(roll_no: str, app_type: str, days: int = 7) -> dict | None:
    """An unfinished request by the same student for the same purpose in the last `days`."""
    since = (config.today() - timedelta(days=days)).isoformat()
    with _db() as conn:
        row = conn.execute(
            f"SELECT {LIST_COLS} FROM requisitions WHERE LOWER(roll_no)=LOWER(?) AND app_type=? "
            "AND substr(created_at,1,10) >= ? ORDER BY id DESC", (roll_no, app_type, since)
        ).fetchall()
    for r in row:
        if r["status"] not in config.FINAL_STATUSES:
            return dict(r)
    return None


def get_email(req_no: str) -> str | None:
    with _db() as conn:
        row = conn.execute("SELECT email FROM requisitions WHERE req_no=?", (req_no,)).fetchone()
    return row["email"] if row else None


def withdraw(req_no: str, roll_no: str) -> None:
    """Student withdraws their own request - only allowed before the office acts on it."""
    rec = track(req_no, roll_no)
    if not rec:
        raise ValueError("Requisition not found")
    if rec["status"] != "Submitted":
        raise ValueError("Only applications that have not yet been processed can be withdrawn")
    update_status(rec["req_no"], "Withdrawn", "Withdrawn by student", by="student")


# ---- brute-force throttle for staff login (global: Streamlit hides client IPs)
def record_failed_login() -> None:
    with _db() as conn:
        conn.execute("INSERT INTO login_failures(at) VALUES(?)", (_now(),))


def login_locked(max_failures: int = 10, window_minutes: int = 5) -> bool:
    since = (config.now() - timedelta(minutes=window_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with _db() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM login_failures WHERE at >= ?", (since,)).fetchone()["c"]
    return n >= max_failures


def history(req_no: str) -> list[dict]:
    with _db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT status, remarks, changed_at, changed_by FROM status_history "
            "WHERE req_no=? ORDER BY id", (req_no,)).fetchall()]


def update_status(req_no: str, status: str, remarks: str, by: str = "admin") -> None:
    if status not in config.STATUSES:
        raise ValueError("Unknown status")
    now = _now()
    with _db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute("UPDATE requisitions SET status=?, remarks=?, updated_at=? "
                               "WHERE req_no=?", (status, remarks, now, req_no))
            if cur.rowcount != 1:
                raise ValueError("Requisition not found")
            conn.execute("INSERT INTO status_history(req_no,status,remarks,changed_at,changed_by)"
                         " VALUES(?,?,?,?,?)", (req_no, status, remarks, now, by))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def stats() -> dict:
    rows = search()
    today = config.today()
    by_status, by_type = {}, {}
    daily = {(today - timedelta(days=i)).isoformat(): 0 for i in range(13, -1, -1)}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_type[r["app_type"]] = by_type.get(r["app_type"], 0) + 1
        if r["created_at"][:10] in daily:
            daily[r["created_at"][:10]] += 1
    return {
        "total": len(rows),
        "today": daily.get(today.isoformat(), 0),
        "overdue": sum(1 for r in rows if r["overdue"]),
        "by_status": by_status,
        "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        "daily": daily,
    }


def safe_dirname(req_no: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", req_no)
