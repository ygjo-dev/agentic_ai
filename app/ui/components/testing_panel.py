"""테스트 탭. 정답표로 발화 해석을 재고, 발화별 기능 선택 · 인자 추출 결과를 훑고 한 건씩 들여다본다.

평가는 dev/evaluation 이 한다. 이 탭은 정답표를 고르고, 「새로 실행」 · 「이어 실행」을 누르면
dev/evaluation/run_evaluation 을 백그라운드 thread 에서 부르고, 끝난 줄을 받아 그린다.

    제목(발화 해석 평가) · Test Suite · 실행 기록
    실행 개요 (내용 폭만. Test Suite · 평가 시작 시간 · 소요 시간(전체 평가시간 · 전체 추론시간 · GPU 누적 대기시간 ·
               기타 진행 시간, 줄마다 ? 도움말) · 발화당 추론 시간 · 평가 결과 · 모델 · 실행 환경)
    모델 설정 (자세히 보기) (접힘. provider · Temperature 같은 요청 설정 · 호출 상한 · 파일 · 저장 위치)
    실행 상태 · GPU 팬 소음 억제 · 새로 실행 · 이어 실행 · 중지
    전체 결과 (낮은 카드 한 줄. 전체 · 성공 · 실패, 오류가 있을 때만 오류. 실패 원인 셋은 실패 카드 오른쪽에)
    기능별 결과 (접힘. 기능마다 카드 단추 하나 — 번호와 x/y 둘만. 범위 밖 발화가 있으면 맨 뒤에 범위 밖. 누르면 표를 거름)
    보기 필터 (전체 | 실패 묶음: 실패 · 기능 선택 · 인자 추출 · 범위 밖 처리)
    테스트 결과 N건 · 발화 검색 | 선택한 발화 상세
    결과 목록 (한 발화 한 줄, 고정 높이. 머리글을 눌러 정렬) | 선택한 발화 상세 (고정 높이)

**실행은 백그라운드 thread 하나가 한다(_Job).** 화면 script 는 그 상태를 읽기만 하고, 도는 동안
아래 몸통(_render_body)이 st.fragment(run_every=POLL_SECONDS)로 스스로 다시 그려진다. 그래서 도는 중에도
「중지」가 눌린다. thread 는 st.* · session_state 를 부르지 않는다 — 줄은 _Job 이 lock 으로 받아 둔다.
한 process 에 도는 평가는 하나뿐이다. 다른 창이 열려도 같은 _Job 을 보고 두 번째 실행을 못 한다.

    새로 실행   새 run_id · 새 폴더(outputs/local_benchmark/<run_id>/). 첫 발화부터. 누른 순간 폴더가 생김
    이어 실행   불러온 끝나지 않은 local 기록 그대로. 같은 run_id · 같은 폴더에서 남은 발화만
                조건(run_evaluation.resume_check)이 다르면 단추는 보이되 눌리지 않고, 다른 조건을 펼쳐 보인다
    중지        지금 부르고 있는 발화 하나는 끝까지 기다려 남기고, 다음 발화는 안 부른다.
                기록은 run.json 없이 meta.json + cases.jsonl 로 남아 「중단됨」이 된다
    그 밖의 조작(Test Suite · 기록 고르기 · 기능 카드 · 필터 · 정렬 · 행 고르기)은 폴더를 만들지 않는다

「GPU 팬 소음 억제」는 실행 박자일 뿐이라 누르는 순간의 화면 값을 쓴다. 새로 실행이면 meta.fan_quiet_mode,
이어 실행이면 그 구간의 값이 meta.resumed_fan_quiet_mode 에 남는다. 이어 실행 조건이 아니다.
도는 동안에는 눌리지 않고 그 실행의 값을 보인다.

**Test Suite 는 고르는 것이다.** 고른 정답표가 발화 목록 · 발화 수 · 실행 · 저장한 실행 기록의
신원을 함께 정한다. 발화 수는 고른 파일에서 세고 화면에 숫자를 박지 않는다.

낱말은 dev/evaluation/engine/manage_benchmark 머리 주석과 같다 — 정답표 한 벌은 화면에서도 「Test Suite」,
한 번 잰 것(Test Run)은 「실행 기록」, 발화 하나의 결과(Case Result)는 「발화 결과」다.

**이 화면이 보는 것은 둘이다 — 기능을 옳게 골랐나, 그 기능이 읽는 인자를 옳게 뽑았나.**
workflow 를 부를 수 있었나(materialize 판정)는 결과에 남아 있지만 여기서 보이지 않는다.
실행 하드웨어는 재현을 위해 GPU 이름 · VRAM 만 보인다. 온도는 보이지 않는다.

**결과 표는 고른 Test Suite 의 발화 목록 한 벌이다.** Test Suite 를 고르면 그 정답표 YAML 의 발화가
전부 「대기」 줄로 바로 선다(suite_rows). LLM 은 안 부른다. 실행은 줄을 덧붙이지 않고, 발화 하나가
끝날 때마다 같은 case_id 의 줄을 결과로 갈아 끼운다(table_rows). 실행 중에도 줄 수가 그대로다.

**결과 칸 하나가 발화의 끝을 말한다.** 성공 · 실패 · 기능 선택 · 실패 · 인자 추출 · 실패 · 범위 밖 처리 · 오류 · 대기.
실패 셋은 모델이 잘못한 것이고, 오류(failure_stage=error)는 예외로 Resolve 결과를 못 받은 것이라 실패에 안 센다.
KRRI · MCP 실행 오류가 아니다. 대기는 아직 안 돈 것이다.

**추론 시간은 소수 둘째 자리로 보인다(_seconds).** 실행 개요의 Median · P95 · Max 와 표 · 상세의 발화별 값이
같은 자릿수다. 글자만 반올림하고 결과의 값은 그대로다.

**정렬은 결과 표의 머리글을 눌러 하고, 줄을 세우는 것은 파이썬이다(sort_rows).** st.dataframe 자체의 머리글
정렬은 브라우저에만 있어 행을 누르는 rerun 에 처음 차례로 돌아갔다. 그래서 그것은 끄고(칸 고르기
single-column 을 켜면 꺼진다), 머리글을 눌러 칸이 골라지는 이벤트를 _keep_row_selected 가 받아 정렬 상태
(SORT_KEY)를 기본 -> 오름차순 -> 내림차순 -> 기본 으로 돌린다(next_sort). 고른 칸은 버린다.
정렬은 보기 필터 · 기능 카드 · 검색으로 거른 줄에 걸린다. 따로 정렬 고르기 widget 은 두지 않는다.

**새로 잰 결과와 불러온 실행 기록이 같은 길로 그려진다.** 실행 기록을 고르면 manage_benchmark.load_benchmark 가
돌려준 결과 한 벌을 방금 잰 결과와 같은 자리(RESULT_KEY)에 두고, Test Suite 고르기를 그 기록의 정답표로
맞춘다. 표는 그 정답표의 대기 줄 위에 저장된 결과를 case_id 로 얹은 것이다. 그리는 함수가 따로 없다.
실행 기록 목록은 manage_benchmark.list_benchmarks 하나가 official · local 을 합쳐 준다. 이 탭은 폴더를 안 뒤진다.
Test Suite 를 바꾸면 지난 결과 · 고른 실행 기록 · 고른 기능 카드를 지우고 새 세트의 대기 줄만 남긴다.

**표를 거르는 것은 셋이고 서로 따로 걸린다.** 보기 필터(실패 · 실패 단계) · 기능별 결과 카드(기능 하나 또는 범위 밖) ·
발화 검색. 셋이 겹친 줄만 남는다. 카드는 하나만 고르고, 고른 카드를 다시 누르면 푼다. 고른 기능은 widget 값이 아니라
session_state 값(GROUP_KEY)이다. 기능 고르기 목록(selectbox)은 두지 않는다 — 같은 거르기를 두 곳에서 하지 않는다.

**여기서 채점하지 않는다.** 성공 · 실패 · 실패 단계(passed · failure_stage) · 기능이 맞았나
(recipe_correct) · 정답표에 적은 값마다 맞았나(spoken_fields) 는 run_evaluation 결과에 이미 있다.
이 탭은 그 칸을 읽어 글자와 색으로 바꾼다. 값끼리 맞대지 않는다.

**LLM 은 「새로 실행」 · 「이어 실행」을 누를 때만 부른다.** 결과는 session_state 에 두고 기능 카드 · 필터 · 검색 ·
정렬 · 행 선택 · 탭 전환은 그것만 다시 그린다.

**상세는 성공과 실패가 같은 틀이다.** 정답표와 AI 모델 출력을 좌우로 맞대고,
실패면 틀린 칸만 강조한다. 「실패」 표시는 그 발화의 실패 단계(failure_stage)를 만든 칸에만 붙는다. 인자는 정답표에 적은 것과 모델이 낸 것을 빠짐없이 보인다.
기대 기능이 읽지 않는 인자는 두 칸 다 「사용 안 함」으로 흐리게 둔다 — 읽는데 값이 null 인 「없음」과 다르다.

화면 낱말은 사람이 읽는 말로 쓴다. 기능 번호는 「기능 015」로 보이고, 인자는
표시명이 있으면 표시명 아래에 변수명을 작게 단다. 표시명이 없는 인자도 변수명
그대로 나온다 — 새 인자가 들어와도 여기를 안 고친다.

**기능 번호가 보이는 자리에는 그 기능이 무엇을 하는지가 마우스에 붙는다.** 번호를 그리는
자리는 `number_markup` 하나를 지난다 (기대 기능 · AI 가 고른 기능 · 되묻기 후보 기능 · 후보 기능 ·
모델 판단 문장 안의 번호). 기능별 결과 카드는 단추라 HTML 을 못 받아 같은 tooltip 을 카드 key 의 CSS 로
그린다(recipe_card_css). 설명의 원천은 run_evaluation 결과 meta.functions 하나고,
화면에 {번호: 설명} 표를 따로 두지 않는다. 설명은 브라우저 title 이 아니라 CSS 가
그리는 tooltip 이다 (panel_css 의 TIP_DELAY_MS) — title 은 뜨기까지의 지연을 바꿀 수 없다.

    ★ 한 자리는 못 붙인다. 결과 목록 표의 「기능」 칸이다.
      st.dataframe 은 칸 값마다의 tooltip 을 받는 파이썬 API 가 없다(Streamlit 1.62 의
      column_config 는 칸 머리의 help 만 받는다). 줄을 고르면 상세 칸에 그 기능의 설명이 그대로 나온다.

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
import time
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
# 실패 단계 -> 결과 칸 글자이자 보기 필터 글자. 「실패 · 기능 선택」 꼴
FAILURE_TEXT = {stage: f"{FAILED} · {STAGE_LABELS[stage]}" for stage in QUALITY_STAGES}
# 실패를 가른 것들. 보기 필터에서 실패와 한 묶음 테두리 안에 딸린 자리로 보인다 (panel_css).
FAILURE_FILTERS = tuple(FAILURE_TEXT[stage] for stage in QUALITY_STAGES)
FILTERS = (ALL, FAILED, *FAILURE_FILTERS)
# 딸린 자리가 시작하는 칸 번호(1부터). CSS 에 숫자를 박지 않으려고 여기서 센다.
FIRST_FAILURE_FILTER = len(FILTERS) - len(FAILURE_FILTERS) + 1
# 묶음의 머리(실패)가 선 칸 번호. 딸린 셋 바로 앞이다
PARENT_FILTER = FILTERS.index(FAILED) + 1
# 필터 칸 폭(px)이 이 아래면 묶음 칸이 두 줄이 된다. 한 줄 묶음이 들어가는 폭(1920 창에서 잰 578px)에 여유를 둔 값
NARROW_FILTER_PX = 620
# 오류가 있는 결과에서만 FILTERS 뒤에 붙는 보기. 실패에 딸리지 않는다
ERROR_FILTER = ERROR_TEXT

# 결과 칸 글자의 차례. 결과로 정렬할 때 이 차례다. 대기는 값이 없는 줄이라 늘 뒤에 간다
RESULT_ORDER = (SUCCESS_TEXT, *FAILURE_FILTERS, ERROR_TEXT)

# 결과 표를 세울 수 있는 칸. 값이 없는 줄(대기 · 추론 시간 없음)은 방향과 상관없이 뒤에 간다
SORT_COLUMNS = ("번호", "기능", "발화", "결과", "추론 시간")
ASCENDING, DESCENDING = "오름차순", "내림차순"
SORT_ORDERS = (ASCENDING, DESCENDING)
# 정렬 중인 칸 머리 글자 뒤에 붙는 표시. 기본 차례(정렬 없음)에는 안 붙는다
SORT_MARKS = {ASCENDING: "▲", DESCENDING: "▼"}
SORT_HELP = "머리글을 누르면 오름차순 → 내림차순 → 기본 차례로 바뀝니다."

# 기능 자리의 두 값. 나머지는 기대 recipe id 다. 범위 밖은 기능이 아니라 거르기 위한 자리일 뿐이다
ALL_GROUPS, OUT_OF_SCOPE_GROUP = "__all__", "__out_of_scope__"
OUT_OF_SCOPE_TEXT = "범위 밖"

NONE_TEXT = "없음"
# 아직 안 돈 발화. 성공도 실패도 아니다
PENDING_TEXT = "대기"
# 실행 기록 고르기 글자에 붙는 보관 갈래. official 만 붙고 local 은 아무것도 안 붙는다. run_id 에는 안 들어간다
KIND_LABELS = {"official": "Official"}
# 끝나지 않은 기록 표시. 고르기 글자의 맨 끝이다
STOPPED_TEXT = "중단됨"
EMPTY_NUMBER = "—"
# 기대 기능이 그 인자를 읽지 않음. 「없음」(읽는데 값이 null)과 다르다
UNUSED_TEXT = "사용 안 함"

# 새로 실행이 run_evaluation 에 넘기는 값. 화면에 안 보인다.
# materialize 는 켠다. 화면에는 안 보이지만 결과(실행 기록)에 남겨 뒤에 실행 화면이 쓴다.
# MCP 는 안 부른다. 문맥은 계기판 기본값(both)과 같다. 팬 소음 억제는 화면의 체크박스(FAN_QUIET_KEY)가 정하고
# 팬을 보는 것은 _Job 이 만드는 monitor_gpu.GpuMonitor 다. 팬 · 온도는 결과에 안 남는다.
RUN_OPTIONS = {"materialize": True, "context_label": "both"}

FAN_QUIET_LABEL = "GPU 팬 소음 억제"
FAN_QUIET_HELP = ("팬 속도가 높아지면 다음 발화 실행을 잠시 대기해 소음을 줄이지만, "
                  "GPU 누적 대기시간이 늘어나 전체 평가시간이 길어질 수 있습니다.")
# 도는 동안 팬 때문에 다음 발화를 기다릴 때 실행 상태 글자 끝에 붙는 말
FAN_WAIT_TEXT = "GPU 팬 안정 대기 중"

# 모델 설정 (자세히 보기) 칸. 화면 글자 -> run_evaluation 결과 meta.conditions 의 칸. 파일 · 폴더는 경로만 보임.
# 모델 이름은 실행 개요에 있어 여기 되풀이하지 않는다
CONDITION_ROWS = (
    ("provider", "provider"),
    ("프롬프트 파일", "prompt"),
    ("응답 형식 파일", "response_schema"),
    ("기능 정의 파일", "menu"),
)
# 실행 환경의 VRAM 줄 글자. 값은 GPU 한 장의 총량이다
VRAM_LABEL = "VRAM (GPU 1개당)"

# 실행 개요의 시간 칸. 앞 셋은 잰 값이고, 기타 진행 시간은 그 셋에서 계산한 나머지다 (따로 잰 timer 가 아님)
TIME_CELL = "소요 시간"
TIME_HELP = {
    "전체 평가시간": "평가를 시작한 시점부터 완료될 때까지 실제로 걸린 전체 시간입니다. 전체 추론시간, GPU 누적 대기시간, "
                     "그리고 발화 간 전환·결과 집계·저장·평가 제어 등 기타 진행 시간이 포함됩니다.",
    "전체 추론시간": "각 발화의 AI 추론에 실제로 소요된 시간을 모두 합한 값입니다. GPU 팬 소음 억제를 위한 대기시간과 "
                     "기타 진행 시간은 포함하지 않습니다.",
    "GPU 누적 대기시간": "GPU 팬 소음 억제 기능으로 인해 다음 발화 실행을 기다린 시간을 모두 합한 값입니다.",
    "기타 진행 시간": "전체 평가시간에서 전체 추론시간과 GPU 누적 대기시간을 제외한 나머지 시간입니다. 발화 간 전환, "
                      "결과 집계·저장, 평가 제어 등 AI 추론이나 GPU 팬 대기에 포함되지 않는 진행 시간이 포함됩니다.",
}
# 기타 진행 시간(나머지)이 이만큼(초)까지 음수면 반올림 오차로 보고 0 으로 둔다. elapsed_s 는 0.1초, latency.total 은
# 0.001초로 반올림해 저장되므로 그 차이보다 넉넉한 값이다. 이보다 더 음수면 기록이 서로 안 맞는 것이라 값을 안 보인다
RESIDUAL_TOLERANCE_S = 1.0
# 실행 개요의 열. 값 한 줄짜리 섹션 셋은 한 열에 쌓고, 나머지는 섹션마다 한 열이다
OVERVIEW_COLUMNS = (
    ("Test Suite", "평가 시작 시간", "모델"),
    (TIME_CELL,),
    ("발화당 추론 시간",),
    ("평가 결과",),
    ("실행 환경",),
)
# 옛 기록이라 그 칸이 저장되지 않은 값. 0 으로 채우지 않는다
MISSING_TEXT = "기록 없음"

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
GROUP_KEY = "test_group"             # 기능별 결과 카드로 고른 기능 자리. widget 이 아니라 값
SAVED_RESET_KEY = "test_saved_reset" # 다음 회차에 실행 기록 고르기를 「불러올 기록 고르기」로 되돌림
DATASET_KEY = "test_set"             # Test Suite 고르기 widget
LOAD_ERROR_KEY = "test_load_error"   # 실행 기록을 못 읽었을 때의 문장
FILTER_KEY = "test_filter"           # 보기 필터 widget
SORT_KEY = "test_sort"               # 머리글로 고른 정렬 (칸, 방향). 없으면(None) 기본 차례(번호 오름차순)
JOB_KEY = "test_job"                 # 이 창이 지켜보는 _Job 의 token. 끝나면 결과를 받아 옴
RESUME_KEY = "test_resume_check"     # {"key", "check"} 불러온 기록의 이어 실행 판정 (run_evaluation.resume_check)
STARTED_KEY = "test_started"         # 몸통 fragment 안에서 실행을 시작했다. 화면 전체를 한 번 다시 그림
FAN_QUIET_KEY = "test_fan_quiet"     # GPU 팬 소음 억제 체크박스. 기본 켜짐. 새로 실행을 누를 때 읽음

# 기능 번호에 마우스를 올린 뒤 설명이 뜨기까지(ms). 스쳐 지나갈 때 깜빡이지 않을 만큼만 둔다.
TIP_DELAY_MS = 120

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
    """고른 Test Suite 의 결과 표 뼈대. 실행이 도는 발화마다 대기 줄 하나, 정답표 차례.

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
    """보기 필터 · 고른 기능 · 발화 검색을 건 목록. 셋은 서로 따로 걸려 겹친 것만 남음.

    입력  run_evaluation 결과 cases. view 는 FILTERS 중 하나. 모르는 값이면 전체
          group 은 ALL_GROUPS · OUT_OF_SCOPE_GROUP · 기대 recipe id
    출력  원래 순서를 지킨 부분 목록
    규칙  실패는 기능 선택 · 인자 추출 · 범위 밖 처리 셋 중 하나에서 멈춘 것. 대기 · 오류 줄은 실패가 아님
          실패 · 기능 선택 · 실패 · 인자 추출 · 실패 · 범위 밖 처리(FAILURE_TEXT)는 그 단계에서 실패한 것.
          오류(ERROR_FILTER)는 오류 줄만
          group 이 ALL_GROUPS 가 아니면 row_group 이 같은 줄만
          검색은 띄어쓰기를 무시한 부분 일치. 빈 검색어는 거르지 않음
    """
    if view == FAILED:
        shown = [r for r in rows if failed(r)]
    elif view == ERROR_FILTER:
        shown = [r for r in rows if errored(r)]
    elif view in FAILURE_FILTERS:
        stage = next(k for k, v in FAILURE_TEXT.items() if v == view)
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
    """표에 있는 기능 자리. 전체 · 결과에 나온 기대 recipe (번호 차례) · 범위 밖(있을 때). 고른 기능이 남았나 볼 때 씀."""
    groups = {row_group(r) for r in rows}
    recipes = sorted(g for g in groups if g and g != OUT_OF_SCOPE_GROUP)
    return [ALL_GROUPS, *recipes, *([OUT_OF_SCOPE_GROUP] if OUT_OF_SCOPE_GROUP in groups else [])]


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
    return FAILURE_TEXT.get(row.get("failure_stage"), FAILED)


def _sort_key(row: dict, column: str):
    """정렬 칸 하나의 값. 값이 없는 줄(대기 결과 · 추론 시간 없음)은 None."""
    if column == "기능":
        group = row_group(row)
        return (1, 0) if group == OUT_OF_SCOPE_GROUP else (0, _recipe_number(group or ""))
    if column == "발화":
        return row["utterance"]
    if column == "결과":
        label = verdict_label(row)
        return RESULT_ORDER.index(label) if label in RESULT_ORDER else None
    if column == "추론 시간":
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
    """초 단위 추론 시간 글자. 소수 둘째 자리 「1.62초」. 값이 없으면 빈 글자. 값은 그대로 두고 글자만 반올림."""
    return f"{value:.2f}초" if isinstance(value, (int, float)) else ""


def list_frame(rows: list[dict]) -> pd.DataFrame:
    """결과 목록 표. 한 발화 한 줄, 칸 다섯. 추론 시간은 그 발화의 resolve 한 번에 걸린 시간.

    규칙  결과 칸은 verdict_label. 대기 줄은 결과 「대기」, 추론 시간 빈칸
          판정 칸을 따로 두지 않음. 모델이 낸 판정 상태(SELECT · CLARIFY · NO_MATCH)는 상세에 있음

    제약  기능 칸에 설명을 붙이지 않는다. st.dataframe 은 칸 값마다의 tooltip 을 받는 API 가 없다.
          줄을 고르면 상세 칸에 그 기능의 설명이 나온다
    """
    return pd.DataFrame(
        {
            "번호": [f"{r['case_id']:03d}" for r in rows],
            "기능": [OUT_OF_SCOPE_TEXT if row_group(r) == OUT_OF_SCOPE_GROUP else (function_label(row_group(r)) or "") for r in rows],
            "발화": [r["utterance"] for r in rows],
            "결과": [verdict_label(r) for r in rows],
            "추론 시간": [_seconds((r.get("timing") or {}).get("resolve_s")) for r in rows],
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
    """모델 설정 (자세히 보기) 의 줄. {화면 글자: 값}. 결과가 없으면 None.

    규칙  run_evaluation 결과 meta.conditions 에서 옮김. provider ·
          요청 설정(Temperature 가 맨 앞) · 호출 상한 · 파일 셋(경로만)
          모델 이름은 실행 개요에 있어 안 넣음. 역할(meta.role) · 게시 자산(conditions.registry) · 실행 기록 id 는
          기록에만 두고 화면에 안 보임
          조건을 못 읽은 결과면 그 까닭 한 줄
    제약  없는 칸을 지어내지 않는다
    """
    if not result:
        return None
    conditions = result["meta"].get("conditions") or {}
    if "error" in conditions:
        return {"모델 설정": conditions["error"]}
    shown = {"provider": conditions.get("provider")}
    shown.update(request_rows(conditions))
    timeout = (conditions.get("inference") or {}).get("timeout")
    if timeout is not None:
        shown["호출 상한"] = f"{timeout}초"
    for label, key in CONDITION_ROWS[1:]:
        value = conditions.get(key)
        shown[label] = value.get("path") if isinstance(value, dict) else value
    return {label: value if value is not None else NONE_TEXT for label, value in shown.items()}


def _duration(seconds) -> str:
    if not isinstance(seconds, (int, float)):
        return EMPTY_NUMBER
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}분 {rest}초" if minutes else f"{rest}초"


def environment_rows(result: dict) -> dict:
    """실행 환경. {"GPU": …, VRAM_LABEL: …}. 기록이 없으면 두 칸 다 「기록 없음」.

    규칙  run_evaluation 결과 meta.environment.gpus. 이름이 모두 같으면 「이름 × 장수」, 다르면 이름을 이음
          VRAM 은 GPU 한 장의 총량(GiB). 모두 같으면 「95.6 GiB」 하나, 다르면 장마다 이음. 글자(VRAM_LABEL)가 한 장 값임을 말함
          온도 · 사용률은 안 보임 (옛 결과의 meta.gpu 도 안 읽음)
    """
    gpus = ((result["meta"].get("environment") or {}).get("gpus")) or []
    if not gpus:
        return {"GPU": "기록 없음", VRAM_LABEL: "기록 없음"}
    names = [gpu.get("name") or "?" for gpu in gpus]
    name = f"{names[0]} × {len(names)}" if len(set(names)) == 1 else " · ".join(names)
    sizes = [gpu.get("memory_total_mib") for gpu in gpus]
    if any(size is None for size in sizes):
        vram = "기록 없음"
    elif len(set(sizes)) == 1:
        vram = f"{sizes[0] / 1024:.1f} GiB"
    else:
        vram = " · ".join(f"{size / 1024:.1f} GiB" for size in sizes)
    return {"GPU": name, VRAM_LABEL: vram}


def run_identity(result: dict) -> dict:
    """저장 자리. 모델 설정 아래 한 줄. 없으면 뺌. 실행 기록 id 는 실행 기록 고르기 글자에 있어 안 되풀이함."""
    meta = result["meta"]
    shown = {}
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


def other_seconds(elapsed, inference, fan_wait) -> float | None:
    """기타 진행 시간(초). 전체 평가시간 - 전체 추론시간 - GPU 누적 대기시간. 계산할 수 없으면 None.

    입력  meta.elapsed_s · summary.latency.total · meta.fan_wait_s
    규칙  셋이 모두 숫자일 때만 셈. 하나라도 없으면(옛 기록) None. 0 으로 채우지 않음
          RESIDUAL_TOLERANCE_S 안의 음수는 반올림 오차라 0. 그보다 큰 음수는 None (기록이 서로 안 맞음)
    제약  따로 잰 값이 아니다. 기록에 새로 적지 않는다
    """
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (elapsed, inference, fan_wait)):
        return None
    rest = elapsed - inference - fan_wait
    if rest < -RESIDUAL_TOLERANCE_S:
        return None
    return max(rest, 0.0)


def overview(result: dict | None, live: dict | None = None) -> list[tuple[str, list[tuple[str, str]]]] | None:
    """실행 개요. 기록을 열면 바로 볼 것만. [(칸 이름, [(글자, 값)])]. 결과가 없으면 None.

    칸  Test Suite · 평가 시작 시간 · 소요 시간(전체 평가시간 · 전체 추론시간 · GPU 누적 대기시간 · 기타 진행 시간) ·
        발화당 추론 시간(Median · P95 · Max) · 평가 결과(전체 · 성공 · 실패 · 오류) · 모델 ·
        실행 환경(GPU · VRAM (GPU 1개당))
        소요 시간 줄은 (글자, 값, 도움말) 셋. 도움말은 TIME_HELP
    규칙  run_evaluation 결과 meta · summary 를 옮겨 적음. 여기서 세지 않음
          평가 지표(기능 선택 · 인자 추출 등)는 여기 안 둠. 아래 전체 결과가 보임
          전체 평가시간은 meta.elapsed_s (잰 동안의 벽시계. 팬 대기 포함, 멈춰 있던 시간 제외)
          전체 추론시간은 summary.latency.total (발화마다 resolve 한 번에 걸린 timing.resolve_s 의 합).
          materialize · 팬 대기 · 화면 시간이 안 섞임. 잰 것이 없으면 줄표
          GPU 누적 대기시간은 meta.fan_wait_s (팬 소음 억제로 다음 발화를 기다린 합)
          elapsed_s · fan_wait_s 칸이 없는 옛 기록은 「기록 없음」. 0 으로 채우지 않음. 칸이 있고 0 이면 0초
          live 가 있으면(도는 중, _Job.live_times) 세 시간은 기록 대신 그 값. 전체 추론시간도 부르는 중인 몫까지
          결과에 planned 가 있으면(도는 중) 평가 결과의 전체는 잴 수, 성공 · 실패 · 오류는 끝난 줄에서
          기타 진행 시간은 세 값에서 계산한 나머지(other_seconds). 하나라도 없으면 「기록 없음」
          발화당 추론 시간은 발화 하나의 resolve 한 번에 걸린 시간의 분포. 소수 둘째 자리. 잰 것이 없으면 줄표
          Temperature 같은 요청 설정 · 파일은 여기 안 보임. 모델 설정 (자세히 보기)에 있음
    """
    if not result:
        return None
    meta, summary = result["meta"], result["summary"]
    total = summary["total"]
    started = meta.get("started_at")
    delay = summary.get("latency") or {}
    conditions = meta.get("conditions") or {}

    def seconds(key):
        return _seconds(delay.get(key)) or EMPTY_NUMBER

    if live:
        elapsed, inference, fan_wait = live["elapsed"], live["inference"], live["fan_wait"]
    else:
        elapsed, inference, fan_wait = meta.get("elapsed_s"), delay.get("total"), meta.get("fan_wait_s")

    def stored(value):
        return _duration(value) if isinstance(value, (int, float)) else MISSING_TEXT

    other = other_seconds(elapsed, inference, fan_wait)
    times = [
        ("전체 평가시간", stored(elapsed)),
        ("전체 추론시간", _duration(inference)),
        ("GPU 누적 대기시간", stored(fan_wait)),
        ("기타 진행 시간", _duration(other) if other is not None else MISSING_TEXT),
    ]

    return [
        ("Test Suite", [("", suite_filename(meta.get("suite") or {}))]),
        ("평가 시작 시간", [("", f"{datetime.datetime.fromisoformat(started):%Y-%m-%d %H:%M:%S}" if started else EMPTY_NUMBER)]),
        (TIME_CELL, [(label, value, TIME_HELP[label]) for label, value in times]),
        ("발화당 추론 시간", [("Median", seconds("median")), ("P95", seconds("p95")), ("Max", seconds("max"))]),
        ("평가 결과", [
            ("전체", str(result.get("planned") or total["runs"])),
            ("성공", str(total["passed"])),
            ("실패", str(total["runs"] - total["passed"] - total["failure_stages"].get("error", 0))),
            ("오류", str(total["errors"])),
        ]),
        ("모델", [("", str(conditions.get("model") or EMPTY_NUMBER))]),
        ("실행 환경", list(environment_rows(result).items())),
    ]


def _recipe_number(recipe_id: str) -> int:
    """기능 번호의 숫자. "recipe_061" -> 61. 숫자가 없으면 아주 큰 수(뒤로)."""
    tail = str(recipe_id).rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 10**9


def recipe_rows(result: dict | None) -> list[dict]:
    """기능별 결과. [{group, label, runs, passed, failed}] 기능 번호의 숫자 차례, 범위 밖 발화가 있으면 맨 뒤에 범위 밖.

    규칙  run_evaluation 결과 summary.recipes 를 옮김. 차례는 번호를 숫자로 읽어 오름차순 (글자 차례가 아님)
          범위 밖(OUT_OF_SCOPE_GROUP)은 기능이 아니라 표를 거르는 자리. summary.total 의 oos_runs · oos_passed 를 옮김.
          범위 밖 발화가 없거나 옛 결과라 oos_passed 가 없으면 안 넣음
    제약  여기서 세지 않는다. 범위 밖을 기능으로 채점하지 않는다
    """
    if not result:
        return []
    entries = [
        {"group": rid, "label": function_label(rid), "runs": v["runs"], "passed": v["passed"], "failed": v["runs"] - v["passed"]}
        for rid, v in (result["summary"].get("recipes") or {}).items()
    ]
    entries.sort(key=lambda e: _recipe_number(e["group"]))
    total = result["summary"].get("total") or {}
    if total.get("oos_runs") and total.get("oos_passed") is not None:
        entries.append({"group": OUT_OF_SCOPE_GROUP, "label": OUT_OF_SCOPE_TEXT, "runs": total["oos_runs"],
                        "passed": total["oos_passed"], "failed": total["oos_runs"] - total["oos_passed"]})
    return entries


def first_failure(rows: list[dict]) -> int | None:
    """목록에서 첫 실패 줄의 자리, 실패가 없으면 첫 오류 줄. 없으면 None. 대기 줄은 실패가 아님."""
    found = next((i for i, r in enumerate(rows) if failed(r)), None)
    return found if found is not None else next((i for i, r in enumerate(rows) if errored(r)), None)


def saved_key(entry: dict) -> str:
    """실행 기록 고르기의 값. "<kind>:<run_id>". 불러올 때 어느 자리의 것인지를 함께 넘김."""
    return f"{entry['kind']}:{entry['run_id']}"


def saved_label(entry: dict) -> str:
    """실행 기록 고르기 글자. 「<run_id> · 성공/전체」 꼴. 전체는 그 기록이 실제로 잰 수다.

    규칙  끝나지 않은 기록(run.json 없음)은 「<run_id> · 끝난 수/잴 수 · 중단됨」. 잴 수를 모르면 수 없이 「중단됨」
          official 기록만 수 뒤에 「Official」(KIND_LABELS). local 은 갈래 글자를 안 붙임
          같은 run_id 가 두 자리에 다 있으면 「중복」을 붙임
          「중단됨」은 늘 맨 끝. 「<run_id> · 끝난 수/잴 수 · Official · 중복 · 중단됨」 차례
    제약  run_id 가 먼저다. 저장 자리가 dev/evaluation/outputs/<official|local>_benchmark/<run_id>/ 라
          고르기 글자와 폴더가 1:1 로 맞아야 한다. 사람용 별칭을 앞에 두지 않는다.
          run_id 안에 이미 정답표 이름과 시각이 들어 있다
    """
    complete = bool(entry.get("complete") and entry.get("runs") is not None)
    parts = [entry["run_id"]]
    if complete:
        parts.append(f"{entry['passed']}/{entry['runs']}")
    elif entry.get("planned") is not None and entry.get("done") is not None:
        parts.append(f"{entry['done']}/{entry['planned']}")
    if entry.get("kind") in KIND_LABELS:
        parts.append(KIND_LABELS[entry["kind"]])
    if entry.get("duplicate"):
        parts.append("중복")
    if not complete:
        parts.append(STOPPED_TEXT)
    return " · ".join(parts)


@st.cache_data(show_spinner=False)
def _case_count(path: str, modified: int) -> int | None:
    """정답표에서 기본으로 도는 발화 수. 파일이 바뀔 때만 다시 읽음. 못 읽으면 None."""
    try:
        suite = evaluation_suite.load(Path(path))
    except (OSError, ValueError):
        return None
    return sum(1 for case in suite["cases"] if case["enabled"])


def dataset_label(entry: dict) -> str:
    """Test Suite 고르기에 보일 이름. 정답표 파일 이름이 먼저고, 발화 수를 셀 수 있으면 붙임.

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


def share_of_failed(count, failed) -> str:
    """실패를 가른 한 갈래의 건수 글자. 「11/15」 꼴. 실패가 없으면 건수만. 모르면 줄표."""
    if not isinstance(count, int) or not isinstance(failed, int):
        return EMPTY_NUMBER
    return f"{count}/{failed}" if failed else str(count)


def summary_markup(summary: dict | None) -> str:
    """전체 결과. 머리 한 줄과 낮은 카드 한 줄. 결과가 없으면 숫자 자리에 줄표만.

    규칙  전체 · 성공 · 실패가 나란한 카드. 숫자 옆에 작은 글자(발화 수 · 끝난 수에 대한 백분율)
          실패 카드만 넓고 왼쪽에 실패 수 · 백분율, 오른쪽에 실패를 가른 셋(기능 선택 · 인자 추출 · 범위 밖 처리)을
          「11/15」 꼴로 세로로 둠. 동등한 카드로 세우면 전체 · 성공 · 실패와 같은 층으로 읽힘
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
        note_html = f'<span class="tt-kpi-note">{_esc(note)}</span>' if note else ""
        main = (
            f'<div class="tt-kpi-main"><div class="tt-kpi-label">{_esc(label)}</div>'
            f'<div class="tt-kpi-line"><span class="tt-kpi-num">{_esc(number)}</span>{note_html}</div></div>'
        )
        return f'<div class="tt-kpi {tone}{" tt-kpi-split" if causes else ""}">{main}{causes}</div>'

    def causes_block(numbers, failed, notes):
        rows = "".join(
            cause(label, share_of_failed(numbers.get(key), failed), notes.get(key, "")) for label, key in FAILURE_CAUSES
        )
        return f'<div class="tt-causes"><div class="tt-causes-head">{_esc(CAUSE_NOTE)}</div>{rows}</div>'

    if summary is None:
        empty = causes_block({}, None, {})
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
    causes = causes_block(summary, summary["failed"], {} if summary.get("oos_runs") else {"scope": NO_OOS_NOTE})
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
    """실행 개요. 섹션마다 제목 아래 (글자 · 값) 줄. 섹션은 OVERVIEW_COLUMNS 의 열로 묶음. 결과가 없으면 빈 글자.

    규칙  한 열에 섹션 하나 또는 값 한 줄짜리 섹션 여럿(Test Suite · 평가 시작 시간 · 모델)을 세로로 쌓음.
          OVERVIEW_COLUMNS 에 없는 섹션은 제 열 하나를 받아 뒤에 붙음
          줄에 도움말(셋째 값)이 있으면 글자 뒤에 작은 「?」 아이콘(tt-help)을 두고, 그 아이콘에 data-tip 을 걸어
          기능 번호와 같은 tooltip 으로 뜸. 글자 자체에는 밑줄 · tooltip 이 없음
          열 폭 · 줄바꿈은 panel_css 가 정함
    """
    if info is None:
        return ""

    def line(row):
        label, value, tip = (*row, None)[:3]
        if not label:
            return f'<div class="tt-ov-row"><span class="tt-ov-v">{_esc(value)}</span></div>'
        help_icon = (f'<span class="tt-help" data-tip="{_esc(tip)}" aria-label="도움말" '
                     f'aria-description="{_esc(tip)}">?</span>') if tip else ""
        return (
            f'<div class="tt-ov-row"><span class="tt-ov-label"><span class="tt-ov-sub">{_esc(label)}</span>{help_icon}</span>'
            f'<span class="tt-ov-v">{_esc(value)}</span></div>'
        )

    def cell(title, rows):
        return (f'<div class="tt-ov"><div class="tt-ov-k">{_esc(title)}</div>'
                f'<div class="tt-ov-rows">{"".join(line(row) for row in rows)}</div></div>')

    sections = dict(info)
    grouped = [[title for title in column if title in sections] for column in OVERVIEW_COLUMNS]
    placed = {title for column in grouped for title in column}
    grouped += [[title] for title, _rows in info if title not in placed]
    columns = "".join(
        '<div class="tt-ovc">' + "".join(cell(title, sections[title]) for title in column) + "</div>"
        for column in grouped if column
    )
    return f'<div class="tt-ovs">{columns}</div>'


def recipe_card_key(entry: dict) -> str:
    """기능별 결과 카드 단추의 key. 실패가 있으면 test_fn_ng_…, 다 맞았으면 test_fn_ok_… (panel_css 가 이 앞머리로 칠함)."""
    tone = "ng" if entry["failed"] else "ok"
    return f"test_fn_{tone}_{entry['group'].strip('_')}"


def recipe_card_label(entry: dict) -> str:
    """기능별 결과 카드 글자. 「기능 015 **4/5**」 꼴 (번호와 성공 수 둘만). 범위 밖이면 「범위 밖 **7/8**」."""
    return f"{entry['label']} **{entry['passed']}/{entry['runs']}**"


def _css_text(text: str) -> str:
    """CSS content 문자열 안에 넣을 글자. 따옴표 · 역슬래시 · 꺾쇠 · 줄바꿈을 escape."""
    return (str(text).replace("\\", "\\\\").replace('"', '\\"').replace("<", "\\3C ").replace(">", "\\3E ")
            .replace("\n", " "))


def recipe_card_css(entries: list[dict], functions: dict | None = None) -> str:
    """기능별 결과 카드의 tooltip. 카드마다 그 기능 설명을 CSS content 로 붙인 <style>.

    규칙  단추 글자는 HTML 을 못 받아 number_markup 의 data-tip 을 못 씀. 같은 tooltip 을 카드 key(recipe_card_key)의
          ::after 로 그림. 모양 · 뜨기까지의 지연(TIP_DELAY_MS)은 panel_css 의 기능 번호 tooltip 과 같음
          설명의 원천은 run_evaluation 결과 meta.functions 하나. 설명이 없는 카드(범위 밖 등)는 tooltip 없음
    제약  {번호: 설명} 표를 화면에 따로 두지 않는다
    """
    functions = functions or {}
    rules = "".join(
        f'.st-key-test_tab .st-key-{recipe_card_key(e)} button::after {{ content: "{_css_text(functions[e["group"]])}"; }}\n'
        for e in entries if functions.get(e["group"])
    )
    return f"<style>{rules}</style>" if rules else ""


def _value_markup(value) -> str:
    """값 하나. 없음은 흐리게."""
    text = display_value(value)
    css = "tt-val tt-none" if text == NONE_TEXT else "tt-val"
    return f'<span class="{css}">{_esc(text)}</span>'


def _muted_markup(text: str) -> str:
    """값 자리에 넣는 흐린 글자."""
    return f'<span class="tt-val tt-none">{_esc(text)}</span>'


def _tip(recipe_id: str | None, functions: dict) -> str:
    """기능 번호에 걸 tooltip 속성. 설명은 run_evaluation 결과 meta.functions (게시 menu 의 function 문장).

    규칙  data-tip 은 panel_css 가 마우스를 올리고 TIP_DELAY_MS 뒤에 그림. aria-description 은 화면 낭독기용
    제약  title 을 쓰지 않는다. 브라우저 기본 tooltip 은 뜨기까지 지연을 못 바꾸고, 같이 두면 두 개가 뜬다
    """
    text = (functions or {}).get(recipe_id)
    return f' data-tip="{_esc(text)}" aria-description="{_esc(text)}"' if text else ""


def number_markup(recipe_id: str | None, functions: dict, css: str = "") -> str:
    """화면에 보이는 기능 번호 하나. 「기능 004」만 보이고 설명은 마우스를 올리면 뜸.

    입력  css 는 이 자리에서 더 붙일 class. 없으면 안 붙음
    출력  <span class="tt-fnum …" data-tip="설명" aria-description="설명">기능 004</span>. 번호가 없으면 빈 글자
    규칙  설명의 원천은 run_evaluation 결과 meta.functions 하나 (게시 menu 의 function 문장)
          설명이 없는 번호면 tooltip 없이 번호만 보임
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


# 기능 번호 pill. 비교 칸 · 후보 기능이 같은 모양이다
CHIP_CSS = "tt-chip"


def _function_markup(recipe_ids: list, functions: dict, empty: str = "선택 없음") -> str:
    """기능 번호 pill 과 설명. 고르지 않았으면 empty 글자.

    규칙  기능이 여럿이면 차례대로 모두 보임. 설명은 줄로도 보이고 번호의 마우스에도 붙음
    """
    shown = [rid for rid in recipe_ids if rid]
    if not shown:
        return f'<div class="tt-fn tt-none">{_esc(empty)}</div>'
    return "".join(
        f'<div class="tt-fn">{number_markup(rid, functions, CHIP_CSS)}</div>'
        f'<div class="tt-desc">{_esc(functions.get(rid) or "")}</div>'
        for rid in shown
    )


def _picked_markup(row: dict, functions: dict) -> str:
    """비교 칸 AI 모델 출력의 기능. 모델 판정마다 다름.

    규칙  오류면 「오류」. SELECT 면 고른 기능 pill 하나와 설명
          CLARIFY 면 모델이 되물은 후보 기능(candidate_recipe_ids)을 모델이 낸 차례대로 pill 하나씩. 설명은 마우스에만.
          후보가 없으면 「되묻기」
          NO_MATCH 면 「해당 없음」. 그 밖의 판정은 판정 글자
    제약  후보 번호를 글자로 이어 붙이지 않는다. 「되묻기」라는 판정은 모델 판정 상태 칸에 그대로 남는다
    """
    model = row.get("actual") or {}
    status = model.get("status")
    if row.get("error"):
        return _function_markup([], functions, STAGE_LABELS["error"])
    if status == "SELECT":
        return _function_markup([model.get("recipe_id")], functions)
    candidates = [rid for rid in model.get("candidate_recipe_ids") or [] if rid]
    if status == "CLARIFY" and candidates:
        chips = "".join(number_markup(rid, functions, CHIP_CSS) for rid in candidates)
        return f'<div class="tt-fn tt-fns">{chips}</div>'
    return _function_markup([], functions, STATUS_LABELS.get(status, "선택 없음"))


def _key_markup(label: str, name: str | None = None) -> str:
    """줄 머리. 표시명이 변수명과 다르면 변수명을 아래에 작게."""
    sub = f'<div class="tt-var">{_esc(name)}</div>' if name and name != label else ""
    return f'<div class="tt-c tt-key"><div class="tt-key-label">{_esc(label)}</div>{sub}</div>'


def _pair_markup(key_html: str, answer_html: str, model_html: str, *, wrong: bool, graded: bool = True,
                 cause: bool = False) -> str:
    """비교 한 줄. 줄 머리 · 정답표 · AI 모델 출력.

    입력  wrong 은 run_evaluation 이 틀렸다고 판정한 칸인가
          cause 는 이 칸이 그 발화의 실패 단계(failure_stage)를 만든 칸인가
    규칙  채점하는 칸이 틀렸으면 모델 출력 칸을 강조함
          「실패」 표시는 틀렸고 cause 인 칸에만 닮. 틀렸어도 먼저 걸린 단계가 따로 있으면
          (기능 선택이 틀려 인자는 실패 원인이 아님) 강조만 하고 표시는 안 닮
          graded 가 거짓인 칸(기대 기능이 안 읽는 인자)은 줄 전체를 흐리게 둠. 강조하지 않음
    """
    tag, cell = "", "tt-c tt-model"
    row = "" if graded else " tt-ungraded"
    if wrong and graded:
        cell += " tt-diff"
        if cause:
            tag = f'<span class="tt-tag tt-tag-fail">{FAILED}</span>'
    return (
        f'<div class="tt-row{row}">{key_html}'
        f'<div class="tt-c tt-answer">{answer_html}</div>'
        f'<div class="{cell}">{model_html}{tag}</div></div>'
    )


def _extra_markup(row: dict, functions: dict | None = None) -> str:
    """AI 모델 출력의 부가 정보. 판정 상태 · 후보 기능 · 판단 · 추론 시간. 오류면 오류 문장.

    규칙  후보 기능은 「기능 NNN」만 보이고, 마우스를 올리면 그 기능 설명(functions)이 뜸
          추론 시간은 이 발화의 resolve 한 번에 걸린 시간
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
        f'<div class="tt-kv"><div class="tt-kv-k">추론 시간</div>'
        f'<div class="tt-kv-v">{_esc(_seconds(timing.get("resolve_s")) or NONE_TEXT)}</div></div>'
        "</div>"
    )


def detail_markup(row: dict, functions: dict) -> str:
    """선택한 발화 상세. 성공 · 실패가 같은 틀.

    입력  run_evaluation 결과 cases 한 줄 · meta.functions
    규칙  맨 위 한 줄에 번호 · 발화 · 결과(verdict_label). 오류는 실패와 다른 색
          정답표 | AI 모델 출력 두 칸에 기능 번호 · 설명과 인자 전부(field_rows).
          AI 모델 출력의 기능은 _picked_markup (되묻기면 후보 기능 pill 여럿)
          기능 칸 강조는 run_evaluation 의 recipe_correct, 인자 칸 강조는 spoken_fields 의 correct
          「실패」 표시는 failure_stage 를 만든 칸에만 — function 이면 기능 칸, input 이면 틀린 인자 칸,
          scope 면 범위 밖 기능 칸. error 는 모델 출력이 없어 강조 · 표시 둘 다 안 함
          인자 값 칸은 셋으로 가름 — 기대 기능이 안 읽는 인자는 두 칸 다 「사용 안 함」,
          읽는데 값이 null 이면 「없음」, 값이 있으면 그 값
          범위 밖 발화는 기능 칸에 「범위 밖 · 선택할 기능 없음」과 모델이 고른 것을 맞댐. 인자 줄 없음.
          강조는 run_evaluation 의 passed
          그 아래 AI 모델 출력의 판정 상태 · 후보 기능(설명은 마우스를 올리면) · 판단 · 추론 시간
    """
    if pending(row):
        return pending_markup(row)
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
    picked = _picked_markup(row, functions)

    if row.get("scope") == "out_of_scope":
        category = row["expected"].get("category")
        rows += [
            '<div class="tt-sec">기능 선택</div>',
            _pair_markup(
                _key_markup("기능"),
                f'<div class="tt-fn">범위 밖 · 선택할 기능 없음</div>'
                f'<div class="tt-desc">{_esc(CATEGORY_LABELS.get(category, category))}</div>',
                picked,
                wrong=failed(row),
                cause=row.get("failure_stage") == "scope",
            ),
        ]
        return f'{head}<div class="tt-cmp">{"".join(rows)}</div>{_extra_markup(row, functions)}'

    rows += [
        '<div class="tt-sec">기능 선택</div>',
        _pair_markup(
            _key_markup("기능"),
            _function_markup(row["expected"]["recipe_ids"], functions),
            picked,
            wrong=row.get("recipe_correct") is False and not errored(row),
            cause=row.get("failure_stage") == "function",
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
                cause=row.get("failure_stage") == "input",
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
def run_selected(dataset_id: str, on_progress=None, should_stop=None, *, fan_quiet: bool = True, monitor=None,
                 clock=None) -> dict:
    """고른 정답표를 dev/evaluation/run_evaluation 으로 새로 잰 결과. 새 run_id · 새 폴더.

    규칙  run_evaluation.run_dataset 에 RUN_OPTIONS 와 그 문맥 · 팬 소음 억제(fan_quiet_mode) · monitor · should_stop 을
          넘김. 판정은 전부 평가 쪽이 함. monitor 가 없으면 여기서 monitor_gpu.GpuMonitor 를 만듦
          run_dataset 이 Test Run 을 outputs/local_benchmark 에 저절로 남김. 폴더는 시작하자마자 생김
          run_evaluation 을 여기서 import 함. 탭을 열기만 해서는 계기판 모듈을 안 읽음
          clock 이 있으면(_Job) resolve 를 clock.timed 로 감싸 추론 중인 구간을 알리고, 시작 머리를 clock.started 에 넘김
    제약  판정 · 채점을 여기서 하지 않는다. st.* 를 부르지 않는다 (백그라운드 thread 에서 불림)
    """
    from dev.evaluation import run_evaluation
    from dev.evaluation.engine import monitor_gpu

    options = dict(RUN_OPTIONS)
    options["context"] = run_evaluation.context_payload(options["context_label"])
    if clock is not None:
        options.update(resolve=clock.timed(run_evaluation.resolve_via_api), on_start=clock.started)
    return run_evaluation.run_dataset(
        dataset_id, progress=on_progress, fan_quiet_mode=fan_quiet, monitor=monitor or monitor_gpu.GpuMonitor(),
        should_stop=should_stop, **options
    )


def resume_selected(kind: str, run_id: str, on_progress=None, should_stop=None, *, fan_quiet: bool = True,
                    monitor=None, clock=None) -> dict:
    """끝나지 않은 local 기록을 같은 run_id 로 이어 잰 결과. run_evaluation.resume 그대로.

    규칙  조건 · 문맥 · 부르는 순간은 기록에 저장된 것을 평가 쪽이 씀. 여기서 넘기지 않음
          팬 소음 억제는 실행 박자라 누른 순간의 화면 값(fan_quiet)을 넘김. 평가 쪽이 이 구간 값으로 기록함
          monitor 는 팬을 보는 자일 뿐임. 없으면 여기서 만듦. 실행 하드웨어는 저장된 것이 없을 때만 이 기계
          clock 은 run_selected 와 같음
    제약  st.* 를 부르지 않는다 (백그라운드 thread 에서 불림)
    """
    from dev.evaluation import run_evaluation
    from dev.evaluation.engine import monitor_gpu

    timing = {}
    if clock is not None:
        timing = {"resolve": clock.timed(run_evaluation.resolve_via_api), "on_start": clock.started}
    return run_evaluation.resume(
        kind, run_id, progress=on_progress, monitor=monitor or monitor_gpu.GpuMonitor(),
        environment=monitor_gpu.environment(), should_stop=should_stop, fan_quiet_mode=fan_quiet, **timing,
    )


def resume_check(kind: str, run_id: str) -> dict:
    """그 기록을 이어 잴 수 있나. run_evaluation.resume_check 그대로 (파일을 안 고치고 Resolve 를 안 부름)."""
    from dev.evaluation import run_evaluation

    return run_evaluation.resume_check(kind, run_id)


NEW, RESUME = "new", "resume"
TITLE_TEXT = "발화 해석 평가"
CONDITIONS_TITLE = "모델 설정 (자세히 보기)"
_TOKENS = itertools.count(1)


class _Job:
    """백그라운드에서 도는 평가 한 번. 화면 script 와 평가 thread 가 나눠 보는 것은 이것뿐.

    규칙  평가 thread 는 add 로 끝난 줄을 넣고, 끝나면 result 또는 error 를 적고 finished 를 켬
          화면은 rows() · stop_requested() · finished · fan_waiting() 만 읽고, 「중지」는 request_stop 으로 알림
          rows 는 이어 실행이면 전에 잰 줄부터 시작함
          fan_quiet 는 이 실행의 팬 소음 억제. 새로 실행 · 이어 실행 둘 다 누른 순간의 체크박스.
          도는 동안 체크박스가 이 값을 보임. monitor 는 평가 thread 에 넘기는 팬 보는 자 (없으면 None)
          도는 동안의 시간(live_times)은 여기서 셈. 평가가 시작 머리를 넘기면(started) 그때부터 벽시계를 새로 재고,
          이어 실행이면 머리의 elapsed_s · fan_wait_s 와 전에 잰 줄의 추론 시간 합을 바탕으로 둠.
          추론 시간은 timed 로 감싼 resolve 가 도는 구간만, 팬 대기는 monitor.live_wait_s 만 셈
    제약  st.* · session_state 를 만지지 않는다. 줄을 채점하지 않는다. 기록에 시간을 적지 않는다 (기록은 평가 쪽 일)
    """

    def __init__(self, mode: str, dataset_id: str, planned: int, rows: list[dict] | None = None,
                 kind: str | None = None, run_id: str | None = None, fan_quiet: bool = True, monitor=None):
        self.token = next(_TOKENS)
        self.mode, self.dataset_id, self.planned = mode, dataset_id, planned
        self.kind, self.run_id = kind, run_id
        self.fan_quiet, self.monitor = bool(fan_quiet), monitor
        self._rows = list(rows or [])
        self.meta: dict | None = None
        self.started_at = datetime.datetime.now(datetime.timezone.utc).astimezone()
        self._t0 = time.monotonic()
        self._base = {"elapsed": 0.0, "inference": 0.0, "fan_wait": 0.0}
        self._inferred = 0.0
        self._inferring_since: float | None = None
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

    def fan_waiting(self) -> bool:
        """지금 팬 때문에 다음 발화를 기다리는 중인가."""
        return bool(getattr(self.monitor, "waiting", False))

    def started(self, head: dict) -> None:
        """평가가 첫 발화 앞에서 넘긴 meta 머리를 받음. 벽시계를 여기서 다시 재기 시작함 (run_evaluation on_start)."""
        done = self.rows()
        with self._lock:
            self.meta = dict(head)
            self._t0 = time.monotonic()
            self._base = {
                "elapsed": float(head.get("elapsed_s") or 0.0),
                "inference": sum(float((r.get("timing") or {}).get("resolve_s") or 0.0) for r in done),
                "fan_wait": float(head.get("fan_wait_s") or 0.0),
            }

    def timed(self, resolve):
        """resolve 를 감싸 부르는 동안을 추론 중으로 셈. 반환값 · 예외는 그대로."""
        def call(*args, **kwargs):
            with self._lock:
                self._inferring_since = time.monotonic()
            try:
                return resolve(*args, **kwargs)
            finally:
                with self._lock:
                    self._inferred += time.monotonic() - self._inferring_since
                    self._inferring_since = None
        return call

    def inferring(self) -> bool:
        """지금 Resolve 를 부르는 중인가."""
        return self._inferring_since is not None

    def live_times(self, now: float | None = None) -> dict:
        """지금 시점의 {"elapsed", "inference", "fan_wait"} 초. 셋 다 이 실행(이어 실행이면 지난 구간 포함)의 누적.

        규칙  elapsed 는 시작 머리를 받은 뒤(또는 job 을 만든 뒤)의 벽시계. inference 는 부르는 중이면 그 몫까지.
              fan_wait 는 monitor.live_wait_s (없으면 waited_s, monitor 가 없으면 0)
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            base, t0 = dict(self._base), self._t0
            inferred = self._inferred + (now - self._inferring_since if self._inferring_since is not None else 0.0)
        live = getattr(self.monitor, "live_wait_s", None)
        waited = live() if callable(live) else float(getattr(self.monitor, "waited_s", 0.0) or 0.0)
        return {"elapsed": base["elapsed"] + (now - t0), "inference": base["inference"] + inferred,
                "fan_wait": base["fan_wait"] + waited}


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


def _new_monitor():
    """팬을 보는 자 하나. 실행 하나에 하나."""
    from dev.evaluation.engine import monitor_gpu

    return monitor_gpu.GpuMonitor()


def _start_new(dataset_id: str) -> None:
    """「새로 실행」의 콜백. 새 Test Run 을 백그라운드로 시작하고 이 창이 지켜봄.

    규칙  잴 수는 고른 정답표의 대기 줄 수. 폴더는 run_evaluation 이 시작하자마자 만듦
          팬 소음 억제는 누른 순간의 체크박스(FAN_QUIET_KEY, 기본 켜짐). 그 값이 이 실행 기록에 굳음
          이미 도는 평가가 있으면 아무것도 안 함
    """
    planned = len(suite_rows(dataset_id))
    fan_quiet = bool(st.session_state.get(FAN_QUIET_KEY, True))
    job = _Job(NEW, dataset_id, planned, fan_quiet=fan_quiet, monitor=_new_monitor())
    if start_job(job, lambda: run_selected(dataset_id, job.add, job.stop_requested, fan_quiet=job.fan_quiet,
                                           monitor=job.monitor, clock=job)):
        _watch(job)


def _start_resume(stored: dict) -> None:
    """「이어 실행」의 콜백. 불러온 끝나지 않은 local 기록을 같은 run_id 로 이어 잼.

    규칙  누른 순간 resume_check 를 다시 봄. 막히면 까닭을 RUN_ERROR_KEY 에 두고 파일을 안 건드림
          잴 수 · 전에 잰 줄은 불러온 결과 그대로
          팬 소음 억제는 누른 순간의 체크박스(FAN_QUIET_KEY). 저장된 meta.fan_quiet_mode 가 덮지 않음
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
    job = _Job(RESUME, stored["dataset_id"], planned, result["cases"], kind=stored["kind"], run_id=run_id,
               fan_quiet=bool(st.session_state.get(FAN_QUIET_KEY, True)), monitor=_new_monitor())
    if start_job(job, lambda: resume_selected(job.kind, job.run_id, job.add, job.stop_requested, fan_quiet=job.fan_quiet,
                                              monitor=job.monitor, clock=job)):
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
    규칙  도는 job 이 있으면 running(중지 전) · stopping(중지 요청됨). 글자에 끝난 수 / 잴 수.
          팬 때문에 다음 발화를 기다리는 중이면 끝에 FAN_WAIT_TEXT
          없으면 불러온 기록으로: 다 쟀으면 complete, 못 다 쟀으면 stopped 와 이어 실행 판정
          불러온 기록이 없으면 idle
    """
    if job is not None and job.active():
        done = len(job.rows())
        if job.stop_requested():
            return {"phase": "stopping", "text": "중지 요청됨 · 현재 발화를 마친 뒤 중지합니다.", "resume": None}
        verb = "이어 실행 중" if job.mode == RESUME else "새로 실행 중"
        waiting = f" · {FAN_WAIT_TEXT}" if job.fan_waiting() else ""
        return {"phase": "running", "text": f"{verb} · {done} / {job.planned}{waiting}", "resume": None}
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
          단추 바로 앞에 「GPU 팬 소음 억제」 체크박스. 기본 켜짐. 도는 동안(running · stopping)은
          눌리지 않고 그 실행의 값(job.fan_quiet)을 보임. 끝난 뒤에도 그 값이 남음 (persist_state="page".
          없으면 도는 동안 fragment 로만 그린 체크박스 값이 끝난 뒤 버려져 기본값(켜짐)으로 돌아감)
    제약  단추 콜백 말고는 평가를 시작하지 않는다
    """
    state = control_state(job, stored)
    phase, check = state["phase"], state["resume"]
    running = phase in ("running", "stopping") and job is not None
    if running:
        st.session_state[FAN_QUIET_KEY] = job.fan_quiet
    else:
        st.session_state.setdefault(FAN_QUIET_KEY, True)
    text, quiet, buttons = st.columns([5.0, 1.6, 1.9], vertical_alignment="center")
    with text:
        badge = ""
        if check is not None:
            ok = check["resumable"]
            badge = f'<span class="tt-resume {"ok" if ok else "no"}">{"이어 실행 가능" if ok else "이어 실행 불가"}</span>'
        st.markdown(
            f'<div class="tt-run tt-run-{phase}"><span class="tt-run-text">{_esc(state["text"])}</span>{badge}</div>',
            unsafe_allow_html=True,
        )
        if running and job.planned:
            st.progress(min(1.0, len(job.rows()) / job.planned))
    with quiet:
        st.checkbox(FAN_QUIET_LABEL, key=FAN_QUIET_KEY, help=FAN_QUIET_HELP, disabled=running, persist_state="page")
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
    """고른 발화 · 표 선택 · 고른 기능 카드를 처음으로. widget 콜백 안에서만 부름.

    규칙  고른 기능(GROUP_KEY)은 지우지 않고 ALL_GROUPS 로 적음
    """
    for key in (SELECTED_KEY, LIST_VIEW_KEY):
        st.session_state.pop(key, None)
    st.session_state[GROUP_KEY] = ALL_GROUPS


def _switch_suite() -> None:
    """Test Suite 고르기의 콜백. 다른 세트의 결과가 남지 않게 지난 결과 · 고른 실행 기록을 지움.

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
          돌려준 결과 한 벌을 RESULT_KEY 에 둠. Test Suite 고르기를 그 기록의 정답표로 맞춤.
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
    """제목 · Test Suite · 실행 기록.

    입력  session_state 의 마지막 실행 {"dataset_id", "result", "kind"}. busy 는 평가가 도는 중인가
    출력  (고른 정답표 id, 고른 정답표의 마지막 결과 또는 None)
    규칙  제목은 「발화 해석 평가」 한 줄. 소제목을 두지 않음 (실행 시각은 실행 개요의 평가 시작 시간)
          Test Suite 를 바꾸면 _switch_suite 가 지난 결과 · 고른 실행 기록을 지움
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
            "Test Suite", list(labels), format_func=labels.get, key=DATASET_KEY, persist_state="page",
            on_change=_switch_suite, disabled=busy,
        )
    with history:
        st.selectbox(
            "실행 기록", [""] + list(saved), format_func=lambda key: saved.get(key, "불러올 기록 고르기"),
            key=SAVED_KEY, on_change=_load_saved, persist_state="page", disabled=busy,
        )
    result = stored.get("result") if stored.get("dataset_id") == dataset_id else None
    with title:
        st.markdown(f'<div class="tt-title">{TITLE_TEXT}</div>', unsafe_allow_html=True)
    return dataset_id, result


def live_record(job: "_Job") -> dict:
    """도는 job 의 개요용 결과 한 벌. {"meta", "summary", "cases", "planned"}.

    규칙  줄 · 합계는 live_result. meta 는 평가가 넘긴 시작 머리(job.meta). 아직 안 넘겼으면 아는 것만
          (Test Suite 는 고른 dataset_id, 평가 시작 시간은 job 을 만든 시각). 모르는 칸은 비워 둠
    제약  값을 지어내지 않는다
    """
    record = live_result(job.rows(), job.planned)
    meta = dict(job.meta or {})
    meta.setdefault("started_at", job.started_at.isoformat())
    meta.setdefault("suite", {"dataset_id": job.dataset_id})
    return {**record, "meta": meta}


def _render_overview(result: dict | None, job: "_Job | None" = None) -> None:
    """실행 개요 한 판. 도는 job 이 있으면 그 실시간 값(live_record · live_times), 없으면 결과. 둘 다 없으면 안 그림."""
    info = overview(live_record(job), job.live_times()) if job is not None else overview(result)
    if info is not None:
        st.markdown(overview_markup(info), unsafe_allow_html=True)


def _pick_group(group: str) -> None:
    """기능별 결과 카드의 콜백. 누른 기능으로 표를 거름. 이미 고른 카드를 다시 누르면 풂 (하나만 고름)."""
    st.session_state[GROUP_KEY] = ALL_GROUPS if st.session_state.get(GROUP_KEY) == group else group


def _render_recipe_summary(result: dict | None, group: str = ALL_GROUPS) -> None:
    """기능별 결과 (접힘). 기능마다 카드 단추 하나, 번호 차례, 범위 밖 발화가 있으면 맨 뒤에 범위 밖. 실패가 있으면 펼침.

    규칙  카드를 누르면 아래 결과 표가 그 기능(범위 밖이면 범위 밖 발화)만 보임. 다시 누르면 풂 (_pick_group).
          보기 필터 · 발화 검색과 따로 걸려 겹친 것만 남음. 고른 카드는 primary 단추라 테두리 · 바탕이 다름
          실패가 하나라도 있으면 붉은 카드, 다 맞았으면 차분한 카드(옆줄만 초록). 색은 key 앞머리(recipe_card_key)로 CSS 가 칠함
          설명은 카드에 마우스를 올리면 뜨는 tooltip 하나. 그 <style>(recipe_card_css)은 _render_body 가 전체 결과와
          한 markdown 에 실음 — 따로 그리면 빈 칸 하나가 펼친 칸 맨 위에 틈을 만듦
    제약  제목은 「기능별 결과」 하나다. 기능 수 · 실패한 기능 수를 제목에 달지 않는다 —
          같은 숫자가 바로 아래 표에 있고, 제목이 길어지면 무엇을 여는 칸인지가 흐려진다.
          「모두 성공」 · 「실패 N」 같은 글자를 두지 않는다 — x/y 가 이미 같은 것을 말한다.
          기능이 마흔 가까이 되므로 성공을 강한 초록으로 칠하지 않는다. 눈에 띄는 쪽은 실패다
    """
    entries = recipe_rows(result)
    if not entries:
        return
    failed = sum(1 for e in entries if e["failed"])
    with st.expander("기능별 결과", expanded=bool(failed)):
        with st.container(key="test_fn_cards"):
            for e in entries:
                st.button(recipe_card_label(e), key=recipe_card_key(e), width="stretch",
                          type="primary" if e["group"] == group else "secondary",
                          on_click=_pick_group, args=(e["group"],))


def _render_conditions(result: dict | None) -> None:
    """모델 설정 (자세히 보기) (접힘). 재현 · 확인에 쓰는 것. provider · 요청 설정 · 호출 상한 · 파일 · 저장 위치.
    결과가 없으면 비어 있다고만. 실행 개요에 이미 있는 모델 이름은 안 되풀이함."""
    with st.expander(CONDITIONS_TITLE, expanded=False):
        conditions = run_conditions(result)
        if conditions is None:
            st.markdown('<div class="tt-empty">새로 실행하거나 기록을 불러오면 표시됩니다.</div>', unsafe_allow_html=True)
        else:
            st.markdown(conditions_markup({**conditions, **run_identity(result)}), unsafe_allow_html=True)


def filter_label(view: str, counts: dict) -> str:
    """보기 필터 pill 글자. 전체 · 실패 · 오류는 「실패  15」, 실패를 가른 셋은 「기능 선택  11/15」.

    규칙  셋은 실패에 딸린 자리라 「실패 ·」를 되풀이하지 않고 단계 이름만. 건수는 실패 수에 대한 몫(share_of_failed)
          건수를 모르면(결과가 없음) 글자만
    """
    stage = next((key for key, text in FAILURE_TEXT.items() if text == view), None)
    name = STAGE_LABELS[stage] if stage else view
    if view not in counts:
        return name
    return f"{name}  {share_of_failed(counts[view], counts[FAILED]) if stage else counts[view]}"


def _render_view_filter(summary: dict | None, rows: list[dict] | None = None) -> str:
    """보기 필터. 표 위에 한 줄. 고른 보기를 돌려줌.

    규칙  결과가 있으면 필터 글자 옆에 그 보기의 건수를 붙임(filter_label). 전체는 표의 줄 수
          보기는 칸 하나다 — 전체 · 실패 다음에 실패를 가른 셋(기능 선택 · 인자 추출 · 범위 밖 처리)이 딸려 붙음.
          고르는 값은 결과 칸 글자(FAILURE_TEXT)와 같고 보이는 글자만 짧음. 실패와 셋을 한 테두리로 묶어
          실패가 머리로 보이게 하는 일은 CSS 가 하고(PARENT_FILTER · FIRST_FAILURE_FILTER), 고르는 뜻 · 건수는 안 바뀜
          오류 줄이 있을 때만 맨 뒤에 오류 보기가 붙음. 실패에 딸리지 않음. 오류가 없어지면 전체로 돌림
          결과가 없으면(대기 줄뿐) 건수를 안 붙임. 대기 줄을 성공 · 실패로 세지 않음
    제약  보기 위해 채점 · 거르는 뜻을 바꾸지 않는다
    """
    rows = rows or []
    counts = {}
    errors = sum(1 for r in rows if errored(r))
    if summary is not None:
        counts = {
            ALL: len(rows),
            FAILED: summary["failed"],
            FAILURE_TEXT["function"]: summary["function"],
            FAILURE_TEXT["input"]: summary["input"],
            FAILURE_TEXT["scope"]: sum(1 for r in rows if failed(r) and r.get("failure_stage") == "scope"),
            ERROR_FILTER: errors,
        }
    options = FILTERS + ((ERROR_FILTER,) if errors else ())
    if st.session_state.get(FILTER_KEY) not in (None, *options):
        st.session_state[FILTER_KEY] = ALL
    with st.container(key="test_filters"):
        view = st.segmented_control(
            "보기",
            options,
            default=ALL,
            required=True,
            format_func=lambda v: filter_label(v, counts),
            key=FILTER_KEY,
            label_visibility="collapsed",
            persist_state="page",
        )
    return view or ALL


def _render_list_controls():
    """결과 표 머리 한 줄. 왼쪽은 「테스트 결과 N건」 자리(비워 둔 칸), 오른쪽은 발화 검색.

    출력  (제목 칸, 검색어). 제목은 거른 뒤에 _render_result_list 가 그 칸에 그림
    규칙  정렬은 여기 없다. 결과 표의 머리글을 눌러 함 (next_sort)
    """
    title, search = st.columns([3.0, 2.0], vertical_alignment="center", gap="small")
    with search:
        query = st.text_input(
            "발화 검색",
            key="test_query",
            placeholder="발화 검색",
            icon=":material/search:",
            label_visibility="collapsed",
            persist_state="page",
        )
    return title, query or ""


def next_sort(current, column: str):
    """머리글 column 을 한 번 눌렀을 때의 다음 정렬. (칸, 방향) 또는 None(기본 차례).

    규칙  다른 칸(또는 정렬 없음)에서 누르면 그 칸 오름차순 -> 다시 누르면 내림차순 -> 다시 누르면 None
          정렬할 수 없는 칸이면 지금 그대로
    """
    if column not in SORT_COLUMNS:
        return current
    if not current or current[0] != column:
        return column, ASCENDING
    return (column, DESCENDING) if current[1] == ASCENDING else None


def current_sort():
    """지금 정렬 상태 (칸, 방향) 또는 None. 모르는 값(옛 창 상태)이면 None."""
    value = st.session_state.get(SORT_KEY)
    if isinstance(value, (tuple, list)) and len(value) == 2 and value[0] in SORT_COLUMNS and value[1] in SORT_ORDERS:
        return tuple(value)
    return None


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
          머리글을 눌러 칸이 골라지면(single-column) 그 칸으로 정렬을 한 단계 돌리고(next_sort → SORT_KEY)
          칸은 버림. 고른 발화는 그대로. 정렬이 바뀌면 표 key 가 바뀌어 새 차례로 다시 붙음
    """
    selection = (st.session_state.get(key) or {}).get("selection") or {}
    cells = selection.get("cells") or []
    columns = selection.get("columns") or []
    if columns and not cells:
        st.session_state[SORT_KEY] = next_sort(current_sort(), columns[0])
        row = ids.index(st.session_state[SELECTED_KEY]) if st.session_state.get(SELECTED_KEY) in ids else 0
    elif cells:
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


def _list_key(view: str, query: str, group: str = ALL_GROUPS, sort: tuple | None = None) -> str:
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


def _list_columns(sort: tuple | None = None) -> dict:
    """결과 목록 표의 칸 폭 · 머리 글자. 넓은 창에서는 표 폭을 따라 늘어남.

    규칙  칸 폭 합은 1280 창의 표 폭(약 750px)에 들어가게 둠. 넘치면 맨 오른쪽 추론 시간 칸이 잘림
          정렬 중인 칸 머리에만 ▲ · ▼ (SORT_MARKS). 칸 머리 도움말은 누르면 정렬된다는 것 (SORT_HELP)

    제약  칸 머리의 설정 메뉴에서 정렬 · 통계 · 자동 너비 · 칸 고정을 여기서 못 끈다.
          Streamlit 1.62 의 column_config 에 그 칸이 없다 — panel_css 가 감춘다
    """
    widths = {"번호": 64, "기능": 80, "발화": 320, "결과": 128, "추론 시간": 96}

    def label(name):
        return f"{name} {SORT_MARKS[sort[1]]}" if sort and sort[0] == name else name

    return {name: st.column_config.TextColumn(label(name), width=width, help=SORT_HELP) for name, width in widths.items()}


def _render_result_list(shown: list[dict], view: str, query: str, height: int, *, group: str = ALL_GROUPS,
                        sort: tuple | None = None, title=None) -> dict | None:
    """결과 목록. 한 발화 한 줄, 고정 높이 안에서 스크롤.

    입력  shown 은 거른 줄. 여기서 sort_rows 로 세워 그림. title 은 「테스트 결과 N건」을 그릴 칸 (없으면 여기)
    출력  지금 고른 결과 줄. 목록이 비었으면 None
    규칙  행 고르기는 st.dataframe 의 행 선택. 발화 글자를 눌러도 골라지게 칸 선택을
          함께 켜고, 칸을 누르면 _keep_row_selected 가 그 줄 선택으로 바꿈
          칸 고르기(single-column)도 켬. 켜면 st.dataframe 의 머리글 정렬이 꺼짐 (Streamlit 1.62).
          머리글을 눌러 칸이 골라지면 _keep_row_selected 가 정렬(SORT_KEY)을 돌림. 줄은 파이썬 한 곳(sort_rows)만 세움
          sort 가 None 이면 기본 차례(번호 오름차순)
          표 key 는 _list_key 가 정함. 같은 보기 안에서 행을 눌러도 표가 새로 안 붙으므로
          스크롤 자리가 그대로임
          보기를 바꾸면 고른 발화가 새 목록에 있으면 그 줄, 없으면 첫 실패 줄, 실패가 없으면 첫 줄을 고름
          표는 늘 고른 정답표의 발화 전부(대기 줄 포함)에서 거른 것. 비는 것은 거른 결과가 없을 때뿐
    제약  single-row-required 를 쓰지 않는다.
          칸을 누르면 행 선택이 비었다고 보고 첫 줄로 되돌림. 발화를 눌렀는데 001 이 뜸
    """
    picked_group = ""
    if group != ALL_GROUPS:
        name = OUT_OF_SCOPE_TEXT if group == OUT_OF_SCOPE_GROUP else function_label(group)
        picked_group = f'<span class="tt-pane-group">{_esc(name)}</span>'
    with title if title is not None else st.container():
        st.markdown(
            f'<div class="tt-pane-title">테스트 결과 <span>{len(shown)}건</span>{picked_group}</div>',
            unsafe_allow_html=True,
        )
    if not shown:
        with st.container(height=height, border=True):
            st.markdown('<div class="tt-empty">조건에 맞는 발화가 없습니다.</div>', unsafe_allow_html=True)
        return None

    shown = sort_rows(shown, *sort) if sort else sort_rows(shown)
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
        column_config=_list_columns(sort),
    )

    rows = event.selection.rows if event is not None else []
    picked = rows[0] if rows and 0 <= rows[0] < len(shown) else default
    st.session_state[SELECTED_KEY] = shown[picked]["case_id"]
    return shown[picked]


def _render_result_detail(row: dict | None, functions: dict, height: int) -> None:
    """선택한 발화 상세. 고정 높이 안에서 스크롤."""
    st.markdown('<div class="tt-pane-title tt-pane-detail">선택한 발화 상세</div>', unsafe_allow_html=True)
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
    """실행 개요 · 모델 설정 · 실행 제어 · 알림 · 전체 결과 · 기능별 결과 · 보기 필터 · 결과 목록 · 상세.
    도는 동안 fragment 로 스스로 다시 그려짐 (실행 개요의 시간이 1초마다 늘어나는 까닭).

    입력  result 는 고른 정답표의 마지막 결과(불러온 기록 포함). 도는 동안에는 안 봄
    규칙  도는 job 이 있으면 표 · 요약은 job.rows() (끝난 줄만. 이어 실행이면 전에 잰 줄 포함) 를 대기 줄 위에 얹은 것
          job 이 끝난 것을 보면 화면 전체를 다시 그려 결과를 받아 옴(_absorb)
          고른 기능(GROUP_KEY)은 기능별 결과 카드가 보일 때만 표에 걸림. 도는 동안 · 표에 없는 기능이면 전체
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

    _render_overview(result, job if busy else None)
    _render_conditions({"meta": job.meta} if busy and job.meta else None if busy else result)
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
    card_css = "" if busy else recipe_card_css(recipe_rows(result), functions)
    st.markdown(summary_markup(summary) + card_css, unsafe_allow_html=True)
    rows = table_rows(suite_rows(dataset_id), done_rows)
    group = st.session_state.get(GROUP_KEY) or ALL_GROUPS
    if busy or group not in group_options(rows):
        group = ALL_GROUPS
    if not busy:
        _render_recipe_summary(result, group)
    view = _render_view_filter(summary, rows)

    height = list_height(ratios)
    left, right = st.columns([63, 37], gap="medium")
    with left:
        title, query = _render_list_controls()
        sort = current_sort()
        shown = filter_results(rows, view, query, group)
        selected = _render_result_list(shown, view, query, height, group=group, sort=sort, title=title)
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
          실행 개요는 도는 동안에도 보임 (그 job 의 실시간 값). 기능별 결과는 결과가 있고 도는 중이 아닐 때만
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
        st.fragment(_render_body, run_every=POLL_SECONDS if busy else None)(ratios, dataset_id, shown)


# ================================================================ CSS
def panel_css() -> str:
    """테스트 탭 전용 CSS. .st-key-test_tab 안에만 걸림.

    규칙  글자색은 테마를 따름(inherit). 선 · 바탕은 회색 반투명이라 밝은 테마 · 어두운
          테마 어느 쪽에서도 읽힘. 성공 · 실패 · AI 모델 출력 강조색만 고정
          보기 필터의 칸 번호는 PARENT_FILTER · FIRST_FAILURE_FILTER · FILTERS 에서 옴. CSS 에 숫자를 박지 않음
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
.st-key-test_tab .tt-title { font-size: 1.35rem; font-weight: 700; line-height: 1.3; padding-bottom: 0.35rem; }

/* ---------------------------------------------- 실행 개요
   상자는 탭 폭을 다 쓰고, 안은 열 다섯(OVERVIEW_COLUMNS)의 grid 다. 열 사이 가는 세로선이 섹션 묶음의 경계다.
   열 폭은 최소 폭 + 비율이라 넓은 창에서 고르게 늘고, 실행 환경(긴 GPU 이름) 열이 가장 넓다.
   섹션 안은 글자 | 값 두 칸 grid 라 값이 열 오른쪽 끝으로 멀리 밀려나지 않는다.
   창이 좁으면(1200px 이하) 열이 15rem 이상 폭으로 다음 줄에 넘어가고, 세로선은 뺀다. 긴 실행 환경 열은 두 칸을 쓴다. */
.st-key-test_tab .tt-ovs {
  display: grid; width: 100%; box-sizing: border-box;
  grid-template-columns: minmax(11rem, 1fr) minmax(15.5rem, 1.25fr) minmax(10rem, 0.9fr) minmax(8rem, 0.75fr) minmax(16rem, 1.6fr);
  font-size: 0.82rem; padding: 0.7rem 0.2rem;
  border: 1px solid var(--tt-line); border-radius: 10px; background: var(--tt-softer);
}
.st-key-test_tab .tt-ovc {
  min-width: 0; padding: 0 1.1rem; border-left: 1px solid var(--tt-line);
  display: flex; flex-direction: column; gap: 0.55rem;
}
.st-key-test_tab .tt-ovc:first-child { border-left: 0; }
@media (max-width: 1200px) {
  .st-key-test_tab .tt-ovs { grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); row-gap: 0.8rem; }
  .st-key-test_tab .tt-ovc { border-left: 0; }
  .st-key-test_tab .tt-ovc:last-child { grid-column: span 2; }
}
@media (max-width: 700px) {
  .st-key-test_tab .tt-ovc:last-child { grid-column: auto; }
}
.st-key-test_tab .tt-ov { min-width: 0; }
.st-key-test_tab .tt-ov-rows {
  display: grid; grid-template-columns: max-content minmax(0, max-content); column-gap: 1.1rem; line-height: 1.55;
}
.st-key-test_tab .tt-ov-row { display: contents; }
/* 도움말이 있는 줄은 글자 뒤 작은 「?」 아이콘(GPU 팬 소음 억제 옆 아이콘과 같은 모양)에만 tooltip 이 붙는다.
   tooltip 은 아이콘 아래 고정 폭으로 떠서 오른쪽 값을 덮어도 되고, 칸 폭을 넓히지 않는다. */
.st-key-test_tab .tt-help {
  position: relative; display: inline-flex; align-items: center; justify-content: center; vertical-align: 0.05rem;
  width: 0.85rem; height: 0.85rem; margin-left: 0.3rem; border: 1px solid currentColor; border-radius: 50%;
  font-size: 0.6rem; font-weight: 700; line-height: 1; color: rgba(140, 150, 165, 0.95);
}
/* 흐리게 하는 데 opacity 를 쓰지 않는다 — opacity 는 쌓임 맥락을 만들어 tooltip 까지 비치고 아래 줄 뒤로 깔린다.
   그래서 아이콘은 흐린 줄 글자(.tt-ov-sub) 밖에 둔다 */
.st-key-test_tab .tt-help:hover { color: inherit; }
.st-key-test_tab .tt-help[data-tip]::after { left: -0.2rem; right: auto; top: 100%; width: 18rem; }
.st-key-test_tab .tt-ov-k {
  opacity: 0.6; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em; margin-bottom: 0.2rem;
}
.st-key-test_tab .tt-ov-label { white-space: nowrap; }
.st-key-test_tab .tt-ov-sub { opacity: 0.65; }
.st-key-test_tab .tt-ov-v { font-weight: 600; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; text-align: right; }
.st-key-test_tab .tt-ov-row > .tt-ov-v:only-child { grid-column: 1 / -1; text-align: left; }
.st-key-test_tab .tt-sum-title { font-size: 0.85rem; font-weight: 600; opacity: 0.85; margin: 0.2rem 0 0.45rem; }

/* ---------------------------------------------- 기능별 결과
   기능마다 카드 단추 하나(recipe_card_key). 카드 사이 gap 으로 경계를 긋는다 (줄이 이어 붙으면 어디까지가 한
   기능인지가 흐려진다). 기능이 마흔 가까이 되므로 성공은 옆줄만 초록으로 차분히 두고,
   배경을 칠하는 것은 실패뿐이다 — 전부 초록이면 붉은 것이 안 보인다.
   고른 카드는 primary 단추다. 테마의 채운 단추 대신 청록 테두리 두 겹과 옅은 바탕으로 칠해 실패 색이 그대로 보이게 한다. */
.st-key-test_tab .st-key-test_fn_cards {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(8.6rem, 1fr)); gap: 0.45rem;
}
.st-key-test_tab .st-key-test_fn_cards > div { width: auto; min-width: 0; }
.st-key-test_tab .st-key-test_fn_cards button {
  position: relative; min-height: 0; padding: 0.28rem 0.65rem; border-radius: 8px; justify-content: stretch;
  color: inherit; border: 1px solid var(--tt-line); background: var(--tt-softer);
}
.st-key-test_tab .st-key-test_fn_cards button > div,
.st-key-test_tab .st-key-test_fn_cards button > div > span,
.st-key-test_tab .st-key-test_fn_cards button [data-testid="stMarkdownContainer"] { width: 100%; }
.st-key-test_tab .st-key-test_fn_cards button p {
  display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem;
  margin: 0; font-size: 0.8rem; white-space: nowrap;
}
.st-key-test_tab .st-key-test_fn_cards button strong { font-variant-numeric: tabular-nums; font-weight: 600; }
.st-key-test_tab .st-key-test_fn_cards button:hover { border-color: rgba(20, 184, 166, 0.6); color: inherit; }
.st-key-test_tab [class*="st-key-test_fn_ok_"] button { box-shadow: inset 3px 0 0 var(--tt-ok); }
.st-key-test_tab [class*="st-key-test_fn_ok_"] button strong { color: var(--tt-ok); }
.st-key-test_tab [class*="st-key-test_fn_ng_"] button {
  background: rgba(229, 83, 75, 0.1); border-color: rgba(229, 83, 75, 0.45); box-shadow: inset 3px 0 0 var(--tt-ng);
}
.st-key-test_tab [class*="st-key-test_fn_ng_"] button strong { color: var(--tt-ng); font-weight: 700; }
.st-key-test_tab .st-key-test_fn_cards button[data-testid="stBaseButton-primary"] {
  border-color: var(--tt-ai); background: rgba(20, 184, 166, 0.16);
}
.st-key-test_tab [class*="st-key-test_fn_ok_"] button[data-testid="stBaseButton-primary"] {
  box-shadow: inset 3px 0 0 var(--tt-ok), 0 0 0 1px var(--tt-ai);
}
.st-key-test_tab [class*="st-key-test_fn_ng_"] button[data-testid="stBaseButton-primary"] {
  background: rgba(229, 83, 75, 0.2); box-shadow: inset 3px 0 0 var(--tt-ng), 0 0 0 1px var(--tt-ai);
}
.st-key-test_tab .st-key-test_fn_cards button[data-testid="stBaseButton-primary"] p { font-weight: 700; }

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

/* ---------------------------------------------- 요약 카드
   낮은 카드 한 줄. 숫자 옆에 작은 글자를 붙여 세로 칸을 줄인다. 실패 카드만 넓고, 실패를 가른 셋은
   실패 수 오른쪽에 세로선으로 매단다 — 전체 · 성공 · 실패와 같은 층으로 보이면 안 된다.
   같은 설명을 셋에 되풀이하지 않고 묶음에 한 번만 적는다. 좁으면 카드가 다음 줄로 넘어간다. */
.st-key-test_tab .tt-kpis { display: flex; flex-wrap: wrap; gap: 0.6rem; }
.st-key-test_tab .tt-kpi {
  flex: 1 1 8rem; min-width: 0;
  border: 1px solid var(--tt-line); border-radius: 10px; background: var(--tt-softer);
  padding: 0.4rem 0.85rem; display: flex; align-items: center; gap: 1.1rem;
}
.st-key-test_tab .tt-kpi-main { display: flex; flex-direction: column; flex: 0 0 auto; }
.st-key-test_tab .tt-kpi-label { font-size: 0.76rem; opacity: 0.7; line-height: 1.3; }
.st-key-test_tab .tt-kpi-line { display: flex; align-items: baseline; gap: 0.45rem; }
.st-key-test_tab .tt-kpi-num { font-size: 1.45rem; font-weight: 700; line-height: 1.2; font-variant-numeric: tabular-nums; }
.st-key-test_tab .tt-kpi-note { font-size: 0.74rem; opacity: 0.6; white-space: nowrap; }
.st-key-test_tab .tt-kpi.ok { box-shadow: inset 3px 0 0 var(--tt-ok); }
.st-key-test_tab .tt-kpi.ok .tt-kpi-num { color: var(--tt-ok); }
.st-key-test_tab .tt-kpi.ng { box-shadow: inset 3px 0 0 var(--tt-ng); }
.st-key-test_tab .tt-kpi.ng .tt-kpi-num { color: var(--tt-ng); }
.st-key-test_tab .tt-kpi.err { box-shadow: inset 3px 0 0 var(--tt-err); }
.st-key-test_tab .tt-kpi.err .tt-kpi-num { color: var(--tt-err); }
.st-key-test_tab .tt-kpi.tt-kpi-split { flex: 2.2 1 19rem; }
.st-key-test_tab .tt-causes {
  flex: 1 1 auto; min-width: 0; padding: 0.05rem 0 0.05rem 0.85rem;
  border-left: 2px solid rgba(229, 83, 75, 0.35);
}
.st-key-test_tab .tt-causes-head { font-size: 0.68rem; opacity: 0.5; line-height: 1.35; }
.st-key-test_tab .tt-cause { display: flex; align-items: baseline; gap: 0.5rem; font-size: 0.78rem; line-height: 1.45; }
.st-key-test_tab .tt-cause-k { opacity: 0.75; min-width: 5.6rem; }
.st-key-test_tab .tt-cause-k::before {
  content: ""; display: inline-block; width: 0.3rem; height: 0.3rem; border-radius: 50%;
  background: var(--tt-ng); opacity: 0.7; margin-right: 0.35rem; vertical-align: 0.1rem;
}
.st-key-test_tab .tt-cause-v { font-weight: 700; font-variant-numeric: tabular-nums; color: rgba(229, 83, 75, 0.95); }
.st-key-test_tab .tt-cause-note { font-size: 0.72rem; opacity: 0.5; }
.st-key-test_tab .tt-kpis-empty .tt-cause-v { opacity: 0.35; color: inherit; }

/* 보기 필터. 붙은 막대(segmented)가 아니라 떨어진 pill 로 둔다.
   전체는 홀로 서고, 실패({parent_filter} 번째)와 실패를 가른 셋({first_failure_filter}~{last_failure_filter} 번째)은
   붉은 테두리 한 칸 안에 함께 든다 — 그 칸이 「실패 = 셋의 합」이라는 묶음이다. 실패는 칸 맨 앞에서
   붉은 글자 · 테두리 · 굵은 글자로 서고 뒤에 세로선, 셋은 한 단계 작고 낮은 pill 로 바탕 없이 옅게 선다.
   고르지 않은 상태에서는 바탕을 칠하지 않는다 — 칠하면 이미 고른 것처럼 보인다. 고른 pill(aria-checked)만
   붉은 바탕 · 흰 글자로 꽉 채운다. 실패 · 셋 · 오류 모두 같은 규칙이다.
   셋의 글자는 「기능 선택  11/15」 — 실패 수에 대한 몫이라 묶음 이름을 따로 달지 않는다.
   칸은 radiogroup 을 grid 로 두고 그 ::before 를 grid 칸 {parent_filter} ~ {last_failure_filter} 뒤에 깔아 그린다. pill 은 제 칸에 박는다
   (자동 배치면 ::before 가 첫 칸을 먹는다). 한 줄이라 높이가 안 는다.
   오류 보기(있을 때만 맨 뒤)는 실패에 딸리지 않으므로 칸 밖에 황색으로 둔다. 고르는 뜻은 그대로다. */
.st-key-test_tab .st-key-test_filter [role="radiogroup"] {
  display: grid; grid-auto-flow: column; grid-auto-columns: max-content; justify-content: start;
  align-items: center; column-gap: 0.35rem;
}
.st-key-test_tab .st-key-test_filter [role="radiogroup"]::before {
  content: ""; grid-row: 1; grid-column: {parent_filter} / {group_end}; align-self: stretch;
  border: 1px solid rgba(229, 83, 75, 0.42); border-radius: 12px; background: rgba(229, 83, 75, 0.045);
}
{placements}
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"] {
  border-radius: 999px; margin: 0.22rem 0; position: relative; padding-left: 0.8rem; padding-right: 0.8rem;
}
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type(1) { margin-right: 0.45rem; }
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type({parent_filter}) {
  margin-left: 0.3rem; margin-right: 0.6rem;
  color: var(--tt-ng); border: 1px solid rgba(229, 83, 75, 0.65); background: transparent;
}
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type({parent_filter}) p { font-weight: 700; }
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type({parent_filter})::after {
  content: ""; position: absolute; right: -0.48rem; top: 18%; bottom: 18%; width: 1px; background: rgba(229, 83, 75, 0.45);
}
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type(n+{first_failure_filter}):nth-of-type(-n+{last_failure_filter}) {
  color: rgba(229, 83, 75, 0.8); border-color: rgba(229, 83, 75, 0.22); background: transparent;
  min-height: 1.85rem; padding: 0 0.6rem;
}
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type(n+{first_failure_filter}):nth-of-type(-n+{last_failure_filter}) p {
  font-size: 0.78rem;
}
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type({last_failure_filter}) { margin-right: 0.3rem; }
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type(n+{parent_filter}):nth-of-type(-n+{last_failure_filter})[aria-checked="true"] {
  color: #FFFFFF; border-color: var(--tt-ng); background: var(--tt-ng);
}
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type({error_filter}) {
  margin-left: 0.45rem; color: var(--tt-err); border-color: rgba(210, 153, 34, 0.45); font-size: 0.84rem;
}
.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type({error_filter})[aria-checked="true"] {
  color: #FFFFFF; border-color: var(--tt-err); background: var(--tt-err);
}
/* 필터 칸이 좁으면(창이 좁을 때) 한 줄 grid 가 옆 칸을 덮는다. 그때는 묶음 칸만 두 줄이 된다 —
   실패는 칸 왼쪽에 세로 가운데로 서고, 셋은 그 오른쪽에 두 줄로 든다. 오류는 첫 줄 맨 뒤다. */
.st-key-test_tab .st-key-test_filters { container: tt-filter / inline-size; }
@container tt-filter (max-width: {narrow_filter}px) {
  .st-key-test_tab .st-key-test_filter [role="radiogroup"]::before { grid-row: 1 / 3; grid-column: {parent_filter} / {narrow_end}; }
  .st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type({parent_filter}) { grid-row: 1 / 3; }
{narrow_placements}
}

/* 팬 소음 억제 체크박스는 단추 바로 옆에 붙인다. */
.st-key-test_tab .st-key-test_fan_quiet { align-self: flex-end; }

/* 결과 표 칸 머리의 「설정」 메뉴. 정렬 · 통계 · 자동 너비 · 칸 고정 명령을 감춘다.
   st.dataframe 자체의 머리글 정렬은 칸 고르기(single-column)를 켜서 꺼 두었다 — 머리글을 누르면 칸이 골라지고
   그것을 _keep_row_selected 가 파이썬 정렬(sort_rows)로 바꾼다.
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
.st-key-test_tab .tt-pane-title { font-size: 0.85rem; font-weight: 600; opacity: 0.85; white-space: nowrap; }
.st-key-test_tab .tt-pane-title span { font-weight: 400; opacity: 0.65; margin-left: 0.3rem; }
.st-key-test_tab .tt-pane-title .tt-pane-group {
  font-size: 0.74rem; font-weight: 600; opacity: 1; color: var(--tt-ai);
  padding: 0.05rem 0.5rem; border: 1px solid rgba(20, 184, 166, 0.55); border-radius: 999px; margin-left: 0.5rem;
}
/* 상세 제목은 옆 칸의 검색 · 정렬 줄과 높이를 맞춰 두 칸의 테두리가 같은 줄에서 시작하게 한다. */
.st-key-test_tab .tt-pane-detail { min-height: 2.5rem; display: flex; align-items: center; margin-bottom: 1rem; }
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
/* overflow 를 가리지 않는다. 기능 번호 tooltip 이 표 아래로 넘쳐도 잘리지 않게 하려는 것이라
   둥근 모서리는 모서리 칸에 따로 준다. */
.st-key-test_tab .tt-cmp {
  border: 1px solid var(--tt-line); border-radius: 10px; font-size: 0.88rem;
}
.st-key-test_tab .tt-cmp > .tt-row:first-child > :last-child { border-top-right-radius: 9px; }
.st-key-test_tab .tt-cmp > .tt-row:last-child > :first-child { border-bottom-left-radius: 9px; }
.st-key-test_tab .tt-cmp > .tt-row:last-child > :last-child { border-bottom-right-radius: 9px; }
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
.st-key-test_tab .tt-fn .tt-chip { font-weight: 600; }
.st-key-test_tab .tt-fns { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.st-key-test_tab .tt-desc { font-size: 0.8rem; opacity: 0.72; line-height: 1.45; margin-top: 0.2rem; }
.st-key-test_tab .tt-none { opacity: 0.45; }
.st-key-test_tab .tt-diff { background: rgba(229, 83, 75, 0.13); box-shadow: inset 3px 0 0 var(--tt-ng); }
.st-key-test_tab .tt-diff .tt-val, .st-key-test_tab .tt-diff .tt-fn { color: var(--tt-ng); font-weight: 700; opacity: 1; }
.st-key-test_tab .tt-ungraded .tt-answer, .st-key-test_tab .tt-ungraded .tt-model { opacity: 0.7; }
.st-key-test_tab .tt-tag {
  position: absolute; top: 0.45rem; right: 0.5rem;
  font-size: 0.66rem; font-weight: 600; padding: 0.05rem 0.4rem; border-radius: 999px;
}
.st-key-test_tab .tt-tag-fail { color: var(--tt-ng); border: 1px solid rgba(229, 83, 75, 0.5); }
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
.st-key-test_tab .tt-kv-v { min-width: 0; display: flex; flex-wrap: wrap; gap: 0.3rem; position: relative; }
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

/* ---------------------------------------------- 기능 번호 tooltip
   브라우저 title 은 뜨기까지 지연을 못 바꿔서 data-tip 을 여기서 그린다. 올리면 {tip_delay}ms 뒤에
   뜨고, 내리면 바로 사라진다. tooltip 은 마우스를 안 받으므로 그 위로 지나가도 깜빡이지 않는다.
   가로는 번호가 든 칸(.tt-c · .tt-kv-v)의 폭에 맞추고, 세로는 번호가 놓인 줄 바로 아래다
   (top 을 비워 두면 제자리 다음 줄). 칸 밖으로 넘치면 상세의 스크롤 칸이 가로로 밀린다.
   기능별 결과 카드는 단추라 data-tip 을 못 받는다. 같은 모양을 카드 단추의 ::after 로 그리고
   글자(content)만 카드 key 마다 recipe_card_css 가 붙인다. 카드 어디에 올려도 뜨고, 카드 바로 아래다. */
.st-key-test_tab [data-tip] { cursor: help; }
.st-key-test_tab [data-tip]::after { content: attr(data-tip); }
.st-key-test_tab .st-key-test_fn_cards button::after { top: 100%; text-align: left; }
.st-key-test_tab [data-tip]::after,
.st-key-test_tab .st-key-test_fn_cards button::after {
  position: absolute; display: block; left: 0.4rem; right: 0.4rem; margin-top: 0.3rem; z-index: 30;
  padding: 0.4rem 0.6rem; border-radius: 6px;
  font-size: 0.78rem; font-weight: 400; line-height: 1.45; letter-spacing: normal;
  white-space: normal; text-align: left; overflow-wrap: anywhere;
  color: #F3F5F8; background: rgba(30, 34, 42, 0.96); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.22);
  opacity: 0; visibility: hidden; pointer-events: none; transition: none;
}
.st-key-test_tab [data-tip]:hover::after,
.st-key-test_tab .st-key-test_fn_cards button:hover::after {
  opacity: 1; visibility: visible;
  transition: opacity 80ms ease {tip_delay}ms, visibility 0s linear {tip_delay}ms;
}
</style>""".replace("{placements}", _filter_placements()) \
        .replace("{first_failure_filter}", str(FIRST_FAILURE_FILTER)).replace("{error_filter}", str(len(FILTERS) + 1)) \
        .replace("{narrow_placements}", _filter_placements(narrow=True)).replace("{narrow_filter}", str(NARROW_FILTER_PX)) \
        .replace("{narrow_end}", str(PARENT_FILTER + 3)) \
        .replace("{parent_filter}", str(PARENT_FILTER)).replace("{group_end}", str(len(FILTERS) + 1)) \
        .replace("{last_failure_filter}", str(len(FILTERS))) \
        .replace("{tip_delay}", str(TIP_DELAY_MS))


def _filter_placements(narrow: bool = False) -> str:
    """보기 필터 pill 마다 grid 칸 자리 (오류 보기 자리까지).

    규칙  넓으면 n 번째 pill 을 첫 줄 n 번째 칸에
          narrow 면 실패를 가른 셋만 실패 오른쪽 두 칸에 두 줄로 (차례대로 가로 먼저), 오류는 그 뒤 첫 줄
    """
    rule = '.st-key-test_tab .st-key-test_filter button[data-variant="segmented_control"]:nth-of-type({n}) {{ {place} }}'
    if not narrow:
        return "\n".join(rule.format(n=n, place=f"grid-row: 1; grid-column: {n};") for n in range(1, len(FILTERS) + 2))
    lines = [
        rule.format(n=FIRST_FAILURE_FILTER + i, place=f"grid-row: {i // 2 + 1}; grid-column: {PARENT_FILTER + 1 + i % 2};")
        for i in range(len(FAILURE_FILTERS))
    ]
    lines.append(rule.format(n=len(FILTERS) + 1, place=f"grid-row: 1; grid-column: {PARENT_FILTER + 3};"))
    return "\n".join(lines)
