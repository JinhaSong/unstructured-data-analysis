"""udav2 — txt 입력 파서 (입력은 모두 txt로 들어온다는 가정).

원천 포맷(hwp/xlsx/pdf/웹 등)이 무엇이든 "텍스트만 추출된 상태"의 txt를 입력으로
받아 CanonicalDocument로 변환한다. 여기의 파서들은 ETRI 표준 txt 규약(수집 시
변환 규칙) 기준이며, 방송사별 상이한 포맷은 PARSERS 레지스트리에
(doc_type, format_id) 키로 파서를 추가해 대응한다.

유형 판별: 상위 디렉토리명(articles/cast/meta/schedule/summary) > 파일명 키워드.
판별 실패 시 generic(문단 분할)으로 처리 — "어떤 포맷이든 텍스트만 추출해서
사용한다"는 최소 동작 보장.
"""
import os
import re

from ..schema import CanonicalDocument, Segment

# ── 유형 판별 ────────────────────────────────────────────────────────────

_DIR_HINTS = {
    "articles": "article", "cast": "cast_info", "schedule": "schedule",
    "subtitle": "subtitle_script",
}
_NAME_HINTS = (
    ("program_meta", "program_meta"), ("episode_summar", "episode_summary"),
    ("episode", "episode_info"), ("synopsis", "synopsis"),
    ("cast", "cast_info"), ("schedule", "schedule"), ("article", "article"),
    ("subtitle", "subtitle_script"), ("cuesheet", "cuesheet"),
    ("script", "narration"),
)


def detect_txt_doc_type(path: str) -> str:
    parent = os.path.basename(os.path.dirname(path)).lower()
    name = os.path.basename(path).lower()
    for key, dt in _NAME_HINTS:          # 파일명이 디렉토리보다 구체적
        if key in name:
            return dt
    if parent in _DIR_HINTS:
        return _DIR_HINTS[parent]
    return "other"


# ── 유형별 파서 (ETRI 표준 txt 규약) ─────────────────────────────────────

def _seg(i, text, **kw):
    return Segment(seg_id=f"s{i:04d}", text=text, order=i, **kw)


def _lines(text):
    return [l.rstrip() for l in text.split("\n")]


_KV = re.compile(r"^([^:#]{1,20}):\s*(.*)$")

_PM_FIELD = {  # program_meta.txt 의 "키: 값" -> 내부 필드
    "제목": "title", "영문 제목": "title_en", "채널": "channel",
    "방송 기간": "broadcast_period", "편성": "timeslot", "부작": "episodes_total",
    "장르": "genre", "연출": "directors", "극본": "writers",
    "제작사": "production_companies", "유통": "distribution", "시청률": "ratings",
}
_LIST_FIELDS = {"directors", "writers", "production_companies", "distribution"}


def _parse_program_meta(text):
    fields, segs = {}, []
    for i, line in enumerate(l for l in _lines(text) if l.strip()):
        segs.append(_seg(len(segs), line, kind="meta"))
        m = _KV.match(line)
        if not m:
            continue
        key = _PM_FIELD.get(m.group(1).strip())
        val = m.group(2).strip()
        if not key or not val:
            continue
        fields[key] = ([v.strip() for v in val.split(",")]
                       if key in _LIST_FIELDS else val)
    if isinstance(fields.get("genre"), str):
        m = re.match(r"([^(]+)\(([^)]*)\)", fields["genre"])
        if m:
            fields["genre"] = m.group(1).strip()
            fields["categories"] = [c.strip() for c in m.group(2).split(",")]
    return segs, {"fields": fields}


_CAST_PAT = re.compile(
    r"^(?P<character>[^(]{1,15})\((?P<actor>[^)]{1,12})\s*분\)\s*"
    r"(?:\[(?P<group>주연|조연|특별출연)\])?\s*(?:\[(?P<age>\d{1,3})세\])?"
    r"\s*(?:[—-]\s*(?P<description>.+))?$")


def _parse_cast(text):
    segs = []
    for line in _lines(text):
        if not line.strip() or line.startswith("#"):
            continue
        m = _CAST_PAT.match(line.strip())
        raw = {}
        if m:
            raw = {k: (v.strip() if isinstance(v, str) else v)
                   for k, v in m.groupdict().items() if v}
            raw["role_group"] = raw.pop("group", "조연")
        segs.append(_seg(len(segs), line.strip(),
                         kind=raw.get("role_group", "cast"), raw=raw))
    return segs, {}


_EP_PAT = re.compile(
    r"^(?P<no>\d{1,3})회\s*\|\s*(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:\s*\((?P<day>[월화수목금토일])\))?"
    r"(?:\s*\|\s*(?P<time>\d{1,2}:\d{2}~\d{1,2}:\d{2}))?"
    r"(?:\s*\|\s*시청률\s*(?P<rating>[\d.]+)%)?"
    r"(?:\s*\|\s*(?P<rest>.*))?$")


def _parse_episode_lines(text, kind):
    """episodes.txt / schedule.txt 공용 — 'N회 | 날짜 | ...' 행 파서."""
    segs = []
    for line in _lines(text):
        if not line.strip() or line.startswith("#"):
            continue
        norm = re.sub(r"\s*\|\s*", " | ", line.strip())
        m = _EP_PAT.match(norm)
        raw = {}
        if m:
            g = m.groupdict()
            raw = {"episode_no": int(g["no"]), "date": g["date"]}
            if g.get("day"):
                raw["day"] = g["day"]
            if g.get("time"):
                raw["start"], raw["end"] = g["time"].split("~")
            if g.get("rating"):
                raw["rating"] = float(g["rating"])
            rest = g.get("rest") or ""
            note = re.search(r"※\s*(.+)$", rest)
            if note:
                raw["note"] = note.group(1).strip()
                rest = rest[:note.start()].strip(" |")
            if rest.strip():
                raw["broadcast_type"] = rest.strip().split(" | ")[0]
        segs.append(_seg(len(segs), norm, kind=kind, raw=raw))
    return segs


_SECTION = re.compile(r"^\[([^\]]+)\]\s*(.*)$")


def _parse_synopsis(text):
    segs, section = [], None
    for line in _lines(text):
        if not line.strip():
            continue
        m = _SECTION.match(line.strip())
        if m and not m.group(2):
            section = {"로그라인": "logline", "기획의도": "planning_intent"}.get(
                m.group(1), m.group(1))
            continue
        segs.append(_seg(len(segs), line.strip(), kind=section or "synopsis"))
    return segs, {}


_EPSUM = re.compile(r"^\[(\d{1,3})(?:[~·,](\d{1,3}))?회\]\s*(.+)$")


def _parse_episode_summaries(text):
    segs = []
    for line in _lines(text):
        if not line.strip() or line.startswith("#"):
            continue
        m = _EPSUM.match(line.strip())
        raw = {}
        if m:
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else lo
            raw = {"episodes": list(range(lo, hi + 1)), "summary": m.group(3)}
        segs.append(_seg(len(segs), line.strip(), kind="episode_summary", raw=raw))
    return segs, {}


_ART_HDR = {"제목": "title", "매체": "press", "기자": "reporter",
            "일자": "published_at", "URL": "source_url", "저작권": "copyright_note",
            "순서": "order_no", "기사 ID": "article_id"}   # 방송사 기사원고 헤더


def _parse_article(text):
    # 헤더: 알려진 키('제목:' 등)의 연속 구간. 빈 줄은 건너뜀 — \r\r\n(방송사
    # 원고 관행)이 유니버설 뉴라인 변환으로 빈 줄을 만들어내기 때문.
    # 알려진 키가 아닌 첫 비공백 행부터 본문.
    header, lines = {}, _lines(text)
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = _KV.match(line)
        if m and m.group(1).strip() in _ART_HDR:
            header[_ART_HDR[m.group(1).strip()]] = m.group(2).strip()
            i += 1
        else:
            break
    body_lines = lines[i:]
    segs = []
    if header.get("title"):
        segs.append(_seg(0, header["title"], kind="title"))
    for para in "\n".join(body_lines).split("\n"):
        if para.strip():
            segs.append(_seg(len(segs), para.strip(), kind="body"))
    return segs, header


def _parse_generic(text):
    """유형 미상 — 문단 단위 분할만 수행 (최소 동작)."""
    segs = [
        _seg(i, para.strip(), kind="paragraph")
        for i, para in enumerate(p for p in text.split("\n") if p.strip())]
    return segs, {}


# (doc_type, format_id) -> parser. format_id "default"가 ETRI 표준 txt 규약이며
# 방송사별 포맷은 ("cuesheet", "mbc_cb") 처럼 키를 추가해 등록한다.
PARSERS = {
    ("program_meta", "default"): _parse_program_meta,
    ("cast_info", "default"): _parse_cast,
    ("episode_info", "default"): lambda t: (_parse_episode_lines(t, "episode"), {}),
    ("schedule", "default"): lambda t: (_parse_episode_lines(t, "schedule_entry"), {}),
    ("synopsis", "default"): _parse_synopsis,
    ("episode_summary", "default"): _parse_episode_summaries,
    ("article", "default"): _parse_article,
}


def parse_txt(path: str, doc_type: str | None = None,
              format_id: str = "default") -> CanonicalDocument:
    """표준 규약 txt 1건 -> CanonicalDocument."""
    with open(path, encoding="utf-8-sig") as f:   # BOM 제거 (방송사 원고 관행)
        text = f.read()
    dt = doc_type or detect_txt_doc_type(path)
    parser = PARSERS.get((dt, format_id)) or PARSERS.get((dt, "default"))
    segs, extra = parser(text) if parser else _parse_generic(text)
    meta = {"format_id": format_id}
    meta.update(extra if isinstance(extra, dict) else {})
    return CanonicalDocument(
        doc_id=os.path.splitext(os.path.basename(path))[0],
        doc_type=dt, source_format="txt", source_path=path,
        program=(extra.get("fields", {}).get("title")
                 if isinstance(extra, dict) else None),
        program_meta=meta, segments=segs)
