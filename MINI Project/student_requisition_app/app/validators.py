"""Input validation. Every function returns a list of human-readable errors
(empty list = valid) so the UI can show all problems at once."""
from __future__ import annotations

import io
import re
from datetime import date

from PIL import Image

import config
from pdf_generator import doc_names_layout, purpose_layout

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,59}$")
ROLL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_\-]{1,19}$")
DIV_RE = re.compile(r"^[A-Za-z0-9]{1,3}$")
# Pragmatic RFC-5322 subset: local@domain.tld, no spaces, TLD >= 2 letters
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$")


def clean(text: str | None) -> str:
    """Trim and collapse repeated spaces (newlines are kept for multi-line fields)."""
    return re.sub(r"[ \t]+", " ", (text or "").strip())


def normalize_mobile(raw: str) -> str | None:
    """Return a 10-digit Indian mobile number, or None if the input is invalid.

    Accepts spaces/hyphens and an optional +91 / 91 / 0 prefix.
    """
    digits = re.sub(r"[\s\-()]", "", raw or "")
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def validate_application(f: dict) -> list[str]:
    """Validate the dict of form values collected by the UI."""
    errs: list[str] = []

    dept = clean(f.get("department"))
    if not dept:
        errs.append("Name of Department is required.")
    elif len(dept) > 60:
        errs.append("Department name is too long (max 60 characters).")

    name = clean(f.get("student_name"))
    if not name:
        errs.append("Student Name is required.")
    elif not NAME_RE.match(name):
        errs.append("Student Name may contain only letters, spaces and . ' - (2-60 characters).")

    roll = clean(f.get("roll_no"))
    if not roll:
        errs.append("Roll Number is required.")
    elif not ROLL_RE.match(roll):
        errs.append("Roll Number may contain only letters, digits, / _ - (2-20 characters).")

    if f.get("semester") not in config.SEMESTERS:
        errs.append("Please select a valid Semester.")

    div = clean(f.get("division"))
    if not div:
        errs.append("Division is required.")
    elif not DIV_RE.match(div):
        errs.append("Division must be 1-3 letters/digits (e.g. A, B2).")

    email = clean(f.get("email"))
    if not email:
        errs.append("Email address is required.")
    elif len(email) > 100 or not EMAIL_RE.match(email):
        errs.append("Please enter a valid email address (e.g. name@example.com).")

    mobile_raw = clean(f.get("mobile"))
    if not mobile_raw:
        errs.append("Mobile number is required.")
    elif normalize_mobile(mobile_raw) is None:
        errs.append("Mobile number must be a valid 10-digit number starting with 6-9 "
                    "(an optional +91 is allowed).")

    app_type = f.get("app_type")
    if not app_type:
        errs.append("Please select an Application Type.")
    elif app_type not in config.APPLICATION_TYPES:
        errs.append("Invalid Application Type.")
    elif app_type == config.OTHER_TYPE and len(clean(f.get("other_details"))) < 3:
        errs.append("Please specify the type of request for 'Other request'.")

    purpose = (f.get("purpose") or "").strip()
    if not purpose:
        errs.append("Purpose / Brief Details of Request is required.")
    elif len(purpose) < config.PURPOSE_MIN:
        errs.append(f"Purpose must be at least {config.PURPOSE_MIN} characters.")
    elif len(purpose) > config.PURPOSE_MAX:
        errs.append(f"Purpose must be at most {config.PURPOSE_MAX} characters "
                    f"(currently {len(purpose)}).")
    elif not purpose_layout(purpose)[2]:
        errs.append("Purpose is too long to fit in the space on the form. Please shorten it "
                    "or use fewer line breaks.")

    if f.get("docs_attached") is None:
        errs.append("Please state whether supporting documents are attached (Yes / No).")
    elif f.get("docs_attached") and not (clean(f.get("doc_names")) or f.get("uploaded_names")):
        errs.append("Please enter the name(s) of the supporting document(s) or upload them.")
    elif f.get("docs_attached") and not doc_names_layout(f.get("all_doc_names", ""))[2]:
        errs.append("The list of document names is too long for the form. Please shorten it.")

    d = f.get("form_date")
    if not isinstance(d, date):
        errs.append("Please select a valid Date.")
    elif d > config.today():
        errs.append("Date cannot be in the future.")

    if not f.get("declaration"):
        errs.append("You must accept the Student Declaration before generating the PDF.")

    return errs


_MAGIC = {"pdf": (b"%PDF",), "png": (b"\x89PNG",), "jpg": (b"\xff\xd8\xff",),
          "jpeg": (b"\xff\xd8\xff",), "docx": (b"PK\x03\x04",)}


def content_matches_extension(name: str, head: bytes) -> bool:
    """Reject files whose real content does not match their extension (e.g. .exe renamed .pdf)."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in _MAGIC and any(head.startswith(m) for m in _MAGIC[ext])


def validate_uploads(files) -> list[str]:
    """Supporting-document uploads: count, size, extension."""
    errs: list[str] = []
    files = files or []
    if len(files) > config.MAX_UPLOAD_FILES:
        errs.append(f"You can upload at most {config.MAX_UPLOAD_FILES} supporting documents.")
    for up in files:
        if up.size > config.MAX_UPLOAD_MB * 1024 * 1024:
            errs.append(f"'{up.name}' is larger than {config.MAX_UPLOAD_MB} MB.")
        elif not content_matches_extension(up.name, up.getvalue()[:8]):
            errs.append(f"'{up.name}' is not a genuine {up.name.rsplit('.', 1)[-1].upper()} file.")
    return errs


def validate_signature(upload) -> list[str]:
    if upload is None:
        return []
    if upload.size > config.MAX_SIGNATURE_MB * 1024 * 1024:
        return [f"Signature image must be smaller than {config.MAX_SIGNATURE_MB} MB."]
    try:
        Image.open(io.BytesIO(upload.getvalue())).verify()
    except Exception:
        return ["The signature file is not a valid image (use PNG or JPG)."]
    return []
