from reportlab.lib import colors, utils as rl_utils
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
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
from matplotlib import font_manager as _mpl_font_manager
from matplotlib.ticker import FuncFormatter, MaxNLocator

# Výchozí styl; stejný TTF jako PDF se doplní v _ensure_matplotlib_chart_font().
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans", "DejaVu Sans Display", "Arial", "Helvetica"]
matplotlib.rcParams["font.weight"] = "normal"
matplotlib.rcParams["axes.titleweight"] = "semibold"
matplotlib.rcParams["axes.labelweight"] = "normal"
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.rcParams["axes.formatter.useoffset"] = False
matplotlib.rcParams["axes.formatter.use_mathtext"] = False
import io
import os
import hashlib
import html
import math
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
# Patička: větší odsazení od spodu (dřív ~15 mm + 4 px bylo u dlouhého textu u řezu)
_FOOTER_LINE_Y = 31 * mm
_FOOTER_FIRST_LINE_Y = 22 * mm
_FOOTER_SIGNATURE_Y = 23.8 * mm
_FOOTER_OWNER_NAME_Y = 21.1 * mm
_FOOTER_OWNER_REST_Y = 18.0 * mm

# Grafy v PDF: jednotná typografie (větší body = čitelné po zmenšení do šablony A4)
_CHART_DPI = 360
_CHART_FS_AXIS = 14
_CHART_FS_TICK = 13
_CHART_FS_LEGEND = 12
_CHART_FS_BAR_VALUE = 13
# Jedno plátno pro koláč i sloupec; nižší výška = méně místa ve flow PDF (1. strana)
_CHART_FIGSIZE = (10.8, 8.6)
_MPL_FONT_SYNCED = False


def _find_czech_font_ttf_paths() -> Tuple[Optional[str], Optional[str]]:
    """
    Stejné cesty jako při registraci TTFont pro ReportLab — aby Matplotlib kreslil
    stejným písmem jako text v PDF.
    """
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        os.path.join(base, "static", "DejaVuSans.ttf"),
        os.path.join(base, "fonts", "DejaVuSans.ttf"),
        "/Library/Fonts/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        bold_path = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf").replace(
            "LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"
        )
        bold_final = bold_path if os.path.isfile(bold_path) else None
        return path, bold_final
    return None, None


def _ensure_matplotlib_chart_font() -> None:
    """Nastaví Matplotlib na stejný TTF soubor jako ReportLab (_CZECH_FONT)."""
    global _MPL_FONT_SYNCED
    if _MPL_FONT_SYNCED:
        return
    regular, bold = _find_czech_font_ttf_paths()
    if regular:
        try:
            _mpl_font_manager.fontManager.addfont(regular)
            prop = _mpl_font_manager.FontProperties(fname=regular)
            fam = prop.get_name()
            matplotlib.rcParams["font.family"] = [fam]
            matplotlib.rcParams["font.sans-serif"] = [fam, "DejaVu Sans", "Arial", "Helvetica"]
        except Exception:
            matplotlib.rcParams["font.family"] = "sans-serif"
            matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
        if bold:
            try:
                _mpl_font_manager.fontManager.addfont(bold)
            except Exception:
                pass
    _MPL_FONT_SYNCED = True


def _format_kc_space(value: float) -> str:
    return f"{int(round(value)):,.0f}".replace(",", " ")


def _format_price_chart_label(kc: float) -> str:
    """Krátký popisek ceny: u velkých částek mil. Kč, jinak celé Kč."""
    if abs(kc) >= 1_000_000.0:
        return f"{kc / 1_000_000.0:.2f} mil. Kč".replace(".", ",")
    return f"{_format_kc_space(kc)} Kč"


def _chart_font_prop(size: float, *, bold: bool = False):
    """
    Jedno písmo pro celý graf (stejný TTF jako PDF). Legenda u koláče i osy u sloupců
    tak nepoužívají jiný fallback než nadpis.
    """
    reg, bold_path = _find_czech_font_ttf_paths()
    path_used = bold_path if (bold and bold_path and os.path.isfile(bold_path)) else reg
    if path_used and os.path.isfile(path_used):
        return _mpl_font_manager.FontProperties(fname=path_used, size=size)
    fam = (matplotlib.rcParams.get("font.sans-serif") or ["DejaVu Sans"])[0]
    return _mpl_font_manager.FontProperties(
        family=fam,
        size=size,
        weight="bold" if bold else "normal",
    )


def _plain_y_formatter_mil(v: float, _pos: Optional[int]) -> str:
    """Ticky na ose Y v mil. Kč — vždy běžné číslo, žádné 1e…"""
    if v != v or math.isinf(v):  # nan / inf
        return ""
    return f"{float(v):.2f}"


def _plain_y_formatter_tis(v: float, _pos: Optional[int]) -> str:
    if v != v or math.isinf(v):
        return ""
    return f"{v:,.0f}".replace(",", " ")


def _hide_axis_offset_text(ax) -> None:
    for axis in (ax.xaxis, ax.yaxis):
        ot = axis.get_offset_text()
        ot.set_visible(False)
        ot.set_text("")


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
        price = _parse_price_fe(item.get("price")) or 0.0
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
    path, bold_path = _find_czech_font_ttf_paths()
    if not path:
        return
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", path))
        if bold_path:
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold_path))
            _CZECH_FONT_BOLD = "DejaVuSans-Bold"
        else:
            _CZECH_FONT_BOLD = "DejaVuSans"
        _CZECH_FONT = "DejaVuSans"
    except Exception:
        pass


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


def _is_js_number(value: Any) -> bool:
    """Odpovídá `typeof x === 'number'` ve frontendu (včetně Decimal z DB, ne bool)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        from decimal import Decimal

        return isinstance(value, Decimal)
    except ImportError:
        return False


def _parse_price_fe(value: Any) -> Optional[float]:
    """Stejné jako `parsePrice` v konderla-dev-fe/pages/projects/[id].tsx (RoundView)."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if _is_js_number(value):
        v = float(value)
        return v if math.isfinite(v) else None
    raw = str(value).strip().replace(",", ".")
    if not raw:
        return None
    try:
        v = float(raw)
        return v if math.isfinite(v) else None
    except ValueError:
        return None


def _get_budget_items_fe(budget: Any) -> List[Dict[str, Any]]:
    """Stejné jako `getBudgetItemsSafe` na stránce projektu (pole nebo `items.list`)."""
    items = getattr(budget, "items", None)
    if isinstance(items, list):
        return [i for i in items if isinstance(i, dict)]
    if isinstance(items, dict):
        maybe_list = items.get("list")
        if isinstance(maybe_list, list):
            return [i for i in maybe_list if isinstance(i, dict)]
    return []


def _truncate_ellipsis(text: str, max_len: int) -> str:
    """Zkrátí řetězec na max_len znaků a na konec doplní ... pokud byl delší."""
    t = (text or "").strip()
    if not t:
        return ""
    if max_len <= 0:
        return ""
    if len(t) <= max_len:
        return t
    if max_len <= 3:
        return "." * max_len
    return t[: max_len - 3].rstrip() + "..."


# Titulky grafů a hlavičky sloupců rozpočtu v PDF — ať se dlouhé názvy vejdou.
_CHART_TITLE_MAX_LEN = 52
_TABLE_BUDGET_COL_MAX_LEN = 30


def _budget_display_name(budget: Any, *, empty_fallback: str = "Bez názvu") -> str:
    """Název firmy (`client_name`) má přednost před technickým názvem rozpočtu (`name`)."""
    cn = (getattr(budget, "client_name", None) or "").strip()
    if cn:
        return cn
    n = (getattr(budget, "name", None) or "").strip()
    return n or empty_fallback


def _budget_chart_title(budget: Any, *, empty_fallback: str = "Rozpočet") -> str:
    """Titulek grafu: technický název rozpočtu / souboru (`name`), ne název firmy — se zkrácením."""
    n = (getattr(budget, "name", None) or "").strip()
    raw = n or empty_fallback
    return _truncate_ellipsis(raw, _CHART_TITLE_MAX_LEN)


def _label_total_price_if_js_number(budget: Any) -> Optional[float]:
    """Hodnota `labels.total_price` jen pokud je numerická (jako `typeof === 'number'` v TS)."""
    labels = getattr(budget, "labels", None)
    if not isinstance(labels, dict):
        return None
    tp = labels.get("total_price")
    if not _is_js_number(tp):
        return None
    v = float(tp)
    return v if math.isfinite(v) else None


def _summary_item_price_or_zero(price: Any) -> float:
    """Odpovídá `(item?.price || 0)` v `getBudgetTotalPriceSafe` (s numerickým parsováním řetězců)."""
    if price is None or price is False or price == "":
        return 0.0
    if _is_js_number(price):
        return float(price)
    if isinstance(price, str):
        return _parse_price_fe(price) or 0.0
    return 0.0


def budget_total_summary_tab(budget: Any) -> float:
    """
    Stejné jako `getBudgetTotalPriceSafe` v ProjectDetail (záložka Souhrn kol):
    numerické `labels.total_price`, jinak součet položek `(item?.price || 0)`.
    """
    labeled = _label_total_price_if_js_number(budget)
    if labeled is not None:
        return labeled
    return sum(_summary_item_price_or_zero(item.get("price")) for item in _get_budget_items_fe(budget))


def budget_total_round_celek_row(budget: Any) -> float:
    """
    Stejné jako řádek „CELKOVÁ CENA“ v RoundView: numerické `labels.total_price`,
    jinak součet `parsePrice(item.price) || 0` přes položky.
    """
    labeled = _label_total_price_if_js_number(budget)
    if labeled is not None:
        return labeled
    return sum(
        _parse_price_fe(item.get("price")) or 0.0 for item in _get_budget_items_fe(budget)
    )


def _chart_item_rows(budget: Any, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Výběr řádků pro koláč / sloupce: stejná idea jako `main._compute_budget_total_price`.
    Když je v rozpočtu číselné `labels.total_price` (typicky import/type1), počítají se jen
    řádky sekcí — ne všechny dílčí položky, aby součet ve grafu nebyl nafouknutý oproti
    „CELKOVÁ CENA“. Bez číselného labelu bereme všechny řádky jako při fallbacku ve webové tabulce.
    """
    dict_items = [i for i in items if isinstance(i, dict)]
    if not dict_items:
        return []
    if _label_total_price_if_js_number(budget) is not None:
        # Stejně jako main._compute_budget_total_price – jen skutečné sekční hlavičky
        section_items = [it for it in dict_items if it.get("is_section_header") is True]
        return section_items if section_items else dict_items
    return dict_items


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

        footer_top_y = _FOOTER_LINE_Y
        self.line(15 * mm, footer_top_y, page_w - 15 * mm, footer_top_y)

        # Levá část patičky: logo + firemní info
        left_x = 15 * mm
        if self.company_lines:
            first_line_y = _FOOTER_FIRST_LINE_Y
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
                        _FOOTER_SIGNATURE_Y,
                        width=w,
                        height=h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
            except Exception:
                pass

        self.setFillColor(HexColor("#111827"))
        self.setFont(_CZECH_FONT_BOLD, 8.4)
        self.drawRightString(right_x, _FOOTER_OWNER_NAME_Y, self.owner_name)
        self.setFont(_CZECH_FONT, 7.7)
        self.setFillColor(HexColor("#374151"))
        right_line_y = _FOOTER_OWNER_REST_Y
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


_GAP_SLICE_NAME = "Rozdíl k celkové ceně"
_GAP_COLOR = "#94a3b8"
_PIE_TOTAL_EPS = 0.5


def create_pie_chart(
    items: List[Dict[str, Any]],
    budget: Any,
    budget_name: str,
    output_path: str,
    color_map: Optional[Dict[str, str]] = None,
    total_display: Optional[float] = None,
):
    """
    Koláč pro rozpočet. Řádky vycházejí z _chart_item_rows (sekce vs. všechny řádky).
    Střed a součet řezů odpovídají řádku „CELKOVÁ CENA“ (total_display).
    Pokud je celková cena vyšší než součet řezů, přidá se šedý řez „Rozdíl k celkové ceně“.
    """
    if not items:
        return None

    row_items = _chart_item_rows(budget, items)
    entries = _prepare_pie_entries(row_items)
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

    sum_slices = float(sum(e["price"] for e in entries))
    td = total_display
    if td is not None and td > sum_slices + _PIE_TOTAL_EPS:
        entries.append(
            {
                "name": _GAP_SLICE_NAME,
                "price": td - sum_slices,
                "color_key": "__budget_gap__",
            }
        )
    elif td is not None and td + _PIE_TOTAL_EPS < sum_slices:
        # Nepodporovaný rozpor (label < součet položek): střed sjednotíme se součtem řezů
        td = None

    _ensure_matplotlib_chart_font()

    prices = [e["price"] for e in entries]
    colors_list = []
    for e in entries:
        if e.get("color_key") == "__budget_gap__":
            colors_list.append(_GAP_COLOR)
        else:
            colors_list.append(_color_for_label_mapped(str(e.get("color_key", e.get("name"))), color_map))
    
    fig_w, fig_h = _CHART_FIGSIZE
    fig, ax = plt.subplots(figsize=_CHART_FIGSIZE, facecolor="white")
    ax.set_facecolor("white")

    # Vnitřek donutu: původní vzhled (velikosti / celé Kč ve středu), ne zjednodušené „mil. Kč“.
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
    ax.set_aspect("equal")
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(11)

    # Celková hodnota doprostřed donutu = stejná logika jako „CELKOVÁ CENA“ (ne jen součet řezů před doplňkem).
    total_price_value = float(td) if td is not None else float(sum(prices))
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

    # Legenda: procenta vůči stejnému celku jako střed donutu
    legend_labels = []
    denom = total_price_value if total_price_value > 0 else (sum(prices) if prices else 0.0)
    for e in entries:
        label_name = (e["name"] or "").strip()
        if len(label_name) > 34:
            label_name = label_name[:34] + "..."
        label = label_name
        if denom > 0:
            pct = (e["price"] / denom) * 100.0
            label = f"{label} ({pct:.1f} %)"
        legend_labels.append(label)
    # Čtverec v palcích: w*h_fig == h*w_fig → kruh při obdélníkovém plátně
    h_frac = 0.48
    w_frac = h_frac * (fig_h / fig_w)
    left = (1.0 - w_frac) / 2.0
    ax.set_position([left, 0.26, w_frac, h_frac])
    fig.legend(
        wedges,
        legend_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.02),
        frameon=False,
        ncol=2,
        handlelength=1.6,
        labelspacing=0.55,
        handletextpad=0.6,
        columnspacing=1.1,
        prop=_chart_font_prop(_CHART_FS_LEGEND, bold=False),
    )
    ax.set_aspect("equal")

    # Nadpis rozpočtu je v PDF (ReportLab), ne zde — víc místa pro graf
    fig.subplots_adjust(bottom=0.22, top=0.96)
    _ = budget_name
    plt.savefig(output_path, dpi=_CHART_DPI, facecolor="white", edgecolor="none")
    plt.close()
    
    return output_path


def create_bar_chart(
    items: List[Dict[str, Any]],
    budget: Any,
    budget_name: str,
    output_path: str,
    color_map: Optional[Dict[str, str]] = None,
):
    """Vytvoří sloupcový graf (TOP položky dle ceny) — stejná báze řádků jako koláč."""
    if not items:
        return None

    row_items = _chart_item_rows(budget, items)
    rows = []
    for item in row_items:
        name = (item.get("name") or "Neznámá položka").strip()
        price = _parse_price_fe(item.get("price")) or 0.0
        if price > 0:
            rows.append((name, price))

    if not rows:
        return None

    _ensure_matplotlib_chart_font()

    # TOP 8 položek podle ceny
    rows.sort(key=lambda x: x[1], reverse=True)
    rows = rows[:8]
    names = [n[:28] + ("..." if len(n) > 28 else "") for n, _ in rows]
    prices = [p for _, p in rows]
    max_p = max(prices) if prices else 0.0
    if max_p < 1_000_000.0:
        y_values = [p / 1_000.0 for p in prices]
        y_unit = "tis. Kč"
        y_formatter = _plain_y_formatter_tis
    else:
        y_values = [p / 1_000_000.0 for p in prices]
        y_unit = "mil. Kč"
        y_formatter = _plain_y_formatter_mil

    fig, ax = plt.subplots(figsize=_CHART_FIGSIZE, facecolor="white")
    bar_colors = [_color_for_label_mapped(n, color_map) for n, _ in rows]
    bars = ax.bar(
        range(len(y_values)),
        y_values,
        width=0.82,
        color=bar_colors,
        edgecolor="#334155",
        linewidth=0.45,
    )

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=24, ha="right", rotation_mode="anchor", color="#334155")
    for _lbl in ax.get_xticklabels():
        _lbl.set_fontproperties(_chart_font_prop(_CHART_FS_TICK))
        _lbl.set_clip_on(False)
    ax.tick_params(axis="y", colors="#475569")
    ax.tick_params(axis="x", colors="#334155", pad=8)
    for _lbl in ax.get_yticklabels():
        _lbl.set_fontproperties(_chart_font_prop(_CHART_FS_TICK))
    ax.grid(axis="y", color="#e2e8f0", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")

    ax.yaxis.set_major_locator(MaxNLocator(nbins=9))
    ax.yaxis.set_major_formatter(FuncFormatter(y_formatter))
    _hide_axis_offset_text(ax)
    ax.margins(x=0.04)

    ymax = max(y_values) if y_values else 0.0
    for i, (rect, p_kc) in enumerate(zip(bars, prices)):
        label = _format_price_chart_label(p_kc)
        h = rect.get_height()
        pad = ymax * 0.028 if ymax > 0 else 0.0
        if i % 2 == 1 and ymax > 0 and h > 0.42 * ymax:
            pad += ymax * 0.035
        ax.text(
            rect.get_x() + rect.get_width() / 2.0,
            h + pad,
            label,
            ha="center",
            va="bottom",
            fontproperties=_chart_font_prop(_CHART_FS_BAR_VALUE),
            color="#1e293b",
        )

    if ymax > 0:
        ax.set_ylim(0, ymax * 1.08)

    ax.set_ylabel(
        f"Cena ({y_unit})",
        fontproperties=_chart_font_prop(_CHART_FS_AXIS),
        color="#475569",
    )

    plt.subplots_adjust(left=0.26, right=0.98, top=0.96, bottom=0.32)
    _ = budget_name
    plt.savefig(
        output_path,
        dpi=_CHART_DPI,
        bbox_inches="tight",
        pad_inches=0.14,
        facecolor="white",
        edgecolor="none",
    )
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
        company_id = "07257309"
        company_tax_id = "CZ07257309"
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

        return lines

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
        return _get_budget_items_fe(b)

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
        for item in _chart_item_rows(b, get_items(b)):
            name = (item.get("name") or "").strip()
            price = _parse_price_fe(item.get("price")) or 0.0
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

    # Cena položky v daném rozpočtu (stejně jako RoundView: parsePrice || 0)
    def price_for(b, item_name):
        for item in get_items(b):
            if (item.get("name") or "").strip() == item_name:
                return _parse_price_fe(item.get("price")) or 0.0
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
        # Rezerva pro patičku (čára + víceřádkový text výš od spodu).
        bottomMargin=38 * mm,
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
        spaceAfter=10, alignment=TA_LEFT, fontName=_CZECH_FONT,
    )
    body_style = ParagraphStyle("BodyCzech", parent=styles["Normal"], fontName=_CZECH_FONT)
    chart_caption_style = ParagraphStyle(
        "ChartFileCaption",
        parent=body_style,
        fontName=_CZECH_FONT_BOLD,
        fontSize=10,
        leading=12,
        textColor=HexColor("#111827"),
        alignment=TA_CENTER,
        spaceAfter=1,
        spaceBefore=0,
    )

    story.append(Paragraph("VYHODNOCENÍ CENOVÝCH NABÍDEK", title_style))
    if client_name or client_project_name:
        lines = []
        if client_name:
            lines.append(client_name)
        if client_project_name:
            lines.append(client_project_name)
        story.append(Paragraph("<br/>".join(lines), client_style))
    story.append(Paragraph(f"Vygenerováno: {datetime.now().strftime('%d.%m.%Y %H:%M')}", subtitle_style))

    firma_style = ParagraphStyle(
        "FirmaHeader",
        parent=styles["Normal"],
        fontSize=10,
        textColor=HexColor("#374151"),
        spaceAfter=4,
        spaceBefore=0,
        alignment=TA_LEFT,
        fontName=_CZECH_FONT,
    )
    firma_warn_style = ParagraphStyle(
        "FirmaWarn",
        parent=styles["Normal"],
        fontSize=10,
        textColor=HexColor("#dc2626"),
        spaceAfter=8,
        spaceBefore=0,
        alignment=TA_LEFT,
        fontName=_CZECH_FONT_BOLD,
    )
    story.append(Spacer(1, 4))

    # Grafy: každý rozpočet = řádek koláč + sloupec. Název firmy vždy u příslušných grafů;
    # KeepTogether zajistí, že se řádek s firmou a grafy na stránce nerozdělí.
    chart_width = 128 * mm
    chart_height = 98 * mm
    charts_per_row = 2

    def build_chart_table(paths_with_names):
        """Nadpis (název rozpočtu/souboru) v PDF — stejná velikost a řádek u obou grafů."""
        title_row: List[Any] = []
        img_row: List[Any] = []
        for path, cap in paths_with_names:
            t = (cap or "Rozpočet").strip()
            title_row.append(Paragraph(html.escape(t).replace("\n", " "), chart_caption_style))
            try:
                img_row.append(Image(path, width=chart_width, height=chart_height))
            except Exception:
                img_row.append(Spacer(1, 1))
        while len(title_row) < charts_per_row:
            title_row.append(Spacer(1, 1))
            img_row.append(Spacer(chart_width, chart_height))
        tbl = Table([title_row, img_row], colWidths=[content_width * 0.55, content_width * 0.45])
        tbl.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, 0), "TOP"),
                    ("VALIGN", (0, 1), (-1, 1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return tbl

    chart_blocks = 0
    for b in root_budgets:
        items = get_items(b)
        row_charts = []

        pie_path = os.path.join(os.path.dirname(output_path), f"chart_{b.id}_pie.png")
        pie_total = budget_total_round_celek_row(b)
        chart_title = _budget_chart_title(b)
        if create_pie_chart(
            items,
            b,
            chart_title,
            pie_path,
            color_map=label_color_map,
            total_display=pie_total,
        ):
            row_charts.append((pie_path, chart_title))

        bar_path = os.path.join(os.path.dirname(output_path), f"chart_{b.id}_bar.png")
        if create_bar_chart(items, b, chart_title, bar_path, color_map=label_color_map):
            row_charts.append((bar_path, chart_title))

        if not row_charts:
            continue

        cn = (getattr(b, "client_name", None) or "").strip()
        if cn:
            firma_p = Paragraph(cn, firma_style)
        else:
            firma_p = Paragraph("chybí jméno stavební firmy", firma_warn_style)
        chart_tbl = build_chart_table(row_charts)
        story.append(KeepTogether([firma_p, Spacer(1, 2), chart_tbl]))
        story.append(Spacer(1, 4))
        chart_blocks += 1

    if chart_blocks > 0:
        story.append(Spacer(1, 6))

    # Tabulka jde na vlastní stránku, aby zůstala dobře čitelná.
    story.append(PageBreak())

    # Hlavička tabulky: Položka | Rozpočet 1 | Rozpočet 2 | ...
    header_row = [Paragraph("Položka", body_style)]
    for b in root_budgets:
        dn = _budget_display_name(b, empty_fallback="Rozpočet")
        name = _truncate_ellipsis(dn, _TABLE_BUDGET_COL_MAX_LEN)
        header_row.append(Paragraph(name, body_style))
    table_data = [header_row]

    # Řádek CELKEM = stejná logika jako „CELKOVÁ CENA“ ve webové tabulce (label / součet parsePrice)
    totals = [budget_total_round_celek_row(b) for b in root_budgets]
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

    # company -> prices[] (len = n_rounds), missing value => None
    company_map: Dict[str, List[Optional[float]]] = {}
    for round_idx, r in enumerate(rounds):
        budgets = crud.get_budgets_by_round(db, r.id)
        root_budgets = [b for b in budgets if not b.parent_budget_id]
        for b in root_budgets:
            base = _budget_display_name(b, empty_fallback="Bez názvu")
            key = base
            suffix = 2
            while key in company_map and company_map[key][round_idx] is not None:
                key = f"{base} ({suffix})"
                suffix += 1
            if key not in company_map:
                company_map[key] = [None] * n_rounds
            company_map[key][round_idx] = budget_total_summary_tab(b)

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
        firma_label = html.escape(company_name[:55] + ("..." if len(company_name) > 55 else ""))
        row: List[Any] = [Paragraph(firma_label, body_style)]
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
        bottomMargin=38 * mm,
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
        company_id = "07257309"
        company_tax_id = "CZ07257309"
        company_address = "Příkop 4, 602 00 Brno"

        lines: List[str] = [company_name]
        lines.append(f"IČ: {company_id}")
        lines.append(f"DIČ: {company_tax_id}")
        if company_address:
            lines.append(company_address)
        lines.append(f"Company ID: {company_id}")
        lines.append(f"VAT number: {company_tax_id}")
        return lines

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
