"""Encoding detection/normalization.

The sample corpus mixes UTF-8-BOM (기사원고) and CP949 (자막) -- reading with a
fixed codec silently mojibakes half the files, so every text read goes
through here. Deterministic strict-decode attempts first; the optional
charset-normalizer (MIT) is only a fallback.
"""

_TRY_ORDER = ("utf-8-sig", "utf-8", "cp949", "euc-kr")


def read_text(path: str) -> tuple[str, str]:
    """Read a text file with encoding auto-detection -> (text, encoding_used)."""
    with open(path, "rb") as fp:
        data = fp.read()
    return decode_bytes(data)


def decode_bytes(data: bytes) -> tuple[str, str]:
    for enc in _TRY_ORDER:
        try:
            return data.decode(enc), enc
        except (UnicodeDecodeError, ValueError):
            continue
    try:  # optional dependency
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best is not None:
            return str(best), best.encoding
    except ImportError:
        pass
    return data.decode("utf-8", errors="replace"), "utf-8?replace"


def normalize_newlines(text: str) -> str:
    """CRLF / lone-CR (both appear in 기사원고) -> LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")
