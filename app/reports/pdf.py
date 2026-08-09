"""Minimal PDF writer for tabular reports.

Generates a valid PDF 1.4 document using the base-14 Helvetica fonts, so no
font files and no third-party packages are required.  Tables paginate
automatically and repeat their headers on every page.
"""
import datetime

# Helvetica advance widths (units of 1/1000 em) for the printable ASCII range.
_W = {
    32: 278, 33: 278, 34: 355, 35: 556, 36: 556, 37: 889, 38: 667, 39: 191,
    40: 333, 41: 333, 42: 389, 43: 584, 44: 278, 45: 333, 46: 278, 47: 278,
    58: 278, 59: 278, 60: 584, 61: 584, 62: 584, 63: 556, 64: 1015,
    65: 667, 66: 667, 67: 722, 68: 722, 69: 667, 70: 611, 71: 778, 72: 722,
    73: 278, 74: 500, 75: 667, 76: 556, 77: 833, 78: 722, 79: 778, 80: 667,
    81: 778, 82: 722, 83: 667, 84: 611, 85: 722, 86: 667, 87: 944, 88: 667,
    89: 667, 90: 611, 91: 278, 92: 278, 93: 278, 94: 469, 95: 556, 96: 333,
    97: 556, 98: 556, 99: 500, 100: 556, 101: 556, 102: 278, 103: 556,
    104: 556, 105: 222, 106: 222, 107: 500, 108: 222, 109: 833, 110: 556,
    111: 556, 112: 556, 113: 556, 114: 333, 115: 500, 116: 278, 117: 556,
    118: 500, 119: 722, 120: 500, 121: 500, 122: 500, 123: 334, 124: 260,
    125: 334, 126: 584,
}
for _d in range(48, 58):
    _W[_d] = 556

_TRANSLATE = {0x2014: "-", 0x2013: "-", 0x2019: "'", 0x2018: "'",
              0x201c: '"', 0x201d: '"', 0x2026: "...", 0xa0: " "}


def _latin(text):
    """Reduce text to a byte range the base-14 fonts can render."""
    text = "".join(_TRANSLATE.get(ord(ch), ch) for ch in str(text))
    return text.encode("latin-1", "replace").decode("latin-1")


def text_width(text, size, bold=False):
    total = sum(_W.get(ord(ch), 556) for ch in text)
    if bold:
        total *= 1.06
    return total * size / 1000.0


def fit(text, width, size, bold=False):
    text = _latin(text)
    if text_width(text, size, bold) <= width:
        return text
    ellipsis = ".."
    while text and text_width(text + ellipsis, size, bold) > width:
        text = text[:-1]
    return text + ellipsis


def _escape(text):
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


class Table(object):
    def __init__(self, columns, widths, aligns=None, rows=None, totals=None):
        self.columns = columns
        self.widths = widths
        self.aligns = aligns or ["l"] * len(columns)
        self.rows = rows or []
        self.totals = totals


class Document(object):
    """Builds a paginated PDF.  Sizes are in points (72 per inch)."""

    def __init__(self, landscape=True, title="Report", org="", subtitle="",
                 footer=""):
        self.width, self.height = (842, 595) if landscape else (595, 842)
        self.margin = 34
        self.title = title
        self.org = org
        self.subtitle = subtitle
        self.footer = footer
        self.pages = []
        self._ops = []
        self._y = 0
        self._page_no = 0
        self._new_page()

    # -- primitives --------------------------------------------------------
    def _op(self, text):
        self._ops.append(text)

    def _text(self, x, y, value, size=9, bold=False, colour=(0, 0, 0)):
        font = "F2" if bold else "F1"
        self._op("BT /%s %g Tf %g %g %g rg %g %g Td (%s) Tj ET"
                 % (font, size, colour[0], colour[1], colour[2], x, y,
                    _escape(_latin(value))))

    def _rect(self, x, y, w, h, colour):
        self._op("%g %g %g rg %g %g %g %g re f" % (colour[0], colour[1], colour[2], x, y, w, h))

    def _line(self, x1, y1, x2, y2, colour=(0.75, 0.75, 0.75), width=0.5):
        self._op("%g w %g %g %g RG %g %g m %g %g l S"
                 % (width, colour[0], colour[1], colour[2], x1, y1, x2, y2))

    # -- page handling -----------------------------------------------------
    def _new_page(self):
        if self._ops:
            self.pages.append("\n".join(self._ops))
        self._ops = []
        self._page_no += 1
        self._y = self.height - self.margin
        self._draw_header()

    def _draw_header(self):
        if self.org:
            self._text(self.margin, self._y - 12, self.org, 14, True, (0.12, 0.22, 0.39))
            self._y -= 20
        self._text(self.margin, self._y - 10, self.title, 10.5, True, (0.2, 0.2, 0.2))
        self._y -= 15
        if self.subtitle:
            self._text(self.margin, self._y - 9, self.subtitle, 8.5, False, (0.4, 0.4, 0.4))
            self._y -= 13
        self._line(self.margin, self._y - 3, self.width - self.margin, self._y - 3,
                   (0.12, 0.22, 0.39), 1.1)
        self._y -= 14

    def _finish_pages(self):
        for index in range(len(self.pages) + 1):
            pass
        if self._ops:
            self.pages.append("\n".join(self._ops))
            self._ops = []

    # -- content -----------------------------------------------------------
    def heading(self, text, size=10):
        if self._y < self.margin + 60:
            self._new_page()
        self._text(self.margin, self._y - size, text, size, True, (0.12, 0.22, 0.39))
        self._y -= size + 7

    def paragraph(self, text, size=8.5):
        if self._y < self.margin + 40:
            self._new_page()
        self._text(self.margin, self._y - size, text, size, False, (0.25, 0.25, 0.25))
        self._y -= size + 5

    def key_values(self, pairs, columns=3):
        available = self.width - 2 * self.margin
        cell = available / columns
        index = 0
        while index < len(pairs):
            if self._y < self.margin + 40:
                self._new_page()
            row = pairs[index:index + columns]
            for position, (label, value) in enumerate(row):
                x = self.margin + position * cell
                self._text(x, self._y - 8, label, 7.5, False, (0.45, 0.45, 0.45))
                self._text(x, self._y - 19, str(value), 10, True, (0.1, 0.1, 0.1))
            self._y -= 28
            index += columns

    def table(self, table, row_height=13.5, header_height=17, size=8):
        total_width = sum(table.widths)
        scale = (self.width - 2 * self.margin) / total_width
        widths = [w * scale for w in table.widths]

        def draw_header():
            y = self._y - header_height
            self._rect(self.margin, y, sum(widths), header_height, (0.12, 0.22, 0.39))
            x = self.margin
            for i, name in enumerate(table.columns):
                label = fit(name, widths[i] - 8, 7.5, True)
                tx = x + 4
                if table.aligns[i] == "r":
                    tx = x + widths[i] - 4 - text_width(label, 7.5, True)
                elif table.aligns[i] == "c":
                    tx = x + (widths[i] - text_width(label, 7.5, True)) / 2
                self._text(tx, y + 5.5, label, 7.5, True, (1, 1, 1))
                x += widths[i]
            self._y = y

        if self._y < self.margin + header_height + 3 * row_height:
            self._new_page()
        draw_header()

        shade = False
        for row in table.rows:
            if self._y - row_height < self.margin + 18:
                self._new_page()
                draw_header()
                shade = False
            y = self._y - row_height
            if shade:
                self._rect(self.margin, y, sum(widths), row_height, (0.965, 0.972, 0.98))
            shade = not shade
            x = self.margin
            for i, value in enumerate(row):
                label = fit("" if value is None else str(value), widths[i] - 8, size)
                tx = x + 4
                if table.aligns[i] == "r":
                    tx = x + widths[i] - 4 - text_width(label, size)
                elif table.aligns[i] == "c":
                    tx = x + (widths[i] - text_width(label, size)) / 2
                self._text(tx, y + 4, label, size, False, (0.13, 0.13, 0.13))
                x += widths[i]
            self._line(self.margin, y, self.margin + sum(widths), y, (0.88, 0.88, 0.9), 0.4)
            self._y = y

        if table.totals:
            if self._y - row_height < self.margin + 18:
                self._new_page()
                draw_header()
            y = self._y - row_height - 1
            self._rect(self.margin, y, sum(widths), row_height + 1, (0.90, 0.925, 0.96))
            x = self.margin
            for i, value in enumerate(table.totals):
                label = fit("" if value is None else str(value), widths[i] - 8, size, True)
                tx = x + 4
                if table.aligns[i] == "r":
                    tx = x + widths[i] - 4 - text_width(label, size, True)
                elif table.aligns[i] == "c":
                    tx = x + (widths[i] - text_width(label, size, True)) / 2
                self._text(tx, y + 4.5, label, size, True, (0.08, 0.16, 0.32))
                x += widths[i]
            self._y = y
        self._y -= 12

    def spacer(self, amount=10):
        self._y -= amount

    # -- output ------------------------------------------------------------
    def save(self, path):
        self._finish_pages()
        stamp = datetime.datetime.now().strftime("%d %b %Y %H:%M")
        total = len(self.pages)
        streams = []
        for index, content in enumerate(self.pages):
            ops = [content]
            note = self.footer or "Generated %s" % stamp
            ops.append("BT /F1 7 Tf 0.5 0.5 0.5 rg %g %g Td (%s) Tj ET"
                       % (self.margin, self.margin - 8, _escape(_latin(note))))
            label = "Page %d of %d" % (index + 1, total)
            ops.append("BT /F1 7 Tf 0.5 0.5 0.5 rg %g %g Td (%s) Tj ET"
                       % (self.width - self.margin - text_width(label, 7),
                          self.margin - 8, _escape(label)))
            streams.append("\n".join(ops).encode("latin-1", "replace"))

        objects = []

        def add(body):
            objects.append(body)
            return len(objects)

        font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                           b"/Encoding /WinAnsiEncoding >>")
        font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                        b"/Encoding /WinAnsiEncoding >>")
        pages_id = add(b"")  # placeholder, filled once page ids are known

        page_ids = []
        for stream in streams:
            content_id = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream
                             + b"\nendstream")
            page_id = add(
                ("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %g %g] "
                 "/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> "
                 "/Contents %d 0 R >>"
                 % (pages_id, self.width, self.height, font_regular, font_bold,
                    content_id)).encode("latin-1"))
            page_ids.append(page_id)

        kids = " ".join("%d 0 R" % pid for pid in page_ids)
        objects[pages_id - 1] = ("<< /Type /Pages /Count %d /Kids [%s] >>"
                                 % (len(page_ids), kids)).encode("latin-1")
        catalog_id = add(("<< /Type /Catalog /Pages %d 0 R >>" % pages_id).encode("latin-1"))
        info_id = add(("<< /Title (%s) /Producer (EOSB Management System) "
                       "/CreationDate (D:%s) >>"
                       % (_escape(_latin(self.title)),
                          datetime.datetime.now().strftime("%Y%m%d%H%M%S")))
                      .encode("latin-1"))

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += ("%d 0 obj\n" % number).encode("latin-1") + body + b"\nendobj\n"
        xref_at = len(out)
        out += ("xref\n0 %d\n" % (len(objects) + 1)).encode("latin-1")
        out += b"0000000000 65535 f \n"
        for offset in offsets[1:]:
            out += ("%010d 00000 n \n" % offset).encode("latin-1")
        out += ("trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objects) + 1, catalog_id, info_id, xref_at)).encode("latin-1")

        with open(path, "wb") as fh:
            fh.write(bytes(out))
        return path
