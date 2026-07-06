"""(format x doc_type) routing.

Extension picks the parser; path keywords (큐시트/대본/자막/...) plus content
heuristics pick the doc_type hint consumed by normalize/.
"""
import os

# path keyword -> doc_type
_PATH_HINTS = (
    ("큐시트", "cuesheet"),
    ("cuesheet", "cuesheet"),
    ("대본", "narration"),
    ("나레이션", "narration"),
    ("원고", "subtitle_script"),   # 기사원고
    ("자막", "subtitle_script"),
    ("편성", "schedule"),
)


def detect_doc_type(path: str) -> str | None:
    lowered = path.lower()
    for key, doc_type in _PATH_HINTS:
        if key in lowered:
            return doc_type
    if lowered.endswith(".xml"):
        return "clip_meta"
    return None


def _parser_for(ext: str):
    # Lazy imports: a worker only needs the deps of formats it actually reads.
    if ext == ".txt":
        from .txt_parser import TxtParser
        return TxtParser()
    if ext in (".xlsx", ".xlsm"):
        from .xlsx_parser import XlsxParser
        return XlsxParser()
    if ext == ".xml":
        from .xml_parser import XmlParser
        return XmlParser()
    if ext == ".pdf":
        from .pdf_parser import PdfParser
        return PdfParser()
    if ext in (".hwp",):
        from .hwp_parser import HwpParser
        return HwpParser()
    raise ValueError(f"unsupported format: {ext}")


def parse(path: str, doc_type: str | None = None):
    """Parse one file -> RawDoc (doc_type_hint filled)."""
    ext = os.path.splitext(path)[1].lower()
    raw = _parser_for(ext).parse(path)
    raw.doc_type_hint = doc_type or detect_doc_type(path) or raw.doc_type_hint
    return raw
