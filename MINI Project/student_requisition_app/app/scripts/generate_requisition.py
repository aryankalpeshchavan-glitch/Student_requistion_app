"""Generate a Student Academic Requisition Form PDF from the command line.

Usage:
    python -m scripts.generate_requisition --student "Aarav Sharma" --roll CMPN2301 \
        --department "Computer" --semester 2 --division "A" --email "a.sharma@example.com" \
        --mobile "9876543210" --app-type "General" --purpose "Career counseling"

This script is a thin CLI wrapper around ``pdf_generator.build_pdf`` so the same
PDF generation logic used by the Streamlit app can be run standalone.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Resolve the ``app`` directory (the directory containing the package
# modules ``config`` and ``pdf_generator``) regardless of the current
# working directory.
APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from pdf_generator import build_pdf  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a Student Academic Requisition Form PDF."
    )
    parser.add_argument(
        "--student",
        required=True,
        help="Full name of the student as it appears on the form.",
    )
    parser.add_argument(
        "--roll",
        required=True,
        help="Roll number / admission code (e.g. CMPN2301).",
    )
    parser.add_argument(
        "--department",
        required=True,
        help="Department the student belongs to.",
    )
    parser.add_argument(
        "--semester",
        required=True,
        help="Semester number (e.g. 2).",
    )
    parser.add_argument(
        "--division",
        required=True,
        help="Division/section of the student.",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Student email address.",
    )
    parser.add_argument(
        "--mobile",
        required=True,
        help="Student mobile number.",
    )
    parser.add_argument(
        "--app-type",
        required=True,
        help="Application type (e.g. General, Sports, Scholarship).",
    )
    parser.add_argument(
        "--purpose",
        required=True,
        help="Purpose of the requisition.",
    )
    parser.add_argument(
        "--doc-names",
        default="",
        help="Comma separated list of attached document names.",
    )
    parser.add_argument(
        "--docs-attached",
        type=int,
        default=0,
        help="Count of documents attached.",
    )
    parser.add_argument(
        "--form-date",
        default="",
        help="Form date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--remarks",
        default="",
        help="Remarks field.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output path for the generated PDF. Defaults to a file in the "
        "repository data directory.",
    )
    return parser


def build_record(args: argparse.Namespace) -> dict:
    record = {
        "student_name": args.student,
        "roll_no": args.roll,
        "department": args.department,
        "semester": int(args.semester),
        "division": args.division,
        "email": args.email,
        "mobile": args.mobile,
        "app_type": args.app_type,
        "purpose": args.purpose,
        "docs_attached": args.docs_attached,
        "doc_names": args.doc_names,
        "remarks": args.remarks,
    }
    if args.form_date:
        record["form_date"] = args.form_date
    return record


def main() -> int:
    args = build_parser().parse_args()

    record = build_record(args)

    output = args.output or (APP_DIR / "data" / "requisitions.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)

    pdf_bytes = build_pdf(record)

    # Persist the PDF to disk for inspection. This mirrors what the app stores
    # in the database, but keeps the CLI self-contained for quick previews.
    output.write_bytes(pdf_bytes)

    print(f"Generated requisition PDF: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
