# udav1 — Unstructured Data Analysis

방송·미디어 **비정형 데이터 분석** 모듈. 큐시트·대본·편성표·자막·기사 등을
파싱해 하나의 정규 스키마로 만들고, 방송 도메인 개체·관계·요약을 붙여
**단일 JSON(`ud_result.json`)** 으로 구조화한다. LLM 미사용.

상위 `specialized-metadata` 파이프라인의 UD 단계로 소비되며(서브모듈
`libs/ud/udav1`), 출력은 TA(시계열 정렬) 단계의 입력이 된다.

- **v1**(원 모듈): 포맷별 파서 + 추출 요약 + ASR 타임코드 이식 → `UDResult`
- **v2**(현행 기본 경로, `structurize.py`): txt 입력 → 도메인 NER·정규화·정제·
  생성요약 → **`ud_result.json`** (아래 [최종 출력 포맷](#최종-출력-포맷--ud_resultjson))

---

## 최종 출력 포맷 — `ud_result.json`

`python -m udav1.structurize <데이터 디렉토리>` 의 산출물. 입력은
`<데이터 디렉토리>/raw/*.txt`(유형 접두어 파일명), 출력은
`<데이터 디렉토리>/output/ud_result.json` **단일 파일**이다.
타임코드는 부여하지 않는다(정렬은 TA 소관).

### 최상위 구조 (11 키, 고정)

```jsonc
{
  "content_id": "MBC_오!주인님",          // = 데이터 디렉토리명
  "program":    { ... } | null,           // 프로그램 메타 (program_meta_*.txt)
  "cast":       [ ... ],                  // 인물 (cast_*.txt)
  "schedule":   [ ... ],                  // 편성 (schedule_*.txt)
  "episodes":   [ ... ],                  // 회차 정보 (episodes_*.txt)
  "synopsis":   { ... } | null,           // 시놉시스 (synopsis_*.txt)
  "episode_narratives": [ ... ],          // 회차 서사 (episode_summary_*.txt)
  "articles":   [ ... ],                  // 기사 다이제스트 (article_*.txt)
  "relations":  [ ... ],                  // 교차 문서 관계 9종
  "documents":  [ ... ],                  // 입력 문서 색인 (원본 추적)
  "models":     { ... }                   // 사용 모델·라이선스
}
```

키 집합은 입력 구성과 무관하게 **항상 동일**하다. 해당 유형의 입력이 없으면
빈 리스트 `[]` 또는 `null`이 된다(예: 뉴스데스크는 `cast: []`, `program: null`).

### 각 필드의 실제 형태

```jsonc
"program": {                              // program_meta_*.txt 의 "키: 값" 파싱
  "title": "오! 주인님", "title_en": "Oh My Ladylord", "channel": "MBC",
  "timeslot": "수목 21:20~22:30", "episodes_total": 16, "genre": "드라마",
  "categories": ["로맨스","코미디"],
  "directors": ["오다영"], "writers": ["조진국"],
  "production_companies": ["넘버쓰리픽쳐스"], "distribution": [...],
  "broadcast_period": {"start": "2021-03-24", "end": "2021-05-13"}
}

"cast": [                                 // 정규식 `배역 (배우 분) [역할군] [N세] — 설명`
  {"character": "한비수", "actor": "이민기", "age": "36",
   "role_group": "주연", "description": "스릴러 드라마 작가. 연애를 '안' 하는 남자"}
]

"schedule": [                             // `N회 | 날짜 (요일) | 시각 | 구분 | ※ 비고`
  {"episode_no": 2, "date": "2021-03-25", "day": "목",
   "start": "22:00", "end": "23:10", "broadcast_type": "본방송",
   "note": "축구 국가대표 평가전(한일전) 중계로 편성 변경"}
]

"episodes": [ {"episode_no": 1, "date": "2021-03-24", "rating": 2.1} ]

"synopsis": { "logline": "...", "planning_intent": ["...", "..."] }

"episode_narratives": [                   // 회차별 서사 + 등장 배역(NER 추출)
  {"episodes": [1], "summary": "드라마 작가 한비수(이민기 분)와 …",
   "characters": ["오주인","한비수"], "source_doc": "episode_summary_001"}
]

"articles": [                             // 기사 1건 = 헤더 + 요약 + 서사문장 + 개체
  {"doc_id": "article_003", "title": "...", "press": "한국강사신문",
   "published_at": "2021.03.31 10:04", "source_url": "https://...",
   "summary": "…KoBART 생성 요약(서사 사실 문장만 입력)…",
   "narrative_facts": ["…", "…"],                    // refine.py 문장 분류 결과
   "entities": {"CHARACTER": ["오주인","한비수"], "DATE": ["2021-03-31"], ...}}
]

"relations": [                            // RELATION_TYPES 9종
  {"rel": "plays", "head": "이민기", "head_tag": "ACTOR",
   "tail": "한비수", "tail_tag": "CHARACTER",
   "doc_id": "cast", "evidence": null, "score": 1.0, "source": "metadata"}
]

"documents": [                            // 입력 추적 색인 (본문 아님)
  {"doc_id": "article_001", "doc_type": "article",
   "source_file": "raw/article_001.txt", "n_segments": 11, "n_entities": 79}
]

"models": {
  "ner": "monologg/koelectra-base-v3-naver-ner (Apache-2.0) + domain gazetteer/rules",
  "normalization": "rule (normalize.py)",
  "sentence_refine": "rule-v1 (refine.py)",
  "summarization": "gogamza/kobart-summarization (MIT)"    // --no-summary 시 null
}
```

### 스키마 계약과 참조

- 내부 dataclass 정의는 [schema.py](schema.py): `CanonicalDocument`/`Segment`
  (파싱 계약), `Entity`(NER 스팬 — `tag`·문자 오프셋·`source`·`normalized`),
  `Relation`(head/tail + 근거·신뢰도). 위 JSON은 `structurize.build_ud_result()`가
  이 객체들로부터 조립한다.
- `NER_TAGS` 18종, `RELATION_TYPES` 9종, `DOC_TYPES_V2` 13종도 schema.py에 고정.

### ⚠️ 확정되지 않은 부분 (변경 예정)

**최상위 11키와 위 필드 형태는 안정적이지만, 아래는 확장이 필요하다.**

1. **실무 문서 유형이 본문에 노출되지 않는다.** `build_ud_result()`는
   `episode_info / synopsis / episode_summary / article` 4종만 최상위로 펼친다.
   **`cuesheet`·`subtitle_script`·`narration`(대본)은 파싱·개체추출까지 수행되지만
   결과가 `documents` 색인의 카운트로만 남고 본문·개체는 출력에서 누락**된다.

   | 프로그램 | 미노출 문서 | 유형 |
   |---|---|---|
   | 뉴스데스크 | 3건 | cuesheet |
   | 충북시사토론창 | 5건 | cuesheet, narration, subtitle_script |
   | 프라임인터뷰 | 3건 | cuesheet, narration, subtitle_script |
   | 생활력 / 인생내컷 | 각 1건 | subtitle_script |

   → MBC충북 실무 문서(대본 157·자막 49·큐시트 609)가 본격 투입되면
   `cuesheets` / `scripts` / `subtitles` 최상위 키 추가가 **필요**하다.
   이때 기존 11키는 유지되므로 **하위호환 확장**이 된다.
2. `articles[].entities`는 태그별 표면형 집합으로 축약돼 있어 오프셋·신뢰도가
   빠진다. 개체 원본이 필요하면 스키마 확장 또는 문서별 출력 부활이 필요.
3. 모델 교체 시 `models` 값 문자열은 바뀐다(키는 고정).

---

## Architecture

```
ingest/ (Layer 1)        normalize/            analyze/ (Layer 2)
 txt  CP949/UTF-8-BOM ─┐                        segment  (kiwipiepy | regex)
 xlsx cuesheet         ├─> RawDoc ─> Canonical ─ align    (subtitle <-> ASR time)  P2
 xml  clipInfo         │            Document    window    (item/turn/gap/fixed)   P3
 pdf  docling|plumber  │            (contract)  summarize (extractive, MMR)       P4
 hwp  hwplib(JPype)   ─┘                              └─> UDResult (time-coded)
```

- **CanonicalDocument** ([schema.py](schema.py)) is the only contract between
  layers: new formats add parsers only; new models add analyzers only.
- **Summaries are extractive** (original sentences picked by centroid+MMR):
  deterministic, traceable (`source_seg_ids`), zero hallucination.
  - Tier A (default): pure-python TF-IDF — no downloads, CPU only
  - Tier B (optional): `sentence-transformers` + `BAAI/bge-m3` (MIT weights)

## Document types (from 비정형 수집 데이터 목록)

| doc_type | 예 | 포맷 | 타임코드 |
|---|---|---|---|
| `cuesheet` | 뉴스/토론/인터뷰 큐시트 | xlsx/pdf/hwp | ✅ 누적 TC → start/end |
| `narration` | 대본/나레이션 원고 | pdf/hwp | ❌ |
| `subtitle_script` | 자막(CP949) / 기사원고(UTF-8-BOM) | txt | ❌ → **ASR 정렬로 부여** |
| `schedule` | 편성표 (샘플 미확보) | TBD | TBD |
| `clip_meta` | 영상 아카이브 메타 | .mp4.xml | DUR/DURTC |

## Usage

```bash
pip install -r requirements.txt          # all optional; core runs stdlib-only

# standalone (from the directory containing udav1/, e.g. libs/ud)
python -m udav1 path/to/큐시트.xlsx --type cuesheet
python -m udav1 path/to/자막.txt --asr asr-transcript.json
```

```python
from udav1 import analyze_path
result = analyze_path("자막.txt", asr_segments=asr["segments"])
result.time_coded_summaries   # [{start, end, summary, source_seg_ids, ...}]
```

## HWP support

`.hwp` needs the vendored **hwplib** (Apache-2.0, `libs/hwplib` submodule):

```bash
git submodule update --init
cd libs/hwplib && mvn -q package        # or: export UDA_HWPLIB_JAR=/path/to.jar
pip install jpype1                       # + a JVM
```

Fallback: LibreOffice (`soffice`) headless conversion if hwplib/JVM is absent.

## Licenses (commercial-safe by policy)

All dependencies are MIT / Apache-2.0 / BSD / LGPL(dynamic).
Rejected for license reasons: pyhwp(GPL), PyMuPDF(AGPL),
marker-pdf(GPL + OpenRAIL-M $2M cap), konlpy(GPL), EXAONE(non-commercial).

## Tests

```bash
python -m unittest discover -s tests -v   # stdlib-only smoke tests
```
