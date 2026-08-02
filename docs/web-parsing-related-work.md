# 웹 비정형 데이터 파싱 모델 — 기존연구 정리

> 목적: 웹 비정형 데이터(기사·시놉시스·인물 정보 등)의 파싱·분석 모델을 설계하기 위한
> 기술 지형 정리. 프로토타입(오!주인님) 구현 옵션 결정의 근거 문서.
> 작성: 2026-08. 라이선스 표기는 과제 조건(Apache 2.0 / MIT / BSD 계열 한정, 결과물 MIT) 관점.

## 0. 문제 정의

웹 문서 1건(HTML 또는 이미지)을 입력으로:
1. **본문 추출** — 광고·내비게이션 제거, 제목/날짜/기자 등 메타 분리
2. **유형 분류** — 기사 / 시놉시스 / 인물 정보 / 편성 / 기타
3. **필드 추출** — 방송 도메인 개체(인물·배역·배우·프로그램·회차·일시·장소) + 유형별 구조 필드
4. **요약·핵심 정보** — 콘텐츠 맥락 보강용 텍스트
5. **관련성 판별** — 이 문서가 어느 프로그램·에피소드에 대한 것인지 (콘텐츠 ID 페어링)

출력은 ETRI 정규화 스키마(JSON) — udav1의 `CanonicalDocument` 계약을 확장.

---

## 1. 본문 추출 (Content Extraction / Boilerplate Removal)

| 계열 | 대표 | 특징 | 라이선스 주의 |
|---|---|---|---|
| 휴리스틱 DOM 규칙 | Readability(mozilla/readability), readability-lxml | 기사형 페이지에 강함, 가벼움 | Apache ✓ |
| 얕은 텍스트 특징 | Boilerpipe (Kohlschütter et al., WSDM 2010), jusText | 고전이지만 여전히 준수 | Apache/BSD ✓ |
| 하이브리드(현 사실상 표준) | **Trafilatura** (Barbaresi, ACL 2021 demo) | 정확도 최상급, 메타데이터(날짜·저자) 추출 포함 | **GPLv3 — 과제 조건상 사용 불가** |
| 학습 기반 | Web2Text (2018), MarkupLM (MS, 2022), DOM-LM | HTML 구조+텍스트 프리트레이닝, 오버킬 가능성 | 모델별 상이 |

- 실무 결론: **readability-lxml(Apache) + 사이트별 보정 규칙**이 기본선.
  Trafilatura는 성능 비교의 벤치마크로만 참고 (GPL이라 산출물에 못 넣음).
- **중요 실무 팁**: 포털·방송사 페이지 상당수가 `schema.org` JSON-LD(TVSeries,
  TVEpisode, Person)를 임베드함 — **파싱 전에 구조화 마크업부터 수확**하는 것이
  가장 값싸고 정확한 경로. (위키백과는 Infobox → API로 구조화 접근 가능)
- 오!주인님 수집에서 확인: MBC 공식 페이지는 JS 렌더링 + 인물관계도 이미지 →
  텍스트 추출 불가. 동적 렌더링(playwright)과 이미지 구조화(OCR)가 별도 경로로 필요.

## 2. 웹 정보 추출 (IE) 패러다임

| 패러다임 | 대표 | 적합 상황 |
|---|---|---|
| Wrapper/템플릿 (사이트별 XPath·CSS 규칙) | 고전 wrapper induction | 소스가 소수·안정적일 때. 용역 WDC-1의 "사이트별 플러그인 수집 모듈"과 대응 |
| 시맨틱 마크업 | schema.org/JSON-LD, OpenGraph | 있으면 공짜. 커버리지 편차 큼 |
| 통합 신경 IE | UIE (Lu et al., ACL 2022), InstructUIE (2023) | 스키마 유도 추출을 단일 모델로. 한국어 공개 가중치 빈약 |
| **LLM 스키마 추출** | GPT/Claude function calling, 오픈 LLM + constrained decoding (outlines, xgrammar) | 유형별 모델 없이 JSON 스키마 프롬프트로 통합 추출. 현재 실무 주류 |

## 3. 한국어 NER / 개체 처리

- **인코더 기반**: KLUE-RoBERTa + KLUE-NER(6개 표준 태그), KoELECTRA,
  KPF-BERT(뉴스 도메인 특화 — 기사 처리에 유리). 모두 상업 허용 라이선스 확인 필요(대부분 Apache/MIT).
- **방송 도메인 태그셋은 공개 표준이 없음** — 인물(실존)/배역(가공)/배우/프로그램/
  회차/방송사/일시 구분이 핵심인데 일반 NER은 인물·배역을 모두 PS로 뭉갬.
- **약지도(weak supervision) 기회**: 기사 관행 표기 `한비수(이민기 분)`,
  위키백과 인포박스·출연진 목록에서 배역-배우 쌍을 자동 수확 → 원거리 감독으로
  도메인 NER 학습 데이터 생성 가능 (오주인님 기사에서 패턴 다수 확인).
- **개체 연결(EL)**: bi-encoder 후보생성 + cross-encoder 재랭킹(BLINK 스타일),
  한국어는 위키백과 앵커 기반. 동명이인 해소는 프로그램 컨텍스트(출연작)로 제약.

## 4. 요약

- 추출식: TextRank/LexRank, centroid+MMR — **udav1 analyze/summarize 재사용 가능**
  (결정적·근거 추적, 웹 문서에도 그대로 적용됨)
- 생성식: KoBART-summarization, pko-t5, LLM 요약 — 유창하나 환각 위험,
  근거 스팬 병기 필요. 시놉시스→로그라인 압축 같은 태스크엔 생성식이 자연스러움.

## 5. LLM 기반 구조화 추출 (현 시점 실무 주류)

- 오픈 가중치 후보: Qwen2.5-Instruct(7B/14B, Apache), Llama-3.x(라이선스 조건부),
  EXAONE-3.5(연구 라이선스 — 상업 조건 확인 필요), 국산 sLLM 계열.
- **Constrained decoding**(outlines, xgrammar, llama.cpp grammar)으로 JSON 스키마를
  강제하면 파싱 실패율이 사실상 0 — 스키마 준수 요구사항(ETRI JSON 규격)과 정합.
- 장점: 유형별 개별 모델 불필요, zero-/few-shot으로 신규 문서 유형 대응, 개발 속도.
- 단점: GPU 비용, 재현성(temperature=0 고정 필요), 환각(없는 배역 생성 등) →
  **검증 레이어 필수**: ① 스키마 밸리데이션 ② 추출값의 원문 스팬 존재 검증(grounding)
  ③ NER/규칙 교차 확인.
- 증류: LLM 추출 결과를 검수해 sLLM(또는 인코더 NER) 파인튜닝 데이터로 재활용 —
  용역 WUA-3(라벨 데이터 구축)와 같은 구조.

## 6. 관련성 판별 / 콘텐츠 ID 페어링

- 1차: **규칙** — 제목 정규화 매칭(《오! 주인님》/'오 주인님'/Oh My Ladylord 변형),
  방영일↔기사 작성일 근접성, 채널 언급.
- 2차: **임베딩 유사도** — bge-m3(MIT) bi-encoder로 문서↔프로그램 프로필 매칭,
  경계 사례는 cross-encoder 재랭킹.
- 페어링 정확도가 데이터셋 품질의 병목 (WDC-4 "콘텐츠 식별자 페어링"의 핵심).

---

## 7. 프로토타입 구현 옵션 (상의용)

| | 옵션 A: 규칙+인코더 | 옵션 B: LLM 중심 | 옵션 C: 하이브리드 (제안) |
|---|---|---|---|
| 본문 추출 | readability-lxml+규칙 | LLM에 HTML 요약 위임 | 규칙 (+JSON-LD 수확) |
| 필드 추출 | KLUE NER + 정규식 | LLM 스키마 추출 | **LLM 스키마 추출** (+constrained decoding) |
| 검증 | — | 스키마만 | **스키마 + 원문 스팬 grounding + NER 교차** |
| 요약 | udav1 추출식 | LLM 생성 | udav1 추출식 기본, 로그라인만 생성式 |
| 관련성 | 규칙 | LLM 판단 | 규칙 1차 + 임베딩 2차 |
| 장점 | 결정적·저비용·CPU | 개발 최속, 신규 유형 무료 | 정확도·신뢰성·비용 균형 |
| 단점 | 도메인 NER 학습 데이터 없음(선구축 필요) | 비용·환각·재현성 | 구성요소 多 |
| GPU | 불필요 | 필요(로컬 LLM) | 부분 필요 |

**제안 방향(C)**: ingest에 `web_parser`(HTML→CanonicalDocument) 추가 →
필드 추출은 로컬 LLM(Qwen2.5-7B + outlines) 스키마 추출 → 검증 레이어 →
관련성은 규칙+bge-m3 → 요약은 기존 udav1 재사용.
udav1의 `CanonicalDocument` 계약을 유지하고 doc_type만 `web_article` /
`web_synopsis` / `web_cast` / `web_program_meta` / `web_episodes`로 확장.

### 결정 필요 사항 (사용자 협의)

1. LLM 사용 여부와 모델 (로컬 Qwen2.5 vs API vs 인코더-only)
2. 방송 도메인 NER을 별도 학습할지, LLM 추출+검증으로 대체할지
3. `CanonicalDocument` 확장 방식 (segments에 필드-값을 얹을지, 별도 `entities`/`fields` 슬롯 추가할지)
4. 동적 렌더링(playwright) 포함 여부 — MBC류 JS 페이지 대응
5. 프로토타입 평가 기준 (오주인님 5개 문서에 대한 필드 추출 정확도 측정 방법)
