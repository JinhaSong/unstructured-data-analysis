"""udav2 P5 — 생성 요약 (KoBART, MIT).

gogamza/kobart-summarization (MIT) 기본. 긴 입력(ASR 전사)은 청크 요약 후
요약문을 다시 요약하는 2단 계층 요약. KE-T5(Apache-2.0) 비교 벤치는 M3 —
MODEL_ID만 바꾸면 동일 인터페이스로 교체 가능.
"""
MODEL_ID = "gogamza/kobart-summarization"   # MIT

_MAX_INPUT_CHARS = 1800      # ~ 1024 token 이내로 유지하는 보수적 문자 상한
_tokenizer = None
_model = None


def _load():
    global _tokenizer, _model
    if _model is None:
        from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration
        _tokenizer = PreTrainedTokenizerFast.from_pretrained(MODEL_ID)
        _model = BartForConditionalGeneration.from_pretrained(MODEL_ID)
        _model.eval()
    return _tokenizer, _model


def _chunks(text, limit=_MAX_INPUT_CHARS):
    """문장 경계를 존중하며 limit 이하 청크로 분할."""
    out, buf = [], ""
    for line in text.replace(". ", ".\n").split("\n"):
        if len(buf) + len(line) + 1 > limit and buf:
            out.append(buf.strip())
            buf = ""
        buf += line + " "
    if buf.strip():
        out.append(buf.strip())
    return out


def summarize_text(text: str, max_length: int = 128, min_length: int = 24) -> str:
    """단일 청크 생성 요약."""
    import torch
    tok, model = _load()
    inputs = tok([text], max_length=1024, truncation=True, return_tensors="pt")
    with torch.no_grad():
        ids = model.generate(
            inputs["input_ids"], num_beams=4, max_length=max_length,
            min_length=min_length, length_penalty=1.0, no_repeat_ngram_size=3,
            repetition_penalty=1.3,   # 방송 원고류에서 구 반복 퇴화 방지
            early_stopping=True)
    return tok.decode(ids[0], skip_special_tokens=True).strip()


def summarize_long(text: str, max_length: int = 160) -> dict:
    """계층 요약: 청크별 요약 -> (2청크 이상이면) 요약의 요약."""
    text = (text or "").strip()
    if not text:
        return {"summary": None, "chunk_summaries": [], "model": MODEL_ID}
    chunks = _chunks(text)
    partials = [summarize_text(c) for c in chunks]
    if len(partials) == 1:
        final = partials[0]
    else:
        final = summarize_text(" ".join(partials), max_length=max_length)
    return {"summary": final, "chunk_summaries": partials if len(partials) > 1 else [],
            "model": MODEL_ID}
