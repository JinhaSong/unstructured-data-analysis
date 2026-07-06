"""P4 -- extractive, time-coded summarization (no generative LLM).

Per window: split sentences -> embed -> rank by centroid similarity ->
MMR-select k sentences -> join in original order. Sentences come verbatim
from the source, so there is zero hallucination risk and full traceability.

Embedding tiers (auto-selected):
  B. sentence-transformers + BAAI/bge-m3 (Apache-2.0 / MIT) if installed
  A. pure-python TF-IDF vectors (stdlib) otherwise -- deterministic, CPU-only
"""
import math
import os
from collections import Counter

from ..schema import TimeCodedSummary
from .segment import split_sentences, tokenize

_st_model = None


def _get_st_model():
    """Tier B embedder, opt-in via UDA_EMBEDDING_MODEL (or default bge-m3)."""
    global _st_model
    if _st_model is None:
        if os.environ.get("UDA_DISABLE_ST"):
            _st_model = False
            return _st_model
        try:
            from sentence_transformers import SentenceTransformer
            _st_model = SentenceTransformer(
                os.environ.get("UDA_EMBEDDING_MODEL", "BAAI/bge-m3"))
        except Exception:
            _st_model = False
    return _st_model


# -- tier A: TF-IDF sparse vectors (dict) -------------------------------------
def _tfidf_vectors(sent_tokens):
    n = len(sent_tokens)
    df = Counter(tok for toks in sent_tokens for tok in set(toks))
    vecs = []
    for toks in sent_tokens:
        tf = Counter(toks)
        vecs.append({t: c * math.log(1 + n / df[t]) for t, c in tf.items()})
    return vecs


def _dot(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def _cos(a, b):
    na, nb = math.sqrt(_dot(a, a)), math.sqrt(_dot(b, b))
    return _dot(a, b) / (na * nb) if na and nb else 0.0


def _sim_matrix(sentences):
    model = _get_st_model()
    if model:
        emb = model.encode(sentences, normalize_embeddings=True)
        sims = emb @ emb.T
        centroid = emb.mean(axis=0)
        rel = emb @ (centroid / (sum(centroid * centroid) ** 0.5))
        return [[float(x) for x in row] for row in sims], [float(x) for x in rel]
    vecs = _tfidf_vectors([tokenize(s) for s in sentences])
    centroid = {}
    for v in vecs:
        for k, val in v.items():
            centroid[k] = centroid.get(k, 0.0) + val / len(vecs)
    sims = [[_cos(a, b) for b in vecs] for a in vecs]
    rel = [_cos(v, centroid) for v in vecs]
    return sims, rel


def _mmr_select(rel, sims, k, lambda_=0.7):
    """Maximal Marginal Relevance: relevant AND non-redundant sentence picks."""
    n = len(rel)
    selected, candidates = [], list(range(n))
    while candidates and len(selected) < k:
        best, best_score = None, -1e9
        for i in candidates:
            redundancy = max((sims[i][j] for j in selected), default=0.0)
            score = lambda_ * rel[i] - (1 - lambda_) * redundancy
            if score > best_score:
                best, best_score = i, score
        selected.append(best)
        candidates.remove(best)
    return sorted(selected)


def summarize_window(window, max_sentences: int = 2) -> TimeCodedSummary:
    sent_src = []   # (sentence, seg_id)
    for seg in window.segments:
        for sent in split_sentences(seg.text):
            sent_src.append((sent, seg.seg_id))

    if not sent_src:
        summary, sources = "", []
    elif len(sent_src) <= max_sentences:
        summary = " ".join(s for s, _ in sent_src)
        sources = sorted({sid for _, sid in sent_src})
    else:
        sentences = [s for s, _ in sent_src]
        sims, rel = _sim_matrix(sentences)
        picked = _mmr_select(rel, sims, max_sentences)
        summary = " ".join(sentences[i] for i in picked)
        sources = sorted({sent_src[i][1] for i in picked})

    return TimeCodedSummary(
        start_time_seconds=window.start_time_seconds,
        end_time_seconds=window.end_time_seconds,
        summary=summary, source_seg_ids=sources,
        keywords=extract_keywords(" ".join(s for s, _ in sent_src), topn=5),
        speaker=window.speaker)


def extract_keywords(text: str, topn: int = 10) -> list[str]:
    counts = Counter(tokenize(text))
    return [w for w, _ in counts.most_common(topn)]
