"""udav2 — examples/ud JSON(부가정보·편성표) + ASR 전사 JSON 로더.

v1 파서(RawDoc 경유)와 달리 수집 JSON은 이미 구조를 갖고 있으므로
CanonicalDocument로 직접 변환한다. 세그먼트 단위:
  synopsis      logline 1 + 기획의도 문단별
  cast_info     인물 1명당 1 세그먼트 ("배역/배우/설명")
  episode_info  회차당 1 세그먼트
  schedule      편성 항목당 1 세그먼트
  article       문단별
  program_meta  주요 필드를 서술문으로 펼침
  asr_transcript 전사 세그먼트 그대로 (타임코드 보존)
"""
import json
import os

from ..schema import CanonicalDocument, Segment

# 수집 JSON의 doc_type 필드 -> DOC_TYPES_V2
_DOC_TYPE_MAP = {
    "web_synopsis": "synopsis", "synopsis": "synopsis",
    "web_cast": "cast_info", "cast": "cast_info",
    "web_episodes": "episode_info", "episodes": "episode_info",
    "web_article": "article", "article": "article",
    "web_episode_summaries": "episode_summary", "episode_summaries": "episode_summary",
    "web_program_meta": "program_meta", "program_meta": "program_meta",
    "schedule": "schedule",
}


def _seg(i, text, **kw):
    return Segment(seg_id=f"s{i:04d}", text=text, order=i, **kw)


def _parse_synopsis(data):
    segs, i = [], 0
    if data.get("logline"):
        segs.append(_seg(i, data["logline"], kind="logline")); i += 1
    intent = data.get("planning_intent")
    if isinstance(intent, str):
        intent = [intent]
    for block in intent or []:
        text = block.get("text") if isinstance(block, dict) else block
        for para in (text or "").split("\n"):
            if para.strip():
                segs.append(_seg(i, para.strip(), kind="planning_intent")); i += 1
    return segs


def _parse_cast(data):
    segs, i = [], 0
    for group, kind in (("main_cast", "main"), ("supporting_cast", "supporting")):
        for person in data.get(group) or []:
            parts = []
            if person.get("character"):
                parts.append(person["character"])
            if person.get("actor"):
                parts.append(f"({person['actor']} 분)")
            if person.get("description"):
                parts.append(f"— {person['description']}")
            segs.append(_seg(i, " ".join(parts), kind=kind, raw=dict(person))); i += 1
    return segs


def _parse_episodes(data):
    segs = []
    for i, ep in enumerate(data.get("episodes") or []):
        bits = [f"{ep.get('episode_no', i + 1)}회"]
        if ep.get("air_date") or ep.get("date"):
            bits.append(f"{ep.get('air_date') or ep.get('date')} 방송")
        if ep.get("rating_nationwide") is not None:
            bits.append(f"시청률 {ep['rating_nationwide']}%")
        elif ep.get("rating") is not None:
            bits.append(f"시청률 {ep['rating']}%")
        segs.append(_seg(i, ", ".join(bits), kind="episode", raw=dict(ep)))
    return segs


def _parse_schedule(data):
    segs = []
    for i, ent in enumerate(data.get("entries") or []):
        bits = [f"{ent.get('episode_no')}회",
                f"{ent.get('date')}({ent.get('day', '')})",
                f"{ent.get('start')}~{ent.get('end')}",
                ent.get("broadcast_type", "")]
        if ent.get("note"):
            bits.append(f"— {ent['note']}")
        segs.append(_seg(i, " ".join(str(b) for b in bits if b),
                         kind="schedule_entry", raw=dict(ent)))
    return segs


def _parse_article(data):
    segs, i = [], 0
    if data.get("title"):
        segs.append(_seg(i, data["title"], kind="title")); i += 1
    for para in (data.get("body") or "").split("\n"):
        if para.strip():
            segs.append(_seg(i, para.strip(), kind="body")); i += 1
    return segs


def _parse_program_meta(data):
    p = data.get("program") or {}
    lines = []
    if p.get("title"):
        aka = f" ({p['title_en']})" if p.get("title_en") else ""
        lines.append(f"《{p['title']}》{aka}는 {p.get('channel', '')} "
                     f"{p.get('timeslot', '')} {p.get('genre', '드라마')}이다.")
    bp = p.get("broadcast_period") or {}
    if bp:
        lines.append(f"{bp.get('start')}부터 {bp.get('end')}까지 "
                     f"{p.get('episodes_total', '')}부작으로 방송되었다.")
    if p.get("directors"):
        lines.append(f"연출 {', '.join(p['directors'])}.")
    if p.get("writers"):
        lines.append(f"극본 {', '.join(p['writers'])}.")
    if p.get("production_companies"):
        lines.append(f"제작 {', '.join(p['production_companies'])}.")
    if p.get("distribution"):
        lines.append(f"배급/유통 {', '.join(p['distribution'])}.")
    if p.get("categories"):
        lines.append(f"장르: {', '.join(p['categories'])}.")
    return [_seg(i, t, kind="meta") for i, t in enumerate(lines)]


def _parse_episode_summaries(data):
    segs = []
    for i, s in enumerate(data.get("summaries") or []):
        eps = s.get("episodes") or []
        label = "·".join(str(e) for e in eps)
        segs.append(_seg(i, f"{label}회: {s.get('summary', '')}",
                         kind="episode_summary", raw=dict(s)))
    return segs


def _parse_asr(data):
    segs = []
    for i, s in enumerate(data.get("segments") or []):
        segs.append(Segment(
            seg_id=f"asr{i:04d}", text=(s.get("text") or "").strip(), order=i,
            start_time_seconds=s.get("start_time_seconds"),
            end_time_seconds=s.get("end_time_seconds"), kind="asr"))
    return segs


_PARSERS = {
    "synopsis": _parse_synopsis, "cast_info": _parse_cast,
    "episode_info": _parse_episodes, "schedule": _parse_schedule,
    "article": _parse_article, "program_meta": _parse_program_meta,
    "episode_summary": _parse_episode_summaries, "asr_transcript": _parse_asr,
}


def detect_json_doc_type(data, path=""):
    if "segments" in data and ("transcript" in data or "asr_model" in data):
        return "asr_transcript"
    hint = _DOC_TYPE_MAP.get(data.get("doc_type") or "")
    if hint:
        return hint
    name = os.path.basename(path).lower()
    for key, dt in (("summar", "episode_summary"), ("cast", "cast_info"),
                    ("episode", "episode_info"), ("schedule", "schedule"),
                    ("synopsis", "synopsis"), ("article", "article"),
                    ("program", "program_meta")):
        if key in name:
            return dt
    return "other"


def parse_json(path: str, doc_type: str | None = None) -> CanonicalDocument:
    """수집 JSON 1건 -> CanonicalDocument."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    dt = doc_type or detect_json_doc_type(data, path)
    segs = _PARSERS.get(dt, lambda d: [])(data)
    doc_id = os.path.splitext(os.path.basename(path))[0]
    program = None
    if isinstance(data.get("program"), dict):
        program = data["program"].get("title")
    program = program or data.get("program_title") or data.get("related_program_hint")
    return CanonicalDocument(
        doc_id=doc_id, doc_type=dt, source_format="json", source_path=path,
        program=program, program_meta={k: v for k, v in data.items()
                                       if k not in ("segments", "body", "episodes",
                                                    "entries", "transcript")},
        segments=segs)
