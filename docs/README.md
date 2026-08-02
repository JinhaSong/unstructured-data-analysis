# udav1 문서 — 비정형 데이터 분석 모델

`udav1`(Unstructured Data Analysis v1)과 차기 확장 `udav2`(BERT급 언어모델 기반
구조화·분석)에 대한 설계·조사 문서 모음.

## 문서 목록

| 문서 | 내용 | 상태 |
|---|---|---|
| [ud-analysis-model-design.md](ud-analysis-model-design.md) | **udav2 설계서** — 비-LLM(BERT급~sub-LLM) 구조화 모델: 문서분류·도메인 NER 18종·관계추출·생성요약·검증. 협의 결정 반영 | **확정 — 구현 기준 문서** |
| [web-parsing-related-work.md](web-parsing-related-work.md) | 웹 비정형 파싱 기존연구 조사 (본문추출·IE·NER·요약·페어링) | 참고 — LLM 옵션(§5, 옵션 B/C)은 협의 결과 **미채택**(비-LLM 결정) |

## 현행 udav1 요약 (v1 — 방송사 실무 문서 기반)

```
ingest/ (파서)          normalize/           analyze/
 txt  CP949/UTF-8-BOM ─┐                      segment  (kiwipiepy | regex)
 xlsx 큐시트            ├─> RawDoc ─> Canonical┼ align   (자막 ↔ ASR 타임코드 이식)
 xml  clipInfo         │           Document   ┼ window  (item/turn/gap/fixed)
 pdf  docling|plumber  │           (계약)      └ summarize (추출 요약, centroid+MMR)
 hwp  hwplib(JPype)   ─┘                            └─> UDResult (time-coded)
```

- **처리 대상**: 큐시트 / 나레이션 원고·대본 / 자막·기사원고(txt) / 편성표 / 영상 메타(xml)
- **계약**: `CanonicalDocument`(schema.py)가 ingest↔analyze 사이의 유일한 계약
- **요약**: 추출식(원문 문장 선택) — 결정적, 근거 추적(`source_seg_ids`)
- **타임코드**: 큐시트는 자체 TC, 자막은 ASR 정렬(P2)로 부여 → 시계열 정렬(TA)의 입력

## udav2 방향 (확정 — 연구계획서 1차년도 대응)

연구계획서(붙임4-1)의 "비정형 데이터(자막·대본·편성표 등) 구조화 정의(인물·서사 등)
및 의미 정보 분석·추출"을 담당. **LLM 미사용, BERT급~sub-LLM**으로:

- 문서 유형 분류 + 방송 도메인 NER 18종 + 관계 추출 8종(배역-배우, 인물관계 등)
- 생성 요약(KoBART/KE-T5 벤치) + bge-m3 임베딩 + 검증 레이어
- 출력: `CanonicalDocument` 확장(entities/relations/summary) → 시계열 정렬(TA) 입력

프로토타입 입력: `examples/ud/MBC_오!주인님/` (편성표+부가정보+ASR 전사) +
기존 MBC충북 실무 문서 샘플(대본·큐시트 파서 검증용).
MMCA 페어링: `examples/mmca/MBC_2021-00-01-오!주인님1회/`.
세부는 [ud-analysis-model-design.md](ud-analysis-model-design.md) 참조.
