"""udav2 오케스트레이터: txt 수집 디렉토리 -> 동일 형식 JSON 정제.

    python -m udav1.structurize examples/ud/MBC_오!주인님

입력 가정(협의 확정): 모든 입력은 텍스트만 추출된 **txt** 파일로 들어온다.
방송사별 원천 포맷 차이는 ingest/txt_meta.py의 파서 레지스트리에서 흡수한다.

파이프라인: parse_txt -> DomainNER(3층) -> 정규화(normalize) -> 문장 정제(refine,
기사류) -> 요약(KoBART, 기사·시놉시스) -> 관계 추출 -> 문서별 동일 형식 JSON
(output/docs/<doc_id>.json) + 프로그램 번들(output/structured_result.json).

범위 제외(협의): ASR 전사는 MMCA 산출물이므로 UD에서 수행·소비하지 않는다
(자막 txt가 별도 제공되면 subtitle/*.txt로 투입). 회차 정렬·씬 정렬은
시계열 정렬(TA) 모듈 담당.
"""
import argparse
import glob
import json
import os

from .analyze.ner import DomainNER, MODEL_ID as NER_MODEL, build_gazetteer
from .analyze.normalize import NormalizeContext, normalize_entities
from .analyze.refine import refine_article
from .analyze.relations import (dedup, relations_from_metadata,
                                relations_from_text)
from .ingest.txt_meta import parse_txt

_SUMMARIZE_TYPES = {"synopsis", "article"}
_SKIP_NAMES = {"rawdata.txt", "readme.txt"}
_SKIP_DIRS = {"output"}


def _collect_inputs(data_dir):
    """원본은 <data_dir>/raw/ 에 유형 접두어 파일명(article_*, schedule_*,
    cast_*, ...)으로 저장된다. raw/가 없으면 하위 전체에서 재귀 수집(과거 배치
    호환). 자막(ASR)은 MMCA 산출물이라 raw에 두지 않는 것이 규약."""
    raw_dir = os.path.join(data_dir, "raw")
    if os.path.isdir(raw_dir):
        paths = sorted(glob.glob(os.path.join(raw_dir, "*.txt")))
    else:
        paths = sorted(glob.glob(os.path.join(data_dir, "**", "*.txt"),
                                 recursive=True))
    out = []
    for p in paths:
        rel = os.path.relpath(p, data_dir)
        parts = rel.split(os.sep)
        if parts[0].lower() in _SKIP_DIRS or parts[-1].lower() in _SKIP_NAMES:
            continue
        out.append(p)
    return out


def _rebuild_metadata(docs):
    """파싱된 문서에서 관계 추출·사전 구축용 dict를 복원한다."""
    program, cast, schedule = {}, {}, {}
    for doc in docs:
        if doc.doc_type == "program_meta":
            f = dict(doc.program_meta.get("fields") or {})
            bp = f.pop("broadcast_period", None)
            if isinstance(bp, str) and "~" in bp:
                s, e = [x.strip() for x in bp.split("~", 1)]
                f["broadcast_period"] = {"start": s, "end": e}
            if str(f.get("episodes_total", "")).isdigit():
                f["episodes_total"] = int(f["episodes_total"])
            program = {"program": f}
        elif doc.doc_type == "cast_info":
            for seg in doc.segments:
                if not seg.raw:
                    continue
                key = ("main_cast" if seg.raw.get("role_group") == "주연"
                       else "supporting_cast")
                cast.setdefault(key, []).append(seg.raw)
        elif doc.doc_type == "schedule":
            schedule = {"entries": [s.raw for s in doc.segments if s.raw]}
    return program, cast, schedule


def _entities_by_seg(entities):
    by = {}
    for e in entities:
        by.setdefault(e.seg_id, []).append(e)
    return by


def build_ud_result(data_dir, docs, per_doc, relations, program_fields,
                    cast_data, schedule_data):
    """UD 최종 산출 — 비정형 데이터 정보를 구조화해 담은 **단일 JSON**.

    타임코드는 부여하지 않는다(협의). 대신 시계열 정렬(TA) 모듈이 씬 단위
    의미 정렬에 쓸 수 있는 키·단위를 ``temporal_alignment`` 블록에 담는다.
    """
    content_id = os.path.basename(os.path.normpath(data_dir))

    # ── 구조화 정보 (유형별) ──
    cast = [p for g in ("main_cast", "supporting_cast")
            for p in cast_data.get(g) or []]
    schedule = (schedule_data or {}).get("entries") or []
    episodes, synopsis, episode_narratives, articles = [], {}, [], []

    for doc, info in zip(docs, per_doc):
        ents_by_seg = _entities_by_seg(info["entities"])
        if doc.doc_type == "episode_info":
            episodes = [s.raw for s in doc.segments if s.raw]
        elif doc.doc_type == "synopsis":
            for s in doc.segments:
                if s.kind == "logline":
                    synopsis["logline"] = s.text
                else:
                    synopsis.setdefault("planning_intent", []).append(s.text)
        elif doc.doc_type == "episode_summary":
            for s in doc.segments:
                if not s.raw:
                    continue
                chars = sorted({e.text for e in ents_by_seg.get(s.seg_id, [])
                                if e.tag == "CHARACTER"})
                episode_narratives.append(
                    {**s.raw, "characters": chars, "source_doc": doc.doc_id})
        elif doc.doc_type == "article":
            hdr = doc.program_meta
            uniq = {}
            for e in info["entities"]:
                uniq.setdefault(e.tag, set()).add(e.normalized or e.text)
            articles.append({
                "doc_id": doc.doc_id,
                "title": hdr.get("title"), "press": hdr.get("press"),
                "published_at": hdr.get("published_at"),
                "source_url": hdr.get("source_url"),
                "summary": (info["summary"] or {}).get("text"),
                "narrative_facts": [n["text"] for n in
                                    (info["refined"] or {}).get("narrative", [])],
                "entities": {t: sorted(v) for t, v in sorted(uniq.items())},
            })

    # ── 시계열 정렬(TA) 활용 데이터 ──
    narrative_units, unit_no = [], 0
    for en in episode_narratives:
        unit_no += 1
        narrative_units.append({
            "unit_id": f"u{unit_no:03d}", "episodes": en.get("episodes"),
            "text": en.get("summary"), "characters": en.get("characters"),
            "source": {"doc_id": en.get("source_doc"), "kind": "episode_summary"}})
    for doc, info in zip(docs, per_doc):
        if doc.doc_type != "article":
            continue
        ents_by_seg = _entities_by_seg(info["entities"])
        ep_hints = sorted({int(n) for e in info["entities"]
                           if e.tag == "EPISODE" and e.normalized
                           and not e.normalized.startswith(("total", "final"))
                           for n in e.normalized.split(",") if n.isdigit()})
        for n in (info["refined"] or {}).get("narrative", []):
            unit_no += 1
            segs = ents_by_seg.get(n["seg_id"], [])
            narrative_units.append({
                "unit_id": f"u{unit_no:03d}",
                "episodes": ep_hints or None,
                "text": n["text"],
                "characters": sorted({e.text for e in segs
                                      if e.tag == "CHARACTER"}),
                "events": sorted({e.text for e in segs if e.tag == "EVENT"}),
                "source": {"doc_id": doc.doc_id, "seg_id": n["seg_id"],
                           "kind": "article_narrative"}})

    anchors = {}
    for ent in schedule:
        no = ent.get("episode_no")
        if no:
            anchors[no] = {"episode_no": no, "air_date": ent.get("date"),
                           "day": ent.get("day"), "start": ent.get("start"),
                           "end": ent.get("end"), "note": ent.get("note")}
    for ep in episodes:
        no = ep.get("episode_no")
        if no:
            anchors.setdefault(no, {"episode_no": no})
            anchors[no].setdefault("air_date", ep.get("date"))
            if ep.get("rating") is not None:
                anchors[no]["rating"] = ep.get("rating")
    for en in episode_narratives:
        for no in en.get("episodes") or []:
            if no in anchors:
                anchors[no].setdefault("narratives", []).append(en["summary"])

    all_entities = [e for info in per_doc for e in info["entities"]]
    match_terms = {}
    for tag in ("PROGRAM", "CHARACTER", "ACTOR", "LOCATION", "EVENT", "STAFF"):
        terms = sorted({e.text for e in all_entities if e.tag == tag})
        if terms:
            match_terms[tag] = terms

    return {
        "content_id": content_id,
        "program": program_fields or None,
        "cast": cast,
        "schedule": schedule,
        "episodes": episodes,
        "synopsis": synopsis or None,
        "episode_narratives": episode_narratives,
        "articles": articles,
        "relations": [r.to_dict() for r in relations],
        "temporal_alignment": {
            "note": ("타임코드 미부여(협의) — 씬 단위 의미 정렬용 데이터. "
                     "MMCA 씬/ASR과의 실제 정렬은 TA 모듈이 수행"),
            "characters": [{"character": p.get("character"),
                            "actor": p.get("actor"),
                            "aliases": [x for x in (p.get("character"),
                                                    p.get("actor")) if x],
                            "description": p.get("description")} for p in cast],
            "episode_anchors": [anchors[k] for k in sorted(anchors)],
            "narrative_units": narrative_units,
            "match_terms": match_terms,
        },
        "documents": [{"doc_id": d.doc_id, "doc_type": d.doc_type,
                       "source_file": os.path.relpath(d.source_path, data_dir),
                       "n_segments": len(d.segments),
                       "n_entities": len(info["entities"])}
                      for d, info in zip(docs, per_doc)],
        "models": {
            "ner": f"{NER_MODEL} (Apache-2.0) + domain gazetteer/rules",
            "normalization": "rule (normalize.py)",
            "sentence_refine": "rule-v1 (refine.py)",
            "summarization": "gogamza/kobart-summarization (MIT)",
        },
    }


def structurize_dir(data_dir: str, use_model: bool = True,
                    summarize: bool = True) -> dict:
    paths = _collect_inputs(data_dir)
    docs = [parse_txt(p) for p in paths]
    program_meta, cast_data, schedule_data = _rebuild_metadata(docs)

    fields = program_meta.get("program") or {}
    plays = {}
    for group in ("main_cast", "supporting_cast"):
        for person in cast_data.get(group) or []:
            if person.get("actor") and person.get("character"):
                plays[person["actor"]] = person["character"]
    ctx = NormalizeContext(
        program_title=fields.get("title"),
        title_variants=[v for v in (fields.get("title_en"),) if v],
        year=(fields.get("broadcast_period") or {}).get("start", "")[:4] or None,
        episodes_total=fields.get("episodes_total"),
        plays=plays)

    ner = DomainNER(gazetteer=build_gazetteer(program_meta, cast_data),
                    use_model=use_model)

    per_doc = []
    all_rels = relations_from_metadata(program_meta, cast_data, schedule_data)

    for doc in docs:
        entities = []
        for seg in doc.segments:
            for e in ner.extract(seg.text, doc.doc_id, seg.seg_id):
                if seg.text[e.start:e.end] == e.text:   # grounding 검증
                    entities.append(e)
        normalize_entities(entities, ctx)

        refined = None
        if doc.doc_type == "article":
            _classes, refined = refine_article(doc.segments, entities)

        summary = None
        if summarize and doc.doc_type in _SUMMARIZE_TYPES and doc.full_text.strip():
            from .analyze.summarize_gen import summarize_long
            # 기사류는 서사 사실 문장만 요약 입력으로 사용 (정제 효과 반영).
            # 서사 문장이 없으면(뉴스 원고 등) 섹션 마커([앵커멘트] 등)를 뺀
            # 본문을 공백 연결로 투입 — 방송 원고의 구 단위 줄바꿈 보정.
            if refined and refined["narrative"]:
                src_text = " ".join(n["text"] for n in refined["narrative"])
            else:
                src_text = " ".join(
                    s.text for s in doc.segments
                    if s.kind != "title" and not s.text.startswith("["))
            gen = summarize_long(src_text)
            summary = {"text": gen["summary"], "model": gen["model"],
                       "input": "narrative_fact" if refined else "full_text"}

        all_rels.extend(relations_from_text(doc.doc_id, doc.full_text, entities))
        per_doc.append({"entities": entities, "summary": summary,
                        "refined": refined})

    return build_ud_result(data_dir, docs, per_doc, dedup(all_rels),
                           fields, cast_data, schedule_data)


def main():
    ap = argparse.ArgumentParser(description="udav2 구조화 분석 (txt 입력)")
    ap.add_argument("data_dir")
    ap.add_argument("--out-dir", default=None,
                    help="기본: <data_dir>/output")
    ap.add_argument("--no-model", action="store_true", help="규칙+사전만 사용")
    ap.add_argument("--no-summary", action="store_true")
    args = ap.parse_args()

    result = structurize_dir(args.data_dir, use_model=not args.no_model,
                             summarize=not args.no_summary)
    out_dir = args.out_dir or os.path.join(args.data_dir, "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "ud_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    ta = result["temporal_alignment"]
    print(f"[udav2] docs={len(result['documents'])} "
          f"entities={sum(d['n_entities'] for d in result['documents'])} "
          f"relations={len(result['relations'])} "
          f"ta_units={len(ta['narrative_units'])} "
          f"anchors={len(ta['episode_anchors'])} -> {out_path}")


if __name__ == "__main__":
    main()
