"""Generates the Student Academic Requisition Form PDF.

The page reproduces the institute's supplied template section-by-section
(header box, processing note, sections 1-6) on a single A4 page. Student-filled
values are printed on the form's lines; the official-use fields (HoD, Forwarded
To, Principal Office) are intentionally left blank.
"""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from PIL import Image
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

import config

W, H = A4
LM = 49.6                 # left margin  (matches form: 993 twips)
RM = W - 49.5             # right edge   (matches form: 991 twips)
CW = RM - LM              # content width

REG, BOLD = "DVSans", "DVSans-Bold"
INK = (0, 0, 0)
LINE = (0.25, 0.25, 0.25)
GREY = (0.45, 0.45, 0.45)
VALUE_INK = (0.05, 0.12, 0.45)   # filled-in values print in dark blue so they
                                 # are distinguishable from the printed form

_fonts_ready = False


def _register_fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    pdfmetrics.registerFont(TTFont(REG, str(config.FONT_REGULAR)))
    pdfmetrics.registerFont(TTFont(BOLD, str(config.FONT_BOLD)))
    pdfmetrics.registerFontFamily(REG, normal=REG, bold=BOLD, italic=REG, boldItalic=BOLD)
    _fonts_ready = True


def Y(t: float) -> float:
    """Convert a top-down coordinate (distance from page top) to PDF y."""
    return H - t


# ----------------------------------------------------------------- helpers
def _fit_size(text: str, font: str, size: float, max_w: float, min_size: float = 6.0) -> float:
    while size > min_size and stringWidth(text, font, size) > max_w:
        size -= 0.25
    return size


def _blank_line(c, x1, x2, t, width=0.6):
    c.setStrokeColorRGB(*LINE)
    c.setLineWidth(width)
    c.line(x1, Y(t), x2, Y(t))


def _label(c, x, t, text, bold=False, size=9.5):
    c.setFillColorRGB(*INK)
    c.setFont(BOLD if bold else REG, size)
    c.drawString(x, Y(t), text)
    return x + stringWidth(text, BOLD if bold else REG, size)


def _value_on_line(c, x1, x2, t, value, size=9.5, align="left"):
    """Draw an underline from x1..x2 and print `value` sitting on it."""
    _blank_line(c, x1, x2, t + 2.2)
    if not value:
        return
    avail = x2 - x1 - 4
    fs = _fit_size(value, REG, size, avail)
    c.setFillColorRGB(*VALUE_INK)
    c.setFont(REG, fs)
    if align == "center":
        c.drawCentredString((x1 + x2) / 2, Y(t) + 1.2, value)
    else:
        c.drawString(x1 + 2, Y(t) + 1.2, value)
    c.setFillColorRGB(*INK)


def _checkbox(c, x, t, checked=False, size=9):
    """Square checkbox whose top-left is (x, t_top); ticked with a drawn check."""
    y = Y(t) - 1.5
    c.setStrokeColorRGB(*INK)
    c.setLineWidth(0.8)
    c.rect(x, y, size, size, stroke=1, fill=0)
    if checked:
        c.setStrokeColorRGB(*VALUE_INK)
        c.setLineWidth(1.6)
        p = c.beginPath()
        p.moveTo(x + 1.6, y + size * 0.50)
        p.lineTo(x + size * 0.42, y + 1.8)
        p.lineTo(x + size - 1.2, y + size - 1.4)
        c.drawPath(p, stroke=1, fill=0)
    return x + size


def _para(c, html, x, t_top, width, size=9, leading=12.5, align=TA_JUSTIFY):
    style = ParagraphStyle("p", fontName=REG, fontSize=size, leading=leading,
                           alignment=align, textColor=INK)
    p = Paragraph(html, style)
    _, h = p.wrap(width, 1000)
    p.drawOn(c, x, Y(t_top) - h)
    return t_top + h


def _heading(c, t, text):
    _label(c, LM, t, text, bold=True, size=10)


def _signature_png(raw: bytes | None) -> ImageReader | None:
    """Turn an uploaded signature into a transparent-background PNG."""
    if not raw:
        return None
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return None
    im.thumbnail((600, 220))
    px = im.load()
    for yy in range(im.height):
        for xx in range(im.width):
            r, g, b, a = px[xx, yy]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            if lum > 225:
                px[xx, yy] = (r, g, b, 0)           # white paper -> transparent
            elif a:
                px[xx, yy] = (r, g, b, min(a, 255))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    buf.seek(0)
    return ImageReader(buf)



# ----------------------------------------------------- text-fit helpers
PURPOSE_RULES = 5          # ruled lines printed in section 2
PURPOSE_MIN_FONT = 8.0


def purpose_layout(text: str) -> tuple[list[str], float, bool]:
    """Wrap `text` for the ruled lines of section 2.

    Returns (lines, font_size, fits). The font shrinks (down to 8 pt) to fit
    PURPOSE_RULES lines; `fits` is False if it still does not fit.
    """
    _register_fonts()
    text = (text or "").strip()
    fs = 9.5
    while True:
        lines: list[str] = []
        for para in text.splitlines() or [""]:
            lines += simpleSplit(para, REG, fs, CW - 4) or [""]
        if len(lines) <= PURPOSE_RULES or fs <= PURPOSE_MIN_FONT:
            return lines, fs, len(lines) <= PURPOSE_RULES
        fs -= 0.5


def doc_names_layout(names: str) -> tuple[str, list[str], bool]:
    """Wrap document names over the form's (shorter) first line + one full line.

    Returns (first_line, extra_lines, fits). Only ONE extra line is available.
    """
    _register_fonts()
    names = (names or "").strip()
    label_w = stringWidth("Document name(s), if applicable:", REG, 9.5)
    first_w = CW - label_w - 5 - 4
    if not names:
        return "", [], True
    first = (simpleSplit(names, REG, 9, first_w) or [""])[0]
    rest = names[len(first):].strip()
    extra = simpleSplit(rest, REG, 9, CW - 4) if rest else []
    return first, extra, len(extra) <= 1

# ------------------------------------------------------------ main builder
def build_pdf(data: dict, signature_bytes: bytes | None = None, draft: bool = False) -> bytes:
    """Return the completed requisition form as PDF bytes.

    `data` keys: req_no, department, student_name, roll_no, semester, division,
    email, mobile, app_type, other_details, purpose, docs_attached (bool),
    doc_names, form_date (dd/mm/yyyy str).
    """
    _register_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Student Academic Requisition - {data.get('req_no', '')}")
    c.setAuthor("Student Academic Requisition Portal")
    c.setSubject("Student Academic Requisition Form")

    if draft:                                   # review-screen preview only
        c.saveState()
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.setFillAlpha(0.13)
        c.setFont(BOLD, 92)
        c.translate(W / 2, H / 2)
        c.rotate(38)
        c.drawCentredString(0, 0, "PREVIEW")
        c.restoreState()

    # ---------------------------------------------------------- header box
    box_t, box_h, split_x = 26, 58, LM + 168
    c.setStrokeColorRGB(*INK)
    c.setLineWidth(0.9)
    c.rect(LM, Y(box_t + box_h), CW, box_h, stroke=1, fill=0)
    c.line(split_x, Y(box_t), split_x, Y(box_t + box_h))
    if config.LOGO_PATH.exists():
        lw = 98
        lh = lw * 73 / 199
        c.drawImage(str(config.LOGO_PATH), LM + (168 - lw) / 2, Y(box_t + 5 + lh),
                    width=lw, height=lh, mask="auto")
    c.setFont(REG, 5.6)
    c.setFillColorRGB(*INK)
    c.drawCentredString(LM + 84, Y(box_t + box_h - 6), config.INSTITUTE_SUBTITLE)
    # Title on two lines, centred in the right cell
    cx = (split_x + RM) / 2
    c.setFont(BOLD, 14.5)
    c.drawCentredString(cx, Y(box_t + 26), "STUDENT ACADEMIC REQUISITION")
    c.drawCentredString(cx, Y(box_t + 44), "FORM")

    # ----------------------------------------- department / outward / date
    t = 106
    x = _label(c, LM, t, "Name of the Department.:", bold=True)
    _value_on_line(c, x + 4, LM + 292, t, data.get("department", ""))
    x = _label(c, LM + 305, t, "Department Outward No.:", bold=True)
    _blank_line(c, x + 4, RM, t + 2.2)           # filled by the department

    t = 126
    x = _label(c, LM, t, "Date:", bold=True)
    _value_on_line(c, x + 4, x + 96, t, data.get("form_date", ""), align="center")
    x = _label(c, LM + 305, t, "Requisition No.:", bold=True)
    _value_on_line(c, x + 4, RM, t, data.get("req_no", ""))

    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.9)
    c.line(LM, Y(135), RM, Y(135))

    # ------------------------------------------------------ processing note
    t = _para(c, f"<b>Processing Time:</b> {escape(config.PROCESSING_NOTE)}",
              LM, 144, CW, size=9, leading=12.3)
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.setLineWidth(0.5)
    c.line(LM, Y(t + 5), RM, Y(t + 5))

    # ----------------------------------------------------- 1. student details
    t += 20
    _heading(c, t, "1. STUDENT DETAILS")

    t += 20
    x = _label(c, LM, t, "Name of Student:")
    _value_on_line(c, x + 6, LM + 400, t, data.get("student_name", ""))

    t += 23
    x = _label(c, LM, t, "Roll No.:")
    _value_on_line(c, x + 5, LM + 150, t, data.get("roll_no", ""))
    x = _label(c, LM + 170, t, "Semester:")
    _value_on_line(c, x + 5, x + 52, t, str(data.get("semester", "")), align="center")
    x = _label(c, LM + 290, t, "Division:")
    _value_on_line(c, x + 5, x + 52, t, data.get("division", ""), align="center")

    t += 23
    x = _label(c, LM, t, "Email / Mobile:")
    contact = " / ".join(v for v in (data.get("email", ""), data.get("mobile", "")) if v)
    _value_on_line(c, x + 6, RM - 20, t, contact)

    # ---- application type: the printed sentence with the chosen option marked
    t += 25
    selected = data.get("app_type", "")
    size = 9.5
    items = [("Application for – ", None)]
    for i, opt in enumerate(config.APPLICATION_TYPES):
        items.append((opt, opt))
        items.append(("/ " if i < len(config.APPLICATION_TYPES) - 1 else ".", None))
    cur_x, line_t, lead = LM, t, 17
    for text, opt in items:
        is_sel = opt is not None and opt == selected
        font = BOLD if is_sel else REG
        w = stringWidth(text, font, size)
        if cur_x + w > RM and text.strip(" ") not in ("/", "."):
            cur_x, line_t = LM, line_t + lead
        if is_sel:
            cur_x += 4
            c.setFillColorRGB(0.88, 0.91, 1.0)
            c.setStrokeColorRGB(*VALUE_INK)
            c.setLineWidth(0.9)
            c.roundRect(cur_x - 2.5, Y(line_t) - 3.2, w + 5, size + 4.6, 2.5, stroke=1, fill=1)
            c.setFillColorRGB(*VALUE_INK)
        else:
            c.setFillColorRGB(*INK)
        c.setFont(font, size)
        c.drawString(cur_x, Y(line_t), text)
        cur_x += w + (5 if is_sel else 0)
    t = line_t
    if selected == config.OTHER_TYPE:
        t += 21
        x = _label(c, LM, t, "Other request (please specify):")
        _value_on_line(c, x + 5, RM, t, data.get("other_details", ""))

    # ----------------------------------------------------------- 2. purpose
    t += 26
    _heading(c, t, "2. PURPOSE / BRIEF DETAILS OF REQUEST")
    rule_gap, n_rules = 15.5, PURPOSE_RULES
    lines, fs, _ = purpose_layout(data.get("purpose", ""))
    lines = lines[:n_rules]
    first = t + 19
    for i in range(n_rules):
        rt = first + i * rule_gap
        _blank_line(c, LM, RM, rt + 2.4, 0.5)
        if i < len(lines) and lines[i]:
            c.setFillColorRGB(*VALUE_INK)
            c.setFont(REG, fs)
            c.drawString(LM + 2, Y(rt) + 1.2, lines[i])
    t = first + (n_rules - 1) * rule_gap

    # ------------------------------------------------- 3. supporting documents
    t += 28
    _heading(c, t, "3. SUPPORTING DOCUMENTS")
    t += 20
    x = _label(c, LM, t, "Documents attached:")
    attached = bool(data.get("docs_attached"))
    x = _checkbox(c, x + 10, t, checked=attached) + 4
    x = _label(c, x, t, "Yes")
    x = _checkbox(c, x + 22, t, checked=not attached) + 4
    _label(c, x, t, "No")
    t += 20
    x = _label(c, LM, t, "Document name(s), if applicable:")
    names = data.get("doc_names", "") if attached else ""
    first_line, extra, _ = doc_names_layout(names)
    _value_on_line(c, x + 5, RM, t, first_line, size=9)
    if extra:
        t += 15
        _value_on_line(c, LM, RM, t, extra[0], size=9)

    # ------------------------------------------------------ 4. declaration
    t += 26
    _heading(c, t, "4. STUDENT DECLARATION")
    t = _para(c, escape(config.DECLARATION), LM, t + 8, CW, size=9, leading=12.3)

    t += 34
    x = _label(c, LM, t, "Student Signature:")
    sig = _signature_png(signature_bytes)
    sig_x1, sig_x2 = x + 6, x + 148
    _blank_line(c, sig_x1, sig_x2, t + 2.2, 0.7)
    if sig:
        iw, ih = sig.getSize()
        max_w, max_h = sig_x2 - sig_x1 - 6, 31
        scale = min(max_w / iw, max_h / ih)
        c.drawImage(sig, sig_x1 + 3, Y(t) - 1.0, width=iw * scale, height=ih * scale,
                    mask="auto")
    x = _label(c, LM + 300, t, "Date:")
    _value_on_line(c, x + 5, x + 100, t, data.get("form_date", ""), align="center")

    # ------------------------------------------------------ 5. HoD section
    t += 28
    x = _label(c, LM, t, "5. HoD Signature:", bold=True, size=10)
    _blank_line(c, x + 8, x + 138, t + 2.2, 0.7)
    x = _label(c, LM + 255, t, "Remarks:", bold=True, size=10)
    _blank_line(c, x + 6, RM, t + 2.2, 0.5)

    t += 18
    t = _para(c, f"<b>Forwarded to</b> {escape(config.FORWARDED_TO)}", LM, t - 9, CW,
              size=9, leading=12.3, align=TA_LEFT)

    t += 22
    x = _label(c, LM, t, "Signature:", bold=True, size=9.5)
    _blank_line(c, x + 8, x + 138, t + 2.2, 0.7)
    x = _label(c, LM + 255, t, "Remarks:", bold=True, size=9.5)
    _blank_line(c, x + 6, RM, t + 2.2, 0.5)

    # --------------------------------------------- 6. principal office use
    t += 26
    _heading(c, t, "6. PRINCIPAL OFFICE USE ONLY")
    t += 20
    x = _label(c, LM, t, "Decision by Principal.:")
    x = _checkbox(c, x + 12, t) + 4
    x = _label(c, x, t, "Approved")
    x = _checkbox(c, x + 16, t) + 4
    x = _label(c, x, t, "Not Approved")
    x = _checkbox(c, x + 16, t) + 4
    _label(c, x, t, "Clarification Required")
    t += 21
    x = _label(c, LM, t, "Remarks (if any):")
    _blank_line(c, x + 5, RM, t + 2.2, 0.5)
    t += 23
    x = _label(c, LM, t, "Principal Signature:")
    _blank_line(c, x + 6, x + 150, t + 2.2, 0.7)

    # ----------------------------------------------------------------- footer
    stamp = config.now().strftime("%d/%m/%Y %H:%M")
    c.setFont(REG, 6.3)
    c.setFillColorRGB(*GREY)
    c.drawString(LM, 28, f"Requisition No. {data.get('req_no', '')}  |  Generated on {stamp} "
                         f"via the Student Academic Requisition Portal")
    c.drawString(LM, 20, "Fields printed in blue were entered by the student. "
                         "HoD / Forwarded To / Principal Office sections are for official use.")
    payload = f"{data.get('req_no', '')}|{data.get('roll_no', '')}"
    code = qr.QrCodeWidget(payload)
    bx0, by0, bx1, by1 = code.getBounds()
    size_q = 40
    d = Drawing(size_q, size_q, transform=[size_q / (bx1 - bx0), 0, 0, size_q / (by1 - by0), 0, 0])
    d.add(code)
    renderPDF.draw(d, c, RM - size_q, 14)

    c.showPage()
    c.save()
    return buf.getvalue()


if __name__ == "__main__":      # quick manual test
    demo = dict(
        req_no="REQ-2026-0001", department="Computer Engineering",
        student_name="Aarav Sharma", roll_no="CMPN2301", semester=5, division="B",
        email="aarav.sharma@example.com", mobile="9876543210", app_type="Bonafide",
        other_details="", purpose="I need a bonafide certificate for submission to the bank "
        "for an education loan application.", docs_attached=True,
        doc_names="Fee receipt, ID card copy", form_date="07/10/2026",
    )
    with open("/tmp/demo.pdf", "wb") as f:
        f.write(build_pdf(demo))
