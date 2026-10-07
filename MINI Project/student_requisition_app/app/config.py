"""Central configuration: everything that mirrors the institute form lives here,
so the form wording can be changed in one place without touching app/PDF code."""
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"
FONT_REGULAR = ASSETS_DIR / "fonts" / "DejaVuSans.ttf"
FONT_BOLD = ASSETS_DIR / "fonts" / "DejaVuSans-Bold.ttf"

# Storage (override with env vars when deploying with a persistent volume)
DATA_DIR = Path(os.environ.get("REQ_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.environ.get("REQ_DB_PATH", DATA_DIR / "requisitions.db"))
UPLOAD_DIR = Path(os.environ.get("REQ_UPLOAD_DIR", DATA_DIR / "uploads"))

INSTITUTE_SUBTITLE = "(Autonomous College Affiliated to University of Mumbai)"
FORM_TITLE = "STUDENT ACADEMIC REQUISITION FORM"

PROCESSING_NOTE = (
    "The request will normally be processed within 4 working days after receiving "
    "the completed form and all required supporting documents. Students are advised "
    "to apply in advance, as incomplete applications may require additional "
    "processing time."
)

DECLARATION = (
    "I certify that the information provided above is correct and that the request "
    "is being submitted for academic purposes. I understand that the request will be "
    "processed as per applicable Institute/University rules and within the "
    "stipulated processing time."
)

FORWARDED_TO = (
    "(VICE PRINCIPAL/ CHIEF ACADEMIC OFFICER/ ACCOUNTS/ SPORTS/ PLACEMENT CELL/ "
    "SCHOLARSHIP CELL/ EXAM CELL) (if required)"
)

# Order and wording exactly as printed on the form
APPLICATION_TYPES = [
    "Bonafide",
    "Student Certificate",
    "Scholarship",
    "NOC",
    "Academic Permission",
    "Examination",
    "Internship",
    "Placement",
    "Other request",
]
OTHER_TYPE = "Other request"

# Edit to match the college's departments
DEPARTMENTS = [
    "Computer Engineering",
    "Information Technology",
    "Electronics & Telecommunication Engineering",
    "Artificial Intelligence & Data Science",
    "Computer Science & Engineering (Data Science)",
    "Electronics & Computer Science",
    "Mechanical Engineering",
    "Basic Sciences & Humanities",
    "MCA / MMS",
    "Other",
]
OTHER_DEPARTMENT = "Other"

SEMESTERS = list(range(1, 9))

PURPOSE_MIN, PURPOSE_MAX = 10, 500
MAX_UPLOAD_FILES = 5
MAX_UPLOAD_MB = 5
ALLOWED_DOC_TYPES = ["pdf", "png", "jpg", "jpeg", "docx"]
MAX_SIGNATURE_MB = 2

SLA_WORKING_DAYS = 4          # "processed within 4 working days" (as printed on the form)
TIMEZONE = os.environ.get("REQ_TIMEZONE", "Asia/Kolkata")
HOLIDAYS: set[date] = set()   # add institute holidays, e.g. {date(2026, 11, 8)}

STATUSES = [
    "Submitted",
    "Under Review (HoD)",
    "Forwarded",
    "Approved",
    "Not Approved",
    "Clarification Required",
    "Ready for Collection",
    "Closed",
    "Withdrawn",
]
# Statuses after which the SLA clock no longer matters
FINAL_STATUSES = {"Approved", "Not Approved", "Ready for Collection", "Closed", "Withdrawn"}
STATUS_COLORS = {
    "Submitted": "#5b6b8c",
    "Under Review (HoD)": "#b7791f",
    "Forwarded": "#2b6cb0",
    "Approved": "#2f855a",
    "Not Approved": "#c53030",
    "Clarification Required": "#c05621",
    "Ready for Collection": "#2c7a7b",
    "Closed": "#4a5568",
    "Withdrawn": "#718096",
}




def now() -> datetime:
    """Current time in the institute's timezone (hosts usually run in UTC)."""
    return datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)


def today() -> date:
    return now().date()


def secret(key: str, default: str = "") -> str:
    """Read a setting from Streamlit secrets, then environment variables."""
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


HELPDESK = secret("HELPDESK_EMAIL")      # shown to students if configured


def staff_users() -> dict[str, str]:
    """Staff accounts {username: password}.

    Sources (merged): ``[admins]`` table in Streamlit secrets, ``ADMIN_USERS``
    env var ("alice:pw1,bob:pw2"), and ``ADMIN_PASSWORD`` (user "admin").
    Falls back to the insecure demo account admin/admin123 if nothing is set.
    """
    users: dict[str, str] = {}
    try:
        import streamlit as st
        if "admins" in st.secrets:
            users.update({str(k): str(v) for k, v in st.secrets["admins"].items()})
    except Exception:
        pass
    for pair in os.environ.get("ADMIN_USERS", "").split(","):
        if ":" in pair:
            u, p = pair.split(":", 1)
            if u.strip() and p:
                users[u.strip()] = p
    pw = secret("ADMIN_PASSWORD")
    if pw:
        users.setdefault("admin", pw)
    return users or {"admin": "admin123"}


def using_demo_credentials() -> bool:
    return staff_users() == {"admin": "admin123"}
