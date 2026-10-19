# ruff: noqa: E501  (XML-шаблоны одной строкой)
"""Минимальный писатель .docx без внешних зависимостей (B2-10).

Нужны только абзацы, жирный/курсив и гиперссылки, поэтому собираем WordprocessingML сами:
python-docx в зависимости сервиса не входит (и uv.lock не пересобирается без сети).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

# символы, которых в XML 1.0 быть не может (встречаются в текстах постов)
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")

_NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    f'<Relationship Id="rId1" Type="{_REL}/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f"<w:styles {_NS}>"
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
    '<w:sz w:val="22"/><w:lang w:val="ru-RU"/></w:rPr></w:rPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:spacing w:after="200"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:keepNext/><w:spacing w:before="280" w:after="80"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>'
    '<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/>'
    '<w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>'
    "</w:styles>"
)


def clean(text: str) -> str:
    return _BAD_XML.sub("", text)


@dataclass
class _Run:
    text: str
    bold: bool = False
    italic: bool = False
    link: str | None = None


@dataclass
class DocxBuilder:
    """Собирает документ из абзацев; `.build()` возвращает байты .docx."""

    _body: list[str] = field(default_factory=list)
    _links: list[str] = field(default_factory=list)

    def paragraph(self, *runs: _Run | str, style: str | None = None) -> None:
        props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        parts = [self._run(r if isinstance(r, _Run) else _Run(r)) for r in runs]
        self._body.append(f"<w:p>{props}{''.join(parts)}</w:p>")

    def title(self, text: str) -> None:
        self.paragraph(text, style="Title")

    def heading(self, *runs: _Run | str) -> None:
        self.paragraph(*runs, style="Heading1")

    def _run(self, run: _Run) -> str:
        props = ""
        if run.bold:
            props += "<w:b/>"
        if run.italic:
            props += "<w:i/>"
        if run.link:
            props += '<w:rStyle w:val="Hyperlink"/>'
        rpr = f"<w:rPr>{props}</w:rPr>" if props else ""
        lines = clean(run.text).split("\n")
        text = "<w:br/>".join(f'<w:t xml:space="preserve">{escape(line)}</w:t>' for line in lines)
        xml = f"<w:r>{rpr}{text}</w:r>"
        if run.link:
            self._links.append(run.link)
            return f'<w:hyperlink r:id="rIdL{len(self._links)}">{xml}</w:hyperlink>'
        return xml

    def build(self) -> bytes:
        document = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f"<w:document {_NS}><w:body>{''.join(self._body)}"
            '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1134" w:right="850" w:bottom="1134" w:left="1134" w:header="708" '
            'w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>'
        )
        rels = "".join(
            f'<Relationship Id="rIdL{i}" Type="{_REL}/hyperlink" Target={quoteattr(clean(url))} '
            'TargetMode="External"/>'
            for i, url in enumerate(self._links, start=1)
        )
        document_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rIdS" Type="{_REL}/styles" Target="styles.xml"/>{rels}'
            "</Relationships>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", _CONTENT_TYPES)
            z.writestr("_rels/.rels", _ROOT_RELS)
            z.writestr("word/document.xml", document)
            z.writestr("word/_rels/document.xml.rels", document_rels)
            z.writestr("word/styles.xml", _STYLES)
        return buf.getvalue()


def run(text: str, *, bold: bool = False, italic: bool = False, link: str | None = None) -> _Run:
    return _Run(text, bold=bold, italic=italic, link=link)
