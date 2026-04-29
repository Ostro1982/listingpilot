import os
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch, cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from PIL import Image as PILImage


def _fit_image(path, max_w_in, max_h_in):
    img = PILImage.open(path)
    w, h = img.size
    aspect = h / w
    max_w = max_w_in * inch
    max_h = max_h_in * inch
    if max_w * aspect <= max_h:
        return Image(path, width=max_w, height=max_w * aspect)
    return Image(path, width=max_h / aspect, height=max_h)


def build_pdf(prop: dict, text: dict, photos: list, out_path: str, agency: dict) -> str:
    accent = agency.get("primary_color", "#079992")
    logo_path = agency.get("logo_path", "")

    doc = SimpleDocTemplate(
        out_path, pagesize=LETTER,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    h_style = ParagraphStyle("h", parent=styles["Heading1"], fontSize=20, textColor=colors.HexColor("#0a3d62"))
    sub_style = ParagraphStyle("sub", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#3c6382"))
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14)
    price_style = ParagraphStyle("price", parent=styles["Heading1"], fontSize=22, textColor=colors.HexColor(accent), alignment=TA_CENTER)

    story = []
    if logo_path and os.path.exists(logo_path):
        try:
            story.append(_fit_image(logo_path, 1.5, 1.0))
            story.append(Spacer(1, 0.1 * inch))
        except Exception:
            pass
    story.append(Paragraph(f"{prop['property_type']} {prop['operation']} — {prop['city']}, {prop['state']}", h_style))
    story.append(Paragraph(f"{prop['address']}, {prop['city']}, {prop['state']} {prop['zip_code']}", sub_style))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(f"${prop['price']:,}", price_style))
    story.append(Spacer(1, 0.15 * inch))

    if photos:
        story.append(_fit_image(photos[0], 7, 4))
        story.append(Spacer(1, 0.15 * inch))

    data = [
        ["Bedrooms", prop['bedrooms'], "Bathrooms", prop['bathrooms']],
        ["Living area", f"{prop['living_area_sqft']:,} sqft",
         "Lot size", f"{prop.get('lot_size_sqft', '-'):,} sqft" if prop.get('lot_size_sqft') else "-"],
        ["Garage", prop.get('garage_spaces', '-'), "Year built", prop.get('year_built', '-')],
    ]
    if prop.get('hoa_fee'):
        data.append(["HOA", f"${prop['hoa_fee']:,.0f}/mo", "", ""])
    tbl = Table(data, colWidths=[1.4 * inch, 1.7 * inch, 1.4 * inch, 1.7 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f6fa")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dcdde1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dcdde1")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Description", sub_style))
    story.append(Paragraph(text['description'], body))
    story.append(Spacer(1, 0.15 * inch))

    if prop.get('features'):
        story.append(Paragraph("Features", sub_style))
        story.append(Paragraph(" • ".join(prop['features']), body))
        story.append(Spacer(1, 0.15 * inch))

    if len(photos) > 1:
        story.append(PageBreak())
        story.append(Paragraph("Gallery", sub_style))
        story.append(Spacer(1, 0.1 * inch))
        rows = []
        row = []
        for i, p in enumerate(photos[1:9]):
            row.append(_fit_image(p, 3.3, 2.3))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            row.append("")
            rows.append(row)
        if rows:
            gtbl = Table(rows, colWidths=[3.5 * inch, 3.5 * inch])
            gtbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            story.append(gtbl)

    story.append(Spacer(1, 0.25 * inch))
    license_str = f"<br/>License #: {agency['license_number']}" if agency.get('license_number') else ""
    contact = f"<b>{agency['agency']}</b><br/>{agency['name']} — {agency['phone']}<br/>{agency['email']}{license_str}"
    story.append(Paragraph(contact, body))

    doc.build(story)
    return out_path
