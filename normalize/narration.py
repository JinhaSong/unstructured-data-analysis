"""Narration script (대본) -> paragraph segments; speaker turns where markable."""
import re

from ..schema import Segment
from ..utils import make_seg_id

_SPEAKER_RE = re.compile(r"^([가-힣A-Za-z]{2,10})\s*[:：]\s*(.+)$")


def fill(doc, raw):
    segments = []
    for i, block in enumerate(raw.text_blocks):
        speaker = None
        m = _SPEAKER_RE.match(block)
        if m:
            speaker, block = m.group(1), m.group(2)
        segments.append(Segment(seg_id=make_seg_id(doc.doc_id, i), text=block,
                                order=i, speaker=speaker))
    doc.segments = segments
    doc.program_meta.update(raw.meta)
