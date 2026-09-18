"""테스트 탭. 발화별 기능 선택 · 인자 추출 결과를 훑고 한 건씩 들여다본다.

지금은 화면 시안이다. 결과는 app/ui/testing_mock.py 의 가짜 200건이고, 백엔드도
LLM 도 부르지 않는다. 실제 평가가 붙으면 결과를 같은 모양으로 받아
mock_test_results() 자리만 바꾼다.

    제목 · 테스트 세트 · 테스트 실행
    실행 조건 (접힘)
    요약 카드 다섯
    보기 필터 · 발화 검색
    결과 목록 (한 발화 한 줄, 고정 높이) | 선택한 발화 상세 (고정 높이)

**상세는 성공과 실패가 같은 틀이다.** 정답표와 AI 모델 출력을 좌우로 맞대고,
실패면 다른 칸만 강조한다. 틀을 둘로 나누면 성공 화면과 실패 화면이 조용히
어긋난다.

화면 낱말은 사람이 읽는 말로 쓴다. 기능 번호는 「기능 015」로 보이고, 인자는
표시명이 있으면 표시명 아래에 변수명을 작게 단다. 표시명이 없는 인자도 변수명
그대로 나온다 — 새 인자가 들어와도 여기를 안 고친다.

CSS 는 .st-key-test_tab 안으로만 건다. 서비스 화면에 새지 않는다.
"""

import html
from datetime import datetime
from functools import partial

import pandas as pd
import streamlit as st

from app.ui.testing_mock import TEST_SET_LABEL, mock_run_conditions, mock_test_results

# 인자 표시명. 여기 없는 인자는 변수명 그대로 나온다.
# argument 는 기능마다 뜻이 달라 표시명을 두지 않는다.
FIELD_LABELS = {
    "travel_mode": "이동 방식",
    "minutes": "시간",
    "admin_level": "행정구역 단계",
}

# 인자 줄 순서. 여기 없는 인자는 뒤에 나온 순서대로 붙는다.
FIELD_ORDER = ("argument", "travel_mode", "minutes", "admin_level")

STATUS_LABELS = {"SELECT": "선택", "CLARIFY": "되묻기", "NO_MATCH": "해당 없음"}
STAGE_LABELS = {"function": "기능 선택", "input": "인자 추출"}

ALL, FAILED = "전체", "실패만"
FILTERS = (ALL, FAILED, STAGE_LABELS["function"], STAGE_LABELS["input"])

NONE_TEXT = "없음"

# session_state 자리
SELECTED_KEY = "test_selected_id"
RUN_AT_KEY = "test_demo_run_at"
LIST_VIEW_KEY = "test_list_view"     # 표를 마지막으로 그린 (보기, 검색어)
LIST_ROUND_KEY = "test_list_round"   # (보기, 검색어)가 바뀐 횟수. 표 key 에 들어감

# 결과 목록 · 상세의 높이(px). 창 높이에서 위쪽 머리 부분을 뺀 값이다.
LIST_MIN_HEIGHT, LIST_MAX_HEIGHT = 420, 720
HEAD_HEIGHT = 520


# ================================================================ 데이터
def summarize(results: list[dict]) -> dict:
    """요약 카드 다섯 개의 숫자.

    출력  {"total", "passed", "failed", "function", "input"}
          function · input 은 그 단계 때문에 실패한 건수
    """
    failed = [r for r in results if not r["passed"]]
    return {
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "function": sum(1 for r in failed if r.get("failure_stage") == "function"),
        "input": sum(1 for r in failed if r.get("failure_stage") == "input"),
    }


def _squash(text: str) -> str:
    """검색 비교용 글자. 띄어쓰기를 빼고 소문자로."""
    return "".join(str(text).split()).lower()


def filter_results(results: list[dict], view: str, query: str = "") -> list[dict]:
    """보기 필터와 발화 검색을 건 목록.

    입력  view 는 FILTERS 중 하나. 모르는 값이면 전체
    출력  원래 순서를 지킨 부분 목록
    규칙  실패만은 성공이 아닌 것 전부. 기능 선택 · 인자 추출은 그 단계에서 실패한 것
          검색은 띄어쓰기를 무시한 부분 일치. 빈 검색어는 거르지 않음
    """
    if view == FAILED:
        shown = [r for r in results if not r["passed"]]
    elif view in STAGE_LABELS.values():
        stage = next(k for k, v in STAGE_LABELS.items() if v == view)
        shown = [r for r in results if not r["passed"] and r.get("failure_stage") == stage]
    else:
        shown = list(results)

    needle = _squash(query or "")
    if needle:
        shown = [r for r in shown if needle in _squash(r["utterance"])]
    return shown


def verdict_label(result: dict) -> str:
    """최종 판정 한 마디. "성공" 또는 "실패 · 기능 선택" 꼴."""
    if result["passed"]:
        return "성공"
    stage = STAGE_LABELS.get(result.get("failure_stage"))
    return f"실패 · {stage}" if stage else "실패"


def display_value(value) -> str:
    """인자 값 하나를 화면 글자로.

    규칙  None 은 "없음". 목록은 " · " 로 이음. 빈 목록도 "없음"
    """
    if value is None:
        return NONE_TEXT
    if isinstance(value, (list, tuple)):
        return " · ".join(str(v) for v in value) if value else NONE_TEXT
    return str(value)


def field_rows(result: dict) -> list[dict]:
    """인자 비교 줄. 정답표와 모델 출력에 나온 인자를 빠짐없이.

    출력  [{"name", "label", "answer", "model", "differs", "graded"}]
    규칙  FIELD_ORDER 순서가 먼저, 그 밖의 인자는 정답표 · 모델 출력에 나온 순서
          한쪽에만 있는 인자는 다른 쪽을 None 으로 봄
          label 은 FIELD_LABELS 에 없으면 변수명 그대로
    """
    answer = result["answer"].get("inputs") or {}
    model = result["model_output"].get("inputs") or {}
    names = [n for n in FIELD_ORDER if n in answer or n in model]
    for name in [*answer, *model]:
        if name not in names:
            names.append(name)

    graded = set(result.get("graded_fields") or ())
    return [
        {
            "name": name,
            "label": FIELD_LABELS.get(name, name),
            "answer": answer.get(name),
            "model": model.get(name),
            "differs": answer.get(name) != model.get(name),
            "graded": name in graded,
        }
        for name in names
    ]


def list_frame(results: list[dict]) -> pd.DataFrame:
    """결과 목록 표. 한 발화 한 줄, 칸 넷."""
    return pd.DataFrame(
        {
            "번호": [f"{r['id']:03d}" for r in results],
            "발화": [r["utterance"] for r in results],
            "결과": ["성공" if r["passed"] else "실패" for r in results],
            "판정": ["" if r["passed"] else STAGE_LABELS.get(r.get("failure_stage"), "") for r in results],
        }
    )


def list_height(ratios: dict) -> int:
    """결과 목록 · 상세 칸의 높이(px). 창 높이를 따라가되 범위 안에서."""
    viewport = int(ratios.get("viewport_height") or 0)
    return max(LIST_MIN_HEIGHT, min(LIST_MAX_HEIGHT, viewport - HEAD_HEIGHT))


# ================================================================ 마크업
def _esc(value) -> str:
    """HTML 에 넣을 글자."""
    return html.escape(str(value))


def summary_markup(summary: dict) -> str:
    """요약 카드 다섯."""
    total = summary["total"] or 1

    def card(label, number, tone="", note=""):
        note_html = f'<div class="tt-kpi-note">{_esc(note)}</div>' if note else ""
        return (
            f'<div class="tt-kpi {tone}"><div class="tt-kpi-label">{_esc(label)}</div>'
            f'<div class="tt-kpi-num">{number}</div>{note_html}</div>'
        )

    return '<div class="tt-kpis">' + "".join(
        [
            card("전체", summary["total"], note="발화"),
            card("성공", summary["passed"], "ok", f"{summary['passed'] / total:.1%}"),
            card("실패", summary["failed"], "ng", f"{summary['failed'] / total:.1%}"),
            card(STAGE_LABELS["function"], summary["function"], "cause", "실패 원인"),
            card(STAGE_LABELS["input"], summary["input"], "cause", "실패 원인"),
        ]
    ) + "</div>"


def conditions_markup(conditions: dict) -> str:
    """실행 조건 네 줄."""
    rows = "".join(
        f'<div class="tt-cond-k">{_esc(k)}</div><div class="tt-cond-v">{_esc(v)}</div>'
        for k, v in conditions.items()
    )
    return f'<div class="tt-cond">{rows}</div>'


def _value_markup(value) -> str:
    """값 하나. 없음은 흐리게."""
    text = display_value(value)
    css = "tt-val tt-none" if text == NONE_TEXT else "tt-val"
    return f'<span class="{css}">{_esc(text)}</span>'


def _function_markup(side: dict) -> str:
    """기능 번호와 설명. 고르지 않았으면 선택 없음."""
    label = side.get("function_label")
    if not label:
        return '<div class="tt-fn tt-none">선택 없음</div>'
    desc = side.get("function_description") or ""
    return f'<div class="tt-fn">{_esc(label)}</div><div class="tt-desc">{_esc(desc)}</div>'


def _key_markup(label: str, name: str | None = None) -> str:
    """줄 머리. 표시명이 변수명과 다르면 변수명을 아래에 작게."""
    sub = f'<div class="tt-var">{_esc(name)}</div>' if name and name != label else ""
    return f'<div class="tt-c tt-key"><div class="tt-key-label">{_esc(label)}</div>{sub}</div>'


def _pair_markup(key_html: str, answer_html: str, model_html: str, *, differs: bool, graded: bool = True) -> str:
    """비교 한 줄. 줄 머리 · 정답표 · AI 모델 출력.

    규칙  채점에 쓰는 칸이 다르면 모델 출력 칸을 강조하고 「차이」를 닮
          채점에 안 쓰는 칸은 흐리게 둠. 값이 다르면 강조 대신 「채점 제외」만 닮
    """
    tag, cell = "", "tt-c tt-model"
    row = "" if graded else " tt-ungraded"
    if differs and graded:
        cell += " tt-diff"
        tag = '<span class="tt-tag tt-tag-diff">차이</span>'
    elif differs:
        tag = '<span class="tt-tag tt-tag-muted">채점 제외</span>'
    return (
        f'<div class="tt-row{row}">{key_html}'
        f'<div class="tt-c tt-answer">{answer_html}</div>'
        f'<div class="{cell}">{model_html}{tag}</div></div>'
    )


def _extra_markup(model: dict) -> str:
    """AI 모델 출력의 부가 정보. 판정 상태 · 후보 기능 · 판단."""
    status = model.get("status")
    status_text = STATUS_LABELS.get(status, status or NONE_TEXT)
    picked = model.get("function_id")
    chips = "".join(
        f'<span class="tt-chip{" tt-chip-on" if cid == picked else ""}">기능 {_esc(cid.split("_")[-1])}</span>'
        for cid in model.get("candidate_ids") or []
    ) or f'<span class="tt-val tt-none">{NONE_TEXT}</span>'
    reason = model.get("reason") or NONE_TEXT
    return (
        '<div class="tt-extra">'
        '<div class="tt-extra-head">AI 모델 출력 · 판단 내용</div>'
        f'<div class="tt-kv"><div class="tt-kv-k">모델 판정 상태</div>'
        f'<div class="tt-kv-v"><span class="tt-status">{_esc(status_text)}</span></div></div>'
        f'<div class="tt-kv"><div class="tt-kv-k">후보 기능</div><div class="tt-kv-v">{chips}</div></div>'
        f'<div class="tt-kv"><div class="tt-kv-k">모델 판단</div>'
        f'<div class="tt-kv-v tt-reason">{_esc(reason)}</div></div>'
        "</div>"
    )


def detail_markup(result: dict) -> str:
    """선택한 발화 상세. 성공 · 실패가 같은 틀.

    규칙  맨 위 한 줄에 번호 · 발화 · 판정
          정답표 | AI 모델 출력 두 칸에 기능 번호 · 설명과 인자 전부
          그 아래 AI 모델 출력의 판정 상태 · 후보 기능 · 판단
    """
    answer, model = result["answer"], result["model_output"]
    tone = "ok" if result["passed"] else "ng"
    head = (
        '<div class="tt-head">'
        f'<span class="tt-no">{result["id"]:03d}</span>'
        f'<span class="tt-utt">{_esc(result["utterance"])}</span>'
        f'<span class="tt-badge {tone}">● {_esc(verdict_label(result))}</span>'
        "</div>"
    )

    rows = [
        '<div class="tt-row tt-cols">'
        '<div class="tt-c"></div>'
        '<div class="tt-c tt-col-answer">✓ 정답표</div>'
        '<div class="tt-c tt-col-model">AI 모델 출력</div>'
        "</div>",
        '<div class="tt-sec">기능 선택</div>',
        _pair_markup(
            _key_markup("기능"),
            _function_markup(answer),
            _function_markup(model),
            differs=answer.get("function_id") != model.get("function_id"),
        ),
        '<div class="tt-sec">인자 추출</div>',
    ]
    for f in field_rows(result):
        rows.append(
            _pair_markup(
                _key_markup(f["label"], f["name"]),
                _value_markup(f["answer"]),
                _value_markup(f["model"]),
                differs=f["differs"],
                graded=f["graded"],
            )
        )

    return f'{head}<div class="tt-cmp">{"".join(rows)}</div>{_extra_markup(model)}'


# ================================================================ 그리기
def _render_header() -> None:
    """제목 · 테스트 세트 · 테스트 실행 · 실행 조건.

    규칙  테스트 실행은 시안 결과를 다시 보이고 시각만 남김
    제약  백엔드 · LLM 을 부르지 않는다
    """
    title, picker, run = st.columns([5, 3, 1.2], vertical_alignment="bottom")
    with picker:
        st.selectbox("테스트 세트", [TEST_SET_LABEL], key="test_set", persist_state="page")
    with run:
        if st.button("테스트 실행", type="primary", key="test_run", width="stretch"):
            st.session_state[RUN_AT_KEY] = datetime.now().strftime("%H:%M:%S")
            st.toast("화면 시안 결과를 다시 표시했습니다.")
    with title:
        run_at = st.session_state.get(RUN_AT_KEY)
        sub = "발화별 기능 선택 및 인자 추출 결과" + (f" · {run_at} 실행" if run_at else "")
        st.markdown(
            f'<div class="tt-title">AI 기능 테스트</div><div class="tt-sub">{_esc(sub)}</div>',
            unsafe_allow_html=True,
        )

    with st.expander("실행 조건", expanded=False):
        st.markdown(conditions_markup(mock_run_conditions()), unsafe_allow_html=True)


def _render_filters(summary: dict) -> tuple[str, str]:
    """보기 필터와 발화 검색.

    출력  (보기, 검색어)
    규칙  필터 글자 옆에 그 보기의 건수를 붙임
    """
    counts = {
        ALL: summary["total"],
        FAILED: summary["failed"],
        STAGE_LABELS["function"]: summary["function"],
        STAGE_LABELS["input"]: summary["input"],
    }
    left, right = st.columns([3, 2], vertical_alignment="center")
    with left:
        view = st.segmented_control(
            "보기",
            FILTERS,
            default=ALL,
            required=True,
            format_func=lambda v: f"{v}  {counts[v]}",
            key="test_filter",
            label_visibility="collapsed",
            persist_state="page",
        )
    with right:
        query = st.text_input(
            "발화 검색",
            key="test_query",
            placeholder="발화 검색",
            icon=":material/search:",
            label_visibility="collapsed",
            persist_state="page",
        )
    return view or ALL, query or ""


def _result_tone(value: str) -> str:
    """결과 칸 글자색."""
    return "color: #2EB67D; font-weight: 600;" if value == "성공" else "color: #E5534B; font-weight: 600;"


def _keep_row_selected(key: str, ids: list[int]) -> None:
    """표에서 누른 것을 한 줄 선택으로 맞춤. 표의 on_select 콜백.

    입력  key 는 표의 key, ids 는 표 줄 순서대로의 결과 번호
    규칙  칸을 눌렀으면 그 칸의 줄을 고름
          고른 줄을 다시 눌러 선택이 비었으면 지금 상세의 줄을 다시 고름. 상세가 늘
          표의 강조 줄과 같게 둠
    """
    selection = (st.session_state.get(key) or {}).get("selection") or {}
    cells = selection.get("cells") or []
    if cells:
        row = cells[0][0]
    elif selection.get("rows"):
        return
    elif st.session_state.get(SELECTED_KEY) in ids:
        row = ids.index(st.session_state[SELECTED_KEY])
    else:
        row = 0
    st.session_state[key] = {"selection": {"rows": [row], "columns": [], "cells": []}}


def _list_key(view: str, query: str) -> str:
    """결과 표의 key. 보기나 검색어가 바뀔 때만 새로 붙음.

    규칙  같은 보기 안에서는 key 가 그대로라 표가 안 새로 붙고 스크롤 자리가 남음
          보기 · 검색어가 바뀌면 key 가 바뀌어 표가 새로 붙고 selection_default 가 다시 먹음.
          전에 봤던 보기로 돌아와도 그때의 선택이 아니라 지금 고른 발화를 따름
    """
    round_ = st.session_state.get(LIST_ROUND_KEY, 0)
    if st.session_state.get(LIST_VIEW_KEY) != (view, query):
        round_ += 1
        st.session_state[LIST_VIEW_KEY] = (view, query)
        st.session_state[LIST_ROUND_KEY] = round_
    return f"test_list_{round_}"


def _render_result_list(shown: list[dict], view: str, query: str, height: int) -> dict | None:
    """결과 목록. 한 발화 한 줄, 고정 높이 안에서 스크롤.

    출력  지금 고른 결과. 목록이 비었으면 None
    규칙  행 고르기는 st.dataframe 의 행 선택. 발화 글자를 눌러도 골라지게 칸 선택을
          함께 켜고, 칸을 누르면 _keep_row_selected 가 그 줄 선택으로 바꿈
          표 key 는 _list_key 가 정함. 같은 보기 안에서 행을 눌러도 표가 새로 안 붙으므로
          스크롤 자리가 그대로임
          보기를 바꾸면 고른 발화가 새 목록에 있으면 그 줄, 없으면 첫 줄을 고름
    제약  single-row-required 를 쓰지 않는다.
          칸을 누르면 행 선택이 비었다고 보고 첫 줄로 되돌림. 발화를 눌렀는데 001 이 뜸
    """
    st.markdown(
        f'<div class="tt-pane-title">테스트 결과 <span>{len(shown)}건</span></div>',
        unsafe_allow_html=True,
    )
    if not shown:
        with st.container(height=height, border=True):
            st.markdown('<div class="tt-empty">조건에 맞는 발화가 없습니다.</div>', unsafe_allow_html=True)
        return None

    remembered = st.session_state.get(SELECTED_KEY)
    default = next((i for i, r in enumerate(shown) if r["id"] == remembered), 0)

    styled = list_frame(shown).style.map(_result_tone, subset=["결과"]).map(
        lambda v: "color: #E5534B;" if v else "", subset=["판정"]
    )
    key = _list_key(view, query)
    event = st.dataframe(
        styled,
        key=key,
        on_select=partial(_keep_row_selected, key, [r["id"] for r in shown]),
        selection_mode=["single-row", "single-cell"],
        selection_default={"selection": {"rows": [default]}},
        hide_index=True,
        height=height,
        row_height=32,
        width="stretch",
        column_config={
            "번호": st.column_config.TextColumn("번호", width=56),
            "발화": st.column_config.TextColumn("발화", width="large"),
            "결과": st.column_config.TextColumn("결과", width=72),
            "판정": st.column_config.TextColumn("판정", width=96),
        },
    )

    rows = event.selection.rows if event is not None else []
    picked = rows[0] if rows and 0 <= rows[0] < len(shown) else default
    st.session_state[SELECTED_KEY] = shown[picked]["id"]
    return shown[picked]


def _render_result_detail(result: dict | None, height: int) -> None:
    """선택한 발화 상세. 고정 높이 안에서 스크롤."""
    st.markdown('<div class="tt-pane-title">선택한 발화 상세</div>', unsafe_allow_html=True)
    with st.container(height=height, border=True, key="test_detail"):
        if result is None:
            st.markdown('<div class="tt-empty">목록에서 발화를 고르면 여기 나옵니다.</div>', unsafe_allow_html=True)
            return
        st.markdown(detail_markup(result), unsafe_allow_html=True)


def render_test_tab(ratios: dict) -> None:
    """테스트 탭 전체.

    입력  config.layout_ratios() 결과. 창 높이로 목록 높이를 정함
    제약  백엔드 · LLM 을 부르지 않는다. 결과는 mock_test_results() 하나에서만 옴
    """
    results = mock_test_results()
    summary = summarize(results)

    with st.container(key="test_tab"):
        st.markdown(panel_css(), unsafe_allow_html=True)
        _render_header()
        st.markdown(summary_markup(summary), unsafe_allow_html=True)
        view, query = _render_filters(summary)
        shown = filter_results(results, view, query)

        height = list_height(ratios)
        left, right = st.columns([63, 37], gap="medium")
        with left:
            selected = _render_result_list(shown, view, query, height)
        with right:
            _render_result_detail(selected, height)


# ================================================================ CSS
def panel_css() -> str:
    """테스트 탭 전용 CSS. .st-key-test_tab 안에만 걸림.

    규칙  글자색은 테마를 따름(inherit). 선 · 바탕은 회색 반투명이라 밝은 테마 · 어두운
          테마 어느 쪽에서도 읽힘. 성공 · 실패 · AI 모델 출력 강조색만 고정
    """
    return """<style>
.st-key-test_tab {
  --tt-ok: #2EB67D;
  --tt-ng: #E5534B;
  --tt-ai: #14B8A6;
  --tt-line: rgba(140, 150, 165, 0.24);
  --tt-soft: rgba(140, 150, 165, 0.08);
  --tt-softer: rgba(140, 150, 165, 0.045);
  gap: 0.7rem;
}
.st-key-test_tab .tt-title { font-size: 1.35rem; font-weight: 700; line-height: 1.3; }
.st-key-test_tab .tt-sub { font-size: 0.82rem; opacity: 0.6; margin: 0.1rem 0 0.6rem; }

/* ---------------------------------------------- 실행 조건 */
.st-key-test_tab .tt-cond {
  display: grid; grid-template-columns: 7.5rem minmax(0, 1fr);
  row-gap: 0.35rem; column-gap: 0.8rem; font-size: 0.82rem;
}
.st-key-test_tab .tt-cond-k { opacity: 0.6; }
.st-key-test_tab .tt-cond-v {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78rem; overflow-wrap: anywhere;
}

/* ---------------------------------------------- 요약 카드 */
.st-key-test_tab .tt-kpis { display: flex; gap: 0.7rem; margin-bottom: 0.8rem; }
.st-key-test_tab .tt-kpi {
  flex: 1 1 0; min-width: 0;
  border: 1px solid var(--tt-line); border-radius: 10px;
  background: var(--tt-softer);
  padding: 0.55rem 0.9rem 0.6rem;
  display: grid; grid-template-columns: 1fr auto; align-items: end; row-gap: 0.1rem;
}
.st-key-test_tab .tt-kpi-label { grid-column: 1 / -1; font-size: 0.78rem; opacity: 0.7; }
.st-key-test_tab .tt-kpi-num { font-size: 1.6rem; font-weight: 700; line-height: 1.15; font-variant-numeric: tabular-nums; }
.st-key-test_tab .tt-kpi-note { font-size: 0.75rem; opacity: 0.6; padding-bottom: 0.2rem; }
.st-key-test_tab .tt-kpi.ok { box-shadow: inset 3px 0 0 var(--tt-ok); }
.st-key-test_tab .tt-kpi.ok .tt-kpi-num { color: var(--tt-ok); }
.st-key-test_tab .tt-kpi.ng { box-shadow: inset 3px 0 0 var(--tt-ng); }
.st-key-test_tab .tt-kpi.ng .tt-kpi-num { color: var(--tt-ng); }
.st-key-test_tab .tt-kpi.cause .tt-kpi-label::before {
  content: ""; display: inline-block; width: 0.45rem; height: 0.45rem; border-radius: 50%;
  background: var(--tt-ng); opacity: 0.75; margin-right: 0.4rem; vertical-align: 0.05rem;
}

/* 표 세로 스크롤바. 기본 얇은 막대는 마우스로 잡기 어렵다. */
.st-key-test_tab [data-testid="stDataFrame"] .dvn-scroller { scrollbar-width: auto; }
.st-key-test_tab [data-testid="stDataFrame"] .dvn-scroller::-webkit-scrollbar { width: 12px; }

/* ---------------------------------------------- 두 칸 제목 */
.st-key-test_tab .tt-pane-title { font-size: 0.85rem; font-weight: 600; opacity: 0.85; margin-top: 0.3rem; }
.st-key-test_tab .tt-pane-title span { font-weight: 400; opacity: 0.65; margin-left: 0.3rem; }
.st-key-test_tab .tt-empty { opacity: 0.6; font-size: 0.9rem; padding: 1.5rem 0.5rem; text-align: center; }

/* ---------------------------------------------- 상세 머리 한 줄 */
.st-key-test_tab .tt-head {
  display: flex; align-items: flex-start; gap: 0.6rem;
  padding: 0.1rem 0 0.75rem; border-bottom: 1px solid var(--tt-line); margin-bottom: 0.8rem;
}
.st-key-test_tab .tt-no {
  flex: 0 0 auto; font-size: 0.78rem; opacity: 0.55; padding-top: 0.28rem;
  font-variant-numeric: tabular-nums;
}
.st-key-test_tab .tt-utt { flex: 1 1 auto; min-width: 0; font-size: 1.08rem; font-weight: 600; line-height: 1.45; overflow-wrap: anywhere; }
.st-key-test_tab .tt-badge {
  flex: 0 0 auto; white-space: nowrap; font-size: 0.8rem; font-weight: 600;
  padding: 0.18rem 0.6rem; border-radius: 999px; margin-top: 0.1rem;
}
.st-key-test_tab .tt-badge.ok { color: var(--tt-ok); background: rgba(46, 182, 125, 0.12); }
.st-key-test_tab .tt-badge.ng { color: var(--tt-ng); background: rgba(229, 83, 75, 0.12); }

/* ---------------------------------------------- 정답표 | AI 모델 출력 */
.st-key-test_tab .tt-cmp {
  border: 1px solid var(--tt-line); border-radius: 10px; overflow: hidden; font-size: 0.88rem;
}
.st-key-test_tab .tt-row {
  display: grid; grid-template-columns: 6.6rem minmax(0, 1fr) minmax(0, 1.08fr);
  border-top: 1px solid var(--tt-line);
}
.st-key-test_tab .tt-row.tt-cols { border-top: 0; }
.st-key-test_tab .tt-c { padding: 0.5rem 0.7rem; min-width: 0; overflow-wrap: anywhere; position: relative; }
.st-key-test_tab .tt-model { background: rgba(20, 184, 166, 0.04); }
.st-key-test_tab .tt-col-answer, .st-key-test_tab .tt-col-model {
  font-size: 0.8rem; font-weight: 700; letter-spacing: 0.01em; padding-top: 0.55rem; padding-bottom: 0.45rem;
}
.st-key-test_tab .tt-col-answer { background: var(--tt-soft); box-shadow: inset 0 3px 0 rgba(140, 150, 165, 0.55); }
.st-key-test_tab .tt-col-model { background: rgba(20, 184, 166, 0.10); box-shadow: inset 0 3px 0 var(--tt-ai); color: var(--tt-ai); }
.st-key-test_tab .tt-sec {
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; opacity: 0.6;
  padding: 0.45rem 0.7rem 0.3rem; border-top: 1px solid var(--tt-line); background: var(--tt-softer);
}
.st-key-test_tab .tt-key { background: var(--tt-softer); }
.st-key-test_tab .tt-key-label { font-weight: 600; font-size: 0.82rem; }
.st-key-test_tab .tt-var {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.7rem; opacity: 0.55; margin-top: 0.1rem;
}
.st-key-test_tab .tt-fn { font-weight: 700; }
.st-key-test_tab .tt-desc { font-size: 0.8rem; opacity: 0.72; line-height: 1.45; margin-top: 0.2rem; }
.st-key-test_tab .tt-none { opacity: 0.45; }
.st-key-test_tab .tt-diff { background: rgba(229, 83, 75, 0.13); box-shadow: inset 3px 0 0 var(--tt-ng); }
.st-key-test_tab .tt-diff .tt-val, .st-key-test_tab .tt-diff .tt-fn { color: var(--tt-ng); font-weight: 700; opacity: 1; }
.st-key-test_tab .tt-ungraded .tt-answer, .st-key-test_tab .tt-ungraded .tt-model { opacity: 0.7; }
.st-key-test_tab .tt-tag {
  position: absolute; top: 0.45rem; right: 0.5rem;
  font-size: 0.66rem; font-weight: 600; padding: 0.05rem 0.4rem; border-radius: 999px;
}
.st-key-test_tab .tt-tag-diff { color: var(--tt-ng); border: 1px solid rgba(229, 83, 75, 0.5); }
.st-key-test_tab .tt-tag-muted { border: 1px solid var(--tt-line); opacity: 0.85; }
.st-key-test_tab .tt-model:has(.tt-tag) .tt-val,
.st-key-test_tab .tt-model:has(.tt-tag) .tt-desc { padding-right: 3.8rem; display: inline-block; }

/* ---------------------------------------------- AI 모델 출력 부가 정보 */
.st-key-test_tab .tt-extra {
  margin-top: 0.8rem; border: 1px solid var(--tt-line); border-radius: 10px;
  box-shadow: inset 3px 0 0 var(--tt-ai); padding: 0.55rem 0.8rem 0.65rem 1rem; font-size: 0.85rem;
}
.st-key-test_tab .tt-extra-head { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; color: var(--tt-ai); margin-bottom: 0.4rem; }
.st-key-test_tab .tt-kv { display: grid; grid-template-columns: 6.2rem minmax(0, 1fr); column-gap: 0.6rem; padding: 0.28rem 0; }
.st-key-test_tab .tt-kv-k { opacity: 0.6; font-size: 0.8rem; padding-top: 0.08rem; }
.st-key-test_tab .tt-kv-v { min-width: 0; display: flex; flex-wrap: wrap; gap: 0.3rem; }
.st-key-test_tab .tt-status { font-weight: 600; }
.st-key-test_tab .tt-chip {
  font-size: 0.75rem; padding: 0.08rem 0.5rem; border-radius: 999px;
  border: 1px solid var(--tt-line); background: var(--tt-softer); white-space: nowrap;
}
.st-key-test_tab .tt-chip-on { border-color: var(--tt-ai); color: var(--tt-ai); font-weight: 600; }
.st-key-test_tab .tt-reason {
  display: block; line-height: 1.55; font-size: 0.83rem;
  background: var(--tt-softer); border-radius: 6px; padding: 0.4rem 0.55rem; overflow-wrap: anywhere;
}
</style>"""
