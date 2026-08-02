# 비정형 데이터 분석 모델 (udav2) — 설계서

> 연구계획서(붙임4-1) 1차년도 "복합구조 비정형 데이터 분석 기술" 대응.
> 사용자 협의 결정(2026-08) 반영: **LLM 미사용, BERT급~sub-LLM 언어모델**로
> 비정형 데이터(자막·대본·편성표·부가정보)를 구조화·분석한다.
> 작성: 2026-08. 상태: 설계 확정 → 구현 착수 단계.

## 0. 협의 결정 사항 (확정)

| # | 논점 | 결정 |
|---|---|---|
| 1 | 자막 입력 | ASR 전사로 대체. mmca 기존 전사는 118초 씬 클립(video3-01) 1건뿐 → **1회 전체(63분) faster-whisper large-v3 전사를 신규 생성**해 사용 |
| 2 | NER 태그셋 | **최대 범위** — 핵심 12종 + 서사 확장 6종 (아래 §3) |
| 3 | 요약 모델 | 정량 우위 + 라이선스 무결 조건 → **KoBART(MIT) 1순위, KE-T5(Apache-2.0) 비교 벤치** 후 ROUGE 우위 모델 채택. GPL·CC-BY-SA 계열 배제 |
| 4 | 대본·큐시트 파서 검증 | 오!주인님은 대본 미공개 → **기존 MBC충북 실무 문서 샘플**(뉴스데스크 큐시트·나레이션 등)로 파서·분석기 검증, 오!주인님은 편성표+부가정보+ASR 전사로 검증 |

모델 크기 제약: 전 구성요소 **BERT급(110M)~sub-LLM(≤600M)**. LLM(디코더 7B+) 미사용.

**추가 협의 결정 (2026-08-02):**

| # | 논점 | 결정 |
|---|---|---|
| 5 | 입력 형식 | **모든 입력은 텍스트만 추출된 txt로 가정** — 원천 포맷별(방송사별) 파서는 `ingest/txt_meta.py` 레지스트리로 확장, 파이프라인은 txt→**동일 형식 JSON** 정제 |
| 6 | ASR | UD에서 수행·소비하지 않음 — MMCA 산출물(느림). 자막 txt가 별도 제공될 때만 입력 |
| 7 | 회차 정렬 | UD 범위 아님 — 시계열 정렬(TA) 모듈 담당. UD는 문서 단위 구조화+개체 정규화까지 |

## 1. 입출력과 전체 구조

```
입력 (examples/ud/*)                    udav2 파이프라인                        출력
─────────────────────    ──────────────────────────────────────────    ─────────────────
자막(ASR 전사 JSON)  ─┐   [P1] ingest: 파서 (v1 유지+확장)              구조화 JSON
대본/큐시트(xlsx·hwp) ├─→ [P2] 문서 유형 분류  (KoELECTRA 분류 헤드)     (CanonicalDocument
편성표(json·xlsx)     │   [P3] 도메인 NER      (KoELECTRA 토큰 분류)      + entities
시놉시스·인물·기사    ─┘   [P4] 관계 추출       (패턴 + cross-encoder)     + relations
                          [P5] 요약           (KoBART│KE-T5 생성식        + summary
                          [P6] 필드 임베딩     (bge-m3)                    + embeddings)
                          [P7] 검증·정규화     (스키마+원문 스팬 검증)          │
                                                                            ▼
                                                                   시계열 정렬(TA) 입력
```

- **계약 유지**: udav1 `CanonicalDocument`(schema.py)를 확장 — `entities`,
  `relations`, `summary`, `doc_class` 슬롯 추가. ingest↔analyze 분리 원칙 유지.
- 표 구조 문서(편성표·큐시트)는 **규칙 파서**(v1 방식), 자유 텍스트(시놉시스·기사·
  대본 지문·ASR 전사)에 **언어모델** 투입.

## 2. P2 문서 유형 분류

- 백본: **KoELECTRA-base-v3** (Apache-2.0, 110M) + 분류 헤드.
- 클래스: `cuesheet / script / schedule / subtitle_or_asr / synopsis / cast_info /
  episode_info / article / program_meta / other` (v1 doc_types 상위 호환).
- 파일 확장자·구조 힌트(규칙)로 1차 판별 → 텍스트 분류는 모호 케이스만. 소량
  학습(문서 수백 건)으로 충분한 난이도.

## 3. P3 방송 도메인 NER — 태그셋 (최대 범위)

일반 공개 NER(KLUE 6종 등)은 인물·배역·배우를 전부 PS로 뭉개므로 자체 태그셋 정의.
BIO 스킴, 문자 단위 오프셋 보존(원문 근거 추적).

**핵심 12종**

| 태그 | 정의 | 예 (오!주인님) |
|---|---|---|
| `PROGRAM` | 프로그램·작품명 | 오! 주인님, 뉴스데스크 |
| `EPISODE` | 회차·부작 표현 | 1회, 16부작, 최종회 |
| `CHARACTER` | 배역(가공 인물) | 한비수, 오주인 |
| `ACTOR` | 배우 | 이민기, 나나 |
| `STAFF` | 제작진(연출·작가·PD) | 이철하(작가) |
| `PERSON` | 기타 실존 인물 | 기자, 인터뷰이 |
| `BROADCASTER` | 방송사·채널 | MBC, tvN |
| `PLATFORM` | OTT·유통 플랫폼 | 웨이브, 넷플릭스 |
| `PRODUCTION` | 제작사 | 초록뱀미디어 |
| `DATE` | 방송일·날짜 | 2021-03-24, 3월 24일 |
| `TIME` | 시각·편성 시간대 | 밤 9시 20분, 수목 |
| `LOCATION` | 장소(극중·실제) | 비수의 저택, 상암 |

**서사·부가 확장 6종**

| 태그 | 정의 | 예 |
|---|---|---|
| `EVENT` | 극중·서사 사건 | 계약 동거, 대본 리딩 하차 |
| `GENRE` | 장르·포맷 | 로맨틱 코미디, 미니시리즈 |
| `ORGANIZATION` | 기타 기관·단체(극중 포함) | 제작발표회 주관사 |
| `MUSIC` | OST·삽입곡 | OST Part.1 곡명 |
| `RATING` | 시청률·등급 | 3.4%(AGB), 15세 이상 시청가 |
| `QUANTITY` | 기타 수치(화수 외) | 시청자 수 등 |

- 백본: **KoELECTRA-base-v3**(Apache-2.0) 토큰 분류. 벤치 참조로 KLUE-RoBERTa
  수치를 보되 **KLUE 모델 자체는 CC-BY-SA-4.0이라 채택 배제** (과제 라이선스 조건).
  뉴스 도메인 보강이 필요하면 KcELECTRA(MIT) 비교.
- **학습 데이터 (약지도 → 검수)**:
  1. 기사 병기 패턴 `배역(배우 분)` → CHARACTER/ACTOR 자동 라벨 (오!주인님 기사에서 확인)
  2. 위키백과 인포박스·출연진 목록 → ACTOR/CHARACTER/STAFF/DATE/BROADCASTER 사전 매칭(distant supervision)
  3. 공개 데이터 보강: 모두의말뭉치 개체명, AI Hub 방송 콘텐츠 계열 코퍼스(라이선스·이용약관 확인 후)
  4. 소량 수작업 검수(오!주인님 문서 전량 + MBC충북 샘플)로 골드셋 구축 → 평가 겸용

## 4. P4 관계 추출

1차: 고신뢰 패턴·구조 기반 (병기 패턴, 인포박스, 편성표 필드) →
2차: 문장 내 후보쌍을 **cross-encoder(KoELECTRA) 관계 분류**로 보강.

| 관계 | 예 |
|---|---|
| `plays(ACTOR→CHARACTER)` | 이민기 → 한비수 |
| `appears_in(ACTOR→PROGRAM)` | 이민기 → 오! 주인님 |
| `directed_by / written_by(PROGRAM→STAFF)` | 오! 주인님 → 조수원 감독 |
| `aired_on(PROGRAM→BROADCASTER)` | 오! 주인님 → MBC |
| `scheduled_at(EPISODE→DATE/TIME)` | 2회 → 2021-03-25 22:00 (편성 변경 반영) |
| `produced_by(PROGRAM→PRODUCTION)` | — |
| `char_rel(CHARACTER↔CHARACTER)` | 한비수 ↔ 오주인 (계약 동거) — 인물관계도 구조화 |
| `involved_in(CHARACTER→EVENT)` | 오주인 → 대본 리딩 하차 |

`char_rel`+`involved_in`이 연구계획서의 "구조화 정의(인물·서사)"에 대응 —
인물관계 그래프와 사건 목록이 서사 구조의 1차 표현.

## 5. P5 요약 (생성식, 정량 벤치로 확정)

- 후보: **KoBART-summarization**(MIT, 124M) vs **KE-T5-base**(Apache-2.0).
- 파인튜닝: AI Hub **방송 콘텐츠 대본 요약 데이터** 등 방송 도메인 요약 코퍼스
  (약관상 연구 활용 확인 후) → 도메인 적합 파인튜닝.
- 평가: ROUGE-1/2/L + 개체 일치율(요약문 속 개체가 원문 NER 결과에 존재하는지 =
  환각 검사). **정량 우위 모델 채택**, 근거 스팬은 udav1 추출식(centroid+MMR)
  결과를 `evidence`로 병기해 생성식 환각을 상호 견제.
- 제외: pko-t5(CC-BY 계열 확인 전 보류), LLM 계열(결정상 미사용),
  Trafilatura류 GPL(무관하지만 동일 원칙).

## 6. P6–P7 임베딩·검증

- 필드·세그먼트 임베딩: **bge-m3**(MIT, 다국어) — RAG 스키마 `embedding`(1024차원)과 정합.
- 검증 레이어: ① 출력 JSON 스키마 밸리데이션 ② 추출값의 원문 스팬 존재 검증
  (grounding) ③ 관계의 타입 제약 검사(plays의 주어는 ACTOR만 등)
  ④ 콘텐츠 ID 페어링(제목 정규화 + bge-m3 유사도) — `MBC_OH_MY_LADYLORD` 부여.

## 7. 시계열 정렬(TA) 인터페이스 (후속 단계)

udav2 출력이 TA의 입력이 되도록:
- ASR 전사 세그먼트: 타임코드 보유 → 그대로 정렬 기준축
- 대본·큐시트: v1 align(P2) 로직으로 ASR에 타임코드 이식
- 부가정보(시놉·인물·기사): 타임코드 없음 → **개체·사건 매칭 기반 씬 단위
  의미 정렬** (NER/관계 출력이 매칭 키) — TA 단계에서 구현

## 8. 모듈 구조 (libs/ud/udav1 확장)

```
libs/ud/udav1/
  ingest/        (v1 유지) + json_meta.py (examples/ud JSON 부가정보 파서)
  schema.py      CanonicalDocument + Entity/Relation/Summary/DocClass 확장
  analyze/
    segment.py align.py window.py summarize.py   (v1 유지 — 추출식은 evidence용)
    classify.py      P2 문서 유형 분류
    ner.py           P3 도메인 NER (KoELECTRA)
    relations.py     P4 관계 추출
    summarize_gen.py P5 생성 요약 (KoBART/KE-T5)
    embed.py         P6 bge-m3
    validate.py      P7 검증
  weak_supervision/  병기 패턴·인포박스 수확 → NER/RE 학습 데이터 생성
  train/             파인튜닝 스크립트 (NER·분류·요약)
  docs/              본 설계서 외
```

## 9. 라이선스 총괄

| 구성요소 | 선택 | 라이선스 | 비고 |
|---|---|---|---|
| NER·분류·RE 백본 | KoELECTRA-base-v3 | Apache-2.0 | KLUE-RoBERTa(CC-BY-SA)는 벤치 참조만 |
| 생성 요약 | KoBART / KE-T5 | MIT / Apache-2.0 | 정량 벤치로 확정 |
| 임베딩 | bge-m3 | MIT | RAG 1024차원 정합 |
| ASR | faster-whisper | MIT (모델 가중치 OpenAI Whisper MIT) | |
| 형태소·문장분리 | kiwipiepy | LGPL v2.1 — **동적 링크 사용 검토 필요** | 문제 시 규칙 분리로 대체 |
| 학습 프레임 | transformers, datasets | Apache-2.0 | |

## 9-1. 실행 방법 (구현됨 — M1 프로토타입)

```bash
pip install -r libs/ud/udav1/requirements-v2.txt   # torch, transformers
cd <repo-root>
PYTHONPATH=libs/ud python -m udav1.structurize "examples/ud/MBC_오!주인님" \
  --asr "examples/mmca/MBC_2021-00-01-오!주인님1회/MBC_2021-00-01-VIDEO-asr-transcript.json"
# -> examples/ud/MBC_오!주인님/output/structured_result.json
# --no-model : 규칙+사전만 (transformers 불필요, CPU 즉시)
# --no-summary : 생성 요약 생략
```

구현 파일: `ingest/json_meta.py`(수집 JSON→CanonicalDocument),
`analyze/ner.py`(3층 도메인 NER), `analyze/relations.py`(관계 8종),
`analyze/summarize_gen.py`(KoBART 계층 요약), `analyze/classify.py`(규칙 분류),
`structurize.py`(오케스트레이터+CLI), `schema.py`(Entity/Relation/
StructuredDocResult/ProgramStructuredResult 확장).

## 10. 마일스톤

1. **M1 — 데이터 준비**: 1회 전체 ASR 전사 생성(진행 중), examples/ud JSON 파서,
   약지도 라벨 생성기(병기 패턴·인포박스), 골드셋 소량 검수
2. **M2 — 분류·NER**: KoELECTRA 파인튜닝(태그 18종), 오!주인님+MBC충북 골드셋 평가(F1)
3. **M3 — 관계·요약**: 관계 추출 8종, KoBART vs KE-T5 벤치·채택
4. **M4 — 통합**: CanonicalDocument 확장 출력 → ud 워커 연결, 구조화 JSON E2E
5. **M5 — 시계열 정렬 착수** (분석 모델 완료 후 — 결정 사항)
