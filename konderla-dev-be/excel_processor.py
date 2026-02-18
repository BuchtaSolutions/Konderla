import pandas as pd
import re
from typing import List, Dict, Any, Optional

def clean_price(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        v = float(value)
        return v if abs(v) < 1e12 else 0.0
    if isinstance(value, str):
        s = value.strip()
        s = re.sub(r"\s+", "", s)
        if not s or not re.search(r"\d", s):
            return 0.0
        # Český formát: mezery = tisíce, čárka = desetinná; nebo tečka = tisíce, čárka = desetinná
        has_comma = "," in s
        has_dot = "." in s
        if has_comma and has_dot:
            # např. "45.172.993,25" – tečka = tisíce, čárka = desetinná
            s = s.replace(".", "").replace(",", ".")
        elif has_comma:
            # "45 172 993,25" nebo "45172993,25"
            s = s.replace(",", ".")
        else:
            # "45 172 993" nebo "45172993" – jen odstraň mezery (už jsme je odstranili)
            pass
        # Odstranit vše kromě číslic, teček a mínusů (včetně "Kč", mezer, atd.)
        s = re.sub(r"[^\d.-]", "", s)
        if not s:
            return 0.0
        try:
            v = float(s)
            return v if abs(v) < 1e12 else 0.0
        except ValueError:
            return 0.0
    return 0.0

def _looks_like_formula_or_continuation(name: str) -> bool:
    """Vyřadí vzorce (7,50*1,50), čistá čísla (11,25000) a pokračovací řádky (text končící ' : ')."""
    if not name or not isinstance(name, str):
        return True
    s = name.strip()
    if not s or len(s) < 2:
        return True
    lower = s.lower()
    # Vzorce s operátory - pouze pokud jsou mezi čísly (např. "7,50*1,50" nebo "10/2")
    # "/" nebo "*" mezi slovy (např. "podloží / pláně") NENÍ vzorec
    if "*" in s:
        # Pokud obsahuje "*", zkontroluj, jestli je to vzorec (čísla kolem *)
        if re.search(r'\d[^\w]*\*[^\w]*\d', s.replace(" ", "")):
            return True
    if "/" in s:
        # Pokud obsahuje "/", zkontroluj, jestli je to vzorec (čísla kolem / bez mezer nebo s písmeny)
        # Ale "/" mezi slovy s mezerami (např. "podloží / pláně") není vzorec
        # Vzorec by měl být něco jako "7,50/2" nebo "10/5" bez mezer kolem /
        if re.search(r'\d[^\w\s]*/[^\w\s]*\d', s.replace(" ", "")):
            # Ale pokud je "/" mezi písmeny nebo slovy s mezerami, není to vzorec
            if not re.search(r'[a-zA-Zá-žÁ-Ž]\s*/\s*[a-zA-Zá-žÁ-Ž]', s):
                return True
    # Čistá čísla (ale ne pokud je to část názvu jako "SO 1000")
    if re.match(r"^[\d\s,.\-]+$", s) and len(s) > 2 and "so" not in lower:
        return True
    # Pokračovací řádky končící " : "
    if s.endswith(" : ") or (s.endswith(" :") and len(s) < 80):
        return True
    # Metadata řádky
    if "začátek provozního součtu" in lower or "konec provozního součtu" in lower:
        return True
    if "součet:" in lower and len(s) < 50:
        return True
    return False


def is_valid_name(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    text = text.strip()
    if len(text) < 1:
        return False
        
    lower = text.lower()
    if lower in ["nan", "null", "none", "0", "0.0"]:
        return False
    
    # Metadata blacklist
    blacklist = [
        "tel:", "tel.", "fax:", "fax.", "e-mail", "email", 
        "ič:", "ičo:", "dič:", "dič ", "psč", 
        "zadavatel", "zhotovitel", "objednatel", "vypracoval", "vyřizuje", 
        "datum", "číslo nabídky", "strana:", "strana ", "projektant"
    ]
    
    for kw in blacklist:
        if kw in lower:
             # Strong check to avoid false positives
             if kw in ["ič:", "dič:", "tel:", "fax:", "strana:"]:
                 # If these are present, it's almost certainly a header/footer
                 return False
             if kw == "strana " and re.search(r'strana\s+\d', lower):
                 return False
             # "email" might be part of a description? Unlikely in budget items.
             if kw in lower and len(text) < 50:
                 return False
            
    return True

import os

# Kód vypadá jako odkaz na podlist (IO 710, SO 000, IO 720a) – použije se pro napojení child sheetů
def _is_subsheet_code(code: str) -> bool:
    if not code or not isinstance(code, str):
        return False
    code = code.strip()
    if len(code) < 3:
        return False
    # IO 710, SO 000, IO 720a, SO 606a – písmena + čísla (s tečkou/písmenem)
    return bool(re.match(r"^[A-Z]{2,}\s*[\dA-Za-z.]+\s*$", code, re.IGNORECASE))

def extract_project_name(df: pd.DataFrame) -> Optional[str]:
    # Scan first 20 rows for generic project info
    for idx in range(min(20, len(df))):
        row = df.iloc[idx]
        for col_i, val in enumerate(row.values):
            val_str = str(val).strip()
            val_lower = val_str.lower()
            if val_lower.startswith(("stavba", "akce", "projekt", "název")):
                # Check for "Stavba: Project Name" format
                if ":" in val_str:
                     parts = val_str.split(":", 1)
                     if len(parts) > 1 and len(parts[1].strip()) > 3:
                         return parts[1].strip()
                
                # Check next few columns (up to 3 headers away)
                for offset in range(1, 5):
                    if col_i + offset < len(row.values):
                        next_val = str(row.values[col_i + offset]).strip()
                        if len(next_val) > 3 and next_val.lower() not in ["nan", "none", "null"]:
                            return next_val
                # Krycí list: "NÁZEV AKCE :" on one row, name on next row – use next row first cell
                if idx + 1 < len(df) and ("akce" in val_lower or "název" in val_lower):
                    next_row = df.iloc[idx + 1]
                    for c in range(min(3, len(next_row.values))):
                        cell = str(next_row.values[c]).strip()
                        if len(cell) > 3 and cell.lower() not in ["nan", "none", "null"] and is_valid_name(cell):
                            return cell
    return None

def process_excel_file(file_path: str, provided_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    filename = os.path.basename(file_path)
    try:
        # CSV: jeden list Rekapitulace (Pozice;Popis;Cena)
        if file_path.lower().endswith(".csv"):
            try:
                df = pd.read_csv(file_path, sep=None, engine="python", header=None, encoding="utf-8")
            except Exception:
                df = pd.read_csv(file_path, sep=";", header=None, encoding="utf-8")
            if df is not None and len(df) >= 2:
                if _is_type3_content(df):
                    result3 = _parse_type3_single_sheet(df)
                    if result3:
                        print(f"CSV parsed as Type 3 (Unistav) -> parent items: {len(result3.get('parent_budget', {}).get('items', []))}, child budgets: {len(result3.get('child_budgets', []))}")
                        return result3
                parent_items, child_budgets = _parse_rekapitulace_single_sheet(df)
                if parent_items:
                    project_name = provided_name if provided_name else filename.rsplit(".", 1)[0]
                    print(f"CSV parsed as Type 2 Rekapitulace -> {len(parent_items)} parent items")
                    return {
                        "type": "type2",
                        "parent_budget": {"name": project_name, "items": parent_items},
                        "child_budgets": child_budgets,
                    }
            print("CSV could not be parsed as Rekapitulace or Type 3")
            return None

        xls = pd.ExcelFile(file_path)
        sheet_names = xls.sheet_names
        print(f"Processing Excel: sheets = {sheet_names}")

        has_stavba = any("stavba" == s.lower() for s in sheet_names)
        has_kryci = any("krycí" in s.lower() for s in sheet_names)
        has_rekapitulace = any("rekapitulace" in s.lower() for s in sheet_names)

        if has_stavba:
            print("Detected Type 1 (Stavba)")
            return process_type_1(xls, filename, provided_name)

        # Type 3 (Var 3): jakýkoli list se strukturou SOUPIS PRACÍ + PČ/Typ/Kód + D/K řádky – stejný parser pro všechny takové xlsx
        print(f"[Type3 Var3] Checking {len(sheet_names)} sheets for Var 3 pattern...")
        for sheet_name in sheet_names:
            if "pokyny" in sheet_name.lower():
                print(f"[Type3 Var3]   Skipping sheet '{sheet_name}' (pokyny)")
                continue
            try:
                df_sheet = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                if df_sheet is None or len(df_sheet) < 50:
                    print(f"[Type3 Var3]   Sheet '{sheet_name}': skipped (rows={len(df_sheet) if df_sheet is not None else 0})")
                    continue
                has_pattern = _sheet_has_unistav_soupis_pattern(df_sheet)
                print(f"[Type3 Var3]   Sheet '{sheet_name}': pattern={has_pattern}, rows={len(df_sheet)}")
                if not has_pattern:
                    continue
                print(f"[Type3 Var3]   Parsing sheet '{sheet_name}' with _parse_unistav_soupis...")
                parent_items_u, child_budgets_u = _parse_unistav_soupis(df_sheet)
                print(f"[Type3 Var3]   Result: {len(parent_items_u)} parent items, {len(child_budgets_u)} child budgets")
                if parent_items_u or child_budgets_u:
                    project_name = provided_name if provided_name else filename.rsplit(".", 1)[0]
                    print(
                        f"Excel '{filename}' parsed as Type 3 (Var 3 Soupis pattern) using sheet '{sheet_name}' -> "
                        f"{len(parent_items_u)} parent items, {len(child_budgets_u)} child budgets"
                    )
                    return {
                        "type": "type3",
                        "parent_budget": {"name": project_name, "items": parent_items_u},
                        "child_budgets": child_budgets_u,
                    }
            except Exception as e:
                print(f"[Type3 Var3]   Sheet '{sheet_name}' failed: {e}")
                import traceback
                traceback.print_exc()
                continue

        # Heuristika pro Unistav export: list „Rekapitulace stavby“ + Soupis v jiném listu (zachováno pro kompatibilitu)
        unistav_rekap_sheets = [s for s in sheet_names if "rekapitulace stavby" in s.lower()]
        if unistav_rekap_sheets:
            try:
                df_unistav = pd.read_excel(xls, sheet_name=unistav_rekap_sheets[0], header=None)
                # Nejprve zkusit vytáhnout hierarchii ze Soupisu prací v jiném listu
                soup_sheets = [s for s in sheet_names if s not in unistav_rekap_sheets and "pokyny" not in s.lower()]
                parent_items_unistav: List[Dict[str, Any]] = []
                child_budgets_unistav: List[Dict[str, Any]] = []
                if soup_sheets:
                    df_soup = pd.read_excel(xls, sheet_name=soup_sheets[0], header=None)
                    print(f"DEBUG: Calling _parse_unistav_soupis with sheet '{soup_sheets[0]}', df shape: {df_soup.shape}")
                    parent_items_unistav, child_budgets_unistav = _parse_unistav_soupis(df_soup)
                    print(f"DEBUG: _parse_unistav_soupis returned: {len(parent_items_unistav)} parent items, {len(child_budgets_unistav)} child budgets")

                print(f"DEBUG: After _parse_unistav_soupis: parent_items_unistav={len(parent_items_unistav)}, child_budgets_unistav={len(child_budgets_unistav)}")
                if parent_items_unistav or child_budgets_unistav:
                    project_name = provided_name if provided_name else filename.rsplit(".", 1)[0]
                    print(
                        f"Excel '{filename}' parsed as Type 3 (Unistav Soupis heuristic) "
                        f"using sheet '{soup_sheets[0]}' -> "
                        f"{len(parent_items_unistav)} parent items, {len(child_budgets_unistav)} child budgets"
                    )
                    return {
                        "type": "type3",
                        "parent_budget": {
                            "name": project_name,
                            "items": parent_items_unistav,
                        },
                        "child_budgets": child_budgets_unistav,
                    }
                else:
                    print(f"DEBUG: Skipping Unistav Soupis result - both lists are empty")

                # Fallback: použít jen rekapitulaci stavby (jedna položka „Bytový dům“)
                parent_items_unistav = _parse_unistav_rekap_stavby(df_unistav)
                if parent_items_unistav:
                    project_name = provided_name if provided_name else filename.rsplit(".", 1)[0]
                    print(f"Excel '{filename}' parsed as Type 3 (Unistav stavba heuristic) using sheet '{unistav_rekap_sheets[0]}' -> {len(parent_items_unistav)} parent items")
                    return {
                        "type": "type3",
                        "parent_budget": {
                            "name": project_name,
                            "items": parent_items_unistav,
                        },
                        "child_budgets": [],
                    }
            except Exception as e:
                print(f"Type 3 heuristic for '{filename}' failed: {e}")

        # Type 3 (Unistav): zkusit před Type 2, protože má velmi specifické hlavičky
        for sheet in sheet_names[:5]:
            try:
                df_sheet = pd.read_excel(xls, sheet_name=sheet, header=None)
                if df_sheet is not None and len(df_sheet) >= 10 and _is_type3_content(df_sheet):
                    result3 = _parse_type3_single_sheet(df_sheet)
                    if result3:
                        print(f"Excel sheet '{sheet}' parsed as Type 3 (Unistav)")
                        return result3
            except Exception:
                pass

        # Type 2: Rekapitulace Pozice/Popis/Cena (včetně fallbacku „child sheets only“)
        result = process_type_2(xls, filename, provided_name)
        has_parent = bool(result and result.get("parent_budget", {}).get("items"))
        has_children = bool(result and result.get("child_budgets"))
        if has_parent or has_children:
            print("Using Type 2 (Rekapitulace)" + (" with parent items" if has_parent else " (child sheets only)"))
            return result
        if has_kryci or has_rekapitulace:
            print("Detected Krycí list or Rekapitulace, returning Type 2 result")
            return result

        print("Using fallback (Default to Type 1)")
        return process_type_1(xls, filename, provided_name)

    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()
        return None

def find_header_row(df: pd.DataFrame, prefer_celkem_for_price: bool = False) -> Dict[str, Any]:
    # Keywords
    kw_code = ["číslo", "cislo", "kód", "kod", "pč", "pol", "poř", "id", "označení", "p.č."]
    kw_name = ["název", "nazev", "popis", "zkrácený", "text", "položka"]
    kw_price = ["cena", "celkem", "náklady", "odbytová", "montáž", "dodávka", "jednotková"]

    best_row_idx = -1
    best_mapping = {}
    best_score = 0

    for idx in range(min(50, len(df))):
        row = df.iloc[idx]
        row_str = " ".join([str(x).lower() for x in row.values if pd.notna(x)])

        current_mapping = {}
        price_candidates = []  # (col_i, has_celkem)

        for col_i, val in enumerate(row.values):
            val_str = str(val).lower()
            if "zakázky" in val_str or "projektu" in val_str:
                continue

            if 'number' not in current_mapping and any(k in val_str for k in kw_code):
                current_mapping['number'] = col_i

            if 'name' not in current_mapping and any(k in val_str for k in kw_name) and "měrná" not in val_str:
                current_mapping['name'] = col_i

            if any(k in val_str for k in kw_price) and "dph" not in val_str:
                has_celkem = "celkem" in val_str and "cena" not in val_str
                price_candidates.append((col_i, has_celkem))

        if price_candidates:
            if prefer_celkem_for_price:
                # Prefer column that is "Celkem" (total), not "Cena / MJ" (unit price)
                celkem_cols = [c for c, has_celkem in price_candidates if has_celkem]
                current_mapping['price'] = celkem_cols[0] if celkem_cols else price_candidates[0][0]
            else:
                current_mapping['price'] = price_candidates[0][0]

        score = 0
        if 'name' in current_mapping:
            score += 2
        if 'number' in current_mapping:
            score += 1
        if 'price' in current_mapping:
            score += 1
        if idx < 5 and score < 4:
            score -= 1

        if 'name' in current_mapping and ('number' in current_mapping or 'price' in current_mapping):
            if score > best_score:
                best_score = score
                best_row_idx = idx
                best_mapping = current_mapping

    return {"idx": best_row_idx, "map": best_mapping}


def _is_type3_content(df: pd.DataFrame) -> bool:
    """Detekce varianty 3: přítomnost 'REKAPITULACE ČLENĚNÍ SOUPISU PRACÍ' a 'SOUPIS PRACÍ'."""
    if df is None or len(df) < 10:
        return False
    full_text = ""
    for idx in range(min(200, len(df))):
        row = df.iloc[idx]
        full_text += " ".join(str(x) for x in row.values if pd.notna(x) and str(x).strip()) + " "
    full_text_lower = full_text.lower()
    has_rekap = "rekapitulace členění soupisu prací" in full_text_lower
    has_soupis = "soupis prací" in full_text_lower or "soupis praci" in full_text_lower
    return bool(has_rekap and has_soupis)


def _sheet_has_unistav_soupis_pattern(df: pd.DataFrame) -> bool:
    """Detekce listu se strukturou Type 3 Soupis: řádek s PČ, Typ, Kód (+ volitelně ‚soupis prací‘). Stačí hlavička a řádky D/K."""
    if df is None or len(df) < 20:
        return False
    header_idx = -1
    has_soupis = False
    typ_col_idx = -1
    for idx in range(min(250, len(df))):
        row = df.iloc[idx]
        row_text = " ".join(str(v).lower() for v in row.values if pd.notna(v))
        if "soupis prací" in row_text or "soupis praci" in row_text:
            has_soupis = True
        if "pč" in row_text and "typ" in row_text and ("kód" in row_text or "kod" in row_text):
            header_idx = idx
            for c, val in enumerate(row.values):
                if pd.notna(val) and str(val).strip().upper() == "TYP":
                    typ_col_idx = c
                    break
            break
    if header_idx < 0 or typ_col_idx < 0:
        return False
    # Ověřit, že pod hlavičkou jsou řádky D a K
    seen_d = seen_k = False
    for idx in range(header_idx + 1, min(header_idx + 500, len(df))):
        row = df.iloc[idx]
        if typ_col_idx >= len(row):
            continue
        typ = str(row.iloc[typ_col_idx]).strip().upper() if pd.notna(row.iloc[typ_col_idx]) else ""
        if typ == "D":
            seen_d = True
        if typ == "K":
            seen_k = True
        if seen_d and seen_k:
            return True
    return bool(has_soupis and header_idx >= 0)


def _parse_unistav_rekap_stavby(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Speciální parser pro Unistav list 'Rekapitulace stavby' s blokem
    'REKAPITULACE OBJEKTŮ STAVBY A SOUPISŮ PRACÍ'.
    Vytáhne objekty (Bytový dům, atd.) jako parent items.
    """
    if df is None or len(df) < 10:
        return []

    header_idx = -1
    col_code = -1
    col_name = -1
    col_price = -1

    # Najít hlavičku: řádek obsahující "Objekt, Soupis prací" a "Cena bez DPH"
    for idx in range(min(100, len(df))):
        row = df.iloc[idx]
        row_lower = [str(v).lower() for v in row.values if pd.notna(v)]
        has_obj = any("objekt" in v and "soupis" in v for v in row_lower)
        has_price = any("cena bez dph" in v for v in row_lower)
        has_kod = any("kód" in v or "kod" in v for v in row_lower)
        if has_obj and has_price and has_kod:
            header_idx = idx
            for c, val in enumerate(row.values):
                v = str(val).strip().lower() if pd.notna(val) else ""
                if ("kód" in v or "kod" in v) and col_code == -1:
                    col_code = c
                elif "objekt" in v and "soupis" in v and col_name == -1:
                    col_name = c
                elif "cena bez dph" in v and col_price == -1:
                    col_price = c
            break

    if header_idx == -1 or col_name == -1 or col_price == -1:
        return []

    parent_items: List[Dict[str, Any]] = []

    for idx in range(header_idx + 1, len(df)):
        row = df.iloc[idx]
        # Přeskočit prázdné řádky
        if all((not pd.notna(v)) or (str(v).strip() == "") for v in row.values):
            continue

        # Zjistit název objektu/soupisu – Unistav má hlavičku v jednom sloupci,
        # ale samotná data často v jiných (např. sloupec 3 + 9).
        name = ""
        if 0 <= col_name < len(row) and pd.notna(row.iloc[col_name]):
            name = str(row.iloc[col_name]).strip()
        if not name:
            # fallback: zkusit sloupce 3 a 9 (podle zjištěné struktury)
            for c in (3, 9, 2):
                if c < len(row) and pd.notna(row.iloc[c]) and str(row.iloc[c]).strip():
                    name = str(row.iloc[c]).strip()
                    break
        if not name:
            continue

        lower_row_text = " ".join(str(v).lower() for v in row.values if pd.notna(v))
        # Přeskočit řádek "Náklady stavby celkem"
        if "náklady stavby celkem" in lower_row_text or "naklady stavby celkem" in lower_row_text:
            continue

        price = 0.0
        try:
            if col_price < len(row):
                price = clean_price(row.iloc[col_price])
        except Exception:
            price = 0.0

        if price <= 0:
            continue

        code = ""
        if col_code != -1 and col_code < len(row) and pd.notna(row.iloc[col_code]):
            code = str(row.iloc[col_code]).strip()

        parent_items.append({
            "number": code,
            "name": name,
            "price": price,
            "is_section_header": True,
        })

    return parent_items


def _parse_unistav_soupis(df: pd.DataFrame) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Speciální parser pro Unistav Soupis prací v listu typu
    „Bytový dům - Nájemní bydlení …“.
    Vytáhne hierarchii podle řádků typu D (sekce) a K (položky),
    aby struktura odpovídala Type 1/2: parent_items + child_budgets.
    """
    if df is None or len(df) < 50:
        return [], []

    parent_items: List[Dict[str, Any]] = []
    child_budgets: List[Dict[str, Any]] = []

    # Najít začátek bloku SOUPIS PRACÍ a hlavičku PČ / Typ / Kód / Popis / Cena celkem
    soupis_start = 0
    header_idx = -1
    typ_col = -1
    kod_col = -1
    popis_col = -1
    cena_col = -1
    mnozstvi_col = -1
    j_cena_col = -1

    for idx in range(len(df)):
        row = df.iloc[idx]
        row_text = " ".join(str(v).lower() for v in row.values if pd.notna(v))
        if "soupis prací" in row_text or "soupis praci" in row_text:
            soupis_start = idx
        if "pč" in row_text and "typ" in row_text and "kód" in row_text and header_idx < 0:
            header_idx = idx
            for c, val in enumerate(row.values):
                v = str(val).strip().lower() if pd.notna(val) else ""
                if v == "typ":
                    typ_col = c
                elif v in ("kód", "kod"):
                    kod_col = c
                elif v == "popis":
                    popis_col = c
                elif "cena celkem" in v and "czk" in v:
                    cena_col = c
                elif v == "množství" or v == "mnozstvi":
                    mnozstvi_col = c
                elif "j.cena" in v and "czk" in v:
                    j_cena_col = c

    if header_idx < 0:
        # fallback – použít pevné indexy podle známé struktury
        header_idx = soupis_start + 12  # cca řádek s hlavičkou tabulky
    if typ_col < 0:
        typ_col = 3
    if kod_col < 0:
        kod_col = 4
    if popis_col < 0:
        popis_col = 5
    if cena_col < 0:
        cena_col = 9
    if mnozstvi_col < 0:
        mnozstvi_col = 7
    if j_cena_col < 0:
        j_cena_col = 8

    # Mapování: kód sekce (1, 2, 3, 711, N00, VRN, R, ...) -> seznam položek (K řádky)
    items_by_section: Dict[str, List[Dict[str, Any]]] = {}
    current_section_code: Optional[str] = None
    current_main_in_soupis: Optional[str] = None  # HSV / PSV skupiny – pouze pro mapování, ne jako vlastní budget

    print(f"_parse_unistav_soupis: header_idx={header_idx}, typ_col={typ_col}, kod_col={kod_col}, popis_col={popis_col}, cena_col={cena_col}")
    
    for idx in range(header_idx + 1, len(df)):
        row = df.iloc[idx]
        ncol = len(row)
        if typ_col >= ncol:
            continue

        typ = str(row.iloc[typ_col]).strip().upper() if pd.notna(row.iloc[typ_col]) else ""

        if typ == "D":
            kod = str(row.iloc[kod_col]).strip() if kod_col < ncol and pd.notna(row.iloc[kod_col]) else ""
            popis = str(row.iloc[popis_col]).strip() if popis_col < ncol and pd.notna(row.iloc[popis_col]) else ""
            try:
                cena = clean_price(row.iloc[cena_col]) if cena_col < ncol else 0.0
            except Exception:
                cena = 0.0

            if not kod:
                current_section_code = None
                continue

            # Stejná heuristika jako v _parse_type3_single_sheet – HSV/PSV jsou jen skupiny,
            # podsekce (1, 2, 3, 711...) tvoří skutečné podrozpočty, N00/VRN/R jsou samostatné sekce.
            kod_stripped = kod.strip()
            is_code_candidate = bool(
                kod_stripped
                and (kod_stripped.isdigit() or (len(kod_stripped) <= 6 and re.match(r"^[A-Z0-9\.]+$", kod_stripped)))
            )
            if not is_code_candidate:
                current_section_code = None
                continue

            is_numeric = bool(re.match(r"^\d+(\.\d+)?$", kod_stripped))
            is_standalone_section = kod_stripped.upper() in ("N00", "VRN", "R")

            if not is_numeric and not is_standalone_section:
                # HSV, PSV – skupinové hlavičky, jen si je pamatujeme jako "current_main_in_soupis"
                current_main_in_soupis = kod_stripped
                current_section_code = None
                if idx < header_idx + 100:  # Debug first 100 D rows
                    print(f"  Row {idx}: D row '{kod_stripped}' ({popis[:40]}) -> group header, current_section_code=None")
            else:
                # Skutečná sekce/podrozpočet
                current_section_code = kod_stripped
                if current_section_code not in items_by_section:
                    items_by_section[current_section_code] = []

                # Přidej do parent_items jako řádek v main budgetu
                parent_items.append(
                    {
                        "number": kod_stripped,
                        "name": popis or kod_stripped,
                        "price": cena,
                        "is_section_header": True,
                    }
                )
                if idx < header_idx + 100:  # Debug first 100 D rows
                    print(f"  Row {idx}: D row '{kod_stripped}' ({popis[:40]}) -> section, current_section_code='{current_section_code}'")
            continue

        if typ == "K":
            if not current_section_code:
                if idx < header_idx + 50:  # Debug first 50 K rows
                    print(f"  Row {idx}: K row but no current_section_code (typ='{typ}')")
                continue
            popis = str(row.iloc[popis_col]).strip() if popis_col < ncol and pd.notna(row.iloc[popis_col]) else ""
            if not popis:
                continue
            try:
                cena = clean_price(row.iloc[cena_col]) if cena_col < ncol else 0.0
            except Exception:
                cena = 0.0
            # Moravostav a podobné: sloupec "Cena celkem" může být 0, cena je v Množství * J.cena
            if cena <= 0 and mnozstvi_col < ncol and j_cena_col < ncol:
                try:
                    m = clean_price(row.iloc[mnozstvi_col])
                    j = clean_price(row.iloc[j_cena_col])
                    if m > 0 and j > 0:
                        cena = round(m * j, 2)
                except Exception:
                    pass
            if cena <= 0:
                continue
            kod_polozky = str(row.iloc[kod_col]).strip() if kod_col < ncol and pd.notna(row.iloc[kod_col]) else ""
            items_by_section.setdefault(current_section_code, []).append(
                {"number": kod_polozky, "name": popis, "price": cena}
            )
            if idx < header_idx + 50:  # Debug first 50 K rows
                print(f"  Row {idx}: Added K item to section '{current_section_code}': '{popis[:40]}' price={cena}")

    # Vytvořit child_budgets z items_by_section
    for sec_code, items in items_by_section.items():
        if not items:
            continue
        # Najít odpovídající parent položku kvůli názvu
        sec_name = sec_code
        for p in parent_items:
            if str(p.get("number", "")).strip() == sec_code:
                sec_name = p.get("name") or sec_code
                break
        child_budgets.append(
            {
                "name": sec_name,
                "number_code": sec_code,
                "items": items,
            }
        )

    # Doplň ceny u parent položek součtem položek v podbudgetu (když v Excelu jsou D řádky s cenou 0)
    section_totals = {sec_code: sum(it["price"] for it in items) for sec_code, items in items_by_section.items()}
    enriched_count = 0
    for p in parent_items:
        num = str(p.get("number", "")).strip()
        old_price = p.get("price", 0)
        if num in section_totals and (not old_price or float(old_price) <= 0):
            new_price = round(section_totals[num], 2)
            if new_price > 0:
                p["price"] = new_price
                enriched_count += 1
                if enriched_count <= 5:  # Log first 5
                    print(f"  Enriched parent item '{num}' ({p.get('name', '')[:30]}): {old_price} -> {new_price}")
    if enriched_count > 0:
        print(f"_parse_unistav_soupis: enriched {enriched_count} parent items with prices from child budgets")

    print(f"_parse_unistav_soupis: found {len(parent_items)} parent items, {len(child_budgets)} child budgets")
    print(f"_parse_unistav_soupis: sections found: {list(items_by_section.keys())}")
    for sec_code, items in items_by_section.items():
        print(f"  Section '{sec_code}': {len(items)} items")

    return parent_items, child_budgets


def _parse_type3_single_sheet(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Varianta 3: jeden list s bloky REKAPITULACE ČLENĚNÍ SOUPISU PRACÍ a SOUPIS PRACÍ.
    Vrací { "parent_budget": { "name", "items" }, "child_budgets": [ { "name", "number_code", "items" }, ... ] }.
    """
    # 1) Najít řádek "Kód dílu - Popis" a sloupec "Cena celkem [CZK]" v Rekapitulaci
    rekap_start = -1
    rekap_name_col = -1
    rekap_price_col = -1
    soupis_start = -1
    soupis_data_start = -1
    soupis_typ_col = -1
    soupis_kod_col = -1
    soupis_popis_col = -1
    soupis_cena_col = -1

    for idx in range(min(120, len(df))):
        row = df.iloc[idx]
        row_str = " ".join(str(x).lower() for x in row.values if pd.notna(x))
        if "kód dílu" in row_str and "popis" in row_str and rekap_start < 0:
            rekap_start = idx + 1  # data od dalšího řádku
            for c, val in enumerate(row.values):
                v = str(val).strip().lower()
                if "cena celkem" in v and "czk" in v:
                    rekap_price_col = c
                    break
            # Název je typicky v jednom z prvních sloupců s obsahem
            for c, val in enumerate(row.values):
                if pd.notna(val) and str(val).strip() and "cena" not in str(val).lower():
                    rekap_name_col = c
                    break
            if rekap_name_col < 0:
                rekap_name_col = 2
        if "soupis prací" in row_str or "soupis praci" in row_str:
            soupis_start = idx
        if soupis_start >= 0 and "pč" in row_str and "typ" in row_str and "kód" in row_str:
            for c, val in enumerate(row.values):
                v = str(val).strip().lower()
                if v == "typ":
                    soupis_typ_col = c
                elif v == "kód" or v == "kod":
                    soupis_kod_col = c
                elif v == "popis":
                    soupis_popis_col = c
                elif "cena celkem" in v and "czk" in v:
                    soupis_cena_col = c
            if soupis_typ_col >= 0:
                soupis_data_start = idx + 1
                break

    if rekap_start < 0:
        print("Type 3: Rekapitulace header not found")
        return None
    # Fallback: najít sloupec ceny z hlavičky v dalších řádcích nebo z prvního datového řádku (pravý sloupec s číslem)
    if rekap_price_col < 0:
        for r in range(max(0, rekap_start - 2), min(len(df), rekap_start + 3)):
            for c, val in enumerate(df.iloc[r].values):
                if pd.notna(val) and "cena" in str(val).lower() and "celkem" in str(val).lower():
                    rekap_price_col = c
                    break
            if rekap_price_col >= 0:
                break
    if rekap_price_col < 0 and rekap_start < len(df):
        row0 = df.iloc[rekap_start]
        for c in range(min(20, len(row0)) - 1, 4, -1):
            if clean_price(row0.iloc[c]) > 100:
                rekap_price_col = c
                break
    if rekap_price_col < 0:
        rekap_price_col = 8
    if rekap_name_col < 0:
        rekap_name_col = 2

    # 2) Parsovat Rekapitulaci
    # Main budget položky = sekce, které mají svůj podbudget: "1 - Zemní práce", "2 - Zakládání", "711 - ...", "N00", "VRN", "R".
    # HSV a PSV jsou jen skupinové hlavičky (ne řádky v tabulce). Každá main položka má jeden child budget s položkami (řádky K).
    parent_items = []
    child_budgets_meta = []  # { "number_code", "name", "price" } – každá má svůj podbudget s položkami
    total_price: Optional[float] = None
    current_main_code: Optional[str] = None
    i = rekap_start
    while i < len(df) and i < 500:
        row = df.iloc[i]
        name_cells = [str(row.iloc[c]).strip() for c in range(min(10, len(row))) if c != rekap_price_col and pd.notna(row.iloc[c]) and str(row.iloc[c]).strip()]
        name = name_cells[0] if name_cells else ""
        if len(name_cells) >= 2 and re.match(r"^\d+(\.\d+)?$", name_cells[0].strip()):
            name = f"{name_cells[0].strip()} - {name_cells[1].strip()}"
        if not name:
            i += 1
            continue
        if "soupis prací" in name.lower() or "soupis praci" in name.lower():
            break
        if "kód dílu" in name.lower() or "kod dilu" in name.lower():
            i += 1
            continue
        try:
            price_val = row.iloc[rekap_price_col]
            price = clean_price(price_val)
        except Exception:
            price = 0.0
        if price == 0.0 and ("náklady soupisu celkem" in name.lower() or "naklady soupisu celkem" in name.lower()):
            for c in range(5, min(20, len(row))):
                p = clean_price(row.iloc[c])
                if p > price:
                    price = p
        if "náklady soupisu celkem" in name.lower() or "naklady soupisu celkem" in name.lower():
            total_price = price
            i += 1
            continue
        code = ""
        display_name = name
        if re.match(r"^\s*\d+(\.\d+)?\s*[-–]", name) or re.match(r"^\s*\d+(\.\d+)?\s+", name):
            m = re.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*(.+)", name.strip())
            if m:
                code = m.group(1).strip()
                display_name = m.group(2).strip()
            else:
                m2 = re.match(r"\s*(\d+(?:\.\d+)?)\s+(.+)", name.strip())
                if m2:
                    code = m2.group(1)
                    display_name = m2.group(2).strip()
        elif " - " in name:
            parts = name.split(" - ", 1)
            if len(parts) == 2 and parts[0].strip():
                code = parts[0].strip()
                display_name = parts[1].strip()
        if not code and display_name:
            code = display_name.split()[0] if display_name.split() else ""
        is_numeric_code = bool(code and re.match(r"^\d+(\.\d+)?$", code.strip()))
        if is_numeric_code:
            # Sekce s číselným kódem (Zemní práce, Zakládání, 711 - ..., atd.) = main budget položka + má svůj podbudget
            parent_items.append({"number": str(code).strip(), "name": display_name.strip() or name, "price": price, "is_section_header": True})
            child_budgets_meta.append({"number_code": str(code).strip(), "name": display_name.strip() or name, "price": price})
        else:
            # HSV, PSV = jen hlavička skupiny, neřadíme do parent_items. N00, VRN, R = main položka bez podskupin v Rekapitulaci.
            current_main_code = code[:20] if code else name[:20]
            if code and code.upper() in ("N00", "VRN", "R"):
                parent_items.append({"number": code, "name": name, "price": price, "is_section_header": True})
                child_budgets_meta.append({"number_code": code, "name": display_name.strip() or name, "price": price})
        i += 1

    # 3) Parsovat SOUPIS PRACÍ: najít hlavičku (PČ, Typ, Kód) a od dalšího řádku data
    if soupis_data_start < 0:
        soupis_data_start = 0
    if soupis_typ_col < 0:
        for idx in range(len(df)):
            row_str = " ".join(str(x).lower() for x in df.iloc[idx].values if pd.notna(x))
            if "pč" in row_str and "typ" in row_str and "kód" in row_str:
                for c, val in enumerate(df.iloc[idx].values):
                    v = str(val).strip().lower()
                    if v == "typ":
                        soupis_typ_col = c
                    elif v == "kód" or v == "kod":
                        soupis_kod_col = c
                    elif v == "popis":
                        soupis_popis_col = c
                    elif "cena celkem" in v and "czk" in v:
                        soupis_cena_col = c
                soupis_data_start = idx + 1
                break
    else:
        for idx in range(soupis_start, min(len(df), soupis_start + 10)):
            row_str = " ".join(str(x).lower() for x in df.iloc[idx].values if pd.notna(x))
            if "pč" in row_str and "typ" in row_str:
                soupis_data_start = idx + 1
                break
    if soupis_typ_col < 0:
        soupis_data_start = soupis_start if soupis_start >= 0 else 0
    if soupis_kod_col < 0:
        soupis_kod_col = 4
    if soupis_popis_col < 0:
        soupis_popis_col = 5
    if soupis_cena_col < 0:
        soupis_cena_col = 9

    # Projít řádky Soupisu a přiřadit K-položky k poslednímu D (poddílu)
    current_section_code = None
    current_main_in_soupis: Optional[str] = None
    section_to_parent: Dict[str, str] = {}  # kód poddílu (1, 2, 711...) -> kód hlavního (HSV, PSV, ...)
    child_budgets = []
    items_by_code = {}  # number_code -> [ items ]

    for idx in range(soupis_data_start, len(df)):
        row = df.iloc[idx]
        ncol = len(row)
        if soupis_typ_col < 0 or soupis_typ_col >= ncol:
            continue
        typ = str(row.iloc[soupis_typ_col]).strip().upper()
        if typ == "D":
            kod = str(row.iloc[soupis_kod_col]).strip() if soupis_kod_col < ncol else ""
            popis = str(row.iloc[soupis_popis_col]).strip() if soupis_popis_col < ncol else ""
            try:
                cena = clean_price(row.iloc[soupis_cena_col]) if soupis_cena_col < ncol else 0.0
            except Exception:
                cena = 0.0
            if kod and (kod.isdigit() or (len(kod) <= 6 and re.match(r"^[A-Z0-9\.]+$", kod))):
                is_main = not re.match(r"^\d+(\.\d+)?$", kod)
                is_standalone_section = kod.upper() in ("N00", "VRN", "R")
                if is_main and not is_standalone_section:
                    current_main_in_soupis = kod
                    current_section_code = None
                else:
                    current_section_code = kod
                    if current_main_in_soupis and not is_standalone_section:
                        section_to_parent[kod] = current_main_in_soupis
                    if current_section_code not in items_by_code:
                        items_by_code[current_section_code] = []
                    # Nepřidávat D řádek (nadpis sekce) jako položku – main budget položka už je v tabulce, v podbudgetu jen K řádky
            else:
                current_section_code = None
            continue
        if typ == "K":
            popis = str(row.iloc[soupis_popis_col]).strip() if soupis_popis_col < ncol else ""
            try:
                cena = clean_price(row.iloc[soupis_cena_col]) if soupis_cena_col < ncol else 0.0
            except Exception:
                cena = 0.0
            kod = str(row.iloc[soupis_kod_col]).strip() if soupis_kod_col < ncol else ""
            if not popis:
                continue
            if current_section_code is not None:
                items_by_code.setdefault(current_section_code, []).append({"number": kod, "name": popis, "price": cena})

    def _items_for_code(code: str, by_code: Dict[str, List]) -> List:
        """Přiřazení položek podle kódu: přesná shoda nebo normalizovaná (1.0 -> 1)."""
        if not code:
            return []
        c = code.strip()
        if c in by_code:
            return by_code[c]
        c_norm = c.rstrip("0").rstrip(".") if "." in c else c
        if c_norm in by_code:
            return by_code[c_norm]
        for k, v in by_code.items():
            if k.strip() == c or (k.rstrip("0").rstrip(".") if "." in k else k) == c_norm:
                return v
        return []

    # 4) Sestavit child_budgets: každá main položka má jeden podbudget (přiřazení podle number_code = parent item number)
    for meta in child_budgets_meta:
        code = meta.get("number_code", "")
        name = meta.get("name", "") or code
        items = _items_for_code(code, items_by_code)
        if not items and meta.get("price", 0) > 0:
            items = [{"number": code, "name": name, "price": meta["price"]}]
        child_budgets.append({"name": name, "number_code": code, "items": items})

    # 4b) Přidat podbudgety ze Soupisu, které nejsou v Rekapitulaci (stejný number_code = jedna main položka)
    existing_codes = {cb["number_code"].strip() for cb in child_budgets}
    for kod, items in items_by_code.items():
        if not kod or not re.match(r"^\d+(\.\d+)?$", kod.strip()):
            continue
        k = kod.strip()
        if k in existing_codes:
            continue
        existing_codes.add(k)
        display_name = (items[0]["name"] if items else kod)
        child_budgets.append({"name": display_name, "number_code": k, "items": items})

    # Parent budget: jeden s položkami z Rekapitulace (hlavní díly)
    project_name = "Rozpočet"
    for idx in range(min(50, len(df))):
        row = df.iloc[idx]
        for c in range(len(row)):
            val = str(row.iloc[c]).strip()
            if "objekt:" in val.lower():
                if c + 1 < len(row) and pd.notna(row.iloc[c + 1]):
                    project_name = str(row.iloc[c + 1]).strip()[:80]
                    break
        if project_name != "Rozpočet":
            break

    return {
        "type": "type3",
        "parent_budget": {
            "name": project_name,
            "items": parent_items,
            "total_price": total_price,
        },
        "child_budgets": child_budgets,
    }


def process_type_1(xls: pd.ExcelFile, filename: str, provided_name: Optional[str] = None) -> Dict[str, Any]:
    # 1. Parse "Stavba" sheet for Project Name and Summary Items
    main_sheet_name = "Stavba"
    found_main = False
    for s in xls.sheet_names:
        if s.lower() == "stavba": 
            main_sheet_name = s
            found_main = True
            break
    
    # If explicit "Stavba" sheet not found, try to find one that looks like it (contains Rekapitulace)
    if not found_main:
        for s in xls.sheet_names:
            try:
                df_test = pd.read_excel(xls, sheet_name=s)
                # Check for specific markers
                s_lower = df_test.to_string().lower()
                if "rekapitulace dílčích částí" in s_lower:
                    main_sheet_name = s
                    break
            except: continue

    parent_items = []
    child_refs = {}
    canonical_child_codes = []  # pořadí: nejdelší první pro lepší match názvu listu

    project_name = provided_name if provided_name else filename.rsplit('.', 1)[0]

    if main_sheet_name in xls.sheet_names:
        df_stavba = pd.read_excel(xls, sheet_name=main_sheet_name)
        if not provided_name:
            project_name_extracted = extract_project_name(df_stavba)
            if project_name_extracted: project_name = project_name_extracted
        
        # We look for specific sections: "Rekapitulace dílčích částí" ONLY
        # Logic: Find the row defining the section, then find the header row below it.
        
        sections_to_parse = [
            {"marker": "rekapitulace dílčích částí", "type": "objects"}
        ]
        
        # Convert df to string for quick searches or iterate? Iterate is safer for row indices.
        # We iterate through rows to find markers.
        
        parsed_codes = set()
        
        for i in range(len(df_stavba)):
            row = df_stavba.iloc[i]
            row_text = " ".join([str(x).lower() for x in row.values if pd.notna(x)])
            
            active_section = None
            for sec in sections_to_parse:
                if sec["marker"] in row_text:
                    active_section = sec
                    break
            
            if active_section:
                header_row_idx = -1
                col_map = {}

                for j in range(i + 1, min(i + 6, len(df_stavba))):
                    r_head = df_stavba.iloc[j]
                    r_head_text = " ".join([str(x).lower() for x in r_head.values if pd.notna(x)])

                    if "číslo" in r_head_text and "název" in r_head_text:
                        header_row_idx = j
                        for col_idx, val in enumerate(r_head.values):
                            val_str = str(val).lower()
                            if "číslo" in val_str:
                                col_map['number'] = col_idx
                            elif "název" in val_str:
                                col_map['name'] = col_idx
                            elif "cena celkem" in val_str:
                                col_map['price'] = col_idx
                        break

                if header_row_idx != -1 and 'name' in col_map and 'price' in col_map:
                    for k in range(header_row_idx + 1, len(df_stavba)):
                        r_item = df_stavba.iloc[k]
                        r_item_text = " ".join([str(x).lower() for x in r_item.values if pd.notna(x)])

                        if not r_item_text.strip():
                            continue
                        if "rekapitulace" in r_item_text:
                            break
                        if "celkem za stavbu" in r_item_text:
                            break

                        name = str(r_item.iloc[col_map['name']]).strip()
                        if not is_valid_name(name) or name.lower() == "nan":
                            continue

                        code = ""
                        if 'number' in col_map and pd.notna(r_item.iloc[col_map['number']]):
                            code = str(r_item.iloc[col_map['number']]).strip()

                        item_id = f"{code}|{name}"
                        if item_id in parsed_codes:
                            continue

                        price = 0.0
                        if 'price' in col_map and pd.notna(r_item.iloc[col_map['price']]):
                            price = clean_price(r_item.iloc[col_map['price']])
                        else:
                            vals = [x for x in r_item.values if pd.notna(x)]
                            if vals:
                                try:
                                    price = clean_price(vals[-1])
                                except Exception:
                                    pass

                        if price > 0 or (code and len(name) > 2):
                            parent_items.append({
                                "number": code,
                                "name": name,
                                "price": price,
                                "is_section_header": True,
                            })
                            parsed_codes.add(item_id)

                            if active_section["type"] == "objects" and code and _is_subsheet_code(code):
                                child_refs[code] = name
                                child_refs[code.replace(" ", "")] = name
                                parts = code.split()
                                if len(parts) > 1:
                                    child_refs[parts[-1]] = name
                                if code not in canonical_child_codes:
                                    canonical_child_codes.append(code)
        
        # Rekapitulace dílů nebereme do parentu – jde o stejné peníze jen jinak rozepsané (dvojí součet).

        if not parent_items:
            print("Warning: No 'Rekapitulace' sections found in Stavba sheet.")

    # 2. Child budgety jen z listů, které odpovídají kódu z Rekapitulace dílčích částí
    canonical_child_codes.sort(key=lambda c: -len(c))
    child_budgets = []

    for sheet in xls.sheet_names:
        if sheet == main_sheet_name or "krycí" in sheet.lower():
            continue

        matched_code = None
        matched_parent_name = sheet

        for code in canonical_child_codes:
            if str(code) in sheet:
                matched_code = code
                matched_parent_name = child_refs[code]
                break

        budget_data = parse_child_sheet(xls, sheet, prefer_celkem_price=True)

        if budget_data and len(budget_data["items"]) > 0 and matched_code is not None:
            # Z podbudgetu vyřadit položku, která je stejná jako řádek v main budgetu (aby se nesčítala dvakrát)
            parent_item = next((p for p in parent_items if str(p.get("number", "")).strip() == str(matched_code).strip()), None)
            if parent_item:
                parent_name = (parent_item.get("name") or "").strip()
                budget_data["items"] = [
                    it for it in budget_data["items"]
                    if not (
                        str(it.get("number", "")).strip() == str(matched_code).strip()
                        and (parent_name and str(it.get("name", "")).strip() == parent_name)
                    )
                ]
            budget_data["name"] = matched_parent_name
            budget_data["number_code"] = matched_code
            if len(budget_data["items"]) > 0:
                child_budgets.append(budget_data)

    return {
        "type": "type1",
        "parent_budget": {
            "name": project_name,
            "items": parent_items
        },
        "child_budgets": child_budgets
    }

def parse_child_sheet(xls: pd.ExcelFile, sheet_name: str, prefer_celkem_price: bool = False) -> Optional[Dict[str, Any]]:
    df = pd.read_excel(xls, sheet_name=sheet_name)

    header_info = find_header_row(df, prefer_celkem_for_price=prefer_celkem_price)
    header_idx = header_info["idx"]
    col_map = header_info["map"]
    
    items = []
    
    if header_idx != -1 and 'name' in col_map:
        for idx in range(header_idx + 1, len(df)):
            row = df.iloc[idx]
            if pd.isna(row.iloc[col_map['name']]): continue
            
            # Check for Section/Díl headers that cause double counting
            # Common markers in first few columns
            row_start = " ".join([str(x).lower() for x in row.values[:3] if pd.notna(x)])
            if "díl:" in row_start or "oddíl:" in row_start:
                continue

            code = ""
            if 'number' in col_map and pd.notna(row.iloc[col_map['number']]):
                code = str(row.iloc[col_map['number']]).strip()

            # Jen řádky s vyplněným P.č. / Číslem položky – pokračovací řádky a vzorce nemají kód
            if not code or code.lower() in ["nan", "none", "vv"]:
                continue
            if "díl" in code.lower() or "dil" in code.lower():
                continue

            name = str(row.iloc[col_map['name']]).strip()
            if not is_valid_name(name):
                continue
            if _looks_like_formula_or_continuation(name):
                continue
            if name.lower().startswith("celkem") or name.lower().startswith("mezisoučet"):
                continue

            price = 0.0
            if 'price' in col_map and pd.notna(row.iloc[col_map['price']]):
                 price = clean_price(row.iloc[col_map['price']])
            else:
                 # Last resort: last numeric column
                 vals = [x for x in row.values if pd.notna(x)]
                 if len(vals) >= 2:
                     try: price = clean_price(vals[-1])
                     except: pass

            if price == 0 and (not code or code.lower()=="nan" or len(code) < 1): continue
            
            items.append({
                "number": code,
                "name": name,
                "price": price
            })
            
    return {
        "name": sheet_name,
        "items": items
    }

def _parse_rekapitulace_single_sheet(df: pd.DataFrame) -> tuple:
    """
    Parse single Rekapitulace sheet: Pozice;Popis;Cena.
    Top-level sections (Pozice = 1, 2, 3, ...) → parent items + one child budget each.
    Rows with Pozice = 1.1, 1.2 or empty → items under current section.
    Returns (parent_items, child_budgets).
    """
    parent_items = []
    child_budgets = []  # list of {"name": str, "items": [...]}
    current_section = None  # {"number": str, "name": str, "items": []}

    # Find header: Pozice / Popis / Cena (v řádcích nebo v df.columns když byl header=0)
    header_idx = -1
    col_posice = -1
    col_popis = -1
    col_cena = -1
    data_start_row = 0
    
    # 1) Zkusit sloupce (když byl Excel načten s header=0)
    # Excel často má první řádek jako hlavičku, ale když čteme s header=None, musíme hledat v řádcích
    # Ale zkusme nejdřív zkontrolovat, jestli první řádek není hlavička
    if len(df) > 0:
        first_row_str = " ".join([str(x).lower() for x in df.iloc[0].values if pd.notna(x)])
        if "pozice" in first_row_str or "popis" in first_row_str or "cena" in first_row_str:
            # První řádek vypadá jako hlavička - zkusme ho použít
            for col_i, val in enumerate(df.iloc[0].values):
                v = str(val).strip().lower()
                if v in ("pozice", "pořadí", "poz.") or "pozice" in v:
                    col_posice = col_i
                elif v in ("popis", "název", "nazev", "položka", "polozka") or "popis" in v:
                    col_popis = col_i
                elif (("cena" in v or v == "celkem") and "dph" not in v) or "cena" in v:
                    col_cena = col_i
            if col_popis != -1 and col_cena != -1:
                header_idx = 0
                if col_posice == -1:
                    col_posice = 0
                data_start_row = 1  # Data začínají od řádku 1
            else:
                # Reset, pokud jsme nenašli hlavičku v prvním řádku
                col_posice = -1
                col_popis = -1
                col_cena = -1
    # 2) Jinak hledat v řádcích (typicky při header=None)
    if header_idx == -1:
        print(f"_parse_rekapitulace: Searching for header in rows 0-{min(20, len(df))}")
        for idx in range(min(20, len(df))):
            row = df.iloc[idx]
            cp, cpop, cc = -1, -1, -1
            row_str = " ".join([str(x).lower() for x in row.values[:5] if pd.notna(x)])
            for col_i, val in enumerate(row.values):
                v = str(val).strip().lower()
                if "pozice" in v or v == "pořadí" or v == "poz.":
                    cp = col_i
                elif "popis" in v or "název" in v or v == "nazev" or "položka" in v or v == "polozka":
                    cpop = col_i
                elif ("cena" in v or v == "celkem") and "dph" not in v:
                    cc = col_i
            if cpop != -1 and cc != -1:
                header_idx = idx
                col_posice = cp if cp != -1 else 0
                col_popis = cpop
                col_cena = cc
                data_start_row = idx + 1
                print(f"_parse_rekapitulace: Found header at row {idx}: col_posice={col_posice}, col_popis={col_popis}, col_cena={col_cena}, data_start_row={data_start_row}")
                break
            elif idx < 5:
                print(f"_parse_rekapitulace: Row {idx} doesn't look like header: {row_str[:100]}")

    # 3) Fallback: předpokládat sloupce 0=Pozice, 1=Popis, 2=Cena (typická struktura)
    if header_idx == -1 or col_popis == -1 or col_cena == -1:
        if len(df) >= 2:
            col_posice, col_popis, col_cena = 0, 1, 2
            for idx in range(min(30, len(df))):
                row = df.iloc[idx]
                if len(row.values) < 3:
                    continue
                v0 = row.values[0]
                v1 = row.values[1]
                v2 = row.values[2]
                # Řádek s číslem 1 (nebo 1.0) v prvním sloupci = začátek dat
                v0_ok = (
                    v0 == 1
                    or (isinstance(v0, float) and v0 == int(v0) and 0 < v0 < 10000)
                    or (str(v0).strip() in ("1", "1.0"))
                )
                if pd.notna(v1) and str(v1).strip() and v0_ok:
                    price = clean_price(v2)
                    if price > 0 or len(str(v1).strip()) > 2:
                        header_idx = max(0, idx - 1)
                        data_start_row = idx
                        break
            else:
                # Žádný řádek s "1" v prvním sloupci – předpokládat hlavičku v řádku 0, data od 1
                header_idx = 0
                data_start_row = 1
        else:
            return parent_items, child_budgets
    if col_popis == -1:
        col_popis = 1
    if col_cena == -1:
        col_cena = 2
    if col_posice == -1:
        col_posice = 0

    def _is_top_level_section(posice_val) -> bool:
        if pd.isna(posice_val):
            return False
        # Excel/pandas často načte čísla jako float (1.0, 2.0) – považovat za celé číslo
        if isinstance(posice_val, (int, float)):
            if posice_val == int(posice_val) and 0 < posice_val < 10000:
                return True
            return False
        s = str(posice_val).strip()
        if not s or s.lower() in ("nan", "none"):
            return False
        # Jedno celé číslo: "1", "2", "3" nebo "1.0", "2.0" z Excelu
        if re.match(r"^\d+$", s):
            return True
        if re.match(r"^\d+\.0+$", s):
            return True
        return False
    
    def _is_subsection_header(posice_val) -> bool:
        """Rozpozná pozice jako 1.1, 1.2, 1.3 jako hlavičky podsekce (child budget)"""
        if pd.isna(posice_val):
            return False
        if isinstance(posice_val, float):
            # Float jako 1.1, 1.2 - pokud není celé číslo, je to podsekce
            if posice_val != int(posice_val) and 0 < posice_val < 10000:
                return True
            return False
        s = str(posice_val).strip()
        if not s or s.lower() in ("nan", "none"):
            return False
        # Desetinné číslo jako "1.1", "1.2", "2.5" (ale ne "1.0" nebo "2.0")
        if re.match(r"^\d+\.\d+$", s):
            # Ale ne pokud končí na .0 (to je top-level)
            if not re.match(r"^\d+\.0+$", s):
                return True
        return False

    def _is_sub_item(posice_val) -> bool:
        if pd.isna(posice_val):
            return True  # empty = continuation under current section
        s = str(posice_val).strip()
        if not s or s.lower() in ("nan", "none"):
            return True
        # decimal (1.1, 1.2) or anything else = item under section
        return True

    print(f"_parse_rekapitulace: header_idx={header_idx}, data_start_row={data_start_row}, col_posice={col_posice}, col_popis={col_popis}, col_cena={col_cena}, total_rows={len(df)}")
    
    rows_processed = 0
    rows_skipped_empty = 0
    rows_added = 0
    
    for idx in range(data_start_row, len(df)):
        row = df.iloc[idx]
        posice_val = row.iloc[col_posice] if col_posice < len(row) else None
        popis_val = row.iloc[col_popis] if col_popis < len(row) else None
        cena_val = row.iloc[col_cena] if col_cena < len(row) else None

        name = str(popis_val).strip() if pd.notna(popis_val) else ""
        if not name or name.lower() in ("nan", "none"):
            # Prázdný řádek = jen oddělovač uvnitř sekce, neukončovat current_section
            rows_skipped_empty += 1
            if idx < data_start_row + 30:
                print(f"  Row {idx}: SKIPPED (empty name)")
            continue
        
        rows_processed += 1

        price = clean_price(cena_val)
        posice_str = str(posice_val).strip() if pd.notna(posice_val) else ""
        
        # Debug: první pár řádků a všechny top-level sections
        if idx < data_start_row + 15 or _is_top_level_section(posice_val):
            print(f"  Row {idx}: posice={posice_val} ({type(posice_val).__name__}, str='{posice_str}'), name='{name[:50]}', price={price}, current_section={current_section['name'] if current_section else None}")

        if _is_top_level_section(posice_val):
            # Flush previous section (child budget)
            if current_section and current_section.get("items"):
                print(f"  Flushing section '{current_section['name']}' with {len(current_section['items'])} items")
                child_budgets.append({
                    "name": current_section["name"],
                    "items": current_section["items"],
                    "number_code": current_section.get("number", "")  # Přidat number_code pro drill-down
                })
            # Normalizovat číslo pro zobrazení (1.0 -> 1)
            num_display = posice_str
            if isinstance(posice_val, float) and posice_val == int(posice_val):
                num_display = str(int(posice_val))
            elif posice_str and re.match(r"^\d+\.0+$", str(posice_str)):
                num_display = str(int(float(posice_str)))
            # New top-level section → parent item + new child budget
            print(f"  Found top-level section: {num_display} - {name}")
            parent_items.append({
                "number": num_display,
                "name": name,
                "price": price,
                "is_section_header": True,
            })
            current_section = {"number": num_display, "name": name, "items": []}
        elif _is_subsection_header(posice_val):
            # Pozice jako 1.1, 1.2, 1.3 = nový child budget pod aktuální parent sekcí
            # Flush previous child budget (pokud existuje a má items)
            if current_section and current_section.get("items"):
                print(f"  Flushing subsection '{current_section['name']}' with {len(current_section['items'])} items")
                child_budgets.append({
                    "name": current_section["name"],
                    "items": current_section["items"],
                    "number_code": current_section.get("number", "")  # Přidat number_code pro drill-down
                })
            # Také přidat subsection header jako parent item (aby se zobrazoval v parent budgetu)
            print(f"  Found subsection header: {posice_str} - {name}")
            parent_items.append({
                "number": posice_str,
                "name": name,
                "price": price,
                "is_section_header": False,  # Subsection header není top-level section
            })
            # Vytvořit nový child budget s tímto názvem
            current_section = {"number": posice_str, "name": name, "items": []}
            # Přidat tento item jako první do nového child budgetu (pokud má cenu)
            if price > 0:
                current_section["items"].append({
                    "number": posice_str,
                    "name": name,
                    "price": price
                })
                rows_added += 1
                print(f"    ✓ Added subsection header item to '{name}': price={price}")
        else:
            # Item under current section (1.1, 1.2, or empty)
            if current_section is not None:
                # Přidat item pokud má validní název a (cenu > 0 nebo pozici)
                should_add = False
                looks_like_formula = _looks_like_formula_or_continuation(name)
                
                if not looks_like_formula:
                    # Má pozici (1.1, 1.2) nebo má cenu > 0
                    if posice_str or price > 0:
                        should_add = True
                else:
                    # I když vypadá jako pokračovací řádek, pokud má pozici (1.1, 1.2), přidat ho
                    if posice_str and re.match(r"^\d+\.\d+", posice_str):
                        should_add = True
                
                # Debug pro všechny řádky s cenou > 0
                if idx < data_start_row + 100 and price > 0:
                    print(f"    Processing row {idx}: should_add={should_add}, looks_like_formula={looks_like_formula}, posice_str='{posice_str}', price={price}, name='{name[:50]}'")
                
                if should_add:
                    item_count_before = len(current_section["items"])
                    current_section["items"].append({
                        "number": posice_str if posice_str else "",  # Prázdná pozice pro pokračovací řádky
                        "name": name,
                        "price": price
                    })
                    item_count_after = len(current_section["items"])
                    rows_added += 1
                    # Log first 20 items and every 10th item after that, plus items with positions like 1.2, 1.3, etc.
                    if item_count_after <= 20 or item_count_after % 10 == 0 or (posice_str and re.match(r"^\d+\.\d+", posice_str)):
                        print(f"    ✓ Added item #{item_count_after} to section '{current_section['name']}': posice='{posice_str}' name='{name[:40]}' price={price}")
                    # Debug: pokud se item nepřidal (což by nemělo nastat)
                    if item_count_after == item_count_before:
                        print(f"    ✗ ERROR: Item was not added! Row {idx}, should_add={should_add}")
                else:
                    if idx < data_start_row + 100 and price > 0:  # Debug why items with price are skipped
                        print(f"    SKIPPED item in section '{current_section['name']}': posice='{posice_str}' name='{name[:40]}' price={price}, looks_like_formula={looks_like_formula}")
            else:
                # Debug pro řádky před první sekcí
                if idx < data_start_row + 20:
                    print(f"    Row {idx} before any section: posice='{posice_str}' name='{name[:40]}' price={price}")

    # Flush final section
    if current_section and current_section.get("items"):
        print(f"  Flushing final section '{current_section['name']}' with {len(current_section['items'])} items")
        child_budgets.append({
            "name": current_section["name"],
            "items": current_section["items"],
            "number_code": current_section.get("number", "")  # Přidat number_code pro drill-down
        })
    elif current_section:
        print(f"  WARNING: Final section '{current_section['name']}' has no items, skipping")

    # Z každého podbudgetu vyřadit položku, která je stejná jako hlavička sekce (main budget řádek)
    def _norm_posice(s):
        if not s:
            return ""
        s = str(s).strip()
        if re.match(r"^\d+\.0+$", s):
            return str(int(float(s)))
        return s

    for cb in child_budgets:
        section_code = _norm_posice(cb.get("number_code", ""))
        section_name = (cb.get("name") or "").strip()
        if not section_name:
            continue
        orig_len = len(cb["items"])
        cb["items"] = [
            it for it in cb["items"]
            if not (
                str(it.get("name", "")).strip() == section_name
                and _norm_posice(it.get("number", "")) == section_code
            )
        ]
        if len(cb["items"]) < orig_len:
            print(f"  Filtered {orig_len - len(cb['items'])} duplicate main item(s) from child '{cb['name']}'")
    
    print(f"_parse_rekapitulace SUMMARY:")
    print(f"  - Rows processed: {rows_processed}")
    print(f"  - Rows skipped (empty): {rows_skipped_empty}")
    print(f"  - Rows added to sections: {rows_added}")
    print(f"  - Parent items: {len(parent_items)}")
    print(f"  - Child budgets: {len(child_budgets)}")
    total_child_items = sum(len(cb["items"]) for cb in child_budgets)
    print(f"  - Total child items: {total_child_items}")
    for i, cb in enumerate(child_budgets):
        print(f"    Child budget {i+1} '{cb['name']}': {len(cb['items'])} items")
        # Debug: první 3 items každého child budgetu
        if len(cb["items"]) > 0:
            for j, item in enumerate(cb["items"][:3]):
                print(f"      Item {j+1}: posice='{item.get('number', '')}' name='{item.get('name', '')[:40]}' price={item.get('price', 0)}")

    return parent_items, child_budgets


def process_type_2(xls: pd.ExcelFile, filename: str, provided_name: Optional[str] = None) -> Dict[str, Any]:
    # Type 2: Either (a) single Rekapitulace sheet with sub-budgets inside, or (b) multiple sheets
    project_name = provided_name if provided_name else filename.rsplit('.', 1)[0]

    # Project name from Krycí list if available
    kryci_sheet = None
    for s in xls.sheet_names:
        s_lower = s.lower()
        if "krycí" in s_lower or "kryci" in s_lower:  # Podporovat i bez diakritiky
            kryci_sheet = s
            break
    if kryci_sheet and not provided_name:
        try:
            df_kl = pd.read_excel(xls, sheet_name=kryci_sheet)
            extracted = extract_project_name(df_kl)
            if extracted:
                project_name = extracted
        except Exception:
            pass

    # Prefer: single Rekapitulace sheet containing Pozice/Popis/Cena and hierarchical sections
    # 1) Zkusit list s názvem obsahujícím "rekapitulace"
    candidate_sheets = []
    for s in xls.sheet_names:
        s_lower = s.lower()
        if "krycí" in s_lower or "kryci" in s_lower:
            continue
        if "rekapitulace" in s_lower or "rekapitulace" in s_lower:
            candidate_sheets.insert(0, s)  # preferovat na začátek
        else:
            candidate_sheets.append(s)
    
    print(f"Type 2: Processing sheets in order: {candidate_sheets}")
    for sheet_name in candidate_sheets:
        try:
            df_rec = pd.read_excel(xls, sheet_name=sheet_name, header=None)
            print(f"Type 2: Reading sheet '{sheet_name}' -> {len(df_rec)} rows, {len(df_rec.columns)} columns")
            parent_items, child_budgets = _parse_rekapitulace_single_sheet(df_rec)
            print(f"Type 2: Parsed sheet '{sheet_name}' -> {len(parent_items)} parent items, {len(child_budgets)} child budgets")
            if parent_items:
                print(f"Type 2: Successfully parsed '{sheet_name}' as Rekapitulace with {len(parent_items)} parent items")
                return {
                    "type": "type2",
                    "parent_budget": {
                        "name": project_name,
                        "items": parent_items
                    },
                    "child_budgets": child_budgets
                }
        except Exception as e:
            print(f"Type 2: sheet '{sheet_name}' failed: {e}")
            import traceback
            traceback.print_exc()

    # Fallback: treat every sheet (except Krycí list) as a child budget
    child_budgets = []
    for sheet in xls.sheet_names:
        if "krycí" in sheet.lower():
            continue
        budget_data = parse_child_sheet(xls, sheet)
        if budget_data and len(budget_data["items"]) > 0:
            child_budgets.append(budget_data)

    return {
        "type": "type2",
        "parent_budget": {
            "name": project_name,
            "items": []
        },
        "child_budgets": child_budgets
    }
