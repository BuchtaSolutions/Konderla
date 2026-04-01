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
matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["font.weight"] = "regular"
matplotlib.rcParams["axes.titleweight"] = "semibold"
matplotlib.rcParams["axes.labelweight"] = "regular"
import io
import os
import hashlib
import re
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
import crud
from uuid import UUID
from datetime import datetime

# Font s diakritikou (DejaVu / fallback Helvetica)
_CZECH_FONT = "Helvetica"
_CZECH_FONT_BOLD = "Helvetica-Bold"
_CHART_PALETTE = [
    "#1d4ed8", "#0f766e", "#0284c7", "#6d28d9", "#16a34a", "#ca8a04",
    "#ea580c", "#4f46e5", "#0ea5e9", "#14b8a6", "#3b82f6", "#8b5cf6",
    "#22c55e", "#84cc16", "#eab308", "#f59e0b", "#f97316", "#06b6d4",
    "#6366f1", "#10b981", "#2563eb", "#7c3aed", "#0d9488", "#65a30d",
    "#c2410c", "#4338ca", "#0891b2", "#2dd4bf", "#93c5fd", "#a78bfa",
]
_PIE_MAX_SLICES = 8
_PIE_MIN_PERCENT = 1.0


def _palette_index(label: str) -> int:
    normalized = (label or "").strip().lower()
    if not normalized:
        return 0
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % len(_CHART_PALETTE)


def _color_for_label(label: str) -> str:
    return _CHART_PALETTE[_palette_index(label)]


def _build_label_color_map(labels: List[str]) -> Dict[str, str]:
    """
    Sestaví konzistentní mapu barev pro labely tak, aby stejný label měl
    stejnou barvu napříč grafy i tabulkou.
    """
    ordered_unique_labels: List[str] = []
    seen = set()
    for raw_label in labels:
        label = (raw_label or "").strip()
        if not label:
            continue
        normalized = label.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered_unique_labels.append(label)

    assigned_by_label: Dict[str, str] = {}
    used_indices = set()
    palette_size = len(_CHART_PALETTE)

    for label in ordered_unique_labels:
        normalized = label.lower()
        preferred_idx = _palette_index(label)
        candidate_idx = preferred_idx

        if len(used_indices) < palette_size:
            for _ in range(palette_size):
                if candidate_idx not in used_indices:
                    break
                candidate_idx = (candidate_idx + 1) % palette_size
            used_indices.add(candidate_idx)
            assigned_by_label[normalized] = _CHART_PALETTE[candidate_idx]
        else:
            # Pokud dojdou unikátní barvy, fallback na deterministický hash.
            assigned_by_label[normalized] = _CHART_PALETTE[preferred_idx]

    return assigned_by_label


def _color_for_label_mapped(label: str, color_map: Optional[Dict[str, str]] = None) -> str:
    if color_map:
        mapped = color_map.get((label or "").strip().lower())
        if mapped:
            return mapped
    return _color_for_label(label)


def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
    raw = (value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join([c * 2 for c in raw])
    if len(raw) != 6:
        return 255, 255, 255
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _blend_with_white(hex_color: str, white_ratio: float = 0.86) -> str:
    """
    ReportLab table background nemá alpha jako CSS, proto simulujeme "nižší opacitu"
    smícháním barvy s bílou.
    """
    r, g, b = _hex_to_rgb(hex_color)
    ratio = max(0.0, min(1.0, white_ratio))
    rr = round(r + (255 - r) * ratio)
    gg = round(g + (255 - g) * ratio)
    bb = round(b + (255 - b) * ratio)
    return f"#{rr:02x}{gg:02x}{bb:02x}"


def _text_color_for_bg(hex_color: str) -> str:
    """Vrátí kontrastní textovou barvu pro dané pozadí."""
    r, g, b = _hex_to_rgb(hex_color)
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return "#0f172a" if luminance > 0.62 else "#ffffff"


def _tint_for_label(label: str, color_map: Optional[Dict[str, str]] = None) -> str:
    # 1:1 stejna barva jako v grafu (bez "opacity" efektu).
    return _color_for_label_mapped(label, color_map)


def _unique_colors_for_chart_keys(keys: List[str]) -> List[str]:
    """
    Vrátí barvy pro položky v jednom grafu tak, aby se v rámci grafu
    neopakovaly (pokud počet položek nepřekročí velikost palety).
    """
    assigned_by_key: Dict[str, int] = {}
    used_indices = set()
    palette_size = len(_CHART_PALETTE)

    for raw_key in keys:
        key = (raw_key or "").strip().lower()
        if key in assigned_by_key:
            continue

        preferred_idx = _palette_index(key)
        candidate_idx = preferred_idx

        if len(used_indices) < palette_size:
            # Lineární probing: drží hash preferenci, ale vyhne se kolizi.
            for _ in range(palette_size):
                if candidate_idx not in used_indices:
                    break
                candidate_idx = (candidate_idx + 1) % palette_size
        assigned_by_key[key] = candidate_idx
        used_indices.add(candidate_idx)

    return [
        _CHART_PALETTE[
            assigned_by_key.get((raw_key or "").strip().lower(), _palette_index(raw_key))
        ]
        for raw_key in keys
    ]


def _prepare_pie_entries(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Připraví položky pro pie chart bez slučování do "Ostatní".
    """
    entries: List[Dict[str, Any]] = []
    for item in items:
        name = (item.get("name") or "Neznámá položka").strip()
        price = float(item.get("price", 0) or 0)
        if price > 0:
            entries.append({"name": name, "price": price, "color_key": name})

    if not entries:
        return []

    entries = sorted(entries, key=lambda x: x["price"], reverse=True)
    return entries

def _register_czech_font() -> None:
    global _CZECH_FONT, _CZECH_FONT_BOLD
    if _CZECH_FONT != "Helvetica":
        return
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        # Debian/Ubuntu (fonts-dejavu-core)
        ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("DejaVuSans", "/usr/share/fonts/TTF/DejaVuSans.ttf"),
        # Projekt / static
        ("DejaVuSans", os.path.join(base, "static", "DejaVuSans.ttf")),
        ("DejaVuSans", os.path.join(base, "fonts", "DejaVuSans.ttf")),
        # macOS
        ("DejaVuSans", "/Library/Fonts/DejaVuSans.ttf"),
        ("DejaVuSans", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        # Fallback: Liberation Sans (často na RHEL/Fedora)
        ("DejaVuSans", "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"),
    ]
    for name, path in candidates:
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont("DejaVuSans", path))
                # Bold varianta – DejaVu nebo Liberation
                bold_path = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf").replace(
                    "LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"
                )
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


def _fit_size_keep_aspect(iw: float, ih: float, max_w: float, max_h: float) -> Tuple[float, float]:
    """Spočítá rozměr do boxu bez deformace (zachová poměr stran)."""
    if iw <= 0 or ih <= 0:
        return max_w, max_h
    scale = min(max_w / float(iw), max_h / float(ih))
    return iw * scale, ih * scale


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
    def __init__(
        self,
        *args,
        logo_path: Optional[str] = None,
        company_lines: Optional[List[str]] = None,
        company_logo_path: Optional[str] = None,
        owner_name: str = "",
        owner_title: str = "",
        owner_email: str = "",
        signature_path: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.logo_path = logo_path
        self.company_lines = company_lines or []
        self.company_logo_path = company_logo_path
        self.owner_name = owner_name
        self.owner_title = owner_title
        self.owner_email = owner_email
        self.signature_path = signature_path
        self._page_num = 0

    def draw_header_footer(self):
        page_w, page_h = self._pagesize if hasattr(self, '_pagesize') else landscape(A4)
        header_bottom_y = page_h - 16 * mm
        self.setStrokeColor(HexColor('#e5e7eb'))
        self.setLineWidth(0.5)
        self.line(15 * mm, header_bottom_y, page_w - 15 * mm, header_bottom_y)
        if self.logo_path and os.path.isfile(self.logo_path):
            try:
                img_reader = rl_utils.ImageReader(self.logo_path)
                iw, ih = img_reader.getSize()
                if iw and ih:
                    max_w, max_h = 36*mm, 10*mm
                    w, h = _fit_size_keep_aspect(iw, ih, max_w, max_h)
                    logo_y = page_h - 3 * mm - h
                    self.setFillColor(colors.white)
                    self.rect(15*mm, logo_y, w, h, fill=1, stroke=0)
                    self.drawImage(self.logo_path, 15*mm, logo_y, width=w, height=h, preserveAspectRatio=True, mask='auto')
                else:
                    self.setFillColor(colors.white)
                    self.rect(15*mm, page_h - 12*mm, 36*mm, 9*mm, fill=1, stroke=0)
                    self.drawImage(self.logo_path, 15*mm, page_h - 12*mm, width=36*mm, height=9*mm, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass
        company_text_start_y = page_h - 9.0 * mm
        if self.company_logo_path and os.path.isfile(self.company_logo_path):
            try:
                img_reader = rl_utils.ImageReader(self.company_logo_path)
                iw, ih = img_reader.getSize()
                if iw and ih:
                    max_w, max_h = 60 * mm, 12.0 * mm
                    w, h = _fit_size_keep_aspect(iw, ih, max_w, max_h)
                    logo_y = page_h - 3.0 * mm - h
                    self.drawImage(
                        self.company_logo_path,
                        page_w - 15 * mm - w,
                        logo_y,
                        width=w,
                        height=h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                    company_text_start_y = logo_y - 2.5 * mm
            except Exception:
                pass

        footer_top_y = 24 * mm
        self.line(15 * mm, footer_top_y, page_w - 15 * mm, footer_top_y)

        # Levá část patičky: logo + firemní info
        left_x = 15 * mm
        if self.company_lines:
            first_line_y = 15.0 * mm
            # Držet spodní odsazení patičky cca 8 mm od spodku stránky.
            first_line_y = max(first_line_y, 15.0 * mm)
            self.setFillColor(HexColor("#111827"))
            header_text = self.beginText()
            header_text.setTextOrigin(left_x, first_line_y)
            header_text.setFont(_CZECH_FONT_BOLD, 8.0)
            header_text.setCharSpace(0.35)
            header_text.textLine(self.company_lines[0])
            self.drawText(header_text)

            self.setFillColor(HexColor("#374151"))
            body_text = self.beginText()
            body_text.setTextOrigin(left_x, first_line_y - 3.0 * mm)
            body_text.setFont(_CZECH_FONT, 7.7)
            body_text.setCharSpace(0.30)
            body_text.setLeading(3.0 * mm)
            for line in self.company_lines[1:]:
                if not line:
                    continue
                body_text.textLine(line)
            self.drawText(body_text)

        # Pravá část patičky: podpis + kontakt
        right_x = page_w - 15 * mm
        if self.signature_path and os.path.isfile(self.signature_path):
            try:
                sig_reader = rl_utils.ImageReader(self.signature_path)
                iw, ih = sig_reader.getSize()
                if iw and ih:
                    max_w, max_h = 24 * mm, 8 * mm
                    w, h = _fit_size_keep_aspect(iw, ih, max_w, max_h)
                    self.drawImage(
                        self.signature_path,
                        right_x - w,
                        16.8 * mm,
                        width=w,
                        height=h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
            except Exception:
                pass

        self.setFillColor(HexColor("#111827"))
        self.setFont(_CZECH_FONT_BOLD, 8.4)
        self.drawRightString(right_x, 14.1 * mm, self.owner_name)
        self.setFont(_CZECH_FONT, 7.7)
        self.setFillColor(HexColor("#374151"))
        right_line_y = 11.0 * mm
        if self.owner_title:
            self.drawRightString(right_x, right_line_y, self.owner_title)
            right_line_y -= 3.0 * mm
        if self.owner_email:
            self.drawRightString(right_x, right_line_y, self.owner_email)

        # Číslování stránek je záměrně vypnuté.

    def showPage(self):
        self._page_num += 1
        self.draw_header_footer()
        super().showPage()


def create_pie_chart(
    items: List[Dict[str, Any]],
    budget_name: str,
    output_path: str,
    color_map: Optional[Dict[str, str]] = None,
):
    """Vytvoří moderní koláčový graf pro budget"""
    if not items:
        return None
    
    entries = _prepare_pie_entries(items)
    if not entries:
        return None

    # Omezíme počet položek v legendě i v grafu, aby se vše vešlo do jednoho obrázku
    # a legenda se "nezakusovala" do spodku.
    # Preferujeme top 9 dle ceny a zbytek sloučíme jako "Ostatní".
    max_items = 10
    top_items = max_items - 1
    if len(entries) > max_items:
        other_price = sum(float(e.get("price", 0) or 0) for e in entries[top_items:])
        other_price = float(other_price or 0)
        if other_price > 0:
            entries = entries[:top_items] + [{"name": "Ostatní", "price": other_price, "color_key": "Ostatní"}]
        else:
            entries = entries[:max_items]

    prices = [e["price"] for e in entries]
    color_keys = [str(e["color_key"]) for e in entries]
    colors_list = [_color_for_label_mapped(k, color_map) for k in color_keys]
    
    # Donut chart ve stylu dashboardu.
    fig, ax = plt.subplots(figsize=(9.8, 8.8), facecolor='white')
    ax.set_facecolor('white')
    
    wedges, _, autotexts = ax.pie(
        prices,
        labels=None,
        autopct=lambda pct: f'{pct:.0f}%' if pct >= 5 else '',
        startangle=90,
        colors=colors_list,
        textprops={'fontsize': 12, 'color': '#1f2937'},
        wedgeprops={'edgecolor': 'white', 'linewidth': 1.4, 'width': 0.52},
        pctdistance=0.75,
        radius=1.05,
    )
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(11)
    
    # Název rozpočtu nekrátit, ať je vždy vidět celý.
    ax.set_title((budget_name or "Rozpočet").strip(), fontsize=14, fontweight='semibold', pad=14, color='#111827')

    # Celková hodnota doprostřed donutu.
    total_price_value = sum(prices)
    ax.text(
        0,
        0,
        f"{total_price_value:,.0f}".replace(",", " "),
        ha='center',
        va='center',
        fontsize=22,
        fontweight='semibold',
        color='#1f2937',
    )

    # Legenda nahoře jako v dashboard přehledech.
    legend_labels = []
    total_price = sum(prices) if prices else 0
    for e in entries:
        label_name = (e["name"] or "").strip()
        if len(label_name) > 34:
            label_name = label_name[:34] + "..."
        label = label_name
        if total_price > 0:
            pct = (e["price"] / total_price) * 100.0
            label = f"{label} ({pct:.1f} %)"
        legend_labels.append(label)
    # Fixní plocha pro donut, legenda je mimo osu (na úrovni figury),
    # aby dlouhá legenda nezmenšovala samotný graf.
    ax.set_position([0.10, 0.28, 0.80, 0.66])
    fig.legend(
        wedges,
        legend_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.02),
        frameon=False,
        fontsize=11.0,
        ncol=2,
        handlelength=1.6,
        labelspacing=0.55,
        handletextpad=0.6,
        columnspacing=1.1,
    )
    ax.axis('equal')

    fig.subplots_adjust(bottom=0.22, top=0.90)
    plt.savefig(output_path, dpi=320, facecolor='white', edgecolor='none')
    plt.close()
    
    return output_path


def create_bar_chart(
    items: List[Dict[str, Any]],
    budget_name: str,
    output_path: str,
    color_map: Optional[Dict[str, str]] = None,
):
    """Vytvoří sloupcový graf (TOP položky dle ceny) pro budget."""
    if not items:
        return None

    rows = []
    for item in items:
        name = (item.get("name") or "Neznámá položka").strip()
        price = float(item.get("price", 0) or 0)
        if price > 0:
            rows.append((name, price))

    if not rows:
        return None

    # TOP 8 položek podle ceny
    rows.sort(key=lambda x: x[1], reverse=True)
    rows = rows[:8]
    names = [n[:28] + ("..." if len(n) > 28 else "") for n, _ in rows]
    prices = [p for _, p in rows]

    # Větší canvas + vyšší DPI kvůli ostrosti při velkém zobrazení v PDF.
    fig, ax = plt.subplots(figsize=(10.8, 6.6), facecolor="white")
    bar_colors = [_color_for_label_mapped(n, color_map) for n, _ in rows]
    bars = ax.bar(range(len(prices)), prices, color=bar_colors, edgecolor="#334155", linewidth=0.45)

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=24, ha="right", fontsize=15, color="#334155")
    ax.tick_params(axis="y", labelsize=15, colors="#475569")
    ax.grid(axis="y", color="#e2e8f0", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")

    # Popisky nad sloupci (zkrácené, aby nepřehušťovaly graf)
    max_price = max(prices) if prices else 0
    for rect, p in zip(bars, prices):
        label = f"{p:,.0f}".replace(",", " ")
        ax.text(
            rect.get_x() + rect.get_width() / 2.0,
            rect.get_height() + max_price * 0.015,
            label,
            ha="center",
            va="bottom",
            fontsize=13,
            color="#1e293b",
        )

    display_name = budget_name[:30] + ("..." if len(budget_name) > 30 else "")
    ax.set_title(display_name, fontsize=14, fontweight="semibold", pad=6, color="#374151")
    ax.set_ylabel("Cena (Kč)", fontsize=15, color="#475569")

    plt.tight_layout()
    plt.savefig(output_path, dpi=320, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()
    return output_path


def generate_pdf_export(round_id: UUID, db: Session, output_path: str):
    """Vygeneruje PDF: jedna srovnávací tabulka (řádky = položky, sloupce = rozpočty) + pod ní jeden graf na rozpočet."""
    _register_czech_font()
    budgets = crud.get_budgets_by_round(db, round_id)
    if not budgets:
        raise ValueError("No budgets found for this round")

    # Získat projekt pro jméno klienta a projektu
    import models
    round_obj = db.query(models.Round).filter(models.Round.id == round_id).first()
    project = crud.get_project(db, round_obj.project_id) if (round_obj and round_obj.project_id) else None
    client_name = (project.client_name or "").strip() if project else ""
    client_project_name = (project.client_project_name or "").strip() if project else ""

    root_budgets = [b for b in budgets if not b.parent_budget_id]
    if not root_budgets:
        raise ValueError("No main budgets in this round")

    def get_company_header_lines() -> List[str]:
        # Firemní údaje jsou záměrně natvrdo, bez ENV konfigurace.
        company_name = "Konderla Development, s.r.o."
        company_id = "07257500"
        company_tax_id = "CZ07257500"
        company_address = "Příkop 4, 602 00 Brno"
        company_city = ""
        company_email = "tomas@konderla.eu"
        company_phone = ""
        company_web = "konderla.eu"

        lines: List[str] = [company_name]

        id_parts = []
        if company_id:
            id_parts.append(f"IČ: {company_id}")
        if company_tax_id:
            id_parts.append(f"DIČ: {company_tax_id}")
        if id_parts:
            lines.append(" | ".join(id_parts))

        if company_address or company_city:
            address_line = " ".join(part for part in [company_address, company_city] if part)
            lines.append(address_line)
        lines.append(f"Company ID: {company_id}")
        lines.append(f"VAT number: {company_tax_id}")

        return lines[:4]

    def get_company_logo_path() -> Optional[str]:
        # Natvrdo: firemní logo pro pravý horní blok v hlavičce.
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "company-header-logo.png")
        return logo_path if os.path.isfile(logo_path) else None

    def get_signature_path() -> Optional[str]:
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "signature.png"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "company-signature.png"),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        return None

    def get_items(b):
        items = b.items if isinstance(b.items, list) else []
        return items

    def parse_number_parts(value: Any) -> List[int]:
        raw = str(value or "").strip()
        if not raw:
            return []
        return [int(x) for x in re.findall(r"\d+", raw)]

    def get_item_number_from_budgets(item_name: str, budgets_pool: List[Any]) -> str:
        for budget in budgets_pool or []:
            for item in get_items(budget):
                if (item.get("name") or "").strip() == item_name:
                    return str(item.get("number") or "")
        return ""

    # Všechna jedinečná jména položek napříč rozpočty (strukturální pořadí jako v UI)
    all_item_names = set()
    for b in root_budgets:
        for item in get_items(b):
            name = item.get("name", "")
            if name:
                all_item_names.add(name)

    primary_budget = next((b for b in root_budgets if len(get_items(b)) > 0), root_budgets[0] if root_budgets else None)
    primary_index_map: Dict[str, int] = {}
    if primary_budget:
        for idx, item in enumerate(get_items(primary_budget)):
            name = (item.get("name") or "").strip()
            if name and name not in primary_index_map:
                primary_index_map[name] = idx

    def item_sort_key(item_name: str):
        if item_name in primary_index_map:
            return (0, primary_index_map[item_name], tuple(), item_name.lower())
        number_parts = tuple(parse_number_parts(get_item_number_from_budgets(item_name, root_budgets)))
        if number_parts:
            return (1, 0, number_parts, item_name.lower())
        return (2, 0, tuple(), item_name.lower())

    all_item_names = sorted(all_item_names, key=item_sort_key)

    # Jednotná mapa barev pro grafy i sloupec "Položka" v tabulce.
    chart_priority_labels: List[str] = []
    for b in root_budgets:
        rows_for_chart: List[Tuple[str, float]] = []
        for item in get_items(b):
            name = (item.get("name") or "").strip()
            price = float(item.get("price", 0) or 0)
            if name and price > 0:
                rows_for_chart.append((name, price))
        rows_for_chart.sort(key=lambda x: x[1], reverse=True)
        # Pie: top N + "Ostatní" podle pravidel čitelnosti.
        pie_items = [{"name": name, "price": price} for name, price in rows_for_chart]
        pie_entries = _prepare_pie_entries(pie_items)
        chart_priority_labels.extend(
            [entry["name"] for entry in pie_entries if entry.get("name", "").strip().lower() != "ostatní"]
        )
        if any((entry.get("name") or "").strip().lower() == "ostatní" for entry in pie_entries):
            chart_priority_labels.append("ostatni")
        # Bar: top 8
        bar_top = rows_for_chart[:8]
        chart_priority_labels.extend([name for name, _ in bar_top])
    label_color_map = _build_label_color_map(chart_priority_labels + all_item_names)

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
        topMargin=21 * mm,
        # Footer začíná na 30 mm; držíme menší, ale bezpečnou rezervu.
        bottomMargin=32 * mm,
    )
    story = []
    logo_path = _find_logo_path()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Heading1"], fontSize=22, textColor=HexColor("#111827"),
        spaceAfter=2, spaceBefore=0, alignment=TA_LEFT, fontName=_CZECH_FONT_BOLD, leading=26,
    )
    client_style = ParagraphStyle(
        "ClientInfo", parent=styles["Normal"], fontSize=10, textColor=HexColor("#6b7280"),
        spaceAfter=12, spaceBefore=0, alignment=TA_LEFT, fontName=_CZECH_FONT,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"], fontSize=9, textColor=HexColor("#6b7280"),
        spaceAfter=16, alignment=TA_LEFT, fontName=_CZECH_FONT,
    )
    body_style = ParagraphStyle("BodyCzech", parent=styles["Normal"], fontName=_CZECH_FONT)

    story.append(Paragraph("VYHODNOCENÍ CENOVÝCH NABÍDEK", title_style))
    if client_name or client_project_name:
        lines = []
        if client_name:
            lines.append(client_name)
        if client_project_name:
            lines.append(client_project_name)
        story.append(Paragraph("<br/>".join(lines), client_style))
    story.append(Paragraph(f"Vygenerováno: {datetime.now().strftime('%d.%m.%Y %H:%M')}", subtitle_style))
    story.append(Spacer(1, 8))

    # Grafy připravit hned na začátku.
    # Každý rozpočet = 1 řádek: koláčový + sloupcový vedle sebe.
    # Velké grafy: první řádek má zaplnit většinu 1. stránky.
    chart_width = 132 * mm
    chart_height = 112 * mm
    charts_per_row = 2
    chart_rows = []
    for b in root_budgets:
        items = get_items(b)
        row_charts = []

        pie_path = os.path.join(os.path.dirname(output_path), f"chart_{b.id}_pie.png")
        if create_pie_chart(items, b.name or "Rozpočet", pie_path, color_map=label_color_map):
            row_charts.append((pie_path, b.name or "Rozpočet"))

        bar_path = os.path.join(os.path.dirname(output_path), f"chart_{b.id}_bar.png")
        if create_bar_chart(items, b.name or "Rozpočet", bar_path, color_map=label_color_map):
            row_charts.append((bar_path, b.name or "Rozpočet"))

        if row_charts:
            chart_rows.append(row_charts)

    def append_chart_row(paths_with_names):
        row_cells = []
        for path, _ in paths_with_names:
            try:
                img = Image(path, width=chart_width, height=chart_height)
                row_cells.append(img)
            except Exception:
                row_cells.append(Spacer(1, 1))
        while len(row_cells) < charts_per_row:
            row_cells.append(Spacer(chart_width, chart_height))
        # Donut chart dostane více místa než bar chart.
        tbl = Table([row_cells], colWidths=[content_width * 0.55, content_width * 0.45])
        tbl.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(tbl)

    # Všechny rozpočty vykreslit pod sebe (každý rozpočet má svůj řádek grafů).
    for row_charts in chart_rows:
        append_chart_row(row_charts)
        story.append(Spacer(1, 8))

    if chart_rows:
        story.append(Spacer(1, 6))

    # Tabulka jde na vlastní stránku, aby zůstala dobře čitelná.
    story.append(PageBreak())

    # Hlavička tabulky: Položka | Rozpočet 1 | Rozpočet 2 | ...
    header_row = [Paragraph("Položka", body_style)]
    for b in root_budgets:
        name = (b.name or "Rozpočet")[:25] + ("..." if len(b.name or "") > 25 else "")
        header_row.append(Paragraph(name, body_style))
    table_data = [header_row]

    totals = [0.0] * len(root_budgets)
    price_cell_styles = []  # Pro dynamické styly (nejnižší cena = zeleně, nejvyšší = červeně)
    item_column_styles = []  # Sloupec "Položka" barevně laděný podle grafů

    for row_idx, item_name in enumerate(all_item_names):
        row = [Paragraph((item_name[:50] + ("..." if len(item_name) > 50 else "")), body_style)]
        tint = _tint_for_label(item_name, label_color_map)
        tint_text = _text_color_for_bg(tint)
        item_column_styles.append(("BACKGROUND", (0, 1 + row_idx), (0, 1 + row_idx), HexColor(tint)))
        item_column_styles.append(("TEXTCOLOR", (0, 1 + row_idx), (0, 1 + row_idx), HexColor(tint_text)))
        prices_in_row = []
        for i, b in enumerate(root_budgets):
            p = price_for(b, item_name)
            totals[i] += p
            prices_in_row.append((p, i))
            row.append(Paragraph(f"{p:,.0f} Kč".replace(",", " "), body_style))
        table_data.append(row)
        # Zvýraznění cen v řádku: minimum zeleně, maximum červeně (jen pokud existují různé ceny)
        valid_prices = [(p, i) for p, i in prices_in_row if p > 0]
        if valid_prices:
            min_price = min(p for p, _ in valid_prices)
            max_price = max(p for p, _ in valid_prices)
            if min_price != max_price:
                for p, col_idx in valid_prices:
                    if p == min_price:
                        price_cell_styles.append(("BACKGROUND", (1 + col_idx, 1 + row_idx), (1 + col_idx, 1 + row_idx), HexColor("#dcfce7")))
                        price_cell_styles.append(("TEXTCOLOR", (1 + col_idx, 1 + row_idx), (1 + col_idx, 1 + row_idx), HexColor("#166534")))
                    elif p == max_price:
                        price_cell_styles.append(("BACKGROUND", (1 + col_idx, 1 + row_idx), (1 + col_idx, 1 + row_idx), HexColor("#fee2e2")))
                        price_cell_styles.append(("TEXTCOLOR", (1 + col_idx, 1 + row_idx), (1 + col_idx, 1 + row_idx), HexColor("#991b1b")))

    # Řádek CELKEM
    total_row = [Paragraph("<b>CELKEM</b>", body_style)]
    for t in totals:
        total_row.append(Paragraph(f"<b>{t:,.0f} Kč</b>".replace(",", " "), body_style))
    table_data.append(total_row)

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    base_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e2e8f0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#0f172a")),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), _CZECH_FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -2), 9),
        ("FONTNAME", (0, 1), (-1, -2), _CZECH_FONT),
        ("TEXTCOLOR", (0, 1), (-1, -2), HexColor("#334155")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [HexColor("#ffffff"), HexColor("#fcfdff")]),
        ("TOPPADDING", (0, 1), (-1, -2), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -2), 6),
        ("BACKGROUND", (0, -1), (-1, -1), HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, -1), (-1, -1), HexColor("#1e293b")),
        ("FONTNAME", (0, -1), (-1, -1), _CZECH_FONT_BOLD),
        ("FONTSIZE", (0, -1), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.white),
        ("LINEBELOW", (0, -2), (-1, -2), 1, HexColor("#e2e8f0")),
    ]
    table.setStyle(TableStyle(base_styles + item_column_styles + price_cell_styles))
    story.append(table)
    story.append(Spacer(1, 12))

    company_lines = get_company_header_lines()
    company_logo_path = get_company_logo_path()
    signature_path = get_signature_path()

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
        return PDFCanvas(
            path,
            *args[1:],
            logo_path=logo_path,
            company_lines=company_lines,
            company_logo_path=company_logo_path,
            owner_name="Tomáš Konderla",
            owner_title="Owner",
            owner_email="tomas@konderla.eu",
            signature_path=signature_path,
            **kwargs,
        )

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


def generate_summary_pdf_export(project_id: UUID, db: Session, output_path: str) -> str:
    """
    Vygeneruje PDF: souhrn (tabulka) mezi koly pro jeden projekt.

    Sloupce a logika odpovídají UI:
    - Firma
    - ceny v jednotlivých kolech
    - delta sloupce (Δ předchozí → aktuální) bez znaménka (UI zobrazuje abs)
    """
    _register_czech_font()

    rounds = crud.get_rounds_by_project(db, project_id)
    if not rounds:
        raise ValueError("No rounds found for this project")

    project = crud.get_project(db, project_id)
    project_name = (project.name or "").strip() if project else ""

    n_rounds = len(rounds)

    def parse_number(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            # Podpora formátů s čárkou jako desetinným oddělovačem
            raw = raw.replace(" ", "").replace(",", ".")
            try:
                return float(raw)
            except Exception:
                return None
        return None

    def get_budget_items(budget: Any) -> List[Dict[str, Any]]:
        items = getattr(budget, "items", None)
        if isinstance(items, list):
            # items je list dictů
            return [i for i in items if isinstance(i, dict)]
        if isinstance(items, dict):
            # někdy bývá obalené { list: [...] }
            maybe_list = items.get("list")
            if isinstance(maybe_list, list):
                return [i for i in maybe_list if isinstance(i, dict)]
        return []

    def get_budget_total_price(budget: Any) -> Optional[float]:
        labels = getattr(budget, "labels", None)
        if isinstance(labels, dict) and "total_price" in labels:
            val = parse_number(labels.get("total_price"))
            if val is not None:
                return val

        # fallback: součet items.price
        items = get_budget_items(budget)
        total = 0.0
        found_any = False
        for item in items:
            price_val = parse_number(item.get("price"))
            if price_val is None:
                continue
            found_any = True
            total += float(price_val)
        return total if found_any else None

    # company -> prices[] (len = n_rounds), missing value => None
    company_map: Dict[str, List[Optional[float]]] = {}
    for round_idx, r in enumerate(rounds):
        budgets = crud.get_budgets_by_round(db, r.id)
        root_budgets = [b for b in budgets if not b.parent_budget_id]
        for b in root_budgets:
            company_name = (getattr(b, "name", None) or "Bez názvu").strip() or "Bez názvu"
            if company_name not in company_map:
                company_map[company_name] = [None] * n_rounds
            company_map[company_name][round_idx] = get_budget_total_price(b)

    def format_kc(value: float) -> str:
        rounded = int(round(value))
        formatted = f"{rounded:,}".replace(",", " ")
        return f"{formatted} Kč"

    def format_maybe_kc(value: Optional[float]) -> str:
        return "—" if value is None else format_kc(value)

    def format_delta(value: Optional[float]) -> str:
        return "—" if value is None else format_kc(abs(value))

    def compute_deltas(prices: List[Optional[float]]) -> List[Optional[float]]:
        deltas: List[Optional[float]] = []
        for idx in range(n_rounds - 1):
            prev = prices[idx]
            curr = prices[idx + 1]
            if curr is None and prev is None:
                deltas.append(None)
            elif curr is not None and prev is None:
                deltas.append(curr)
            elif curr is None and prev is not None:
                deltas.append(-prev)
            else:
                deltas.append((curr or 0.0) - (prev or 0.0))
        return deltas

    company_names_sorted = sorted(company_map.keys(), key=lambda x: x.lower())

    # Hlavička tabulky odpovídá UI
    header_row: List[Any] = [Paragraph("Firma", ParagraphStyle("HeaderCell", fontName=_CZECH_FONT_BOLD, fontSize=10))]
    for r in rounds:
        header_row.append(Paragraph(str(r.name)[:25] + ("..." if len(str(r.name)) > 25 else ""), ParagraphStyle("HeaderRound", fontName=_CZECH_FONT, fontSize=9)))
    for i in range(n_rounds - 1):
        prev_name = str(rounds[i].name)
        next_name = str(rounds[i + 1].name)
        title = f"Δ {prev_name} → {next_name}"
        header_row.append(Paragraph(title[:35] + ("..." if len(title) > 35 else ""), ParagraphStyle("HeaderDelta", fontName=_CZECH_FONT, fontSize=9)))

    # Šířky sloupců: Firma + ceny + delty
    content_width = 267 * mm  # landscape A4 minus margins (stejně jako generate_pdf_export)
    col_item_w = 80 * mm
    col_price_w = (content_width - col_item_w) / (2 * n_rounds - 1) if n_rounds > 0 else 40 * mm
    col_widths = [col_item_w] + [col_price_w] * (len(header_row) - 1)

    body_style = ParagraphStyle("BodyCzechSummary", parent=getSampleStyleSheet()["Normal"], fontName=_CZECH_FONT, fontSize=8.5, leading=10)
    delta_style = ParagraphStyle("DeltaCzechSummary", parent=body_style, fontName=_CZECH_FONT_BOLD, fontSize=8.5, leading=10)

    table_data: List[List[Any]] = [header_row]
    for company_name in company_names_sorted:
        prices = company_map.get(company_name) or [None] * n_rounds
        deltas = compute_deltas(prices)

        row: List[Any] = [Paragraph((company_name[:55] + ("..." if len(company_name) > 55 else "")), body_style)]
        for p in prices:
            row.append(Paragraph(format_maybe_kc(p), body_style))
        for d in deltas:
            if d is None:
                row.append(Paragraph("—", body_style))
            else:
                row.append(Paragraph(format_delta(d), delta_style))
        table_data.append(row)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=21 * mm,
        bottomMargin=32 * mm,
    )

    story: List[Any] = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SummaryTitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=HexColor("#111827"),
        spaceAfter=4,
        spaceBefore=0,
        alignment=TA_LEFT,
        fontName=_CZECH_FONT_BOLD,
        leading=24,
    )
    subtitle_style = ParagraphStyle(
        "SummarySubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=HexColor("#6b7280"),
        spaceAfter=10,
        spaceBefore=0,
        alignment=TA_LEFT,
        fontName=_CZECH_FONT,
    )

    story.append(Paragraph("Souhrn vývoje cen mezi koly", title_style))
    if project_name:
        story.append(Paragraph(project_name, subtitle_style))
    story.append(Spacer(1, 8))

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    base_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e2e8f0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#0f172a")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), _CZECH_FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#fcfdff")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, HexColor("#cbd5e1")),
    ]
    table.setStyle(TableStyle(base_styles))
    story.append(table)

    # Header/footer konzistentní jako u generate_pdf_export
    def get_company_header_lines() -> List[str]:
        company_name = "Konderla Development, s.r.o."
        company_id = "07257500"
        company_tax_id = "CZ07257500"
        company_address = "Příkop 4, 602 00 Brno"

        lines: List[str] = [company_name]
        lines.append(f"IČ: {company_id}")
        lines.append(f"DIČ: {company_tax_id}")
        if company_address:
            lines.append(company_address)
        return lines[:4]

    def get_company_logo_path() -> Optional[str]:
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "company-header-logo.png")
        return logo_path if os.path.isfile(logo_path) else None

    def get_signature_path() -> Optional[str]:
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "signature.png"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "company-signature.png"),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        return None

    logo_path = _find_logo_path()
    company_lines = get_company_header_lines()
    company_logo_path = get_company_logo_path()
    signature_path = get_signature_path()

    def _canvas_maker(*args, **kwargs):
        if args and isinstance(args[0], str) and (args[0].endswith(".pdf") or os.path.sep in args[0]):
            path = args[0]
        elif args and hasattr(args[0], "_filename"):
            path = getattr(args[0], "_filename", output_path)
        elif args and hasattr(args[0], "filename"):
            path = getattr(args[0], "filename", output_path)
        else:
            path = output_path
        return PDFCanvas(
            path,
            *args[1:],
            logo_path=logo_path,
            company_lines=company_lines,
            company_logo_path=company_logo_path,
            owner_name="Tomáš Konderla",
            owner_title="Owner",
            owner_email="tomas@konderla.eu",
            signature_path=signature_path,
            **kwargs,
        )

    try:
        doc.build(story, canvasmaker=_canvas_maker)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("Summary PDF custom canvas failed: %s", e, exc_info=True)
        doc.build(story)

    return output_path
