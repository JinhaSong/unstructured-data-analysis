"""udav2 P3 — 방송 도메인 NER (18종, 설계서 §3).

3층 구조 (우선순위 높은 순):
  1. rule      정규식 — 배역(배우 분) 병기, 회차, 시청률·등급, ISO 날짜, 시각
  2. gazetteer 프로그램 메타·출연진에서 구축한 도메인 사전 (ACTOR/CHARACTER/...)
  3. model     monologg/koelectra-base-v3-naver-ner (Apache-2.0) — 일반 개체
               Naver NER 14종 -> 도메인 태그 매핑, 겹치는 스팬은 상위 층이 이김

학습 없이 기존 공개 모델 + 도메인 지식으로 동작. (KoELECTRA 파인튜닝은 M2에서
골드셋 구축 후 — 이 모듈의 인터페이스는 그대로 유지된다.)
"""
import re

from ..schema import Entity

MODEL_ID = "monologg/koelectra-base-v3-naver-ner"   # Apache-2.0

# Naver NER -> 도메인 태그 (해당 없음 -> None = 폐기)
_NAVER_MAP = {
    "PER": "PERSON", "ORG": "ORGANIZATION", "LOC": "LOCATION",
    "DAT": "DATE", "TIM": "TIME", "EVT": "EVENT", "NUM": "QUANTITY",
    "AFW": "PROGRAM",   # artifacts/works — 작품명
    "ANM": None, "FLD": None, "CVL": None, "PLT": None, "MAT": None, "TRM": None,
}

_RULES = (
    # 한비수(이민기 분) — CHARACTER + ACTOR 병기 패턴 (그룹별 태그)
    (re.compile(r"([가-힣]{2,4})\s*\(\s*([가-힣A-Za-z]{2,10})\s*분\s*\)"),
     (("CHARACTER", 1), ("ACTOR", 2))),
    ((re.compile(r"(\d{1,3}\s*부작|\d{1,3}\s*회|첫\s*회|최종회|마지막\s*회)")),
     (("EPISODE", 1),)),
    (re.compile(r"(시청률\s*\d{1,2}(?:\.\d+)?\s*%|\d{1,2}(?:\.\d+)?\s*%\s*\(AGB[^)]*\)|\d{1,2}세\s*이상\s*시청가)"),
     (("RATING", 1),)),
    (re.compile(r"(\d{4}-\d{2}-\d{2}|\d{4}년\s*\d{1,2}월\s*\d{1,2}일)"),
     (("DATE", 1),)),
    (re.compile(r"(\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2}|(?:오전|오후|밤|저녁)\s*\d{1,2}시(?:\s*\d{1,2}분)?)"),
     (("TIME", 1),)),
)

_STATIC_GAZ = {
    "BROADCASTER": ("MBC", "KBS", "KBS2", "SBS", "tvN", "JTBC", "ENA",
                    "채널A", "MBN", "OCN", "MBC충북"),
    "PLATFORM": ("넷플릭스", "웨이브", "티빙", "디즈니+", "쿠팡플레이",
                 "왓챠", "iQIYI", "iQIYI International"),
    "GENRE": ("로맨스", "로맨틱 코미디", "로코", "코미디", "멜로", "스릴러",
              "판타지", "사극", "미니시리즈", "예능", "다큐멘터리"),
}


def build_gazetteer(program_meta: dict | None = None,
                    cast_data: dict | None = None) -> dict:
    """수집 메타데이터 -> {surface: tag}. 긴 표면형 우선 매칭을 위해 정렬은 조회 시."""
    gaz = {}
    for tag, terms in _STATIC_GAZ.items():
        for t in terms:
            gaz[t] = tag
    p = (program_meta or {}).get("program") or program_meta or {}
    title = p.get("title")
    if title:
        gaz[title] = "PROGRAM"
        gaz[title.replace(" ", "")] = "PROGRAM"
        gaz[f"《{title}》"] = "PROGRAM"
        if p.get("title_en"):
            gaz[p["title_en"]] = "PROGRAM"
    for d in p.get("directors") or []:
        gaz[d] = "STAFF"
    for w in p.get("writers") or []:
        gaz[w] = "STAFF"
    for c in p.get("production_companies") or []:
        gaz[c] = "PRODUCTION"
    if p.get("channel"):
        gaz[p["channel"]] = "BROADCASTER"
    for g in p.get("categories") or []:
        gaz.setdefault(g, "GENRE")
    for group in ("main_cast", "supporting_cast"):
        for person in (cast_data or {}).get(group) or []:
            if person.get("character"):
                gaz[person["character"]] = "CHARACTER"
            if person.get("actor"):
                gaz[person["actor"]] = "ACTOR"
    return gaz


def _rule_entities(text):
    out = []
    for pattern, groups in _RULES:
        for m in pattern.finditer(text):
            for tag, gi in groups:
                if m.group(gi):
                    out.append((m.start(gi), m.end(gi), tag, m.group(gi), 1.0, "rule"))
    return out


def _gaz_entities(text, gaz):
    out = []
    # 긴 표면형부터 — '오! 주인님'이 '주인' 등 부분어에 잠식되지 않게
    for surface in sorted(gaz, key=len, reverse=True):
        start = 0
        while True:
            idx = text.find(surface, start)
            if idx < 0:
                break
            out.append((idx, idx + len(surface), gaz[surface], surface, 1.0, "gazetteer"))
            start = idx + len(surface)
    return out


class DomainNER:
    """3층 NER. 모델 로드는 지연 — use_model=False면 규칙+사전만으로 동작."""

    def __init__(self, gazetteer: dict | None = None, use_model: bool = True):
        self.gaz = gazetteer or {}
        self.use_model = use_model
        self._pipe = None

    def _model_pipe(self):
        if self._pipe is None:
            from transformers import (AutoModelForTokenClassification,
                                      AutoTokenizer, pipeline)
            model = AutoModelForTokenClassification.from_pretrained(MODEL_ID)
            # 이 모델의 라벨은 'PER-B' 접미사식 — HF aggregation은 'B-PER'
            # 접두사식만 인식하므로 로드 시 표준형으로 변환한다.
            id2label = {}
            for i, label in model.config.id2label.items():
                if "-" in label:
                    tag, bi = label.rsplit("-", 1)
                    label = f"{bi}-{tag}"
                id2label[i] = label
            model.config.id2label = id2label
            model.config.label2id = {v: k for k, v in id2label.items()}
            self._pipe = pipeline(
                "token-classification", model=model,
                tokenizer=AutoTokenizer.from_pretrained(MODEL_ID),
                aggregation_strategy="simple")
        return self._pipe

    _TRIM = "'\"“”‘’()《》〈〉[]·…,.!? \t"

    def _model_entities(self, text):
        out = []
        for ent in self._model_pipe()(text):
            tag = _NAVER_MAP.get(ent["entity_group"])
            if not tag:
                continue
            start, end = ent["start"], ent["end"]
            # 서브워드 병합 잔재(따옴표·괄호·한 글자 조각) 정리
            while start < end and text[start] in self._TRIM:
                start += 1
            while end > start and text[end - 1] in self._TRIM:
                end -= 1
            surface = text[start:end]
            if len(surface) < 2:
                continue
            out.append((start, end, tag, surface,
                        float(ent["score"]), f"model:{MODEL_ID.split('/')[-1]}"))
        return out

    def extract(self, text: str, doc_id: str, seg_id: str | None = None):
        """텍스트 1개 -> list[Entity]. 겹침은 rule > gazetteer > model, 긴 스팬 우선."""
        candidates = _rule_entities(text) + _gaz_entities(text, self.gaz)
        if self.use_model and text.strip():
            candidates += self._model_entities(text)
        prio = {"rule": 0, "gazetteer": 1}
        candidates.sort(key=lambda c: (prio.get(c[5], 2), -(c[1] - c[0]), c[0]))
        taken, ents = [], []
        for start, end, tag, surface, score, source in candidates:
            if any(start < e and end > s for s, e in taken):
                continue
            taken.append((start, end))
            ents.append(Entity(tag=tag, text=surface, doc_id=doc_id, seg_id=seg_id,
                               start=start, end=end, score=round(score, 4),
                               source=source))
        ents.sort(key=lambda e: e.start)
        return ents
