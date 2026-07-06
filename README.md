# udav1 — Unstructured Data Analysis (v1)

Broadcasting/media **unstructured-data analysis** module: parses cuesheets,
narration scripts, schedules and subtitle/article drafts (pdf/hwp/xlsx/txt/xml),
normalizes them into one canonical schema, grafts ASR timecodes onto un-timed
subtitles, and produces **time-coded extractive summaries** — no generative LLM.

Consumed by the parent `specialized-metadata` pipeline (UD stage → TA stage)
as a git submodule at `libs/ud/udav1`.

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
