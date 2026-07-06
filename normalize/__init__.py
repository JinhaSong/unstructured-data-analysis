"""RawDoc -> CanonicalDocument dispatch. All doc-type knowledge lives here."""
import os

from ..schema import CanonicalDocument
from . import cuesheet, narration, subtitle


def _doc_id(raw) -> str:
    return os.path.splitext(os.path.basename(raw.source_path))[0]


def _base(raw, doc_type: str) -> CanonicalDocument:
    return CanonicalDocument(
        doc_id=_doc_id(raw), doc_type=doc_type,
        source_format=raw.source_format, source_path=raw.source_path)


def to_canonical(raw) -> CanonicalDocument:
    doc_type = raw.doc_type_hint or "subtitle_script"
    doc = _base(raw, doc_type)
    if doc_type == "cuesheet":
        cuesheet.fill(doc, raw)
    elif doc_type == "narration":
        narration.fill(doc, raw)
    elif doc_type == "clip_meta":
        doc.program_meta = dict(raw.meta)
        doc.clip_id = raw.meta.get("clip_id")
    elif doc_type == "schedule":
        # 편성표: no samples collected yet -- treat rows/blocks as plain segments
        narration.fill(doc, raw)
    else:
        subtitle.fill(doc, raw)
    return doc
