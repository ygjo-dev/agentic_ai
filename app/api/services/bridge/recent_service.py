"""저쪽 화면에서 넣은 발화 한 회차를 기억해 두고, 창구 하나로 읽어가게 한다.

**저쪽 화면과 Streamlit 이 이미 같은 서버를 본다.** 저쪽은 `POST /chat/stream`
으로 발화를 넣고 Streamlit 은 `POST /resolve` 로 그래프를 그린다. 그러니 저쪽이
넣은 발화의 결과를 이 서버가 이미 알고 있다 — 그것을 기억해 두면 Streamlit 이
물어가 따라 그릴 수 있다. **저쪽 코드는 한 줄도 안 바뀐다.**

방향은 하나다. 저쪽에서 넣고 Streamlit 이 따라 그린다. 반대 방향은 저쪽 화면을
고쳐야 하므로 여기 없다.

**메모리에만 둔다.** 파일도 DB 도 만들지 않는다. 서버를 다시 띄우면 사라지는데,
시연용 연동이라 그때는 발화를 다시 넣으면 된다. `clarify_service` 가 되묻기
하나를 기억하는 것과 같은 크기의 일이다.

**raw JSON 을 담지 않는다. 이 파일의 계약이다.**
회차에 실리는 문자열은 전부 `vendor_to_be_deleted/asap/workflow_answer` 가 이미 만들어
저쪽 화면으로 나간 것이다. 여기서 결과를 다시 요약하지 않는다 — 요약하는
코드가 둘이 되는 순간 한쪽이 geojson 을 흘린다. `commands` 는 아예 안 읽는다.
지도 명령이 좌표 배열을 통째로 들고 있는 자리가 그것이다.

**기록 때문에 `/chat` 이 깨지면 안 된다.** 훔쳐보는 자리도 남기는 자리도 전부
감싸서 삼킨다. 답이 먼저다.

지나가며 훔쳐보는 자리가 둘이다. 둘 다 **값을 안 바꾸는 껍데기**이고
`app/api/main.py` 가 한 번 씌운다.

    resolve_service.resolve   축 셋 · 인자 · 고른 recipe · 후보들
    execute_service.run       실제로 부른 recipe 와 인자 (되묻기 뒤 고르기는
                              해석을 안 거치므로 이 자리에서만 보인다)

`ContextVar` 로 회차를 가른다. 요청마다 asyncio Task 가 따로라 두 발화가
겹쳐 들어와도 서로의 칸에 안 쓴다.
"""

import re
import time
from collections import deque
from contextvars import ContextVar

# 기억할 회차 수. 넘으면 오래된 것부터 버린다.
#
# 시연 대본이 다섯 발화이고 되묻기까지 세도 열을 안 넘는다. 스물이면 리허설
# 한 바퀴가 통째로 남는다. 화면은 늘 마지막 것만 그리므로 더 둘 이유가 없다.
MAX_TURNS = 20

# since 를 안 줬을 때 돌려줄 회차 수.
TAIL = 5

# 답에서 단계 줄이 시작되는 꼴. workflow_answer.compose_workflow_answer 가
# "1. tool  인자  결과" 로 적는다. 줄머리에 공백이 없다.
#
# 되묻기 답의 후보 줄("  1  전기차 충전소 검색")과 갈라야 한다. 그쪽은 앞에
# 공백이 있고 번호 뒤에 마침표가 없다.
#
# **한 단계가 여러 줄일 수 있다.** knowledge.query 는 건수 줄 아래에 문서 조각
# 두셋을 들여 쓴 줄로 늘어놓는다 (2026-08-26 「서른한째」). 그 줄들은 이 꼴에
# 안 걸리므로 바로 앞 단계에 붙인다 — 떼어 내면 화면에서 조각이 사라진다.
_STEP_HEAD = re.compile(r"^\d+\. ")

# 이 회차가 지나가며 모으는 칸. /chat 흐름 안에서만 채워진다.
#
# 이 칸이 None 이면 아무것도 안 남긴다 — Streamlit 이 부르는 POST /resolve 는
# 회차가 아니므로 그때는 훔쳐보는 자리가 조용히 지나간다.
_SLOT: ContextVar[dict | None] = ContextVar("recent_slot", default=None)

# 남긴 회차. 왼쪽이 오래된 것.
_TURNS: "deque[dict]" = deque(maxlen=MAX_TURNS)

# 회차 번호. 늘기만 한다. 화면이 "새 것이 왔는지" 를 이것으로 안다.
_SEQ = 0

# 되묻기 뒤에 번호로 고른 회차의 status. SELECT · CLARIFY · NO_MATCH 는
# 발화 해석이 쓰는 값이고, 고르기는 해석을 안 거치므로 여기서 붙인다.
CHOICE = "CHOICE"


# ================================================================ 남기기
def watched(text: str, events):
    """`/chat` 이벤트 흐름을 그대로 흘려보내면서 회차 하나를 남김.

    입력  발화 · execute_service.chat 이 낸 이벤트 흐름
    출력  받은 이벤트를 순서 그대로 다시 냄. 하나도 안 바꿈
    규칙  마지막 result 를 본 회차만 남김. 중간에 끊긴 것은 답이 없으므로
          남길 것이 없음
          남기다 터져도 이벤트는 이미 다 나간 뒤임. 삼키고 지나감
    제약  이벤트를 고치거나 버리지 않는다.
          저쪽 화면이 읽는 흐름이다. 여기서 한 건이라도 모양이 달라지면
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
        "given": None,
        "want": None,
        "about": None,
        "argument": "",
        "recipe_id": None,
        "candidate_recipe_ids": [],
        "nodes": [],
        "answer": "",
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

    규칙  step_end 의 node 만 모음. 단계 줄은 답에서 가져오므로 여기서 안 만듦
          result 를 보면 답 문구를 담고 이 회차를 완결로 표시함
    제약  commands 를 안 읽는다.
          지도 명령이 geojson 과 좌표 배열을 통째로 들고 있음. 이 파일이
          raw JSON 을 안 담기로 한 자리가 그것이다
    """
    try:
        kind = payload.get("type")
        if kind == "step_end":
            slot["nodes"].append(payload.get("node") or "")
        elif kind == "result":
            slot["answer"] = payload.get("answer") or ""
            slot["done"] = True
    except Exception:  # noqa: BLE001 — 기록 때문에 이벤트를 막지 않는다.
        pass


def _keep(slot: dict) -> None:
    """이 회차를 목록에 남김. 번호를 하나 올림.

    규칙  답을 못 본 회차는 안 남김. 중간에 끊긴 것임
    제약  여기서 예외를 올리지 않는다.
          이 함수는 이벤트가 다 나간 뒤에 돈다. 여기서 터지면 답은 이미
          나갔는데 요청이 500 으로 끝난다
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
                "status": slot["status"] or CHOICE,
                "given": slot["given"],
                "want": slot["want"],
                "about": slot["about"],
                "argument": slot["argument"],
                "recipe_id": slot["recipe_id"],
                "candidate_recipe_ids": list(slot["candidate_recipe_ids"]),
                "head": _head(slot["answer"]),
                "steps": _steps(slot["answer"], slot["nodes"]),
                "answer": slot["answer"],
            }
        )
    except Exception:  # noqa: BLE001 — 답이 먼저다.
        pass


def _head(answer: str) -> str:
    """답에서 단계 줄을 뺀 머리말.

    입력  답 문구 전체
    출력  첫 단계 줄 앞까지. 단계가 없으면 답 그대로
    규칙  되묻기 회차면 번호 붙은 후보 목록이 통째로 여기 들어옴. 그 줄은
          단계 줄 꼴이 아님
    제약  문구를 다시 만들지 않는다. 자를 뿐임
    """
    lines = answer.splitlines()
    for index, line in enumerate(lines):
        if _STEP_HEAD.match(line):
            return "\n".join(lines[:index]).strip()
    return answer.strip()


def _steps(answer: str, nodes: list[str]) -> list[dict]:
    """답에 이미 적힌 단계 덩이에 노드 id 를 짝지음.

    입력  답 문구 전체 · step_end 로 지나간 노드 id 목록
    출력  [{"node": ..., "line": ...}]. 단계가 없으면 빈 목록
    규칙  덩이는 답에서 그대로 가져옴. 도구 이름 · 보낸 인자 · 결과 요약이
          이미 그 안에 있음
          단계 줄 꼴이 아닌 줄은 바로 앞 단계에 붙임. 문서 조각이 그 줄임
          노드 id 는 뒤에서부터 짝지음. 앞머리에 도구가 아닌 단계가 붙음.
          해석(node="resolve")과 고르기(node="choice")가 그것이고, 도구
          단계는 늘 그 뒤에 답의 덩이와 같은 수만큼 나옴
          모자라면 빈 문자열. 짝을 못 지어도 덩이는 남김
    제약  단계 줄을 다시 만들지 않는다.
          요약하는 코드가 둘이 되면 한쪽이 raw JSON 을 흘린다.
          workflow_answer 가 만든 문자열만 담는다
    """
    blocks: list[list[str]] = []
    for line in answer.splitlines():
        if _STEP_HEAD.match(line):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)

    lines = ["\n".join(block).rstrip() for block in blocks]
    tail = nodes[-len(lines):] if lines and len(nodes) >= len(lines) else []
    return [
        {"node": tail[index] if index < len(tail) else "", "line": line}
        for index, line in enumerate(lines)
    ]


# ================================================================ 훔쳐보기
def watch_resolve(resolve):
    """`resolve_service.resolve` 를 감싸 축 셋과 후보를 훔쳐봄.

    출력  같은 값을 그대로 돌려주는 함수
    제약  결과를 고치지 않는다.
          판정에 손대는 순간 이 작업이 프롬프트를 안 건드렸다는 말이 거짓이 됨
    """

    def watching(*args, **kwargs):
        result = resolve(*args, **kwargs)
        _note_resolve(result)
        return result

    watching.__wrapped__ = resolve
    return watching


def watch_run(run):
    """`execute_service.run` 을 감싸 실제로 부른 recipe 와 인자를 훔쳐봄.

    출력  같은 이벤트를 그대로 내는 async generator 함수
    규칙  되묻기 뒤 고르기는 해석을 안 거침. 그 회차의 recipe 는 이 자리에서만
          보임
    제약  이벤트를 고치거나 버리지 않는다
    """

    async def watching(recipe_id, argument, *args, **kwargs):
        _note_run(recipe_id, argument)
        async for payload in run(recipe_id, argument, *args, **kwargs):
            yield payload

    watching.__wrapped__ = run
    return watching


def _note_resolve(result) -> None:
    """해석 결과에서 남길 칸만 옮겨 적음. 회차 밖이면 아무 일도 안 함."""
    slot = _SLOT.get()
    if slot is None:
        return
    try:
        slot["status"] = result.get("status") or ""
        slot["given"] = result.get("given")
        slot["want"] = result.get("want")
        slot["about"] = result.get("about")
        slot["recipe_id"] = result.get("recipe_id")
        slot["candidate_recipe_ids"] = list(result.get("candidate_recipe_ids") or [])
        slot["argument"] = result.get("argument") or ""
    except Exception:  # noqa: BLE001 — 훔쳐보다 터져서 해석을 막지 않는다.
        pass


def _note_run(recipe_id, argument) -> None:
    """실제로 부른 recipe 와 인자. 회차 밖이면 아무 일도 안 함."""
    slot = _SLOT.get()
    if slot is None:
        return
    try:
        slot["recipe_id"] = recipe_id
        slot["argument"] = argument or slot["argument"]
    except Exception:  # noqa: BLE001
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
