"""테스트 탭. 정답표로 발화 해석을 재고, 발화별 기능 선택 · 인자 추출 결과를 훑고 한 건씩 들여다본다.

평가는 dev/evaluation 이 한다. 이 탭은 정답표를 고르고, 「테스트 실행」을 누르면
dev/evaluation/runner.run_dataset 을 부르고, 돌아온 결과를 그린다.

    제목 · 테스트 세트 · 실행 기록 · 테스트 실행
    실행 개요 (정답표 · 시각 · 걸린 시간 · 발화 수 · 지표 · GPU)
    실행 조건 (접힘)
    요약 카드 다섯
    기능별 결과 (접힘)
    보기 필터 · 기능 고르기 · 발화 검색
    결과 목록 (한 발화 한 줄, 고정 높이) | 선택한 발화 상세 (고정 높이)

낱말은 dev/evaluation/test_runs 머리 주석과 같다 — 정답표 한 벌(Test Suite)은 「테스트 세트」,
한 번 잰 것(Test Run)은 「실행 기록」, 발화 하나의 결과(Case Result)는 「발화 결과」다.

**새로 잰 결과와 불러온 실행 기록이 같은 길로 그려진다.** 실행 기록을 고르면 test_runs.load_run 이
돌려준 결과 한 벌을 방금 잰 결과와 같은 자리(RESULT_KEY)에 둔다. 그리는 함수가 따로 없다.

**여기서 채점하지 않는다.** 성공 · 실패 · 실패 단계(passed · failure_stage) · 기능이 맞았나
(recipe_correct) · 정답표에 적은 값마다 맞았나(spoken_fields) 는 runner 결과에 이미 있다.
이 탭은 그 칸을 읽어 글자와 색으로 바꾼다. 값끼리 맞대지 않는다.

**LLM 은 「테스트 실행」을 누를 때만 부른다.** 결과는 session_state 에 두고 필터 · 검색 ·
행 선택 · 탭 전환은 그것만 다시 그린다.

**상세는 성공과 실패가 같은 틀이다.** 정답표와 AI 모델 출력을 좌우로 맞대고,
실패면 틀린 칸만 강조한다. 인자는 정답표에 적은 것과 모델이 낸 것을 빠짐없이 보인다.
정답표에 안 적은 인자는 채점 제외로 흐리게 둔다.

화면 낱말은 사람이 읽는 말로 쓴다. 기능 번호는 「기능 015」로 보이고, 인자는
표시명이 있으면 표시명 아래에 변수명을 작게 단다. 표시명이 없는 인자도 변수명
그대로 나온다 — 새 인자가 들어와도 여기를 안 고친다.

CSS 는 .st-key-test_tab 안으로만 건다. 서비스 화면에 새지 않는다.
"""

import datetime
import html
import re
from functools import partial
from pathlib import Path

import pandas as pd
import streamlit as st

from dev.evaluation import suite as evaluation_suite

# 인자 표시명. 여기 없는 인자는 변수명 그대로 나온다.
# argument 는 기능마다 뜻이 달라 표시명을 두지 않는다.
FIELD_LABELS = {
    "travel_mode": "이동 방식",
    "minutes": "시간",
    "admin_level": "행정구역 단계",
}

STATUS_LABELS = {"SELECT": "선택", "CLARIFY": "되묻기", "NO_MATCH": "해당 없음"}
# runner 결과의 failure_stage 값 -> 화면 글자
STAGE_LABELS = {"function": "기능 선택", "input": "인자 추출", "scope": "범위 밖 처리", "error": "실행 오류"}

# runner 결과의 outcome · materialize 판정 -> 화면 글자. 여기 없는 값은 그대로 나온다.
OUTCOME_LABELS = {
    **STATUS_LABELS,
    "READY": "실행 준비됨",
    "MISSING_ARGUMENT": "인자 부족",
    "MISSING_CONTEXT": "화면 문맥 없음",
    "UNWIRED": "연결 안 된 단계",
    "NOTHING_TO_CALL": "부를 것 없음",
    "NOT_ACCEPTED": "등록 안 된 기능",
    "NOT_SELECTED": "선택 없음",
    "ERROR": "만들기 오류",
}

# 범위 밖 갈래 -> 화면 글자
CATEGORY_LABELS = {"unsupported": "지원 안 함", "ambiguous": "기능 여럿", "insufficient": "정보 부족"}

ALL, FAILED = "전체", "실패만"
FILTERS = (ALL, FAILED, STAGE_LABELS["function"], STAGE_LABELS["input"], STAGE_LABELS["scope"])

# 기능 고르기의 두 자리. 나머지는 기대 recipe id 다.
ALL_GROUPS, OUT_OF_SCOPE_GROUP = "__all__", "__out_of_scope__"

NONE_TEXT = "없음"
EMPTY_NUMBER = "—"
UNGRADED_TEXT = "채점 제외"

# 테스트 실행이 runner 에 넘기는 값. 화면에 안 보인다.
# materialize 를 켠다 — 범위 밖 「정보 부족」 판정과 상세의 실행 준비 칸이 그것을 읽는다.
# MCP 는 안 부른다. 문맥은 계기판 기본값(both)과 같다. GPU 쉼표는 run_selected 가 넘기는
# gpu.GpuMonitor(gate=True) 가 맡는다 (3건마다 5초 · 뜨거우면 멈춤).
RUN_OPTIONS = {"materialize": True, "context_label": "both"}

# 실행 조건 네 줄. 화면 글자 -> runner 결과 meta.conditions 의 칸
CONDITION_ROWS = (
    ("모델", "model"),
    ("프롬프트 파일", "prompt"),
    ("응답 형식 파일", "response_schema"),
    ("기능 정의 파일", "menu"),
)

# session_state 자리
RESULT_KEY = "test_result"           # {"dataset_id", "result"} 마지막으로 잰 결과 또는 불러온 실행 기록
RUN_ERROR_KEY = "test_run_error"     # 실행이 예외로 끝났을 때의 문장
SELECTED_KEY = "test_selected_id"
LIST_VIEW_KEY = "test_list_view"     # 표를 마지막으로 그린 (보기, 검색어)
LIST_ROUND_KEY = "test_list_round"   # (보기, 검색어)가 바뀐 횟수. 표 key 에 들어감
SAVED_KEY = "test_saved_run"         # 실행 기록 고르기 widget
DATASET_KEY = "test_set"             # 테스트 세트 고르기 widget
LOAD_ERROR_KEY = "test_load_error"   # 실행 기록을 못 읽었을 때의 문장

# 결과 목록 · 상세의 높이(px). 창 높이에서 위쪽 머리 부분을 뺀 값이다.
LIST_MIN_HEIGHT, LIST_MAX_HEIGHT = 420, 720
HEAD_HEIGHT = 520


# ================================================================ 데이터
def summarize(result: dict | None) -> dict | None:
    """요약 카드 다섯 개의 숫자. 결과가 없으면 None.

    출력  {"total", "done", "passed", "failed", "function", "input", "error"}
          total 은 잴 발화 수, done 은 끝난 발화 수
          function · input · error 는 그 단계 때문에 실패한 건수
    규칙  runner 결과 summary.total 을 옮겨 적음. 여기서 세지 않음
          실행 중 결과(live_result)면 total 은 잴 수 전체, 성공 · 실패는 끝난 것만
    """
    if not result:
        return None
    total = result["summary"]["total"]
    stages = total["failure_stages"]
    return {
        "total": result.get("planned") or total["runs"],
        "done": total["runs"],
        "passed": total["passed"],
        "failed": total["runs"] - total["passed"],
        "function": stages.get("function", 0),
        "input": stages.get("input", 0),
        "error": stages.get("error", 0),
    }


def live_result(rows: list[dict], planned: int) -> dict:
    """실행 중 화면에 그릴 결과. 끝난 결과 줄만 담음.

    입력  runner 가 progress 로 넘긴 결과 줄들 · 잴 발화 수
    출력  {"summary", "cases", "planned"}. summarize · filter_results 가 끝난 결과처럼 읽음
    규칙  합계는 runner.summarize 로 셈. 판정은 줄에 이미 있음
    제약  줄을 다시 채점하지 않는다
    """
    from dev.evaluation import runner

    return {"summary": runner.summarize(rows, ()), "cases": list(rows), "planned": planned}


def _squash(text: str) -> str:
    """검색 비교용 글자. 띄어쓰기를 빼고 소문자로."""
    return "".join(str(text).split()).lower()


def row_group(row: dict) -> str:
    """결과 줄이 속한 기능 자리. 범위 밖이면 OUT_OF_SCOPE_GROUP, 아니면 기대 recipe id."""
    if row.get("scope") == "out_of_scope":
        return OUT_OF_SCOPE_GROUP
    return row.get("recipe_group") or (row["expected"].get("recipe_ids") or [None])[0]


def filter_results(rows: list[dict], view: str, query: str = "", group: str = ALL_GROUPS) -> list[dict]:
    """보기 필터 · 기능 고르기 · 발화 검색을 건 목록.

    입력  runner 결과 cases. view 는 FILTERS 중 하나. 모르는 값이면 전체
          group 은 ALL_GROUPS · OUT_OF_SCOPE_GROUP · 기대 recipe id
    출력  원래 순서를 지킨 부분 목록
    규칙  실패만은 성공이 아닌 것 전부(실행 오류 포함). 기능 선택 · 인자 추출 · 범위 밖 처리는 그 단계에서 실패한 것
          group 이 ALL_GROUPS 가 아니면 row_group 이 같은 줄만
          검색은 띄어쓰기를 무시한 부분 일치. 빈 검색어는 거르지 않음
    """
    if view == FAILED:
        shown = [r for r in rows if not r["passed"]]
    elif view in STAGE_LABELS.values():
        stage = next(k for k, v in STAGE_LABELS.items() if v == view)
        shown = [r for r in rows if not r["passed"] and r.get("failure_stage") == stage]
    else:
        shown = list(rows)

    if group and group != ALL_GROUPS:
        shown = [r for r in shown if row_group(r) == group]

    needle = _squash(query or "")
    if needle:
        shown = [r for r in shown if needle in _squash(r["utterance"])]
    return shown


def group_options(rows: list[dict]) -> list[str]:
    """기능 고르기에 보일 자리. 전체 · 결과에 나온 기대 recipe (번호 차례) · 범위 밖(있을 때)."""
    groups = {row_group(r) for r in rows}
    recipes = sorted(g for g in groups if g and g != OUT_OF_SCOPE_GROUP)
    return [ALL_GROUPS, *recipes, *([OUT_OF_SCOPE_GROUP] if OUT_OF_SCOPE_GROUP in groups else [])]


def group_label(group: str, rows: list[dict]) -> str:
    """기능 고르기 글자. 「기능 015 · 5건 · 실패 1」 꼴."""
    if group == ALL_GROUPS:
        return "모든 기능"
    members = [r for r in rows if row_group(r) == group]
    name = "범위 밖" if group == OUT_OF_SCOPE_GROUP else function_label(group)
    failed = sum(1 for r in members if not r["passed"])
    return f"{name} · {len(members)}건" + (f" · 실패 {failed}" if failed else "")


def outcome_label(value: str | None) -> str:
    """처리 결과 한 마디. 모르는 값은 그대로, 없으면 「없음」."""
    if not value:
        return NONE_TEXT
    return OUTCOME_LABELS.get(value, value)


def verdict_label(row: dict) -> str:
    """최종 판정 한 마디. "성공" 또는 "실패 · 기능 선택" 꼴."""
    if row["passed"]:
        return "성공"
    stage = STAGE_LABELS.get(row.get("failure_stage"))
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


def function_label(recipe_id: str | None) -> str | None:
    """기능 번호 글자. "recipe_015" -> "기능 015". 없으면 None."""
    if not recipe_id:
        return None
    return f"기능 {recipe_id.rsplit('_', 1)[-1]}"


def readable_reason(text: str) -> str:
    """모델 판단 문장의 기능 번호를 화면 글자로. "recipe_061" -> "기능 061".

    규칙  번호만 바꿈. 그 밖의 글자는 모델이 쓴 그대로
    """
    return re.sub(r"\brecipe_(\d+)", r"기능 \1", text)


def field_rows(row: dict) -> list[dict]:
    """인자 비교 줄. 정답표에 적은 인자와 모델이 낸 인자를 빠짐없이.

    출력  [{"name", "label", "graded", "answer", "model", "in_model", "correct"}]
    규칙  모델 출력 차례가 먼저, 정답표에만 있는 인자는 뒤에 정답표 차례로
          graded 는 정답표에 그 이름이 적혔나. runner 의 spoken_fields 에 있는 이름임
          correct 는 runner 가 맞댄 결과 그대로. 채점 제외면 None
          answer 는 정답표에 적은 값. 채점 제외면 None
          label 은 FIELD_LABELS 에 없으면 변수명 그대로
    제약  값끼리 맞대지 않는다. 판정은 runner 결과에 있음
    """
    graded = {field["name"]: field for field in row.get("spoken_fields") or []}
    model = ((row.get("actual") or {}).get("spoken")) or {}
    names = [*model, *(name for name in graded if name not in model)]
    return [
        {
            "name": name,
            "label": FIELD_LABELS.get(name, name),
            "graded": name in graded,
            "answer": graded[name]["expected"] if name in graded else None,
            "model": model.get(name),
            "in_model": name in model,
            "correct": graded[name]["correct"] if name in graded else None,
        }
        for name in names
    ]


def _seconds(value) -> str:
    return f"{value:.1f}초" if isinstance(value, (int, float)) else ""


def list_frame(rows: list[dict]) -> pd.DataFrame:
    """결과 목록 표. 한 발화 한 줄, 칸 여섯."""
    return pd.DataFrame(
        {
            "번호": [f"{r['case_id']:03d}" for r in rows],
            "기능": ["범위 밖" if row_group(r) == OUT_OF_SCOPE_GROUP else (function_label(row_group(r)) or "") for r in rows],
            "발화": [r["utterance"] for r in rows],
            "결과": ["성공" if r["passed"] else "실패" for r in rows],
            "판정": ["" if r["passed"] else STAGE_LABELS.get(r.get("failure_stage"), "") for r in rows],
            "시간": [_seconds((r.get("timing") or {}).get("resolve_s")) for r in rows],
        }
    )


def list_height(ratios: dict) -> int:
    """결과 목록 · 상세 칸의 높이(px). 창 높이를 따라가되 범위 안에서."""
    viewport = int(ratios.get("viewport_height") or 0)
    return max(LIST_MIN_HEIGHT, min(LIST_MAX_HEIGHT, viewport - HEAD_HEIGHT))


def run_conditions(result: dict | None) -> dict | None:
    """실행 조건 네 줄. {화면 글자: 값}. 결과가 없으면 None.

    규칙  runner 결과 meta.conditions 에서 옮김. 파일은 경로만 보임
          조건을 못 읽은 결과면 그 까닭 한 줄
    """
    if not result:
        return None
    conditions = result["meta"].get("conditions") or {}
    if "error" in conditions:
        return {"실행 조건": conditions["error"]}
    shown = {}
    for label, key in CONDITION_ROWS:
        value = conditions.get(key)
        shown[label] = value.get("path") if isinstance(value, dict) else value
    return {label: value if value is not None else NONE_TEXT for label, value in shown.items()}


def _fraction(pair: dict | None) -> str:
    """지표 한 칸. 「48/48 · 100%」. 분모가 0 이면 줄표."""
    if not pair or not pair.get("total"):
        return EMPTY_NUMBER
    return f"{pair['correct']}/{pair['total']} · {pair['correct'] / pair['total']:.0%}"


def _elapsed(seconds) -> str:
    if not isinstance(seconds, (int, float)):
        return EMPTY_NUMBER
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}분 {rest}초" if minutes else f"{rest}초"


def gpu_text(gpu: dict | None) -> str:
    """GPU 한 줄. 기록이 없으면 「기록 없음」.

    규칙  시작 · 최고 · 끝 온도, 쉰 횟수, 열 제한. 열 제한을 못 읽었으면 그 말을 뺌
    """
    if not gpu or not gpu.get("available"):
        return "기록 없음"
    parts = [f"시작 {gpu.get('start_temp')}°C · 최고 {gpu.get('max_temp')}°C · 끝 {gpu.get('end_temp')}°C"]
    parts.append(f"쉼 {gpu.get('pauses') or 0}회")
    if gpu.get("thermal_throttle") is not None:
        parts.append("열 제한 있음" if gpu["thermal_throttle"] else "열 제한 없음")
    return " · ".join(parts)


def run_identity(result: dict) -> dict:
    """실행 기록 id 와 저장 자리. 실행 조건 아래 두 줄. 없으면 그 줄을 뺌."""
    meta = result["meta"]
    shown = {}
    if meta.get("run_id"):
        shown["실행 기록 id"] = meta["run_id"]
    if meta.get("saved_to"):
        shown["저장 위치"] = meta["saved_to"]
    return shown


def suite_label(suite: dict) -> str:
    """결과 meta.suite 의 화면 이름. 붙은 이름 -> 등록된 정답표의 이름(경로로 찾음) -> 「정답표」."""
    if suite.get("label"):
        return suite["label"]
    path = suite.get("path")
    for entry in evaluation_suite.datasets():
        if path and Path(entry["path"]).resolve() == Path(path).resolve():
            return entry["label"]
    return "정답표"


def overview(result: dict | None) -> dict | None:
    """실행 개요. {화면 글자: 값}. 결과가 없으면 None.

    규칙  runner 결과 meta · summary.metrics · summary.latency 를 옮겨 적음. 여기서 세지 않음
          지표는 「맞은 수/잰 수 · 백분율」. 잰 것이 없으면 줄표 (FULL48 의 범위 밖 등)
          실행 기록 id 는 여기 안 보임 (정답표 이름이 들어 있어 개발 용어가 샘). 실행 조건에 있음
    """
    if not result:
        return None
    meta, summary = result["meta"], result["summary"]
    board = summary.get("metrics") or {}
    total = summary["total"]
    suite = meta.get("suite") or {}
    started = meta.get("started_at")
    delay = summary.get("latency") or {}
    return {
        "테스트 세트": suite_label(suite),
        "시작": f"{datetime.datetime.fromisoformat(started):%m-%d %H:%M:%S}" if started else EMPTY_NUMBER,
        "걸린 시간": _elapsed(meta.get("elapsed_s")),
        "발화": f"{total['runs']}건 · 성공 {total['passed']} · 실패 {total['runs'] - total['passed']} · 오류 {total['errors']}",
        "기능 선택": _fraction(board.get("selection")),
        "인자 추출": _fraction(board.get("semantic_fields")),
        "발화 성공": _fraction(board.get("joint")),
        "범위 밖 처리": _fraction(board.get("oos")),
        "실행 준비": _fraction(board.get("ready")),
        "응답 시간": (
            f"중앙 {delay['median']:.1f}초 · 95% {delay['p95']:.1f}초 · 최대 {delay['max']:.1f}초" if delay else EMPTY_NUMBER
        ),
        "GPU": gpu_text(meta.get("gpu")),
    }


def recipe_rows(result: dict | None) -> list[dict]:
    """기능별 결과. [{group, label, runs, passed, failed}] 실패가 많은 것부터, 같으면 번호 차례.

    규칙  runner 결과 summary.recipes 를 옮김. 범위 밖은 summary.total 의 oos_* 로 한 줄 덧붙임
    """
    if not result:
        return []
    entries = [
        {"group": rid, "label": function_label(rid), "runs": v["runs"], "passed": v["passed"], "failed": v["runs"] - v["passed"]}
        for rid, v in (result["summary"].get("recipes") or {}).items()
    ]
    total = result["summary"]["total"]
    if total.get("oos_runs"):
        entries.append({
            "group": OUT_OF_SCOPE_GROUP, "label": "범위 밖", "runs": total["oos_runs"],
            "passed": total["oos_passed"], "failed": total["oos_runs"] - total["oos_passed"],
        })
    return sorted(entries, key=lambda e: (-e["failed"], e["group"]))


def first_failure(rows: list[dict]) -> int | None:
    """목록에서 첫 실패 줄의 자리. 없으면 None."""
    return next((i for i, r in enumerate(rows) if not r["passed"]), None)


def saved_label(entry: dict) -> str:
    """실행 기록 고르기 글자. 「09-18 16:02 · 테스트 세트 v2 · 성공 201/219」 꼴."""
    started = entry.get("started_at")
    when = f"{datetime.datetime.fromisoformat(started):%m-%d %H:%M}" if started else entry["run_id"]
    score = f"성공 {entry['passed']}/{entry['runs']}" if entry.get("runs") is not None else "끝나지 않음"
    return f"{when} · {entry.get('suite_label') or entry.get('suite_name') or ''} · {score}"


@st.cache_data(show_spinner=False)
def _case_count(path: str, modified: int) -> int | None:
    """정답표에서 기본으로 도는 발화 수. 파일이 바뀔 때만 다시 읽음. 못 읽으면 None."""
    try:
        suite = evaluation_suite.load(Path(path))
    except (OSError, ValueError):
        return None
    return sum(1 for case in suite["cases"] if case["enabled"])


def dataset_label(entry: dict) -> str:
    """테스트 세트 고르기에 보일 이름. 발화 수를 셀 수 있으면 붙임."""
    path = Path(entry["path"])
    count = _case_count(str(path), path.stat().st_mtime_ns) if path.is_file() else None
    return f"{entry['label']} · {count}개 발화" if count is not None else entry["label"]


# ================================================================ 마크업
def _esc(value) -> str:
    """HTML 에 넣을 글자."""
    return html.escape(str(value))


def summary_markup(summary: dict | None) -> str:
    """요약 카드 다섯. 결과가 없으면 숫자 자리에 줄표만."""

    def card(label, number, tone="", note=""):
        note_html = f'<div class="tt-kpi-note">{_esc(note)}</div>' if note else ""
        return (
            f'<div class="tt-kpi {tone}"><div class="tt-kpi-label">{_esc(label)}</div>'
            f'<div class="tt-kpi-num">{_esc(number)}</div>{note_html}</div>'
        )

    if summary is None:
        cards = [
            card("전체", EMPTY_NUMBER),
            card("성공", EMPTY_NUMBER, "ok"),
            card("실패", EMPTY_NUMBER, "ng"),
            card(STAGE_LABELS["function"], EMPTY_NUMBER, "cause"),
            card(STAGE_LABELS["input"], EMPTY_NUMBER, "cause"),
        ]
        return '<div class="tt-kpis tt-kpis-empty">' + "".join(cards) + "</div>"

    done = summary["done"]
    finished = done == summary["total"]

    def share(count):
        return f"{count / done:.1%}" if done else ""

    failed_note = share(summary["failed"])
    if summary["error"]:
        failed_note += f" · {STAGE_LABELS['error']} {summary['error']}"
    return '<div class="tt-kpis">' + "".join(
        [
            card("전체", summary["total"], note="발화" if finished else f"완료 {done} / {summary['total']}"),
            card("성공", summary["passed"], "ok", share(summary["passed"])),
            card("실패", summary["failed"], "ng", failed_note),
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


def overview_markup(info: dict | None) -> str:
    """실행 개요. 결과가 없으면 빈 글자."""
    if info is None:
        return ""
    cells = "".join(
        f'<div class="tt-ov"><div class="tt-ov-k">{_esc(k)}</div><div class="tt-ov-v">{_esc(v)}</div></div>'
        for k, v in info.items()
    )
    return f'<div class="tt-ovs">{cells}</div>'


def recipe_summary_markup(entries: list[dict]) -> str:
    """기능별 결과 표. 실패가 있는 줄은 붉게."""
    if not entries:
        return '<div class="tt-empty">결과가 없습니다.</div>'
    rows = "".join(
        f'<div class="tt-rs{" tt-rs-ng" if e["failed"] else ""}">'
        f'<div>{_esc(e["label"])}</div><div>{e["passed"]}/{e["runs"]}</div>'
        f'<div>{"실패 " + str(e["failed"]) if e["failed"] else "모두 성공"}</div></div>'
        for e in entries
    )
    return f'<div class="tt-rss">{rows}</div>'


def _value_markup(value) -> str:
    """값 하나. 없음은 흐리게."""
    text = display_value(value)
    css = "tt-val tt-none" if text == NONE_TEXT else "tt-val"
    return f'<span class="{css}">{_esc(text)}</span>'


def _muted_markup(text: str) -> str:
    """값 자리에 넣는 흐린 글자."""
    return f'<span class="tt-val tt-none">{_esc(text)}</span>'


def _function_markup(recipe_ids: list, functions: dict, empty: str = "선택 없음") -> str:
    """기능 번호와 설명. 고르지 않았으면 empty 글자.

    규칙  기능이 여럿이면 차례대로 모두 보임. 설명은 runner 결과의 meta.functions
    """
    shown = [rid for rid in recipe_ids if rid]
    if not shown:
        return f'<div class="tt-fn tt-none">{_esc(empty)}</div>'
    return "".join(
        f'<div class="tt-fn">{_esc(function_label(rid))}</div>'
        f'<div class="tt-desc">{_esc(functions.get(rid) or "")}</div>'
        for rid in shown
    )


def _key_markup(label: str, name: str | None = None) -> str:
    """줄 머리. 표시명이 변수명과 다르면 변수명을 아래에 작게."""
    sub = f'<div class="tt-var">{_esc(name)}</div>' if name and name != label else ""
    return f'<div class="tt-c tt-key"><div class="tt-key-label">{_esc(label)}</div>{sub}</div>'


def _pair_markup(key_html: str, answer_html: str, model_html: str, *, wrong: bool, graded: bool = True) -> str:
    """비교 한 줄. 줄 머리 · 정답표 · AI 모델 출력.

    입력  wrong 은 runner 가 틀렸다고 판정한 칸인가
    규칙  채점하는 칸이 틀렸으면 모델 출력 칸을 강조하고 「차이」를 닮
          채점 제외 칸은 줄 전체를 흐리게 둠. 강조하지 않음
    """
    tag, cell = "", "tt-c tt-model"
    row = "" if graded else " tt-ungraded"
    if wrong and graded:
        cell += " tt-diff"
        tag = '<span class="tt-tag tt-tag-diff">차이</span>'
    return (
        f'<div class="tt-row{row}">{key_html}'
        f'<div class="tt-c tt-answer">{answer_html}</div>'
        f'<div class="{cell}">{model_html}{tag}</div></div>'
    )


def _extra_markup(row: dict) -> str:
    """AI 모델 출력의 부가 정보. 판정 상태 · 후보 기능 · 판단. 실행 오류면 오류 문장."""
    model = row.get("actual") or {}
    if row.get("error"):
        status_text = STAGE_LABELS["error"]
        reason = row["error"]
    else:
        status = model.get("status")
        status_text = STATUS_LABELS.get(status, status or NONE_TEXT)
        reason = readable_reason(model.get("reason") or NONE_TEXT)
    picked = model.get("recipe_id")
    built = row.get("materialize") or {}
    readiness = outcome_label(built.get("status")) if built else NONE_TEXT
    if built.get("missing"):
        readiness += f" ({', '.join(str(m) for m in built['missing'])})"
    timing = row.get("timing") or {}
    chips = "".join(
        f'<span class="tt-chip{" tt-chip-on" if cid == picked else ""}">{_esc(function_label(cid))}</span>'
        for cid in model.get("candidate_recipe_ids") or []
    ) or f'<span class="tt-val tt-none">{NONE_TEXT}</span>'
    return (
        '<div class="tt-extra">'
        '<div class="tt-extra-head">AI 모델 출력 · 판단 내용</div>'
        f'<div class="tt-kv"><div class="tt-kv-k">모델 판정 상태</div>'
        f'<div class="tt-kv-v"><span class="tt-status">{_esc(status_text)}</span></div></div>'
        f'<div class="tt-kv"><div class="tt-kv-k">후보 기능</div><div class="tt-kv-v">{chips}</div></div>'
        f'<div class="tt-kv"><div class="tt-kv-k">모델 판단</div>'
        f'<div class="tt-kv-v tt-reason">{_esc(reason)}</div></div>'
        f'<div class="tt-kv"><div class="tt-kv-k">처리 결과</div><div class="tt-kv-v">{_esc(outcome_label(row.get("outcome")))}</div></div>'
        f'<div class="tt-kv"><div class="tt-kv-k">실행 준비</div><div class="tt-kv-v">{_esc(readiness)}</div></div>'
        f'<div class="tt-kv"><div class="tt-kv-k">응답 시간</div>'
        f'<div class="tt-kv-v">{_esc(_seconds(timing.get("resolve_s")) or NONE_TEXT)}</div></div>'
        "</div>"
    )


def detail_markup(row: dict, functions: dict) -> str:
    """선택한 발화 상세. 성공 · 실패가 같은 틀.

    입력  runner 결과 cases 한 줄 · meta.functions
    규칙  맨 위 한 줄에 번호 · 발화 · 판정
          정답표 | AI 모델 출력 두 칸에 기능 번호 · 설명과 인자 전부(field_rows)
          기능 칸 강조는 runner 의 recipe_correct, 인자 칸 강조는 spoken_fields 의 correct
          정답표에 안 적은 인자는 정답표 칸에 「채점 제외」, 모델 칸은 값을 흐리게
          범위 밖 발화는 기능 · 인자 대신 갈래와 받아들이는 처리 결과를 맞댐. 강조는 runner 의 passed
          그 아래 AI 모델 출력의 판정 상태 · 후보 기능 · 판단 · 처리 결과 · 실행 준비 · 응답 시간
    """
    model = row.get("actual") or {}
    errored = bool(row.get("error"))
    tone = "ok" if row["passed"] else "ng"
    head = (
        '<div class="tt-head">'
        f'<span class="tt-no">{row["case_id"]:03d}</span>'
        f'<span class="tt-utt">{_esc(row["utterance"])}</span>'
        f'<span class="tt-badge {tone}">● {_esc(verdict_label(row))}</span>'
        "</div>"
    )

    rows = [
        '<div class="tt-row tt-cols">'
        '<div class="tt-c"></div>'
        '<div class="tt-c tt-col-answer">✓ 정답표</div>'
        '<div class="tt-c tt-col-model">AI 모델 출력</div>'
        "</div>",
    ]
    if row.get("scope") == "out_of_scope":
        category = row["expected"].get("category")
        accepted = " 또는 ".join(outcome_label(o) for o in row["expected"].get("outcomes") or [])
        rows += [
            '<div class="tt-sec">범위 밖 처리</div>',
            _pair_markup(
                _key_markup("갈래"),
                f'<div class="tt-fn">범위 밖 · {_esc(CATEGORY_LABELS.get(category, category))}</div>',
                _function_markup([model.get("recipe_id")], functions, STAGE_LABELS["error"] if errored else "선택 없음"),
                wrong=False,
            ),
            _pair_markup(
                _key_markup("처리 결과"),
                _value_markup(accepted),
                _value_markup(STAGE_LABELS["error"] if errored else outcome_label(row.get("outcome"))),
                wrong=not row["passed"],
            ),
        ]
        return f'{head}<div class="tt-cmp">{"".join(rows)}</div>{_extra_markup(row)}'

    rows += [
        '<div class="tt-sec">기능 선택</div>',
        _pair_markup(
            _key_markup("기능"),
            _function_markup(row["expected"]["recipe_ids"], functions),
            _function_markup([model.get("recipe_id")], functions, STAGE_LABELS["error"] if errored else "선택 없음"),
            wrong=not row["recipe_correct"],
        ),
        '<div class="tt-sec">인자 추출</div>',
    ]
    for f in field_rows(row):
        rows.append(
            _pair_markup(
                _key_markup(f["label"], f["name"]),
                _value_markup(f["answer"]) if f["graded"] else _muted_markup(UNGRADED_TEXT),
                _value_markup(f["model"]) if f["in_model"] else _muted_markup(EMPTY_NUMBER),
                wrong=f["correct"] is False,
                graded=f["graded"],
            )
        )

    return f'{head}<div class="tt-cmp">{"".join(rows)}</div>{_extra_markup(row)}'


def _note_markup(text: str) -> str:
    """결과 위에 띄우는 알림 한 줄. 멈춘 까닭 · 실행 오류 문장."""
    return f'<div class="tt-note">{_esc(text)}</div>'


# ================================================================ 실행
def run_selected(dataset_id: str, on_progress=None) -> dict:
    """고른 정답표를 dev/evaluation 공통 runner 로 잰 결과.

    규칙  runner.run_dataset 에 RUN_OPTIONS 와 그 문맥 · GPU 조용 정책을 넘김. 판정은 전부 runner 가 함
          run_dataset 이 Test Run 을 test_runs 에 저절로 남김
          runner 를 여기서 import 함. 탭을 열기만 해서는 계기판 모듈을 안 읽음
    제약  판정 · 채점을 여기서 하지 않는다
    """
    from dev.evaluation import gpu, runner

    options = dict(RUN_OPTIONS)
    options["context"] = runner.context_payload(options["context_label"])
    return runner.run_dataset(dataset_id, progress=on_progress, monitor=gpu.GpuMonitor(gate=True), **options)


def _execute(dataset_id: str, slots: dict, height: int) -> None:
    """테스트 실행 한 번. 발화 하나가 끝날 때마다 그 줄을 화면에 쌓고, 다 끝나면 결과를 두고 다시 그림.

    입력  slots 는 진행 · 요약 · 목록 · 상세 자리({"status", "kpi", "list", "detail"}의 st.empty)
    규칙  시작하자마자 0건 화면을 그림. 잴 수는 정답표에서 센 발화 수
          runner 가 progress 로 넘긴 결과 줄(판정까지 끝난 것)을 모아 네 자리를 갈아 그림.
          같은 script 실행 안에서 자리만 바꾸므로 발화마다 rerun 하지 않음
          다 끝나면 결과를 RESULT_KEY 에 두고 한 번 rerun 함. 그때 같은 자리에 보통 화면이 그려져
          실행 중 표와 끝난 표가 겹치지 않음
          예외로 끝나면 문장을 RUN_ERROR_KEY 에 두고 지난 결과는 안 지움
          새 결과가 들어오면 고른 발화 · 표 선택을 처음으로 돌림
    제약  결과 줄을 여기서 채점하지 않는다. 합계는 live_result 가 runner.summarize 로 셈
          실행 중에 session_state 를 바꾸지 않는다. 발화마다 rerun 하지 않는다
    """
    from dev.evaluation import runner

    entry = next(entry for entry in evaluation_suite.datasets() if entry["id"] == dataset_id)
    path = Path(entry["path"])
    planned = _case_count(str(path), path.stat().st_mtime_ns) or 0
    functions = runner.functions()
    done_rows: list[dict] = []

    with slots["status"].container():
        bar = st.progress(0.0, text=f"테스트 실행 중 · 0 / {planned}")
    _render_live(slots, done_rows, planned, functions, height)

    def on_progress(done: int, total: int, row: dict) -> None:
        done_rows.append(row)
        bar.progress(done / total if total else 1.0, text=f"테스트 실행 중 · {done} / {total}")
        _render_live(slots, done_rows, total, functions, height)

    st.session_state.pop(RUN_ERROR_KEY, None)
    try:
        result = run_selected(dataset_id, on_progress)
    except Exception as exc:  # noqa: BLE001 — 화면이 통째로 죽지 않고 까닭을 보인다.
        st.session_state[RUN_ERROR_KEY] = f"테스트를 실행하지 못했습니다 — {type(exc).__name__}: {exc}"
    else:
        st.session_state[RESULT_KEY] = {"dataset_id": dataset_id, "result": result}
        for key in (SELECTED_KEY, LIST_VIEW_KEY, SAVED_KEY):
            st.session_state.pop(key, None)
    st.rerun()


def _render_live(slots: dict, rows: list[dict], planned: int, functions: dict, height: int) -> None:
    """실행 중 화면. 끝난 줄만 요약 · 목록에 쌓고, 상세에는 방금 끝난 발화를 보임.

    규칙  요약 카드는 전체에 잴 수, 성공 · 실패에 끝난 것만
          목록은 끝난 줄만 정답표 차례로. 행 고르기는 끔(실행 중 누르면 rerun 으로 멈춤)
          같은 자리를 갈아 그리므로 표가 둘이 되지 않음
    """
    slots["kpi"].markdown(summary_markup(summarize(live_result(rows, planned))), unsafe_allow_html=True)
    with slots["list"].container():
        st.markdown(
            f'<div class="tt-pane-title">테스트 결과 <span>{len(rows)}건</span></div>', unsafe_allow_html=True
        )
        if rows:
            st.dataframe(
                _styled_frame(rows), hide_index=True, height=height, row_height=32, width="stretch",
                column_config=_list_columns(),
            )
        else:
            with st.container(height=height, border=True):
                st.markdown('<div class="tt-empty">첫 발화 결과를 기다리는 중입니다.</div>', unsafe_allow_html=True)
    with slots["detail"].container():
        st.markdown('<div class="tt-pane-title">방금 끝난 발화 상세</div>', unsafe_allow_html=True)
        with st.container(height=height, border=True):
            if rows:
                st.markdown(detail_markup(rows[-1], functions), unsafe_allow_html=True)
            else:
                st.markdown('<div class="tt-empty">결과가 나오면 여기 표시됩니다.</div>', unsafe_allow_html=True)


# ================================================================ 그리기
def saved_runs() -> list[dict]:
    """저장된 실행 기록 목록. test_runs.list_runs 그대로. 못 읽으면 빈 목록."""
    from dev.evaluation import test_runs

    try:
        return test_runs.list_runs()
    except OSError:
        return []


def _load_saved() -> None:
    """실행 기록 고르기의 콜백. 고른 기록을 방금 잰 결과와 같은 자리에 둠.

    규칙  test_runs.load_run 이 돌려준 결과 한 벌을 RESULT_KEY 에 둠. 테스트 세트 고르기를 그 기록의
          정답표로 맞춤. 고른 발화 · 표 선택을 처음으로 돌림
          못 읽으면 문장을 LOAD_ERROR_KEY 에 두고 지난 결과는 안 지움
    제약  평가 · LLM 을 부르지 않는다
    """
    from dev.evaluation import test_runs

    run_id = st.session_state.get(SAVED_KEY)
    st.session_state.pop(LOAD_ERROR_KEY, None)
    if not run_id:
        return
    try:
        result = test_runs.load_run(run_id)
    except (OSError, ValueError) as exc:
        st.session_state[LOAD_ERROR_KEY] = f"실행 기록을 읽지 못했습니다 — {type(exc).__name__}: {exc}"
        return
    dataset_id = (result["meta"].get("suite") or {}).get("dataset_id")
    known = {entry["id"] for entry in evaluation_suite.datasets()}
    if dataset_id not in known:
        dataset_id = st.session_state.get(DATASET_KEY)
    else:
        st.session_state[DATASET_KEY] = dataset_id
    st.session_state[RESULT_KEY] = {"dataset_id": dataset_id, "result": result}
    for key in (SELECTED_KEY, LIST_VIEW_KEY):
        st.session_state.pop(key, None)


def _render_header(stored: dict) -> tuple[str, bool, dict | None]:
    """제목 · 테스트 세트 · 실행 기록 · 테스트 실행.

    입력  session_state 의 마지막 실행 {"dataset_id", "result"}
    출력  (고른 정답표 id, 테스트 실행을 눌렀나, 고른 정답표의 마지막 결과 또는 None)
    규칙  실행 기록은 저장된 Test Run 목록. 고르면 _load_saved 가 그 결과를 지금 결과 자리에 둠
    제약  여기서 평가를 부르지 않는다. 누른 것만 알림
    """
    entries = evaluation_suite.datasets()
    labels = {entry["id"]: dataset_label(entry) for entry in entries}
    saved = {entry["run_id"]: saved_label(entry) for entry in saved_runs()}
    title, picker, history, run = st.columns([4, 2.6, 3, 1.2], vertical_alignment="bottom")
    with picker:
        dataset_id = st.selectbox(
            "테스트 세트", list(labels), format_func=labels.get, key=DATASET_KEY, persist_state="page"
        )
    with history:
        st.selectbox(
            "실행 기록", [""] + list(saved), format_func=lambda rid: saved.get(rid, "불러올 기록 고르기"),
            key=SAVED_KEY, on_change=_load_saved,
        )
    with run:
        clicked = st.button("테스트 실행", type="primary", key="test_run", width="stretch")
    result = stored.get("result") if stored.get("dataset_id") == dataset_id else None
    with title:
        sub = "발화별 기능 선택 및 인자 추출 결과"
        if result:
            started = datetime.datetime.fromisoformat(result["meta"]["started_at"])
            sub += f" · {started:%m-%d %H:%M} 실행"
        st.markdown(
            f'<div class="tt-title">AI 기능 테스트</div><div class="tt-sub">{_esc(sub)}</div>',
            unsafe_allow_html=True,
        )
    return dataset_id, clicked, result


def _render_overview(result: dict | None) -> None:
    """실행 개요 한 판. 결과가 없으면 안 그림."""
    info = overview(result)
    if info is not None:
        st.markdown(overview_markup(info), unsafe_allow_html=True)


def _render_recipe_summary(result: dict | None) -> None:
    """기능별 결과 (접힘). 실패가 있으면 펼침."""
    entries = recipe_rows(result)
    if not entries:
        return
    failed = sum(1 for e in entries if e["failed"])
    title = f"기능별 결과 · {len(entries)}개" + (f" · 실패 있는 기능 {failed}" if failed else "")
    with st.expander(title, expanded=bool(failed)):
        st.markdown(recipe_summary_markup(entries), unsafe_allow_html=True)


def _render_conditions(result: dict | None) -> None:
    """실행 조건 (접힘). 결과가 없으면 비어 있다고만."""
    with st.expander("실행 조건", expanded=False):
        conditions = run_conditions(result)
        if conditions is None:
            st.markdown('<div class="tt-empty">테스트를 실행하면 표시됩니다.</div>', unsafe_allow_html=True)
        else:
            st.markdown(conditions_markup({**conditions, **run_identity(result)}), unsafe_allow_html=True)


def _render_filters(summary: dict | None, rows: list[dict] | None = None) -> tuple[str, str, str]:
    """보기 필터 · 기능 고르기 · 발화 검색.

    출력  (보기, 검색어, 기능 자리)
    규칙  결과가 있으면 필터 글자 옆에 그 보기의 건수를 붙임
          기능 고르기는 결과에 나온 기대 기능과 범위 밖. 결과가 없으면 모든 기능 하나
    """
    rows = rows or []
    counts = {}
    if summary is not None:
        counts = {
            ALL: summary["total"],
            FAILED: summary["failed"],
            STAGE_LABELS["function"]: summary["function"],
            STAGE_LABELS["input"]: summary["input"],
            STAGE_LABELS["scope"]: sum(1 for r in rows if not r["passed"] and r.get("failure_stage") == "scope"),
        }
    left, middle, right = st.columns([3.2, 1.6, 1.6], vertical_alignment="center")
    with left:
        view = st.segmented_control(
            "보기",
            FILTERS,
            default=ALL,
            required=True,
            format_func=lambda v: f"{v}  {counts[v]}" if v in counts else v,
            key="test_filter",
            label_visibility="collapsed",
            persist_state="page",
        )
    with middle:
        options = group_options(rows)
        group = st.selectbox(
            "기능", options, format_func=lambda g: group_label(g, rows), key="test_group",
            label_visibility="collapsed",
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
    return view or ALL, query or "", group or ALL_GROUPS


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


def _list_key(view: str, query: str, group: str = ALL_GROUPS) -> str:
    """결과 표의 key. 보기나 검색어가 바뀔 때만 새로 붙음.

    규칙  같은 보기 안에서는 key 가 그대로라 표가 안 새로 붙고 스크롤 자리가 남음
          보기 · 검색어가 바뀌면 key 가 바뀌어 표가 새로 붙고 selection_default 가 다시 먹음.
          전에 봤던 보기로 돌아와도 그때의 선택이 아니라 지금 고른 발화를 따름
          새 결과가 들어오면 _execute 가 LIST_VIEW_KEY 를 지워 표가 새로 붙음
    """
    round_ = st.session_state.get(LIST_ROUND_KEY, 0)
    if st.session_state.get(LIST_VIEW_KEY) != (view, query, group):
        round_ += 1
        st.session_state[LIST_VIEW_KEY] = (view, query, group)
        st.session_state[LIST_ROUND_KEY] = round_
    return f"test_list_{round_}"


def _styled_frame(rows: list[dict]):
    """결과 목록 표에 결과 · 판정 글자색을 입힌 것."""
    return list_frame(rows).style.map(_result_tone, subset=["결과"]).map(
        lambda v: "color: #E5534B;" if v else "", subset=["판정"]
    )


def _list_columns() -> dict:
    """결과 목록 표의 칸 폭."""
    return {
        "번호": st.column_config.TextColumn("번호", width=56),
        "기능": st.column_config.TextColumn("기능", width=76),
        "발화": st.column_config.TextColumn("발화", width="large"),
        "결과": st.column_config.TextColumn("결과", width=60),
        "판정": st.column_config.TextColumn("판정", width=96),
        "시간": st.column_config.TextColumn("시간", width=60),
    }


def _render_result_list(shown: list[dict], view: str, query: str, height: int, *, ran: bool, group: str = ALL_GROUPS) -> dict | None:
    """결과 목록. 한 발화 한 줄, 고정 높이 안에서 스크롤.

    출력  지금 고른 결과 줄. 목록이 비었으면 None
    규칙  행 고르기는 st.dataframe 의 행 선택. 발화 글자를 눌러도 골라지게 칸 선택을
          함께 켜고, 칸을 누르면 _keep_row_selected 가 그 줄 선택으로 바꿈
          표 key 는 _list_key 가 정함. 같은 보기 안에서 행을 눌러도 표가 새로 안 붙으므로
          스크롤 자리가 그대로임
          보기를 바꾸면 고른 발화가 새 목록에 있으면 그 줄, 없으면 첫 실패 줄, 실패가 없으면 첫 줄을 고름
          아직 안 돌렸으면(ran 거짓) 빈 목록 안내
    제약  single-row-required 를 쓰지 않는다.
          칸을 누르면 행 선택이 비었다고 보고 첫 줄로 되돌림. 발화를 눌렀는데 001 이 뜸
    """
    count = f"{len(shown)}건" if ran else ""
    st.markdown(
        f'<div class="tt-pane-title">테스트 결과 <span>{count}</span></div>',
        unsafe_allow_html=True,
    )
    if not shown:
        message = (
            "조건에 맞는 발화가 없습니다." if ran
            else "테스트 세트를 선택하고 실행하면<br>발화별 기능 선택과 인자 추출 결과를 확인할 수 있습니다."
        )
        with st.container(height=height, border=True):
            st.markdown(f'<div class="tt-empty">{message}</div>', unsafe_allow_html=True)
        return None

    remembered = st.session_state.get(SELECTED_KEY)
    default = next((i for i, r in enumerate(shown) if r["case_id"] == remembered), None)
    if default is None:
        default = first_failure(shown) or 0

    key = _list_key(view, query, group)
    event = st.dataframe(
        _styled_frame(shown),
        key=key,
        on_select=partial(_keep_row_selected, key, [r["case_id"] for r in shown]),
        selection_mode=["single-row", "single-cell"],
        selection_default={"selection": {"rows": [default]}},
        hide_index=True,
        height=height,
        row_height=32,
        width="stretch",
        column_config=_list_columns(),
    )

    rows = event.selection.rows if event is not None else []
    picked = rows[0] if rows and 0 <= rows[0] < len(shown) else default
    st.session_state[SELECTED_KEY] = shown[picked]["case_id"]
    return shown[picked]


def _render_result_detail(row: dict | None, functions: dict, height: int) -> None:
    """선택한 발화 상세. 고정 높이 안에서 스크롤."""
    st.markdown('<div class="tt-pane-title">선택한 발화 상세</div>', unsafe_allow_html=True)
    with st.container(height=height, border=True, key="test_detail"):
        if row is None:
            st.markdown('<div class="tt-empty">결과에서 발화를 선택하면 상세가 표시됩니다.</div>', unsafe_allow_html=True)
            return
        st.markdown(detail_markup(row, functions), unsafe_allow_html=True)


def render_test_tab(ratios: dict) -> None:
    """테스트 탭 전체.

    입력  config.layout_ratios() 결과. 창 높이로 목록 높이를 정함
    규칙  결과는 session_state 의 마지막 실행 하나(방금 잰 것 또는 불러온 실행 기록). 고른 정답표의 것일 때만 그림
          실행 개요 · 기능별 결과는 결과가 있을 때만
          진행 · 요약 · 목록 · 상세를 st.empty 자리로 잡아 둠. 실행 중에는 _execute 가 그 자리를
          갈아 그리고, 보통 때는 같은 자리에 결과를 그림
          테스트 실행을 누른 회차에만 _execute 가 runner 를 부름
    제약  테스트 실행을 누르지 않은 회차에는 평가 · LLM 을 부르지 않는다.
          필터 · 검색 · 행 선택 · 탭 전환이 다시 재게 하면 한 번에 수십 분이 듦
    """
    with st.container(key="test_tab"):
        st.markdown(panel_css(), unsafe_allow_html=True)
        dataset_id, clicked, result = _render_header(st.session_state.get(RESULT_KEY) or {})

        if not clicked:
            _render_overview(result)
        _render_conditions(result)
        status_slot = st.empty()
        kpi_slot = st.empty()
        summary = None if clicked else summarize(result)
        if not clicked:
            _render_recipe_summary(result)
        view, query, group = _render_filters(summary, [] if clicked or not result else result["cases"])

        height = list_height(ratios)
        left, right = st.columns([63, 37], gap="medium")
        list_slot, detail_slot = left.empty(), right.empty()
        if clicked:
            slots = {"status": status_slot, "kpi": kpi_slot, "list": list_slot, "detail": detail_slot}
            _execute(dataset_id, slots, height)

        if st.session_state.get(RUN_ERROR_KEY):
            status_slot.markdown(_note_markup(st.session_state[RUN_ERROR_KEY]), unsafe_allow_html=True)
        elif st.session_state.get(LOAD_ERROR_KEY):
            status_slot.markdown(_note_markup(st.session_state[LOAD_ERROR_KEY]), unsafe_allow_html=True)
        elif result and result["meta"].get("stopped"):
            status_slot.markdown(
                _note_markup(f"테스트가 중간에 멈췄습니다 — {result['meta']['stopped']}"), unsafe_allow_html=True
            )

        kpi_slot.markdown(summary_markup(summary), unsafe_allow_html=True)
        rows = result["cases"] if result else []
        shown = filter_results(rows, view, query, group)
        with list_slot.container():
            selected = _render_result_list(shown, view, query, height, ran=result is not None, group=group)
        with detail_slot.container():
            _render_result_detail(selected, (result or {}).get("meta", {}).get("functions") or {}, height)


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

/* ---------------------------------------------- 실행 개요 */
.st-key-test_tab .tt-ovs {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(10.5rem, 1fr));
  gap: 0.35rem 0.9rem; font-size: 0.8rem; padding: 0.5rem 0.75rem;
  border: 1px solid var(--tt-line); border-radius: 10px; background: var(--tt-softer);
}
.st-key-test_tab .tt-ov-k { opacity: 0.6; font-size: 0.72rem; }
.st-key-test_tab .tt-ov-v { font-weight: 600; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }

/* ---------------------------------------------- 기능별 결과 */
.st-key-test_tab .tt-rss { display: grid; grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr)); gap: 0.3rem 0.8rem; }
.st-key-test_tab .tt-rs {
  display: grid; grid-template-columns: 1fr auto auto; gap: 0.5rem; font-size: 0.8rem;
  padding: 0.2rem 0.45rem; border-radius: 6px; background: var(--tt-softer);
}
.st-key-test_tab .tt-rs-ng { color: var(--tt-ng); background: rgba(229, 83, 75, 0.08); font-weight: 600; }

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
.st-key-test_tab .tt-kpis-empty .tt-kpi-num { opacity: 0.35; color: inherit; }
.st-key-test_tab .tt-note {
  font-size: 0.84rem; padding: 0.45rem 0.75rem; border-radius: 8px;
  color: var(--tt-ng); background: rgba(229, 83, 75, 0.10); overflow-wrap: anywhere;
}

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
