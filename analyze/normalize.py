"""udav2 정제층 ④ — 개체 정규화 (Entity.normalized 채움).

같은 대상의 표면형을 표준형으로 통합한다:
  DATE     '3월 24일'/'2021년 3월 24일' -> ISO(YYYY-MM-DD, 연도는 프로그램 방영
           연도 컨텍스트로 보완. 월 없는 '25일'류는 정규화 보류)
  TIME     '밤 9시 20분'/'오후 10시 30분' -> HH:MM, 'H:MM~H:MM' -> 그대로
  EPISODE  '3~4회' -> '3,4' / '첫 회' -> '1' / '최종회' -> 총부작 / 'N부작' -> 'total:N'
  PROGRAM  '오!주인님'/'《오! 주인님》'/영문 제목 -> 정식 제목
  CHARACTER/ACTOR  plays 관계로 '배역(배우)' 상호 연결형
  RATING   '2.6%' -> '2.6' / '15세 이상 시청가' -> '15+'
  BROADCASTER  대문자 표준형
"""
import re


class NormalizeContext:
    def __init__(self, program_title=None, title_variants=(), year=None,
                 episodes_total=None, plays=None, content_id=None):
        self.title = program_title
        self.variants = {self._key(v) for v in (*title_variants,
                                                *( [program_title] if program_title else []))}
        self.year = year
        self.total = episodes_total
        self.plays = plays or {}            # actor -> character
        self.by_char = {c: a for a, c in (plays or {}).items()}
        self.content_id = content_id

    @staticmethod
    def _key(s):
        return re.sub(r"[\s!《》〈〉'\"“”‘’.]+", "", (s or "").lower())

    def is_title(self, surface):
        return self._key(surface) in self.variants


_DATE_FULL = re.compile(r"(\d{4})[.년]\s*(\d{1,2})[.월]\s*(\d{1,2})일?")
_DATE_MD = re.compile(r"^(\d{1,2})월\s*(\d{1,2})일")
_TIME_AMPM = re.compile(r"(오전|오후|밤|저녁|아침|낮)\s*(\d{1,2})시(?:\s*(\d{1,2})분)?")
_EP_RANGE = re.compile(r"(\d{1,3})\s*[~·,]\s*(\d{1,3})\s*회")
_EP_ONE = re.compile(r"(\d{1,3})\s*회")
_EP_TOTAL = re.compile(r"(\d{1,3})\s*부작")


def _norm_date(text, ctx):
    m = _DATE_FULL.search(text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = _DATE_MD.match(text.strip())
    if m and ctx.year:
        return f"{ctx.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text.strip()):
        return text.strip()
    return None


def _norm_time(text):
    if re.fullmatch(r"\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2}", text.strip()):
        return re.sub(r"\s", "", text)
    m = _TIME_AMPM.search(text)
    if m:
        hour = int(m.group(2))
        if m.group(1) in ("오후", "밤", "저녁") and hour < 12:
            hour += 12
        return f"{hour:02d}:{int(m.group(3) or 0):02d}"
    return None


def _norm_episode(text, ctx):
    m = _EP_RANGE.search(text)
    if m:
        return ",".join(str(n) for n in range(int(m.group(1)), int(m.group(2)) + 1))
    m = _EP_TOTAL.search(text)
    if m:
        return f"total:{m.group(1)}"
    if "첫" in text:
        return "1"
    if "최종" in text or "마지막" in text:
        return str(ctx.total) if ctx.total else "final"
    m = _EP_ONE.search(text)
    if m:
        return m.group(1)
    return None


def _norm_rating(text):
    m = re.search(r"([\d.]+)\s*%", text)
    if m:
        return m.group(1)
    m = re.search(r"(\d{1,2})세\s*이상", text)
    if m:
        return f"{m.group(1)}+"
    return None


def normalize_entities(entities, ctx: NormalizeContext):
    """Entity 리스트의 normalized 필드를 in-place로 채운다."""
    for e in entities:
        if e.tag == "DATE":
            e.normalized = _norm_date(e.text, ctx)
        elif e.tag == "TIME":
            e.normalized = _norm_time(e.text)
        elif e.tag == "EPISODE":
            e.normalized = _norm_episode(e.text, ctx)
        elif e.tag == "RATING":
            e.normalized = _norm_rating(e.text)
        elif e.tag == "PROGRAM" and ctx.is_title(e.text):
            e.normalized = ctx.title
        elif e.tag == "ACTOR" and e.text in ctx.plays:
            e.normalized = f"{e.text}({ctx.plays[e.text]} 역)"
        elif e.tag == "CHARACTER" and e.text in ctx.by_char:
            e.normalized = f"{e.text}({ctx.by_char[e.text]} 분)"
        elif e.tag == "BROADCASTER":
            e.normalized = e.text.upper() if e.text.isascii() else e.text
    return entities
