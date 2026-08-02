"""udav2 정제층 ① — 기사 문장 분류 (서사 정보 추출).

회차 줄거리·리뷰 기사에는 서사 사실 외에 예고성 문장, 시청률·재방송 안내,
제작진 코멘트가 섞여 있다. 문장(세그먼트)을 4+1종으로 분류해 '서사 사실'만
회차 요약·서사 구조화에 쓰도록 정제한다.

  narrative_fact       극중 사건·관계 서술 (배역 개체 + 서술형)
  preview_speculation  예고·추측·관전포인트 ("~할 전망", "궁금증을 자아낸다")
  broadcast_notice     방송·편성·시청률 안내 ("재방송된다", "닐슨코리아")
  quote_comment        제작진·배우 발언 인용 ("~라고 전했다")
  other                판별 불가

규칙 기반 v1 — KoELECTRA 분류 헤드(M2, 골드셋 검수 후)로 교체 예정이며
classify_sentence() 인터페이스는 유지된다.
"""
import re

SENT_CLASSES = ("narrative_fact", "preview_speculation", "broadcast_notice",
                "quote_comment", "other")

_QUOTE = re.compile(r"라고\s*(전했다|밝혔다|말했다|덧붙였다|답했다|평가했다)|고\s*(전했다|밝혔다)")
_NOTICE = re.compile(
    r"재방송|다시보기|닐슨코리아|시청률\s*[\d.]+\s*%|분부터|채널에서|편성표|"
    r"방송된다|방송한다|첫\s*방송되었|부작인\s*드라마|출연진은|극본\s|연출\s|제작진은.*방송을 앞두고")
_PREVIEW = re.compile(
    r"전망이다|예고|기대감|기대를|궁금증|관전\s*포인트|주목된다|눈길|이목|집중되고|"
    r"보인다$|것으로 보인다|할지|일까|를까|긴장감을 불어넣을|예정이다|"
    r"사진\s*속|공개된 사진|스틸|포착한 것|깜짝 공개")
_NARR_VERB = re.compile(
    r"(했다|됐다|였다|졌다|있다|난다|들었다|받았다|남겼다|나눴다|보냈다|"
    r"암시됐다|공개된다|시작된다|벌어진다|사라진|선언|고백|목격|작성했다)")


def classify_sentence(text: str, has_character: bool = False) -> str:
    """문장 1개 -> SENT_CLASSES. 규칙 우선순위: 인용 > 안내 > 예고 > 서사."""
    t = text.strip()
    if not t:
        return "other"
    if _QUOTE.search(t):
        return "quote_comment"
    if _NOTICE.search(t):
        return "broadcast_notice"
    if _PREVIEW.search(t):
        return "preview_speculation"
    if has_character and _NARR_VERB.search(t):
        return "narrative_fact"
    if has_character:
        return "narrative_fact"
    return "other"


def refine_article(segments, entities):
    """기사 세그먼트에 sent_class를 부여하고 서사 사실만 추린 정제 결과 반환.

    returns: (per-seg {seg_id: sent_class}, refined dict)
    """
    char_segs = {e.seg_id for e in entities if e.tag in ("CHARACTER", "EVENT")}
    classes, narrative, counts = {}, [], {}
    for seg in segments:
        if seg.kind == "title":
            classes[seg.seg_id] = "other"
            continue
        cls = classify_sentence(seg.text, has_character=seg.seg_id in char_segs)
        classes[seg.seg_id] = cls
        counts[cls] = counts.get(cls, 0) + 1
        if cls == "narrative_fact":
            narrative.append({"seg_id": seg.seg_id, "text": seg.text})
    return classes, {"narrative": narrative, "sent_class_counts": counts,
                     "method": "rule-v1 (KoELECTRA head: M2)"}
