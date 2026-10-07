"""Student Academic Requisition Portal  -  Streamlit front-end.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import hmac
import re
from datetime import timedelta

import pandas as pd
import pypdfium2 as pdfium
import streamlit as st
from PIL import Image

import config
import database as db
import notifications
import validators as V
from pdf_generator import build_pdf

st.set_page_config(page_title="Student Academic Requisition",
                   page_icon=Image.open(config.LOGO_PATH), layout="wide",
                   initial_sidebar_state="collapsed")


@st.cache_resource
def _init_once() -> bool:
    db.init_db()
    return True


_init_once()

# ------------------------------------------------------------------ styling
st.markdown(
    """
    <style>
      .block-container {padding-top: 3rem;}
      h1 {font-size: 1.5rem !important; margin-bottom: 0 !important;}
      .sec-title {font-weight: 700; letter-spacing: .02em; color: #1f2a6b;
                  border-left: 4px solid #c8102e; padding-left: .6rem; margin: .2rem 0 .6rem;}
      .badge {display:inline-block; padding: .18rem .7rem; border-radius: 999px;
              color:#fff; font-weight:600; font-size:.85rem;}
      .note {background:#f4f6fb; border:1px solid #dfe4f2; border-radius:8px;
             padding:.7rem .9rem; font-size:.88rem; color:#333;}
      .decl {background:#fffaf0; border:1px solid #f0dcae; border-radius:8px;
             padding:.8rem 1rem; font-size:.92rem; line-height:1.5;}
      .steps {display:flex; gap:.5rem; flex-wrap:wrap; margin:.2rem 0 .8rem;}
      .step {flex:1 1 140px; background:#fff; border:1px solid #e3e7f3; border-radius:10px;
             padding:.5rem .7rem; font-size:.82rem; color:#333;}
      .step b {color:#c8102e; display:block; font-size:.95rem;}
      .foot {color:#7a7f94; font-size:.78rem; text-align:center; margin-top:2rem;
             border-top:1px solid #e8eaf3; padding-top:.8rem;}
      div[data-testid="stMetricValue"] {font-size: 1.55rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ helpers
def section(title: str) -> None:
    st.markdown(f'<div class="sec-title">{title}</div>', unsafe_allow_html=True)


def badge(status: str) -> str:
    color = config.STATUS_COLORS.get(status, "#4a5568")
    return f'<span class="badge" style="background:{color}">{status}</span>'


def pdf_filename(roll_no: str, name: str) -> str:
    """Requisition_RollNo_StudentName.pdf (filesystem-safe)."""
    safe = lambda s: re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") or "NA"
    return f"Requisition_{safe(roll_no)}_{safe(name)}.pdf"


def render_preview(pdf_bytes: bytes):
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        return doc[0].render(scale=1.7).to_pil()
    finally:
        doc.close()


def save_uploads(req_no: str, files: list[tuple[str, bytes]]) -> None:
    if not files:
        return
    folder = config.UPLOAD_DIR / db.safe_dirname(req_no)
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in files:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)[-80:] or "document"
        (folder / safe).write_bytes(data)


def list_uploads(req_no: str):
    folder = config.UPLOAD_DIR / db.safe_dirname(req_no)
    return sorted(folder.iterdir()) if folder.exists() else []


# --------------------------------------------------------------- sidebar
staff = st.session_state.get("staff_user")
with st.sidebar:
    st.markdown("### Student Academic Requisition")
    st.caption(f"Normal processing time: **{config.SLA_WORKING_DAYS} working days**.")
    if config.HELPDESK:
        st.caption(f"Help: {config.HELPDESK}")
    st.divider()
    if staff:
        st.success(f"Signed in as **{staff}**")
        if st.button("Sign out", width="stretch"):
            st.session_state.pop("staff_user", None)
            st.rerun()
    else:
        st.markdown("**Institute staff login**")
        if db.login_locked():
            st.error("Too many failed attempts. Please try again in a few minutes.")
        else:
            with st.form("staff_login"):
                u = st.text_input("Username")
                pw = st.text_input("Password", type="password")
                go_login = st.form_submit_button("Sign in", type="primary")
            if go_login:
                users = config.staff_users()
                ok = u.strip() in users and hmac.compare_digest(
                    pw.encode(), users[u.strip()].encode())
                if ok:
                    st.session_state["staff_user"] = u.strip()
                    st.rerun()
                db.record_failed_login()
                st.error("Incorrect username or password.")
        if config.using_demo_credentials():
            st.caption("⚠️ Demo credentials active (admin / admin123). Configure "
                       "`ADMIN_PASSWORD` or `[admins]` secrets before going live.")

# students get a readable narrow column; staff get the full width for tables
st.markdown(f"<style>.block-container{{max-width:{1280 if staff else 880}px;}}</style>",
            unsafe_allow_html=True)

# ------------------------------------------------------------------- header
head_l, head_r = st.columns([1, 3], vertical_alignment="center")
with head_l:
    st.image(str(config.LOGO_PATH), width=150)
with head_r:
    st.title("Student Academic Requisition")
    st.caption(config.INSTITUTE_SUBTITLE)

tab_names = ["📝 New Requisition", "🔎 Track Status"] + (["🛠️ Staff Dashboard"] if staff else [])
tabs = st.tabs(tab_names)
tab_apply, tab_track = tabs[0], tabs[1]
tab_admin = tabs[2] if staff else None


# =========================================================================
# REVIEW DIALOG  (shown after validation passes; nothing is saved until confirmed)
# =========================================================================
@st.dialog("Review your requisition", width="large")
def review_dialog(record: dict, sig_bytes, doc_files: list[tuple[str, bytes]]):
    st.caption("This is a **preview**. Check every detail — once you confirm, a requisition "
               "number is issued and the application is submitted.")
    st.image(render_preview(build_pdf({**record, "req_no": "To be assigned"}, sig_bytes,
                                      draft=True)), width="stretch")
    dup = db.find_open_duplicate(record["roll_no"], record["app_type"])
    if dup:
        st.warning(f"You already have an open **{dup['app_type']}** request "
                   f"(**{dup['req_no']}**, status: {dup['status']}). Submit again only if "
                   "this is a different request.")
    c1, c2 = st.columns(2)
    if c1.button("✏️ Go back and edit", width="stretch"):
        st.rerun()
    if c2.button("✅ Confirm & Submit", type="primary", width="stretch"):
        with st.spinner("Submitting..."):
            try:
                saved = db.create_requisition(record, lambda rec: build_pdf(rec, sig_bytes))
                save_uploads(saved["req_no"], doc_files)
            except Exception as exc:                        # pragma: no cover
                st.error(f"Sorry, your request could not be saved: {exc}")
                return
            fname = pdf_filename(saved["roll_no"], saved["student_name"])
            emailed = notifications.notify_submission(saved, saved["pdf"], fname)
        st.session_state["result"] = {"req_no": saved["req_no"], "pdf": saved["pdf"],
                                      "filename": fname, "emailed_to": saved["email"] if emailed else ""}
        st.rerun()


# =========================================================================
# TAB 1 - APPLY
# =========================================================================
with tab_apply:
    v = st.session_state.setdefault("form_v", 0)
    k = lambda name: f"{name}_{v}"            # versioned keys -> one-click form reset

    result = st.session_state.get("result")
    if result:
        st.success(f"✅ Requisition submitted successfully  —  **{result['req_no']}**")
        c1, c2 = st.columns([3, 2])
        with c1:
            st.image(render_preview(result["pdf"]), caption="Your completed requisition form",
                     width="stretch")
        with c2:
            st.download_button("⬇️  Download PDF", data=result["pdf"],
                               file_name=result["filename"], mime="application/pdf",
                               type="primary", width="stretch")
            mail = (f"<br>📧 A copy was e-mailed to <b>{result['emailed_to']}</b>."
                    if result.get("emailed_to") else "")
            st.markdown(
                f"""
                <div class="note">
                <b>Next steps</b><br>
                1. Print the PDF and sign it (if you did not upload a signature).<br>
                2. Submit it to your <b>HoD</b> with the supporting documents.<br>
                3. Track progress in <b>Track Status</b> with<br>
                &nbsp;&nbsp;&nbsp;Requisition No. <b>{result['req_no']}</b> and your Roll No.<br><br>
                Normal processing time: <b>{config.SLA_WORKING_DAYS} working days</b>.{mail}
                </div>
                """, unsafe_allow_html=True)
            st.write("")
            if st.button("➕  Fill another requisition", width="stretch"):
                st.session_state["form_v"] = v + 1
                st.session_state.pop("result", None)
                st.rerun()
    else:
        st.markdown(
            '<div class="steps">'
            '<div class="step"><b>1</b>Fill in your details</div>'
            '<div class="step"><b>2</b>Choose the request &amp; purpose</div>'
            '<div class="step"><b>3</b>Accept declaration</div>'
            '<div class="step"><b>4</b>Review, submit &amp; download PDF</div></div>',
            unsafe_allow_html=True)
        st.markdown(f'<div class="note"><b>Processing Time:</b> {config.PROCESSING_NOTE}</div>',
                    unsafe_allow_html=True)
        st.caption("Fields marked * are mandatory. The PDF follows the institute's official "
                   "requisition format.")

        # ------------------------------------------------ 1. student details
        with st.container(border=True):
            section("1. STUDENT DETAILS")
            a, b = st.columns([3, 2])
            dept_choice = a.selectbox("Name of the Department *", config.DEPARTMENTS,
                                      index=None, placeholder="Select department",
                                      key=k("dept"))
            form_date = b.date_input("Date *", value=config.today(), max_value=config.today(),
                                     format="DD/MM/YYYY", key=k("date"))
            department = dept_choice or ""
            if dept_choice == config.OTHER_DEPARTMENT:
                department = st.text_input("Specify department *", max_chars=60,
                                           key=k("dept_other"))

            student_name = st.text_input("Name of Student *", max_chars=60,
                                         placeholder="As per college records", key=k("name"))
            r1, r2, r3 = st.columns([2, 1, 1])
            roll_no = r1.text_input("Roll No. *", max_chars=20, key=k("roll"))
            semester = r2.selectbox("Semester *", config.SEMESTERS, index=None,
                                    placeholder="Select", key=k("sem"))
            division = r3.text_input("Division *", max_chars=3, placeholder="e.g. A",
                                     key=k("div"))
            e1, e2 = st.columns(2)
            email = e1.text_input("Email *", max_chars=100, placeholder="name@example.com",
                                  key=k("email"))
            mobile = e2.text_input("Mobile Number *", max_chars=16,
                                   placeholder="10-digit number", key=k("mobile"))

            st.markdown("**Application for –** \\*")
            app_type = st.pills("Application type", config.APPLICATION_TYPES,
                                selection_mode="single", label_visibility="collapsed",
                                key=k("type"))
            other_details = ""
            if app_type == config.OTHER_TYPE:
                other_details = st.text_input("Please specify the request *", max_chars=80,
                                              key=k("other"))

        # ----------------------------------------------------- 2. purpose
        with st.container(border=True):
            section("2. PURPOSE / BRIEF DETAILS OF REQUEST")
            purpose = st.text_area("Purpose / Brief Details of Request *", height=140,
                                   max_chars=config.PURPOSE_MAX, label_visibility="collapsed",
                                   placeholder="Briefly describe why you need this and any "
                                               "details the office should know "
                                               "(e.g. bank name, company, exam, dates).",
                                   key=k("purpose"))

        # ------------------------------------------- 3. supporting documents
        with st.container(border=True):
            section("3. SUPPORTING DOCUMENTS")
            docs_choice = st.radio("Documents attached *", ["Yes", "No"], index=None,
                                   horizontal=True, key=k("docs"))
            doc_names, uploads = "", []
            if docs_choice == "Yes":
                doc_names = st.text_input("Document name(s) *", max_chars=150,
                                          placeholder="e.g. Fee receipt, Offer letter",
                                          key=k("docnames"))
                uploads = st.file_uploader(
                    f"Optionally upload the files (max {config.MAX_UPLOAD_FILES} files, "
                    f"{config.MAX_UPLOAD_MB} MB each)",
                    type=config.ALLOWED_DOC_TYPES, accept_multiple_files=True,
                    key=k("uploads")) or []

        # ------------------------------------------------ 4. declaration
        with st.container(border=True):
            section("4. STUDENT DECLARATION")
            st.markdown(f'<div class="decl">{config.DECLARATION}</div>', unsafe_allow_html=True)
            declaration = st.checkbox("I agree to the above declaration *", key=k("decl"))
            signature = st.file_uploader("Student signature (optional — PNG/JPG on a plain "
                                         "background; otherwise sign the printed copy)",
                                         type=["png", "jpg", "jpeg"], key=k("sig"))

        # ------------------------------------------------------- generate
        st.write("")
        if st.button("📄  Generate PDF", type="primary", width="stretch", key=k("gen")):
            mobile_norm = V.normalize_mobile(mobile)
            form = dict(
                department=V.clean(department), student_name=V.clean(student_name),
                roll_no=V.clean(roll_no).upper(), semester=semester,
                division=V.clean(division).upper(), email=V.clean(email).lower(),
                mobile=V.clean(mobile), app_type=app_type,
                other_details=V.clean(other_details), purpose=purpose,
                docs_attached=None if docs_choice is None else docs_choice == "Yes",
                doc_names=V.clean(doc_names), uploaded_names=[u.name for u in uploads],
                form_date=form_date, declaration=declaration,
            )
            names = [n.strip() for n in form["doc_names"].split(",") if n.strip()]
            for n in form["uploaded_names"]:
                if n.lower() not in (x.lower() for x in names):
                    names.append(n)
            form["all_doc_names"] = ", ".join(names)
            errors = V.validate_application(form)
            if form["docs_attached"]:
                errors += V.validate_uploads(uploads)
            errors += V.validate_signature(signature)

            if errors:
                st.error("Please fix the following before generating the PDF:\n\n"
                         + "\n".join(f"- {e}" for e in errors))
            else:
                record = dict(
                    department=form["department"], student_name=form["student_name"],
                    roll_no=form["roll_no"], semester=int(semester),
                    division=form["division"], email=form["email"],
                    mobile=f"+91 {mobile_norm}", app_type=app_type,
                    other_details=form["other_details"] if app_type == config.OTHER_TYPE else "",
                    purpose=re.sub(r"[ \t]+", " ", purpose.strip()),
                    docs_attached=form["docs_attached"],
                    doc_names=form["all_doc_names"] if form["docs_attached"] else "",
                    form_date=form_date.strftime("%d/%m/%Y"),
                )
                review_dialog(record, signature.getvalue() if signature else None,
                              [(u.name, u.getvalue()) for u in uploads]
                              if form["docs_attached"] else [])

# =========================================================================
# TAB 2 - TRACK STATUS
# =========================================================================
with tab_track:
    section("TRACK YOUR APPLICATION")
    with st.form("track_form"):
        t1, t2 = st.columns(2)
        q_req = t1.text_input("Requisition No.", placeholder="REQ-2026-0001")
        q_roll = t2.text_input("Roll No.")
        go = st.form_submit_button("Check status", type="primary")
    if go:
        st.session_state["track_q"] = (q_req.strip(), q_roll.strip())
    q = st.session_state.get("track_q")
    if q:
        rec = db.track(*q) if q[0] and q[1] else None
        if not rec:
            st.error("No matching requisition found. Please check the Requisition No. and "
                     "Roll No. (both are required).")
        else:
            rec = db._enrich(rec)
            st.markdown(f"### {rec['req_no']}  {badge(rec['status'])}", unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("Application", rec["app_type"])
            m2.metric("Submitted", rec["created_at"][:10])
            m3.metric("Last update", rec["updated_at"][:16])
            if rec["overdue"]:
                st.warning("This request has taken longer than the usual "
                           f"{config.SLA_WORKING_DAYS} working days. Please contact the "
                           "academic office" + (f" ({config.HELPDESK})." if config.HELPDESK else "."))
            if rec["remarks"]:
                st.info(f"**Remarks from office:** {rec['remarks']}")
            st.markdown("**Progress**")
            for h in rec["history"]:
                note = f" — {h['remarks']}" if h["remarks"] else ""
                st.markdown(f"- `{h['changed_at'][:16]}`  **{h['status']}**{note}")
            c_a, c_b = st.columns(2)
            pdf = db.get_pdf(rec["req_no"])
            if pdf:
                c_a.download_button("⬇️ Download PDF again", pdf,
                                    file_name=pdf_filename(rec["roll_no"], rec["student_name"]),
                                    mime="application/pdf", width="stretch")
            if rec["status"] == "Submitted":
                with c_b.popover("Withdraw application", width="stretch"):
                    st.write("Withdraw this request? This cannot be undone — you would need "
                             "to submit a new requisition.")
                    if st.button("Yes, withdraw", type="primary", key="withdraw_btn"):
                        db.withdraw(rec["req_no"], rec["roll_no"])
                        st.rerun()

# =========================================================================
# TAB 3 - STAFF DASHBOARD  (only exists for signed-in staff)
# =========================================================================
if tab_admin is not None:
    with tab_admin:
        s = db.stats()
        pending = sum(n for st_, n in s["by_status"].items() if st_ not in config.FINAL_STATUSES)
        m = st.columns(5)
        m[0].metric("Total", s["total"])
        m[1].metric("Today", s["today"])
        m[2].metric("Pending", pending)
        m[3].metric("Overdue", s["overdue"], help=f"Open for more than "
                    f"{config.SLA_WORKING_DAYS} working days")
        m[4].metric("Approved", s["by_status"].get("Approved", 0))
        if s["total"]:
            ch1, ch2 = st.columns(2)
            ch1.caption("Requests in the last 14 days")
            ch1.bar_chart(pd.Series(s["daily"]), height=190)
            ch2.caption("Requests by application type")
            ch2.bar_chart(pd.Series(s["by_type"]), horizontal=True, height=230)
            st.markdown(" ".join(f"{badge(k_)} **{n}**&nbsp;&nbsp;"
                                 for k_, n in s["by_status"].items()), unsafe_allow_html=True)

        st.divider()
        f1, f2, f3 = st.columns([3, 2, 2])
        text = f1.text_input("🔍 Search", placeholder="Name, roll no., req. no., email, mobile...")
        f_status = f2.selectbox("Status", ["All"] + config.STATUSES)
        f_type = f3.selectbox("Type", ["All"] + config.APPLICATION_TYPES)
        g1, g2, g3 = st.columns([3, 2, 2])
        f_dept = g1.selectbox("Department", ["All"] + config.DEPARTMENTS)
        overdue_only = g2.checkbox("Overdue only")
        use_dates = g3.checkbox("Filter by date")
        date_from = date_to = None
        if use_dates:
            rng = st.date_input("Submission date range",
                                value=(config.today() - timedelta(days=30), config.today()),
                                format="DD/MM/YYYY")
            if isinstance(rng, tuple) and len(rng) == 2:
                date_from, date_to = rng[0].isoformat(), rng[1].isoformat()

        rows = db.search(text, f_status, f_type, date_from, date_to, f_dept, overdue_only)
        st.caption(f"{len(rows)} record(s) — select a row to view or update it")
        if not rows:
            st.info("No requisitions match the current filters.")
        else:
            df = pd.DataFrame(rows)
            df["docs_attached"] = df["docs_attached"].map({1: "Yes", 0: "No"})
            df["sla"] = df["overdue"].map({True: "⚠️ Overdue", False: ""})
            df["submitted"] = df["created_at"].str[:10]
            show = df[["req_no", "submitted", "student_name", "roll_no",
                       "app_type", "status", "age_days", "sla"]]
            ev = st.dataframe(show, hide_index=True, width="stretch",
                              on_select="rerun", selection_mode="single-row",
                              column_config={"req_no": "Req. No.", "submitted": "Submitted",
                                             "student_name": "Student", "roll_no": "Roll No.",
                                             "app_type": "Type",
                                             "status": "Status", "age_days": "Age (wd)",
                                             "sla": "SLA"})
            st.download_button("⬇️ Export results (CSV)",
                               df.drop(columns=["overdue"]).to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"requisitions_{config.now():%Y%m%d_%H%M}.csv",
                               mime="text/csv")

            sel = ev.selection.rows
            if sel:
                r = rows[sel[0]]
                st.divider()
                st.markdown(f"#### {r['req_no']}  {badge(r['status'])}", unsafe_allow_html=True)
                if r["overdue"]:
                    st.warning(f"Overdue: open for {r['age_days']} working days "
                               f"(target {config.SLA_WORKING_DAYS}).")
                d_l, d_r = st.columns(2)
                d_l.markdown(
                    f"**Student:** {r['student_name']}  \n**Roll / Sem / Div:** {r['roll_no']} / "
                    f"{r['semester']} / {r['division']}  \n**Department:** {r['department']}  \n"
                    f"**Email:** {r['email']}  \n**Mobile:** {r['mobile']}")
                other = f" ({r['other_details']})" if r["other_details"] else ""
                d_r.markdown(
                    f"**Application:** {r['app_type']}{other}  \n**Form date:** {r['form_date']}  \n"
                    f"**Submitted:** {r['created_at']}  \n"
                    f"**Documents:** {r['doc_names'] if r['docs_attached'] else 'None'}")
                st.markdown("**Purpose**")
                st.text(r["purpose"])

                for fpath in list_uploads(r["req_no"]):
                    st.download_button(f"📎 {fpath.name}", fpath.read_bytes(),
                                       file_name=fpath.name, key=f"f_{r['req_no']}_{fpath.name}")
                pdf = db.get_pdf(r["req_no"])
                if pdf:
                    st.download_button("⬇️ Download requisition PDF", pdf,
                                       file_name=pdf_filename(r["roll_no"], r["student_name"]),
                                       mime="application/pdf", key=f"pdf_{r['req_no']}")

                with st.form(f"upd_{r['req_no']}"):
                    u1, u2 = st.columns([1, 2])
                    new_status = u1.selectbox("Update status", config.STATUSES,
                                              index=config.STATUSES.index(r["status"]))
                    new_rem = u2.text_input("Remarks (visible to student)", value=r["remarks"],
                                            max_chars=200)
                    notify = st.checkbox("E-mail the student about this change",
                                         value=notifications.enabled(),
                                         disabled=not notifications.enabled(),
                                         help=None if notifications.enabled()
                                         else "E-mail (SMTP) is not configured.")
                    if st.form_submit_button("Save update", type="primary"):
                        db.update_status(r["req_no"], new_status, new_rem.strip(), by=staff)
                        if notify:
                            notifications.notify_status(r["email"], r["req_no"], new_status,
                                                        new_rem.strip())
                        st.success("Status updated.")
                        st.rerun()
                with st.expander("Status history (audit trail)"):
                    for h in db.history(r["req_no"]):
                        note = f" — {h['remarks']}" if h["remarks"] else ""
                        st.markdown(f"- `{h['changed_at'][:16]}` **{h['status']}**{note} "
                                    f"*({h['changed_by']})*")

# ------------------------------------------------------------------- footer
st.markdown(
    '<div class="foot">Your details are used only to process this request and are visible '
    'to authorised institute staff. · Institute staff: sign in from the sidebar (top-left arrow).'
    '</div>', unsafe_allow_html=True)
