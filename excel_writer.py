# -*- coding: utf-8 -*-
"""写 Excel"""
import logging
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
HEADER_FONT = Font(bold=True)
EXCEL_MAX_COLS = 16000


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace(",", "").replace("，", "").replace(" ", "")
    if s in ("", "-", "—", "–", "无", "null", "None", "N/A", "nan"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    try:
        n = float(s)
    except ValueError:
        return str(v)
    return -n if neg else n


def _style_header(ws, ncols: int):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def write_excel(statements, out_path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    ws = wb.active
    ws.title = "明细"
    ws.append(["项目", "公司", "年份", "报表类型", "单位", "科目", "列", "金额"])
    for st in statements:
        for r in st.get("rows", []):
            ws.append([
                st.get("project"), st.get("company"), st.get("year"),
                st.get("statement_type"), st.get("unit"),
                r.get("item"), r.get("column"), _num(r.get("value")),
            ])

    widths = [20, 30, 10, 16, 8, 32, 14, 16]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    _style_header(ws, len(widths))

    col_keys, item_map = [], {}
    for st in statements:
        base = f"{st.get('company') or '未知'}|{st.get('year') or ''}|{st.get('statement_type') or ''}"
        for r in st.get("rows", []):
            ck = f"{base}|{r.get('column') or ''}"
            if ck not in col_keys:
                col_keys.append(ck)
            item = str(r.get("item") or "").strip() or "(空科目)"
            item_map.setdefault(item, {})[ck] = _num(r.get("value"))

    if col_keys and len(col_keys) + 1 <= EXCEL_MAX_COLS:
        ws2 = wb.create_sheet("宽表")
        ws2.append(["科目"] + col_keys)
        for item, d in item_map.items():
            ws2.append([item] + [d.get(ck) for ck in col_keys])
        ws2.column_dimensions["A"].width = 34
        for i in range(2, len(col_keys) + 2):
            ws2.column_dimensions[get_column_letter(i)].width = 18
        _style_header(ws2, len(col_keys) + 1)
    else:
        logger.warning("宽表列数过多，已跳过宽表生成")

    wb.save(out_path)
    return out_path