"""저쪽 화면에서 넣은 발화를 이 화면이 따라 그린다.

**방향은 하나다.** 저쪽에서 넣고 여기가 따라 그린다. 반대 방향은 저쪽 코드를
고쳐야 하므로 없다.

시연에서 두 화면이 나란히 선다.

    저쪽 화면    지도 · 채팅 · 실행 결과       쓰는 사람이 보는 것
    Streamlit    온톨로지 그래프 · 고른 경로    그 뒤에서 무슨 일이 일어났나

**깜빡임을 줄이는 것이 이 파일의 일이다.** 주기 갱신을 전체 rerun 으로 돌리면
3초마다 그래프 iframe 이 다시 붙고 시연 중에 스크롤이 튄다. 그래서 두 단으로
가른다.

    부분 갱신(fragment)   주기마다 도는 것. GET /recent 하나와 상태 한 줄뿐
    전체 rerun            회차 번호가 바뀐 그때 한 번. 그래프와 패널을 다시 그림

번호가 그대로면 아무것도 다시 안 그린다. 조각 안의 상태 한 줄만 같은 값으로
다시 찍힌다.

**그래프는 좌표가 고정이라 다시 그려도 모양이 안 바뀐다.** 전체 rerun 이
돌아도 노드가 안 움직인다 — `layout.json` 과 `neato -n` 이 그것을 지킨다.
움직였다면 배치를 건드린 것이다.

**끄면 지금까지의 화면과 똑같이 동작한다.** 조각을 아예 안 만들므로 주기
요청도 안 나가고, 발화 넣기와 노드 등록 흐름에 손대는 것이 없다.
"""

import time

import streamlit as st

from demo.ui import api_client, config, styles
from demo.ui.api_client import ApiError

# 따라 보기 켜짐/꺼짐. 체크박스가 이 자리에 쓴다.
FOLLOW_KEY = "follow_on"

# 마지막으로 그린 회차 번호. 이것과 서버의 seq 를 견주어 새 것을 가른다.
SEEN_KEY = "follow_seq"

LABEL = "KRRI_ASAP 연동"

# 상태 한 줄. 조각이 주기마다 같은 값으로 다시 찍는 유일한 것이다.
WAITING = "연동 중 · {seq}회차"
IDLE = "연동 중 · 아직 들어온 발화가 없습니다"


def follow_view(turn: dict) -> dict:
    """회차 하나를 화면이 아는 장면으로.

    입력  GET /recent 의 turns 한 건
    출력  main 의 view. kind 는 "resolve"
    규칙  kind 를 "resolve" 로 둠. 그래야 이미 있는 강조가 그대로 돎.
          render_mode 가 resolve 모드를 고르고 recipe_ids_to_show 가
          고른 것과 후보들을 집음
          answer 와 단계는 follow 칸에 그대로 둠. 여기서 다시 만들지 않음
    제약  강조 규칙을 새로 만들지 않는다.
          발화를 여기서 넣었을 때와 같은 길로 그려야 두 장면이 안 갈린다
    """
    return {
        "kind": "resolve",
        "utterance": turn.get("utterance") or "",
        "result": {
            "recipe_id": turn.get("recipe_id"),
            "candidate_recipe_ids": turn.get("candidate_recipe_ids") or [],
        },
        "follow": turn,
    }


def head_of(turn: dict) -> str:
    """답에서 단계 줄을 뺀 머리말.

    입력  회차 한 건
    출력  머리말. 되묻기 회차면 번호 붙은 후보 목록이 여기 들어옴
    규칙  서버가 이미 갈라 놓은 head 를 씀. 없으면 답 전체
    제약  여기서 다시 가르지 않는다.
          가르는 규칙이 둘이 되면 단계가 여러 줄인 회차(문서 조각)에서
          한쪽만 어긋난다
    """
    return turn.get("head") or (turn.get("answer") or "").strip()


def at_text(turn: dict) -> str:
    """그 회차가 언제 들어왔는지. 시:분:초."""
    try:
        return time.strftime("%H:%M:%S", time.localtime(turn.get("at") or 0))
    except (OverflowError, OSError, ValueError):
        return ""


def render_follow_panel(view) -> None:
    """따라 그린 회차 하나. 발화 · 답 문구 · 단계.

    입력  지금 장면
    규칙  따라 보기가 꺼져 있으면 아무것도 안 그림
          전체 rerun 때만 돎. 주기 갱신은 이 함수를 안 부름
    제약  결과 값을 여기서 요약하지 않는다.
          단계 줄은 저쪽 화면에 이미 나간 문자열 그대로임. 다시 만들면
          그쪽에서 걸러진 geojson 이 이쪽으로 샌다
    """
    if not st.session_state.get(FOLLOW_KEY):
        return

    turn = view.get("follow") if isinstance(view, dict) else None
    if not turn:
        return

    st.caption(f"{at_text(turn)}  {turn.get('status') or ''}")

    head = head_of(turn)
    if head:
        # 등폭으로 낸다. 되묻기 후보 목록과 단계 줄이 칸을 맞춰 적혀 있어
        # 마크다운으로 내면 연속 공백이 접힌다.
        st.code(head, language=None)

    steps = turn.get("steps") or []
    if steps:
        st.code("\n".join(step["line"] for step in steps), language=None)


def render_follow_switch() -> None:
    """따라 보기 스위치와 주기 갱신 조각.

    규칙  꺼져 있으면 조각을 아예 안 만듦. 주기 요청도 안 나감
    제약  화면 맨 끝에서 부른다.
          조각이 새 회차를 보면 전체 rerun 을 건다. 앞쪽에서 부르면 Run 클릭이
          그 rerun 에 삼켜져 발화가 안 들어간다
    """
    st.checkbox(LABEL, key=FOLLOW_KEY)
    if st.session_state.get(FOLLOW_KEY):
        _poll()


@st.fragment(run_every=config.FOLLOW_INTERVAL_SECONDS)
def _poll() -> None:
    """주기마다 도는 것. GET /recent 하나와 상태 한 줄뿐.

    규칙  번호가 그대로면 상태 한 줄만 다시 찍고 끝냄. 그래프도 패널도 안 건드림
          새 회차가 오면 장면을 갈아끼우고 전체 rerun 을 걸어 한 번에 다시 그림
          서버가 다시 떠서 번호가 되감기면 본 번호를 지움. 안 지우면 새 회차가
          영영 작아 보여 화면이 멈춤
          호출이 실패해도 조용히 한 줄만 남김. 3초마다 오류 상자를 띄우면
          시연이 못 볼 화면이 됨
    """
    seen = st.session_state.get(SEEN_KEY)

    try:
        payload = api_client.recent(seen)
    except ApiError as exc:
        st.markdown(styles.note_markup(f"따라 보기 — {exc}"), unsafe_allow_html=True)
        return

    seq = payload.get("seq") or 0
    if seen is not None and seq < seen:
        st.session_state[SEEN_KEY] = None
        return

    turns = payload.get("turns") or []
    if not turns:
        st.caption(WAITING.format(seq=seq) if seq else IDLE)
        return

    st.session_state[SEEN_KEY] = seq
    st.session_state["view"] = follow_view(turns[-1])
    st.rerun()
