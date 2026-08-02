"""시계열 정렬(TA) 준비 데이터 생성 — **TA 모델 단계에서 호출** (UD 출력 아님).

협의: 정렬용 파생 데이터(정렬 키·서사 단위·회차 앵커)는 시계열 정렬 모델의
결과물에 속한다. UD의 ``ud_result.json``을 입력으로 받아 TA가 쓸 데이터를
생성하는 헬퍼로, udav1에 두되 structurize(UD 출력)에서는 호출하지 않는다.

    from udav1.analyze.ta_prep import build_temporal_alignment
    ta_input = build_temporal_alignment(ud_result)   # dict (ud_result.json 내용)
"""


def _find_characters(text, cast):
    return sorted({p["character"] for p in cast
                   if p.get("character") and p["character"] in text})


def build_temporal_alignment(ud_result: dict) -> dict:
    """ud_result(dict) -> TA 입력 블록 (타임코드 없음 — 의미 정렬용 키)."""
    cast = ud_result.get("cast") or []
    schedule = ud_result.get("schedule") or []
    episodes = ud_result.get("episodes") or []
    narratives = ud_result.get("episode_narratives") or []
    articles = ud_result.get("articles") or []

    characters = [{"character": p.get("character"), "actor": p.get("actor"),
                   "aliases": [x for x in (p.get("character"), p.get("actor")) if x],
                   "description": p.get("description")} for p in cast]

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
    for en in narratives:
        for no in en.get("episodes") or []:
            if no in anchors:
                anchors[no].setdefault("narratives", []).append(en.get("summary"))

    units, no = [], 0
    for en in narratives:
        no += 1
        units.append({"unit_id": f"u{no:03d}", "episodes": en.get("episodes"),
                      "text": en.get("summary"),
                      "characters": en.get("characters")
                      or _find_characters(en.get("summary") or "", cast),
                      "source": {"doc_id": en.get("source_doc"),
                                 "kind": "episode_summary"}})
    for art in articles:
        for fact in art.get("narrative_facts") or []:
            no += 1
            units.append({"unit_id": f"u{no:03d}", "episodes": None,
                          "text": fact,
                          "characters": _find_characters(fact, cast),
                          "source": {"doc_id": art.get("doc_id"),
                                     "kind": "article_narrative"}})

    match_terms = {}
    for tag in ("PROGRAM", "CHARACTER", "ACTOR", "LOCATION", "EVENT", "STAFF"):
        terms = set()
        for art in articles:
            terms.update((art.get("entities") or {}).get(tag) or [])
        if tag == "CHARACTER":
            terms.update(p["character"] for p in cast if p.get("character"))
        if tag == "ACTOR":
            terms.update(p["actor"] for p in cast if p.get("actor"))
        if tag == "PROGRAM" and (ud_result.get("program") or {}).get("title"):
            terms.add(ud_result["program"]["title"])
        if terms:
            match_terms[tag] = sorted(terms)

    return {
        "note": ("타임코드 미부여 — 씬 단위 의미 정렬용 데이터. "
                 "MMCA 씬/ASR과의 실제 정렬은 TA 모델이 수행"),
        "characters": characters,
        "episode_anchors": [anchors[k] for k in sorted(anchors)],
        "narrative_units": units,
        "match_terms": match_terms,
    }
