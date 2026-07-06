"""Korean sentence splitting.

kiwipiepy (LGPL-2.1, dynamically linked -> commercial OK) when installed;
regex fallback keeps the pipeline runnable with zero deps.
"""
import re

_kiwi = None


def _get_kiwi():
    global _kiwi
    if _kiwi is None:
        try:
            from kiwipiepy import Kiwi
            _kiwi = Kiwi()
        except ImportError:
            _kiwi = False
    return _kiwi


_FALLBACK_RE = re.compile(
    r"(?<=[\.!\?])\s+|(?<=(?:다|요|죠|까|네|오|라|자))\.\s*|(?<=[\.!\?])$")


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    kiwi = _get_kiwi()
    if kiwi:
        return [s.text.strip() for s in kiwi.split_into_sents(text) if s.text.strip()]
    parts = re.split(r"(?<=[\.!\?…])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def tokenize(text: str) -> list[str]:
    """Content-word tokens for TF-IDF scoring (nouns/verbs via Kiwi if present)."""
    kiwi = _get_kiwi()
    if kiwi:
        return [t.form for t in kiwi.tokenize(text)
                if t.tag.startswith(("NN", "VV", "VA", "SL", "SN")) and len(t.form) > 1]
    return [t for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", text)]
