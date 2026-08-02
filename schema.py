"""P0 -- canonical schemas shared by every UDA stage.

Dataclass-based (stdlib only) so workers/tests run without extra installs.
``CanonicalDocument`` is the ONLY contract between the ingest layer and the
analyze layer: new file formats only add parsers, new models only add
analyzers -- neither side touches the other.
"""
from dataclasses import dataclass, field, asdict

# Document types found in the sample corpus (비정형 수집 데이터 목록):
#   cuesheet        큐시트        (xlsx/pdf/hwp, carries timecodes)
#   narration       나레이션원고/대본 (pdf/hwp)
#   schedule        편성표        (no samples yet -- format TBD)
#   subtitle_script 자막/기사원고  (txt; subtitles have NO timecodes)
#   clip_meta       영상 메타      (.mp4.xml clipInfo)
DOC_TYPES = ("cuesheet", "narration", "schedule", "subtitle_script", "clip_meta")

# udav2 (docs/ud-analysis-model-design.md): 웹·부가정보 JSON + ASR 전사까지 확장.
DOC_TYPES_V2 = DOC_TYPES + (
    "asr_transcript", "synopsis", "episode_summary", "cast_info",
    "episode_info", "article", "program_meta", "other")

# 방송 도메인 NER 태그셋 — 핵심 12종 + 서사·부가 확장 6종 (설계서 §3)
NER_TAGS = (
    "PROGRAM", "EPISODE", "CHARACTER", "ACTOR", "STAFF", "PERSON",
    "BROADCASTER", "PLATFORM", "PRODUCTION", "DATE", "TIME", "LOCATION",
    "EVENT", "GENRE", "ORGANIZATION", "MUSIC", "RATING", "QUANTITY")

# 관계 8종 (설계서 §4)
RELATION_TYPES = (
    "plays", "appears_in", "directed_by", "written_by", "aired_on",
    "scheduled_at", "produced_by", "char_rel", "involved_in")


@dataclass
class Segment:
    """One minimal unit of a document (cuesheet row, speaker turn, paragraph)."""
    seg_id: str
    text: str
    order: int | None = None
    start_time_seconds: float | None = None   # None until aligned (subtitles)
    end_time_seconds: float | None = None
    speaker: str | None = None                # "앵커", "해설", reporter name, ...
    kind: str | None = None                   # cuesheet 구분(S/R) + 형식(eVCR/CG) etc.
    raw: dict = field(default_factory=dict)   # original fields, for traceability

    def to_dict(self):
        return asdict(self)


@dataclass
class CanonicalDocument:
    """Normalized document -- the contract between ingest and analyze."""
    doc_id: str
    doc_type: str                             # one of DOC_TYPES
    source_format: str                        # pdf/hwp/xlsx/txt/xml
    source_path: str = ""
    program: str | None = None                # 뉴스데스크 / 프라임인터뷰 / ...
    air_date: str | None = None
    clip_id: str | None = None                # joins with .mp4.xml CLIPID
    program_meta: dict = field(default_factory=dict)
    segments: list = field(default_factory=list)   # list[Segment]

    @property
    def full_text(self) -> str:
        return "\n".join(s.text for s in self.segments if s.text)

    def to_dict(self):
        return asdict(self)


@dataclass
class TimeCodedSummary:
    """Extractive summary of one time window (original sentences, no generation)."""
    start_time_seconds: float | None
    end_time_seconds: float | None
    summary: str
    source_seg_ids: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    speaker: str | None = None

    def to_dict(self):
        return asdict(self)


@dataclass
class Entity:
    """One NER span. ``source``: gazetteer | rule | model(<name>)."""
    tag: str                                  # one of NER_TAGS
    text: str
    doc_id: str
    seg_id: str | None = None
    start: int | None = None                  # char offsets within the segment text
    end: int | None = None
    score: float = 1.0
    source: str = "rule"
    normalized: str | None = None             # canonical form (e.g. date -> ISO)

    def to_dict(self):
        return asdict(self)


@dataclass
class Relation:
    """One typed relation between two entities (or entity -> literal)."""
    rel: str                                  # one of RELATION_TYPES
    head: str                                 # entity surface (canonical form)
    head_tag: str
    tail: str
    tail_tag: str
    doc_id: str | None = None                 # evidence document
    evidence: str | None = None               # evidence sentence/field
    score: float = 1.0
    source: str = "rule"

    def to_dict(self):
        return asdict(self)


@dataclass
class StructuredDocResult:
    """udav2 per-document output: classification + entities + summary."""
    doc_id: str
    doc_type: str                             # one of DOC_TYPES_V2
    doc_class_method: str = "rule"            # rule | model
    source_path: str = ""
    entities: list = field(default_factory=list)       # list[Entity]
    summary: str | None = None                # generative (KoBART) summary
    summary_model: str | None = None
    evidence_summary: list = field(default_factory=list)  # extractive fallback
    segments_analyzed: int = 0

    def to_dict(self):
        return asdict(self)


@dataclass
class ProgramStructuredResult:
    """udav2 program-level bundle -> TA 입력 및 CMG/RAG 소스."""
    content_id: str
    program_title: str | None = None
    documents: list = field(default_factory=list)      # list[StructuredDocResult]
    relations: list = field(default_factory=list)      # list[Relation] (cross-doc)
    models: dict = field(default_factory=dict)         # component -> model name/license

    def to_dict(self):
        return asdict(self)


@dataclass
class UDResult:
    """Final UD output handed to the TA (time-series alignment) stage."""
    doc_id: str
    doc_type: str
    cues: list = field(default_factory=list)                 # list[Segment], time-coded
    time_coded_summaries: list = field(default_factory=list)  # list[TimeCodedSummary]
    keywords: list = field(default_factory=list)
    program_meta: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)
