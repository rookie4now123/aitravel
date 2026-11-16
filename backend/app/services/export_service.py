from __future__ import annotations

from io import BytesIO
import ipaddress
from pathlib import Path
import socket
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import httpx

from app.schemas.trip import Itinerary, TripDetailResponse


TECHNICAL_EXPORT_PHRASES = (
    "llm",
    "rag",
    "langchain",
    "sqlite",
    "trip_service",
    "source code",
    "rule-based",
    "fallback",
)


def _safe_text(value: object) -> str:
    """Escape special XML characters in ReportLab Paragraph text."""
    return escape(str(value or ""))


def _clean_export_tips(tips: list[str]) -> list[str]:
    """Filter out internal technical notes from exported tips."""
    cleaned_tips: list[str] = []
    for tip in tips:
        normalized_tip = tip.strip()
        if not normalized_tip:
            continue
        tip_lower = normalized_tip.lower()
        if any(phrase in tip_lower for phrase in TECHNICAL_EXPORT_PHRASES):
            continue
        if normalized_tip not in cleaned_tips:
            cleaned_tips.append(normalized_tip)
    return cleaned_tips


def _public_source_notes(source_notes: list[str]) -> list[str]:
    """Keep reader-friendly source notes that are suitable for export."""
    public_notes: list[str] = []
    for note in source_notes:
        normalized_note = note.strip()
        if not normalized_note:
            continue
        note_lower = normalized_note.lower()
        if any(phrase in note_lower for phrase in TECHNICAL_EXPORT_PHRASES):
            continue
        if normalized_note.startswith("[Source:"):
            public_notes.append(normalized_note)
    return public_notes


def _render_budget_lines(itinerary: Itinerary) -> list[str]:
    """Format the budget breakdown into a Markdown list."""
    budget = itinerary.budget_breakdown
    return [
        f"- Transport: {budget.transport:.2f} USD",
        f"- Accommodation: {budget.hotel:.2f} USD",
        f"- Meals: {budget.meals:.2f} USD",
        f"- Tickets: {budget.tickets:.2f} USD",
        f"- Other: {budget.other:.2f} USD",
        f"- Total: {budget.total:.2f} USD",
    ]


def itinerary_to_markdown(trip_detail: TripDetailResponse) -> str:
    """Render itinerary to Markdown."""
    itinerary = trip_detail.itinerary

    lines: list[str] = [
        f"# {itinerary.destination} Itinerary",
        "",
        f"- Trip ID: {trip_detail.trip_id}",
        f"- Destination: {itinerary.destination}",
        f"- Estimated Budget: {itinerary.estimated_budget:.2f} USD",
        "",
        "## Trip Overview",
        itinerary.summary,
        "",
        "## Daily Schedule",
    ]

    for day in itinerary.days:
        lines.extend(
            [
                "",
                f"### Day {day.day_index} {day.theme or ''}".rstrip(),
                f"- Date: {day.date.isoformat()}" if day.date else "- Date: TBA",
            ]
        )

        for spot in day.spots:
            lines.extend(
                [
                    f"- Main Attraction: {spot.name}",
                    f"  - Time: {spot.start_time or 'TBA'} - {spot.end_time or 'TBA'}",
                    f"  - Description: {spot.description or 'None'}",
                ]
            )

        for meal in day.meals:
            lines.extend(
                [
                    f"- Meal Recommendation: {meal.name} ({meal.meal_type})",
                    f"  - Notes: {meal.notes or 'None'}",
                ]
            )

        if day.hotel is not None:
            lines.append(
                f"- Hotel: {day.hotel.name} ({day.hotel.level or 'Level not specified'})"
            )

        for note in day.notes:
            lines.append(f"- Note: {note}")

    lines.extend(["", "## Budget Breakdown", *_render_budget_lines(itinerary)])

    export_tips = _clean_export_tips(itinerary.tips)
    if export_tips:
        lines.extend(["", "## Travel Tips"])
        lines.extend(f"- {tip}" for tip in export_tips)

    public_notes = _public_source_notes(itinerary.source_notes)
    if public_notes:
        lines.extend(["", "## References"])
        lines.extend(f"- {note}" for note in public_notes)

    return "\n".join(lines).strip() + "\n"


def _register_pdf_font() -> str:
    """Register a Unicode TrueType font supporting European diacritics, falling back to Helvetica."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_name = "TripUnicodeSans"
    try:
        pdfmetrics.getFont(font_name)
        return font_name
    except KeyError:
        pass

    candidate_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]

    for raw_path in candidate_paths:
        font_path = Path(raw_path)
        if font_path.exists():
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
                return font_name
            except Exception:
                continue

    return "Helvetica"


def _draw_pdf_footer(canvas, doc, trip_detail: TripDetailResponse, font_name: str) -> None:
    """Draw footer and page number at the bottom of each PDF page."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    page_width, _ = doc.pagesize
    footer_y = 10 * mm
    line_y = 14 * mm

    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cbd2d9"))
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, line_y, page_width - doc.rightMargin, line_y)

    canvas.setFont(font_name, 9)
    canvas.setFillColor(colors.HexColor("#52606d"))
    canvas.drawString(doc.leftMargin, footer_y, f"Trip Planner | {trip_detail.trip_id}")
    canvas.drawRightString(page_width - doc.rightMargin, footer_y, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _is_safe_public_http_url(url: str) -> bool:
    """Validate that a URL is an http(s) URL resolving strictly to public IP addresses (anti-SSRF)."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False

    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        return False

    if not addr_infos:
        return False

    for info in addr_infos:
        ip_str = info[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if not ip_obj.is_global:
            return False

    return True


def _load_pdf_image(image_url: str, max_width: float, max_height: float):
    """Safely download a spot image and convert it into a ReportLab Image object, or return None."""
    from reportlab.platypus import Image

    if not image_url or not _is_safe_public_http_url(image_url):
        return None

    try:
        with httpx.Client(timeout=4.0, follow_redirects=False) as client:
            response = client.get(
                image_url,
                headers={"User-Agent": "TripPlannerDemo/1.0"},
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("image/"):
                return None
            image_bytes = response.content[:2_000_000]
            if len(response.content) > 2_000_000:
                return None
    except Exception:
        return None

    try:
        image = Image(BytesIO(image_bytes))
        image._restrictSize(max_width, max_height)
        return image
    except Exception:
        return None


def itinerary_to_pdf_bytes(trip_detail: TripDetailResponse) -> bytes:
    """Render the complete itinerary into styled PDF bytes."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PDF export depends on reportlab, please install it first: pip install reportlab"
        ) from exc

    font_name = _register_pdf_font()
    itinerary = trip_detail.itinerary

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"{trip_detail.trip_id}.pdf",
    )

    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TripTitle",
        parent=base_styles["Title"],
        fontName=font_name,
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#16324f"),
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "TripSubtitle",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#4b5d73"),
        spaceAfter=10,
    )
    section_style = ParagraphStyle(
        "TripSection",
        parent=base_styles["Heading2"],
        fontName=font_name,
        fontSize=13.5,
        leading=19,
        textColor=colors.HexColor("#0f4c5c"),
        spaceBefore=10,
        spaceAfter=6,
    )
    day_style = ParagraphStyle(
        "TripDay",
        parent=base_styles["Heading3"],
        fontName=font_name,
        fontSize=12,
        leading=17,
        textColor=colors.HexColor("#1b4332"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "TripBody",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#222222"),
        spaceAfter=4,
    )
    note_style = ParagraphStyle(
        "TripNote",
        parent=body_style,
        leftIndent=8,
        bulletIndent=0,
        spaceAfter=3,
    )

    story = [
        Paragraph(f"{_safe_text(itinerary.destination)} Itinerary", title_style),
        Paragraph(
            f"Trip ID: {_safe_text(trip_detail.trip_id)}<br/>"
            f"Destination: {_safe_text(itinerary.destination)}<br/>"
            f"Budget: {itinerary.estimated_budget:.2f} USD",
            subtitle_style,
        ),
    ]

    meta_table = Table(
        [
            ["Trip Duration", f"{len(itinerary.days)} days"],
            ["Created At", trip_detail.created_at.isoformat() if trip_detail.created_at else "Not recorded"],
            ["Updated At", trip_detail.updated_at.isoformat() if trip_detail.updated_at else "Not recorded"],
        ],
        colWidths=[32 * mm, 120 * mm],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#243b53")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eaf4f4")),
                ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#f8fbff")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cdd7e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([meta_table, Spacer(1, 8)])

    story.append(Paragraph("Trip Overview", section_style))
    story.append(Paragraph(_safe_text(itinerary.summary), body_style))

    story.append(Paragraph("Daily Schedule", section_style))
    for day in itinerary.days:
        title = f"Day {day.day_index}"
        if day.theme:
            title += f" - {day.theme}"
        story.append(Paragraph(_safe_text(title), day_style))

        if day.date:
            story.append(Paragraph(f"Date: {day.date.isoformat()}", body_style))

        for spot in day.spots:
            story.append(Paragraph(f"Main Attraction: {_safe_text(spot.name)}", body_style))
            image_url = getattr(spot, "image_url", None)
            spot_image = _load_pdf_image(image_url or "", max_width=72 * mm, max_height=42 * mm)
            if spot_image is not None:
                story.extend([spot_image, Spacer(1, 4)])
            story.append(
                Paragraph(
                    f"Time: {_safe_text(spot.start_time or 'TBA')} - {_safe_text(spot.end_time or 'TBA')}",
                    note_style,
                )
            )
            if spot.address or spot.location:
                story.append(
                    Paragraph(
                        f"Address: {_safe_text(spot.address or spot.location)}",
                        note_style,
                    )
                )
            story.append(Paragraph(f"Description: {_safe_text(spot.description or 'None')}", note_style))

        for meal in day.meals:
            story.append(
                Paragraph(
                    f"Meal Recommendation: {_safe_text(meal.name)} ({_safe_text(meal.meal_type)})",
                    body_style,
                )
            )
            story.append(Paragraph(f"Notes: {_safe_text(meal.notes or 'None')}", note_style))

        if day.hotel is not None:
            story.append(
                Paragraph(
                    f"Accommodation: {_safe_text(day.hotel.name)} ({_safe_text(day.hotel.level or 'Not specified')})",
                    body_style,
                )
            )

        for note in day.notes:
            story.append(Paragraph(f"Notes: {_safe_text(note)}", note_style))

        story.append(Spacer(1, 4))

    story.append(Paragraph("Budget Breakdown", section_style))
    budget = itinerary.budget_breakdown
    budget_table = Table(
        [
            ["Item", "Amount (USD)"],
            ["Transportation", f"{budget.transport:.2f}"],
            ["Accommodation", f"{budget.hotel:.2f}"],
            ["Meals", f"{budget.meals:.2f}"],
            ["Tickets", f"{budget.tickets:.2f}"],
            ["Other", f"{budget.other:.2f}"],
            ["Total", f"{budget.total:.2f}"],
        ],
        colWidths=[48 * mm, 48 * mm],
    )
    budget_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9edf7")),
                ("BACKGROUND", (0, 1), (-1, -2), colors.white),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef6f2")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1f2933")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd2d9")),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([budget_table, Spacer(1, 6)])

    export_tips = _clean_export_tips(itinerary.tips)
    if export_tips:
        story.append(Paragraph("Travel Tips", section_style))
        for tip in export_tips:
            story.append(Paragraph(f"- {_safe_text(tip)}", body_style))

    public_notes = _public_source_notes(itinerary.source_notes)
    if public_notes:
        story.append(Paragraph("References", section_style))
        for note in public_notes:
            story.append(Paragraph(f"- {_safe_text(note)}", body_style))

    def draw_footer(canvas, document) -> None:
        _draw_pdf_footer(canvas, document, trip_detail, font_name)

    doc.build(
        story,
        onFirstPage=draw_footer,
        onLaterPages=draw_footer,
    )
    return buffer.getvalue()