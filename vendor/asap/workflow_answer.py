"""workflow trace 를 사람이 읽는 답으로. **우리 코드다.** 원본에는 없다.

generic_mcp_executor._compose_workflow_answer 가 Gemini 로 답을 다듬던 자리를
대신한다. 우리는 그 키를 쓰지 않고, 무엇보다 **호출 순서가 그대로 보여야 한다** —
지금 증명하려는 것이 "온톨로지가 실행 순서를 정한다" 이기 때문이다. LLM 이 다시
쓰면 순서가 문장에 녹아 사라진다.

여기는 도구 이름을 모른다. trace 의 result 모양만 보고 한 줄을 만든다. 도구가
늘어도 이 파일은 그대로다.

**성공했는지도 여기서 가른다.** 부르는 쪽은 성공과 실패를 모른다 — Gateway 가
실패를 200 + {"error": {...}} 로 돌려주고(asap_probe_out/geo.geocode.
english_notfound.json), mcp_client 가 예외를 안 올리므로 vendor 는 그것을 성공한
호출로 보고 answer_draft 에 성공 문구를 적는다. 판정 근거는 trace 뿐이라 판정도
여기 있다.

**결과 값을 문자열에 담지 않는다.** geojson · cctvUrl · features 의 값이 화면에
raw JSON 으로 새던 자리가 _preview 하나였고 지웠다. 모르는 결과는 칸 이름만
보여준다. 값을 실을 때는 **칸 이름을 미리 정해 두고 길이를 잘라서만** 싣는다 —
모르는 칸은 안 읽으므로 새 도구가 큰 값을 들고 와도 화면에 안 샌다.

**무엇으로 불렀는지도 여기서 적는다.** trace 항목의 input 은 vendor 가 참조
($s1.location)와 어댑터(point_radius_to_bbox)까지 푼 뒤의 실제 호출 인자다.
인자가 잘못 들어갔는지 · 데이터가 없는 것인지 · 도구가 터진 것인지를 사람이
화면만 보고 갈라야 하고, 그 셋 중 첫째는 input 을 안 적으면 알 수가 없다.

**trace 가 아예 없는 자리도 여기서 답한다** (2026-08-29). 사람이 읽는 문구를
한 파일에 모아 두려는 것이다 — 실행이 돌았을 때와 안 돌았을 때의 말투가
갈리면 화면에서 그 둘이 다른 시스템처럼 보인다. 그 자리가 둘이고, 저쪽
plugin 셋이 하는 일이 그것이다. 아래 「도구가 안 돈 자리」 절을 본다.
"""

import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# 단계 줄에서 도구 이름 칸의 전체 폭. 도구 이름은 전부 ASCII 라 ljust 로 맞는다.
TOOL_COLUMN = 18

# 이름이 칸보다 길 때도 요약과 벌어져 있어야 하는 최소 간격.
#
# 실측 : 이름이 42자인 도구가 있다 (election.findAssemblyPledgeDistrictByPoint).
# TOOL_COLUMN 을 거기 맞추면 짧은 이름 쪽이 스무 칸 넘게 빈다.
TOOL_GAP = 2

# 오류 문구를 잘라내는 길이.
SUMMARY_LIMIT = 120

# 판정 셋. 마지막 단계 하나로 갈린다.
SUCCESS = "success"
EMPTY = "empty"
ERROR = "error"

# 빈 결과 · 오류일 때의 첫 줄. 이때는 headline 을 안 쓴다.
#
# headline 은 STEP_OF 가 "{arg} 행정구역을 조회했습니다." 처럼 완결된 한국어
# 문장으로 갖고 있어 부정형으로 바꿀 수 없다. 어미를 문자열로 잘라 고치지
# 않는다 — 문형이 하나 늘 때마다 자르는 규칙이 하나 는다. STEP_OF 를 명사형
# ("{arg} 행정구역")으로 바꾸면 세 문구를 한 틀로 합칠 수 있는데 48줄을 다시
# 쓰는 일이라 이번 범위 밖이다 (NOTES.md).
# 무엇을 조회하려던 것인지는 아래 단계 줄이 말한다.
EMPTY_HEADLINE = "찾지 못했습니다."
ERROR_HEADLINE = "조회하지 못했습니다."

# 실패한 단계 줄의 앞머리. 사유가 뒤에 붙는다.
FAILED_MARK = "실패 · "

# 결과 dict 에서 건수를 세는 칸. 실측으로 본 이름만 둔다.
#
# LIST_KEYS  첫 list 값의 길이. adminBoundary.findBoundaryByPoint 가 features 로
#            돌려준다 (0건 응답 {"features": [], "count": 0, ...} 실측).
#            items · results · data 는 아직 실물을 못 봤고 흔한 이름이라 함께 둔다
# COUNT_KEY  int 일 때만. ev.searchChargers 가 count 100 (실측)
# TOTAL_KEY  ev.searchChargers 가 totalMatches 2195 (실측). count 는 이번에 받은
#            것, totalMatches 는 조건에 맞는 전체다
LIST_KEYS = ("features", "items", "results", "data")
COUNT_KEY = "count"
TOTAL_KEY = "totalMatches"

# 0건일 때 그 이유가 실려 오는 최상위 칸. 실측으로 본 이름만 둔다.
#
# warning   adminBoundary.searchBoundaries · adminBoundary.findBoundaryByPoint
#           election.searchLocalPledgeSummaries              (2026-08-22 실측)
# message   election.getLocalPledgeSummary
#           election.findLocalPledgeSummaryByPoint           (status "not_found" 와 함께)
#
# knowledge.query · knowledge.listDocs · bim.listModels 는 응답이 [] 하나라
# 안내 문장이 실릴 자리가 없다(실측). 그 셋은 0건까지만 나오는 것이 맞고,
# 이유가 안 뜬다고 다시 조사할 것이 아니다.
#
# dev/tools/probe_tools.py 의 find_warning 이 같은 일을 하는데 가져다 쓰지 않는다.
# vendor 가 tools 를 import 하면 의존이 거꾸로 선다. 짧아서 여기 따로 둔다.
NOTICE_KEYS = ("warning", "message")

# 건수와 안내 문장 사이 표시.
NOTICE_JOIN = " · "

# 도구 호출이 터진 사유를 가르는 유일한 영어 조각.
#
# 실측 : web-search/web.search 를 부르면 Gateway 가 500 과 함께
# "MCP tool 'web-search/web.search' is not applied for this user." 를 돌려준다.
# 권한이 없는 것은 사용자가 알아야 할 사실이고, 잠깐 터진 것과 다르다.
NOT_APPLIED = "is not applied for this user"

NO_PERMISSION_REASON = "이 도구를 쓸 권한이 없습니다"
CALL_FAILED_REASON = "도구 호출에 실패했습니다"

# 모양을 못 알아본 결과 · message 가 없는 오류.
UNKNOWN_RESULT = "결과를 받았습니다"
ERROR_WITHOUT_MESSAGE = "오류가 돌아왔습니다"

# 모르는 결과에서 보여줄 최상위 칸 이름의 최대 개수와 그 사이 표시.
KEY_LIMIT = 6
KEY_JOIN = " · "
KEY_PREFIX = "칸: "

# 목록형이 아닌 한 건짜리 응답에서 사람이 볼 것을 고르는 칸 이름. 실측으로 본
# 이름만 둔다. 어느 안을 왜 골랐는지와 언제 뒤집는지는 NOTES.md 「스물셋째」.
#
# NAME_KEY      인구 응답의 "청주시 흥덕구" · election.getDistrict item 의
#               "충북 청주서원"
# TOTAL_PREFIX  대표 수치의 앞토막. totalPopulation 292625 (실측)
# PART_WORDS    대표 수치와 뒤 이름이 같은 곁수치의 앞토막과 그 이름표.
#               malePopulation · femalePopulation (실측)
# SUBJECT_UNITS 뒤 이름의 단위. 여기 없는 수치는 안 보여준다
# DATE_KEY      언제 기준인가. 인구는 기준일마다 값이 통째로 바뀐다
NAME_KEY = "name"
TOTAL_PREFIX = "total"
PART_WORDS = (("male", "남"), ("female", "여"))
SUBJECT_UNITS = {"population": "명"}
DATE_KEY = "referenceDate"

# 한 건 줄의 조각 사이 표시와 기준일 꼬리말.
RECORD_JOIN = " · "
DATE_SUFFIX = " 기준"

# 원문에서 그대로 가져온 값을 감싸는 표시. 인자 값과 본문 첫 대목이 쓴다.
QUOTE = '"{text}"'

# get* 이 여러 건 중 하나를 집어 줄 때 그 한 건이 담겨 오는 칸.
#
# 실측 : election.getDistrict(name="충북") 가 count 1 · totalMatches 8 로
# "충북 청주서원" 하나를 item 에 담아 준다. features 는 비어 있다.
ITEM_KEY = "item"

# 여럿 중 하나를 준 것을 밝히는 문구. totalMatches 가 count 보다 클 때만 쓴다.
ONE_OF_MANY = "전체 {total:,}건 중 하나"

# 응답이 스스로 "없다" 고 말하는 status 값과 그때 쓸 문구. 실측으로 본 값만 둔다.
#
# dev/tools/probe_out 131건 중 최상위 status 칸이 있는 응답이 14건이고 값은 넷이다
# (2026-08-25 실측).
#
#   not_found  10건  election.getDistrict · getAssemblyDistrict ·
#                    getAssemblyPledgeDistrict · getLocalPledgeSummary ·
#                    findLocalPledgeSummaryByPoint.
#                    열 건 모두 최상위 message 를 함께 준다
#   empty       2건  ev.getDatasetInfo · population.getDatasetInfo.
#                    적재된 것이 없다는 뜻이고 message 는 없다
#   syncing     1건  ev.getDatasetInfo. 93,353건이 들어 있고 동기화 중이다
#   ready       1건  population.getDatasetInfo. 정상이다
#
# 뒤의 둘은 안 쓴다. 데이터가 있는 상태라 "없다" 고 말하면 거짓이 된다.
#
# 이 칸을 보는 이유는 건수 칸이 아예 없는 응답이 0건 판정에 안 걸리기
# 때문이다. not_found 응답은 features 도 count 도 없어 _counted 가 None 을
# 내고, 그래서 _notice 가 붙는 길로 안 갔다 — 화면에 "칸: status · message ·
# dataset · query" 만 나왔다 (2026-08-25 화면 실측, NOTES.md 「스물셋째」).
STATUS_KEY = "status"
MISSING_STATUS = {
    "not_found": "찾지 못했습니다",
    "empty": "데이터가 없습니다",
}

# ── 못 찾았을 때의 머리말을 넓히는 것 ─────────────────────────────
#
# 지금까지 0건 · not_found 의 머리말이 EMPTY_HEADLINE 한 줄이었다. 화면이
# "찾지 못했습니다." 만 말하고 **왜 못 찾았는지도 어떻게 말하면 되는지도 없어**
# 사람이 다음에 무엇을 할지 모른다 (2026-08-30 화면 실측).
#
#   찾지 못했습니다.
#     1. election.searchDistricts  query="국회의원 선거구"  0건
#
# **무엇으로 찾았는지는 머리말이 되풀이하지 않는다.** 단계 줄이 이미
# `query="국회의원 선거구"` 를 적는다 (_input_text). 같은 값을 두 줄에 적으면
# 늘어난 줄이 새로 알려주는 것이 없다. 머리말은 단계 줄이 못 말하는 둘을
# 맡는다 — **어디를 뒤졌는가** 와 **어떻게 말하면 되는가** 다.
#
# **낱말을 코드에 안 적는다.** 「마흔아홉째」가 NO_MATCH 안내를 그렇게 만들었다 —
# 이름을 코드에 안 두고 온톨로지에서 뽑아 넘겼다(no_match_answer 의 topics ·
# starts). 여기서도 낱말을 데이터에서 뽑되 **출처가 온톨로지가 아니라 응답이다.**
# 0건은 vendor 가 실패로 안 보므로 답을 generic_mcp_executor 가 (intent, trace)
# 만으로 부르고, vendor 가 ontology 를 import 하면 의존이 거꾸로 선다
# (NOTICE_KEYS 위 주석과 같은 까닭). 자세한 것은 NOTES.md 「쉰다섯째」.
#
# DATASET_KEY       무엇을 뒤졌는지가 실려 오는 최상위 칸.
#                   dev/tools/probe_out 240건 중 101건이 이 칸을 갖고 있다
#                   (2026-08-30 실측)
# DATASET_NAME_KEY  그 안에서 볼 이름. **name 하나만 본다.**
#                   실측 101건 중 85건이 name 을 갖고 값이 사람이 읽는 이름이다
#                   ("2024 제22대 국회의원 선거구" · "한국환경공단 전기자동차
#                   충전소" · "2026 지방선거 시도별 교통 공약 요약" · "시군구").
#                   나머지 16건(adminBoundary 둘)은 name 이 없고 source 만
#                   있는데 그것은 데이터의 출처지 이름이 아니라
#                   ("2026 지방선거 공약 GIS 프로젝트 행정구역 shapefile" ·
#                   "election.shp" · "https://github.com/…") 화면에 낼 것이
#                   아니다. **source 는 안 본다.** 그 도구의 0건은 아래
#                   WHERE_LINE 이 통째로 빠지고 RETRY 만 남는다
# DATASET_NAME_LIMIT 자르는 길이. 아래 SOURCE_LIMIT 과 같은 48 이다 —
#                   둘 다 「」 안에 들어가는 데이터 이름이라 자를 자가 같아야
#                   한다. 상수를 하나로 합치지 않은 것은 SOURCE_LIMIT 이
#                   이 줄보다 아래에 있어서다 (파일 차례를 안 흔든다)
#
# **건수는 안 싣는다.** dataset 안에 featureCount · districtCount 가 있지만
# 단위를 모르는 수치를 이름 옆에 놓으면 딴 뜻으로 읽힌다 — 이 파일이
# _measure_text 에서 이미 겪었다 (totalRegionCount 17 이 충전소 수로 읽혔다).
DATASET_KEY = "dataset"
DATASET_NAME_KEY = "name"
DATASET_NAME_LIMIT = 48

# 어디를 뒤졌는가. dataset 이름이 있을 때만 붙는다.
WHERE_LINE = "찾아본 곳은 {name}입니다."

# 어떻게 말하면 되는가. **0건과 not_found 를 가른다.**
#
# 둘은 뜻이 다르고 사람이 할 일도 다르다.
#
#   0건        검색어로 훑었는데 걸린 것이 없다. 그 낱말이 아무 이름과도
#              안 겹친 것이라 **낱말을 바꾸면** 나올 수 있다
#   not_found  이름을 지정해 집어 오는 호출인데 그 이름이 데이터에 없다.
#              낱말을 바꾸는 것이 아니라 **그 데이터에 있는 이름을 그대로**
#              대야 한다 (election.getDistrict 가 "충북 청주서원" 은 주고
#              "충북 제1선거구" 는 not_found 다 — 2026-08-30 실측)
#
# **status "empty" 에는 안 붙인다.** 그것은 적재된 것이 없다는 뜻이라
# (ev.getDatasetInfo · population.getDatasetInfo, MISSING_STATUS 위 주석)
# 사람이 다시 말해서 될 일이 아니다. 될 리 없는 일을 시키지 않는다.
RETRY_EMPTY = "다른 낱말로 다시 말씀해 주세요."
RETRY_OF_STATUS = {"not_found": "데이터에 있는 이름을 그대로 말씀해 주세요."}

# 머리말 둘째 줄의 조각 사이 표시.
GUIDE_JOIN = " "

# ── 무엇으로 불렀는가 ──────────────────────────────────────────────
#
# trace 항목의 input 은 vendor 가 참조와 어댑터까지 푼 실제 호출 인자다.
#
# 적을 수 있는 것만 적는다. 문자열 · 정수 · 실수만 적고 dict · list 는
# 통째로 건너뛴다. 목록형 인자를 적기 시작하면 bbox 두 겹 · geojson 이
# 화면으로 흘러나오고, 그것이 이 파일이 _preview 를 지운 이유다.
#
# INPUT_KEY_LIMIT  한 줄에 적을 칸 수. 실측 배선의 최대가 넷이다
#                  (road.getCctv · ev.searchStations 의 bbox 넷)
# INPUT_VALUE_LIMIT 문자열 값 하나를 자르는 길이
# COORD_DIGITS     실수의 소수점 자리. _place_line 이 좌표에 쓰는 것과 같다
INPUT_JOIN = " · "
INPUT_FORMAT = "{key}={value}"
INPUT_KEY_LIMIT = 4
INPUT_VALUE_LIMIT = 24
INPUT_MORE = "…"
COORD_DIGITS = 4

# ── 목록의 항목 ──────────────────────────────────────────────────
#
# 건수만으로는 무엇이 왔는지 모른다. knowledge.query 가 본문을 돌려주는데
# 화면에는 "4건" 만 나왔다.
#
# 항목이 글(TEXT_KEYS)인 목록만 앞 두셋을 아래 줄로 늘어놓는다. 조각 하나로는
# "문서에서 내용을 찾아온다" 가 안 보인다. 글이 아닌 목록(CCTV · 행정구역)은
# 예전대로 첫 항목 하나다 — 이름 한 줄이 더 늘어야 알려주는 것이 없다.
# 전부 늘어놓지는 않는다. 화면이 응답 전문이 된다.
# 항목을 요약하는 것은 _record_line 이고 그것은 아래 칸 이름만 읽는다 —
# geojson feature({geometry, properties, type})는 읽을 칸이 하나도 없어
# 조용히 건너뛴다.
#
# TEXT_KEYS         사람이 읽을 글이 담기는 칸.
#                   실측은 content 뿐이다 — knowledge.query 항목이
#                   {content, metadata} 이고 content 가 962~995자다
#                   (2026-08-25 Gateway 직접 호출).
#                   text 는 아직 실물을 못 봤고 흔한 이름이라 함께 둔다
#                   (LIST_KEYS 와 같은 이유)
# TEXT_LIMIT        본문을 자르는 길이. 자른 것은 _clip 이 "…" 로 밝힌다
# SHOWN_RECORDS     글 목록에서 늘어놓을 항목 수. 시연 요구가 "조각 두셋" 이다
# RECORD_INDENT     늘어놓은 항목 줄의 들여쓰기. 단계 번호 "1. " 의 폭이라
#                   단계 줄에 딸린 줄로 읽힌다
# SOURCE_CONTAINER  출처가 담긴 중첩 칸. knowledge.query 의 metadata 다
# SOURCE_KEYS       그 안에서 볼 이름. 실측 : title 은 빈 문자열이고
#                   source 가 "철도안전법(법률)(제21188호)(20260303).pdf" 다.
#                   최상위 source 는 안 본다 — 그쪽은 데이터셋 설명
#                   ("한국환경공단 … 정보 API") 이라 뜻이 다르다
# PAGE_KEY          그 조각이 문서의 몇 쪽인지. SOURCE_CONTAINER 안만 보고
#                   출처 이름이 있을 때만 그 옆에 붙는다
TEXT_KEYS = ("content", "text")
TEXT_LIMIT = 60
SHOWN_RECORDS = 3
RECORD_INDENT = "   "
SOURCE_CONTAINER = "metadata"
SOURCE_KEYS = ("title", "source")
SOURCE_FORMAT = "「{name}」"
SOURCE_LIMIT = 48
PAGE_KEY = "page"
PAGE_FORMAT = "{page}쪽"


def compose_workflow_answer(
    intent: Dict[str, Any],
    trace: List[Dict[str, Any]],
    *,
    failed: bool = False,
) -> str:
    """실행 결과 한 벌을 답으로.

    입력  intent(answer_instruction 이 첫 줄) · vendor 가 쌓은 trace ·
          부르는 쪽이 이미 실패를 알 때의 failed
    출력  첫 줄에 무엇을 했는지, 빈 줄, 그다음 단계 목록
    규칙  성공 · 빈 결과 · 오류 셋으로 가름. 가르는 것은 _verdict 임
          성공이면 첫 줄은 intent.answer_instruction 을 그대로 씀. 노드가 아는
          문장이라 도구 이름으로는 만들 수 없음
          빈 결과 · 오류면 첫 줄을 우리 문구로 바꿔 씀
          빈 결과의 첫 줄은 두 줄일 수 있음. 어디를 뒤졌고 어떻게 말하면
          되는지를 _empty_headline 이 아래에 붙임
          answer_instruction 이 없으면 단계 목록만 남음
          trace 가 비면 단계 목록이 없으므로 첫 줄만 남음
          failed 는 키워드 전용이고 기본이 거짓임. vendor 의
          _compose_workflow_answer 호출부가 안 바뀌어야 함
    """
    verdict = _verdict(trace, failed)
    lines = [f"{index}. {step_line(item)}" for index, item in enumerate(trace, start=1)]

    if verdict == SUCCESS:
        headline = str(intent.get("answer_instruction") or "").strip()
    elif verdict == EMPTY:
        headline = _empty_headline(trace[-1] if trace else {})
    else:
        headline = ERROR_HEADLINE

    if not headline:
        return "\n".join(lines)
    if not lines:
        return headline
    return "\n".join([headline, "", *lines])


def step_failed(item: Dict[str, Any]) -> bool:
    """이 단계가 터졌는가.

    입력  vendor 가 쌓은 trace 항목 하나
    출력  참이면 도구 호출이 실패한 것
    규칙  error 칸이 있으면 참. vendor 가 거기서 멈춘 자리임
          result 가 200 으로 돌아온 오류면 참. Gateway 가 실패를 200 과
          {"error": {...}} 로도 돌려주고 그것은 result 에 담김
          0건은 거짓. 호출은 끝났고 결과가 없는 것뿐임. 답 문구가
          "찾지 못했습니다" 로 이미 말함
    제약  판정을 여러 곳에 흩어 놓지 않는다.
          _outcome · _verdict · demo 의 진행 표시가 전부 이것을 부름.
          200 오류를 안 보는 곳이 하나라도 있으면 그 화면만 "완료" 라고 찍음
    이력  demo 의 진행 표시가 item["error"] 만 봤음. 200 오류는 그 칸이 비어
          있어 화면이 "완료" 로 찍혔고, 그 탓에 "대전~김천 구간이 유효하다" 는
          틀린 사실이 문서에 박혔음. NOTES.md 2026-08-22 넷째의 정정 참고
    """
    return "error" in item or _has_error(item.get("result"))


def step_line(item: Dict[str, Any]) -> str:
    """단계 하나의 줄. 도구 이름 · 무엇으로 불렀는가 · 결과 한 마디.

    규칙  이름이 칸보다 길어도 TOOL_GAP 만큼은 벌림. 안 벌리면 요약과 붙어
          한 낱말로 읽힘 (adminBoundary.findBoundaryByPoint0건)
          짧은 이름의 정렬은 안 달라짐. 칸을 좁힌 만큼 뒤에 다시 붙임
          인자는 도구 이름과 결과 사이. 적을 것이 없으면 그 자리가 통째로
          빠짐. 빈 dict 에 "input: {}" 를 찍지 않음
          결과 줄에 이미 나온 값은 인자로 다시 안 적음. 무엇을 고를지는
          _input_text 임
    """
    tool = str(item.get("tool") or "")
    outcome = _outcome(item)
    given = _input_text(item.get("input"), outcome)
    tail = f"{given}{' ' * TOOL_GAP}{outcome}" if given else outcome
    return f"{tool.ljust(TOOL_COLUMN - TOOL_GAP)}{' ' * TOOL_GAP}{tail}"


def _input_text(tool_input: Any, shown: str) -> str:
    """무엇으로 불렀는지 한 마디. 적을 것이 없으면 "".

    입력  vendor 가 참조와 어댑터까지 푼 실제 호출 인자 · 같은 줄의 결과 문구
    출력  key=value 를 INPUT_JOIN 으로 이은 줄. 칸이 남으면 끝에 INPUT_MORE
    규칙  dict 가 아니면 "". 값이 dict · list · bool · None 인 칸은 건너뜀
          값이 결과 문구에 이미 있으면 건너뜀. geo.geocode 의 query 가
          "오송역 → 주소 (경도, 위도)" 의 앞머리로 이미 나와 있음
          INPUT_KEY_LIMIT 개까지. 넘으면 끝에 INPUT_MORE 를 붙여 밝힘
    제약  값을 통째로 적지 않는다.
          목록 · 중첩 dict 는 안 적고 문자열은 INPUT_VALUE_LIMIT 에서 자른다.
          bbox 두 겹 · geojson 이 화면으로 흘러나오던 자리다
    """
    if not isinstance(tool_input, dict):
        return ""

    parts: List[str] = []
    more = False
    for key, value in tool_input.items():
        pair = _input_pair(value)
        if pair is None:
            continue
        raw, text = pair
        if raw in shown:
            continue
        if len(parts) >= INPUT_KEY_LIMIT:
            more = True
            break
        parts.append(INPUT_FORMAT.format(key=key, value=text))

    if not parts:
        return ""
    return INPUT_JOIN.join(parts) + (INPUT_MORE if more else "")


def _input_pair(value: Any):
    """인자 값 하나의 (겹침을 볼 원문, 화면에 적을 것). 적을 수 없으면 None.

    규칙  bool 은 안 적음. 참·거짓만으로는 무엇을 물었는지 못 말하고 실측
          배선(STEP_OF)에 bool 인자가 없음
          실수는 COORD_DIGITS 자리까지. 배선의 실수는 전부 좌표임
          문자열은 한 줄로 붙이고 INPUT_VALUE_LIMIT 에서 자른 뒤 따옴표
          dict · list · None 은 None 을 냄
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float):
        text = f"{value:.{COORD_DIGITS}f}"
        return text, text
    if isinstance(value, int):
        return str(value), str(value)
    if isinstance(value, str):
        text = " ".join(value.split())
        if not text:
            return None
        return text, QUOTE.format(text=_clip(text, INPUT_VALUE_LIMIT))
    return None


def summarize(tool_input: Any, result: Any) -> str:
    """결과 모양만 보고 한 마디.

    규칙  위에서부터 걸리는 데서 멈춤
          error 칸이 있으면 오류. 200 으로 돌아온 실패가 이 모양임
          배열이면 건수. 0건도 배열임. 첫 항목에서 고를 것이 있으면 함께 냄
          status 가 "없다" 고 말하면 그 사유. 건수 칸이 아예 없는 응답이
          0건 판정에 안 걸려 칸 이름만 나가던 자리임
          location 이 [lon, lat] 이면 주소와 좌표. 어디를 찍었는지 사람이
          알아볼 수 있어야 함
          건수를 세는 칸이 있으면 건수. 0건이고 안내 문장이 있으면 함께 냄.
          한 건이고 그 한 건이 item 에 담겨 있으면 그것을 요약하고, 전체가
          그보다 많으면 여럿 중 하나라는 것을 밝힘
          건수가 없어도 이름 · 수치를 고를 수 있으면 한 건으로 요약함.
          목록형이 아닌 응답(인구)이 여기로 옴
          그 밖에는 최상위 칸 이름만
    제약  결과 값을 문자열에 담지 않는다.
          geojson · cctvUrl · features 가 raw JSON 으로 화면에 새던 자리다.
          값을 실을 때는 미리 정한 칸 이름만 읽고 길이를 자른다
    """
    if _has_error(result):
        return FAILED_MARK + _error_text(result["error"])

    if isinstance(result, list):
        return _list_line(result)

    if isinstance(result, dict):
        missing = _missing_line(result)
        if missing:
            return missing

        point = _lon_lat(result.get("location"))
        if point:
            return _place_line(tool_input, result, point)

        counted = _counted(result)
        if counted:
            return _counted_line(result, *counted)

        record = _record_line(result)
        if record:
            return record

        return _keys_line(result)

    return UNKNOWN_RESULT


def _list_line(items: List[Any]) -> str:
    """배열 결과. 건수와 항목 한 마디 — 항목이 글이면 앞 두셋을 아래 줄로.

    규칙  건수는 늘 냄. 0건도 건수임
          항목이 글이면 앞 SHOWN_RECORDS 개를 건수 아래에 줄마다 늘어놓음.
          어느 목록이 그런지는 _excerpt_lines 가 결과 모양으로 가름
          글이 아니면 첫 항목 한 마디만. 예전 그대로임
          첫 항목에서 고를 것이 없으면 건수만. geojson feature 가 그럼
    이력  첫 항목 하나만 봤음. knowledge.query 조각 두셋을 보여주는 시연
          요구가 생겨 글 목록만 늘렸음 (2026-08-26, NOTES.md 「서른한째」)
    """
    line = f"{len(items)}건"
    excerpts = _excerpt_lines(items)
    if excerpts:
        return "\n".join([line, *excerpts])
    first = _record_line(items[0]) if items else ""
    return line + RECORD_JOIN + first if first else line


def _excerpt_lines(items: List[Any]) -> List[str]:
    """항목이 글인 목록의 앞 두셋 줄. 글 목록이 아니면 빈 목록.

    규칙  글 목록인지는 첫 항목으로 가름. dict 이고 TEXT_KEYS 글이 있어야 함.
          도구 이름이 아니라 결과 모양으로 가르는 것이 이 파일의 계약임
          앞 SHOWN_RECORDS 개만. 항목마다 _record_line 한 줄이고 고를 것이
          없는 항목은 건너뜀
          줄 앞에 RECORD_INDENT 를 붙여 단계 줄에 딸린 줄로 보이게 함
    제약  값을 통째로 싣지 않는다. _record_line 이 정해 둔 칸만 읽고
          길이를 자른다
    """
    if not items or not isinstance(items[0], dict) or not _excerpt(items[0]):
        return []

    lines = []
    for record in items[:SHOWN_RECORDS]:
        line = _record_line(record)
        if line:
            lines.append(RECORD_INDENT + line)
    return lines


def _missing_status(result: Any) -> str:
    """응답의 status 가 "없다" 고 말하면 그 값. 아니면 "".

    규칙  최상위 status 만 봄. dataset.status 처럼 중첩된 것은 안 봄
          MISSING_STATUS 에 있는 값만. ready · syncing 은 데이터가 있는
          상태라 안 걸림
    """
    if not isinstance(result, dict):
        return ""
    status = result.get(STATUS_KEY)
    return status if isinstance(status, str) and status in MISSING_STATUS else ""


def _missing_line(result: Dict[str, Any]) -> str:
    """못 찾았다는 응답 한 줄. 그런 응답이 아니면 "".

    규칙  응답이 제 사유를 실어 보냈으면 그것을 그대로 씀. 우리 문구보다
          무엇을 어디서 못 찾았는지를 말함 ("조건에 맞는 선거구를 찾지
          못했습니다.")
          사유가 없으면 status 값에 매인 우리 문구. ev.getDatasetInfo 의
          empty 가 그럼
    """
    status = _missing_status(result)
    if not status:
        return ""
    return _notice(result) or MISSING_STATUS[status]


def _empty_headline(item: Dict[str, Any]) -> str:
    """못 찾았을 때의 첫 줄. 붙일 것이 있으면 두 줄.

    입력  빈 결과 판정을 낸 마지막 trace 항목. trace 가 비면 빈 dict
    출력  EMPTY_HEADLINE 한 줄, 또는 그 아래 안내 한 줄이 더 붙은 두 줄
    규칙  첫 줄은 늘 EMPTY_HEADLINE 임. 판정이 그 줄이고 안 바뀜
          둘째 줄은 어디를 뒤졌는가와 어떻게 말하면 되는가를 이은 것임.
          둘 다 없으면 둘째 줄이 통째로 빠져 지금까지와 같은 한 줄이 됨
          어디를 뒤졌는가는 응답이 들고 온 데이터 이름임. 없으면 그 칸이 빠짐
          어떻게 말하면 되는가는 _retry_line 이 고름. 사람이 다시 말해서
          될 일이 아니면 빈 문자열을 냄
    제약  무엇으로 찾았는지를 여기 안 적는다.
          단계 줄이 이미 인자를 적음. 같은 값을 두 줄에 적지 않음
    """
    result = item.get("result")

    parts = []
    name = _dataset_name(result)
    if name:
        parts.append(WHERE_LINE.format(name=SOURCE_FORMAT.format(name=name)))

    retry = _retry_line(item)
    if retry:
        parts.append(retry)

    if not parts:
        return EMPTY_HEADLINE
    return EMPTY_HEADLINE + "\n" + GUIDE_JOIN.join(parts)


def _dataset_name(result: Any) -> str:
    """무엇을 뒤졌는지 응답이 밝힌 이름. 없으면 "".

    규칙  최상위 DATASET_KEY 안의 DATASET_NAME_KEY 하나만 봄
          문자열이 아니거나 비어 있으면 ""
          DATASET_NAME_LIMIT 에서 자름. 자른 것은 _clip 이 밝힘
    제약  같은 칸의 다른 이름을 대신 쓰지 않는다.
          source 는 데이터의 출처지 사람이 읽을 이름이 아님
    """
    if not isinstance(result, dict):
        return ""

    dataset = result.get(DATASET_KEY)
    if not isinstance(dataset, dict):
        return ""

    value = dataset.get(DATASET_NAME_KEY)
    if not isinstance(value, str) or not value.strip():
        return ""
    return _clip(value, DATASET_NAME_LIMIT)


def _retry_line(item: Dict[str, Any]) -> str:
    """어떻게 말하면 되는지 한 마디. 댈 것이 없으면 "".

    입력  빈 결과 판정을 낸 trace 항목
    출력  다시 말하는 법 한 문장
    규칙  그 단계를 글자로 부른 것이 아니면 "". 좌표 · 번호로만 부른
          호출은 사람이 고쳐 말할 낱말이 그 단계에 없음
          응답이 status 로 "없다" 고 말했으면 RETRY_OF_STATUS 를 봄.
          거기 없는 status 는 "" — empty 가 그럼
          status 가 없는 0건은 RETRY_EMPTY
    제약  예시 값을 지어내지 않는다.
          무엇이 데이터에 있는지 이 파일은 모름. 있는 이름을 대라고만 함
    """
    if not _called_with_words(item.get("input")):
        return ""

    status = _missing_status(item.get("result"))
    if status:
        return RETRY_OF_STATUS.get(status, "")
    return RETRY_EMPTY


def _called_with_words(tool_input: Any) -> bool:
    """그 단계를 사람의 낱말로 불렀는가.

    출력  참이면 인자에 글자 값이 하나라도 있음
    규칙  최상위 값만 봄. 문자열이고 비어 있지 않아야 함
          숫자 · bool · dict · list 는 안 셈. 좌표 두 개로 부른 호출은
          거짓임
    """
    if not isinstance(tool_input, dict):
        return False
    return any(
        isinstance(value, str) and value.strip() for value in tool_input.values()
    )


def _verdict(trace: List[Dict[str, Any]], failed: bool) -> str:
    """이 실행이 성공인가 빈 결과인가 오류인가.

    입력  vendor 가 쌓은 trace · 부르는 쪽이 이미 아는 실패 여부
    출력  SUCCESS · EMPTY · ERROR 중 하나
    규칙  failed 가 참이면 오류. vendor 는 중단할 때 대개 trace 에 아무것도
          안 남기므로 trace 만으로는 못 가름
          어느 항목이든 step_failed 면 오류. 200 으로 돌아온 오류도 거기서 걸림.
          다음 도구가 그 칸을 optional 로 받으면 vendor 가 끝까지 돌고
          errors 도 비어 있음
          trace 가 비면 오류. 한 단계도 안 돌았음
          마지막 항목의 센 건수가 0이면 빈 결과. 발화에 답하는 것은 마지막임
          마지막 항목의 status 가 "없다" 고 말해도 빈 결과. 건수 칸이 아예
          없는 응답이라 위 줄에 안 걸림
          그 밖은 성공
    """
    if failed:
        return ERROR

    for item in trace:
        if step_failed(item):
            return ERROR

    if not trace:
        return ERROR

    last = trace[-1].get("result")
    counted = _counted(last)
    if counted and counted[0] == 0:
        return EMPTY
    if _missing_status(last):
        return EMPTY

    return SUCCESS


def _outcome(item: Dict[str, Any]) -> str:
    """단계 줄의 뒷부분. 실패한 단계면 사유, 아니면 결과 한 마디.

    규칙  실패인지는 step_failed 가 가름. 여기서 따로 판정하지 않음
          실패 모양이 둘임. error 칸이 있으면 vendor 가 거기서 멈춘 것이라
          result 가 없고 _failure_reason 이 사유를 씀
          200 오류는 사유가 result 안에 있어 summarize 가 씀.
          둘 다 앞에 FAILED_MARK 가 붙음
    """
    if step_failed(item) and "error" in item:
        return FAILED_MARK + _failure_reason(item)
    return summarize(item.get("input"), item.get("result"))


def _failure_reason(item: Dict[str, Any]) -> str:
    """실패한 단계의 사유 한 마디.

    입력  error 칸이 있는 trace 항목
    출력  사람에게 보일 사유
    규칙  error_detail 이 있으면 도구 호출 자체가 터진 것. 원문을 화면에 안 냄.
          HTTP 오류 문장 · 내부 URL · Gateway 응답 본문이 그대로 들어 있음.
          vendor 가 이미 logger.error 로 남겼음
          error_detail 이 없으면 우리가 입력을 못 채운 것. vendor 가 쓴 문장에
          필드 이름밖에 없어 그대로 보여도 안전함. 앞의 "{step_id} 단계 "
          접두만 뗌. 사람에게 step id 는 뜻이 없음
    제약  vendor 의 한국어 문구를 문자열로 보지 않는다.
          저쪽이 문구를 갱신하면 조용히 깨진다. 항목의 구조로 가른다
    """
    detail = item.get("error_detail")
    if detail:
        if NOT_APPLIED in str(detail):
            return NO_PERMISSION_REASON
        return CALL_FAILED_REASON

    message = str(item.get("error") or "")
    return _clip(_without_step_prefix(message, item.get("id"))) or CALL_FAILED_REASON


def _without_step_prefix(message: str, step_id: Any) -> str:
    """vendor 문장 앞의 "{step_id} 단계 " 를 뗌. 없으면 그대로."""
    prefix = f"{step_id} 단계 "
    if step_id and message.startswith(prefix):
        return message[len(prefix):]
    return message


def _place_line(tool_input: Any, result: Dict[str, Any], point: Tuple[float, float]) -> str:
    """좌표를 찍은 결과 한 줄.

    규칙  주소를 반드시 보여줌. 좌표만 보이면 엉뚱한 곳을 찍어도 사람이
          알아챌 방법이 없음. "오송시" 가 경상남도 거제시 동부면 오송리를
          찍은 일이 있음
          주소가 없으면 그 칸을 뺌. query 가 없으면 그 칸을 뺌
    """
    query = tool_input.get("query") if isinstance(tool_input, dict) else None
    address = result.get("address")

    coordinates = f"({point[0]:.4f}, {point[1]:.4f})"
    tail = f"{address} {coordinates}" if address else coordinates
    return f"{query} → {tail}" if query else tail


def _count_line(count: int, total: Optional[int], notice: str = "") -> str:
    """건수 한 줄. 받은 것과 전체가 다르면 둘 다. 안내 문장이 있으면 뒤에 붙임.

    규칙  안내 문장은 0건일 때만 옴. 부르는 쪽이 가름
          빈 문자열이면 안 붙임. "0건 · " 만 남으면 안 됨
    """
    if total is not None and total != count:
        line = f"{count}건 (전체 {total:,}건)"
    else:
        line = f"{count}건"

    return line + NOTICE_JOIN + notice if notice else line


def _counted_line(result: Dict[str, Any], count: int, total: Optional[int]) -> str:
    """건수를 센 결과 한 줄.

    입력  결과 dict · 보여줄 건수 · 전체 건수(없으면 None)
    출력  건수 줄. 한 건을 집어 준 것이면 그 한 건의 요약
    규칙  0건이면 안내 문장을 함께 냄. 건수가 있으면 안 냄 — 답이 나온 자리에
          warning 을 붙이면 사람이 헷갈림
          한 건이고 item 에 그 한 건이 담겨 있고 거기서 이름이나 수치를 고를 수
          있으면 건수 대신 그것을 보여줌. "1건" 은 무엇을 받았는지 안 말함
          전체가 받은 것보다 많으면 여럿 중 하나라는 것을 밝힘. 여덟 중 하나를
          확신에 찬 한 줄로 주면 사람은 그것이 전부인 줄 앎
          totalMatches 를 안 주는 도구가 있음. 없으면 조용히 넘어감
          item 이 없으면 센 목록의 첫 항목을 봄. 건수 뒤에 붙임 — 그것은
          여럿 중 첫째라 건수를 대신할 수 없음
    """
    if count == 0:
        return _count_line(count, total, notice=_notice(result))

    record = _record_line(result.get(ITEM_KEY)) if count == 1 else ""
    if not record:
        first = _first_record(result)
        line = _count_line(count, total)
        return line + RECORD_JOIN + first if first else line

    if total is not None and total > count:
        return record + RECORD_JOIN + ONE_OF_MANY.format(total=total)
    return record + RECORD_JOIN + _count_line(count, total)


def _record_line(record: Any) -> str:
    """한 건에서 사람이 볼 것만 골라 한 줄로. 고를 것이 없으면 "".

    입력  결과 dict 하나 (응답 전체이거나 그 안의 item 이거나 목록의 첫 항목)
    출력  이름 · 수치 · 출처 · 본문 · 기준일을 이어 붙인 줄
    규칙  이름 · 수치 · 출처 · 본문 중 하나는 있어야 함. 기준일만 있는 줄은
          안 만듦 — 무엇의 기준일인지 말하지 않으므로 칸 이름을 찍는 것만 못함
          없는 칸은 뺌. 지어내지 않음
          읽는 칸이 정해져 있음. geojson feature({geometry, properties,
          type})는 하나도 안 걸려 ""
    제약  값을 고를 뿐 만들지 않는다. 응답에 없는 칸은 안 읽는다
          본문은 통째로 안 싣는다. TEXT_LIMIT 에서 자르고 잘랐다고 밝힌다
    """
    if not isinstance(record, dict):
        return ""

    name = record.get(NAME_KEY)
    name = name.strip() if isinstance(name, str) else ""
    measure = _measure_text(record)

    parts = []
    if name and measure:
        parts.append(f"{name} {measure}")
    elif name or measure:
        parts.append(name or measure)

    source = _source_name(record)
    if source:
        quoted = SOURCE_FORMAT.format(name=source)
        page = _page_text(record)
        parts.append(f"{quoted} {page}" if page else quoted)

    excerpt = _excerpt(record)
    if excerpt:
        parts.append(excerpt)

    if not parts:
        return ""

    date = record.get(DATE_KEY)
    if isinstance(date, str) and date.strip():
        parts.append(date.strip() + DATE_SUFFIX)
    return RECORD_JOIN.join(parts)


def _source_name(record: Dict[str, Any]) -> str:
    """이 한 건이 어디서 왔는지. 없으면 "".

    규칙  SOURCE_CONTAINER 안만 봄. 최상위 source 는 데이터셋 설명이라
          뜻이 다름
          SOURCE_KEYS 를 순서대로 봄. 먼저 걸리는 것 하나만 씀
          SOURCE_LIMIT 에서 자름
    """
    container = record.get(SOURCE_CONTAINER)
    if not isinstance(container, dict):
        return ""

    for key in SOURCE_KEYS:
        value = container.get(key)
        if isinstance(value, str) and value.strip():
            return _clip(value, SOURCE_LIMIT)
    return ""


def _page_text(record: Dict[str, Any]) -> str:
    """이 한 건이 문서의 몇 쪽에서 왔는지. 없으면 "".

    규칙  SOURCE_CONTAINER 안의 PAGE_KEY 만 봄. 최상위 page 는 실물을 못 봤음
          int 로 못 읽는 값은 조용히 넘어감. 정수로도 "0" 같은 문자열로도
          온 실물이 있음 (2026-08-25 · 2026-08-26 실측)
          응답의 page 는 0부터 셈. 사람이 세는 쪽수로 1을 더해 냄.
          실측 : page 0 조각의 본문 머리가 "1", page 50 조각이 "51"
          (2026-08-26, dev/tools/probe_out 의 knowledge.query 응답 전문)
    """
    container = record.get(SOURCE_CONTAINER)
    if not isinstance(container, dict):
        return ""

    value = container.get(PAGE_KEY)
    if isinstance(value, bool):
        return ""
    try:
        page = int(value)
    except (TypeError, ValueError):
        return ""
    return PAGE_FORMAT.format(page=page + 1)


def _excerpt(record: Dict[str, Any]) -> str:
    """사람이 읽을 글의 첫 대목. 없으면 "".

    규칙  TEXT_KEYS 를 순서대로 봄. 먼저 걸리는 것 하나만 씀
          최상위만 봄. 문자열이 아니면 무시함
          TEXT_LIMIT 에서 자름. 자른 것은 _clip 이 밝힘
    제약  칸 이름을 모르는 값은 안 읽는다.
          "긴 문자열이면 글" 로 고르면 base64 · geojson 문자열이 그대로
          화면에 나간다
    """
    for key in TEXT_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return QUOTE.format(text=_clip(value, TEXT_LIMIT))
    return ""


def _measure_text(record: Dict[str, Any]) -> str:
    """대표 수치와 곁수치 한 마디. 고를 것이 없으면 "".

    규칙  대표 수치를 고르는 것은 _total_field 임. 단위를 모르는 수치는 안 씀 —
          무엇의 수인지 못 말하는 숫자를 이름 옆에 놓으면 딴 뜻으로 읽힘.
          실측 : ev.getDatasetInfo 의 totalRegionCount 17 이 충전소 수로 읽힘
          곁수치는 뒤 이름이 같고 앞토막이 PART_WORDS 에 있는 칸.
          사전에 없는 앞토막은 안 보여줌
    """
    found = _total_field(record)
    if not found:
        return ""

    subject, value = found

    parts = []
    for prefix, word in PART_WORDS:
        part = _int_value(record.get(prefix + subject))
        if part is not None:
            parts.append(f"{word} {part:,}")

    text = f"{value:,}{SUBJECT_UNITS[subject.lower()]}"
    return f"{text} ({RECORD_JOIN.join(parts)})" if parts else text


def _total_field(record: Dict[str, Any]):
    """쓸 수 있는 대표 수치의 (뒤 이름, 값). 없으면 None.

    규칙  TOTAL_PREFIX 로 시작하고 뒤가 대문자로 시작해야 함 — total 하나뿐인
          칸은 무엇의 합인지 모름
          정수여야 함. 뒤 이름이 SUBJECT_UNITS 에 있어야 함
          먼저 걸리는 것 하나만 씀
    """
    for key, value in record.items():
        if not isinstance(key, str) or not key.startswith(TOTAL_PREFIX):
            continue
        subject = key[len(TOTAL_PREFIX):]
        if not subject[:1].isupper() or subject.lower() not in SUBJECT_UNITS:
            continue
        number = _int_value(value)
        if number is not None:
            return subject, number
    return None


def _notice(result: Dict[str, Any]) -> str:
    """0건의 이유로 응답에 실려 온 안내 문장. 없으면 "".

    규칙  NOTICE_KEYS 를 순서대로 봄. 먼저 걸리는 것 하나만 씀
          최상위만 봄. dataset.message 처럼 중첩된 것은 안 봄
          문자열이 아니면 무시함
          SUMMARY_LIMIT 에서 자름
    """
    for key in NOTICE_KEYS:
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return _clip(value)
    return ""


def _keys_line(result: Dict[str, Any]) -> str:
    """모르는 결과를 칸 이름만으로. 이름도 없으면 받았다는 말만."""
    names = [str(name) for name in list(result)[:KEY_LIMIT]]
    if not names:
        return UNKNOWN_RESULT
    return KEY_PREFIX + KEY_JOIN.join(names)


def _has_error(result: Any) -> bool:
    """200 으로 돌아온 실패인가.

    출력  참이면 Gateway 가 오류를 본문에 담아 보낸 것
    규칙  mcp_client 가 예외를 안 올리므로 vendor 는 이것을 성공으로 봄.
          가르는 곳이 여기뿐임
    """
    return isinstance(result, dict) and "error" in result


def _error_text(error: Any) -> str:
    """오류 칸을 한 줄로.

    규칙  dict 면 message 만 씀. 코드와 나머지 칸은 사람이 읽을 것이 아님
          문자열이면 그대로
          message 가 없으면 오류라는 사실만 알림
    """
    if isinstance(error, dict):
        text = str(error.get("message") or "").strip()
    else:
        text = str(error or "").strip()

    return _clip(text) if text else ERROR_WITHOUT_MESSAGE


def _clip(text: str, limit: int = SUMMARY_LIMIT) -> str:
    """한 줄로 붙이고 limit 에서 자름. 자르면 끝에 "…" 를 붙여 밝힘.

    규칙  줄바꿈 · 잇단 공백을 한 칸으로 붙임. PDF 본문이 공백 수십 칸을
          달고 옴 (knowledge.query 실측)
          한글은 낱자를 NFC 로 붙인 뒤에 잼. 실측 : knowledge.query 의
          source 가 낱자로 풀린(NFD) 한글이라 눈에 41자인 문서 이름이
          len 67 로 세져 48 한도에서 어중간하게 잘렸음 (2026-08-26 화면,
          dev/tools/probe_out 의 응답 전문)
    """
    text = unicodedata.normalize("NFC", " ".join(text.split()))
    return text if len(text) <= limit else text[:limit] + "…"


def _counted(result: Any):
    """건수를 셀 수 있으면 (보여줄 건수, 전체 건수). 못 세면 None.

    출력  전체 건수는 count 와 totalMatches 가 함께 있을 때만 채워짐
    규칙  배열은 길이. dict 는 count 가 int 일 때 그것, 아니면 LIST_KEYS 중
          먼저 나오는 list 의 길이
          셀 칸이 하나도 없으면 None. 건수가 아닌 dict 를 0건이라고 하면 안 됨
    """
    if isinstance(result, list):
        return len(result), None

    if not isinstance(result, dict):
        return None

    count = _int_value(result.get(COUNT_KEY))
    if count is None:
        length = _first_list_length(result)
        return (length, None) if length is not None else None

    return count, _int_value(result.get(TOTAL_KEY))


def _first_list_length(result: Dict[str, Any]) -> Optional[int]:
    """LIST_KEYS 중 먼저 나오는 list 의 길이. 없으면 None."""
    for key in LIST_KEYS:
        value = result.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _first_record(result: Dict[str, Any]) -> str:
    """센 목록의 첫 항목 한 마디. 고를 것이 없으면 "".

    규칙  LIST_KEYS 를 순서대로 보고 고를 것이 나오는 첫 목록을 씀.
          _first_list_length 와 달리 먼저 걸리는 목록에서 멈추지 않음
          한 응답이 목록을 둘 담아 오고 첫째가 비어 있음 (실측 :
          adminBoundary.findBoundaryByPoint 가 features 0건 · items 3건,
          election.searchDistricts 가 features 0건 · items 254건).
          features 에서 멈추면 이름이 있는 items 를 못 봄
    제약  최상위만 본다.
          geojson.features 처럼 중첩된 목록은 안 들어간다. 그 안은 좌표
          덩어리이고 화면에 낼 것이 아니다
    """
    for key in LIST_KEYS:
        value = result.get(key)
        if not isinstance(value, list) or not value:
            continue
        record = _record_line(value[0])
        if record:
            return record
    return ""


def _int_value(value: Any) -> Optional[int]:
    """int 면 그것. 아니면 None. bool 은 int 가 아닌 것으로 봄."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _lon_lat(value: Any):
    """[lon, lat] 이면 그 둘. 아니면 None."""
    if not isinstance(value, list) or len(value) < 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


# ── 도구가 안 돈 자리 ────────────────────────────────────────────────
#
# 여기까지 오는 자리가 둘이고 둘 다 trace 가 없다. 단계 목록을 못 만든다.
#
#   지도 명령만 낸 실행     부를 도구가 없는 노드가 경로의 전부였다
#   부를 것이 없는 발화     온톨로지에 맞는 경로가 없다 (NO_MATCH)
#
# 저쪽 plugin 셋이 그 자리다. 아홉 개 plugin 에는 다 있는 `## Run` 절이
# show-facility · system-chat · unsupported-request 셋에만 없다
# (KRRI_ASAP/ASAP-orchestrator/plugins/. 읽기만 했다).
#
# **여기도 도구 이름을 모른다.** 아래 둘은 문자열만 받는다.

# 지도 명령만 낸 실행의 답. headline 이 비었을 때만 쓴다.
#
# headline 은 배선표(step_service.TOOL_OF)가 갖고 있고 인자가 들어간 문장이라
# ("오송 테스트트랙 시설물을 화면에 띄웠습니다") 이 자리보다 늘 낫다.
NOTHING_RAN = "화면에 표시했습니다."

# 맞는 경로가 없을 때의 첫 줄.
#
# **문구를 안 바꿨다.** demo/api/services/execute_service.py 의 NO_MATCH_ANSWER
# 에 있던 것을 글자 그대로 옮겼다.
NO_MATCH_HEADLINE = "지금 할 수 있는 일 중에 맞는 것이 없습니다."

# 그 뒤에 붙는 안내 두 줄.
#
# **낱말은 온톨로지가 댄다.** 여기는 틀만 갖는다 — 노드를 등록하면 안내도 함께
# 늘고, 두 곳이 어긋날 자리가 없다. 저쪽 unsupported-request 의 답은 고정 문구
# 한 줄이라("죄송합니다. 현재 지원하지 않는 요청입니다") 무엇을 대신 말해야
# 할지는 안 알려준다.
NO_MATCH_TOPICS = "제가 다루는 것은 {topics}입니다."
NO_MATCH_STARTS = "{starts} 가운데 하나를 함께 말씀해 주세요."

# 이름을 늘어놓을 때의 사이. 답 문구가 쓰는 다른 구분자와 같다.
NAME_JOIN = " · "


def command_answer(headline: str) -> str:
    """도구를 안 부르고 지도 명령만 낸 실행의 답.

    입력  배선표가 만든 답 첫 줄. 없으면 빈 문자열
    출력  화면에 그대로 나갈 한 줄
    규칙  단계 목록이 없으므로 첫 줄이 곧 답 전부임
          headline 이 비면 대비 문구를 씀
    제약  무엇을 냈는지 op 이름으로 적지 않는다.
          사람에게 뜻이 없고, 이 파일은 부르는 쪽이 무엇을 부르는지 모른다
    """
    return headline.strip() or NOTHING_RAN


def no_match_answer(reason: str, topics: List[str], starts: List[str]) -> str:
    """맞는 경로가 없을 때의 답.

    입력  발화 해석이 적은 이유 · 온톨로지의 대상 이름 · 시작 데이터 이름
    출력  첫 줄, 빈 줄, 이유, 빈 줄, 안내 두 줄
    규칙  이유가 비면 그 칸이 통째로 빠짐. 빈 줄만 남지 않음
          이름 목록이 비면 그 안내 줄도 빠짐. 온톨로지가 비었을 때 틀만
          남아 "제가 다루는 것은입니다" 가 되지 않아야 함
    """
    blocks = [NO_MATCH_HEADLINE]

    if reason.strip():
        blocks.append(reason.strip())

    guide = []
    if topics:
        guide.append(NO_MATCH_TOPICS.format(topics=NAME_JOIN.join(topics)))
    if starts:
        guide.append(NO_MATCH_STARTS.format(starts=NAME_JOIN.join(starts)))
    if guide:
        blocks.append("\n".join(guide))

    return "\n\n".join(blocks)
