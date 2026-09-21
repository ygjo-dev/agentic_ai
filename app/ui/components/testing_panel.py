"""테스트 탭. 정답표로 발화 해석을 재고, 발화별 기능 선택 · 인자 추출 결과를 훑고 한 건씩 들여다본다.

평가는 dev/evaluation 이 한다. 이 탭은 정답표를 고르고, 「새로 실행」 · 「이어 실행」을 누르면
dev/evaluation/run_evaluation 을 백그라운드 thread 에서 부르고, 끝난 줄을 받아 그린다.

    제목 · 테스트 세트 · 실행 기록
    실행 개요 (테스트 세트 · 시작 시간 · 소요 시간 · 추론 지연시간 · 발화 · 모델 설정 · 실행 환경)
    모델 설정 (접힘. 파일 · 실행 기록 id 까지)
    실행 상태 · 새로 실행 · 이어 실행 · 중지
    전체 결과 (전체 · 성공 · 실패, 오류가 있을 때만 오류. 실패 원인 셋은 실패 카드 안에)
    기능별 결과 (접힘. 기능마다 카드 하나 — 번호와 x/y 둘만)
    보기 필터 · 기능 고르기 · 발화 검색 · 정렬
    결과 목록 (한 발화 한 줄, 고정 높이) | 선택한 발화 상세 (고정 높이)

**실행은 백그라운드 thread 하나가 한다(_Job).** 화면 script 는 그 상태를 읽기만 하고, 도는 동안
아래 몸통(_render_body)이 st.fragment(run_every=POLL_SECONDS)로 스스로 다시 그려진다. 그래서 도는 중에도
「중지」가 눌린다. thread 는 st.* · session_state 를 부르지 않는다 — 줄은 _Job 이 lock 으로 받아 둔다.
한 process 에 도는 평가는 하나뿐이다. 다른 창이 열려도 같은 _Job 을 보고 두 번째 실행을 못 한다.

    새로 실행   새 run_id · 새 폴더(outputs/local_benchmark/<run_id>/). 첫 발화부터. 누른 순간 폴더가 생김
    이어 실행   불러온 끝나지 않은 local 기록 그대로. 같은 run_id · 같은 폴더에서 남은 발화만
                조건(run_evaluation.resume_check)이 다르면 단추는 보이되 눌리지 않고, 다른 조건을 펼쳐 보인다
    중지        지금 부르고 있는 발화 하나는 끝까지 기다려 남기고, 다음 발화는 안 부른다.
                기록은 run.json 없이 meta.json + cases.jsonl 로 남아 「중단됨」이 된다
    그 밖의 조작(테스트 세트 · 기록 고르기 · 필터 · 정렬 · 행 고르기)은 폴더를 만들지 않는다

**테스트 세트는 고르는 것이다.** 고른 정답표가 발화 목록 · 발화 수 · 실행 · 저장한 실행 기록의
신원을 함께 정한다. 발화 수는 고른 파일에서 세고 화면에 숫자를 박지 않는다.

낱말은 dev/evaluation/engine/manage_benchmark 머리 주석과 같다 — 정답표 한 벌(Test Suite)은 「테스트 세트」,
한 번 잰 것(Test Run)은 「실행 기록」, 발화 하나의 결과(Case Result)는 「발화 결과」다.

**이 화면이 보는 것은 둘이다 — 기능을 옳게 골랐나, 그 기능이 읽는 인자를 옳게 뽑았나.**
workflow 를 부를 수 있었나(materialize 판정)는 결과에 남아 있지만 여기서 보이지 않는다.
실행 하드웨어는 재현을 위해 GPU 이름 · VRAM 만 보인다. 온도는 보이지 않는다.

**결과 표는 고른 테스트 세트의 발화 목록 한 벌이다.** 테스트 세트를 고르면 그 정답표 YAML 의 발화가
전부 「대기」 줄로 바로 선다(suite_rows). LLM 은 안 부른다. 실행은 줄을 덧붙이지 않고, 발화 하나가
끝날 때마다 같은 case_id 의 줄을 결과로 갈아 끼운다(table_rows). 실행 중에도 줄 수가 그대로다.

**결과 칸 하나가 발화의 끝을 말한다.** 성공 · 실패 · 기능 선택 · 실패 · 인자 추출 · 실패 · 범위 밖 처리 · 오류 · 대기.
실패 셋은 모델이 잘못한 것이고, 오류(failure_stage=error)는 예외로 Resolve 결과를 못 받은 것이라 실패에 안 센다.
KRRI · MCP 실행 오류가 아니다. 대기는 아직 안 돈 것이다.

**정렬은 파이썬이 한다(sort_rows).** 정렬 칸 · 방향을 session_state 에 두고 표에 넘기기 전에 줄을 세운다.
st.dataframe 의 머리글 정렬은 브라우저에만 있어 행을 누르는 rerun 에 처음 차례로 돌아갔다. 그래서 끈다 —
칸 고르기(single-column)를 켜면 머리글 정렬이 꺼지고, 고른 칸은 _keep_row_selected 가 버린다.

**새로 잰 결과와 불러온 실행 기록이 같은 길로 그려진다.** 실행 기록을 고르면 manage_benchmark.load_benchmark 가
돌려준 결과 한 벌을 방금 잰 결과와 같은 자리(RESULT_KEY)에 두고, 테스트 세트 고르기를 그 기록의 정답표로
맞춘다. 표는 그 정답표의 대기 줄 위에 저장된 결과를 case_id 로 얹은 것이다. 그리는 함수가 따로 없다.
실행 기록 목록은 manage_benchmark.list_benchmarks 하나가 official · local 을 합쳐 준다. 이 탭은 폴더를 안 뒤진다.
테스트 세트를 바꾸면 지난 결과 · 고른 실행 기록을 지우고 새 세트의 대기 줄만 남긴다.

**여기서 채점하지 않는다.** 성공 · 실패 · 실패 단계(passed · failure_stage) · 기능이 맞았나
(recipe_correct) · 정답표에 적은 값마다 맞았나(spoken_fields) 는 run_evaluation 결과에 이미 있다.
이 탭은 그 칸을 읽어 글자와 색으로 바꾼다. 값끼리 맞대지 않는다.

**LLM 은 「새로 실행」 · 「이어 실행」을 누를 때만 부른다.** 결과는 session_state 에 두고 필터 · 검색 ·
정렬 · 행 선택 · 탭 전환은 그것만 다시 그린다.

**상세는 성공과 실패가 같은 틀이다.** 정답표와 AI 모델 출력을 좌우로 맞대고,
실패면 틀린 칸만 강조한다. 인자는 정답표에 적은 것과 모델이 낸 것을 빠짐없이 보인다.
기대 기능이 읽지 않는 인자는 두 칸 다 「사용 안 함」으로 흐리게 둔다 — 읽는데 값이 null 인 「없음」과 다르다.

화면 낱말은 사람이 읽는 말로 쓴다. 기능 번호는 「기능 015」로 보이고, 인자는
표시명이 있으면 표시명 아래에 변수명을 작게 단다. 표시명이 없는 인자도 변수명
그대로 나온다 — 새 인자가 들어와도 여기를 안 고친다.

**기능 번호가 보이는 자리에는 그 기능이 무엇을 하는지가 마우스에 붙는다.** 번호를 그리는
자리는 전부 `number_markup` 하나를 지난다 (기대 기능 · AI 가 고른 기능 · 후보 기능 ·
기능별 결과 · 모델 판단 문장 안의 번호). 설명의 원천은 run_evaluation 결과 meta.functions 하나고,
화면에 {번호: 설명} 표를 따로 두지 않는다.

    ★ 두 자리는 못 붙인다. 결과 목록 표의 「기능」 칸과 기능 고르기 목록이다.
      st.dataframe 은 칸 값마다의 tooltip 을 받는 파이썬 API 가 없고(Streamlit 1.62 의
      column_config 는 칸 머리의 help 만 받는다), st.selectbox 도 보기마다의 tooltip 이 없다.
      둘 다 고르면 상세 칸에 그 기능의 설명이 그대로 나온다.

      Result-grid per-cell feature tooltip: deferred until later UI/chart refinement
      because native Streamlit 1.62 st.dataframe has no per-cell tooltip API.
      표를 custom HTML · 다른 grid · 새 frontend component 로 갈아 끼우면 tooltip 하나를
      얻는 값으로 행 선택 · 정렬 · 스크롤 · 높이가 전부 다시 만들어야 하는 것이 된다.

CSS 는 .st-key-test_tab 안으로만 건다. 서비스 화면에 새지 않는다. 한 자리만 예외다 —
결과 표 칸 머리의 설정 메뉴는 portal 로 탭 밖에 그려진다 (panel_css 에 까닭이 적혀 있다).
"""

import datetime
import html
import itertools
import json
import re
import threading
from functools import partial
from pathlib import Path

import pandas as pd
import streamlit as st

from dev.evaluation.engine import load_test_suite as evaluation_suite

# 인자 표시명. 여기 없는 인자는 변수명 그대로 나온다.
# argument 는 기능마다 뜻이 달라 표시명을 두지 않는다.
FIELD_LABELS = {
    "travel_mode": "이동 방식",
    "minutes": "시간",
    "admin_level": "행정구역 단계",
}

STATUS_LABELS = {"SELECT": "선택", "CLARIFY": "되묻기", "NO_MATCH": "해당 없음"}
# run_evaluation 결과의 failure_stage 값 -> 화면 글자. error 는 실패가 아니라 평가가 결과를 못 받은 것이다
STAGE_LABELS = {"function": "기능 선택", "input": "인자 추출", "scope": "범위 밖 처리", "error": "오류"}
# 모델이 잘못한 단계. error 는 여기 안 든다
QUALITY_STAGES = ("function", "input", "scope")
SUCCESS_TEXT = "성공"
ERROR_TEXT = STAGE_LABELS["error"]

# 범위 밖 갈래 -> 화면 글자. ambiguous · insufficient 는 옛 실행 기록을 불러올 때만 나옴
CATEGORY_LABELS = {"unsupported": "지원하지 않는 요청", "ambiguous": "기능 여럿", "insufficient": "정보 부족"}

ALL, FAILED = "전체", "실패"
# 실패를 가른 것들. 보기 필터에서 실패에 딸린 자리로 보인다 (panel_css 가 앞에 선을 긋고 눌러 둠).
FAILURE_FILTERS = tuple(STAGE_LABELS[stage] for stage in QUALITY_STAGES)
FILTERS = (ALL, FAILED, *FAILURE_FILTERS)
# 딸린 자리가 시작하는 칸 번호(1부터). CSS 에 숫자를 박지 않으려고 여기서 센다.
FIRST_FAILURE_FILTER = len(FILTERS) - len(FAILURE_FILTERS) + 1
# 오류가 있는 결과에서만 FILTERS 뒤에 붙는 보기. 실패에 딸리지 않는다
ERROR_FILTER = ERROR_TEXT

# 결과 칸 글자의 차례. 결과로 정렬할 때 이 차례다. 대기는 값이 없는 줄이라 늘 뒤에 간다
RESULT_ORDER = (SUCCESS_TEXT, *(f"실패 · {label}" for label in FAILURE_FILTERS), ERROR_TEXT)

# 결과 표를 세울 수 있는 칸. 값이 없는 줄(대기 · 지연시간 없음)은 방향과 상관없이 뒤에 간다
SORT_COLUMNS = ("번호", "기능", "발화", "결과", "추론 지연시간")
ASCENDING, DESCENDING = "오름차순", "내림차순"
SORT_ORDERS = (ASCENDING, DESCENDING)
SORT_ORDER_LABELS = {ASCENDING: "↑ 오름차순", DESCENDING: "↓ 내림차순"}

# 기능 고르기의 두 자리. 나머지는 기대 recipe id 다.
ALL_GROUPS, OUT_OF_SCOPE_GROUP = "__all__", "__out_of_scope__"

NONE_TEXT = "없음"
# 아직 안 돈 발화. 성공도 실패도 아니다
PENDING_TEXT = "대기"
# 실행 기록 고르기 글자 끝에 붙는 보관 갈래. run_id 에는 안 들어간다
KIND_LABELS = {"official": "공식", "local": "로컬"}
EMPTY_NUMBER = "—"
# 기대 기능이 그 인자를 읽지 않음. 「없음」(읽는데 값이 null)과 다르다
UNUSED_TEXT = "사용 안 함"

# 새로 실행이 run_evaluation 에 넘기는 값. 화면에 안 보인다.
# materialize 는 켠다. 화면에는 안 보이지만 결과(실행 기록)에 남겨 뒤에 실행 화면이 쓴다.
# MCP 는 안 부른다. 문맥은 계기판 기본값(both)과 같다. GPU 쉼표는 run_selected 가 넘기는
# monitor_gpu.GpuMonitor(gate=True) 가 맡는다 (3건마다 5초 · 뜨거우면 멈춤). 온도는 결과에 안 남는다.
RUN_OPTIONS = {"materialize": True, "context_label": "both"}

# 모델 설정 칸. 화면 글자 -> run_evaluation 결과 meta.conditions 의 칸. 파일 셋은 경로만 보임
CONDITION_ROWS = (
    ("모델", "model"),
    ("provider", "provider"),
    ("프롬프트 파일", "prompt"),
    ("응답 형식 파일", "response_schema"),
    ("기능 정의 파일", "menu"),
)

# provider 요청 설정(meta.conditions.request)의 화면 이름. 여기 없는 칸은 그 이름 그대로 나온다.
REQUEST_LABELS = {
    "temperature": "Temperature",
    "seed": "Seed",
    "max_tokens": "Max tokens",
    "reasoning_effort": "Reasoning effort",
    "num_ctx": "Context",
}

# session_state 자리
RESULT_KEY = "test_result"           # {"dataset_id", "result", "kind"} 마지막으로 잰 결과 또는 불러온 실행 기록
RUN_ERROR_KEY = "test_run_error"     # 실행이 예외로 끝났을 때의 문장
SELECTED_KEY = "test_selected_id"
LIST_VIEW_KEY = "test_list_view"     # 표를 마지막으로 그린 (보기, 검색어)
LIST_ROUND_KEY = "test_list_round"   # (보기, 검색어)가 바뀐 횟수. 표 key 에 들어감
SAVED_KEY = "test_saved_run"         # 실행 기록 고르기 widget. 값은 "<kind>:<run_id>"
GROUP_KEY = "test_group"             # 기능 고르기 widget
SAVED_RESET_KEY = "test_saved_reset" # 다음 회차에 실행 기록 고르기를 「불러올 기록 고르기」로 되돌림
DATASET_KEY = "test_set"             # 테스트 세트 고르기 widget
LOAD_ERROR_KEY = "test_load_error"   # 실행 기록을 못 읽었을 때의 문장
FILTER_KEY = "test_filter"           # 보기 필터 widget
SORT_COLUMN_KEY = "test_sort_column" # 정렬 칸 widget. 값은 SORT_COLUMNS 중 하나
SORT_ORDER_KEY = "test_sort_order"   # 정렬 방향 widget. 값은 SORT_ORDERS 중 하나
JOB_KEY = "test_job"                 # 이 창이 지켜보는 _Job 의 token. 끝나면 결과를 받아 옴
RESUME_KEY = "test_resume_check"     # {"key", "check"} 불러온 기록의 이어 실행 판정 (run_evaluation.resume_check)
STARTED_KEY = "test_started"         # 몸통 fragment 안에서 실행을 시작했다. 화면 전체를 한 번 다시 그림

# 도는 동안 몸통을 다시 그리는 간격(초).
POLL_SECONDS = 1.0

# 결과 목록 · 상세의 높이(px). 창 높이에서 위쪽 머리 부분을 뺀 값이다.
LIST_MIN_HEIGHT, LIST_MAX_HEIGHT = 420, 720
HEAD_HEIGHT = 520


# ================================================================ 데이터
def summarize(result: dict | None) -> dict | None:
    """전체 결과 카드의 숫자. 결과가 없으면 None.

    출력  {"total", "done", "passed", "failed", "function", "input", "scope", "error", "oos_runs"}
          total 은 잴 발화 수, done 은 끝난 발화 수
          function · input · scope · error 는 그 단계에서 멈춘 건수. run_evaluation 이 발화마다 단계를
          하나만 적음(오류 -> 기능 선택 -> 인자 추출 차례로 먼저 걸린 것). 범위 밖은 scope 뿐
          failed 는 모델이 잘못한 것(function + input + scope). 오류(error)는 실패에 안 셈
          oos_runs 는 범위 밖 발화 수. 옛 결과에 칸이 없으면 0
    규칙  run_evaluation 결과 summary.total 을 옮겨 적음. 여기서 세지 않음
          실행 중 결과(live_result)면 total 은 잴 수 전체, 성공 · 실패는 끝난 것만.
          불러온 기록이면 total 은 그 기록이 잴 수 전체(manage_benchmark.planned_runs). 중단된 기록도 전체가 보임
    """
    from dev.evaluation.engine import manage_benchmark

    if not result:
        return None
    total = result["summary"]["total"]
    stages = total["failure_stages"]
    planned = result.get("planned") or manage_benchmark.planned_runs(result.get("meta") or {})
    return {
        "total": max(planned or 0, total["runs"]),
        "done": total["runs"],
        "passed": total["passed"],
        "failed": sum(stages.get(stage, 0) for stage in QUALITY_STAGES),
        "function": stages.get("function", 0),
        "input": stages.get("input", 0),
        "scope": stages.get("scope", 0),
        "error": stages.get("error", 0),
        "oos_runs": total.get("oos_runs", 0),
    }


def live_result(rows: list[dict], planned: int) -> dict:
    """실행 중 화면에 그릴 결과. 끝난 결과 줄만 담음.

    입력  run_evaluation 이 progress 로 넘긴 결과 줄들 · 잴 발화 수
    출력  {"summary", "cases", "planned"}. summarize · filter_results 가 끝난 결과처럼 읽음
    규칙  합계는 score.summarize 로 셈. 판정은 줄에 이미 있음
    제약  줄을 다시 채점하지 않는다
    """
    from dev.evaluation.engine import score

    return {"summary": score.summarize(rows, ()), "cases": list(rows), "planned": planned}


def pending(row: dict) -> bool:
    """아직 안 돈 발화의 대기 줄인가."""
    return row.get("pending") is True


def failed(row: dict) -> bool:
    """끝났고 모델이 잘못한 줄인가(기능 선택 · 인자 추출 · 범위 밖 처리). 대기 · 오류 줄은 실패가 아님."""
    return row.get("passed") is False and row.get("failure_stage") != "error"


def errored(row: dict) -> bool:
    """끝났는데 예외로 Resolve 결과를 못 받은 줄인가 (failure_stage=error)."""
    return row.get("passed") is False and row.get("failure_stage") == "error"


@st.cache_data(show_spinner=False)
def _suite_rows(path: str, modified: int) -> list[dict]:
    """정답표 한 벌의 대기 줄. 파일이 바뀔 때만 다시 만듦."""
    from dev.evaluation.engine import score

    suite = evaluation_suite.load(Path(path))
    label_of = evaluation_suite.label_of(suite)
    return [
        {
            **score.case_head(case, label_of[case["group"]], 1),
            "pending": True,
            "passed": None,
            "failure_stage": None,
            "recipe_correct": None,
            "spoken_fields": [],
            "actual": None,
            "timing": None,
            "error": None,
        }
        for case in suite["cases"]
        if case["enabled"]
    ]


def suite_rows(dataset_id: str) -> list[dict]:
    """고른 테스트 세트의 결과 표 뼈대. 실행이 도는 발화마다 대기 줄 하나, 정답표 차례.

    출력  결과 줄과 같은 앞머리(score.case_head)에 pending True · passed None. 못 찾으면 빈 목록
    규칙  실행(run_evaluation.run_dataset)이 도는 발화와 같은 것(enabled)만. 정답표 파일에서 셈
    제약  LLM · Resolve 를 부르지 않는다. 판정 칸을 지어내지 않는다
    """
    entry = next((entry for entry in evaluation_suite.datasets() if entry["id"] == dataset_id), None)
    if entry is None or not Path(entry["path"]).is_file():
        return []
    path = Path(entry["path"])
    return _suite_rows(str(path), path.stat().st_mtime_ns)


def table_rows(skeleton: list[dict], cases: list[dict]) -> list[dict]:
    """결과 표의 줄. 대기 줄 위에 끝난 결과 줄을 case_id 로 얹은 것.

    입력  skeleton 은 suite_rows. cases 는 run_evaluation 결과 cases (끝난 것만이어도 됨)
    출력  정답표 차례. 결과가 있는 case_id 는 그 결과 줄, 없으면 대기 줄 그대로
    규칙  줄 자리는 case_id 로 찾음. 줄 차례(도착 순서)로 찾지 않음
          한 case_id 에 결과가 여럿(runs 여럿)이면 그 자리에 차례대로 놓음
          정답표에 없는 case_id 의 결과는 뒤에 붙임 (다른 판의 정답표로 잰 옛 기록)
    제약  줄을 덧붙여 늘리지 않는다. 결과 줄을 다시 채점하지 않는다
    """
    by_case: dict = {}
    for row in cases:
        by_case.setdefault(row["case_id"], []).append(row)
    rows = []
    for row in skeleton:
        rows.extend(by_case.pop(row["case_id"], None) or [row])
    for rest in by_case.values():
        rows.extend(rest)
    return rows


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

    입력  run_evaluation 결과 cases. view 는 FILTERS 중 하나. 모르는 값이면 전체
          group 은 ALL_GROUPS · OUT_OF_SCOPE_GROUP · 기대 recipe id
    출력  원래 순서를 지킨 부분 목록
    규칙  실패는 기능 선택 · 인자 추출 · 범위 밖 처리 셋 중 하나에서 멈춘 것. 대기 · 오류 줄은 실패가 아님
          기능 선택 · 인자 추출 · 범위 밖 처리는 그 단계에서 실패한 것. 오류(ERROR_FILTER)는 오류 줄만
          group 이 ALL_GROUPS 가 아니면 row_group 이 같은 줄만
          검색은 띄어쓰기를 무시한 부분 일치. 빈 검색어는 거르지 않음
    """
    if view == FAILED:
        shown = [r for r in rows if failed(r)]
    elif view == ERROR_FILTER:
        shown = [r for r in rows if errored(r)]
    elif view in FAILURE_FILTERS:
        stage = next(k for k, v in STAGE_LABELS.items() if v == view)
        shown = [r for r in rows if failed(r) and r.get("failure_stage") == stage]
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
    """기능 고르기 글자. 「기능 015 · 5건 · 실패 1」 꼴. 오류가 있으면 「· 오류 N」을 더 붙임."""
    if group == ALL_GROUPS:
        return "모든 기능"
    members = [r for r in rows if row_group(r) == group]
    name = "범위 밖" if group == OUT_OF_SCOPE_GROUP else function_label(group)
    lost = sum(1 for r in members if failed(r))
    broken = sum(1 for r in members if errored(r))
    return f"{name} · {len(members)}건" + (f" · 실패 {lost}" if lost else "") + (f" · {ERROR_TEXT} {broken}" if broken else "")


def verdict_label(row: dict) -> str:
    """결과 칸 글자. 대기 · 성공 · 실패 · 기능 선택 · 실패 · 인자 추출 · 실패 · 범위 밖 처리 · 오류 중 하나.

    규칙  오류(failure_stage=error)는 「실패 · …」가 아님. 모델 품질 실패가 아니라 결과를 못 받은 것
    """
    if pending(row):
        return PENDING_TEXT
    if row["passed"]:
        return SUCCESS_TEXT
    if errored(row):
        return ERROR_TEXT
    stage = STAGE_LABELS.get(row.get("failure_stage"))
    return f"실패 · {stage}" if stage else "실패"


def _sort_key(row: dict, column: str):
    """정렬 칸 하나의 값. 값이 없는 줄(대기 결과 · 지연시간 없음)은 None."""
    if column == "기능":
        group = row_group(row)
        return (1, 0) if group == OUT_OF_SCOPE_GROUP else (0, _recipe_number(group or ""))
    if column == "발화":
        return row["utterance"]
    if column == "결과":
        label = verdict_label(row)
        return RESULT_ORDER.index(label) if label in RESULT_ORDER else None
    if column == "추론 지연시간":
        value = (row.get("timing") or {}).get("resolve_s")
        return value if isinstance(value, (int, float)) else None
    return row["case_id"], row.get("run", 1)


def sort_rows(rows: list[dict], column: str = SORT_COLUMNS[0], order: str = ASCENDING) -> list[dict]:
    """결과 표 줄을 정렬 칸 · 방향으로 세운 새 목록.

    규칙  같은 값끼리는 번호(case_id · run) 오름차순. 방향을 바꿔도 이 차례는 그대로
          값이 없는 줄(_sort_key 가 None)은 방향과 상관없이 맨 뒤, 번호 차례
          모르는 칸이면 번호로
    제약  줄을 고치거나 거르지 않는다
    """
    column = column if column in SORT_COLUMNS else SORT_COLUMNS[0]
    base = sorted(rows, key=lambda row: (row["case_id"], row.get("run", 1)))
    valued = [row for row in base if _sort_key(row, column) is not None]
    empty = [row for row in base if _sort_key(row, column) is None]
    valued.sort(key=lambda row: _sort_key(row, column), reverse=order == DESCENDING)
    return valued + empty


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


def recipe_ids_in(text: str) -> list[str]:
    """글자 안에 적힌 기능 id 들. 나온 차례 그대로."""
    return re.findall(r"\brecipe_\d+", str(text))


def field_rows(row: dict) -> list[dict]:
    """인자 비교 줄. 기대 기능이 읽는 인자와 모델이 낸 인자를 빠짐없이.

    출력  [{"name", "label", "used", "graded", "answer", "model", "in_model", "correct"}]
    규칙  모델 출력 차례가 먼저, 모델이 안 낸 인자는 뒤에 정답표 · 읽는 칸 차례로
          used 는 기대 기능(Recipe.execution)이 그 인자를 읽나. run_evaluation 이 적은 expected.reads.
          그 칸이 없는 옛 결과면 정답표에 적은 이름(정답표는 읽는 칸만 적음)
          graded 는 정답표에 그 이름이 적혔나. run_evaluation 의 spoken_fields 에 있는 이름임
          correct 는 run_evaluation 이 맞댄 결과 그대로. 채점하지 않은 칸이면 None
          answer 는 정답표에 적은 값. 안 적었으면 None
          label 은 FIELD_LABELS 에 없으면 변수명 그대로
    제약  값끼리 맞대지 않는다. 판정은 run_evaluation 결과에 있음
    """
    graded = {field["name"]: field for field in row.get("spoken_fields") or []}
    reads = row["expected"].get("reads")
    used = set(reads) if reads is not None else set(graded)
    model = ((row.get("actual") or {}).get("spoken")) or {}
    names = [*model, *(name for name in [*graded, *sorted(used)] if name not in model)]
    names = list(dict.fromkeys(names))
    return [
        {
            "name": name,
            "label": FIELD_LABELS.get(name, name),
            "used": name in used,
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
    """결과 목록 표. 한 발화 한 줄, 칸 다섯. 추론 지연시간은 resolve 한 번에 걸린 시간.

    규칙  결과 칸은 verdict_label. 대기 줄은 결과 「대기」, 추론 지연시간 빈칸
          판정 칸을 따로 두지 않음. 모델이 낸 판정 상태(SELECT · CLARIFY · NO_MATCH)는 상세에 있음

    제약  기능 칸에 설명을 붙이지 않는다. st.dataframe 은 칸 값마다의 tooltip 을 받는 API 가 없다.
          줄을 고르면 상세 칸에 그 기능의 설명이 나온다
    """
    return pd.DataFrame(
        {
            "번호": [f"{r['case_id']:03d}" for r in rows],
            "기능": ["범위 밖" if row_group(r) == OUT_OF_SCOPE_GROUP else (function_label(row_group(r)) or "") for r in rows],
            "발화": [r["utterance"] for r in rows],
            "결과": [verdict_label(r) for r in rows],
            "추론 지연시간": [_seconds((r.get("timing") or {}).get("resolve_s")) for r in rows],
        }
    )


def list_height(ratios: dict) -> int:
    """결과 목록 · 상세 칸의 높이(px). 창 높이를 따라가되 범위 안에서."""
    viewport = int(ratios.get("viewport_height") or 0)
    return max(LIST_MIN_HEIGHT, min(LIST_MAX_HEIGHT, viewport - HEAD_HEIGHT))


def request_rows(conditions: dict) -> dict:
    """provider 요청 설정. {화면 글자: 값}. Temperature 가 맨 앞. 못 읽은 기록이면 빈 dict.

    규칙  run_evaluation 결과 meta.conditions.request (provider 코드가 실제로 싣는 값을 run_evaluation 이 읽어 둔 것)
          화면 글자는 REQUEST_LABELS, 없는 칸은 이름 그대로. 값은 그대로 글자로
    제약  값을 여기 적지 않는다. 옛 결과에 칸이 없으면 안 보일 뿐임
    """
    request = conditions.get("request") or {}
    if not isinstance(request, dict) or "error" in request:
        return {}
    ordered = sorted(request, key=lambda key: (key != "temperature", list(REQUEST_LABELS).index(key) if key in REQUEST_LABELS else 99))
    return {REQUEST_LABELS.get(key, key): display_value(request[key]) for key in ordered}


def run_conditions(result: dict | None) -> dict | None:
    """모델 설정 전부. {화면 글자: 값}. 결과가 없으면 None.

    규칙  run_evaluation 결과 meta.conditions 에서 옮김. 모델 · provider · 요청 설정(Temperature 등) ·
          호출 상한 · 파일 셋(경로만)
          조건을 못 읽은 결과면 그 까닭 한 줄
    """
    if not result:
        return None
    conditions = result["meta"].get("conditions") or {}
    if "error" in conditions:
        return {"모델 설정": conditions["error"]}
    shown = {}
    for label, key in CONDITION_ROWS[:2]:
        shown[label] = conditions.get(key)
    shown.update(request_rows(conditions))
    timeout = (conditions.get("inference") or {}).get("timeout")
    if timeout is not None:
        shown["호출 상한"] = f"{timeout}초"
    for label, key in CONDITION_ROWS[2:]:
        value = conditions.get(key)
        shown[label] = value.get("path") if isinstance(value, dict) else value
    return {label: value if value is not None else NONE_TEXT for label, value in shown.items()}


def _elapsed(seconds) -> str:
    if not isinstance(seconds, (int, float)):
        return EMPTY_NUMBER
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}분 {rest}초" if minutes else f"{rest}초"


def environment_rows(result: dict) -> dict:
    """실행 환경. {"GPU": …, "VRAM": …}. 기록이 없으면 두 칸 다 「기록 없음」.

    규칙  run_evaluation 결과 meta.environment.gpus. 이름이 모두 같으면 「이름 × 장수」, 다르면 이름을 이음
          VRAM 은 GPU 마다의 총량(GiB). 모두 같으면 「장당 N GiB」
          온도 · 사용률은 안 보임 (옛 결과의 meta.gpu 도 안 읽음)
    """
    gpus = ((result["meta"].get("environment") or {}).get("gpus")) or []
    if not gpus:
        return {"GPU": "기록 없음", "VRAM": "기록 없음"}
    names = [gpu.get("name") or "?" for gpu in gpus]
    name = f"{names[0]} × {len(names)}" if len(set(names)) == 1 else " · ".join(names)
    sizes = [gpu.get("memory_total_mib") for gpu in gpus]
    if any(size is None for size in sizes):
        vram = "기록 없음"
    elif len(set(sizes)) == 1:
        vram = f"장당 {sizes[0] / 1024:.1f} GiB"
    else:
        vram = " · ".join(f"{size / 1024:.1f} GiB" for size in sizes)
    return {"GPU": name, "VRAM": vram}


def run_identity(result: dict) -> dict:
    """실행 기록 id 와 저장 자리. 모델 설정 아래 두 줄. 없으면 그 줄을 뺌."""
    meta = result["meta"]
    shown = {}
    if meta.get("run_id"):
        shown["실행 기록 id"] = meta["run_id"]
    if meta.get("saved_to"):
        shown["저장 위치"] = meta["saved_to"]
    return shown


def suite_filename(suite: dict) -> str:
    """결과 meta.suite 를 저장소의 파일 이름으로. 「test_suite_v2.yaml」 꼴.

    규칙  meta.suite.path 의 파일 이름 -> 등록된 정답표의 파일 이름(dataset_id 로 찾음) -> 「정답표」
    제약  사람용 별칭(meta.suite.label)을 앞에 두지 않는다 — 화면에 보이는 이름이
          dev/evaluation/inputs/test_suites/ 의 파일과 바로 맞아야 무엇을 잰 것인지 되짚을 수 있다
    """
    if suite.get("path"):
        return Path(suite["path"]).name
    for entry in evaluation_suite.datasets():
        if entry["id"] == suite.get("dataset_id"):
            return Path(entry["path"]).name
    return "정답표"


def overview(result: dict | None) -> list[tuple[str, list[tuple[str, str]]]] | None:
    """실행 개요. [(칸 이름, [(글자, 값)])]. 결과가 없으면 None.

    칸  테스트 세트 · 시작 시간 · 소요 시간 · 추론 지연시간(Median · P95 · Max) ·
        발화(전체 · 성공 · 실패 · 오류) · 모델 설정(모델 · Temperature …) · 실행 환경(GPU · VRAM)
    규칙  run_evaluation 결과 meta · summary 를 옮겨 적음. 여기서 세지 않음
          평가 지표(기능 선택 · 인자 추출 등)는 여기 안 둠. 아래 전체 결과가 보임
          추론 지연시간은 resolve 한 번에 걸린 시간의 분포. 잰 것이 없으면 줄표
          실행 기록 id 는 여기 안 보임 (정답표 이름이 들어 있어 개발 용어가 샘). 모델 설정 접힘 칸에 있음
    """
    if not result:
        return None
    meta, summary = result["meta"], result["summary"]
    total = summary["total"]
    started = meta.get("started_at")
    delay = summary.get("latency") or {}
    conditions = meta.get("conditions") or {}

    def seconds(key):
        return f"{delay[key]:.2f}초" if isinstance(delay.get(key), (int, float)) else EMPTY_NUMBER

    model = [("모델", str(conditions.get("model") or EMPTY_NUMBER))]
    request = request_rows(conditions)
    model += [(label, value) for label, value in request.items() if label == REQUEST_LABELS["temperature"]]
    if REQUEST_LABELS["temperature"] not in request:
        model.append((REQUEST_LABELS["temperature"], "기록 없음"))
    return [
        ("테스트 세트", [("", suite_filename(meta.get("suite") or {}))]),
        ("시작 시간", [("", f"{datetime.datetime.fromisoformat(started):%Y-%m-%d %H:%M:%S}" if started else EMPTY_NUMBER)]),
        ("소요 시간", [("", _elapsed(meta.get("elapsed_s")))]),
        ("추론 지연시간", [("Median", seconds("median")), ("P95", seconds("p95")), ("Max", seconds("max"))]),
        ("발화", [
            ("전체", str(total["runs"])),
            ("성공", str(total["passed"])),
            ("실패", str(total["runs"] - total["passed"] - total["failure_stages"].get("error", 0))),
            ("오류", str(total["errors"])),
        ]),
        ("모델 설정", model),
        ("실행 환경", list(environment_rows(result).items())),
    ]


def _recipe_number(recipe_id: str) -> int:
    """기능 번호의 숫자. "recipe_061" -> 61. 숫자가 없으면 아주 큰 수(뒤로)."""
    tail = str(recipe_id).rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 10**9


def recipe_rows(result: dict | None) -> list[dict]:
    """기능별 결과. [{group, label, runs, passed, failed}] 기능 번호의 숫자 차례.

    규칙  run_evaluation 결과 summary.recipes 를 옮김. 범위 안(지원하는 기능)만. 범위 밖은 기능이 아니라 안 넣음
          차례는 번호를 숫자로 읽어 오름차순 (글자 차례가 아님)
    """
    if not result:
        return []
    entries = [
        {"group": rid, "label": function_label(rid), "runs": v["runs"], "passed": v["passed"], "failed": v["runs"] - v["passed"]}
        for rid, v in (result["summary"].get("recipes") or {}).items()
    ]
    return sorted(entries, key=lambda e: _recipe_number(e["group"]))


def first_failure(rows: list[dict]) -> int | None:
    """목록에서 첫 실패 줄의 자리, 실패가 없으면 첫 오류 줄. 없으면 None. 대기 줄은 실패가 아님."""
    found = next((i for i, r in enumerate(rows) if failed(r)), None)
    return found if found is not None else next((i for i, r in enumerate(rows) if errored(r)), None)


def saved_key(entry: dict) -> str:
    """실행 기록 고르기의 값. "<kind>:<run_id>". 불러올 때 어느 자리의 것인지를 함께 넘김."""
    return f"{entry['kind']}:{entry['run_id']}"


def saved_label(entry: dict) -> str:
    """실행 기록 고르기 글자. 「<run_id> · 성공/전체 · 공식」 꼴. 전체는 그 기록이 실제로 잰 수다.

    규칙  끝나지 않은 기록(run.json 없음)은 「<run_id> · 끝난 수/잴 수 · 중단됨 · 로컬」. 잴 수를 모르면 「중단됨」만
          끝에 보관 갈래(공식 · 로컬). 같은 run_id 가 두 자리에 다 있으면 「중복」을 더 붙임
    제약  run_id 가 먼저다. 저장 자리가 dev/evaluation/outputs/<official|local>_benchmark/<run_id>/ 라
          고르기 글자와 폴더가 1:1 로 맞아야 한다. 사람용 별칭을 앞에 두지 않는다.
          run_id 안에 이미 정답표 이름과 시각이 들어 있다
    """
    if entry.get("complete") and entry.get("runs") is not None:
        score = f"{entry['passed']}/{entry['runs']}"
    elif entry.get("planned") is not None and entry.get("done") is not None:
        score = f"{entry['done']}/{entry['planned']} · 중단됨"
    else:
        score = "중단됨"
    kind = KIND_LABELS.get(entry.get("kind"), entry.get("kind") or "")
    return f"{entry['run_id']} · {score} · {kind}" + (" · 중복" if entry.get("duplicate") else "")


@st.cache_data(show_spinner=False)
def _case_count(path: str, modified: int) -> int | None:
    """정답표에서 기본으로 도는 발화 수. 파일이 바뀔 때만 다시 읽음. 못 읽으면 None."""
    try:
        suite = evaluation_suite.load(Path(path))
    except (OSError, ValueError):
        return None
    return sum(1 for case in suite["cases"] if case["enabled"])


def dataset_label(entry: dict) -> str:
    """테스트 세트 고르기에 보일 이름. 정답표 파일 이름이 먼저고, 발화 수를 셀 수 있으면 붙임.

    제약  사람용 별칭(entry["label"])을 앞에 두지 않는다 — 고른 것이 저장소의 어느 파일인지가
          바로 보여야 한다. 발화 수는 고른 파일에서 세고 화면에 숫자를 박지 않는다
    """
    path = Path(entry["path"])
    count = _case_count(str(path), path.stat().st_mtime_ns) if path.is_file() else None
    return f"{path.name} · {count}개 발화" if count is not None else path.name


# ================================================================ 마크업
def _esc(value) -> str:
    """HTML 에 넣을 글자."""
    return html.escape(str(value))


# 전체 결과 카드 셋. (글자, summarize 칸, 색). 이것이 늘 보이는 지표의 전부다.
# 실패는 모델이 잘못한 것만 센다. 오류(failure_stage=error)는 평가가 결과를 못 받은 것이라
# 오류가 하나라도 있을 때만 ERROR_CARD 가 뒤에 따로 선다. 없을 때 0 카드를 세우지 않는다.
RESULT_CARDS = (
    ("전체", "total", ""),
    ("성공", "passed", "ok"),
    ("실패", "failed", "ng"),
)
ERROR_CARD = (ERROR_TEXT, "error", "err")

# 실패 카드 **안에** 들어가는 원인 셋. 동등한 지표가 아니라 실패를 가른 것이다.
FAILURE_CAUSES = (
    (STAGE_LABELS["function"], "function"),
    (STAGE_LABELS["input"], "input"),
    (STAGE_LABELS["scope"], "scope"),
)

# 원인 묶음에 한 번만 붙는 말. 카드마다 같은 문장을 되풀이하지 않는다.
CAUSE_NOTE = "최초 실패 원인 기준"

# 범위 밖 발화가 없는 정답표(FULL48)에서 범위 밖 처리 원인 자리에 적는 말.
NO_OOS_NOTE = "해당 발화 없음"


def summary_markup(summary: dict | None) -> str:
    """전체 결과. 머리 한 줄과 카드 셋. 결과가 없으면 숫자 자리에 줄표만.

    규칙  전체 · 성공 · 실패가 나란한 카드 셋. 성공 · 실패는 끝난 수에 대한 백분율을 닮
          실패 원인 셋(기능 선택 · 인자 추출 · 범위 밖 처리)은 실패 카드 **안에** 들어감.
          동등한 카드로 세우면 전체 · 성공 · 실패와 같은 층으로 읽힘
          원인은 발화마다 먼저 걸린 것 하나로 셈. 그 말(CAUSE_NOTE)은 묶음에 한 번만 붙음
          오류는 실패에 안 들어감. 하나라도 있으면 ERROR_CARD 를 뒤에 따로 세움. 없으면 안 세움
          범위 밖 발화가 없는 정답표면 범위 밖 처리 자리에 「해당 발화 없음」
    """
    head = '<div class="tt-sum-title">전체 결과</div>'

    def cause(label, number, note=""):
        note_html = f'<span class="tt-cause-note">{_esc(note)}</span>' if note else ""
        return (
            f'<div class="tt-cause"><span class="tt-cause-k">{_esc(label)}</span>'
            f'<span class="tt-cause-v">{_esc(number)}</span>{note_html}</div>'
        )

    def card(label, number, tone="", note="", causes=""):
        note_html = f'<div class="tt-kpi-note">{_esc(note)}</div>' if note else ""
        return (
            f'<div class="tt-kpi {tone}"><div class="tt-kpi-label">{_esc(label)}</div>'
            f'<div class="tt-kpi-num">{_esc(number)}</div>{note_html}{causes}</div>'
        )

    def causes_block(numbers, notes):
        rows = "".join(cause(label, numbers[key], notes.get(key, "")) for label, key in FAILURE_CAUSES)
        return f'<div class="tt-causes"><div class="tt-causes-head">{_esc(CAUSE_NOTE)}</div>{rows}</div>'

    if summary is None:
        empty = causes_block({key: EMPTY_NUMBER for _label, key in FAILURE_CAUSES}, {})
        cards = [
            card(label, EMPTY_NUMBER, tone, causes=empty if key == "failed" else "")
            for label, key, tone in RESULT_CARDS
        ]
        return head + '<div class="tt-kpis tt-kpis-empty">' + "".join(cards) + "</div>"

    done = summary["done"]
    finished = done == summary["total"]

    def share(count):
        return f"{count / done:.1%}" if done else ""

    notes = {
        "total": "발화 수" if finished else f"완료 {done} / {summary['total']}",
        "passed": share(summary["passed"]),
        "failed": share(summary["failed"]),
        "error": "결과를 못 받음",
    }
    shown = RESULT_CARDS + ((ERROR_CARD,) if summary.get("error") else ())
    causes = causes_block(summary, {} if summary.get("oos_runs") else {"scope": NO_OOS_NOTE})
    return head + '<div class="tt-kpis">' + "".join(
        card(label, summary[key], tone, notes[key], causes if key == "failed" else "")
        for label, key, tone in shown
    ) + "</div>"


def conditions_markup(conditions: dict) -> str:
    """모델 설정 줄들."""
    rows = "".join(
        f'<div class="tt-cond-k">{_esc(k)}</div><div class="tt-cond-v">{_esc(v)}</div>'
        for k, v in conditions.items()
    )
    return f'<div class="tt-cond">{rows}</div>'


def overview_markup(info: list | None) -> str:
    """실행 개요. 칸마다 제목 아래 (글자 · 값) 줄을 세로로. 결과가 없으면 빈 글자."""
    if info is None:
        return ""

    def cell(title, rows):
        lines = "".join(
            f'<div class="tt-ov-row"><span class="tt-ov-sub">{_esc(label)}</span>'
            f'<span class="tt-ov-v">{_esc(value)}</span></div>'
            if label else f'<div class="tt-ov-row"><span class="tt-ov-v">{_esc(value)}</span></div>'
            for label, value in rows
        )
        return f'<div class="tt-ov"><div class="tt-ov-k">{_esc(title)}</div>{lines}</div>'

    return '<div class="tt-ovs">' + "".join(cell(title, rows) for title, rows in info) + "</div>"


def recipe_summary_markup(entries: list[dict], functions: dict | None = None) -> str:
    """기능별 결과 카드. 카드 하나에 기능 번호와 성공 수(x/y) 둘만. 기능 번호 차례.

    규칙  실패가 하나라도 있으면 붉은 카드, 다 맞았으면 차분한 카드(옆줄만 초록)
          설명은 카드 전체와 기능 번호 둘 다에 마우스로 붙음. 원천은 결과 meta.functions 하나
    제약  「모두 성공」 · 「실패 N」 같은 글자를 두지 않는다 — x/y 가 이미 같은 것을 말한다.
          기능이 마흔 가까이 되므로 성공을 강한 초록으로 칠하지 않는다. 눈에 띄는 쪽은 실패다
    """
    if not entries:
        return '<div class="tt-empty">결과가 없습니다.</div>'
    functions = functions or {}
    cards = "".join(
        f'<div class="tt-rs {"tt-rs-ng" if e["failed"] else "tt-rs-ok"}"{_tip(e["group"], functions)}>'
        f'<div class="tt-rs-fn">{number_markup(e["group"], functions)}</div>'
        f'<div class="tt-rs-n">{e["passed"]}/{e["runs"]}</div></div>'
        for e in entries
    )
    return f'<div class="tt-rss">{cards}</div>'


def _value_markup(value) -> str:
    """값 하나. 없음은 흐리게."""
    text = display_value(value)
    css = "tt-val tt-none" if text == NONE_TEXT else "tt-val"
    return f'<span class="{css}">{_esc(text)}</span>'


def _muted_markup(text: str) -> str:
    """값 자리에 넣는 흐린 글자."""
    return f'<span class="tt-val tt-none">{_esc(text)}</span>'


def _tip(recipe_id: str | None, functions: dict) -> str:
    """기능 번호에 걸 title 속성. 설명은 run_evaluation 결과 meta.functions (게시 menu 의 function 문장)."""
    text = (functions or {}).get(recipe_id)
    return f' title="{_esc(text)}"' if text else ""


def number_markup(recipe_id: str | None, functions: dict, css: str = "") -> str:
    """화면에 보이는 기능 번호 하나. 「기능 004」만 보이고 설명은 마우스를 올리면 뜸.

    입력  css 는 이 자리에서 더 붙일 class. 없으면 안 붙음
    출력  <span class="tt-fnum …" title="설명">기능 004</span>. 번호가 없으면 빈 글자
    규칙  설명의 원천은 run_evaluation 결과 meta.functions 하나 (게시 menu 의 function 문장)
          설명이 없는 번호면 title 없이 번호만 보임
    제약  기능 번호를 보이는 자리는 전부 이것을 쓴다.
          마크업에 function_label 을 직접 넣으면 그 자리만 설명이 안 뜬다.
          {번호: 설명} 표를 화면에 따로 두지 않는다
    """
    label = function_label(recipe_id)
    if label is None:
        return ""
    classes = " ".join(part for part in ("tt-fnum", css) if part)
    return f'<span class="{classes}"{_tip(recipe_id, functions)}>{_esc(label)}</span>'


def reason_markup(text: str, functions: dict) -> str:
    """모델 판단 문장. 안에 적힌 기능 id 를 「기능 NNN」으로 보이고 설명을 마우스에 붙임.

    규칙  번호 자리만 바꿈. 그 밖의 글자는 모델이 쓴 그대로 (HTML 로 새지 않게 escape)
    """
    return re.sub(r"\brecipe_\d+", lambda hit: number_markup(hit.group(0), functions), _esc(text))


def _function_markup(recipe_ids: list, functions: dict, empty: str = "선택 없음") -> str:
    """기능 번호와 설명. 고르지 않았으면 empty 글자.

    규칙  기능이 여럿이면 차례대로 모두 보임. 설명은 줄로도 보이고 번호의 마우스에도 붙음
    """
    shown = [rid for rid in recipe_ids if rid]
    if not shown:
        return f'<div class="tt-fn tt-none">{_esc(empty)}</div>'
    return "".join(
        f'<div class="tt-fn">{number_markup(rid, functions)}</div>'
        f'<div class="tt-desc">{_esc(functions.get(rid) or "")}</div>'
        for rid in shown
    )


def _key_markup(label: str, name: str | None = None) -> str:
    """줄 머리. 표시명이 변수명과 다르면 변수명을 아래에 작게."""
    sub = f'<div class="tt-var">{_esc(name)}</div>' if name and name != label else ""
    return f'<div class="tt-c tt-key"><div class="tt-key-label">{_esc(label)}</div>{sub}</div>'


def _pair_markup(key_html: str, answer_html: str, model_html: str, *, wrong: bool, graded: bool = True) -> str:
    """비교 한 줄. 줄 머리 · 정답표 · AI 모델 출력.

    입력  wrong 은 run_evaluation 이 틀렸다고 판정한 칸인가
    규칙  채점하는 칸이 틀렸으면 모델 출력 칸을 강조하고 「차이」를 닮
          graded 가 거짓인 칸(기대 기능이 안 읽는 인자)은 줄 전체를 흐리게 둠. 강조하지 않음
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


def _extra_markup(row: dict, functions: dict | None = None) -> str:
    """AI 모델 출력의 부가 정보. 판정 상태 · 후보 기능 · 판단 · 추론 지연시간. 오류면 오류 문장.

    규칙  후보 기능은 「기능 NNN」만 보이고, 마우스를 올리면 그 기능 설명(functions)이 뜸
          추론 지연시간은 이 발화의 resolve 한 번에 걸린 시간
    제약  workflow 를 부를 수 있었나(materialize 판정)는 보이지 않는다. 이 화면이 재는 것이 아님
    """
    functions = functions or {}
    model = row.get("actual") or {}
    if row.get("error"):
        status_text = STAGE_LABELS["error"]
        reason = reason_markup(row["error"], functions)
    else:
        status = model.get("status")
        status_text = STATUS_LABELS.get(status, status or NONE_TEXT)
        reason = reason_markup(model.get("reason") or NONE_TEXT, functions)
    picked = model.get("recipe_id")
    timing = row.get("timing") or {}
    chips = "".join(
        number_markup(cid, functions, "tt-chip tt-chip-on" if cid == picked else "tt-chip")
        for cid in model.get("candidate_recipe_ids") or []
    ) or f'<span class="tt-val tt-none">{NONE_TEXT}</span>'
    return (
        '<div class="tt-extra">'
        '<div class="tt-extra-head">AI 모델 출력 · 판단 내용</div>'
        f'<div class="tt-kv"><div class="tt-kv-k">모델 판정 상태</div>'
        f'<div class="tt-kv-v"><span class="tt-status">{_esc(status_text)}</span></div></div>'
        f'<div class="tt-kv"><div class="tt-kv-k">후보 기능</div><div class="tt-kv-v">{chips}</div></div>'
        f'<div class="tt-kv"><div class="tt-kv-k">모델 판단</div>'
        f'<div class="tt-kv-v tt-reason">{reason}</div></div>'
        f'<div class="tt-kv"><div class="tt-kv-k">추론 지연시간</div>'
        f'<div class="tt-kv-v">{_esc(_seconds(timing.get("resolve_s")) or NONE_TEXT)}</div></div>'
        "</div>"
    )


def detail_markup(row: dict, functions: dict) -> str:
    """선택한 발화 상세. 성공 · 실패가 같은 틀.

    입력  run_evaluation 결과 cases 한 줄 · meta.functions
    규칙  맨 위 한 줄에 번호 · 발화 · 결과(verdict_label). 오류는 실패와 다른 색
          정답표 | AI 모델 출력 두 칸에 기능 번호 · 설명과 인자 전부(field_rows)
          기능 칸 강조는 run_evaluation 의 recipe_correct, 인자 칸 강조는 spoken_fields 의 correct
          인자 값 칸은 셋으로 가름 — 기대 기능이 안 읽는 인자는 두 칸 다 「사용 안 함」,
          읽는데 값이 null 이면 「없음」, 값이 있으면 그 값
          범위 밖 발화는 기능 칸에 「범위 밖 · 선택할 기능 없음」과 모델이 고른 것을 맞댐. 인자 줄 없음.
          강조는 run_evaluation 의 passed
          그 아래 AI 모델 출력의 판정 상태 · 후보 기능(설명은 마우스를 올리면) · 판단 · 추론 지연시간
    """
    if pending(row):
        return pending_markup(row)
    model = row.get("actual") or {}
    has_error = bool(row.get("error"))
    tone = "ok" if row["passed"] else "err" if errored(row) else "ng"
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
    picked = _function_markup([model.get("recipe_id")], functions, STAGE_LABELS["error"] if has_error else
                              STATUS_LABELS.get(model.get("status"), "선택 없음") if model.get("status") != "SELECT" else "선택 없음")

    if row.get("scope") == "out_of_scope":
        category = row["expected"].get("category")
        rows += [
            '<div class="tt-sec">기능 선택</div>',
            _pair_markup(
                _key_markup("기능"),
                f'<div class="tt-fn">범위 밖 · 선택할 기능 없음</div>'
                f'<div class="tt-desc">{_esc(CATEGORY_LABELS.get(category, category))}</div>',
                picked,
                wrong=not row["passed"],
            ),
        ]
        return f'{head}<div class="tt-cmp">{"".join(rows)}</div>{_extra_markup(row, functions)}'

    rows += [
        '<div class="tt-sec">기능 선택</div>',
        _pair_markup(
            _key_markup("기능"),
            _function_markup(row["expected"]["recipe_ids"], functions),
            picked,
            wrong=not row["recipe_correct"],
        ),
        '<div class="tt-sec">인자 추출</div>',
    ]
    for f in field_rows(row):
        rows.append(
            _pair_markup(
                _key_markup(f["label"], f["name"]),
                _value_markup(f["answer"]) if f["used"] else _muted_markup(UNUSED_TEXT),
                (_value_markup(f["model"]) if f["in_model"] else _muted_markup(EMPTY_NUMBER))
                if f["used"] else _muted_markup(UNUSED_TEXT),
                wrong=f["correct"] is False,
                graded=f["used"],
            )
        )

    return f'{head}<div class="tt-cmp">{"".join(rows)}</div>{_extra_markup(row, functions)}'


def pending_markup(row: dict) -> str:
    """아직 안 돈 발화의 상세. 번호 · 발화 · 「대기」와 실행 전이라는 한 줄. 판정을 보이지 않음."""
    return (
        '<div class="tt-head">'
        f'<span class="tt-no">{row["case_id"]:03d}</span>'
        f'<span class="tt-utt">{_esc(row["utterance"])}</span>'
        f'<span class="tt-badge wait">● {PENDING_TEXT}</span>'
        "</div>"
        '<div class="tt-empty">아직 실행하지 않은 발화입니다.</div>'
    )


def _note_markup(text: str) -> str:
    """결과 위에 띄우는 알림 한 줄. 멈춘 까닭 · 실행 오류 문장."""
    return f'<div class="tt-note">{_esc(text)}</div>'


# ================================================================ 실행
def run_selected(dataset_id: str, on_progress=None, should_stop=None) -> dict:
    """고른 정답표를 dev/evaluation/run_evaluation 으로 새로 잰 결과. 새 run_id · 새 폴더.

    규칙  run_evaluation.run_dataset 에 RUN_OPTIONS 와 그 문맥 · GPU 조용 정책 · should_stop 을 넘김. 판정은 전부 평가 쪽이 함
          run_dataset 이 Test Run 을 outputs/local_benchmark 에 저절로 남김. 폴더는 시작하자마자 생김
          run_evaluation 을 여기서 import 함. 탭을 열기만 해서는 계기판 모듈을 안 읽음
    제약  판정 · 채점을 여기서 하지 않는다. st.* 를 부르지 않는다 (백그라운드 thread 에서 불림)
    """
    from dev.evaluation import run_evaluation
    from dev.evaluation.engine import monitor_gpu

    options = dict(RUN_OPTIONS)
    options["context"] = run_evaluation.context_payload(options["context_label"])
    return run_evaluation.run_dataset(
        dataset_id, progress=on_progress, monitor=monitor_gpu.GpuMonitor(gate=True), should_stop=should_stop, **options
    )


def resume_selected(kind: str, run_id: str, on_progress=None, should_stop=None) -> dict:
    """끝나지 않은 local 기록을 같은 run_id 로 이어 잰 결과. run_evaluation.resume 그대로.

    규칙  조건 · 문맥 · 부르는 순간은 기록에 저장된 것을 평가 쪽이 씀. 여기서 넘기지 않음
          GPU 조용 정책은 새로 실행과 같음. 실행 하드웨어는 저장된 것이 없을 때만 이 기계
    제약  st.* 를 부르지 않는다 (백그라운드 thread 에서 불림)
    """
    from dev.evaluation import run_evaluation
    from dev.evaluation.engine import monitor_gpu

    return run_evaluation.resume(
        kind, run_id, progress=on_progress, monitor=monitor_gpu.GpuMonitor(gate=True),
        environment=monitor_gpu.environment(), should_stop=should_stop,
    )


def resume_check(kind: str, run_id: str) -> dict:
    """그 기록을 이어 잴 수 있나. run_evaluation.resume_check 그대로 (파일을 안 고치고 Resolve 를 안 부름)."""
    from dev.evaluation import run_evaluation

    return run_evaluation.resume_check(kind, run_id)


NEW, RESUME = "new", "resume"
_TOKENS = itertools.count(1)


class _Job:
    """백그라운드에서 도는 평가 한 번. 화면 script 와 평가 thread 가 나눠 보는 것은 이것뿐.

    규칙  평가 thread 는 add 로 끝난 줄을 넣고, 끝나면 result 또는 error 를 적고 finished 를 켬
          화면은 rows() · stop_requested() · finished 만 읽고, 「중지」는 request_stop 으로 알림
          rows 는 이어 실행이면 전에 잰 줄부터 시작함
    제약  st.* · session_state 를 만지지 않는다. 줄을 채점하지 않는다
    """

    def __init__(self, mode: str, dataset_id: str, planned: int, rows: list[dict] | None = None,
                 kind: str | None = None, run_id: str | None = None):
        self.token = next(_TOKENS)
        self.mode, self.dataset_id, self.planned = mode, dataset_id, planned
        self.kind, self.run_id = kind, run_id
        self._rows = list(rows or [])
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.finished = threading.Event()
        self.result: dict | None = None
        self.error: str | None = None
        self.thread: threading.Thread | None = None

    def add(self, done: int, total: int, row: dict) -> None:
        with self._lock:
            self._rows.append(row)

    def rows(self) -> list[dict]:
        with self._lock:
            return list(self._rows)

    def request_stop(self) -> None:
        self._stop.set()

    def stop_requested(self) -> bool:
        return self._stop.is_set()

    def active(self) -> bool:
        return not self.finished.is_set()


# 이 process 에서 지금(또는 마지막으로) 도는 평가. 창이 여럿이어도 하나다.
_job: _Job | None = None
_JOB_LOCK = threading.Lock()


def current_job() -> _Job | None:
    """이 process 의 마지막 _Job. 없으면 None."""
    return _job


def _work(job: _Job, target) -> None:
    """평가 thread 의 몸. target() 의 결과나 예외 문장을 job 에 적고 finished 를 켬."""
    try:
        job.result = target()
    except Exception as exc:  # noqa: BLE001 — 화면이 까닭을 보인다. 끝난 줄은 cases.jsonl 에 남아 있다.
        job.error = f"{type(exc).__name__}: {exc}"
    finally:
        job.finished.set()


def start_job(job: _Job, target) -> bool:
    """job 을 백그라운드 thread 로 시작. 이미 도는 평가가 있으면 시작하지 않고 거짓.

    규칙  한 process 에 도는 _Job 은 하나. 확인과 시작을 _JOB_LOCK 안에서 함
    제약  Resolve 를 여기서 부르지 않는다. 기다리지 않는다
    """
    global _job
    with _JOB_LOCK:
        if _job is not None and _job.active():
            return False
        _job = job
        job.thread = threading.Thread(target=_work, args=(job, target), name=f"test-tab-job-{job.token}", daemon=True)
        job.thread.start()
    return True


def _start_new(dataset_id: str) -> None:
    """「새로 실행」의 콜백. 새 Test Run 을 백그라운드로 시작하고 이 창이 지켜봄.

    규칙  잴 수는 고른 정답표의 대기 줄 수. 폴더는 run_evaluation 이 시작하자마자 만듦
          이미 도는 평가가 있으면 아무것도 안 함
    """
    planned = len(suite_rows(dataset_id))
    job = _Job(NEW, dataset_id, planned)
    if start_job(job, lambda: run_selected(dataset_id, job.add, job.stop_requested)):
        _watch(job)


def _start_resume(stored: dict) -> None:
    """「이어 실행」의 콜백. 불러온 끝나지 않은 local 기록을 같은 run_id 로 이어 잼.

    규칙  누른 순간 resume_check 를 다시 봄. 막히면 까닭을 RUN_ERROR_KEY 에 두고 파일을 안 건드림
          잴 수 · 전에 잰 줄은 불러온 결과 그대로
    """
    from dev.evaluation.engine import manage_benchmark

    result = stored["result"]
    run_id = result["meta"]["run_id"]
    check = resume_check(stored.get("kind"), run_id)
    st.session_state[RESUME_KEY] = {"key": _resume_cache_key(stored), "check": check}
    if not check["resumable"]:
        st.session_state[RUN_ERROR_KEY] = check["reason"]
        return
    planned = manage_benchmark.planned_runs(result["meta"]) or len(result["cases"])
    job = _Job(RESUME, stored["dataset_id"], planned, result["cases"], kind=stored["kind"], run_id=run_id)
    if start_job(job, lambda: resume_selected(job.kind, job.run_id, job.add, job.stop_requested)):
        _watch(job)


def _watch(job: _Job) -> None:
    """이 창이 job 을 지켜보게 함. 끝나면 결과를 받아 옴 (_absorb)."""
    st.session_state[JOB_KEY] = job.token
    st.session_state[STARTED_KEY] = True
    st.session_state.pop(RUN_ERROR_KEY, None)


def _request_stop() -> None:
    """「중지」의 콜백. 도는 평가에 멈추라고 알림. 지금 부르는 발화는 끝까지 감."""
    job = current_job()
    if job is not None and job.active():
        job.request_stop()


def _absorb(job: _Job) -> None:
    """끝난 job 의 결과를 이 창의 결과 자리에 둠. 한 번만.

    규칙  결과는 방금 잰(또는 이어 잰) 기록 그대로 RESULT_KEY 에 둠. kind 는 local
          끝나지 않고 멈췄으면 그 기록이 그대로 불러온 것이 되어 이어 실행 판정이 바로 보임
          예외로 끝났으면 문장을 RUN_ERROR_KEY 에 두고 지난 결과는 안 지움
          새 결과가 들어오면 고른 발화 · 표 선택을 처음으로 돌리고, 다음 회차에 실행 기록 고르기를 비움
          (SAVED_RESET_KEY. 이미 그린 widget 의 값은 같은 회차에 못 고침)
    """
    st.session_state.pop(JOB_KEY, None)
    st.session_state.pop(RESUME_KEY, None)
    if job.error is not None or job.result is None:
        st.session_state[RUN_ERROR_KEY] = f"테스트를 실행하지 못했습니다 — {job.error}"
        return
    st.session_state[RESULT_KEY] = {"dataset_id": job.dataset_id, "result": job.result, "kind": "local"}
    for key in (SELECTED_KEY, LIST_VIEW_KEY):
        st.session_state.pop(key, None)
    st.session_state[SAVED_RESET_KEY] = True


def _resume_cache_key(stored: dict) -> tuple:
    result = stored.get("result") or {}
    return stored.get("kind"), (result.get("meta") or {}).get("run_id"), len(result.get("cases") or [])


def record_state(stored: dict | None) -> dict | None:
    """불러온(또는 방금 잰) 기록 한 벌의 상태. 결과가 없으면 None.

    출력  {"complete", "done", "planned", "kind", "run_id"}
    규칙  complete 는 멈춘 까닭(meta.stopped)이 없고 잴 것을 다 잰 것. done 은 끝난 줄 수
          planned 는 manage_benchmark.planned_runs, 모르면 done
    """
    from dev.evaluation.engine import manage_benchmark

    result = (stored or {}).get("result")
    if not result:
        return None
    meta = result["meta"]
    done = len(result["cases"])
    planned = manage_benchmark.planned_runs(meta) or done
    return {"complete": not meta.get("stopped") and done >= planned, "done": done, "planned": planned,
            "kind": stored.get("kind"), "run_id": meta.get("run_id")}


def _resume_verdict(stored: dict) -> dict:
    """불러온 끝나지 않은 기록의 이어 실행 판정. 같은 기록이면 지난 판정을 다시 씀.

    규칙  kind 가 없는 기록(옛 창 상태)은 local 로 보지 않음. 판정은 「이어 실행」을 누를 때 다시 봄
    """
    key = _resume_cache_key(stored)
    cached = st.session_state.get(RESUME_KEY) or {}
    if cached.get("key") == key:
        return cached["check"]
    check = resume_check(stored.get("kind"), key[1]) if stored.get("kind") else {
        "resumable": False, "reason": "저장 자리를 모르는 기록입니다.", "fields": [], "gaps": []}
    st.session_state[RESUME_KEY] = {"key": key, "check": check}
    return check


def _short(value) -> str:
    """조건 값 한 칸. sha256 같은 긴 hex 는 앞 12자, dict · 목록은 JSON 한 줄, 없으면 「기록 없음」."""
    if value is None:
        return "기록 없음"
    if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40,}", value):
        return value[:12]
    if isinstance(value, list):
        return " · ".join(_short(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def condition_rows(check: dict) -> list[dict]:
    """「변경된 조건 보기」 표. [{"실행 조건", "상태", "저장된 값", "지금 값"}].

    규칙  run_evaluation.resume_check 의 fields 차례. 상태는 동일 · 변경됨 · 기록 없음
          값은 _short. 맞대기는 평가 쪽이 값 전체로 했음
    제약  meta.json 을 통째로 보이지 않는다
    """
    rows = []
    for field in check.get("fields") or []:
        status = "동일" if field["same"] else "기록 없음" if field["stored"] is None else "변경됨"
        rows.append({"실행 조건": field["label"], "상태": status,
                     "저장된 값": _short(field["stored"]), "지금 값": _short(field["current"])})
    return rows


def control_state(job: _Job | None, stored: dict | None) -> dict:
    """실행 제어 칸의 상태. 글자 · 단추를 정하는 값 하나.

    출력  {"phase", "text", "resume": 판정 또는 None}
          phase 는 idle · complete · running · stopping · stopped
    규칙  도는 job 이 있으면 running(중지 전) · stopping(중지 요청됨). 글자에 끝난 수 / 잴 수
          없으면 불러온 기록으로: 다 쟀으면 complete, 못 다 쟀으면 stopped 와 이어 실행 판정
          불러온 기록이 없으면 idle
    """
    if job is not None and job.active():
        done = len(job.rows())
        if job.stop_requested():
            return {"phase": "stopping", "text": "중지 요청됨 · 현재 발화를 마친 뒤 중지합니다.", "resume": None}
        verb = "이어 실행 중" if job.mode == RESUME else "새로 실행 중"
        return {"phase": "running", "text": f"{verb} · {done} / {job.planned}", "resume": None}
    state = record_state(stored)
    if state is None:
        return {"phase": "idle", "text": "", "resume": None}
    if state["complete"]:
        return {"phase": "complete", "text": f"완료 · {state['done']} / {state['planned']}", "resume": None}
    return {"phase": "stopped", "text": f"중단됨 · {state['done']} / {state['planned']}", "resume": _resume_verdict(stored)}


def _render_controls(job: _Job | None, stored: dict | None, dataset_id: str) -> None:
    """실행 상태 한 줄과 단추. control_state 를 그대로 그림.

    규칙  idle · complete  「새로 실행」 하나
          running          「중지」 하나. stopping 이면 「중지 요청됨」 (눌리지 않음)
          stopped          「이어 실행」 · 「새로 실행」. 이어 잴 수 있으면 이어 실행이 앞 단추.
                           못 하면 이어 실행을 숨기지 않고 눌리지 않게 두고, 까닭과 「변경된 조건 보기」를 보임
    제약  단추 콜백 말고는 평가를 시작하지 않는다
    """
    state = control_state(job, stored)
    phase, check = state["phase"], state["resume"]
    text, buttons = st.columns([6.2, 1.9], vertical_alignment="center")
    with text:
        badge = ""
        if check is not None:
            ok = check["resumable"]
            badge = f'<span class="tt-resume {"ok" if ok else "no"}">{"이어 실행 가능" if ok else "이어 실행 불가"}</span>'
        st.markdown(
            f'<div class="tt-run tt-run-{phase}"><span class="tt-run-text">{_esc(state["text"])}</span>{badge}</div>',
            unsafe_allow_html=True,
        )
        if phase in ("running", "stopping") and job is not None and job.planned:
            st.progress(min(1.0, len(job.rows()) / job.planned))
    with buttons:
        if phase == "running":
            st.button("중지", key="test_stop", width="stretch", on_click=_request_stop)
        elif phase == "stopping":
            st.button("중지 요청됨", key="test_stop", width="stretch", disabled=True)
        elif phase == "stopped":
            left, right = st.columns(2)
            ok = bool(check and check["resumable"])
            left.button("이어 실행", key="test_resume", type="primary" if ok else "secondary", width="stretch",
                        disabled=not ok, on_click=_start_resume, args=(stored,))
            right.button("새로 실행", key="test_run", type="secondary" if ok else "primary", width="stretch",
                         on_click=_start_new, args=(dataset_id,))
        else:
            st.button("새로 실행", key="test_run", type="primary", width="stretch", on_click=_start_new, args=(dataset_id,))
    if check is not None and not check["resumable"]:
        st.markdown(f'<div class="tt-resume-why">{_esc(check["reason"])}</div>', unsafe_allow_html=True)
        rows = condition_rows(check)
        if rows:
            with st.expander("변경된 조건 보기", expanded=False):
                st.markdown(condition_markup(rows), unsafe_allow_html=True)


def condition_markup(rows: list[dict]) -> str:
    """「변경된 조건 보기」 표 마크업. 달라진 줄만 강조."""
    head = "".join(f"<th>{_esc(name)}</th>" for name in ("실행 조건", "상태", "저장된 값", "지금 값"))
    body = "".join(
        f'<tr class="{"" if row["상태"] == "동일" else "tt-changed"}">'
        + "".join(f"<td>{_esc(row[name])}</td>" for name in ("실행 조건", "상태", "저장된 값", "지금 값"))
        + "</tr>"
        for row in rows
    )
    return f'<table class="tt-conds"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


# ================================================================ 그리기
def saved_runs() -> list[dict]:
    """저장된 실행 기록 목록. official · local 을 합쳐 최근 것이 앞. manage_benchmark.list_benchmarks 그대로.

    규칙  못 읽으면 빈 목록
    제약  폴더를 여기서 뒤지지 않는다. 어느 자리를 읽는지는 manage_benchmark 만 안다
    """
    from dev.evaluation.engine import manage_benchmark

    try:
        return manage_benchmark.list_benchmarks()
    except OSError:
        return []


def storage_notes() -> list[str]:
    """실행 기록 보관 자리가 틀렸다는 문장들. manage_benchmark.storage_problems 그대로. 못 읽으면 빈 목록."""
    from dev.evaluation.engine import manage_benchmark

    try:
        return manage_benchmark.storage_problems()
    except OSError:
        return []


def _reset_view() -> None:
    """고른 발화 · 표 선택 · 기능 고르기를 처음으로. widget 콜백 안에서만 부름.

    규칙  기능 고르기는 값을 지우지 않고 ALL_GROUPS 로 적음. widget 값을 지우기만 하면 브라우저가 옛 값을
          들고 있다가 다음 회차에 도로 보냄
    """
    for key in (SELECTED_KEY, LIST_VIEW_KEY):
        st.session_state.pop(key, None)
    st.session_state[GROUP_KEY] = ALL_GROUPS


def _switch_suite() -> None:
    """테스트 세트 고르기의 콜백. 다른 세트의 결과가 남지 않게 지난 결과 · 고른 실행 기록을 지움.

    규칙  RESULT_KEY · 실행 · 불러오기 오류 문장을 지움. 표는 새 세트의 대기 줄만 남음
          실행 기록 고르기는 지우지 않고 빈 값(「불러올 기록 고르기」)으로 적음. 지우기만 하면 브라우저가
          옛 기록을 계속 보이고, 같은 기록을 다시 골라도 바뀐 것이 없어 _load_saved 가 안 불림
    제약  평가 · LLM 을 부르지 않는다
    """
    for key in (RESULT_KEY, RUN_ERROR_KEY, LOAD_ERROR_KEY, RESUME_KEY):
        st.session_state.pop(key, None)
    st.session_state[SAVED_KEY] = ""
    _reset_view()


def _load_saved() -> None:
    """실행 기록 고르기의 콜백. 고른 기록을 방금 잰 결과와 같은 자리에 둠.

    규칙  고른 값 "<kind>:<run_id>" 그대로 manage_benchmark.load_benchmark(kind, run_id) 를 부름.
          돌려준 결과 한 벌을 RESULT_KEY 에 둠. 테스트 세트 고르기를 그 기록의 정답표로 맞춤.
          표는 그 정답표의 대기 줄 위에 저장된 결과를 얹은 것이 됨. 고른 발화 · 표 선택을 처음으로 돌림
          못 읽으면(없음 · 깨짐 · 두 자리에 같은 id) 문장을 LOAD_ERROR_KEY 에 두고 지난 결과는 안 지움
    제약  평가 · LLM 을 부르지 않는다. 어느 자리의 기록인지를 짐작하지 않는다
    """
    from dev.evaluation.engine import manage_benchmark

    picked = st.session_state.get(SAVED_KEY)
    st.session_state.pop(LOAD_ERROR_KEY, None)
    if not picked:
        return
    kind, _, run_id = str(picked).partition(":")
    try:
        result = manage_benchmark.load_benchmark(kind, run_id)
    except (OSError, ValueError, KeyError) as exc:
        st.session_state[LOAD_ERROR_KEY] = f"실행 기록을 읽지 못했습니다 — {type(exc).__name__}: {exc}"
        return
    dataset_id = (result["meta"].get("suite") or {}).get("dataset_id")
    known = {entry["id"] for entry in evaluation_suite.datasets()}
    if dataset_id not in known:
        dataset_id = st.session_state.get(DATASET_KEY)
    else:
        st.session_state[DATASET_KEY] = dataset_id
    st.session_state[RESULT_KEY] = {"dataset_id": dataset_id, "result": result, "kind": kind}
    for key in (RUN_ERROR_KEY, RESUME_KEY):
        st.session_state.pop(key, None)
    _reset_view()


def _render_header(stored: dict, busy: bool = False) -> tuple[str, dict | None]:
    """제목 · 테스트 세트 · 실행 기록.

    입력  session_state 의 마지막 실행 {"dataset_id", "result", "kind"}. busy 는 평가가 도는 중인가
    출력  (고른 정답표 id, 고른 정답표의 마지막 결과 또는 None)
    규칙  테스트 세트를 바꾸면 _switch_suite 가 지난 결과 · 고른 실행 기록을 지움
          실행 기록 고르기는 widget 을 그리기 전에 비울 것을 비움 (방금 끝난 실행 · 목록에서 사라진 기록)
          실행 기록은 official · local 을 합친 목록(saved_runs). 값은 "<kind>:<run_id>".
          고르면 _load_saved 가 그 결과를 지금 결과 자리에 둠
          도는 동안(busy)은 두 고르기를 눌리지 않게 둠. 화면이 다른 실행을 다루는 것처럼 보이지 않게
    제약  여기서 평가를 부르지 않는다
    """
    entries = evaluation_suite.datasets()
    labels = {entry["id"]: dataset_label(entry) for entry in entries}
    saved = {saved_key(entry): saved_label(entry) for entry in saved_runs()}
    if st.session_state.pop(SAVED_RESET_KEY, False) or st.session_state.get(SAVED_KEY) not in ("", None, *saved):
        st.session_state[SAVED_KEY] = ""
    title, picker, history = st.columns([4, 2.6, 3.4], vertical_alignment="bottom")
    with picker:
        dataset_id = st.selectbox(
            "테스트 세트", list(labels), format_func=labels.get, key=DATASET_KEY, persist_state="page",
            on_change=_switch_suite, disabled=busy,
        )
    with history:
        st.selectbox(
            "실행 기록", [""] + list(saved), format_func=lambda key: saved.get(key, "불러올 기록 고르기"),
            key=SAVED_KEY, on_change=_load_saved, persist_state="page", disabled=busy,
        )
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
    return dataset_id, result


def _render_overview(result: dict | None) -> None:
    """실행 개요 한 판. 결과가 없으면 안 그림."""
    info = overview(result)
    if info is not None:
        st.markdown(overview_markup(info), unsafe_allow_html=True)


def _render_recipe_summary(result: dict | None) -> None:
    """기능별 결과 (접힘). 지원하는 기능만, 번호 차례. 실패가 있으면 펼침.

    제약  제목은 「기능별 결과」 하나다. 기능 수 · 실패한 기능 수를 제목에 달지 않는다 —
          같은 숫자가 바로 아래 표에 있고, 제목이 길어지면 무엇을 여는 칸인지가 흐려진다
    """
    entries = recipe_rows(result)
    if not entries:
        return
    failed = sum(1 for e in entries if e["failed"])
    with st.expander("기능별 결과", expanded=bool(failed)):
        st.markdown(
            recipe_summary_markup(entries, (result or {}).get("meta", {}).get("functions") or {}),
            unsafe_allow_html=True,
        )


def _render_conditions(result: dict | None) -> None:
    """모델 설정 (접힘). 모델 · 요청 설정 · 파일 · 실행 기록 id. 결과가 없으면 비어 있다고만."""
    with st.expander("모델 설정", expanded=False):
        conditions = run_conditions(result)
        if conditions is None:
            st.markdown('<div class="tt-empty">새로 실행하거나 기록을 불러오면 표시됩니다.</div>', unsafe_allow_html=True)
        else:
            st.markdown(conditions_markup({**conditions, **run_identity(result)}), unsafe_allow_html=True)


def _render_filters(summary: dict | None, rows: list[dict] | None = None) -> tuple[str, str, str, tuple[str, str]]:
    """보기 필터 · 기능 고르기 · 발화 검색 · 정렬.

    출력  (보기, 검색어, 기능 자리, (정렬 칸, 정렬 방향))
    규칙  결과가 있으면 필터 글자 옆에 그 보기의 건수를 붙임. 전체는 표의 줄 수
          보기는 칸 하나다 — 전체 · 실패 다음에 실패를 가른 셋이 딸려 붙음.
          딸린 것으로 보이게 하는 일은 CSS 가 하고(FIRST_FAILURE_FILTER), 고르는 뜻은 안 바뀜
          오류 줄이 있을 때만 맨 뒤에 오류 보기가 붙음. 실패에 딸리지 않음. 오류가 없어지면 전체로 돌림
          기능 고르기는 표에 있는 기대 기능과 범위 밖. 대기 줄도 제 기능 자리에 들어감
          결과가 없으면(대기 줄뿐) 건수를 안 붙임. 대기 줄을 성공 · 실패로 세지 않음
          정렬 칸 · 방향은 session_state(SORT_COLUMN_KEY · SORT_ORDER_KEY)에 남음. 기본은 번호 오름차순
    제약  보기 위해 채점 · 거르는 뜻을 바꾸지 않는다
    """
    rows = rows or []
    counts = {}
    errors = sum(1 for r in rows if errored(r))
    if summary is not None:
        counts = {
            ALL: len(rows),
            FAILED: summary["failed"],
            STAGE_LABELS["function"]: summary["function"],
            STAGE_LABELS["input"]: summary["input"],
            STAGE_LABELS["scope"]: sum(1 for r in rows if failed(r) and r.get("failure_stage") == "scope"),
            ERROR_FILTER: errors,
        }
    options = FILTERS + ((ERROR_FILTER,) if errors else ())
    if st.session_state.get(FILTER_KEY) not in (None, *options):
        st.session_state[FILTER_KEY] = ALL
    left, middle, right, order_by, order = st.columns([3.6, 1.5, 1.5, 1.25, 1.2], vertical_alignment="center")
    with left:
        view = st.segmented_control(
            "보기",
            options,
            default=ALL,
            required=True,
            format_func=lambda v: f"{v}  {counts[v]}" if v in counts else v,
            key=FILTER_KEY,
            label_visibility="collapsed",
            persist_state="page",
        )
    with middle:
        options = group_options(rows)
        group = st.selectbox(
            "기능", options, format_func=lambda g: group_label(g, rows), key=GROUP_KEY,
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
    with order_by:
        column = st.selectbox(
            "정렬", SORT_COLUMNS, format_func=lambda c: f"정렬 · {c}", key=SORT_COLUMN_KEY,
            label_visibility="collapsed", persist_state="page",
        )
    with order:
        direction = st.segmented_control(
            "정렬 방향", SORT_ORDERS, default=ASCENDING, required=True, format_func=SORT_ORDER_LABELS.get,
            key=SORT_ORDER_KEY, label_visibility="collapsed", persist_state="page",
        )
    return view or ALL, query or "", group or ALL_GROUPS, (column or SORT_COLUMNS[0], direction or ASCENDING)


def _result_tone(value: str) -> str:
    """결과 칸 글자색. 성공 초록 · 실패 빨강 · 오류 황색 · 대기 색 없음."""
    if value == SUCCESS_TEXT:
        return "color: #2EB67D; font-weight: 600;"
    if value.startswith("실패"):
        return "color: #E5534B; font-weight: 600;"
    if value == ERROR_TEXT:
        return "color: #D29922; font-weight: 600;"
    return ""


def _keep_row_selected(key: str, ids: list[int]) -> None:
    """표에서 누른 것을 한 줄 선택으로 맞춤. 표의 on_select 콜백.

    입력  key 는 표의 key, ids 는 표 줄 순서대로의 결과 번호
    규칙  칸을 눌렀으면 그 칸의 줄을 고름
          고른 줄을 다시 눌러 선택이 비었으면 지금 상세의 줄을 다시 고름. 상세가 늘
          표의 강조 줄과 같게 둠
          머리글을 눌러 칸이 골라지면(single-column) 그 칸을 버리고 지금 상세의 줄을 다시 고름.
          칸 고르기는 머리글 정렬을 끄려고만 켠 것임
    """
    selection = (st.session_state.get(key) or {}).get("selection") or {}
    cells = selection.get("cells") or []
    if cells:
        row = cells[0][0]
    elif selection.get("rows"):
        if not selection.get("columns"):
            return
        row = selection["rows"][0]
    elif st.session_state.get(SELECTED_KEY) in ids:
        row = ids.index(st.session_state[SELECTED_KEY])
    else:
        row = 0
    st.session_state[key] = {"selection": {"rows": [row], "columns": [], "cells": []}}


def _list_key(view: str, query: str, group: str = ALL_GROUPS, sort: tuple = (SORT_COLUMNS[0], ASCENDING)) -> str:
    """결과 표의 key. 보기 · 검색어 · 기능 · 정렬이 바뀔 때만 새로 붙음.

    규칙  같은 보기 안에서는 key 가 그대로라 표가 안 새로 붙고 스크롤 자리가 남음
          보기 · 검색어 · 정렬이 바뀌면 key 가 바뀌어 표가 새로 붙고 selection_default 가 다시 먹음.
          줄 자리가 바뀌므로 옛 자리의 선택을 들고 가면 다른 발화가 골라짐.
          전에 봤던 보기로 돌아와도 그때의 선택이 아니라 지금 고른 발화를 따름
          새 결과가 들어오면 _absorb 가 LIST_VIEW_KEY 를 지워 표가 새로 붙음
    """
    round_ = st.session_state.get(LIST_ROUND_KEY, 0)
    if st.session_state.get(LIST_VIEW_KEY) != (view, query, group, sort):
        round_ += 1
        st.session_state[LIST_VIEW_KEY] = (view, query, group, sort)
        st.session_state[LIST_ROUND_KEY] = round_
    return f"test_list_{round_}"


def _styled_frame(rows: list[dict]):
    """결과 목록 표에 결과 글자색을 입힌 것."""
    return list_frame(rows).style.map(_result_tone, subset=["결과"])


def _list_columns() -> dict:
    """결과 목록 표의 칸 폭.

    제약  칸 머리의 설정 메뉴에서 정렬 · 통계 · 자동 너비 · 칸 고정을 여기서 못 끈다.
          Streamlit 1.62 의 column_config 에 그 칸이 없다 — panel_css 가 감춘다
    """
    return {
        "번호": st.column_config.TextColumn("번호", width=56),
        "기능": st.column_config.TextColumn("기능", width=76),
        "발화": st.column_config.TextColumn("발화", width="large"),
        "결과": st.column_config.TextColumn("결과", width=128),
        "추론 지연시간": st.column_config.TextColumn("추론 지연시간", width=96),
    }


def _render_result_list(shown: list[dict], view: str, query: str, height: int, *, group: str = ALL_GROUPS,
                        sort: tuple = (SORT_COLUMNS[0], ASCENDING)) -> dict | None:
    """결과 목록. 한 발화 한 줄, 고정 높이 안에서 스크롤.

    입력  shown 은 거른 줄. 여기서 sort_rows 로 세워 그림
    출력  지금 고른 결과 줄. 목록이 비었으면 None
    규칙  행 고르기는 st.dataframe 의 행 선택. 발화 글자를 눌러도 골라지게 칸 선택을
          함께 켜고, 칸을 누르면 _keep_row_selected 가 그 줄 선택으로 바꿈
          칸 고르기(single-column)도 켬. 켜면 st.dataframe 의 머리글 정렬이 꺼짐 (Streamlit 1.62).
          정렬은 파이썬 한 곳(sort_rows)만 함
          표 key 는 _list_key 가 정함. 같은 보기 안에서 행을 눌러도 표가 새로 안 붙으므로
          스크롤 자리가 그대로임
          보기를 바꾸면 고른 발화가 새 목록에 있으면 그 줄, 없으면 첫 실패 줄, 실패가 없으면 첫 줄을 고름
          표는 늘 고른 정답표의 발화 전부(대기 줄 포함)에서 거른 것. 비는 것은 거른 결과가 없을 때뿐
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

    shown = sort_rows(shown, *sort)
    remembered = st.session_state.get(SELECTED_KEY)
    default = next((i for i, r in enumerate(shown) if r["case_id"] == remembered), None)
    if default is None:
        default = first_failure(shown) or 0

    key = _list_key(view, query, group, sort)
    event = st.dataframe(
        _styled_frame(shown),
        key=key,
        on_select=partial(_keep_row_selected, key, [r["case_id"] for r in shown]),
        selection_mode=["single-row", "single-cell", "single-column"],
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


def _render_status(stored: dict | None) -> None:
    """실행 상태 아래의 알림 한 줄. 실행 · 불러오기 오류, 사람이 누르지 않았는데 멈춘 까닭, 보관 자리 문제 중 앞의 것."""
    from dev.evaluation import run_evaluation

    stopped = ((stored or {}).get("result") or {}).get("meta", {}).get("stopped")
    notes = storage_notes()
    if st.session_state.get(RUN_ERROR_KEY):
        text = st.session_state[RUN_ERROR_KEY]
    elif st.session_state.get(LOAD_ERROR_KEY):
        text = st.session_state[LOAD_ERROR_KEY]
    elif stopped and stopped != run_evaluation.USER_STOP:
        text = f"테스트가 중간에 멈췄습니다 — {stopped}"
    elif notes:
        text = " · ".join(notes)
    else:
        return
    st.markdown(_note_markup(text), unsafe_allow_html=True)


def _render_body(ratios: dict, dataset_id: str, result: dict | None) -> None:
    """실행 제어 · 알림 · 전체 결과 · 기능별 결과 · 필터 · 결과 목록 · 상세. 도는 동안 fragment 로 스스로 다시 그려짐.

    입력  result 는 고른 정답표의 마지막 결과(불러온 기록 포함). 도는 동안에는 안 봄
    규칙  도는 job 이 있으면 표 · 요약은 job.rows() (끝난 줄만. 이어 실행이면 전에 잰 줄 포함) 를 대기 줄 위에 얹은 것
          job 이 끝난 것을 보면 화면 전체를 다시 그려 결과를 받아 옴(_absorb)
          이 fragment 안에서 실행을 시작했으면 화면 전체를 다시 그림 (머리의 고르기를 잠그려고)
    제약  여기서 평가를 기다리지 않는다. 한 번 그리고 끝남
    """
    job = current_job()
    watched = job is not None and st.session_state.get(JOB_KEY) == job.token
    if st.session_state.pop(STARTED_KEY, False) or (watched and not job.active()):
        st.rerun()
    busy = job is not None and job.active()
    stored = st.session_state.get(RESULT_KEY) or {}
    record = stored if stored.get("dataset_id") == dataset_id and result is not None else None

    _render_controls(job if busy else None, record, dataset_id)
    _render_status(None if busy else record)

    if busy:
        dataset_id = job.dataset_id
        done_rows = job.rows()
        summary = summarize(live_result(done_rows, job.planned))
        functions = _functions()
    else:
        done_rows = result["cases"] if result else []
        summary = summarize(result)
        functions = (result or {}).get("meta", {}).get("functions") or {}
    st.markdown(summary_markup(summary), unsafe_allow_html=True)
    if not busy:
        _render_recipe_summary(result)
    rows = table_rows(suite_rows(dataset_id), done_rows)
    view, query, group, sort = _render_filters(summary, rows)

    height = list_height(ratios)
    left, right = st.columns([63, 37], gap="medium")
    shown = filter_results(rows, view, query, group)
    with left:
        selected = _render_result_list(shown, view, query, height, group=group, sort=sort)
    with right:
        _render_result_detail(selected, functions, height)


@st.cache_data(show_spinner=False, ttl=60)
def _functions() -> dict:
    """도는 동안 상세에 붙일 기능 설명. 게시 menu 의 function 문장 (monitor_metadata.functions)."""
    from dev.evaluation.engine import monitor_metadata

    return monitor_metadata.functions()


def render_test_tab(ratios: dict) -> None:
    """테스트 탭 전체.

    입력  config.layout_ratios() 결과. 창 높이로 목록 높이를 정함
    규칙  표는 고른 정답표의 대기 줄(suite_rows) 위에 결과를 case_id 로 얹은 것(table_rows). 고르기만 해도 발화 전부가 보임
          결과는 session_state 의 마지막 실행 하나(방금 잰 것 또는 불러온 실행 기록). 고른 정답표의 것일 때만 얹음
          이 창이 지켜보던 job 이 끝났으면 맨 먼저 그 결과를 받아 옴(_absorb)
          다른 창이 시작한 job 이 돌고 있어도 그것을 지켜봄. 두 번째 실행을 못 하게 단추가 「중지」로 보임
          실행 개요 · 기능별 결과는 결과가 있고 도는 중이 아닐 때만
          몸통(_render_body)은 도는 동안 POLL_SECONDS 마다 스스로 다시 그려짐
    제약  「새로 실행」 · 「이어 실행」을 누르지 않은 회차에는 평가 · LLM 을 부르지 않는다.
          필터 · 검색 · 정렬 · 행 선택 · 탭 전환이 다시 재게 하면 한 번에 수십 분이 듦
    """
    with st.container(key="test_tab"):
        st.markdown(panel_css(), unsafe_allow_html=True)
        st.session_state.pop(STARTED_KEY, None)
        job = current_job()
        if job is not None and not job.active() and st.session_state.get(JOB_KEY) == job.token:
            _absorb(job)
        busy = job is not None and job.active()
        if busy:
            st.session_state[JOB_KEY] = job.token

        dataset_id, result = _render_header(st.session_state.get(RESULT_KEY) or {}, busy)
        shown = None if busy else result
        _render_overview(shown)
        _render_conditions(shown)
        st.fragment(_render_body, run_every=POLL_SECONDS if busy else None)(ratios, dataset_id, shown)


# ================================================================ CSS
def panel_css() -> str:
    """테스트 탭 전용 CSS. .st-key-test_tab 안에만 걸림.

    규칙  글자색은 테마를 따름(inherit). 선 · 바탕은 회색 반투명이라 밝은 테마 · 어두운
          테마 어느 쪽에서도 읽힘. 성공 · 실패 · AI 모델 출력 강조색만 고정
          보기 필터의 칸 번호는 FIRST_FAILURE_FILTER 에서 옴. CSS 에 숫자를 박지 않음
          칸 설정 메뉴 규칙만 .st-key-test_tab 밖에 있음 — 그 메뉴가 portal 로 탭 밖에 그려짐
    """
    return """<style>
.st-key-test_tab {
  --tt-ok: #2EB67D;
  --tt-ng: #E5534B;
  --tt-ai: #14B8A6;
  --tt-err: #D29922;
  --tt-line: rgba(140, 150, 165, 0.24);
  --tt-soft: rgba(140, 150, 165, 0.08);
  --tt-softer: rgba(140, 150, 165, 0.045);
  gap: 0.7rem;
}
.st-key-test_tab .tt-title { font-size: 1.35rem; font-weight: 700; line-height: 1.3; }
.st-key-test_tab .tt-sub { font-size: 0.82rem; opacity: 0.6; margin: 0.1rem 0 0.6rem; }

/* ---------------------------------------------- 실행 개요 */
.st-key-test_tab .tt-ovs {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: 0.6rem 1.2rem; font-size: 0.82rem; padding: 0.65rem 0.85rem;
  border: 1px solid var(--tt-line); border-radius: 10px; background: var(--tt-softer);
}
.st-key-test_tab .tt-ov-k { opacity: 0.6; font-size: 0.74rem; margin-bottom: 0.2rem; }
.st-key-test_tab .tt-ov-row { display: flex; justify-content: space-between; gap: 0.8rem; line-height: 1.55; }
.st-key-test_tab .tt-ov-sub { opacity: 0.65; }
.st-key-test_tab .tt-ov-v { font-weight: 600; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; text-align: right; }
.st-key-test_tab .tt-ov-row:only-child .tt-ov-v { text-align: left; }
.st-key-test_tab .tt-sum-title { font-size: 0.85rem; font-weight: 600; opacity: 0.85; margin: 0.2rem 0 0.45rem; }

/* ---------------------------------------------- 기능별 결과
   기능마다 카드 하나. 카드 사이 gap 으로 경계를 긋는다 (줄이 이어 붙으면 어디까지가 한
   기능인지가 흐려진다). 기능이 마흔 가까이 되므로 성공은 옆줄만 초록으로 차분히 두고,
   배경을 칠하는 것은 실패뿐이다 — 전부 초록이면 붉은 것이 안 보인다. */
.st-key-test_tab .tt-rss { display: grid; grid-template-columns: repeat(auto-fill, minmax(10.5rem, 1fr)); gap: 0.55rem; }
.st-key-test_tab .tt-rs {
  display: flex; align-items: baseline; justify-content: space-between; gap: 0.6rem;
  font-size: 0.8rem; padding: 0.42rem 0.7rem; border-radius: 8px;
  border: 1px solid var(--tt-line); background: var(--tt-softer);
}
.st-key-test_tab .tt-rs-n { font-variant-numeric: tabular-nums; font-weight: 600; }
.st-key-test_tab .tt-rs-ok { box-shadow: inset 3px 0 0 var(--tt-ok); }
.st-key-test_tab .tt-rs-ok .tt-rs-n { color: var(--tt-ok); }
.st-key-test_tab .tt-rs-ng {
  background: rgba(229, 83, 75, 0.1); border-color: rgba(229, 83, 75, 0.45);
  box-shadow: inset 3px 0 0 var(--tt-ng);
}
.st-key-test_tab .tt-rs-ng .tt-rs-n { color: var(--tt-ng); font-weight: 700; }

/* ---------------------------------------------- 모델 설정 */
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
.st-key-test_tab .tt-kpi.err { box-shadow: inset 3px 0 0 var(--tt-err); }
.st-key-test_tab .tt-kpi.err .tt-kpi-num { color: var(--tt-err); }

/* 실패 카드 안의 원인 셋. 전체 · 성공 · 실패와 같은 층으로 보이면 안 되므로
   카드 **안에** 들여쓰고 선으로 매단다. 같은 설명을 셋에 되풀이하지 않고 묶음에 한 번만 적는다. */
.st-key-test_tab .tt-kpi.ng { flex-grow: 1.9; }
.st-key-test_tab .tt-causes {
  grid-column: 1 / -1; margin: 0.5rem 0 0 0.2rem; padding: 0.35rem 0 0.05rem 0.7rem;
  border-left: 2px solid rgba(229, 83, 75, 0.35); border-top: 1px solid var(--tt-line);
}
.st-key-test_tab .tt-causes-head { font-size: 0.7rem; opacity: 0.5; margin-bottom: 0.2rem; }
.st-key-test_tab .tt-cause {
  display: flex; align-items: baseline; gap: 0.4rem; font-size: 0.78rem; line-height: 1.7;
}
.st-key-test_tab .tt-cause-k { opacity: 0.7; }
.st-key-test_tab .tt-cause-k::before {
  content: ""; display: inline-block; width: 0.3rem; height: 0.3rem; border-radius: 50%;
  background: var(--tt-ng); opacity: 0.7; margin-right: 0.35rem; vertical-align: 0.1rem;
}
.st-key-test_tab .tt-cause-v { font-weight: 700; font-variant-numeric: tabular-nums; }
.st-key-test_tab .tt-cause-note { font-size: 0.72rem; opacity: 0.5; }
.st-key-test_tab .tt-kpis-empty .tt-cause-v { opacity: 0.35; }

/* 보기 필터. 실패를 가른 셋(FIRST_FAILURE_FILTER 번째부터)은 실패에 딸린 것으로 보이게
   앞에 선을 긋고 글자를 눌러 둔다. 고르는 뜻은 그대로다. */
.st-key-test_tab .st-key-test_filter [data-testid="stButtonGroup"] button:nth-of-type({first_failure_filter}) {
  margin-left: 0.7rem; border-left: 1px solid var(--tt-line); padding-left: 0.85rem; border-radius: 0;
}
.st-key-test_tab .st-key-test_filter [data-testid="stButtonGroup"] button:nth-of-type(n+{first_failure_filter}) {
  font-size: 0.82rem;
}
/* 오류 보기(있을 때만 맨 뒤)는 실패에 딸리지 않는다. 선으로 떼어 둔다. */
.st-key-test_tab .st-key-test_filter [data-testid="stButtonGroup"] button:nth-of-type({error_filter}) {
  margin-left: 0.7rem; border-left: 1px solid var(--tt-line); padding-left: 0.85rem; border-radius: 0; font-size: 0.82rem;
}

/* 결과 표 칸 머리의 「설정」 메뉴. 정렬 · 통계 · 자동 너비 · 칸 고정 명령을 감춘다.
   머리글을 눌러 정렬하는 것은 칸 고르기(single-column)를 켜서 꺼 두었다 — 정렬은 파이썬(sort_rows)만 한다.
   칸 폭 조정은 그대로다.
   Streamlit 1.62 의 st.dataframe 에는 이 메뉴를 고르는 파이썬 설정이 없어 CSS 로만 가려진다
   (column_config 에 sortable · statistics · pinnable 같은 칸이 없다).
   메뉴는 portal 로 .st-key-test_tab 밖에 그려지므로 이 규칙만 탭 밖에 있다.
   이 화면이 st.dataframe 을 쓰는 유일한 자리라 다른 화면에 새지 않는다.
   마지막 줄(칸 숨기기)만 남긴다. */
[data-testid="stDataFrameColumnMenu"] [role="menuitem"],
[data-testid="stDataFrameColumnMenu"] [role="presentation"],
[data-testid="stDataFrameColumnMenu"] [role="menu"] > div:not([role]):not(:first-child) { display: none; }
[data-testid="stDataFrameColumnMenu"] [role="menu"] > [role="menuitem"]:last-child { display: flex; }

/* 표 세로 스크롤바. 기본 얇은 막대는 마우스로 잡기 어렵다. */
.st-key-test_tab [data-testid="stDataFrame"] .dvn-scroller { scrollbar-width: auto; }
.st-key-test_tab [data-testid="stDataFrame"] .dvn-scroller::-webkit-scrollbar { width: 12px; }

/* ---------------------------------------------- 실행 상태 · 이어 실행 */
.st-key-test_tab .tt-run { display: flex; align-items: center; gap: 0.7rem; font-size: 0.9rem; min-height: 2.4rem; }
.st-key-test_tab .tt-run-text { font-weight: 600; font-variant-numeric: tabular-nums; }
.st-key-test_tab .tt-run-stopping .tt-run-text { opacity: 0.75; }
.st-key-test_tab .tt-resume { font-size: 0.76rem; font-weight: 600; padding: 0.1rem 0.55rem; border-radius: 999px; }
.st-key-test_tab .tt-resume.ok { color: var(--tt-ok); background: rgba(46, 182, 125, 0.12); }
.st-key-test_tab .tt-resume.no { color: var(--tt-ng); background: rgba(229, 83, 75, 0.10); }
.st-key-test_tab .tt-resume-why { font-size: 0.82rem; opacity: 0.8; }
.st-key-test_tab .tt-conds { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.st-key-test_tab .tt-conds th, .st-key-test_tab .tt-conds td {
  text-align: left; padding: 0.3rem 0.5rem; border-bottom: 1px solid var(--tt-line); overflow-wrap: anywhere;
}
.st-key-test_tab .tt-conds th { opacity: 0.6; font-weight: 600; }
.st-key-test_tab .tt-conds td:nth-child(n+3) { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.74rem; }
.st-key-test_tab .tt-conds tr.tt-changed td { color: var(--tt-ng); font-weight: 600; }

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
.st-key-test_tab .tt-badge.err { color: var(--tt-err); background: rgba(210, 153, 34, 0.14); }
.st-key-test_tab .tt-badge.wait { opacity: 0.7; background: rgba(128, 128, 128, 0.12); }

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
.st-key-test_tab .tt-fnum[title] { cursor: help; }
</style>""".replace("{first_failure_filter}", str(FIRST_FAILURE_FILTER)).replace("{error_filter}", str(len(FILTERS) + 1))
