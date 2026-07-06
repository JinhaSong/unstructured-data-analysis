""".mp4.xml clipInfo parser (stdlib xml) -- archive metadata attached to videos.

<clipInfo><CLIPID>..</CLIPID><TITLE>..</TITLE><KEYWORD>a / b, c</KEYWORD>
<DUR>48: 54</DUR><DURTC>00:48:54:05</DURTC><GRADE>2</GRADE></clipInfo>
"""
import re
import xml.etree.ElementTree as ET

from ..utils import parse_timecode
from .base import BaseParser, RawDoc


class XmlParser(BaseParser):
    def parse(self, path: str, hint: str | None = None) -> RawDoc:
        root = ET.parse(path).getroot()
        kv = {child.tag: (child.text or "").strip() for child in root}

        keywords = [k.strip().rstrip(".")
                    for k in re.split(r"[/,]", kv.get("KEYWORD", "")) if k.strip()]
        meta = {
            "clip_id": kv.get("CLIPID"),
            "title": kv.get("TITLE"),
            "subtitle": kv.get("SUBTITLE"),
            "created_date": kv.get("CDATE"),
            "curator": kv.get("CURNM"),
            "grade": kv.get("GRADE"),
            "duration_seconds": parse_timecode(kv.get("DURTC") or kv.get("DUR")),
            "keywords": keywords,
            "raw": kv,
        }
        blocks = [t for t in (kv.get("TITLE"), kv.get("SUBTITLE")) if t]
        return RawDoc(source_path=path, source_format="xml",
                      doc_type_hint="clip_meta", text_blocks=blocks, meta=meta)
