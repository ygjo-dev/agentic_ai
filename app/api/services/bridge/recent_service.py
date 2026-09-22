"""KRRI_ASAP 시스템의 실행 회차를 기억해 두고, Streamlit 따라 그리기가 읽어간다.

KRRI_ASAP 은 `POST /chat/stream` 으로 발화를 넣고 Streamlit 은 `GET /recent` 로
그 결과를 물어간다. 방향은 하나이고 **KRRI_ASAP 코드는 한 줄도 안 바뀐다.**

계약이 넷이다.

    원본을 안 바꾼다     훔쳐보는 자리 둘 다 받은 것을 그대로 다시 낸다.
                        기록 때문에 이벤트가 한 건이라도 달라지면 시연이 깨진다
    raw JSON 을 안 담는다 회차의 문자열은 전부 이미 화면으로 나간 것이다 — 답(실행한
                        답은 KRRI_ASAP, 안 간 자리는 local_presentation)과 단계 이벤트의
                        message. 여기서 다시 요약하지 않는다 — 요약하는 코드가 둘이
                        되는 순간 한쪽이 geojson 을 흘린다.
                        `commands` 는 아예 안 읽는다. 좌표 배열이 거기 있다
    회차가 안 섞인다     `ContextVar` 로 가른다. 요청마다 asyncio Task 가 따로라
                        두 발화가 겹쳐 들어와도 서로의 칸에 안 쓴다
    완결된 것만 남긴다   마지막 result 를 본 회차만 남긴다. 중간에 끊긴 것은
                        답이 없으므로 남길 것이 없다

**메모리에만 둔다.** 서버를 다시 띄우면 사라지는데, 시연용 연동이라 그때는
발화를 다시 넣으면 된다.

**기록 때문에 `/chat/stream` 이 깨지면 안 된다.** 훔쳐보는 자리도 남기는 자리도
전부 감싸서 삼킨다. 답이 먼저다.

훔쳐보는 자리는 `resolve_service.resolve` 하나다(인자 · 고른 recipe · 후보들).
`app/api/main.py` 가 한 번 씌운다. 발화 한 건은 늘 해석을 거치고 그 결과 그대로
실행되므로 실제로 부른 recipe 와 인자도 거기서 보인다.

**단계와 실행 판정은 이벤트에서 옮겨 적는다.** 답 문장에서 되살리지 않는다 — 답은
사람에게 보일 표현이고, KRRI 답은 단계 줄 꼴을 약속하지 않는다.

    steps              step_start · step_end 를 받은 차례대로. {node, start_message,
                       end_message, failed}. 해석 단계(node="resolve")도 한 단계다
    execution_status   result 의 status. KRRI 가 실행한 회차에만 있고(success · failed)
                       KRRI 까지 안 간 회차는 None
"""

import time
from collections import deque
from contextvars import ContextVar

# 기억할 회차 수. 넘으면 오래된 것부터 버린다.
# 리허설 한 바퀴가 통째로 남는 크기다. 화면은 늘 마지막 것만 그린다.
MAX_TURNS = 20

# since 를 안 줬을 때 돌려줄 회차 수.
TAIL = 5

# 이 회차가 지나가며 모으는 칸. /chat/stream 흐름 안에서만 채워진다.
#
# 이 칸이 None 이면 아무것도 안 남긴다 — Streamlit 이 부르는 POST /resolve 는
# 회차가 아니므로 그때는 훔쳐보는 자리가 조용히 지나간다.
_SLOT: ContextVar[dict | None] = ContextVar("recent_slot", default=None)

# 남긴 회차. 왼쪽이 오래된 것.
_TURNS: "deque[dict]" = deque(maxlen=MAX_TURNS)

# 회차 번호. 늘기만 한다. 화면이 "새 것이 왔는지" 를 이것으로 안다.
_SEQ = 0


# ================================================================ 남기기
def watched(text: str, events):
    """`/chat/stream` 이벤트 흐름을 그대로 흘려보내면서 회차 하나를 남김.

    출력  받은 이벤트를 순서 그대로 다시 냄. 하나도 안 바꿈
    규칙  마지막 result 를 본 회차만 남김. 중간에 끊긴 것은 답이 없으므로
          남길 것이 없음
          남기다 터져도 이벤트는 이미 다 나간 뒤임. 삼키고 지나감
    제약  이벤트를 고치거나 버리지 않는다.
          KRRI_ASAP 화면이 읽는 흐름이다. 여기서 한 건이라도 모양이 달라지면
          기록 때문에 시연이 깨진다
    """

    async def stream():
        slot = _new_slot(text)
        token = _SLOT.set(slot)
        try:
            async for payload in events:
                _note_event(slot, payload)
                yield payload
        finally:
            _release(token)
            _keep(slot)

    return stream()


def _new_slot(text: str) -> dict:
    """이 회차가 채워 갈 빈 칸."""
    return {
        "at": time.time(),
        "utterance": text,
        "status": "",
        "argument": "",
        "recipe_id": None,
        "candidate_recipe_ids": [],
        "steps": [],
        "answer": "",
        "execution_status": None,
        "done": False,
    }


def _release(token) -> None:
    """훔쳐보는 칸을 되돌림. 못 되돌려도 지나감.

    규칙  일찍 닫힌 흐름은 token 을 만든 문맥과 다를 수 있음. 그때는 비워만 둠
    """
    try:
        _SLOT.reset(token)
    except Exception:  # noqa: BLE001 — 되돌리기 실패로 답을 막지 않는다.
        try:
            _SLOT.set(None)
        except Exception:  # noqa: BLE001
            pass


def _note_event(slot: dict, payload) -> None:
    """이벤트 하나에서 남길 것만 뽑음.

    규칙  step_start 가 단계 하나를 열고 같은 node 의 step_end 가 그것을 닫음.
          짝이 없는 step_end 는 단계 하나로 따로 남김
          failed 는 step_end 의 칸 그대로. 칸이 없으면 실패가 아님
          result 를 보면 답 문구와 status 를 담고 이 회차를 완결로 표시함
    제약  commands 를 안 읽는다.
          지도 명령이 geojson 과 좌표 배열을 통째로 들고 있음. 이 파일이
          raw JSON 을 안 담기로 한 자리가 그것이다
          message 를 읽어 실패를 가르지 않는다. 실패는 이벤트의 failed 칸이 말함
    """
    try:
        kind = payload.get("type")
        node = payload.get("node") or ""
        steps = slot["steps"]
        if kind == "step_start":
            steps.append({"node": node, "start_message": payload.get("message") or "", "end_message": "", "failed": False})
        elif kind == "step_end":
            if not steps or steps[-1]["node"] != node or steps[-1]["end_message"]:
                steps.append({"node": node, "start_message": "", "end_message": "", "failed": False})
            steps[-1]["end_message"] = payload.get("message") or ""
            steps[-1]["failed"] = payload.get("failed") is True
        elif kind == "result":
            slot["answer"] = payload.get("answer") or ""
            status = payload.get("status")
            slot["execution_status"] = status if isinstance(status, str) else None
            slot["done"] = True
    except Exception:  # noqa: BLE001 — 기록 때문에 이벤트를 막지 않는다.
        pass


def _keep(slot: dict) -> None:
    """이 회차를 목록에 남김. 번호를 하나 올림.

    규칙  답을 못 본 회차는 안 남김. 중간에 끊긴 것임
    제약  여기서 예외를 올리지 않는다.
          이벤트가 다 나간 뒤에 도는 함수임. 여기서 터지면 답은 이미 나갔는데
          요청이 500 으로 끝남
    """
    try:
        if not slot.get("done"):
            return

        global _SEQ
        _SEQ += 1
        _TURNS.append(
            {
                "seq": _SEQ,
                "at": slot["at"],
                "utterance": slot["utterance"],
                "status": slot["status"],
                "argument": slot["argument"],
                "recipe_id": slot["recipe_id"],
                "candidate_recipe_ids": list(slot["candidate_recipe_ids"]),
                "steps": [dict(step) for step in slot["steps"]],
                "execution_status": slot["execution_status"],
                "answer": slot["answer"],
            }
        )
    except Exception:  # noqa: BLE001 — 답이 먼저다.
        pass


# ================================================================ 훔쳐보기
def watch_resolve(resolve):
    """`resolve_service.resolve` 를 감싸 고른 recipe · 후보 · 인자를 훔쳐봄.

    출력  같은 값을 그대로 돌려주는 함수
    제약  결과를 고치지 않는다.
          값을 안 바꾸는 껍데기임. 여기서 손대면 기록이 판정을 바꾸게 됨
    """

    def watching(*args, **kwargs):
        result = resolve(*args, **kwargs)
        _note_resolve(result)
        return result

    watching.__wrapped__ = resolve
    return watching


def _note_resolve(result) -> None:
    """해석 결과에서 남길 칸만 옮겨 적음. 회차 밖이면 아무 일도 안 함."""
    slot = _SLOT.get()
    if slot is None:
        return
    try:
        slot["status"] = result.get("status") or ""
        slot["recipe_id"] = result.get("recipe_id")
        slot["candidate_recipe_ids"] = list(result.get("candidate_recipe_ids") or [])
        slot["argument"] = result.get("argument") or ""
    except Exception:  # noqa: BLE001 — 훔쳐보다 터져서 해석을 막지 않는다.
        pass


# ================================================================ 읽어가기
def since(seq=None) -> dict:
    """그 번호보다 큰 회차들과 지금 번호.

    입력  마지막으로 본 회차 번호. 없으면 마지막 몇 회차
    출력  {"seq": 지금 번호, "turns": [...]}
    규칙  번호가 그대로면 turns 가 빈 목록. 화면이 그것으로 "새 것이 없다" 를 앎
    제약  아무것도 바꾸지 않는다. 읽기 전용임
    """
    turns = list(_TURNS)
    if seq is None:
        turns = turns[-TAIL:]
    else:
        turns = [turn for turn in turns if turn["seq"] > seq]
    return {"seq": _SEQ, "turns": turns}


def clear() -> None:
    """전부 지움. 시험이 서로 안 섞이게 하는 자리다."""
    global _SEQ
    _TURNS.clear()
    _SEQ = 0
