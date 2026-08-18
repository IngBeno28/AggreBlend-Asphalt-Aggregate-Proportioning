"""
pdf_report.py
--------------
Generates a branded PDF report for the Asphalt Coarse Aggregate
Proportioning Calculator, matching the look of Automation_hub's other
tools (cover page with logo + project info table, results page, full-page
charts, and a certification page, with a running footer on every page).

No Streamlit imports here either — this can be unit tested by calling
build_pdf_report() directly with plain data.
"""

import io
import os
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    HRFlowable, Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# =======================================================================
# Branding constants — shared across Automation_hub's tools. Edit these
# in one place to rebrand every report this module produces.
# =======================================================================
APP_NAME = "Asphalt Aggregate Proportioning Calculator"
APP_SHORT_NAME = "Asphalt Proportioning Calculator"
APP_TAGLINE = "Built for engineering precision"
COMPANY_NAME = "Automation_hub Engineering Group Limited"
COMPANY_PHONE = "+233501365878/+233256346244"
COMPANY_WEB = "https://automationapps.streamlit.app/"

# Drop an actual logo PNG at this path (relative to this file) to replace
# the generated placeholder badge below with your real Automation_hub mark.
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")

BRAND_BLUE = colors.HexColor("#1a56db")
BRAND_TEAL = colors.HexColor("#0f766e")
TEXT_GRAY = colors.HexColor("#4b5563")
LIGHT_GRAY_BG = colors.HexColor("#f3f4f6")
BORDER_GRAY = colors.HexColor("#d1d5db")
FAIL_BG = colors.HexColor("#fddede")
FAIL_TEXT = colors.HexColor("#b91c1c")
PASS_TEXT = colors.HexColor("#15803d")

PAGE_SIZE = A4
MARGIN = 20 * mm


# =======================================================================
# Placeholder logo (used only if LOGO_PATH doesn't exist)
# =======================================================================
def _placeholder_logo_flowable(size_mm=24):
    """Draw a simple circular 'AH' badge with PIL so the report has a
    logo even before a real brand asset is supplied."""
    from PIL import Image as PILImage, ImageDraw, ImageFont

    px = 300
    img = PILImage.new("RGBA", (px, px), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, px - 4, px - 4), fill=(15, 118, 110, 255))
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 110
        )
    except Exception:
        font = ImageFont.load_default()
    text = "AH"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((px - tw) / 2 - bbox[0], (px - th) / 2 - bbox[1]), text,
               fill=(255, 255, 255, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    flow = Image(buf, width=size_mm * mm, height=size_mm * mm)
    flow.hAlign = "CENTER"
    return flow


def _logo_flowable(max_w_mm=45, max_h_mm=28):
    """Fit the real logo (if present) within a bounding box, preserving its
    aspect ratio — most company marks aren't perfectly square, and forcing
    one into a square would stretch/distort it."""
    if os.path.exists(LOGO_PATH):
        from PIL import Image as PILImage
        try:
            w_px, h_px = PILImage.open(LOGO_PATH).size
        except Exception:
            return _placeholder_logo_flowable()
        aspect = h_px / w_px
        width = max_w_mm * mm
        height = width * aspect
        if height > max_h_mm * mm:
            height = max_h_mm * mm
            width = height / aspect
        flow = Image(LOGO_PATH, width=width, height=height)
        flow.hAlign = "CENTER"
        return flow
    return _placeholder_logo_flowable()


# =======================================================================
# Paragraph styles
# =======================================================================
def _styles():
    return {
        "title": ParagraphStyle(
            "ReportTitle", fontName="Helvetica-Bold", fontSize=22,
            textColor=BRAND_BLUE, alignment=TA_CENTER, spaceBefore=10, spaceAfter=4,
            leading=26,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle", fontName="Helvetica", fontSize=11,
            textColor=TEXT_GRAY, alignment=TA_CENTER, spaceAfter=6,
        ),
        "section_header": ParagraphStyle(
            "SectionHeader", fontName="Helvetica-Bold", fontSize=13,
            textColor=colors.HexColor("#111827"), alignment=TA_LEFT,
            spaceBefore=10, spaceAfter=6,
        ),
        "status_pass": ParagraphStyle(
            "StatusPass", fontName="Helvetica-Bold", fontSize=16,
            textColor=PASS_TEXT, alignment=TA_CENTER, spaceBefore=2, spaceAfter=8,
        ),
        "status_fail": ParagraphStyle(
            "StatusFail", fontName="Helvetica-Bold", fontSize=16,
            textColor=FAIL_TEXT, alignment=TA_CENTER, spaceBefore=2, spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body", fontName="Helvetica", fontSize=10, textColor=colors.black,
            alignment=TA_LEFT, spaceAfter=6, leading=14,
        ),
        "body_bold": ParagraphStyle(
            "BodyBold", fontName="Helvetica-Bold", fontSize=10,
            textColor=colors.black, alignment=TA_LEFT, spaceAfter=6,
        ),
        "italic_center": ParagraphStyle(
            "ItalicCenter", fontName="Helvetica-Oblique", fontSize=9,
            textColor=TEXT_GRAY, alignment=TA_CENTER,
        ),
        "italic_left": ParagraphStyle(
            "ItalicLeft", fontName="Helvetica-Oblique", fontSize=8.5,
            textColor=TEXT_GRAY, alignment=TA_LEFT,
        ),
        "cert_title": ParagraphStyle(
            "CertTitle", fontName="Helvetica-Bold", fontSize=18,
            textColor=colors.HexColor("#111827"), alignment=TA_CENTER, spaceAfter=14,
        ),
        "chart_title": ParagraphStyle(
            "ChartTitle", fontName="Helvetica-Bold", fontSize=14,
            textColor=colors.HexColor("#111827"), alignment=TA_CENTER, spaceAfter=10,
        ),
    }


# =======================================================================
# Footer with page numbers (two-pass canvas, standard reportlab recipe)
# =======================================================================
def _make_footer_canvas():
    class FooterCanvas(pdfcanvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            page_count = len(self._saved_page_states)
            for i, state in enumerate(self._saved_page_states):
                self.__dict__.update(state)
                self._draw_footer(i + 1, page_count)
                super().showPage()
            super().save()

        def _draw_footer(self, page_num, page_count):
            width, _ = PAGE_SIZE
            y = 14 * mm
            self.saveState()
            self.setStrokeColor(BORDER_GRAY)
            self.setLineWidth(0.5)
            self.line(MARGIN, y + 11, width - MARGIN, y + 11)
            self.setFont("Helvetica", 8)
            self.setFillColor(TEXT_GRAY)
            left = f"{COMPANY_NAME} | © {datetime.now().year} {APP_SHORT_NAME} | {APP_TAGLINE}"
            self.drawString(MARGIN, y + 3, left)
            self.drawRightString(width - MARGIN, y + 3, f"Page {page_num}/{page_count}")
            self.drawString(MARGIN, y - 6, f"Tel: {COMPANY_PHONE} | Web: {COMPANY_WEB}")
            self.restoreState()

    return FooterCanvas


# =======================================================================
# Chart embedding helper
# =======================================================================
def _fig_to_flowable(fig, max_width_mm=160, max_height_mm=190):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight")
    buf.seek(0)
    from PIL import Image as PILImage
    w_px, h_px = PILImage.open(buf).size
    buf.seek(0)
    aspect = h_px / w_px
    width = max_width_mm * mm
    height = width * aspect
    if height > max_height_mm * mm:
        height = max_height_mm * mm
        width = height / aspect
    flow = Image(buf, width=width, height=height)
    flow.hAlign = "CENTER"
    return flow


def _info_table(rows, col_widths=(45 * mm, 105 * mm)):
    tbl = Table(rows, colWidths=list(col_widths))
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl


# =======================================================================
# Main entry point
# =======================================================================
def build_pdf_report(
    project_info,      # dict: project_name, prepared_for, prepared_by, engineer_name, report_date
    target_info,        # dict: mix_type, course, designation, nmas
    blend_options,       # list of {label, note, n_fail, weights_df} for the comparison table
    selected_label,      # label of the blend used for the detailed section below
    prop_df,             # DataFrame: Stockpile | Optimized % | Rounded %  (selected blend)
    result_df,           # DataFrame: Sieve | Lower spec | Upper spec | Blend % passing | Status
    n_fail,              # int, sieves failing for the selected blend
    gradation_fig=None,  # matplotlib Figure
    proportions_fig=None,  # matplotlib Figure
):
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=PAGE_SIZE, topMargin=MARGIN, bottomMargin=30 * mm,
        leftMargin=MARGIN, rightMargin=MARGIN, title=f"{APP_NAME} Report",
    )
    story = []

    # ---------------- Page 1: cover ----------------
    story.append(Spacer(1, 6 * mm))
    story.append(_logo_flowable())
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Asphalt Aggregate Proportioning Report", styles["title"]))
    subtitle = (
        f"{escape(str(target_info['mix_type']))} – {escape(str(target_info['course']))} "
        f"– {escape(str(target_info['designation']))} Gradation Specification"
    )
    story.append(Paragraph(subtitle, styles["subtitle"]))
    story.append(HRFlowable(width="55%", thickness=1.4, color=BRAND_BLUE, spaceAfter=10, hAlign="CENTER"))
    story.append(Spacer(1, 6 * mm))

    info_rows = [
        ["Project", escape(str(project_info.get("project_name") or "Unnamed Project"))],
        ["Prepared For", escape(str(project_info.get("prepared_for") or "-"))],
        ["Prepared By", escape(str(project_info.get("prepared_by") or COMPANY_NAME))],
        ["Date Generated", escape(str(project_info.get("report_date") or ""))],
        ["Target Mix", subtitle.replace(" Gradation Specification", "")],
        ["Blend Options Evaluated", str(len(blend_options))],
    ]
    story.append(_info_table(info_rows))
    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph(
        f"© {datetime.now().year} {APP_SHORT_NAME} | {APP_TAGLINE}", styles["italic_center"],
    ))
    story.append(PageBreak())

    # ---------------- Page 2: blend comparison + selected blend ----------------
    story.append(Paragraph("Trial Blend Comparison", styles["section_header"]))
    story.append(Paragraph(
        "Three trial blends were evaluated across the spec band — coarse-leaning, "
        "balanced (mid-band), and fine-leaning — following standard trial-blend practice. "
        f"The <b>{escape(selected_label)}</b> blend is carried forward as the recommended "
        "job-mix formula below.", styles["body"],
    ))
    cmp_rows = [["Trial Blend", "Sieves Failed", "Notes"]]
    for opt in blend_options:
        marker = " (selected)" if opt["label"] == selected_label else ""
        cmp_rows.append([
            Paragraph(escape(opt["label"] + marker), styles["body"]),
            str(opt["n_fail"]),
            Paragraph(escape(opt["note"]), styles["body"]),
        ])
    cmp_tbl = Table(cmp_rows, colWidths=[34 * mm, 30 * mm, 104 * mm])
    cmp_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(cmp_tbl)
    story.append(Spacer(1, 5 * mm))

    status_style = styles["status_pass"] if n_fail == 0 else styles["status_fail"]
    status_text = "BLEND MEETS SPEC" if n_fail == 0 else f"{n_fail} SIEVE(S) OUTSIDE SPEC"
    story.append(Paragraph(f"Recommended Blend: {escape(selected_label)}", styles["section_header"]))
    story.append(Paragraph(status_text, status_style))

    story.append(Paragraph("Stockpile Proportions", styles["body_bold"]))
    prop_rows = [list(prop_df.columns)] + prop_df.astype(str).values.tolist()
    prop_tbl = Table(prop_rows, colWidths=[70 * mm, 40 * mm, 40 * mm])
    prop_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(prop_tbl)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Blended Gradation vs. Target", styles["body_bold"]))
    grad_rows = [list(result_df.columns)] + result_df.astype(str).values.tolist()
    grad_tbl = Table(grad_rows, colWidths=[24 * mm, 26 * mm, 26 * mm, 30 * mm, 20 * mm])
    grad_style = [
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ]
    status_col = list(result_df.columns).index("Status")
    for i, row in enumerate(result_df.itertuples(index=False), start=1):
        if str(row[status_col]) == "FAIL":
            grad_style.append(("BACKGROUND", (0, i), (-1, i), FAIL_BG))
    grad_tbl.setStyle(TableStyle(grad_style))
    story.append(grad_tbl)

    fails = result_df[result_df["Status"] == "FAIL"]["Sieve (mm)"].astype(str).tolist()
    if n_fail == 0:
        interp = (
            f"The {escape(selected_label).lower()} blend satisfies the target gradation band "
            "at every controlled sieve for the selected mix type, course, and grading "
            "designation."
        )
    else:
        interp = (
            f"The {escape(selected_label).lower()} blend falls outside the target band at "
            f"{n_fail} sieve(s): {', '.join(fails)} mm. Consider reviewing the other trial "
            "blends above, adjusting stockpile minimum/maximum limits, or sourcing an "
            "additional stockpile (e.g. extra filler or fines) to correct these sieves."
        )
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(interp, styles["body"]))
    story.append(PageBreak())

    # ---------------- Page 3: gradation chart ----------------
    if gradation_fig is not None:
        story.append(Paragraph("Gradation Curve", styles["chart_title"]))
        story.append(_fig_to_flowable(gradation_fig))
        story.append(PageBreak())

    # ---------------- Page 4: proportions chart ----------------
    if proportions_fig is not None:
        story.append(Paragraph("Stockpile Proportions", styles["chart_title"]))
        story.append(_fig_to_flowable(proportions_fig))
        story.append(PageBreak())

    # ---------------- Page 5: certification ----------------
    story.append(Paragraph("Certification", styles["cert_title"]))
    story.append(Paragraph(
        "This asphalt aggregate proportioning report has been reviewed and is certified "
        "as suitable for the stated project and engineering requirements.", styles["body"],
    ))
    story.append(Spacer(1, 10 * mm))
    cert_rows = [
        ["Engineer Name:", escape(str(project_info.get("engineer_name") or ""))],
        ["Date:", escape(str(project_info.get("report_date") or ""))],
    ]
    cert_tbl = Table(cert_rows, colWidths=[35 * mm, 110 * mm], rowHeights=[10 * mm, 10 * mm])
    cert_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LINEBELOW", (1, 0), (1, -1), 0.75, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(cert_tbl)
    story.append(Spacer(1, 16 * mm))
    story.append(Paragraph("Signature / Stamp", styles["body_bold"]))
    story.append(Spacer(1, 2 * mm))
    box = Table([[""]], colWidths=[65 * mm], rowHeights=[26 * mm])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.75, BORDER_GRAY)]))
    story.append(box)
    story.append(Spacer(1, 16 * mm))
    story.append(Paragraph(
        f"Report prepared using {APP_NAME} by {COMPANY_NAME}. "
        f"© {datetime.now().year} {APP_SHORT_NAME} | {APP_TAGLINE}",
        styles["italic_left"],
    ))

    doc.build(story, canvasmaker=_make_footer_canvas())
    buf.seek(0)
    return buf.getvalue()
