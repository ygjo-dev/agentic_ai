"""정답표 발화가 지금 온톨로지에서 통하는지 재는 도구.

살아 있는 recipe 마다 대표 발화를 한 줄씩 두고, 그 발화를 `/resolve` 에 넣어
LLM 이 그 recipe 를 고르는지 잰다. 「이 recipe 를 어떤 말로도 못 부른다」를
드러내는 것이 이 자의 일이다.

**GT 는 사람이 쥔 잠정 benchmark 다.** 무엇이 정답인지는 표를 보고 사람이
정한다. 온톨로지나 menu 가 바뀌면 다시 재고 다시 정한다.

**시연 자(dev/tools/check_demo.py)와 다른 자다.** 저쪽은 그날 실제로 할 말이
하나의 recipe 로 SELECT 되는지를 재므로 같은 recipe 가 여러 줄에 걸린다.
이쪽은 recipe 하나에 발화 하나여야 커버리지를 볼 수 있다.

    python dev/tools/check_resolve.py                   전체 정답표 (기본 5회)
    python dev/tools/check_resolve.py --runs 3          회차만 바꿔
    python dev/tools/check_resolve.py --only 2,4        고친 발화만 다시
    python dev/tools/check_resolve.py --context bbox    실행에 실을 문맥을 우클릭 전 모양으로
    python dev/tools/check_resolve.py --execute         ★ 실행까지 부른다. 실행 칸 표가 하나 더 나온다

정답표(발화 · 기대 recipe · 이름 있는 값 · 표시 · 묶음)는 `dev/evaluation/resolve_regression.yaml`
이고 읽는 곳은 `dev/evaluation/suite.py` 다. 같은 정답표를 JSON 결과 한 벌로 재는 공통 runner 는
`dev/evaluation/runner.py` 다.

## 한 번 눌러본 것은 근거가 안 된다

같은 발화가 두 번 다르게 나올 수 있다. LLM 이 고르는 자리라 한 판으로는 그것이
실력인지 운인지 갈리지 않는다. 그래서 발화마다 `--runs` 만큼 돌려 무엇이
나왔는지 표로 찍는다. 표를 보고 사람이 발화를 고치고, 다시 돌리고, 확정한다.

## 두 가지를 잰다 — 고르기와 실행

    /resolve 만 부른다   「경로를 맞게 골랐는가」. 평소 쓰는 길이고 빠르다
    --execute            ★ 「그 recipe 가 답을 내놓는가」. 가끔 돌려 실행 칸을 갱신한다

**둘의 뜻이 다르다.** 고른 recipe 는 맞는데 그것을 부른 결과가 0건일 수 있다 —
화면에는 "찾지 못했습니다" 가 뜨는데 경로만 재는 표는 그 자리를 「다 잘 된다」로
읽는다.

**실행 칸을 관문으로 삼지 않는다.** Gateway 쪽 데이터가 늘면 건수가 바뀌고
Gateway 가 꺼지면 전부 실패한다. 적중 판정은 이 칸을 안 본다 — recipe 를 맞게
골랐는가와 Gateway 에 그 데이터가 있는가는 다른 문제다.

## 화면과 같은 경로를 부른다

POST /resolve 를 부른다. 화면이 지나는 것과 같은 경로여야 표를 믿을 수 있다.
서버(uvicorn)가 떠 있어야 하고, `--execute` 는 POST /chat/stream 까지 간다.

## 「지도 문맥」 옵션 — `--execute` 에만 걸린다

★ **`--context` 는 고르기 점수에 관여하지 않는다.** recipe 선택은 발화와 menu
원문만 보므로 `/resolve` 는 문맥을 아예 받지 않는다. 그 값이 실리는 곳은
`--execute` 의 `/chat/stream` 뿐이다.

    none   안 보낸다. 화면 문맥을 읽는 recipe 는 실행 전에 막힌다
    bbox   보이는 범위만. KRRI_ASAP 평상시(우클릭 전)와 같은 모양
    both   보이는 범위 + 찍은 지점. **기본값이다.** 우클릭을 한 뒤와 같은 모양

**문맥이 없다고 후보를 뒤에서 걸러내지 않는다.** 문맥은 고르기 조건이 아니라
실행 전제다. 배선이 `$context` 를 읽는 recipe 는 값이 없으면 실행 단계에서
막히고, 고른 결과 자체는 그대로 남는다.

## 세 묶음 — 말한 것과 찍은 지점과 보이는 범위를 갈라 찍는다

정답표 발화를 **한 백분율로 합치지 않는다.** 묶는 기준은 그 발화가 닿는 데
무엇이 있어야 하는가, 곧 **시작 데이터**이고 그것이 곧 **잴 수 있는 조건**이다.

    말한 것        발화만으로 닿는다                     group: spoken
    찍은 지점      실행에 우클릭한 지점이 있어야 닿는다   group: picked_point
    보이는 범위    실행에 보고 있는 화면이 있어야 닿는다  group: view_extent
    합계           셋을 더한 값도 내지만 묶음 값이 그 위에 따로 보인다

★ **묶음은 정답표의 각 발화 group 이 갖는다** (dev/evaluation/resolve_regression.yaml).
여기 숫자를 다시 적으면 발화가 늘 때마다 두 곳이 어긋난다.

**묶음의 점수를 서로 견주지 않는다.** 발화가 다르므로 다른 자다. 한쪽만
돌리려면 `--only` 에 번호를 적는다 — 묶음을 고르는 옵션은 따로 안 만들었다.

★ **정답표는 recipe 하나에 발화 하나다.** 살아 있는 recipe 마다 한 줄이 있고
빠진 recipe 는 없다. 이 1대1 이 깨지면 「이 recipe 를 어떤 말로도 못 부른다」를
자가 못 본다.

각 발화에 **표시** 한 칸이 붙는다 (`겹침` · `-`). 낮은 점수가 무엇 때문인지
표에서 바로 읽으라고 둔 칸이고 판정에는 영향이 없다. 뜻은 `MARKS` 옆 주석에
있다.

## 표 세 장과 시간 줄

적중 표 · 인자 표 · 후보 표를 찍고 그 아래 시간 줄을 낸다. `--execute` 를
붙이면 실행 칸 표가 한 장 더 나온다.

recipe 가 맞았는데 실행이 엉뚱한 것을 조회하면 인자 표에서 갈린다 — 발화에서
뽑은 인자(argument)가 흔들린 것이다. 후보 표는 모델을 바꿔 잰 두 판을 견주는
데 쓴다. 후보 수가 줄면 모델이 문장을 읽어 가른 것이고, 그대로면 문장으로는
못 가르는 것이라 손볼 곳이 모델이 아니라 menu 문장이다.

시간 줄은 `/resolve` 한 번의 평균이고 묶음마다 한 줄이다. **이 도구가 잰
값이다** — 요청 직전과 직후의 perf_counter 차이라 네트워크와 서버 시간이 함께
들어 있다. 서버가 무엇에 시간을 썼는지는 안 가른다.

## 적중 표의 네 칸 — 「빗나감」을 지우지 말 것

적중 표는 틀린 것을 셋으로 가른다. **넷을 더하면 시행 횟수가 된다.**

    적중     set(후보) == 기대값
    근접     정답이 후보 안에 남아 있는데 하나로 못 좁혔다 (CLARIFY).
             사람이 고르면 되는 상태다
    빗나감   정답이 후보에 아예 없다.  ★ 제일 나쁘다
    못 붙음  NO_MATCH · 후보가 빔 · 호출 오류

**왜 「빗나감」이 제일 나쁜가.** 점수로는 근접도 빗나감도 똑같이 0 이다.
그런데 사람이 겪는 것은 전혀 다르다.

    근접     CLARIFY {034, 045, 046}   정답 045 가 후보 안에 있다. 사람이 고르면 된다
    빗나감   SELECT  {011}             확신하고 틀린다. 사람이 알 방법이 없다

「틀린 답보다 정직한 되물음이 낫다」가 이 저장소의 원칙이다. 한 칸짜리 적중률은
그 차이를 못 본다 — 되묻던 자리가 확신하고 틀리는 것으로 바뀌어도 숫자는 안
움직인다. 표가 못 보면 아무도 못 본다.

그러니 **이 칸을 합치지 말 것.** 적중률만 남기면 품질이 무너지는 것을 놓친다.
빗나감이 늘고 근접이 줄었으면 적중률이 그대로여도 나빠진 것이다.

「빗나감」에는 SELECT 로 하나 고르고 틀린 것과, CLARIFY 인데 정답이 후보에 아예
없는 것이 함께 들어간다. 둘 다 사람이 정답에 닿을 길이 없다. 어느 쪽인지는 옆의
「틀렸을 때 나온 것」 칸에서 갈린다.

## ★ 지금 재는 것은 LLM selection 하나다

`/resolve` 는 menu 원문과 발화만 받아 LLM 이 고른 것을 그대로 돌려준다.
**고른 결과를 뒤에서 바꾸는 자리가 하나도 없다** — 검산도 거르개도 없다.
그래서 「LLM 이 쓴 것」과 「최종 후보」가 언제나 같고, 후보 표는 LLM 후보 수와
status 만 본다.

재는 모델은 창구가 읽는 resolve 역할 설정(`llm_engine/roles/resolve/resolve.yaml`)
한 판이다 — 이 도구가 고르지 않는다. 다른 모델을 재려면 manifest 를 고치고 판을
올린다. 표 머리의 역할 줄은 **이 저장소의** manifest 를 읽은 것이다. `/resolve`
응답에는 판이 안 실리므로 창구가 다른 사본에서 떠 있으면 다를 수 있다.

발화가 확정된 뒤에도 **이 파일은 지우지 않는다.** 온톨로지나 menu 가 바뀌면
다시 재야 하고, 지웠다 되살리는 것보다 두는 편이 싸다. 그래서 파일 하나에 담고
저장소의 다른 곳을 건드리지 않는다.

실측 기록과 「다시 시도하지 말 것」은 NOTES.md 에 있다. 발화를 고치기 전에
읽는다 — 이미 재본 것을 또 재게 된다.
"""

import argparse
import contextlib
import io
import itertools
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

# 저장소 뿌리를 path 에 넣는다. dev/tools/ 아래에서 돌아가므로 이것 없이는 app 을
# 못 찾는다 (check_wiring.py 와 같은 방식이다).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import endpoints  # noqa: E402
import paths  # noqa: E402
from dev.evaluation import suite  # noqa: E402

# ── 정답표 ──────────────────────────────────────────────────────────
#
# **정답표는 dev/evaluation/resolve_regression.yaml 에 있다** (2026-09-15 옮김).
# 발화 · 기대 recipe · 이름 있는 값 · 표시 · 묶음을 그 파일이 갖는다. 옮기기 전 이 자리에
# 있던 주석(발화별 실측 · 지운 까닭 · 번호가 밀린 이력)도 글자 그대로 그리로 옮겼다.
# 기대값을 고치려면 그 파일을 고친다. 여기서 다시 적지 않는다 — 두 곳이 되면 조용히 어긋난다.
#
# 아래 이름(UTTERANCES · SPOKEN_VALUES · MARKS · BASELINE_LAST · EXTENSION_LAST)은 그대로
# 둔다. check_llm · check_argument · check_demo 와 시험이 이 이름으로 부른다.
SUITE = suite.load()

# (번호, 발화, 기대 recipe 집합, 기본 실행 여부)
UTTERANCES = suite.utterances(SUITE)

# ── 이름 있는 값의 정답표 ───────────────────────────────────────────
#
# {발화 번호: {이름: 기대값}}. **null 은 실패가 아니다** — 기대값 None 은 「null 이어야
# 한다」는 요구다. 적는 칸만 본다. 까닭과 이력은 정답표 YAML 의 「이름 있는 값」 절에 있다.
SPOKEN_VALUES = suite.spoken_values(SUITE)

# 그 표가 보는 이름의 차례. 표를 찍는 차례이기도 하다.
SPOKEN_VALUE_NAMES = ("argument", "travel_mode", "minutes", "admin_level")

# 값이 없다는 것을 표에 어떻게 적나. "-" 는 이미 인자 표가 쓰는 글자라
# **null 을 그것과 갈라 적는다** — 사람이 말 안 한 것과 못 뽑은 것이 다르다.
NULL_MARK = "null"


# ── 표시 ────────────────────────────────────────────────────────────
#
# 적중 표에 한 칸으로 찍는다. **낮은 점수가 무엇 때문인지 표에서 바로 읽히게
# 하는 것이 전부다.** 판정에는 아무 영향이 없다 — 세는 법은 표시가 없을 때와
# 글자까지 같다.
#
#   겹침  **발화 하나로 recipe 하나를 못 집는 자리.** 기대값은 그대로 하나이고
#         후보에 늘 따라붙는 상대가 있다. 그 상대는 발화 옆 주석에 적혀 있다.
#         빗나감·근접이 나오는 것이 이상하지 않은 자리이고, 고칠 곳은 발화가
#         아니라 recipe 를 가르는 규칙이다
#   -     겹치는 상대가 없는 자리. 여기서 안 맞으면 그것은 발견이다
#
# ★ **2026-09-03 「아흔셋째」에 표시의 뜻을 갈았다.** 옛 넷(시연·위험·애매·
#   화면)은 「어느 날 어떤 근거로 넣은 줄인가」를 적은 것이라 정답표를 통째로
#   새로 지으면서 가리킬 데가 없어졌다. 새 표시는 **지금 무엇이 갈리지
#   않는가**를 적는다 — 그것이 이 표를 보고 다음에 고칠 것을 고르는 자리다.
#   ★ 「화면」은 표시에서 뺐다. 묶음 이름(찍은 지점 · 보이는 범위)이 이미 그
#   말을 하고 있어 한 칸에 같은 것을 두 번 적을 까닭이 없다.
#   ★ 옛 이름 넷은 지우지 않고 남긴다 — 옛 NOTES 의 표에 그 글자가 찍혀 있다.
DEMO, RISKY, VAGUE, SCREEN, PLAIN = "시연", "위험", "애매", "화면", "-"
OVERLAP = "겹침"

# 번호 → 표시. 여기 없는 번호는 PLAIN 이다.
#
# **발화 줄과 따로 둔 표다** — 정답표 YAML 에서도 cases 와 갈라 marks 절에 둔다. 표시를
# 고칠 때 발화 줄의 diff 가 0 이어야 「발화는 안 움직였다」를 diff 만 보고 확인할 수 있다.
# 개수가 바뀐 이력은 그 절에 옮겼다.
MARKS = suite.marks(SUITE)


def _mark(number: int) -> str:
    return MARKS.get(number, PLAIN)


# ── 세 묶음 ─────────────────────────────────────────────────────────
#
# **셋을 합쳐 하나의 백분율로 만들지 않는다. 묶음의 점수를 서로 견주지도 않는다.**
# 새 셋은 **시작 데이터**로 가른다 — 말한 것 · 찍은 지점 · 보이는 범위.
#
# ★ **묶음은 정답표 YAML 의 각 발화 group 이 정한다** (2026-09-15 부터). 옛 숫자 경계
# (BASELINE_LAST · EXTENSION_LAST)를 코드에 두던 까닭과 경계를 옮긴 이력은 그 파일
# groups 절에 글자 그대로 옮겼다.
#
# BASELINE_LAST · EXTENSION_LAST 는 그 이름으로 부르는 계기판(check_llm)과 시험 때문에
# 남긴 값이고, 이제는 그 묶음의 마지막 번호에서 계산한다. 묶음이 번호 순으로 이어져
# 있어야 뜻이 있다 — suite.load 가 본다.
BASELINE_LABEL, EXTENSION_LABEL, SCREEN_LABEL = suite.group_labels(SUITE)
BASELINE_LAST = suite.last_id(SUITE, "spoken")
EXTENSION_LAST = suite.last_id(SUITE, "picked_point")

# 번호 → 묶음 이름. _groups 와 _group_label 이 따로 읽는다.
GROUP_OF = suite.group_of(SUITE)


def _groups(entries) -> list:
    """발화 목록을 기준선 · 확장 · 화면으로 가름.

    입력  발화 목록
    출력  [(묶음 이름, 그 묶음의 발화 목록)] — 빈 묶음은 뺌
    규칙  --only 로 한 묶음만 돌리면 한 묶음만 나옴. 그때는 합계 줄을 안 찍음.
          소계 한 줄과 합계 한 줄이 같은 값으로 두 번 나오면 읽는 사람이
          둘을 다른 것으로 본다
          묶음은 정답표의 group 이 정함 (GROUP_OF). 정답표에 없는 번호는 어느 묶음에도 안 듦
    """
    baseline = [entry for entry in entries if GROUP_OF.get(entry[0]) == BASELINE_LABEL]
    extension = [entry for entry in entries if GROUP_OF.get(entry[0]) == EXTENSION_LABEL]
    screen = [entry for entry in entries if GROUP_OF.get(entry[0]) == SCREEN_LABEL]
    return [
        (label, group)
        for label, group in (
            (BASELINE_LABEL, baseline),
            (EXTENSION_LABEL, extension),
            (SCREEN_LABEL, screen),
        )
        if group
    ]


def _group_label(number: int) -> str:
    """발화 번호가 어느 묶음에 드는가. **_groups 와 같은 경계를 쓴다.**

    입력  발화 번호
    출력  묶음 이름 셋 중 하나
    규칙  _groups 가 목록을 가르는 경계와 여기가 어긋나면, 표는 _groups 로
          만든 칸에 여기가 고른 이름으로 넣게 되어 없는 칸을 찾는다.
          경계를 고칠 일이 생기면 두 곳을 같이 고친다
          정답표에 있는 번호는 그 group 을 씀. 없는 번호만 마지막 번호로 가름
    이력  이것이 없어 두 표가 「번호 <= BASELINE_LAST 면 기준선, 아니면 확장」
          이라는 두 갈래로 이름을 골랐다. 화면 갈래가 없어 32~36 이 확장으로
          갔고, --only 32 처럼 화면만 돌리면 확장 칸이 아예 안 만들어져
          KeyError 로 죽었다 (「예순셋째」)
    """
    if number in GROUP_OF:
        return GROUP_OF[number]
    if number <= BASELINE_LAST:
        return BASELINE_LABEL
    if number <= EXTENSION_LAST:
        return EXTENSION_LABEL
    return SCREEN_LABEL


load_dotenv(REPO_ROOT / ".env")



def _base_url() -> str:
    """창구 주소(AGENTIC_API_URL).

    규칙  화면이 부르는 주소와 같아야 표를 믿을 수 있으므로 같은 환경변수를 봄
          부를 때마다 읽음. import 시점에 굳히면 이 파일의 발화 목록만 빌려
          쓰는 자(check_llm)까지 주소를 요구하게 됨
    """
    return endpoints.agentic_api_url()

# 역할 manifest 의 timeout 보다 짧으면 느린 판을 잴 때 서버가 답하기 전에 여기서
# 끊겨 표가 오류로만 찬다. 화면(app/ui/api_client.RESOLVE_TIMEOUT 180)과 달리 이
# 도구는 느린 판도 재므로 값을 넉넉히 따로 둔다.
TIMEOUT = 900

UTTERANCE_WIDTH = 38  # 표에서 발화 칸의 폭. 넘치면 자른다 — 번호로 알아본다.

# 실행에 실어 보내는 지도 문맥 스위치. --context 가 정한다. 기본은 "both".
#
# **고르는 데는 안 쓰인다.** recipe 선택은 발화와 menu 만 보므로 /resolve 는
# 문맥을 안 받는다. 이 값이 걸리는 곳은 `--execute` 의 /chat/stream 하나이고,
# 거기서는 배선이 실제로 $context 를 읽는 recipe 가 있어 값이 있어야 돈다.
#
# 기본이 both 인 것은 KRRI_ASAP 화면에서 우클릭한 뒤와 같은 조건이기 때문이다.
# 우클릭 전을 재려면 `--context bbox`, 아예 안 보내려면 `--context none`.
CONTEXT_NONE, CONTEXT_BBOX, CONTEXT_BOTH = "none", "bbox", "both"
CONTEXT = CONTEXT_BOTH

# 실행에 쓰는 지도 범위. 오송역(127.3277, 36.6200)에서 반경 15km 이고
# 온톨로지의 지점 주변 범위 변환(radiusMeters 15000)으로 만든 상자다. 시연이 오송·청주에서 돈다.
VIEW_BBOX = [[127.1598, 36.4853], [127.4956, 36.7547]]

# --context both 일 때 얹는 찍은 지점. bbox 의 중심과 같은 좌표다.
# label 과 source 는 KRRI_ASAP 의 useChat 이 우클릭 뒤에 얹는 문자열과 같다.
PICKED_POINT = {
    "lon": 127.3277,
    "lat": 36.6200,
    "label": "관심 지점",
    "source": "map-right-click",
}


def _context_payload() -> dict | None:
    """이번 측정에서 /chat/stream 본문에 실을 지도 문맥.

    출력  문맥 dict. --context none 이면 None
    규칙  bbox 만 있는 것이 우클릭 전 모양임. selectedLocation 은 null
          both 는 그 위에 찍은 지점을 얹음
    """
    if CONTEXT == CONTEXT_NONE:
        return None

    context = {"view": {"bbox": VIEW_BBOX}, "selectedLocation": None}
    if CONTEXT == CONTEXT_BOTH:
        context = {**context, "selectedLocation": dict(PICKED_POINT)}
    return context


# ── 한글 폭 ──────────────────────────────────────────────────────────
# 한글은 폭이 2 라 ljust 로는 표가 어긋난다. 표 라이브러리를 쓰지 않으므로
# 여기서 직접 센다.


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _clip(text: str, width: int) -> str:
    """폭 width 안에 들어가게 자름. 잘렸으면 끝에 … 를 붙임."""
    if _width(text) <= width:
        return text
    kept, used = "", 0
    for ch in text:
        ch_width = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if used + ch_width > width - 1:
            break
        kept, used = kept + ch, used + ch_width
    return kept + "…"


# ── 호출 ────────────────────────────────────────────────────────────


class ServerDown(RuntimeError):
    """서버에 닿지 못했다. 재시도하지 않고 즉시 멈춘다."""


def _short(recipe_ids) -> str:
    """{"recipe_004", "recipe_005"} → "{004, 005}"."""
    trimmed = sorted(rid[len("recipe_"):] if rid.startswith("recipe_") else rid for rid in recipe_ids)
    return "{" + ", ".join(trimmed) + "}"


def _argument_of(result: dict) -> str:
    """응답이 발화에서 뽑은 인자. 못 뽑았으면 "-".

    규칙  Counter 의 key 라 문자열로 둠
    이력  2026-09-04 까지는 축 셋(given · want · about)과 한 튜플이었음.
          그 셋을 걷어 응답에서 없어졌고, 2026-09-06 에 늘 "-" 만 찍던 세 칸을
          지웠음. 남은 것이 인자다 — recipe 가 맞는데 인자만 흔들리는 자리를
          여기서 본다
    """
    return result.get("argument") or "-"


def _spoken_values_of(result: dict) -> tuple:
    """응답이 발화에서 뽑은 이름 있는 값들. Counter 의 key 라 튜플로 둠.

    출력  ((이름, 값 글자), ...). SPOKEN_VALUE_NAMES 차례
    규칙  값이 null 이면 NULL_MARK. 못 뽑은 것과 안 말한 것을 안 섞음 —
          이 계약에서는 안 말한 것이 정답인 자리가 있음
          목록은 대괄호 없이 이어 적음. Counter 의 key 라 해시가 돼야 함
    """
    rows = []
    for name in SPOKEN_VALUE_NAMES:
        value = result.get(name)
        if value is None:
            said = NULL_MARK
        elif isinstance(value, list):
            said = ",".join(str(item) for item in value)
        else:
            said = str(value)
        rows.append((name, said))
    return tuple(rows)


def _spoken_value_verdict(number: int, seen: Counter) -> tuple:
    """그 발화의 이름 있는 값이 정답표와 맞나.

    입력  발화 번호 · 회차마다 나온 _spoken_values_of 결과의 Counter
    출력  (맞은 회수, 전체 회수, [어긋난 칸 설명]). 정답표에 없는 번호면 None
    규칙  SPOKEN_VALUES 에 적은 이름만 봄. 안 적은 이름은 무엇이 와도 넘어감
          기대값 None 은 NULL_MARK 와 맞대는 것임. 「안 말한 것을 안 지어냈나」
          회차가 갈리면 맞은 회수로 셈. 흔들리는 자리를 표에서 바로 읽게 함
    """
    wanted = SPOKEN_VALUES.get(number)
    if wanted is None:
        return None

    hits, total, wrong = 0, 0, Counter()
    for rows, count in seen.items():
        total += count
        said = dict(rows)
        bad = [
            f"{name}={said.get(name, '-')}"
            for name, value in wanted.items()
            if said.get(name) != (NULL_MARK if value is None else
                                  ",".join(str(item) for item in value)
                                  if isinstance(value, list) else str(value))
        ]
        if bad:
            wrong[" · ".join(bad)] += count
        else:
            hits += count
    return hits, total, [f"{text} ({count}회)" for text, count in wrong.most_common()]


def _tally(result: dict) -> tuple:
    """응답의 후보 수와 status. 후보 표에 한 줄로 찍을 형태.

    출력  (LLM 후보 수, 최종 status). 없는 key 는 "-"
    규칙  LLM 후보 수는 candidate_recipe_ids 의 길이.
          recipe_id 가 있고 그 목록에 없으면 하나 더 셈
          Counter 의 key 라 문자열 튜플로 둠. 리스트는 해시가 안 됨
    이력  2026-09-04 에 축 조회를 걷어 shortlist_recipe_ids 가 응답에서
          없어짐. 그래서 「조회 후보 수」와 「조회 판정」 두 칸이 늘 빈 값이었고
          2026-09-06 에 지웠음
    """
    spoken = result.get("candidate_recipe_ids")
    if spoken is None:
        llm_count = "-"
    else:
        chosen = result.get("recipe_id")
        llm_count = str(len(spoken) + (1 if chosen and chosen not in spoken else 0))

    return llm_count, result.get("status") or "-"


def _describe_role(role) -> str:
    """역할 설정 한 벌을 표 머리 한 줄로. 계기판들이 같은 글자로 적게 한 곳에 둠."""
    return (
        f"역할 {role.role} v{role.version} · {role.model} ({role.provider}) · "
        f"prompt v{role.prompt_version} · response_schema v{role.response_schema_version}"
    )


def _role_label() -> str:
    """표 머리에 적을 resolve 역할 한 줄.

    규칙  이 저장소의 역할 manifest 를 읽음. 창구가 같은 사본에서 떠 있을 때
          창구가 쓰는 판과 같음. /resolve 응답에는 판이 안 실림
          못 읽으면 그 까닭을 적고 재기는 멈추지 않음. 재는 것은 창구임
          부를 때 import 함. 이 파일의 발화 목록만 빌려 쓰는 자가 역할 설정까지
          끌어오지 않게 하려는 것
    """
    from llm_engine.role_config import RESOLVE, get_role_config

    try:
        return _describe_role(get_role_config(RESOLVE))
    except ValueError as error:
        return f"역할 {RESOLVE} 못 읽음 ({error})"


def _call_resolve(utterance: str) -> tuple:
    """POST /resolve 한 번.

    입력  발화
    출력  (후보 집합, status, 인자, 후보 수와 조회 후보 집합, 시간 칸,
          이름 있는 값들).
          후보는 recipe_id 와 candidate_recipe_ids 를 합친 것
          맨 뒤에만 덧붙인다 — check_argument 가 앞의 셋만 받아 쓴다
          시간 칸은 이 도구가 잰 /resolve 한 번의 시간(elapsed) 하나뿐인 dict
    규칙  서버에 못 닿으면 ServerDown. 재시도하지 않고 즉시 멈춤
          지도 문맥을 안 보냄. 고르는 것은 LLM 뿐이라 /resolve 가 안 받음
          status 를 후보와 함께 냄. 적중 표가 근접·빗나감을 가르는 데 씀 —
          후보 집합만으로는 CLARIFY 와 SELECT 가 안 갈림
    """
    params = {"utterance": utterance}

    started = time.perf_counter()
    try:
        response = requests.post(
            f"{_base_url()}/resolve",
            params=params,
            timeout=TIMEOUT,
        )
    except requests.exceptions.ConnectionError as exc:
        raise ServerDown(str(exc)) from exc
    elapsed = time.perf_counter() - started

    response.raise_for_status()
    result = response.json()
    found = [result.get("recipe_id"), *(result.get("candidate_recipe_ids") or [])]
    return (
        frozenset(rid for rid in found if rid),
        result.get("status") or "-",
        _argument_of(result),
        _tally(result),
        {"elapsed": elapsed},
        _spoken_values_of(result),
    )


# ── 측정 ────────────────────────────────────────────────────────────


def _measure(
    entries, runs: int, outcomes: dict, axes: dict, tallies: dict,
    times: dict | None = None,
    spoken: dict | None = None,
) -> None:
    """발화마다 runs 회 돌려 결과를 쌓음.

    입력  발화 목록 · 반복 횟수 · 채워 넣을 dict 넷
    규칙  outcomes[번호] 에 나온 (후보 집합, status) 조합의 Counter 를 쌓음.
          status 를 함께 묶는 것은 적중 표가 근접·빗나감을 가르기 위함임.
          적중 판정은 후보 집합만 봄 — 예전과 같은 숫자가 나와야 함
          axes[번호] 에 나온 argument 의 Counter 를 쌓음
          tallies[번호] 에 나온 (LLM 후보 수, status) 의 Counter 를 쌓음
          spoken[번호] 에 나온 이름 있는 값들의 Counter 를 쌓음. 값 표가 씀
          실행 하나가 끝날 때마다 점 하나를 찍음. 20회면 몇 분 걸려서
          아무것도 안 나오면 멈춘 줄 앎
          오류도 결과의 하나로 Counter 에 남김. 그때 인자와 후보 수는
          안 쌓음. 응답이 없음
          times[번호] 에 회차마다 시간 칸(dict)을 목록으로 쌓음. 시간 줄이 씀
    제약  결과를 돌려주지 않는다.
          받은 dict 에 채움. 중간에 끊겨도(Ctrl-C · 서버 중단) 거기까지의
          결과가 부르는 쪽에 남아 있어야 표를 찍을 수 있음
    """
    for number, utterance, _expected, _default in entries:
        counter = Counter()
        axis_counter = Counter()
        tally_counter = Counter()
        spoken_counter = Counter()
        time_rows = []
        outcomes[number] = counter
        axes[number] = axis_counter
        tallies[number] = tally_counter
        if times is not None:
            times[number] = time_rows
        if spoken is not None:
            spoken[number] = spoken_counter
        sys.stdout.write(f"  {number} ")
        sys.stdout.flush()
        for _ in range(runs):
            try:
                found, status, axis, tally, timing, values = _call_resolve(
                    utterance
                )
                counter[(found, status)] += 1
                axis_counter[axis] += 1
                tally_counter[tally] += 1
                spoken_counter[values] += 1
                time_rows.append(timing)
                sys.stdout.write(".")
            except ServerDown:
                sys.stdout.write("\n")
                raise
            except Exception as exc:  # noqa: BLE001 — 오류도 결과의 하나로 표에 남긴다.
                counter[(f"오류: {type(exc).__name__}", "-")] += 1
                sys.stdout.write("!")
            sys.stdout.flush()
        sys.stdout.write("\n")
        sys.stdout.flush()


# ── 실행 ────────────────────────────────────────────────────────────
#
# **정답표는 「경로를 맞게 골랐는가」만 잰다.** 그래서 이런 것이 안 보였다 —
# 6번 「국회의원 선거구 찾아줘」가 적중 3/3 인데 화면에서는 "찾지 못했습니다"
# 였다. 고른 recipe 는 맞고, 그 recipe 를 부른 결과가 0건이었다.
#
# 실행 칸이 그 자리를 잰다. **두 칸의 뜻이 다르다.**
#
#   정답(기대값)  "이 발화는 이 recipe 로 가야 한다"   사람이 정한 것. 안 바뀜
#   실행 칸       "그 recipe 가 답을 내놓는다"          관찰한 사실. 날짜와 함께
#
# **실행 칸을 관문으로 삼지 않는다.** Gateway 쪽 데이터가 늘면 건수가 바뀌고
# Gateway 가 꺼지면 전부 실패한다. 적중 판정은 이 칸을 안 본다 — 네 칸과
# 그 합계는 --execute 를 붙이기 전과 같은 숫자가 나와야 한다.
#
# ## 무엇을 부르나 — KRRI_ASAP 화면과 같은 길
#
# POST /chat/stream 이다. **KRRI_ASAP 화면이 부르는 바로 그 길이다.** 해석부터 도구
# 호출까지 한 번에 지난다. 그다음 GET /recent 로 그 회차를 읽는다. 회차에
# status · recipe_id · candidate_recipe_ids · 단계 줄 · 답 문구가 다 들어 있어
# 무엇이 불렸고 무엇이 돌아왔는지를 응답 본문을 다시 파싱하지 않고 읽는다.
#
# **발화마다 한 번만 누른다.** 이 칸은 분포가 아니라 「지금 답이 나오는가」를
# 적는 자리다. 여러 번 눌러 평균을 내면 시간이 몇 배가 되는데 얻는 것이 없다 —
# 흔들리는 것은 해석이고 그것은 위의 적중 표가 이미 세 번씩 재고 있다.
#
# ## 되묻기가 나면 — 사람이 고르는 자리를 이 도구가 대신 고른다
#
# 되묻기가 나는 발화는 화면에서 사람이 번호를 골라야 실행된다. 그 자리를
# `?` 로 두면 29~31 번 같은 「애매」 자리가 영영 안 재어진다. 그래서
# **기대 recipe 가 후보에 있으면 그 번호를 골라 이어 누른다.** 고르기는
# 해석을 다시 하지 않으므로 부르는 것은 정확히
# 기대 recipe 다. 사람이 화면에서 하는 것과 같은 동작이고, 표에는 「되묻기→고름」
# 이라고 밝혀 곧장 실행된 자리와 갈라 적는다.
#
# 기대 recipe 가 후보에 아예 없거나 다른 것을 확신하고 골랐으면 `?` 다.
# **그 자리에서 실행이 되는지는 이 표가 말할 수 없다.** 왜 못 쟀는지를 적는다 —
# 「빗나감」인지 「못 붙음」인지는 위의 적중 표가 이미 말하고 있다.
#
# ## 값 셋
#
#   ✓  기대 recipe 가 돌았고 결과가 왔다
#   ✗  기대 recipe 가 돌았는데 답이 안 나왔다. 0건 · not_found · 권한 · 인자 · 배선
#   ?  기대 recipe 를 아예 안 지났다. 해석이 다른 데로 갔다
#
# **왜 그런지를 한 줄로 함께 적는다.** ✗ 만 있으면 Gateway 쪽 데이터가 없는 것인지
# 우리 인자가 틀린 것인지 권한이 없는 것인지를 못 가른다. 그 셋은 할 일이
# 전혀 다르다.

# 판정 문구는 vendor 와 demo 에서 그대로 가져온다. 여기서 다시 적으면 그쪽
# 문구가 바뀔 때 이 표가 조용히 거짓말을 한다 — 화면은 "찾지 못했습니다" 인데
# 표는 ✓ 로 찍히는 식이다.
from vendor_to_be_deleted.asap.workflow_answer import (  # noqa: E402
    EMPTY_HEADLINE,
    ERROR_HEADLINE,
    MISSING_STATUS,
    NO_ARGUMENT_ANSWER,
    NO_PERMISSION_REASON,
    UNWIRED_ANSWER,
)

RAN, EMPTY, UNMEASURED = "✓", "✗", "?"

# 배선이 없을 때의 답에서 이름 뒤에 붙는 부분. 문구를 다시 적지 않으려고
# 틀에서 잘라 쓴다.
UNWIRED_TAIL = UNWIRED_ANSWER.split("{names}")[-1]

# 왜 ✗ 인지를 가르는 말. 표의 「왜」 칸 맨 앞에 온다.
#
# **응답이 status 로 "없다" 고 말한 것은 그 status 이름을 그대로 쓴다**
# (not_found · empty). 셋의 뜻이 다르고 할 일도 다르다 — 0건은 낱말을 바꾸면
# 되고, not_found 는 데이터에 있는 이름을 그대로 대야 하고, empty 는 Gateway 에
# 데이터가 아예 안 실린 것이라 우리가 할 일이 없다. 이름은 MISSING_STATUS 에서
# 온다. 여기서 다시 적지 않는다.
WHY_EMPTY = "0건"
WHY_PERMISSION = "권한"
WHY_CALL_FAILED = "호출 실패"
WHY_ARGUMENT = "인자"
WHY_UNWIRED = "배선"


def _empty_why(detail: str) -> str:
    """빈 결과를 0건과 status 로 가름.

    입력  마지막 단계 줄
    출력  status 이름(not_found · empty) 또는 WHY_EMPTY
    규칙  단계 줄에 MISSING_STATUS 의 문구가 있으면 그 status 임.
          답의 둘째 줄로 안 가름 — 그 줄은 글자로 부른 단계에만 붙어서
          (workflow_answer._retry_line) 좌표로 부른 not_found 를 놓침
    """
    for status, text in MISSING_STATUS.items():
        if text in detail:
            return status
    return WHY_EMPTY

# 되묻기를 지나 고른 자리에 붙이는 표시.
PICKED_MARK = "되묻기→고름"


def _recent_seq() -> int:
    """지금 회차 번호. 이 뒤에 생긴 회차만 읽으려고 먼저 물어 둔다."""
    response = requests.get(f"{_base_url()}/recent", timeout=TIMEOUT)
    response.raise_for_status()
    return response.json().get("seq") or 0


def _chat_turn(text: str, since: int) -> tuple:
    """POST /chat/stream 한 번과 그것이 남긴 회차.

    입력  보낼 말 · 부르기 전의 회차 번호
    출력  (회차 dict, 새 회차 번호). 회차가 안 남았으면 (None, 그대로)
    규칙  흐름을 끝까지 받고 버림. **SSE 를 파싱하지 않음** — 읽을 것은 전부
          GET /recent 의 회차에 있고(status · 후보 · 단계 줄 · 답), 여기서
          이벤트를 다시 해석하면 KRRI_ASAP 화면과 다른 자를 갖게 됨.
          끝까지 받는 것은 필요함 — 흐름이 끝나야 회차가 남는다
          (recent_service.watched 의 finally)
    제약  서버에 못 닿으면 ServerDown 을 올린다.
          측정과 같은 처신임. 재시도하지 않음
    이력  2026-09-06 까지는 평범한 POST /chat 을 썼음. 그 창구를 지우면서
          KRRI_ASAP 화면과 같은 길로 옮겼음 — 그 전에도 같은 흐름이었지만
          「같은 흐름을 쓴다」는 것을 사람이 알고 있어야 성립하던 자리였다
    """
    try:
        with requests.post(
            f"{_base_url()}/chat/stream",
            json={"text": text, "context": _context_payload()},
            timeout=TIMEOUT,
            stream=True,
        ) as response:
            response.raise_for_status()
            for _line in response.iter_lines():
                pass
    except requests.exceptions.ConnectionError as exc:
        raise ServerDown(str(exc)) from exc

    recent = requests.get(
        f"{_base_url()}/recent", params={"since": since}, timeout=TIMEOUT
    ).json()
    turns = recent.get("turns") or []
    return (turns[-1] if turns else None), (recent.get("seq") or since)


def _last_step(turn: dict) -> str:
    """마지막 단계 줄 한 줄. 단계가 없으면 "".

    규칙  앞의 "N. " 을 떼고 이어진 줄을 한 줄로 붙임. 문서 검색처럼 조각을
          여러 줄로 내놓는 단계가 있어 그대로 두면 표가 무너짐
    """
    steps = turn.get("steps") or []
    if not steps:
        return ""
    line = (steps[-1].get("line") or "").strip()
    if ". " in line[:4]:
        line = line.split(". ", 1)[1]
    return " ".join(line.split())


def _execution_of(turn: dict) -> tuple:
    """이 회차가 답을 내놓았는가.

    입력  기대 recipe 가 실제로 돈 회차
    출력  (RAN 또는 EMPTY, 왜인지 한 줄)
    규칙  판정 근거는 답의 첫 줄임. vendor 의 _verdict 가 거기에 결과를
          적었음 — 성공이면 recipe 가 아는 문장, 빈 결과·오류면 우리 문구
          0건과 not_found 는 마지막 단계 줄로 갈림 (_empty_why)
          권한과 그냥 터진 것은 단계 줄의 사유로 갈림
          도구를 하나도 안 부른 자리(인자 없음 · 배선 없음)도 여기서 가름.
          그때는 단계 줄이 아예 없음
    제약  건수를 여기서 다시 세지 않는다.
          결과 모양을 아는 것은 vendor_to_be_deleted/asap/workflow_answer 이고, 여기가
          또 세면 두 곳이 다른 기준을 갖게 된다
    """
    answer = turn.get("answer") or ""
    detail = _last_step(turn)

    if answer.startswith(EMPTY_HEADLINE):
        why = _empty_why(detail)
        return EMPTY, f"{why} · {detail}" if detail else why

    if answer.startswith(ERROR_HEADLINE):
        why = WHY_PERMISSION if NO_PERMISSION_REASON in answer else WHY_CALL_FAILED
        return EMPTY, f"{why} · {detail}" if detail else why

    if answer in set(NO_ARGUMENT_ANSWER.values()):
        return EMPTY, f"{WHY_ARGUMENT} · 뽑은 것이 없다"

    if answer.rstrip().endswith(UNWIRED_TAIL.rstrip()):
        return EMPTY, f"{WHY_UNWIRED} · {answer.removesuffix(UNWIRED_TAIL)}".rstrip()

    return RAN, detail


def _execute(entries, executions: dict) -> None:
    """발화마다 한 번씩 실행까지 눌러 결과를 쌓음.

    입력  발화 목록 · 채워 넣을 dict
    규칙  executions[번호] 에 (판정, 왜, 되묻기를 지났는가) 를 넣음
          기대값이 하나일 때만 잼. 여럿이면 무엇을 불러야 하는지가
          정해지지 않아 `?` 임
          되묻기가 나고 기대 recipe 가 후보에 있으면 그 번호를 골라 이어
          누름. 사람이 화면에서 하는 것과 같음
          해석이 다른 데로 갔으면 `?` 임. 기대 recipe 가 안 돌았으므로
          이 표가 그 자리를 말할 수 없음
          오류도 결과의 하나로 남김. 표가 비는 것보다 무엇이 터졌는지가 나음
    제약  결과를 돌려주지 않는다.
          받은 dict 에 채움. 중간에 끊겨도 거기까지가 부르는 쪽에 남아야 함
    """
    for number, utterance, expected, _default in entries:
        sys.stdout.write(f"  {number} ")
        sys.stdout.flush()
        try:
            if len(expected) != 1:
                executions[number] = (UNMEASURED, "기대값이 여럿이다", False)
                sys.stdout.write("?\n")
                continue

            wanted = next(iter(expected))
            since = _recent_seq()
            turn, since = _chat_turn(utterance, since)
            picked = False

            if turn is None:
                executions[number] = (UNMEASURED, "회차가 안 남았다", False)
                sys.stdout.write("?\n")
                continue

            # 되묻기일 때만 번호를 눌러 본다. 사람이 화면에서 하는 것과 같다.
            #
            # 2026-09-01 에 세션을 걷어낸 뒤로 이 번호는 고르기가 아니라 새
            # 발화로 해석된다. 그래도 누르는 것을 남긴다 — 화면 앞의 사람이
            # 겪는 것이 이것이고, 그 결과는 아래에서 「?」로 표에 남는다.
            candidates = turn.get("candidate_recipe_ids") or []
            if turn.get("recipe_id") is None and wanted in candidates:
                turn, since = _chat_turn(str(candidates.index(wanted) + 1), since)
                picked = True

            if turn is None or turn.get("recipe_id") != wanted:
                got = (turn or {}).get("recipe_id")
                status = (turn or {}).get("status") or "-"
                went = _short([got]) if got else _short(candidates) if candidates else "없음"
                executions[number] = (UNMEASURED, f"{status} {went} 로 갔다", False)
                sys.stdout.write("?\n")
                continue

            executions[number] = (*_execution_of(turn), picked)
            sys.stdout.write(executions[number][0] + "\n")
        except ServerDown:
            sys.stdout.write("\n")
            raise
        except Exception as exc:  # noqa: BLE001 — 오류도 결과의 하나로 표에 남긴다.
            executions[number] = (UNMEASURED, f"오류: {type(exc).__name__}", False)
            sys.stdout.write("!\n")
        sys.stdout.flush()


# ── 표 ──────────────────────────────────────────────────────────────


# 적중 표의 네 칸. 자세한 뜻과 「빗나감」이 왜 제일 나쁜지는 파일 맨 위 주석에 있다.
HIT, NEAR, MISS, UNATTACHED = "적중", "근접", "빗나감", "못 붙음"

# 칸 폭. 머리글보다 좁으면 표가 어긋난다 ("못 붙음" 이 폭 7).
NEAR_WIDTH = 8
MISS_WIDTH = 9
UNATTACHED_WIDTH = 10


def _grade(result, status: str, expected: set) -> str:
    """한 번의 결과를 네 칸 중 하나로 가름.

    입력  후보 집합(오류면 문자열) · 최종 status · 기대 recipe 집합
    출력  HIT · NEAR · MISS · UNATTACHED 중 하나
    규칙  넷이 서로 안 겹치고 빠짐이 없음. 그래야 넷의 합이 시행 횟수가 됨
          **적중 판정은 예전 그대로 set(result) == expected 임.**
          아래 순서를 바꿔도 적중 수는 안 변함 — 못 붙음이 먼저지만
          NO_MATCH 일 때 후보가 기대값과 같을 수는 없기 때문
          오류는 못 붙음에 넣음. 답이 안 붙은 것은 마찬가지임.
          몇 번이 오류였는지는 옆 "틀렸을 때 나온 것" 칸에 그대로 보임
    """
    if not isinstance(result, frozenset):  # 오류
        return UNATTACHED
    if status == "NO_MATCH" or not result:
        return UNATTACHED
    if set(result) == expected:
        return HIT
    if expected <= set(result):  # 하나로 못 좁혔을 뿐 정답이 남아 있다
        return NEAR
    return MISS


# 표시 칸의 폭. 머리글("표시" 폭 4)보다 좁으면 표가 어긋난다.
MARK_WIDTH = 6


def _print_rows(entries, outcomes: dict, widths: tuple) -> tuple:
    """한 묶음의 발화 줄을 찍고 그 묶음의 합을 돌려줌.

    입력  그 묶음의 발화 목록 · outcomes · 칸 폭 묶음
    출력  (네 칸 Counter, 시행 횟수, 완전 적중이 아닌 번호 목록)
    규칙  줄을 찍는 법은 묶음을 가르기 전과 글자까지 같음.
          **판정은 표시 칸을 안 봄** — 표시는 사람이 읽으라고 적는 칸이고
          _grade 는 예전 그대로 후보 집합과 status 만 봄
    제약  합계 줄은 안 찍는다. 부르는 쪽이 묶음마다 찍음
    """
    hit_width, detail_column = widths

    total = Counter()
    total_runs = 0
    imperfect = []

    for number, utterance, expected, _default in entries:
        counter = outcomes.get(number)
        done = sum(counter.values()) if counter else 0
        if done == 0:  # 끊겨서 아직 한 번도 안 돈 발화. 0/0 을 적으면 오해한다.
            continue

        graded = Counter()
        for (result, status), count in counter.items():
            graded[_grade(result, status, expected)] += count

        hits = graded[HIT]
        total.update(graded)
        total_runs += done
        if hits < done:
            imperfect.append(number)

        misses = sorted(
            (
                (result, status, count)
                for (result, status), count in counter.items()
                if _grade(result, status, expected) != HIT
            ),
            key=lambda item: (
                -item[2],
                _short(item[0]) if isinstance(item[0], frozenset) else item[0],
            ),
        )

        head = (
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
            + _pad(_mark(number), MARK_WIDTH)
            + _pad(f"{hits}/{done}", hit_width)
            + _pad(str(graded[NEAR]), NEAR_WIDTH)
            + _pad(str(graded[MISS]), MISS_WIDTH)
            + _pad(str(graded[UNATTACHED]), UNATTACHED_WIDTH)
        )
        if not misses:
            print(head.rstrip())
            continue

        for index, (result, status, count) in enumerate(misses):
            shown = _short(result) if isinstance(result, frozenset) else result
            prefix = head if index == 0 else " " * detail_column
            print(
                prefix
                + _pad(shown, 20)
                + _pad(_grade(result, status, expected), 9)
                + _pad(status, 10)
                + f"{count}회"
            )

    return total, total_runs, imperfect


def _print_sum(label: str, total, total_runs: int, widths: tuple) -> None:
    """한 줄짜리 합. 묶음마다 한 번, 맨 아래 합계에 한 번 쓴다.

    입력  줄 끝에 적을 이름 · 네 칸 Counter · 시행 횟수 · 칸 폭
    규칙  적중 백분율 뒤에 이름을 붙임. **이름이 붙어야 어느 묶음의 값인지
          읽힌다** — 백분율 셋이 세로로 놓이면 어느 것이 아홉인지 못 가름
    """
    hit_width, hit_column = widths
    grade_width = hit_width + NEAR_WIDTH + MISS_WIDTH + UNATTACHED_WIDTH

    percent = round(100 * total[HIT] / total_runs) if total_runs else 0

    print(" " * hit_column + "─" * grade_width)
    print(
        " " * hit_column
        + _pad(f"{total[HIT]}/{total_runs}", hit_width)
        + _pad(str(total[NEAR]), NEAR_WIDTH)
        + _pad(str(total[MISS]), MISS_WIDTH)
        + _pad(str(total[UNATTACHED]), UNATTACHED_WIDTH)
        + _pad(f"{percent}%", 7)
        + f"← {label}"
    )


def _print_table(entries, outcomes: dict, runs: int) -> None:
    """적중 표. **두 묶음을 갈라 찍는다.**

    입력  발화 목록 · outcomes · 반복 횟수
    규칙  기준선 아홉과 확장 열아홉의 점수를 따로 냄. 합계 한 줄도 내지만
          아홉의 값이 그 위에 따로 보임. 둘을 한 백분율로 합치지 않음 —
          왜인지는 BASELINE_LAST 옆 주석에 있음
          한 묶음만 돌았으면(--only) 합계 줄은 안 찍음. 같은 값이 두 번 나옴
    """
    # 표의 적중 칸이 시작하는 자리. 표시 칸이 들어와 MARK_WIDTH 만큼 밀렸다.
    hit_column = 2 + 3 + UTTERANCE_WIDTH + 4 + MARK_WIDTH
    hit_width = len(f"{runs}/{runs}") + 4
    grade_width = hit_width + NEAR_WIDTH + MISS_WIDTH + UNATTACHED_WIDTH
    detail_column = hit_column + grade_width  # "틀렸을 때 나온 것" 칸이 시작하는 자리.

    print()
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("표시", MARK_WIDTH)
        + _pad(HIT, hit_width)
        + _pad(NEAR, NEAR_WIDTH)
        + _pad(MISS, MISS_WIDTH)
        + _pad(UNATTACHED, UNATTACHED_WIDTH)
        + "틀렸을 때 나온 것"
    )

    groups = _groups(entries)
    grand = Counter()
    grand_runs = 0
    imperfect = []

    for label, group in groups:
        total, total_runs, group_imperfect = _print_rows(
            group, outcomes, (hit_width, detail_column)
        )
        if total_runs == 0:  # 그 묶음이 아직 한 번도 안 돌았다
            continue
        _print_sum(label, total, total_runs, (hit_width, hit_column))
        grand.update(total)
        grand_runs += total_runs
        imperfect += group_imperfect

    if len(groups) > 1 and grand_runs:
        print()
        _print_sum("합계", grand, grand_runs, (hit_width, hit_column))

    # 넷을 더하면 시행 횟수여야 한다. 아니면 _grade 에 구멍이 난 것이다.
    counted = grand[HIT] + grand[NEAR] + grand[MISS] + grand[UNATTACHED]
    if counted != grand_runs:
        print()
        print(f"  ⚠ 네 칸의 합 {counted} 가 시행 횟수 {grand_runs} 와 다르다 — _grade 를 본다")

    if imperfect:
        print()
        print("  ⚠ 완전 적중이 아닌 발화 : " + " · ".join(str(n) for n in imperfect))
        if grand[MISS]:
            print("  ★ 빗나감 " + str(grand[MISS]) + "회 — 확신하고 틀린 것이다. 근접보다 나쁘다")
            print(
                "     위험 · 애매 표시가 붙은 발화라면 그것이 알고 넣은 자리다."
                " 표시가 「시연」이나 「-」인데 빗나갔으면 ★ 그것이 발견이다"
            )


# 인자 칸의 폭.
ARGUMENT_WIDTH = 22


def _print_arguments(entries, axes: dict) -> None:
    """발화마다 어떤 인자가 나왔는지.

    입력  발화 목록 · {번호: 인자 Counter}
    규칙  많이 나온 것부터. 값이 하나면 한 줄, 갈리면 여러 줄
          적중 표가 맞는데 실행이 엉뚱한 것을 조회하면 여기서 갈림 —
          recipe 는 맞았고 인자가 흔들린 것임
    이력  2026-09-06 까지는 축 셋(given · want · about)을 함께 찍었음.
          2026-09-04 에 그 셋이 응답에서 없어져 늘 "-" 였고, 걷기 전 판과
          표를 맞대려고 한동안 남겨 뒀다가 지웠음
    """
    print()
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("argument", ARGUMENT_WIDTH)
        + "횟수"
    )

    for number, utterance, _expected, _default in entries:
        counter = axes.get(number)
        if not counter:
            continue

        head = (
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
        )
        rows = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        for index, (argument, count) in enumerate(rows):
            prefix = head if index == 0 else " " * _width(head)
            print(
                prefix
                + _pad(_clip(argument, ARGUMENT_WIDTH - 2), ARGUMENT_WIDTH)
                + f"{count}회"
            )


# 값 표의 칸 폭. 머리글보다 좁으면 표가 어긋난다.
WANTED_WIDTH = 34
SAID_WIDTH = 34


def _print_spoken_values(entries, spoken: dict) -> None:
    """이름 있는 값이 정답표와 맞나. 적는 칸이 있는 발화만 찍는다.

    입력  발화 목록 · {번호: 이름 있는 값 Counter}
    규칙  SPOKEN_VALUES 에 없는 번호는 건너뜀. 그 발화는 이 표가 볼 것이 없음
          기대값 None 은 "null" 로 찍음. **안 말한 것이 정답인 자리다**
          어긋나면 무엇이 어떻게 나왔는지 옆에 적음. recipe 는 맞는데 값만
          흔들리는 자리를 여기서 봄
    제약  기대값을 나온 값에 맞춰 고치지 않는다.
          이 표는 사람이 화면에서 확인한 계약이고, 자를 결과에 맞추면
          자가 아무것도 안 지킴
    """
    rows = [entry for entry in entries if entry[0] in SPOKEN_VALUES]
    if not rows:
        return

    print()
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("기대한 값", WANTED_WIDTH)
        + _pad("적중", 8)
        + "어긋난 것"
    )

    hit_total, run_total, missed = 0, 0, []
    for number, utterance, _expected, _default in rows:
        verdict = _spoken_value_verdict(number, spoken.get(number) or Counter())
        if verdict is None:
            continue
        hits, total, wrong = verdict
        hit_total += hits
        run_total += total
        if wrong:
            missed.append(number)
        wanted = " · ".join(
            f"{name}={NULL_MARK if value is None else value}"
            for name, value in SPOKEN_VALUES[number].items()
        )
        print(
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
            + _pad(_clip(wanted, WANTED_WIDTH - 2), WANTED_WIDTH)
            + _pad(f"{hits}/{total}", 8)
            + _clip(" · ".join(wrong), SAID_WIDTH * 2)
        )

    print()
    print(f"  이름 있는 값  적중 {hit_total}/{run_total}"
          + (f" · 어긋난 발화 {' · '.join(str(n) for n in missed)}" if missed else ""))


# 후보 표의 칸 폭. 머리글보다 좁으면 표가 어긋난다.
LLM_COUNT_WIDTH = 15
STATUS_WIDTH = 12


def _print_candidates(entries, tallies: dict) -> None:
    """발화마다 후보가 몇 개까지 좁혀졌는지.

    입력  발화 목록 · {번호: 후보 수 조합 Counter}
    규칙  많이 나온 것부터. 조합이 하나면 한 줄, 갈리면 여러 줄
          인자 표와 같은 모양. 나란히 놓고 읽음
          모델을 바꿔 잰 두 표를 견주는 것이 이 표의 쓸모.
          후보 수가 줄면 모델이 문장을 읽어 가른 것이고, 그대로면 문장으로는
          못 가르는 것 — 그때 손볼 곳은 모델이 아니라 menu 문장이다
    이력  2026-09-06 까지는 「조회 후보 수」와 「조회 판정」 두 칸이 더 있었음.
          2026-09-04 에 축 조회를 걷어 늘 빈 값이었고, 걷기 전 판과 표를
          맞대려고 한동안 남겨 뒀다가 지웠음
    """
    print()
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("LLM 후보 수", LLM_COUNT_WIDTH)
        + _pad("status", STATUS_WIDTH)
        + "횟수"
    )

    for number, utterance, _expected, _default in entries:
        counter = tallies.get(number)
        if not counter:
            continue

        head = (
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
        )
        rows = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        for index, (tally, count) in enumerate(rows):
            llm_count, status = tally
            prefix = head if index == 0 else " " * _width(head)
            print(
                prefix
                + _pad(llm_count, LLM_COUNT_WIDTH)
                + _pad(status, STATUS_WIDTH)
                + f"{count}회"
            )


# ── 시간 ────────────────────────────────────────────────────────────
#
# /resolve 한 번이 몇 초인가. 뜻은 파일 맨 위 주석에 있다.


def _mean(values) -> str:
    values = [v for v in values if v is not None]
    return f"{sum(values) / len(values):.1f}" if values else "-"


def _print_times(entries, times: dict) -> None:
    """시간 줄. 묶음마다 /resolve 한 번의 평균.

    입력  발화 목록 · {번호: [시간 칸 dict, ...]}
    규칙  이 도구가 잰 값임. 묶음이 둘 이상이면 합계 한 줄을 더 찍음
    제약  적중 판정을 안 건드린다. 시간만 읽음
    """
    print()
    totals = {label: [] for label, _group in _groups(entries)}
    for number, _u, _e, _d in entries:
        rows = times.get(number) or []
        totals[_group_label(number)] += [row["elapsed"] for row in rows]
    measured = [(label, values) for label, values in totals.items() if values]
    for label, values in measured:
        print(f"  시간 · {label}  /resolve 한 번 평균 {_mean(values)}초 (합 {len(values)}회)")
    if len(measured) > 1:
        everything = [v for _l, values in measured for v in values]
        print(f"  시간 · 합계         /resolve 한 번 평균 {_mean(everything)}초 (합 {len(everything)}회)")


# 실행 표의 칸 폭.
EXPECTED_WIDTH = 8
EXECUTION_WIDTH = 6
WHY_WIDTH = 52


def _print_execution(entries, executions: dict, measured_on: str) -> None:
    """실행 표. 발화마다 ✓ · ✗ · ? 와 왜인지, 그리고 잰 날.

    입력  발화 목록 · executions · 잰 날짜 문자열
    규칙  묶음을 갈라 찍음. 적중 표와 같은 차례로 읽히게 하려는 것임
          묶음마다 ✓ 몇 · ✗ 몇 · ? 몇 을 셈. 백분율을 안 냄 — 관문이 아니고
          Gateway 쪽 데이터가 늘면 바뀌는 값임
          되묻기를 지나 고른 자리는 「왜」 칸에 밝힘. 곧장 실행된 자리와
          같은 것으로 읽히면 안 됨
    제약  적중 표의 숫자를 여기서 다시 내지 않는다.
          두 칸의 뜻이 다르고, 한 표에 나란히 두면 더한 값을 읽게 된다
    """
    print()
    print(f"  ── 실행 칸 (잰 날 {measured_on} · 발화마다 한 번) ──")
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("정답", EXPECTED_WIDTH)
        + _pad("실행", EXECUTION_WIDTH)
        + "왜"
    )

    for label, group in _groups(entries):
        rows = [(n, u, e) for n, u, e, _d in group if n in executions]
        if not rows:
            continue
        tally = Counter()
        for number, utterance, expected in rows:
            mark, why, picked = executions[number]
            tally[mark] += 1
            if picked:
                why = f"{why}  ({PICKED_MARK})" if why else f"({PICKED_MARK})"
            print(
                "  "
                + _pad(str(number), 3)
                + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
                + _pad(_short(expected), EXPECTED_WIDTH)
                + _pad(mark, EXECUTION_WIDTH)
                + _clip(why, WHY_WIDTH)
            )
        print(
            "  " + " " * (3 + UTTERANCE_WIDTH + 4)
            + f"{RAN} {tally[RAN]} · {EMPTY} {tally[EMPTY]} · {UNMEASURED} {tally[UNMEASURED]}"
            f"   ← {label}"
        )
        print()

    print("  ✓ 답이 나온다 · ✗ 기대 recipe 가 돌았는데 안 나온다 · ? 기대 recipe 를 안 지났다")
    print("  ★ 실행 칸은 관문이 아니다. Gateway 쪽 데이터가 늘면 바뀌고 Gateway 가 꺼지면 전부 실패한다")


def _recipe_state() -> str:
    """표 머리에 적을 지금 recipe 상태. 게시 자산 뿌리에 있는 recipe 수."""
    current = sorted(p.stem for p in paths.RECIPES_DIR.glob("recipe_*.yaml"))
    return f"게시본 (recipe {len(current)})"


def _selfcheck() -> None:
    """서버 없이 표 여섯이 어떤 묶음 조합에서도 끝까지 찍히는지. 틀리면 죽는다.

    규칙  **진짜 UTTERANCES 를 쓴다.** 손으로 적은 발화 몇 개로는 번호 경계가
          안 걸린다 — 실제로 죽은 것이 화면 발화(32~36)의 경계였음
          묶음 조합 일곱 가지(기준선 · 확장 · 화면 · 그 짝들 · 셋 다)를
          각각 --only 처럼 잘라 표 여섯을 다 찍어 봄. 좁히기는 끔 · 켬 둘 다
          찍은 것은 버림. 여기서 보는 것은 「죽지 않는가」임
    제약  서버 · Gateway · 온톨로지를 안 부른다. 값은 모양만 맞는 가짜이고
          이 검사는 **판정이 맞는지 안 본다** — 판정은 실측이 보는 것임
    이력  재는 도구가 조용히 죽은 것이 이번이 세 번째다 — check_argument
          나흘(「스물다섯째」) · check_inputs 하루(「쉰째」) · check_resolve
          (「예순셋째」). 앞의 둘은 배선표가 바뀌어 못 따라간 것이고 이번은
          발화가 늘어(화면 다섯) 묶음이 셋이 됐는데 이름을 고르는 자리가
          두 갈래에 머문 것이다. 셋 다 「표를 찍는 마지막에 죽는다」가 같다
    """
    labels = {label for label, _group in _groups(UTTERANCES)}
    assert labels == {BASELINE_LABEL, EXTENSION_LABEL, SCREEN_LABEL}, labels

    # 이름 있는 값의 정답표가 없는 번호를 가리키면 그 줄은 영영 안 찍힌다.
    numbers = {number for number, _u, _e, _d in UTTERANCES}
    unknown = sorted(set(SPOKEN_VALUES) - numbers)
    assert not unknown, f"SPOKEN_VALUES 에 없는 발화 번호 {unknown}"
    unknown_names = sorted(
        name
        for wanted in SPOKEN_VALUES.values()
        for name in wanted
        if name not in SPOKEN_VALUE_NAMES
    )
    assert not unknown_names, f"SPOKEN_VALUES 에 모르는 칸 {unknown_names}"

    # 번호 → 이름이 _groups 의 경계와 어긋나면 없는 칸을 찾게 된다.
    for number, _u, _e, _d in UTTERANCES:
        assert _group_label(number) in labels, number
    for label, group in _groups(UTTERANCES):
        for number, _u, _e, _d in group:
            assert _group_label(number) == label, (number, label, _group_label(number))

    picked = "recipe_019"
    argument = "오송역"
    time_row = {"elapsed": 1.0}

    def _fake(entries):
        outcomes, axes, tallies, times, executions, spoken = {}, {}, {}, {}, {}, {}
        for number, _u, expected, _d in entries:
            found = frozenset(expected)
            outcomes[number] = Counter({(found, "OK"): 1})
            axes[number] = Counter({argument: 1})
            # LLM 후보 수는 실제로 문자열이다 ("-" 또는 str(n))
            tallies[number] = Counter({("1", "OK"): 1})
            times[number] = [dict(time_row)]
            executions[number] = ("OK", "", picked)
            spoken[number] = Counter({_spoken_values_of({}): 1})
        return outcomes, axes, tallies, times, executions, spoken

    groups = _groups(UTTERANCES)
    subsets = []
    for size in (1, 2, 3):
        subsets += list(itertools.combinations(groups, size))

    for subset in subsets:
        entries = [entry for _label, group in subset for entry in group]
        outcomes, axes, tallies, times, executions, spoken = _fake(entries)
        with contextlib.redirect_stdout(io.StringIO()):
            _print_table(entries, outcomes, 1)
            _print_arguments(entries, axes)
            _print_spoken_values(entries, spoken)
            _print_candidates(entries, tallies)
            _print_times(entries, times)
            _print_execution(entries, executions, "1970-01-01")


def main() -> int:
    parser = argparse.ArgumentParser(description="후보 발화가 지금 온톨로지에서 통하는지 잰다.")
    parser.add_argument("--runs", type=int, default=5, help="발화마다 몇 번 돌릴지 (기본 5)")
    parser.add_argument(
        "--only",
        default="",
        help="돌릴 발화 번호. 예: 2,4 (기준선 아홉만: 1,2,3,4,5,6,7,8,9)",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="실행까지 부른다 (발화마다 한 번 더). 실행 칸 표가 하나 더 나온다",
    )
    parser.add_argument(
        "--context",
        choices=(CONTEXT_NONE, CONTEXT_BBOX, CONTEXT_BOTH),
        default=CONTEXT_BOTH,
        help="실행(--execute)에 실을 지도 문맥. 기본은 both — 우클릭한 뒤와 같다",
    )
    args = parser.parse_args()

    global CONTEXT
    CONTEXT = args.context

    if args.only:
        wanted = [int(part) for part in args.only.replace(" ", "").split(",") if part]
        entries = [entry for entry in UTTERANCES if entry[0] in wanted]
        missing = sorted(set(wanted) - {entry[0] for entry in entries})
        if missing:
            print(f"목록에 없는 번호 : {missing}")
            return 2
    else:
        entries = [entry for entry in UTTERANCES if entry[3]]

    # 잰 역할 판을 적는다. NOTES.md 의 측정 기록은 조건 없는 숫자를 받지 않는다.
    print(
        f"발화 {len(entries)}개 × {args.runs}회 · {_recipe_state()}"
        f" · {_role_label()}"
        f" · 지도 문맥 {CONTEXT}"
        f"{' · 실행까지' if args.execute else ''}"
    )
    print()

    outcomes, axes, tallies, times, note, status = {}, {}, {}, {}, "", 0
    executions, spoken = {}, {}
    try:
        _measure(
            entries, args.runs, outcomes, axes, tallies, times, spoken
        )
        if args.execute:
            print()
            print("  실행까지 부른다 (발화마다 한 번)")
            _execute(entries, executions)
    except ServerDown:
        # 재시도하지 않는다. 여기까지 잰 것이 있으면 표는 찍는다.
        note, status = "uvicorn 을 먼저 실행하세요", 1
    except KeyboardInterrupt:
        # 오래 걸리는 도구라 중간에 끊는 일이 생긴다. 거기까지의 표를 찍는다.
        note = "(중단됨 — 여기까지의 결과)"

    if any(outcomes.values()):
        _print_table(entries, outcomes, args.runs)
    if any(axes.values()):
        _print_arguments(entries, axes)
    if any(spoken.values()):
        _print_spoken_values(entries, spoken)
    if any(tallies.values()):
        _print_candidates(entries, tallies)
    if any(times.values()):
        _print_times(entries, times)
    if executions:
        _print_execution(entries, executions, time.strftime("%Y-%m-%d"))
    if note:
        print()
        print(note)

    return status


if __name__ == "__main__":
    sys.exit(main())
