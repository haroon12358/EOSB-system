"""Minimal Excel (.xlsx) writer.

An xlsx file is a zip of XML parts.  Writing it directly keeps the
application free of third-party packages, which is what makes the folder
portable.  Strings are written inline, so no shared-string table is needed.
"""
import datetime
import zipfile

# Style indices used by the report builders.
S_DEFAULT, S_TITLE, S_SUBTITLE, S_HEADER, S_TEXT = 0, 1, 2, 3, 4
S_NUM1, S_INT, S_DATE, S_TOTAL_NUM, S_TOTAL_TEXT, S_MONEY, S_TOTAL_INT = 5, 6, 7, 8, 9, 10, 11

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
%s
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="3">
<numFmt numFmtId="164" formatCode="#,##0.0"/>
<numFmt numFmtId="165" formatCode="#,##0"/>
<numFmt numFmtId="166" formatCode="#,##0.00"/>
</numFmts>
<fonts count="6">
<font><sz val="10"/><name val="Calibri"/></font>
<font><b/><sz val="15"/><color rgb="FF1F3864"/><name val="Calibri"/></font>
<font><sz val="10"/><color rgb="FF595959"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF1F3864"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F3864"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="3">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left/><right/><top/><bottom style="thin"><color rgb="FFBFBFBF"/></bottom><diagonal/></border>
<border><left/><right/><top style="thin"><color rgb="FF1F3864"/></top><bottom style="double"><color rgb="FF1F3864"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="12">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="3" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
<xf numFmtId="14" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
<xf numFmtId="164" fontId="4" fillId="0" borderId="2" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
<xf numFmtId="0" fontId="4" fillId="0" borderId="2" xfId="0" applyFont="1" applyBorder="1"/>
<xf numFmtId="166" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
<xf numFmtId="165" fontId="4" fillId="0" borderId="2" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

_EPOCH = datetime.date(1899, 12, 30)


def _escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _col_letter(index):
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


class Sheet(object):
    def __init__(self, name, freeze_row=None, widths=None):
        self.name = name[:31]
        self.rows = []
        self.freeze_row = freeze_row
        self.widths = widths or []
        self.merges = []

    def add(self, values, style=S_DEFAULT, styles=None):
        """Append a row.  values may contain None, str, int, float or date."""
        self.rows.append((values, style, styles))
        return self

    def blank(self, count=1):
        for _ in range(count):
            self.rows.append(([], S_DEFAULT, None))
        return self

    def merge(self, row_index, first_col, last_col):
        self.merges.append((row_index, first_col, last_col))

    def _xml(self):
        parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                 '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
        if self.widths:
            parts.append("<cols>")
            for i, width in enumerate(self.widths):
                parts.append('<col min="%d" max="%d" width="%s" customWidth="1"/>'
                             % (i + 1, i + 1, width))
            parts.append("</cols>")
        parts.append("<sheetData>")
        for r, (values, row_style, cell_styles) in enumerate(self.rows, start=1):
            if not values:
                parts.append('<row r="%d"/>' % r)
                continue
            parts.append('<row r="%d">' % r)
            for c, value in enumerate(values):
                style = row_style
                if cell_styles and c < len(cell_styles) and cell_styles[c] is not None:
                    style = cell_styles[c]
                ref = "%s%d" % (_col_letter(c), r)
                if value is None or value == "":
                    parts.append('<c r="%s" s="%d"/>' % (ref, style))
                elif isinstance(value, bool):
                    parts.append('<c r="%s" s="%d" t="inlineStr"><is><t>%s</t></is></c>'
                                 % (ref, style, "Yes" if value else "No"))
                elif isinstance(value, (datetime.date, datetime.datetime)):
                    day = value.date() if isinstance(value, datetime.datetime) else value
                    parts.append('<c r="%s" s="%d"><v>%d</v></c>'
                                 % (ref, style, (day - _EPOCH).days))
                elif isinstance(value, (int, float)):
                    parts.append('<c r="%s" s="%d"><v>%s</v></c>' % (ref, style, repr(value)))
                else:
                    parts.append('<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                                 % (ref, style, _escape(value)))
            parts.append("</row>")
        parts.append("</sheetData>")
        if self.merges:
            parts.append('<mergeCells count="%d">' % len(self.merges))
            for row_index, first, last in self.merges:
                parts.append('<mergeCell ref="%s%d:%s%d"/>'
                             % (_col_letter(first), row_index, _col_letter(last), row_index))
            parts.append("</mergeCells>")
        parts.append("</worksheet>")
        # sheetView must precede sheetData
        if self.freeze_row:
            view = ('<sheetViews><sheetView workbookViewId="0" showGridLines="0">'
                    '<pane ySplit="%d" topLeftCell="A%d" activePane="bottomLeft" state="frozen"/>'
                    '</sheetView></sheetViews>' % (self.freeze_row, self.freeze_row + 1))
        else:
            view = '<sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews>'
        parts.insert(2, view)
        return "".join(parts)


class Workbook(object):
    def __init__(self):
        self.sheets = []

    def sheet(self, name, freeze_row=None, widths=None):
        sheet = Sheet(name, freeze_row, widths)
        self.sheets.append(sheet)
        return sheet

    def save(self, path):
        overrides = "\n".join(
            '<Override PartName="/xl/worksheets/sheet%d.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            % (i + 1) for i in range(len(self.sheets)))
        sheet_tags = "".join(
            '<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (_escape(s.name), i + 1, i + 1)
            for i, s in enumerate(self.sheets))
        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets>%s</sheets></workbook>' % sheet_tags)
        rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
        for i in range(len(self.sheets)):
            rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
                        'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>'
                        % (i + 1, i + 1))
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
                    'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                    % (len(self.sheets) + 1))
        rels.append("</Relationships>")

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _CONTENT_TYPES % overrides)
            zf.writestr("_rels/.rels", _ROOT_RELS)
            zf.writestr("xl/workbook.xml", workbook_xml)
            zf.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
            zf.writestr("xl/styles.xml", _STYLES)
            for i, sheet in enumerate(self.sheets):
                zf.writestr("xl/worksheets/sheet%d.xml" % (i + 1), sheet._xml())
        return path
