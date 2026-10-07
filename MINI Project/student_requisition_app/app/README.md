# Student Academic Requisition Portal

A Streamlit web app that lets a student fill in the institute's **Student Academic
Requisition Form** online and download it as a PDF that reproduces the official form
(header box, processing note, sections 1-6). Official-use fields — HoD signature/remarks,
Forwarded To, Principal decision/remarks/signature — are printed **blank**, as on the
supplied form.

## Features

**Student side**

| Requirement | Implementation |
|---|---|
| Online form, all fields | Department, name, roll no., semester, division, email + mobile, the 9 application types printed on the form, purpose, documents Yes/No + names, date |
| Declaration + checkbox | Exact wording from the form; nothing can be generated until accepted |
| PDF generation | ReportLab, one A4 page laid out section-by-section like the supplied form |
| **Review before submit** | A watermarked *PREVIEW* of the exact PDF appears first; a requisition number is issued only after the student confirms |
| Download PDF | `Requisition_<RollNo>_<StudentName>.pdf` |
| Validation | Mandatory fields, 10-digit Indian mobile (+91/spaces tolerated), email format, no future dates, declaration, text-must-fit-the-form checks, upload content sniffing (a renamed `.exe` is rejected). All errors listed at once |
| Duplicate warning | Warns if the student already has an open request of the same type |
| Track status | Needs Requisition No. **and** Roll No.; full history; student can **withdraw** while still "Submitted" |
| E-mail (optional) | PDF e-mailed on submission, and on every status change, when SMTP is configured |

**Staff side** (sign in from the sidebar — the dashboard does not exist for students)

* Named staff accounts (`[admins]` secrets / `ADMIN_USERS`) → every status change is recorded with **who** made it (audit trail); brute-force throttle on login.
* KPIs: total, today, pending, **overdue**; 14-day trend and per-type charts.
* **SLA tracking:** the form promises 4 working days — requests older than that (weekends and `HOLIDAYS` excluded) are flagged ⚠️ Overdue and filterable.
* Search (name, roll, req. no., email, mobile, purpose) + filters (status, type, department, dates, overdue); CSV export; per-request PDF and uploaded documents; status update with remarks visible to the student.

**Under the hood:** SQLite with atomic numbering (`REQ-2026-0001`; a failed PDF rolls everything back), institute-timezone clock (`Asia/Kolkata`, not the host's UTC), parameterised SQL, sanitised file names, QR code on every PDF, mobile-friendly UI.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Staff accounts: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and edit
`[admins]` (or set `ADMIN_USERS="alice:pw1,bob:pw2"` / `ADMIN_PASSWORD`). With nothing configured
the demo login `admin` / `admin123` is active and a warning is shown — never deploy like that.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q          # 51 tests: validation, DB, SLA, auth, uploads, e-mail, PDF content
```

## Deploy (Streamlit Community Cloud — free)

1. Push this folder to a GitHub repository (the `data/` folder is git-ignored).
2. On share.streamlit.io choose **New app**, pick the repo, main file `app.py`.
3. Under **Advanced settings → Secrets** paste your edited `secrets.toml.example`.
4. Deploy and submit the generated `https://<name>.streamlit.app` link.

**Production (recommended for a real rollout):** use the included `Dockerfile` on a host with a
persistent volume (Render, Railway, Fly.io, or a college server) — see the header of the Dockerfile.

> **Note:** Community Cloud's disk is ephemeral — the SQLite file and uploaded documents are
> lost when the app restarts or redeploys. For real use deploy on a host with a persistent
> volume (Render/Railway/VPS) and point `REQ_DATA_DIR` at it, or swap SQLite for a hosted DB.
> Admins can export CSV at any time.

## Project structure

```
app.py              Streamlit UI (apply / track / admin)
pdf_generator.py    Draws the requisition form (ReportLab)
database.py         SQLite layer: numbering, records, history, search, stats
validators.py       All validation rules
notifications.py    Optional SMTP e-mails
config.py           Form wording, types, departments, statuses, SLA, timezone, staff users
assets/             Institute logo + bundled DejaVu fonts (Unicode names work)
tests/              pytest suite
sample_output/      Sample generated PDF
screenshots/        Screenshots of the working app
```

## Customising

Departments, application types, statuses, SLA days, holidays, timezone and the
declaration/processing-note wording are all in `config.py`. Page coordinates for the PDF are in `pdf_generator.py` (`build_pdf`).

## Known limitations (honest list)

* Students are not authenticated — anyone can submit under any roll number. Production fix:
  college SSO / e-mail OTP. The HoD/Principal sign the printed form, which remains the legal record.
* Staff roles are flat (no per-department HoD scoping yet).
* The login throttle is global, because Streamlit does not expose client IPs.
