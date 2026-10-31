import io
from decimal import Decimal
from xml.sax.saxutils import escape


def _fmt(value) -> str:
    return f"{Decimal(value):,.2f}"


def _esc(value) -> str:
    return escape(str(value))


def render_invoice_pdf(inv) -> bytes:
    # Imported lazily so the API still starts if reportlab is missing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    customer = inv.customer
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=inv.invoice_number,
    )

    bill_to = ["<b>Bill to</b>", f"<b>{_esc(customer.name)}</b>"]
    if customer.company_name:
        bill_to.append(_esc(customer.company_name))
    bill_to.append(_esc(customer.email))
    if customer.tax_id:
        bill_to.append(f"Tax ID: {_esc(customer.tax_id)}")
    details = [
        "<b>Details</b>",
        f"Invoice date: {inv.invoice_date:%d %b %Y}",
        f"Due date: {inv.due_date:%d %b %Y}",
        f"Billing period: {inv.billing_period_start:%d %b %Y} to {inv.billing_period_end:%d %b %Y}",
        f"Subscription: {_esc(inv.subscription.subscription_number)}",
    ]
    header = Table(
        [[Paragraph("<br/>".join(bill_to), normal), Paragraph("<br/>".join(details), normal)]],
        colWidths=[87 * mm, 87 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    rows = [["Description", "Qty", "Unit price", "Discount", "Tax", "Total"]]
    for line in sorted(inv.lines, key=lambda x: x.id):
        rows.append(
            [
                Paragraph(_esc(line.description), normal),
                str(line.quantity),
                _fmt(line.unit_price),
                _fmt(line.discount_amount),
                _fmt(line.tax_amount),
                _fmt(line.line_total),
            ]
        )
    items = Table(
        rows,
        colWidths=[66 * mm, 14 * mm, 24 * mm, 22 * mm, 22 * mm, 26 * mm],
        repeatRows=1,
    )
    items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    totals = Table(
        [
            ["Subtotal", _fmt(inv.subtotal)],
            ["Discount", "-" + _fmt(inv.discount_amount)],
            ["Tax", _fmt(inv.tax_amount)],
            ["Total", _fmt(inv.total_amount)],
            ["Paid", _fmt(inv.paid_amount)],
            ["Balance due", _fmt(inv.total_amount - inv.paid_amount)],
        ],
        colWidths=[40 * mm, 32 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
                ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"),
                ("LINEABOVE", (0, 3), (-1, 3), 0.6, colors.black),
            ]
        )
    )

    story = [
        Paragraph("INVOICE", styles["Title"]),
        Paragraph(f"<b>{_esc(inv.invoice_number)}</b> &nbsp;&nbsp; Status: {inv.status.value}", normal),
        Spacer(1, 6 * mm),
        header,
        Spacer(1, 8 * mm),
        items,
        Spacer(1, 6 * mm),
        totals,
        Spacer(1, 8 * mm),
        Paragraph("All amounts are in INR.", styles["Italic"]),
    ]
    doc.build(story)
    return buffer.getvalue()