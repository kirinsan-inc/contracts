#!/usr/bin/env python3
"""Render the allowlisted Markdown directly, then verify the extracted PDF text."""
from __future__ import annotations

import hashlib
import html
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.graphics import renderPDF
from reportlab.platypus import (
    HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from svglib.svglib import svg2rlg

from check_sources import PARSER, ROOT, check

OUTPUT = ROOT / "output/pdf"
LOGO = ROOT / "print/assets/k.inc.brand.full.2025.svg"
LOGO_SHA256 = "0c057716cdcc4d2d80baec99a1dc5f9ba215702d7536b99f457a21c19f2a83a0"
FONTS = {
    "LineSeedJP": (
        ROOT / "print/fonts/LINESeedJP-Regular.ttf",
        "04a6c0077ddb8ba5af3638bd76b4600708dde7b38df047b40fbe6f3af358d3c3",
    ),
    "LineSeedJP-Bold": (
        ROOT / "print/fonts/LINESeedJP-Bold.ttf",
        "67aec2dc10b3ad210d6f7d53b33bbfea42ea28e32fa3834624eee699a638d5ff",
    ),
}
REPOSITORY = "https://github.com/kirinsan-inc/contracts"
PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
WIDTH = PAGE_W - 2 * MARGIN
INK = colors.HexColor("#192735")
MUTED = colors.HexColor("#64747D")
ACCENT = colors.HexColor("#547C83")
RULE = colors.HexColor("#CBD5D7")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def logo_drawing():
    if sha(LOGO) != LOGO_SHA256:
        raise ValueError(f"Bundled brand logo hash does not match: {LOGO.name}")
    drawing = svg2rlg(str(LOGO))
    if drawing is None or drawing.width <= 0 or drawing.height <= 0:
        raise ValueError(f"Cannot render brand logo: {LOGO.name}")
    return drawing


def register_fonts():
    for name, (path, checksum) in FONTS.items():
        if sha(path) != checksum:
            raise ValueError(f"Bundled LINE Seed JP font hash does not match: {path.name}")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "LineSeedJP", normal="LineSeedJP", bold="LineSeedJP-Bold",
        italic="LineSeedJP", boldItalic="LineSeedJP-Bold",
    )


def styles(guide=False, ai=False):
    base = dict(fontName="LineSeedJP", fontSize=9.4,
                leading=14.4 if guide else 16.1,
                textColor=INK, alignment=TA_LEFT, wordWrap="CJK",
                spaceAfter=4 if guide else 6, allowWidows=0, allowOrphans=0)
    if ai:
        base |= dict(fontSize=9.2, leading=13.5, spaceAfter=3)
    result = {
        "body": ParagraphStyle("body", **base),
        "h1": ParagraphStyle("title", **(base | dict(
            fontName="LineSeedJP-Bold", fontSize=18.5 if guide else 19.2,
            leading=26 if guide else 28,
            spaceBefore=8, spaceAfter=12, keepWithNext=True))),
        "h2": ParagraphStyle("section", **(base | dict(
            fontName="LineSeedJP-Bold", fontSize=11.5, leading=18,
            textColor=INK, spaceBefore=10 if guide else 14,
            spaceAfter=5 if guide else 7, keepWithNext=True))),
        "h3": ParagraphStyle("subsection", **(base | dict(
            fontName="LineSeedJP-Bold", fontSize=10.2, leading=16,
            spaceBefore=10, spaceAfter=6, keepWithNext=True))),
        "quote": ParagraphStyle("quote", **(base | dict(
            leftIndent=10, borderColor=RULE, borderWidth=0.5,
            borderPadding=8, spaceBefore=4, spaceAfter=10))),
        "cell": ParagraphStyle("cell", **(base | dict(fontSize=8.5, leading=14, spaceAfter=0))),
        "form_heading": ParagraphStyle("form-heading", **(base | dict(
            fontName="LineSeedJP-Bold", fontSize=10, leading=15, spaceAfter=0))),
        "form_label": ParagraphStyle("form-label", **(base | dict(
            fontName="LineSeedJP-Bold", fontSize=8.4, leading=13.2,
            textColor=MUTED, spaceAfter=0))),
        "form_value": ParagraphStyle("form-value", **(base | dict(
            fontSize=9, leading=14, spaceAfter=0))),
        "meta": ParagraphStyle("metadata", **(base | dict(
            fontSize=8.2, leading=13.3, textColor=MUTED, spaceAfter=2))),
        "masthead": ParagraphStyle("masthead", **(base | dict(
            fontSize=8.4, leading=14.2, textColor=MUTED,
            spaceAfter=15, keepWithNext=True))),
        "opening_note": ParagraphStyle("opening-note", **(base | dict(
            fontSize=8.2, leading=13, textColor=MUTED, spaceAfter=13))),
    }
    if ai:
        result["h2"] = ParagraphStyle("ai-section", parent=result["h2"],
                                      fontSize=11, leading=16, spaceBefore=9, spaceAfter=4)
        result["meta"] = ParagraphStyle("ai-meta", parent=result["meta"],
                                        fontSize=8, leading=11.5, spaceAfter=1)
    return result


def inline(token, source):
    markup, plain = [], []
    for child in token.children or []:
        kind, content = child.type, child.content
        if kind in ("text", "code_inline"):
            escaped = html.escape(content)
            if "/guide-" in source:
                for symbol in ("☀", "★"):
                    escaped = escaped.replace(symbol, f'<font color="#547C83">{symbol}</font>')
            markup.append(escaped)
            plain.append(content)
        elif kind == "softbreak":
            markup.append(" ")
            plain.append(" ")
        elif kind == "hardbreak":
            markup.append("<br/>")
            plain.append("\n")
        elif kind in ("strong_open", "strong_close"):
            markup.append("<b>" if kind.endswith("open") else "</b>")
        elif kind in ("em_open", "em_close"):
            # Japanese emphasis is rendered with semibold, not synthetic italics.
            markup.append("<b>" if kind.endswith("open") else "</b>")
        elif kind == "link_open":
            href = child.attrGet("href") or ""
            if not urlsplit(href).scheme:
                base = REPOSITORY + "/blob/main/" + quote(source)
                href = urljoin(base, href)
            markup.append(f'<link href="{html.escape(href, quote=True)}" color="#365E69">')
        elif kind == "link_close":
            markup.append("</link>")
        else:
            raise ValueError(f"Unsupported inline Markdown token {kind} in {source}")
    return "".join(markup), "".join(plain)


class NumberedCanvas(Canvas):
    def __init__(self, *args, label, version, **kwargs):
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)
        self.states, self.label, self.version = [], label, version

    def showPage(self):
        self.states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self.states)
        for state in self.states:
            self.__dict__.update(state)
            self.decorate(total)
            super().showPage()
        super().save()

    def decorate(self, total):
        self.saveState()
        logo = logo_drawing()
        logo_scale = 7.2 * mm / logo.height
        self.saveState()
        self.translate(MARGIN, PAGE_H - 14.6 * mm)
        self.scale(logo_scale, logo_scale)
        renderPDF.draw(logo, self, 0, 0)
        self.restoreState()
        self.setFont("LineSeedJP", 6.8)
        self.setFillColor(MUTED)
        self.drawRightString(PAGE_W - MARGIN, PAGE_H - 14 * mm, self.label)
        self.setStrokeColor(RULE)
        self.setLineWidth(0.45)
        self.line(MARGIN, PAGE_H - 17.5 * mm, PAGE_W - MARGIN, PAGE_H - 17.5 * mm)
        self.line(MARGIN, 17 * mm, PAGE_W - MARGIN, 17 * mm)
        self.setFont("LineSeedJP", 6.8)
        footer = f"github.com/kirinsan-inc/contracts | {self.version}"
        self.drawString(MARGIN, 12 * mm, footer)
        self.drawRightString(PAGE_W - MARGIN, 12 * mm, f"{self._pageNumber:02d} / {total:02d}")
        self.restoreState()


def render_flowables(entry):
    source = entry["source"]
    raw = (ROOT / source).read_text(encoding="utf-8")
    is_ai = source.startswith("ai-guidelines/")
    lines, tokens, st = raw.splitlines(), PARSER.parse(raw), styles("/guide-" in source, ai=is_ai)
    story, expected, signature = [], [], None
    section_starts, section_names = [], []
    list_stack, item_stack = [], []
    seen_section, quote_depth, i = False, 0, 0
    while i < len(tokens):
        token = tokens[i]
        kind = token.type
        if kind == "heading_open":
            text, plain = inline(tokens[i + 1], source)
            if token.tag == "h2":
                seen_section = True
                section_starts.append(len(story))
                section_names.append(plain)
            if plain.startswith("締結欄"):
                signature = len(story)
            style = st.get(token.tag, st["h3"])
            story.append(Paragraph(text, style))
            expected.append(plain)
            i += 3
        elif kind in ("bullet_list_open", "ordered_list_open"):
            list_stack.append(kind)
            i += 1
        elif kind in ("bullet_list_close", "ordered_list_close"):
            list_stack.pop()
            i += 1
        elif kind == "list_item_open":
            marker = "•"
            if list_stack[-1] == "ordered_list_open":
                match = re.match(r"\s*(\d+)[.)]\s", lines[token.map[0]])
                if not match:
                    raise ValueError(f"Cannot recover source list number in {source}")
                marker = match.group(1) + "."
            item_stack.append({"marker": marker, "first": True})
            i += 1
        elif kind == "list_item_close":
            item_stack.pop()
            i += 1
        elif kind == "paragraph_open":
            text, plain = inline(tokens[i + 1], source)
            style = st["quote"] if quote_depth else st["body"]
            if not seen_section and (plain.startswith("標準書式") or
                                     plain.startswith("標準別紙") or
                                     plain.startswith("標準雛形の説明用") or
                                     plain.startswith("標準別添資料")):
                style = st["masthead"]
            elif not seen_section and (plain.startswith("本書の作成日・公開日は") or
                                       plain.startswith("本書は記入前の標準雛形")):
                style = st["opening_note"]
            if list_stack:
                metadata = not seen_section and list_stack[0] == "bullet_list_open"
                style = st["meta"] if metadata else style
                compact = (source.startswith("security-policy/") or is_ai) and not metadata
                indent = (14 if compact else 18) * len(list_stack)
                style = ParagraphStyle("item", parent=style, leftIndent=indent,
                                       bulletIndent=indent - (14 if compact else 18),
                                       bulletFontName="LineSeedJP",
                                       bulletFontSize=style.fontSize,
                                       leading=15.2 if source.startswith("security-policy/") and compact else style.leading,
                                       spaceAfter=3 if compact else style.spaceAfter)
                marker = item_stack[-1]["marker"] if item_stack[-1]["first"] else None
                item_stack[-1]["first"] = False
            else:
                marker = None
            story.append(Paragraph(text, style, bulletText=marker))
            expected.append(plain)
            i += 3
        elif kind == "blockquote_open":
            quote_depth += 1
            i += 1
        elif kind == "blockquote_close":
            quote_depth -= 1
            i += 1
        elif kind == "hr":
            story.extend([Spacer(1, 8), HRFlowable(width="100%", color=RULE, thickness=0.5), Spacer(1, 8)])
            i += 1
        elif kind == "table_open":
            form = signature is not None
            rows, row, row_plain, row_labels = [], [], [], []
            i += 1
            while tokens[i].type != "table_close":
                current = tokens[i]
                if current.type == "tr_open":
                    row, row_plain = [], []
                elif current.type == "inline":
                    text, plain = inline(current, source)
                    if form:
                        style = st["form_heading"] if not rows else (
                            st["form_label"] if not row else st["form_value"])
                    else:
                        style = st["cell"]
                    row.append(Paragraph(text, style))
                    row_plain.append(plain)
                    expected.append(plain)
                elif current.type == "tr_close":
                    rows.append(row)
                    if form:
                        row_labels.append(row_plain[0])
                i += 1
            columns = len(rows[0])
            if form:
                if columns != 2:
                    raise ValueError(f"Signature form must have two columns: {source}")
                heights = [None] * len(rows)
                for number, label in enumerate(row_labels):
                    if "署名・押印" in label:
                        heights[number] = 17 * mm
                table = Table(rows, colWidths=[67 * mm, WIDTH - 67 * mm],
                              rowHeights=heights, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF2F2")),
                    ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#F8FAFA")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]))
                story.extend([table, Spacer(1, 11)])
            else:
                table = Table(rows, colWidths=[WIDTH / columns] * columns,
                              repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF2F2")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]))
                story.extend([table, Spacer(1, 8)])
            i += 1
        elif kind in ("fence", "code_block"):
            for line in token.content.splitlines():
                story.append(Paragraph(html.escape(line) or " ", st["quote"]))
                expected.append(line)
            i += 1
        else:
            raise ValueError(f"Unsupported Markdown block {kind} in {source}")
    if signature is not None:
        story[signature:] = [KeepTogether(story[signature:])]
    elif entry.get("keep_final_sections"):
        count = entry["keep_final_sections"]
        if not isinstance(count, int) or not 1 <= count <= len(section_starts):
            raise ValueError(f"Invalid keep_final_sections in {source}")
        start = section_starts[-count]
        story[start:] = [KeepTogether(story[start:])]
    if source.startswith("security-policy/"):
        section = section_names.index("9. 業務終了時")
        start = section_starts[section]
        end = section_starts[section + 1]
        story[start:end] = [KeepTogether(story[start:end])]
    return story, expected


def normalize(text):
    return re.sub(r"\s+", "", text)


def validate_pdf(path, expected, entry):
    reader = PdfReader(path)
    pages = []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        for decoration in (entry["label"],
                           f"github.com/kirinsan-inc/contracts | {entry['version']}",
                           f"{number:02d} / {len(reader.pages):02d}"):
            # Decorations are appended after body text by NumberedCanvas.
            position = text.rfind(decoration)
            if position >= 0:
                text = text[:position] + text[position + len(decoration):]
        if len(normalize(text)) < 30:
            raise ValueError(f"Blank or near-blank page: {path.name} page {number}")
        if "\ufffd" in text or "\x00" in text:
            raise ValueError(f"Broken text encoding: {path.name} page {number}")
        pages.append(text)
    all_text = normalize("".join(pages))
    position = 0
    for block in expected:
        needle = normalize(block)
        if not needle:
            continue
        found = all_text.find(needle, position)
        if found < 0:
            raise ValueError(f"PDF text missing or changed in {path.name}: {block[:120]}")
        position = found + len(needle)
    fonts = {}
    for page in reader.pages:
        for font in page["/Resources"].get("/Font", {}).values():
            obj = font.get_object()
            if "LINESeedJP" in str(obj.get("/BaseFont", "")):
                descriptor = obj["/FontDescriptor"].get_object()
                if "/FontFile2" not in descriptor:
                    raise ValueError(f"Japanese font not embedded: {path.name}")
                fonts[str(obj["/BaseFont"])] = True
    if not all(any(weight in name for name in fonts) for weight in ("Regular", "Bold")):
        raise ValueError(f"Both Japanese font weights must be embedded: {path.name}")
    return len(reader.pages)


def main():
    entries = check()
    register_fonts()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for entry in entries:
        story, expected = render_flowables(entry)
        for font_name in FONTS:
            supported = pdfmetrics.getFont(font_name).face.charWidths
            missing = sorted({c for text in expected for c in text
                              if not c.isspace() and ord(c) not in supported})
            if missing:
                raise ValueError(f"{font_name} lacks source characters in {entry['source']}: {missing}")
        target = OUTPUT / entry["output"]
        title = expected[0]
        document = SimpleDocTemplate(
            str(target), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=23 * mm, bottomMargin=23 * mm,
            title=title, author="株式会社kirinsan",
            subject=f"{entry['version']} | {entry['source']}",
            pageCompression=1,
        )
        document.build(story, canvasmaker=lambda *a, **kw: NumberedCanvas(
            *a, label=entry["label"], version=entry["version"], **kw))
        page_count = validate_pdf(target, expected, entry)
        manifest.append({"source": entry["source"], "source_sha256": sha(ROOT / entry["source"]),
                         "pdf": entry["output"], "pdf_sha256": sha(target),
                         "version": entry["version"], "pages": page_count,
                         "verified_text_blocks": len(expected)})
        print(f"OK: {target.name}: {page_count} pages; {len(expected)} source blocks verified")
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
