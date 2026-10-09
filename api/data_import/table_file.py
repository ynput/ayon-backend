"""Write table exports as CSV or XLSX.

XLSX is written as a minimal SpreadsheetML package with the standard library,
so exports don't need a spreadsheet dependency.
"""

import csv
import io
import math
import re
import zipfile
from xml.sax.saxutils import escape, quoteattr

Cell = str | int | float | bool | None

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# characters XML 1.0 does not allow, Excel refuses files that contain them
_ILLEGAL_XML_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_ILLEGAL_SHEET_NAME_CHARS = re.compile(r"[\[\]:*?/\\]")
_MAX_CELL_TEXT = 32767  # Excel's limit per cell


def write_csv(header: list[str], rows: list[list[str]], delimiter: str) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(header)
    writer.writerows(rows)
    # BOM, without it Excel reads the file as ANSI
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def write_xlsx(header: list[str], rows: list[list[Cell]], sheet_name: str) -> bytes:
    sheet_name = _ILLEGAL_SHEET_NAME_CHARS.sub("", sheet_name)[:31] or "Export"
    last_column = _column_letter(max(len(header), 1) - 1)
    last_row = len(rows) + 1

    widths = [len(label) for label in header]
    for row in rows[:1000]:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(_text(value)))
    cols = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{min(max(w, 6), 60) + 2}" '
        'customWidth="1"/>'
        for i, w in enumerate(widths)
    )

    sheet_rows = [_row_xml(1, header, style=1)]
    for index, row in enumerate(rows, start=2):
        sheet_rows.append(_row_xml(index, row))

    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews>"
        f"<cols>{cols}</cols>"
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        f'<autoFilter ref="A1:{last_column}{last_row}"/>'
        "</worksheet>"
    )

    quoted_sheet = "'" + sheet_name.replace("'", "''") + "'"
    filter_range = f"{quoted_sheet}!$A$1:${last_column}${last_row}"
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets><sheet name={quoteattr(sheet_name)} "
        'sheetId="1" r:id="rId1"/></sheets>'
        '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" '
        f'hidden="1">{escape(filter_range)}</definedName></definedNames>'
        "</workbook>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _CONTENT_TYPES)
        package.writestr("_rels/.rels", _ROOT_RELS)
        package.writestr("xl/workbook.xml", workbook)
        package.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        package.writestr("xl/styles.xml", _STYLES)
        package.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def _column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _text(value: Cell) -> str:
    if value is None:
        return ""
    return str(value)


def _row_xml(row_number: int, values: list[Cell] | list[str], style: int = 0) -> str:
    cells = []
    for index, value in enumerate(values):
        ref = f"{_column_letter(index)}{row_number}"
        style_attr = f' s="{style}"' if style else ""
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            cells.append(f'<c r="{ref}"{style_attr} t="b"><v>{int(value)}</v></c>')
        elif isinstance(value, int | float) and math.isfinite(value):
            cells.append(f'<c r="{ref}"{style_attr}><v>{value!r}</v></c>')
        else:
            text = escape(_ILLEGAL_XML_CHARS.sub("", str(value))[:_MAX_CELL_TEXT])
            cells.append(
                f'<c r="{ref}"{style_attr} t="inlineStr">'
                f'<is><t xml:space="preserve">{text}</t></is></c>'
            )
    return f'<row r="{row_number}">{"".join(cells)}</row>'


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    "</Types>"
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
    '2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)

_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
    '2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/'
    '2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)

# style 0 is the default, style 1 the bold header
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border>'
    "</borders>"
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
    "</cellStyleXfs>"
    '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    "</cellXfs>"
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>'
    "</cellStyles>"
    "</styleSheet>"
)
