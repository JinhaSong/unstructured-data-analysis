"""udav2 P4 — 관계 추출 8종 (설계서 §4).

1차: 고신뢰 구조 소스 (cast/program_meta/schedule JSON 필드, 병기 패턴)
2차: 문장 공기(co-occurrence) 기반 — CHARACTER쌍(char_rel), CHARACTER-EVENT
     (involved_in). cross-encoder 관계 분류기는 M3에서 이 자리에 꽂는다.
"""
import re

from ..schema import Relation

_PLAYS_PAT = re.compile(r"([가-힣]{2,4})\s*\(\s*([가-힣A-Za-z]{2,10})\s*분\s*\)")
_SENT_SPLIT = re.compile(r"(?<=[.!?다요])\s+")


def relations_from_metadata(program_meta: dict | None, cast_data: dict | None,
                            schedule_data: dict | None) -> list:
    """구조화 수집 JSON 필드 -> 고신뢰(1.0) 관계."""
    rels = []
    p = (program_meta or {}).get("program") or {}
    title = p.get("title")

    for group in ("main_cast", "supporting_cast"):
        for person in (cast_data or {}).get(group) or []:
            ch, ac = person.get("character"), person.get("actor")
            if ch and ac:
                rels.append(Relation("plays", ac, "ACTOR", ch, "CHARACTER",
                                     doc_id="cast", source="metadata"))
            if ac and title:
                rels.append(Relation("appears_in", ac, "ACTOR", title, "PROGRAM",
                                     doc_id="cast", source="metadata"))
    if title:
        for d in p.get("directors") or []:
            rels.append(Relation("directed_by", title, "PROGRAM", d, "STAFF",
                                 doc_id="program_meta", source="metadata"))
        for w in p.get("writers") or []:
            rels.append(Relation("written_by", title, "PROGRAM", w, "STAFF",
                                 doc_id="program_meta", source="metadata"))
        if p.get("channel"):
            rels.append(Relation("aired_on", title, "PROGRAM",
                                 p["channel"], "BROADCASTER",
                                 doc_id="program_meta", source="metadata"))
        for c in p.get("production_companies") or []:
            rels.append(Relation("produced_by", title, "PROGRAM", c, "PRODUCTION",
                                 doc_id="program_meta", source="metadata"))
    for ent in (schedule_data or {}).get("entries") or []:
        if ent.get("episode_no") and ent.get("date"):
            when = f"{ent['date']} {ent.get('start', '')}".strip()
            rels.append(Relation(
                "scheduled_at", f"{ent['episode_no']}회", "EPISODE", when, "DATE",
                doc_id="schedule", evidence=ent.get("note"), source="metadata"))
    return rels


def relations_from_text(doc_id: str, text: str, entities: list) -> list:
    """문서 텍스트 + NER 결과 -> plays(병기 패턴)·char_rel·involved_in."""
    rels = []
    for m in _PLAYS_PAT.finditer(text):
        rels.append(Relation("plays", m.group(2), "ACTOR", m.group(1), "CHARACTER",
                             doc_id=doc_id, evidence=m.group(0), source="rule"))

    by_sent = {}
    offset = 0
    for sent in _SENT_SPLIT.split(text):
        span = (offset, offset + len(sent))
        chars = sorted({e.text for e in entities
                        if e.tag == "CHARACTER" and e.start is not None
                        and span[0] <= e.start < span[1]})
        events = sorted({e.text for e in entities
                         if e.tag == "EVENT" and e.start is not None
                         and span[0] <= e.start < span[1]})
        if chars or events:
            by_sent[sent.strip()] = (chars, events)
        offset += len(sent) + 1

    for sent, (chars, events) in by_sent.items():
        for i in range(len(chars)):
            for j in range(i + 1, len(chars)):
                rels.append(Relation("char_rel", chars[i], "CHARACTER",
                                     chars[j], "CHARACTER", doc_id=doc_id,
                                     evidence=sent[:120], score=0.6,
                                     source="cooccurrence"))
            for ev in events:
                rels.append(Relation("involved_in", chars[i], "CHARACTER",
                                     ev, "EVENT", doc_id=doc_id,
                                     evidence=sent[:120], score=0.6,
                                     source="cooccurrence"))
    return rels


def dedup(relations: list) -> list:
    seen, out = set(), []
    for r in sorted(relations, key=lambda r: -r.score):
        key = (r.rel, r.head, r.tail)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
