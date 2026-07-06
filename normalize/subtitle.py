"""Subtitle dump / news article draft -> speaker-turn segments (no timecodes).

Timecodes are attached later by analyze/align.py against the ASR result.
"""
from ..schema import Segment
from ..utils import make_seg_id


def fill(doc, raw):
    turns = raw.meta.get("turns") or [{}] * len(raw.text_blocks)
    segments = []
    for i, block in enumerate(raw.text_blocks):
        turn = turns[i] if i < len(turns) else {}
        segments.append(Segment(
            seg_id=make_seg_id(doc.doc_id, i), text=block, order=i,
            speaker=turn.get("speaker"),
            kind=(raw.meta.get("sections") or [None])[0] if raw.meta.get("sections") else None))
    doc.segments = segments
    doc.program_meta.update(
        {k: v for k, v in raw.meta.items() if k not in ("turns", "sections")})
