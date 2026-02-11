from reportlab.lib import colors, utils as rl_utils
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm, inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import io
import os
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import crud
from uuid import UUID
from datetime import datetime

# Font s diakritikou (DejaVu / fallback Helvetica)
_CZECH_FONT = "Helvetica"
_CZECH_FONT_BOLD = "Helvetica-Bold"

def _register_czech_font() -> None:
    global _CZECH_FONT, _CZECH_FONT_BOLD
    if _CZECH_FONT != "Helvetica":
        return
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("DejaVuSans", "/usr/share/fonts/TTF/DejaVuSans.ttf"),
        ("DejaVuSans", os.path.join(base, "static", "DejaVuSans.ttf")),
        ("DejaVuSans", "/Library/Fonts/DejaVuSans.ttf"),
        ("DejaVuSans", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),  # macOS
    ]
    for name, path in candidates:
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont("DejaVuSans", path))
                bold_path = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
                if os.path.isfile(bold_path):
                    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold_path))
                    _CZECH_FONT_BOLD = "DejaVuSans-Bold"
                else:
                    _CZECH_FONT_BOLD = "DejaVuSans"
                _CZECH_FONT = "DejaVuSans"
                break
            except Exception:
                continue


def _logo_image_with_aspect(path: str, max_w: float, max_h: float):
    """Vrátí platypus Image s poměrem stran podle obrázku (max šířka/výška v mm)."""
    try:
        img_reader = rl_utils.ImageReader(path)
        iw, ih = img_reader.getSize()
        if iw <= 0:
            return Image(path, width=max_w, height=max_h)
        aspect = ih / float(iw)
        w = max_w
        h = min(max_h, max_w * aspect)
        return Image(path, width=w, height=h)
    except Exception:
        return Image(path, width=max_w, height=max_h)


# Cesta k logu: backend/logo.png, nebo FE public/logo.png
def _find_logo_path() -> Optional[str]:
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, "logo.png"),
        os.path.join(base, "static", "logo.png"),
        os.path.join(os.path.dirname(base), "konderla-dev-fe", "public", "logo.png"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


class PDFCanvas(canvas.Canvas):
    """Vlastní canvas: hlavička s logem a patička s číslem stránky na každé stránce."""
    def __init__(self, *args, logo_path: Optional[str] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.logo_path = logo_path
        self._page_num = 0

    def draw_header_footer(self):
        page_w, page_h = self._pagesize if hasattr(self, '_pagesize') else landscape(A4)
        self.setStrokeColor(HexColor('#e5e7eb'))
        self.setLineWidth(0.5)
        self.line(15*mm, page_h - 14*mm, page_w - 15*mm, page_h - 14*mm)
        if self.logo_path and os.path.isfile(self.logo_path):
            try:
                img_reader = rl_utils.ImageReader(self.logo_path)
                iw, ih = img_reader.getSize()
                if iw and ih:
                    max_w, max_h = 36*mm, 10*mm
                    aspect = ih / float(iw)
                    w = min(max_w, max_h / aspect)
                    h = min(max_h, w * aspect)
                    logo_y = page_h - 14*mm - 2*mm - h
                    self.setFillColor(colors.white)
                    self.rect(15*mm, logo_y, w, h, fill=1, stroke=0)
                    self.drawImage(self.logo_path, 15*mm, logo_y, width=w, height=h, preserveAspectRatio=True, mask='auto')
                else:
                    self.setFillColor(colors.white)
                    self.rect(15*mm, page_h - 12*mm, 36*mm, 9*mm, fill=1, stroke=0)
                    self.drawImage(self.logo_path, 15*mm, page_h - 12*mm, width=36*mm, height=9*mm, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass
        self.line(15*mm, 16*mm, page_w - 15*mm, 16*mm)
        self.setFont(_CZECH_FONT, 8)
        self.setFillColor(HexColor('#6b7280'))
        self.drawRightString(page_w - 15*mm, 12*mm, f"Stránka {self._page_num}")
        self.drawString(15*mm, 12*mm, "Srovnání rozpočtů · Konderla")

    def showPage(self):
        self._page_num += 1
        self.draw_header_footer()
        super().showPage()


def create_pie_chart(items: List[Dict[str, Any]], budget_name: str, output_path: str):
    """Vytvoří moderní koláčový graf pro budget"""
    if not items:
        return None
    
    # Připravit data pro graf
    names = []
    prices = []
    for item in items:
        name = item.get('name', 'Neznámá položka')
        price = float(item.get('price', 0))
        if price > 0:
            # Zkrátit dlouhé názvy
            if len(name) > 20:
                name = name[:17] + '...'
            names.append(name)
            prices.append(price)
    
    if not prices or sum(prices) == 0:
        return None
    
    # Pokud je příliš mnoho položek, zobrazit jen top 8 a zbytek jako "Ostatní"
    if len(prices) > 8:
        sorted_data = sorted(zip(prices, names), reverse=True)
        top_prices = [p for p, n in sorted_data[:7]]
        top_names = [n for p, n in sorted_data[:7]]
        other_price = sum(p for p, n in sorted_data[7:])
        if other_price > 0:
            top_prices.append(other_price)
            top_names.append('Ostatní')
        prices = top_prices
        names = top_names
    
    # Jemnější paleta (šedomodré až zelené tóny, bez křiklavých)
    chart_colors = ['#4f46e5', '#059669', '#0d9488', '#2563eb', '#7c3aed', '#6366f1', '#0891b2', '#4b5563']
    colors_list = [chart_colors[i % len(chart_colors)] for i in range(len(prices))]
    
    fig, ax = plt.subplots(figsize=(6, 6), facecolor='none')
    ax.set_facecolor('none')
    
    wedges, texts, autotexts = ax.pie(
        prices,
        labels=names,
        autopct=lambda pct: f'{pct:.0f}%' if pct >= 5 else '',
        startangle=90,
        colors=colors_list,
        textprops={'fontsize': 9, 'color': '#1f2937'},
        wedgeprops={'edgecolor': 'white', 'linewidth': 1.5},
        pctdistance=0.75,
    )
    for t in texts:
        t.set_fontsize(8)
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(8)
    
    display_name = budget_name[:40] + ('...' if len(budget_name) > 40 else '')
    ax.set_title(display_name, fontsize=10, fontweight='600', pad=12, color='#374151')
    ax.axis('equal')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()
    
    return output_path


def generate_pdf_export(round_id: UUID, db: Session, output_path: str):
    """Vygeneruje PDF: jedna srovnávací tabulka (řádky = položky, sloupce = rozpočty) + pod ní jeden graf na rozpočet."""
    _register_czech_font()
    budgets = crud.get_budgets_by_round(db, round_id)
    if not budgets:
        raise ValueError("No budgets found for this round")

    root_budgets = [b for b in budgets if not b.parent_budget_id]
    if not root_budgets:
        raise ValueError("No main budgets in this round")

    def get_items(b):
        items = b.items if isinstance(b.items, list) else []
        return items

    # Všechna jedinečná jména položek napříč rozpočty (jako v UI)
    all_item_names = set()
    for b in root_budgets:
        for item in get_items(b):
            name = item.get("name", "")
            if name:
                all_item_names.add(name)
    all_item_names = sorted(all_item_names)

    # Cena položky v daném rozpočtu
    def price_for(b, item_name):
        for item in get_items(b):
            if (item.get("name") or "").strip() == item_name:
                return float(item.get("price", 0))
        return 0.0

    # Jedna srovnávací tabulka: hlavička = Položka + názvy rozpočtů
    n_cols = 1 + len(root_budgets)
    content_width = 267 * mm  # landscape A4 minus margins
    col_item_w = 100 * mm
    col_price_w = (content_width - col_item_w) / len(root_budgets) if root_budgets else 40 * mm
    col_widths = [col_item_w] + [col_price_w] * len(root_budgets)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
    )
    story = []
    logo_path = _find_logo_path()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Heading1"], fontSize=22, textColor=HexColor("#111827"),
        spaceAfter=2, spaceBefore=0, alignment=TA_CENTER, fontName=_CZECH_FONT_BOLD, leading=26,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"], fontSize=9, textColor=HexColor("#6b7280"),
        spaceAfter=16, alignment=TA_CENTER, fontName=_CZECH_FONT,
    )
    body_style = ParagraphStyle("BodyCzech", parent=styles["Normal"], fontName=_CZECH_FONT)

    if logo_path:
        try:
            logo_img = _logo_image_with_aspect(logo_path, 50 * mm, 15 * mm)
            story.append(Paragraph('<para align="center"> </para>', styles["Normal"]))
            story.append(logo_img)
            story.append(Spacer(1, 6))
        except Exception:
            pass
    story.append(Paragraph("Srovnání rozpočtů", title_style))
    story.append(Paragraph(f"Vygenerováno: {datetime.now().strftime('%d.%m.%Y %H:%M')}", subtitle_style))
    story.append(Spacer(1, 8))

    # Hlavička tabulky: Položka | Rozpočet 1 | Rozpočet 2 | ...
    header_row = [Paragraph("Položka", body_style)]
    for b in root_budgets:
        name = (b.name or "Rozpočet")[:25] + ("..." if len(b.name or "") > 25 else "")
        header_row.append(Paragraph(name, body_style))
    table_data = [header_row]

    totals = [0.0] * len(root_budgets)
    for item_name in all_item_names:
        row = [Paragraph((item_name[:50] + ("..." if len(item_name) > 50 else "")), body_style)]
        for i, b in enumerate(root_budgets):
            p = price_for(b, item_name)
            totals[i] += p
            row.append(Paragraph(f"{p:,.0f}".replace(",", " "), body_style))
        table_data.append(row)

    # Řádek CELKEM
    total_row = [Paragraph("<b>CELKEM</b>", body_style)]
    for t in totals:
        total_row.append(Paragraph(f"<b>{t:,.0f}</b>".replace(",", " "), body_style))
    table_data.append(total_row)

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f9fafb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#374151")),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), _CZECH_FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("FONTSIZE", (0, 1), (-1, -2), 8),
        ("FONTNAME", (0, 1), (-1, -2), _CZECH_FONT),
        ("TEXTCOLOR", (0, 1), (-1, -2), HexColor("#111827")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, HexColor("#fafafa")]),
        ("TOPPADDING", (0, 1), (-1, -2), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -2), 4),
        ("BACKGROUND", (0, -1), (-1, -1), HexColor("#f3f4f6")),
        ("FONTNAME", (0, -1), (-1, -1), _CZECH_FONT_BOLD),
        ("FONTSIZE", (0, -1), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#e5e7eb")),
        ("LINEBELOW", (0, -2), (-1, -2), 1, HexColor("#e5e7eb")),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    # Jeden graf na rozpočet (pod tabulkou), menší – 2 vedle sebe na landscape
    chart_width = 75 * mm
    chart_height = 75 * mm
    chart_paths = []
    for b in root_budgets:
        items = get_items(b)
        path = os.path.join(os.path.dirname(output_path), f"chart_{b.id}.png")
        if create_pie_chart(items, b.name or "Rozpočet", path):
            chart_paths.append((path, b.name or "Rozpočet"))

    # Grafy vedle sebe, max 2 na stránku
    charts_per_row = 2
    for i in range(0, len(chart_paths), charts_per_row):
        row_charts = chart_paths[i : i + charts_per_row]
        row_cells = []
        for path, _ in row_charts:
            try:
                img = Image(path, width=chart_width, height=chart_height)
                row_cells.append([img])
            except Exception:
                row_cells.append([Spacer(1, 1)])
        while len(row_cells) < charts_per_row:
            row_cells.append([Spacer(chart_width, chart_height)])
        cell_w = content_width / charts_per_row
        tbl = Table(row_cells, colWidths=[cell_w] * charts_per_row)
        tbl.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8))
        # Nová stránka po každých 2 grafech (max 2 grafy na list)
        if i + charts_per_row < len(chart_paths):
            story.append(PageBreak())

    # Vygenerovat PDF s vlastním canvasem (hlavička s logem, patička)
    # ReportLab volá canvasmaker s (filename,) nebo (doc_template), popř. (filename, pagesize, ...)
    def _canvas_maker(*args, **kwargs):
        if args and isinstance(args[0], str) and (args[0].endswith('.pdf') or os.path.sep in args[0]):
            path = args[0]
        elif args and hasattr(args[0], '_filename'):
            path = getattr(args[0], '_filename', output_path)
        elif args and hasattr(args[0], 'filename'):
            path = getattr(args[0], 'filename', output_path)
        else:
            path = output_path
        return PDFCanvas(path, *args[1:], logo_path=logo_path, **kwargs)

    try:
        doc.build(story, canvasmaker=_canvas_maker)
    except Exception as e:
        # Při selhání vlastního canvasu zkusit vygenerovat PDF bez hlavičky/patičky
        import logging
        logging.getLogger(__name__).warning("PDF custom canvas failed: %s", e, exc_info=True)
        doc.build(story)

    # Smazat dočasné soubory s grafy
    import glob
    chart_files = glob.glob(os.path.join(os.path.dirname(output_path), "chart_*.png"))
    for f in chart_files:
        try:
            os.remove(f)
        except:
            pass
    
    return output_path
