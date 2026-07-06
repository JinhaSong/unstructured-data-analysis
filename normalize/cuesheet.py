"""Cuesheet table -> time-coded segments.

News cuesheet columns (xlsx): 순서/상태/개별 길이/누적/구분/제목/기자/비고.
'누적' is the running END timecode of each item, so
    start = 누적 - 개별길이, end = 누적
which is exactly the item boundary the windowing stage uses.
"""
from ..schema import Segment
from ..utils import make_seg_id, parse_timecode

# header alias -> canonical column key
_COLUMNS = {
    "순서": "order", "상태": "status", "개별 길이": "duration", "개별길이": "duration",
    "누적": "cumulative", "구분": "kind", "제목": "title", "기자": "reporter",
    "비고": "note", "형식": "kind2",
}


def _find_header(table):
    for i, row in enumerate(table):
        hits = sum(1 for cell in row if cell.strip() in _COLUMNS)
        if hits >= 3:
            return i, {j: _COLUMNS[c.strip()] for j, c in enumerate(row)
                       if c.strip() in _COLUMNS}
    return None, {}


def fill(doc, raw):
    segments = []
    for table in raw.tables:
        header_idx, colmap = _find_header(table)
        if header_idx is None:
            continue
        for row in table[header_idx + 1:]:
            item = {key: row[j].strip() for j, key in colmap.items() if j < len(row)}
            title = item.get("title", "")
            if not title:
                continue
            end = parse_timecode(item.get("cumulative"))
            dur = parse_timecode(item.get("duration"))
            start = end - dur if (end is not None and dur is not None) else None
            kind = " ".join(k for k in (item.get("kind"), item.get("kind2"),
                                        item.get("note")) if k)
            segments.append(Segment(
                seg_id=make_seg_id(doc.doc_id, len(segments)),
                text=title,
                order=int(item["order"]) if item.get("order", "").isdigit() else None,
                start_time_seconds=start, end_time_seconds=end,
                speaker=item.get("reporter") or None,
                kind=kind or None, raw=item))
    # PDF/HWP cuesheets often come as text blocks, not tables -- keep them raw
    if not segments:
        for i, block in enumerate(raw.text_blocks):
            segments.append(Segment(seg_id=make_seg_id(doc.doc_id, i), text=block,
                                    order=i))
    doc.segments = segments
    doc.program_meta.update({k: v for k, v in raw.meta.items() if k != "sheets"})
