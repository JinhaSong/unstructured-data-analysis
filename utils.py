"""Small shared helpers (timecode parsing, id generation)."""
import re


def parse_timecode(value, fps: float = 30.0):
    """'MM:SS' | 'HH:MM:SS' | 'HH:MM:SS:FF' | '48: 54' -> seconds (float) or None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"\s+", "", str(value))
    if not text:
        return None
    parts = text.split(":")
    if not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    if len(nums) == 1:
        return float(nums[0])
    if len(nums) == 2:                       # MM:SS
        return nums[0] * 60.0 + nums[1]
    if len(nums) == 3:                       # HH:MM:SS
        return nums[0] * 3600.0 + nums[1] * 60.0 + nums[2]
    if len(nums) == 4:                       # HH:MM:SS:FF (drop-frame ignored)
        return nums[0] * 3600.0 + nums[1] * 60.0 + nums[2] + nums[3] / fps
    return None


def make_seg_id(doc_id: str, index: int) -> str:
    return f"{doc_id}#seg_{index:04d}"


_NORM_RE = re.compile(r"[\s\.,!\?~‥…·\"'“”‘’\(\)\[\]<>「」『』:;\-_/]+")


def norm_for_match(text: str) -> str:
    """Normalize for fuzzy text matching: drop whitespace/punctuation."""
    return _NORM_RE.sub("", text or "")
