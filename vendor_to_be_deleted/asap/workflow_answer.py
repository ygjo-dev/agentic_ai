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

**읽는 사람이 기자와 일반 독자로 바뀌었다** (2026-09-01, feature/accessibility).
지금까지 이 파일이 적어 온 것은 「우리가 화면만 보고 무엇이 틀렸는지 가른다」
였다 — 도구 이름 · 호출 인자 · 모르는 결과의 칸 이름이 그 자리였다. 보도자료
그림에 실릴 화면은 그 셋을 읽을 사람이 아무도 없다. 세 가지가 바뀌었다.

  단계 이름   도구 이름(geo.geocode) 대신 **온톨로지 노드의 name**
              (「장소 좌표 변환」). 부르는 쪽이 step 에 실어 보내고 여기는
              그것을 쓰기만 한다 — 이 파일은 여전히 도구 이름을 모르고,
              48개 노드가 한 자리에서 같은 규칙으로 갈린다
  호출 인자   칸 이름을 늘어놓지 않는다. 사람이 읽을 조건만 적는다
              (수단 · 출발 시각 · 발화에서 온 낱말). 무엇을 적을지는
              **칸 이름을 미리 정해 두고** 고른다 — 결과 쪽에서 이 파일이
              이미 하던 것과 같은 방식이다
  좌표        경위도 숫자를 화면에 안 낸다. 주소는 남긴다 — 엉뚱한 곳을
              찍었는지는 주소로 알아본다("오송시" 가 거제시 오송리를 찍은 일)

**되돌리는 자리를 좁혀 뒀다.** 셋 다 상수와 작은 함수로 갈라 두었고, 판정
(_verdict · step_failed)과 결과 요약(_counted · _record_line)은 손대지 않았다.
"""

import math
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# ── 단계 줄의 이름 ──────────────────────────────────────────────
#
# **이름은 부르는 쪽이 실어 보낸다.** step 에 얹힌 칸 하나를 읽을 뿐이고,
# 그 값의 원천은 온톨로지의 노드 name 이다 (execution/step_service.STEP_NAME).
# 이 파일은 여전히 도구 이름을 모르고, 노드가 늘어도 여기는 그대로다.
#
# 없으면 도구 이름으로 되돌아간다. 이름을 안 실어 보내는 부르는 쪽이 있고
# (시험이 step_line 을 직접 부른다) 그때 이름 자리가 통째로 비면 어느 단계가
# 무엇이었는지 아무것도 안 남는다.
STEP_NAME_KEY = "name"

# 줄바꿈과 딸린 줄의 들여쓰기. **이 파일의 줄나눔은 전부 이 둘로 만든다.**
#
# ITEM_INDENT 는 목록 기호 "- " 의 폭이라 들여 쓴 줄이 바로 위 항목에 딸린
# 줄로 읽힌다 — CommonMark 가 그 줄을 <li> 안에 담는다. 아래 「목록의 항목」
# 절도 같은 것을 쓴다.
BELOW = "\n"
ITEM_INDENT = "  "

# 한 항목 안에서 줄을 바꿀 때 쓰는 표시. **딸린 줄을 들여 쓴다.**
#
# 동 목록이 이것을 쓴다 — 시군구 묶음마다 줄을 바꾸는데 그 줄들이 한
# 「행정동」 항목 안에 머물러야 한다. 목록 기호의 폭만큼 들여 쓰면
# CommonMark 가 그 줄을 <li> 안에 담는다.
#
# 그 앞의 이력 — 단계 이름과 값을 " — " 로 한 줄에 잇던 것을 걷고 (2026-09-02
# 「여든다섯째」), 칸 폭(18)으로 줄을 맞추던 것을 걷은 자리이기도 하다.
# 한글은 한 글자가 두 칸이라 글자 수로 ljust 하면 오히려 어긋난다.
STEP_JOIN = BELOW + ITEM_INDENT

# ── 이름표 ───────────────────────────────────────────────────────
#
# **줄은 갈렸는데 무엇을 말하는 값인지가 안 보였다** (2026-09-02 보도자료
# 그림 2). 「29.96 km²」 · 「54만 명」이 이름 없이 나란히 서 있어 화면이
# 평평했다. 값마다 이름표를 앞에 놓고 굵게 해 눈이 왼쪽에 걸리게 한다.
#
# 저쪽이 react-markdown 을 플러그인 없이 쓴다 (MARKDOWN_BREAK 문단).
# 그래서 여기 쓰는 표시는 CommonMark 에 있는 것뿐이다 — 굵게(**), 목록(-).
#
#   STEP_HEAD    단계 제목. **굵게 감싸 번호를 우리가 매긴다.** 감싸지 않으면
#                "1. " 로 시작하는 줄이라 CommonMark 가 <ol> 로 읽고 저쪽이
#                번호를 다시 매긴다. 그때는 우리가 쓴 번호가 화면에 안 남는다
#   ITEM_MARK    값 한 줄. 목록 점이 나온다
#   LABEL        이름표. 값과의 사이는 " : " 다
#   FIGURE       수치 값을 굵게. 면적과 인구 넷뿐이다 (아래 _figure)
#
# **단계 사이에 빈 줄이 있어야 한다.** 없으면 다음 단계 제목이 바로 위 목록의
# 딸린 줄로 읽혀 <li> 안으로 빨려 들어간다 (markdown-it commonmark 실측).
STEP_HEAD = "**{number}. {name}**"
NUMBER_HEAD = "**{number}.**"
ITEM_MARK = "- "
LABEL = "**{label}** : "
FIGURE = "**{text}**"
STEP_GAP = BELOW + BELOW

# 값에 붙는 이름표. 이 답에 나오는 여섯 자리다.
LABEL_QUERY = "입력"
LABEL_ADDRESS = "좌표"
LABEL_AREA = "면적"
LABEL_AREA_REFERENCE = "비교"
LABEL_DISTRICTS = "행정동"
LABEL_POPULATION = "인구"

# 줄 끝에 붙여 마크다운에서 줄바꿈을 살리는 표시. **공백 둘이다.**
#
# 저쪽 화면(ASAP-web packages/chat/src/components/ChatPanel.tsx)이 답을
# `<ReactMarkdown>{msg.text}</ReactMarkdown>` 로 그린다. react-markdown 10 을
# 플러그인 없이 쓰므로 CommonMark 그대로이고, **줄바꿈 하나는 공백이 된다** —
# 우리가 나눈 줄이 저쪽에서 한 줄로 붙는다 (2026-09-02 실측).
#
# CommonMark 에서 줄바꿈을 살리는 길이 셋이고 이것을 골랐다.
#
#   공백 둘      <br> 하나. 줄 간격이 안 벌어지고 글자가 하나도 안 바뀐다
#   빈 줄        문단이 나뉘어 줄 사이가 벌어진다
#   목록 기호    "- " 가 화면에 목록 점으로 나간다
#
# **셋 다 쓰고 있다.** 한 단계 안의 줄은 공백 둘, 단계와 단계 사이는 빈 줄
# (STEP_GAP), 값 줄은 목록 기호(ITEM_MARK)다. 2026-09-02 에 공백 둘 하나만
# 골랐던 자리인데, 그때 목록 기호를 물린 까닭("답의 낱말이 바뀐다")은 이름표를
# 넣으면서 값이 목록의 항목이 되어 없어졌다.
#
# **답을 짓는 쪽은 이것을 모른다.** 줄은 BELOW 로만 나누고, 내보내기 직전에
# _for_markdown 이 한 번 얹는다. 저쪽 화면이 마크다운을 안 쓰게 되면 그
# 함수 하나만 걷는다.
MARKDOWN_BREAK = "  "

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

# 좌표는 왔는데 주소가 없을 때의 한 마디.
#
# 좌표 숫자를 안 내기로 하면서 생긴 자리다. 예전에는 주소가 없으면 좌표만
# 보여줬다. 지어낼 것이 없으므로 무엇이 왔는지만 말한다.
POINT_FOUND = "좌표를 찾았습니다"

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

# ── 어떤 조건으로 불렀는가 ────────────────────────────────────────
#
# trace 항목의 input 은 vendor 가 참조와 어댑터까지 푼 실제 호출 인자다.
#
# **칸을 늘어놓지 않는다. 미리 정한 칸만 읽는다.** 예전에는 문자열 · 정수 ·
# 실수인 칸을 순서대로 `key=value` 로 적었다. 그것이 화면에
# `origin_lon=126.9482 · origin_lat=37.3201 · mode="TRANSIT" ·
# departure_date="2026-09-01"…` 로 나갔다 (2026-09-01 실측). 읽을 사람이
# 기자와 일반 독자인 화면에서 그 줄이 알려주는 것은 없다.
#
# 결과 쪽에서 이 파일이 이미 하던 것과 같은 방식으로 바꿨다 — 칸 이름을
# 미리 정해 두고 그 칸만 읽는다. 모르는 칸은 안 읽으므로 새 도구가 무엇을
# 들고 와도 화면에 안 샌다.
#
# **수는 안 적는다.** 배선에 실려 오는 실수는 전부 경위도이고
# (origin_lon · minLat …) 정수는 단위를 몰라 딴 뜻으로 읽힌다. 뜻과 단위를
# 아는 것이 cutoffs_minutes 하나였는데 그것도 뺐다 (아래 「자를 겹」).
# 지금은 예외가 없다.
#
# **적는 것이 지금은 하나다.** 나머지 셋은 답 첫 줄이 이미 말해서 뺐다.
#
#   SPOKEN_KEYS    사람이 입으로 말한 낱말이 앉는 칸. 실측 배선에서 @arg 가
#                  앉는 여섯 칸뿐이다 (execution/wiring.yaml). level="sigungu"
#                  같은 기계 낱말은 여기 없어 저절로 빠진다
#   MODE_KEY       무엇으로 갔는가. 뺐다 — 아래 문단
#   DEPARTURE_*    언제 떠났는가. 뺐다 — 아래 문단
#   CUTOFFS_KEY    몇 분으로 자르는가. 뺐다 — 아래 문단
#
# **발화에서 온 낱말은 0건일 때 특히 있어야 한다.** _empty_headline 이
# 「무엇으로 찾았는지는 머리말이 되풀이하지 않는다」로 서 있고, 그 근거가
# 단계 줄이 그 낱말을 적는다는 것이다.
INPUT_JOIN = " · "
INPUT_VALUE_LIMIT = 24

# 무엇으로 갔는가. **단계 줄에는 안 적는다** (2026-09-02 보도자료 검토).
#
# 「대중교통 이용 시」로 적던 자리다. 답 첫 줄이 「대중교통으로 30분 안에」로
# 이미 말해 같은 것이 한 답에 두 번 나왔다. 자를 겹(CUTOFFS_KEY)과 같은
# 까닭으로 뺐고, 어미(" 이용 시")도 쓰는 곳이 없어져 함께 걷었다.
#
# 이름과 표는 남는다. execution/execute_service.py 의 첫 줄(REACH_HEADLINE)이
# 이 표를 읽어 「대중교통으로 30분 안에」를 짓는다. 값이 영어 enum 이라
# 우리말로 옮기는 표이고, 도구 스키마의 enum 넷이 근거다 (WALK · BICYCLE ·
# CAR · TRANSIT, 2026-09-01 /api/tools 실측).
MODE_KEY = "mode"
MODE_WORDS = {
    "WALK": "도보",
    "BICYCLE": "자전거",
    "CAR": "승용차",
    "TRANSIT": "대중교통",
}

# 출발 날짜와 시각. **단계 줄에는 안 적는다** (2026-09-01 「일흔아홉째」).
# 답 첫 줄이 「(2026년 9월 1일 08시 15분 출발 기준)」으로 이미 말하고, 두 곳이
# 같은 것을 말하면 둘째 줄이 길어지기만 한다. 첫 줄을 짓는 자리는
# execution/execute_service.py 이고 이 두 이름을 그쪽이 읽는다.
DEPARTURE_DATE_KEY = "departure_date"
DEPARTURE_TIME_KEY = "departure_time"

# 자를 겹. **단계 줄에는 안 적는다** (2026-09-02 보도자료 검토).
#
# 「일흔아홉째」가 「도달 시간 30분」으로 되살렸던 자리다. 겹이 셋이던 때는
# 지도의 세 겹을 가리키는 말이 답에 하나도 없어 그 앞머리가 필요했는데,
# 배선의 cutoffs 가 [30] 하나가 되면서 같은 30분이 한 답에 세 번 나온다 —
# 첫 줄의 「30분 안에 닿을 수 있는」, 이 자리, 바로 아래 면적 줄. 셋 중
# 첫 줄 하나만 남긴다. 아래 면적 줄에서도 「30분 이내」를 뺐다 (REACH_LINE).
#
# 이름은 남는다. execution/execute_service.py 가 첫 줄의 「30분」을 이 칸에서
# 읽는다 — 값을 글자로 박지 않는 것은 그쪽도 같다.
CUTOFFS_KEY = "cutoffs_minutes"

SPOKEN_KEYS = ("query", "name", "stationName", "sectionName", "railwayName", "facilityName")

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
          단계 이름은 intent.steps 가 들고 옴. step id 로 맞춰 씀 — trace 는
          부른 데까지만 있고 intent 는 부르려던 전부라 길이가 다를 수 있음
          면적을 견줄 넓이도 intent 가 들고 옴. 없으면 견줌이 안 붙음.
          어느 장소의 넓이인지는 이 파일이 모름
          단계 덩이 사이는 빈 줄임. 없으면 다음 단계 제목이 바로 위 목록에
          딸린 줄로 읽혀 <li> 안으로 빨려 들어감 (STEP_GAP)
          내보내기 직전에 줄 끝마다 마크다운 줄바꿈을 얹음. _for_markdown 임
    """
    verdict = _verdict(trace, failed)
    names = _step_names(intent)
    reference = intent.get(AREA_REFERENCE_INTENT_KEY)
    lines = [
        step_line(item, names.get(item.get("id"), ""), reference, number=index)
        for index, item in enumerate(trace, start=1)
    ]

    if verdict == SUCCESS:
        headline = str(intent.get("answer_instruction") or "").strip()
    elif verdict == EMPTY:
        headline = _empty_headline(trace[-1] if trace else {})
    else:
        headline = ERROR_HEADLINE

    if not headline:
        return _for_markdown(STEP_GAP.join(lines))
    if not lines:
        return _for_markdown(headline)
    return _for_markdown(STEP_GAP.join([headline, *lines]))


def _for_markdown(answer: str) -> str:
    """줄 끝마다 MARKDOWN_BREAK 를 얹은 답. 줄이 하나면 그대로.

    입력  BELOW 로만 나뉜 답 전체
    출력  같은 답. 빈 줄이 아닌 줄마다 끝에 공백 둘이 붙음
    규칙  빈 줄에는 안 붙임. 공백만 있는 줄이 되면 문단 가르기가 흐려짐
          문단 마지막 줄에 붙는 것은 CommonMark 가 무시함. 가려내지 않음
          글자를 하나도 안 더함. 공백은 화면에 안 보임
    제약  줄을 나누는 자리에서 얹지 않는다.
          답을 짓는 자리(step_line · _shadow_line …)는 저쪽 화면이 무엇으로
          그리는지 모른다. 내보내기 직전 한 자리에서만 얹는다
    이력  저쪽이 react-markdown 을 플러그인 없이 써서 줄바꿈 하나가 공백이
          됐음. 답이 화면에서 한 줄로 붙었음 (2026-09-02. MARKDOWN_BREAK)
    """
    return "\n".join(
        line + MARKDOWN_BREAK if line.strip() else line for line in answer.split("\n")
    )


def _step_names(intent: Dict[str, Any]) -> Dict[str, str]:
    """step id -> 단계 이름. 실려 온 것이 없으면 빈 표.

    입력  부르는 쪽이 만든 intent. steps 는 vendor 에 넘긴 그 배열임
    출력  {step id: 이름}
    규칙  STEP_NAME_KEY 가 있고 문자열이고 비어 있지 않은 것만 담음
          steps 가 없거나 모양이 다르면 빈 표. 그때는 단계 줄이 도구 이름으로
          되돌아감
    제약  이름을 여기서 짓지 않는다.
          원천은 온톨로지의 노드 name 하나이고, 부르는 쪽이 그것을 실어 보낸다.
          여기서 도구 이름을 한국어로 옮기기 시작하면 원천이 둘이 된다
    """
    steps = intent.get("steps")
    if not isinstance(steps, list):
        return {}

    names: Dict[str, str] = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id")
        name = step.get(STEP_NAME_KEY)
        if isinstance(step_id, str) and isinstance(name, str) and name.strip():
            names[step_id] = name.strip()
    return names


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


def step_line(
    item: Dict[str, Any],
    name: str = "",
    reference: Any = None,
    number: Optional[int] = None,
) -> str:
    """단계 하나의 덩이. 단계 제목 한 줄과 그 아래 값 목록.

    입력  trace 항목 하나 · 부르는 쪽이 실어 보낸 단계 이름(없으면 "") ·
          면적을 견줄 넓이(없으면 None) · 단계 번호(없으면 제목을 안 감쌈)
    출력  제목 한 줄과 그 아래 목록 줄들
    규칙  이름이 없으면 도구 이름으로 되돌아감. 시험이 이름 없이 부름
          번호를 받으면 제목을 STEP_HEAD 로 감쌈. 이름이 통째로 비면
          번호만 남김
          이름 다음은 늘 줄을 바꿈. 값이 한 줄이든 여럿이든 같음
          값은 줄마다 목록의 한 항목임. 딸린 줄(ITEM_INDENT 로 시작하는
          줄)은 항목을 안 새로 열고 바로 위 항목에 붙음 — _bulleted 임
          조건은 제목과 결과 사이의 한 항목. 적을 것이 없으면 통째로 빠짐
          결과 줄에 이미 나온 값은 조건으로 다시 안 적음. 무엇을 고를지는
          _input_text 임
    이력  이름 자리가 도구 이름이었음. 보도자료 그림에 실릴 화면이라
          geo.geocode 가 아니라 「장소 좌표 변환」이 보여야 함 (2026-09-01)
          이름과 값을 " — " 로 한 줄에 이었음 (2026-09-02 걷음. STEP_JOIN)
          제목도 값도 맨 글자였음. 줄은 갈렸는데 무엇을 말하는 값인지가
          안 보였음 (2026-09-02. 위 「이름표」 절)
    """
    head = name.strip() or str(item.get("tool") or "")
    if number is not None:
        head = (
            STEP_HEAD.format(number=number, name=head)
            if head
            else NUMBER_HEAD.format(number=number)
        )

    outcome = _outcome(item, reference)
    given = _input_text(item.get("input"), outcome)

    tail = _bulleted(BELOW.join(text for text in (given, outcome) if text))
    return f"{head}{BELOW}{tail}" if head else tail


def _bulleted(body: str) -> str:
    """값 줄마다 목록 기호를 붙인 덩이. 딸린 줄은 그대로 둔다.

    입력  BELOW 로만 나뉜 값 줄들
    출력  줄마다 앞에 ITEM_MARK 가 붙은 같은 줄들
    규칙  ITEM_INDENT 로 시작하는 줄에는 안 붙임. 그 줄은 바로 위 항목에
          딸린 줄이고 CommonMark 가 <li> 안에 담음
          빈 줄은 그대로 둠. 항목 사이에 문단이 갈리면 목록이 끊김
    제약  이름표를 여기서 붙이지 않는다.
          무엇을 말하는 값인지는 값을 만드는 자리가 안다. 여기는 줄의
          생김새만 본다
    """
    return BELOW.join(
        line if not line.strip() or line.startswith(ITEM_INDENT) else ITEM_MARK + line
        for line in body.split(BELOW)
    )


def _item(label: str, value: str) -> str:
    """이름표를 앞에 놓은 값 한 줄. 이름표가 없으면 값만.

    입력  이름표(없으면 "") · 값
    출력  "**면적** : 29.96 km²" 꼴
    규칙  목록 기호는 안 붙임. 그것은 _bulleted 가 한 자리에서 함
    """
    return LABEL.format(label=label) + value if label else value


def _figure(text: str) -> str:
    """수치 값 하나를 굵게. 굵게 하는 자리를 한 곳에 모아 둔 것.

    입력  이미 다 지어진 수치 문구("29.96 km²" · "54만 명")
    출력  같은 문구를 FIGURE 로 감싼 것
    규칙  감싸는 것은 면적 둘과 인구 둘뿐임. 견줌(백분율)과 주소는 안 감쌈 —
          다 굵으면 굵은 것이 없는 것과 같음
    """
    return FIGURE.format(text=text)


def _input_text(tool_input: Any, shown: str) -> str:
    """어떤 조건으로 불렀는지 한 마디. 적을 것이 없으면 "".

    입력  vendor 가 참조와 어댑터까지 푼 실제 호출 인자 · 같은 줄의 결과 문구
    출력  조건을 INPUT_JOIN 으로 이은 줄
    규칙  미리 정한 칸만 읽음. 지금은 발화에서 온 낱말 하나임
          dict 가 아니면 ""
          발화에서 온 낱말은 한 칸만. SPOKEN_KEYS 를 순서대로 보고 먼저
          걸리는 것 하나를 씀 — 배선이 그 값을 한 자리에만 앉힘
          그 값이 결과 문구에 이미 있으면 건너뜀. geo.geocode 의 query 가
          "오송역 → 주소" 의 앞머리로 이미 나와 있음
    제약  칸 이름을 화면에 안 낸다.
          `origin_lon=…` 은 사람이 읽을 것이 아니다. 뜻이 우리말로 안 되는
          칸은 아예 안 적는다
          수를 안 적는다.
          배선의 실수는 전부 경위도이고 정수는 단위를 모른다. 예외가 없다
    이력  문자열 · 정수 · 실수인 칸을 순서대로 `key=value` 로 적었음.
          화면이 `origin_lon=126.9482 · origin_lat=37.3201 · mode="TRANSIT" ·
          departure_date="2026-09-01"…` 이었음 (2026-09-01 실측)
          자를 겹(`10 / 20 / 30분`)을 넷째로 적었음. 바로 아래 면적 줄이
          같은 수를 다시 말해 뺐고 (2026-09-01 「일흔여덟째」), 「도달 시간
          30분」으로 되살렸다가 (「일흔아홉째」) 겹이 하나가 되면서 다시
          뺐음 (2026-09-02. CUTOFFS_KEY 문단)
          수단(「대중교통 이용 시」)을 첫째로 적었음. 답 첫 줄이 이미
          「대중교통으로 30분 안에」라고 말해 뺐음 (2026-09-02. MODE_KEY 문단)
    """
    if not isinstance(tool_input, dict):
        return ""

    parts = [text for text in (_spoken_text(tool_input, shown),) if text]
    return INPUT_JOIN.join(parts)


def _spoken_text(tool_input: Dict[str, Any], shown: str) -> str:
    """사람이 입으로 말한 낱말. 없거나 이미 나왔으면 "".

    규칙  SPOKEN_KEYS 를 순서대로 보고 먼저 걸리는 것 하나만 씀
          문자열이어야 하고 한 줄로 붙인 뒤 비면 건너뜀
          결과 문구에 이미 그대로 있으면 건너뜀
          INPUT_VALUE_LIMIT 에서 자른 뒤 따옴표로 감쌈
    """
    for key in SPOKEN_KEYS:
        value = tool_input.get(key)
        if not isinstance(value, str):
            continue
        text = " ".join(value.split())
        if not text or text in shown:
            continue
        return QUOTE.format(text=_clip(text, INPUT_VALUE_LIMIT))
    return ""


def summarize(tool_input: Any, result: Any, reference: Any = None) -> str:
    """결과 모양만 보고 한 마디.

    입력  실제 호출 인자 · 도구 응답 · 면적을 견줄 넓이(없으면 None)
    규칙  위에서부터 걸리는 데서 멈춤
          error 칸이 있으면 오류. 200 으로 돌아온 실패가 이 모양임
          배열이면 건수. 0건도 배열임. 첫 항목에서 고를 것이 있으면 함께 냄
          status 가 "없다" 고 말하면 그 사유. 건수 칸이 아예 없는 응답이
          0건 판정에 안 걸려 칸 이름만 나가던 자리임
          location 이 [lon, lat] 이면 주소. 어디를 찍었는지 사람이 알아볼 수
          있어야 함. 좌표 숫자는 안 냄
          도달권 폴리곤이 실려 왔으면 제일 바깥 겹의 면적. _reach_line 임
          행정동 목록이 실려 왔으면 그것. _districts_line 임
          음영 지역이 실려 왔으면 넓이와 그 안의 동. _shadow_line 임
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

        if _lon_lat(result.get("location")):
            return _place_line(tool_input, result)

        districts = _districts_line(result)
        if districts:
            return districts

        shadow = _shadow_line(result)
        if shadow:
            return shadow

        reach = _reach_line(result, reference)
        if reach:
            return reach

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
          줄 앞에 ITEM_INDENT 를 붙여 건수 항목에 딸린 줄로 보이게 함
    제약  값을 통째로 싣지 않는다. _record_line 이 정해 둔 칸만 읽고
          길이를 자른다
    """
    if not items or not isinstance(items[0], dict) or not _excerpt(items[0]):
        return []

    lines = []
    for record in items[:SHOWN_RECORDS]:
        line = _record_line(record)
        if line:
            lines.append(ITEM_INDENT + line)
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


def _outcome(item: Dict[str, Any], reference: Any = None) -> str:
    """단계 줄의 뒷부분. 실패한 단계면 사유, 아니면 결과 한 마디.

    입력  trace 항목 하나 · 면적을 견줄 넓이(없으면 None)
    규칙  실패인지는 step_failed 가 가름. 여기서 따로 판정하지 않음
          실패 모양이 둘임. error 칸이 있으면 vendor 가 거기서 멈춘 것이라
          result 가 없고 _failure_reason 이 사유를 씀
          200 오류는 사유가 result 안에 있어 summarize 가 씀.
          둘 다 앞에 FAILED_MARK 가 붙음
    """
    if step_failed(item) and "error" in item:
        return FAILED_MARK + _failure_reason(item)
    return summarize(item.get("input"), item.get("result"), reference)


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


def _place_line(tool_input: Any, result: Dict[str, Any]) -> str:
    """좌표를 찍은 결과. 발화의 낱말과 주소 두 항목. **좌표는 안 적는다.**

    규칙  주소를 보여줌. 좌표만 보이면 엉뚱한 곳을 찍어도 사람이 알아챌
          방법이 없음. "오송시" 가 경상남도 거제시 동부면 오송리를 찍은
          일이 있음 — 그것을 알아챈 것은 좌표가 아니라 주소였음
          주소가 없으면 좌표를 찾았다는 사실만. 값을 지어내지 않음
          query 가 없으면 그 항목이 통째로 빠지고 주소 하나만 남음
          "의왕역 → 주소" 로 한 줄이었음. 화살표가 무엇에서 무엇으로인지를
          말해 주지 않아 이름표 둘로 갈랐음 (2026-09-02)
    제약  경위도 숫자를 화면에 안 낸다.
          기자와 일반 독자가 보는 화면이고 (126.9482, 37.3201) 이 알려주는
          것이 없다. 좌표가 맞는지는 주소로 본다
    이력  주소 뒤에 (126.9482, 37.3201) 을 붙였음. 우리가 화면만 보고
          디버깅하던 때의 자리임 (2026-09-01 걷음)
    """
    query = tool_input.get("query") if isinstance(tool_input, dict) else None
    address = result.get("address")

    tail = str(address).strip() if isinstance(address, str) and address.strip() else POINT_FOUND
    found = _item(LABEL_ADDRESS, tail)
    return _item(LABEL_QUERY, str(query)) + BELOW + found if query else found


# ── 도달권의 넓이 ─────────────────────────────────────────────────
#
# 도달권 응답은 이 파일이 아는 모양이 하나도 아니다 — 건수 칸도 이름 칸도
# 없고 location 도 없다. 그래서 화면에 `칸: status · scenario_id · origin ·
# max_minutes · cutoffs_minutes · mode` 만 나갔다 (2026-09-01 실측).
# 사람이 알고 싶은 것 하나는 **얼마나 넓은 구역에 갈 수 있는가** 인데
# 응답은 그 수를 안 준다. 폴리곤은 준다.
#
# **면적은 응답의 폴리곤에서 잰다. 지어내지 않는다.**
#
# 재는 법 — 구면 다각형의 넓이를 닫힌 고리의 좌표만으로 구하는 식이다.
#
#     A = R² / 2 · | Σ (λ_{i+1} − λ_i) · (2 + sin φ_i + sin φ_{i+1}) |
#
# λ 는 경도, φ 는 위도(라디안), R 은 지구 평균 반지름이다. **위도 보정이
# 식 안에 들어 있다** — sin φ 가 그 자리다. 경위도를 평면처럼 재면
# 우리 위도(37.3°)에서 1/cos(37.3°) = 1.257 배, 25.7% 크게 나온다
# (실측 : 29.7 km² 를 37.4 km² 로 셌다).
#
# 검산 — 같은 폴리곤을 위도 보정한 평면(x = R·λ·cos φ₀, y = R·φ)으로도 재서
# 29.734 대 29.735 km² 로 맞췄다. R 을 평균반지름 · 등적반지름 · 6371000 중
# 무엇으로 잡아도 소수 둘째 자리가 안 움직인다 (2026-09-01, NOTES.md 「일흔일곱째」·「일흔여덟째」).
#
# **제일 큰 겹 하나만 잰다.** 응답의 겹은 누적이다 — 10분 폴리곤의 꼭짓점
# 열여섯 개가 모두 30분 폴리곤 안에 있다(실측). 그래서 겹을 더하면 안 되고
# 제일 큰 cutoff 하나가 곧 「그 시간 안에 갈 수 있는 구역」이다.
# 30을 코드에 안 적는다 — 자를 겹은 배선이 정하고 응답이 그대로 들고 온다.
#
# **조각이 여럿이면 더한다. 구멍은 뺀다.** 30분 겹이 조각 여섯이고
# (버스·전철이 끊긴 자리마다 따로 뜬다) GeoJSON 은 한 폴리곤의 첫 고리가
# 바깥, 나머지가 구멍이다. 조각끼리 겹치는지는 안 본다 — MultiPolygon 은
# 겹치지 않는 것이 규약이고, 실측에서도 겹친 짝이 없었다(20만 점 표본).
#
# REACH_KEY          폴리곤이 담겨 오는 최상위 칸
# REACH_POLYGON_KEY  그 안에서 넓이를 잴 것. lines 는 테두리라 넓이가 없다
# CUTOFF_KEY         그 겹이 몇 분짜리인지 (properties 안)
# EARTH_RADIUS_M     지구 평균 반지름 (IUGG). 위 검산 참고
# REACH_MIN_RING     넓이를 잴 수 있는 최소 꼭짓점 수. 닫힌 삼각형이 넷이다
# REACH_LINE         화면에 나갈 한 줄. 소수 둘째 자리.
#                    **몇 분짜리 겹인지는 안 적는다** — 답 첫 줄이 이미
#                    「30분 안에 닿을 수 있는 범위」로 말한다 (2026-09-02).
#                    잰 겹을 고르는 데에는 여전히 cutoff 를 읽는다.
#                    **「도달」도 안 적는다** — 단계 이름이 이미
#                    「도달 범위」다 (2026-09-02).
#                    **「면적」도 안 적는다** — 이름표가 그 자리다
#                    (2026-09-02. LABEL_AREA)
#
# **소수 둘째 자리다.** 한 자리로 자르면 29.960 이 30.0 으로 떨어져,
# 재서 얻은 수가 어림잡아 적은 수처럼 보인다 (2026-09-01 「일흔여덟째」).
# 잰 값의 자릿수는 검산이 소수 셋째 자리까지 맞은 것이 근거다 — 위
# 「검산」 문단의 29.734 대 29.735 가 그것이다.
REACH_KEY = "feature_collections"
REACH_POLYGON_KEY = "polygons"
CUTOFF_KEY = "cutoff_min"
EARTH_RADIUS_M = 6371008.8
REACH_MIN_RING = 4
REACH_LINE = "{area:.2f} km²"

# 면적 옆에 붙는 견줌. **값은 부르는 쪽이 준다.**
#
# 「29.96 km² 가 넓은가 좁은가」를 사람이 스스로 답할 수 없다. 아는 넓이 하나에
# 대면 읽힌다. 그 넓이는 장소마다 다르고 이 파일은 어느 장소인지 모르므로,
# 값이 있을 때만 괄호가 붙는다 — 없으면 괄호가 통째로 안 나온다. 아무 시군구
# 면적이나 갖다 대면 조용히 틀린 수가 붙는다.
#
# **넓이를 견준 것이지 그 안에 든다는 뜻이 아니다.** 의왕역 30분 겹은
# 군포·안양·수원까지 걸친다(실측). 그래서 「의왕시의 55%」가 아니라
# 「의왕시 전체 면적 …의 55%」로 적는다.
# 부르는 쪽이 견줌을 실어 보내는 칸. intent 에 얹힌다.
#
# **면적 아랫줄로 내렸다** (2026-09-02). 괄호로 면적 옆에 붙이면 줄이 여든
# 칸을 넘어 사진에서 접힌다. 견줄 넓이(54.02 km²)도 함께 걷었다 — 백분율이
# 뜻이고, 분모를 함께 적으면 읽는 사람이 나눗셈을 하게 된다. 그 값은 여전히
# 부르는 쪽이 실어 보내고 백분율을 그것으로 낸다.
AREA_REFERENCE_INTENT_KEY = "area_reference"
AREA_REFERENCE_NAME = "name"
AREA_REFERENCE_AREA = "area_km2"
AREA_REFERENCE_LINE = "{name} 전체 면적의 {percent}%{radius}"

# 견줌 둘째 자리. 반경 몇 km 짜리 원과 대는가.
#
# 시군구 넓이는 장소마다 표를 갖고 있어야 하지만 원은 아무 장소에나 선다.
# **원의 넓이도 부르는 쪽이 잰다** — 이 파일은 어느 점을 중심으로 잰 것인지
# 모르고, 위도에 따라 경도 1도의 길이가 달라 값이 조금씩 다르다.
AREA_REFERENCE_RADIUS_KM = "radius_km"
AREA_REFERENCE_RADIUS_AREA = "radius_area_km2"
AREA_RADIUS_PART = " · 반경 {radius:g}km 권역의 {percent}%"

# ── 도달 지역 ─────────────────────────────────────────────────
#
# execution/reach_districts 가 도달권 안에서 점을 뽑아 행정동을 모아 온 것이다.
# 여기는 그 목록을 줄로 만들기만 한다.
#
# **시군구로 묶고 묶음마다 줄을 바꾼다** (2026-09-02). 「삼동 · 내손동 ·
# 산본동」만 늘어놓으면 어느 시의 동인지 모르고, 동마다 시를 붙이면 같은 시가
# 되풀이된다. 한 줄에 다 이으면 열 곳이 백 칸을 넘어 사진에서 접힌다.
#
# **시가 같고 구만 다르면 시 이름을 한 번만 적는다.** 실려 오는 이름이
# 「수원시 권선구」·「수원시 장안구」라 그대로 묶으면 줄이 둘이 되고 「수원시」가
# 두 번 나온다. 첫 낱말로 한 번 더 묶어 「수원시 권선구 … · 장안구 …」로 적는다.
#
# **열까지 적고 그 뒤는 조용히 자른다.** 앞에 오는 것이 점이 많이 걸린
# 차례라(reach_districts 가 그 차례로 준다) 넓게 걸치는 곳이 남는다.
#
# ★ **수를 안 쓴다.** 「외 N곳」을 뒀다가 걷었다 — N 이 「우리가 찾은 수」이지
# 실제 수가 아니기 때문이다. 격자 사이로 빠지는 동이 있어서(500m 예산에서
# 스물다섯 중 스물) 「외 5곳」이라고 적으면 틀린 값이 화면에 박힌다.
# 이름은 실제로 찾은 것이라 참이고, 수만 참이 아니다 (NOTES.md 「일흔아홉째」).
# ── 음영 지역 ─────────────────────────────────────────────────
#
# execution/shadow_districts 가 낸 것이다. 여기는 줄로 만들기만 한다.
#
# **뜻을 화면에 안 적는다** (2026-09-02). 「30분 도달 범위에 둘러싸인 접근
# 취약 구역」을 넓이 앞에 적던 자리다. 한 줄이 여든 칸을 넘어 사진에서 접혔고,
# 단계 이름이 이미 「음영 지역」이라 같은 자리에서 두 번 말했다.
#
# 대신 **넓이 옆에 몫을 적는다.** 「18.42 km²」만으로는 넓은지 좁은지 읽히지
# 않고, 그 몫이 뜻을 대신 말한다 — 30분 권역(볼록 껍질)의 38%가 둘러싸이고도
# 안 닿는 자리라는 것이다. 무엇이 분모인지는 재는 쪽이 안다
# (execution/shadow_districts.SHADOW_HULL_AREA_KEY).
#
# **동 이름은 아랫줄로 내린다.** 넓이와 한 줄에 두면 줄이 길어 접힌다.
# 도달 지역 줄과 같은 들여쓰기를 쓴다.
#
# ★ **수를 안 쓴다.** 도달 지역과 같은 까닭이다 — 이름은 참이고 몇 곳인지는
# 격자가 정하는 값이라 참이 아니다 (NOTES.md 「여든째」).
SHADOW_KEY = "shadow"
SHADOW_AREA_KEY = "area_km2"
SHADOW_HULL_AREA_KEY = "hull_area_km2"
SHADOW_DISTRICTS_KEY = "districts"
SHADOW_CUTOFF_KEY = "cutoff_min"

# 음영 지역의 넓이 줄. 도달 범위의 면적 줄과 같은 틀이다.
#
# 몫은 잰 것이 다 있을 때만 뒤에 붙는다. 몇 분짜리 범위인지도 무엇으로 나눌
# 것인지도 응답이 들고 온다 — 30 도 껍질 넓이도 여기 적지 않는다. 못 읽으면
# 넓이만 남는다.
SHADOW_AREA_LINE = "{area:.2f} km²"
SHADOW_SHARE_PART = " ({minutes}분 권역의 {percent}%)"

DISTRICTS_KEY = "districts"
DISTRICTS_SIGUNGU = "sigungu"
DISTRICTS_EMD = "emd"
DISTRICTS_SHOWN = 10
DISTRICTS_EMD_JOIN = " · "
DISTRICTS_GU_JOIN = " · "

# ── 「(일부)」 ────────────────────────────────────────────────
#
# execution/district_overlap 이 동 경계와 구역을 겹쳐 재고 문턱과 견준 것이다.
# 여기는 그 판정을 읽어 꼬리표를 붙이기만 한다 — 몇 %를 일부로 볼지는 사람이
# 정한 값이라 재는 쪽이 그 한 줄을 가진다.
#
# **왜 붙이나.** 이름만 늘어놓으면 그 동의 99%가 든 곳과 0.2%만 스친 곳이
# 화면에서 똑같이 보인다 (의왕역 30분 겹에서 고천동 99.17% · 세류동 0.16%).
#
# ★ **못 잰 동에는 아무것도 안 붙인다.** 경계를 못 받았거나 코드가 안 실려
# 온 동이다. 「(일부)」가 없는 것이 「거의 다 걸친다」는 뜻이 되지만, 안 잰
# 것을 잰 것처럼 적는 것보다 낫다. 몇 곳을 쟀는지는 결과의 share 칸에 있다.
DISTRICTS_PARTIAL_KEY = "partial"
DISTRICTS_PARTIAL_MARK = "(일부)"

# ── 그 동들의 인구 ────────────────────────────────────────────
#
# execution/district_population 이 센 것이다. 여기는 줄로 만들기만 한다.
#
# **「해당 지역」은 우리가 찾은 동들이다.** 도달 범위 안의 인구가 아니다 —
# 행정동 하나가 넓어 일부만 겹치는 곳이 많고, 격자가 빠뜨리는 동도 있다.
# 그래서 「도달 지역 인구」가 아니라 「해당 지역 인구」로 적는다.
#
# **화면에 열만 보이고 인구는 찾은 동 전부를 더한 것이다.** 세는 쪽이
# 그렇게 센다(district_population 모듈 주석).
#
# **만 명으로 적는다.** 보도자료 그림에서 읽는 사람이 자릿수를 세지 않아도
# 크기가 읽혀야 한다. 만이 안 되는 수는 만으로 적으면 「0만 명」이 되므로
# 그때만 낱수로 적는다.
#
# ── 교통약자 ─────────────────────────────────────────────────
#
# **음영 지역 줄에만 붙인다** (2026-09-02). 도달 지역 줄에서는 총인구만 적는다 —
# 「가까운데 안 닿는 자리에 누가 사는가」가 물음이라 그 수가 뜻을 갖는 자리가
# 음영 지역이다.
#
# ★ **우리가 셀 수 있는 것은 둘뿐이라 덜 센 값이다.** 교통약자법(교통약자의
# 이동편의 증진법 제2조)이 정한 교통약자는 장애인 · 고령자 · 임산부 ·
# 영유아 동반자 · 어린이 다섯이고, 인구 데이터가 주는 것은 고령(65세 이상)과
# 유소년(0~14세) 둘이다. 그래서 **괄호에 무엇을 셌는지 적는다** — 「교통약자
# ○○만 명」이라고만 적으면 다섯을 다 센 수로 읽힌다. NOTES.md 「여든다섯째」.
#
# 나이 범위는 세는 쪽이 안다 (execution/district_population).
POPULATION_KEY = "population"
POPULATION_TOTAL_KEY = "total"
POPULATION_SENIOR_KEY = "senior"
POPULATION_CHILDREN_KEY = "children"
POPULATION_LINE = "{total}"
POPULATION_WEAK_PART = " · 교통약자(고령·유소년) {weak}"
POPULATION_MAN = 10000
POPULATION_MAN_TEXT = "{value:,}만 명"
POPULATION_ONE_TEXT = "{value:,}명"


def _reach_line(result: Dict[str, Any], reference: Any = None) -> str:
    """도달권 면적 한 줄. 잴 것이 없으면 "".

    입력  결과 dict
    출력  면적 한 항목. 견줄 넓이가 있으면 「비교」 항목이 아래에 붙음
    규칙  제일 큰 cutoff 하나만 잼. 겹이 누적이라 더하면 두 번 셈
          cutoff 를 못 읽는 feature 는 건너뜀
          잰 넓이가 0이면 "". 0.0 km² 라고 적으면 잰 것처럼 보임
          고른 cutoff 는 줄에 안 적음. 답 첫 줄이 이미 말함 (REACH_LINE)
    제약  cutoff 값을 코드에 안 적는다.
          몇 분으로 자를지는 배선이 정하고 응답이 들고 온다. 30 을 여기 적으면
          배선을 고쳤을 때 겹을 잘못 고른다
    """
    features = reach_features(result)
    if not features:
        return ""

    _cutoff, geometry = max(features, key=lambda pair: pair[0])
    area = geometry_area(geometry) / 1_000_000
    if area <= 0:
        return ""

    line = _item(LABEL_AREA, _figure(REACH_LINE.format(area=area)))
    reference_text = _area_reference_text(area, reference)
    if not reference_text:
        return line
    return line + BELOW + _item(LABEL_AREA_REFERENCE, reference_text)


def _area_reference_text(area: float, reference: Any) -> str:
    """면적 옆의 견줌 한 마디. 견줄 것이 없으면 "".

    입력  잰 넓이(km²) · 부르는 쪽이 준
          {name, area_km2, radius_km, radius_area_km2}
    출력  "의왕시 전체 면적의 55% · 반경 5km 권역의 38%" 꼴
    규칙  이름과 넓이가 다 있고 넓이가 0보다 클 때만 적음
          견줄 넓이를 화면에 안 적음. 백분율을 내는 데에만 씀
          반경 권역은 반지름과 그 넓이가 다 있을 때만 뒤에 붙음. 없으면 그
          자리가 통째로 빠짐
          백분율은 반올림해 정수로. 소수를 적으면 잰 값처럼 보임
    제약  견줄 넓이를 여기서 고르지 않는다.
          이 파일은 어느 장소인지 모른다. 아무 시군구 넓이나 갖다 대면
          조용히 틀린 수가 화면에 붙는다
          원의 넓이를 여기서 재지 않는다.
          중심이 어디인지 모르고, 위도에 따라 값이 달라진다
    """
    if not isinstance(reference, dict):
        return ""
    name = reference.get(AREA_REFERENCE_NAME)
    whole = _positive(reference.get(AREA_REFERENCE_AREA))
    if not isinstance(name, str) or not name.strip() or whole is None:
        return ""
    return AREA_REFERENCE_LINE.format(
        name=name.strip(),
        percent=round(area / whole * 100),
        radius=_area_radius_text(area, reference),
    )


def _area_radius_text(area: float, reference: dict) -> str:
    """견줌 뒤에 붙는 반경 권역 한 마디. 잰 원이 없으면 "".

    입력  잰 넓이(km²) · 부르는 쪽이 준 견줌
    출력  " · 반경 5km 권역의 38%" 꼴
    규칙  반지름과 그 넓이가 둘 다 0보다 큰 수일 때만 적음
    """
    radius = _positive(reference.get(AREA_REFERENCE_RADIUS_KM))
    whole = _positive(reference.get(AREA_REFERENCE_RADIUS_AREA))
    if radius is None or whole is None:
        return ""
    return AREA_RADIUS_PART.format(radius=radius, percent=round(area / whole * 100))


def _positive(value: Any):
    """0보다 큰 실수 값. 그런 수가 아니면 None. bool 은 수로 안 봄."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value)


def _districts_line(result: Dict[str, Any]) -> str:
    """도달권 안의 행정동. 그런 응답이 아니면 "".

    입력  execution/reach_districts 가 만든 결과
    출력  행정동 한 항목(시군구 묶음마다 딸린 줄). 인구를 세었으면
          「인구」 항목이 아래에 붙음
    규칙  받은 차례를 지킴. 점이 많이 걸린 차례로 와 있음
          시군구로 묶고 묶음마다 줄을 바꿈. 묶음 안의 차례도 받은 차례임
          교통약자는 안 적음. 음영 지역 줄만 그것을 적음
          DISTRICTS_SHOWN 개까지만 적고 나머지는 조용히 자름
          시군구와 읍면동이 둘 다 문자열인 항목만 셈
          인구는 찾은 동 전부를 더한 것임. 화면에 보이는 열과 다름
    제약  몇 곳인지를 화면에 안 적는다.
          센 수가 격자가 찾은 수이지 실제 수가 아니다. 이름은 참이고
          수는 참이 아니다
    """
    if not isinstance(result, dict):
        return ""
    pairs = _district_pairs(result.get(DISTRICTS_KEY))
    if not pairs:
        return ""

    line = _item(LABEL_DISTRICTS, _grouped_districts(pairs))
    people = _population_line(result)
    return line + BELOW + people if people else line


def _district_pairs(found: Any) -> List[Tuple[str, str, bool]]:
    """목록에서 (시군구, 읍면동, 일부인가) 셋만. 그런 목록이 아니면 빈 목록.

    규칙  이름 둘이 다 문자열이고 비어 있지 않은 항목만 셈
          받은 차례를 지킴. 점이 많이 걸린 차례로 와 있음
          일부인지는 실어 온 칸을 그대로 읽음. 그 칸이 없으면 못 잰 동이라
          일부로 안 봄
          참인 것만 참으로 봄. 문턱을 여기서 안 견줌 — 몇 %를 일부로 볼지는
          사람이 정한 값이고 execution/district_overlap 이 그 한 줄을 가짐
    """
    if not isinstance(found, list):
        return []

    pairs = []
    for entry in found:
        if not isinstance(entry, dict):
            continue
        sigungu = entry.get(DISTRICTS_SIGUNGU)
        emd = entry.get(DISTRICTS_EMD)
        if isinstance(sigungu, str) and isinstance(emd, str) and sigungu and emd:
            pairs.append((sigungu, emd, entry.get(DISTRICTS_PARTIAL_KEY) is True))
    return pairs


def _grouped_districts(pairs: List[Tuple[str, str, bool]]) -> str:
    """동 이름을 시군구로 묶은 줄들. 적을 것이 없으면 "".

    출력  시군구 묶음마다 한 줄. 둘째 줄부터 STEP_JOIN 으로 들여 씀 —
          목록 기호의 폭이라 그 줄들이 한 항목 안에 머묾
          "군포시 부곡동 · 당정동(일부)"
          "수원시 권선구 입북동(일부) · 장안구 율전동(일부)"
    규칙  DISTRICTS_SHOWN 개까지만 적고 나머지는 조용히 자름
          시가 같고 구만 다르면 한 줄에 담고 시 이름을 한 번만 적음.
          시군구 이름의 첫 낱말이 시임
          구가 없는 시군구는 그 자리가 통째로 빠져 동 이름이 바로 붙음
          묶음의 차례도 묶음 안의 차례도 받은 차례임
          일부만 걸치는 동은 이름 바로 뒤에 꼬리표를 붙임. 사이를 안 띄움
    제약  몇 곳인지를 적지 않는다.
          센 수가 격자가 찾은 수이지 실제 수가 아니다
    """
    grouped: Dict[str, Dict[str, List[str]]] = {}
    for sigungu, emd, partial in pairs[:DISTRICTS_SHOWN]:
        si, _, gu = sigungu.partition(" ")
        names = grouped.setdefault(si, {}).setdefault(gu.strip(), [])
        names.append(emd + DISTRICTS_PARTIAL_MARK if partial else emd)

    lines = []
    for si, districts in grouped.items():
        parts = [
            f"{gu} {DISTRICTS_EMD_JOIN.join(names)}" if gu else DISTRICTS_EMD_JOIN.join(names)
            for gu, names in districts.items()
        ]
        lines.append(f"{si} {DISTRICTS_GU_JOIN.join(parts)}")
    return STEP_JOIN.join(lines)


def _shadow_line(result: Dict[str, Any]) -> str:
    """음영 지역 한 줄. 그런 응답이 아니면 "".

    입력  execution/shadow_districts 가 만든 결과
    출력  면적 한 항목. 동을 찾았으면 「행정동」 항목이, 인구를 세었으면
          「인구」 항목이 아래에 붙음
    규칙  넓이가 0보다 클 때만 적음. 0.00 km² 라고 적으면 잰 것처럼 보임
          동을 못 찾았으면 넓이만. 넓이는 폴리곤에서 잰 것이라 점 뽑기가
          실패해도 참임
          인구 줄에 교통약자를 함께 적음. 도달 지역 줄과 다른 자리임
    제약  넓이를 여기서 재지 않는다.
          무엇을 어떻게 재는지는 execution/shadow_districts 가 안다
    """
    if not isinstance(result, dict):
        return ""
    shadow = result.get(SHADOW_KEY)
    if not isinstance(shadow, dict):
        return ""

    area = shadow.get(SHADOW_AREA_KEY)
    if isinstance(area, bool) or not isinstance(area, (int, float)) or area <= 0:
        return ""

    districts = _grouped_districts(_district_pairs(shadow.get(SHADOW_DISTRICTS_KEY)))
    line = _shadow_area_line(shadow, float(area))
    for below in (
        _item(LABEL_DISTRICTS, districts) if districts else "",
        _population_line(shadow, weak=True),
    ):
        if below:
            line += BELOW + below
    return line


def _shadow_area_line(shadow: Dict[str, Any], area: float) -> str:
    """음영 지역의 넓이 줄. 몫은 잰 것이 다 있을 때만 뒤에 붙음.

    입력  음영 지역 dict · 그 넓이(km²)
    출력  "**면적** : **18.42 km²** (30분 권역의 38%)" 꼴
    규칙  겹을 못 읽거나 껍질 넓이가 없으면 넓이만. 반쪽 문장을 안 냄
          백분율은 반올림해 정수로. 소수를 적으면 잰 값처럼 보임
    제약  분도 껍질 넓이도 코드에 적지 않는다.
          몇 분으로 자를지는 배선이 정하고 껍질을 재는 것은
          execution/shadow_districts 다. 둘 다 응답이 들고 온다
    """
    line = _figure(SHADOW_AREA_LINE.format(area=area))

    minutes = shadow.get(SHADOW_CUTOFF_KEY)
    whole = _positive(shadow.get(SHADOW_HULL_AREA_KEY))
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or whole is None:
        return _item(LABEL_AREA, line)
    return _item(
        LABEL_AREA,
        line + SHADOW_SHARE_PART.format(minutes=int(minutes), percent=round(area / whole * 100)),
    )


def _population_line(holder: Dict[str, Any], weak: bool = False) -> str:
    """그 동들의 주민등록 인구 한 줄. 센 것이 없으면 "".

    입력  동 목록이 놓인 dict · 교통약자를 함께 적을 것인가
    출력  "**인구** : **65만 명** · 교통약자(고령·유소년) 22만 명" 꼴
    규칙  총인구가 0보다 클 때만 적음. 0명이라고 적으면 잰 것처럼 보임
          만 명으로 적음. 만이 안 되는 수만 낱수로 적음
          교통약자는 weak 일 때만. 고령과 유소년을 더한 것임
          둘 중 하나라도 못 세었으면 교통약자 자리가 통째로 빠짐.
          한쪽만 더하면 덜 센 값이 온전한 값처럼 보임
    제약  몇 곳을 세었는지 적지 않는다.
          찾은 동의 수가 격자가 정하는 값이라 참이 아니다. 이름과 같은 규칙임
          교통약자를 다 센 것처럼 적지 않는다.
          법이 정한 다섯 중 둘만 세고 있고 그 둘을 괄호가 밝힌다
    """
    if not isinstance(holder, dict):
        return ""
    counted = holder.get(POPULATION_KEY)
    if not isinstance(counted, dict):
        return ""

    total = _int_value(counted.get(POPULATION_TOTAL_KEY))
    if not total or total <= 0:
        return ""

    line = _figure(POPULATION_LINE.format(total=_people_text(total)))
    return _item(LABEL_POPULATION, line + _weak_part(counted) if weak else line)


def _weak_part(counted: Dict[str, Any]) -> str:
    """인구 줄 뒤에 붙는 교통약자 한 마디. 못 세었으면 "".

    입력  execution/district_population 이 낸 인구 dict
    출력  " · 교통약자(고령·유소년) 22만 명" 꼴. 굵게 하지 않음 —
          한 항목에 굵은 수가 둘이면 눈이 어디에 걸릴지 안 정해짐
    규칙  고령과 유소년이 둘 다 0 이상의 정수일 때만 적음
          둘을 더한 것이 교통약자임. 두 무리가 안 겹침 (세는 쪽 주석)
    제약  둘 중 하나만으로 적지 않는다.
          한쪽만 더한 수를 「교통약자」라고 부르면 덜 센 값이 온전한 값처럼
          보인다
    """
    senior = _int_value(counted.get(POPULATION_SENIOR_KEY))
    children = _int_value(counted.get(POPULATION_CHILDREN_KEY))
    if senior is None or senior < 0 or children is None or children < 0:
        return ""
    return POPULATION_WEAK_PART.format(weak=_people_text(senior + children))


def _people_text(value: int) -> str:
    """사람 수 한 마디. 만 명 아니면 낱수.

    규칙  만이 넘으면 만으로 반올림해 적음. 자릿수를 안 세도 크기가 읽힘
          만이 안 되면 낱수로 적음. 만으로 적으면 "0만 명" 이 됨
    """
    if value >= POPULATION_MAN:
        return POPULATION_MAN_TEXT.format(value=round(value / POPULATION_MAN))
    return POPULATION_ONE_TEXT.format(value=value)


def reach_features(result: Any) -> List[Tuple[float, Any]]:
    """도달권 폴리곤의 (cutoff, geometry) 짝들. 그런 응답이 아니면 빈 목록.

    규칙  REACH_KEY 안의 REACH_POLYGON_KEY 안의 "features" 만 봄.
          그 세 겹이 다 있어야 도달권 응답으로 봄
          properties.CUTOFF_KEY 가 수인 것만. bool 은 수로 안 봄
    """
    if not isinstance(result, dict):
        return []

    collections = result.get(REACH_KEY)
    if not isinstance(collections, dict):
        return []
    polygons = collections.get(REACH_POLYGON_KEY)
    if not isinstance(polygons, dict):
        return []
    features = polygons.get("features")
    if not isinstance(features, list):
        return []

    found = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        cutoff = properties.get(CUTOFF_KEY) if isinstance(properties, dict) else None
        if isinstance(cutoff, bool) or not isinstance(cutoff, (int, float)):
            continue
        found.append((float(cutoff), feature.get("geometry")))
    return found


def geometry_area(geometry: Any) -> float:
    """폴리곤 하나의 넓이 (m²). 못 재면 0.

    규칙  Polygon 이면 고리 목록 한 벌, MultiPolygon 이면 그것이 여럿
          한 벌의 첫 고리가 바깥이고 나머지는 구멍이라 빼냄
          구멍이 바깥보다 크게 나오면 그 벌은 0으로 봄. 음수 넓이를 더해
          전체를 줄이지 않음
    """
    if not isinstance(geometry, dict):
        return 0.0

    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        return 0.0

    if kind == "Polygon":
        rings = [coordinates]
    elif kind == "MultiPolygon":
        rings = [item for item in coordinates if isinstance(item, list)]
    else:
        return 0.0

    total = 0.0
    for polygon in rings:
        if not polygon:
            continue
        outer = _ring_area(polygon[0])
        holes = sum(_ring_area(ring) for ring in polygon[1:])
        total += max(outer - holes, 0.0)
    return total


def _ring_area(ring: Any) -> float:
    """닫힌 고리 하나가 두르는 구면 넓이 (m²). 못 재면 0.

    규칙  위 절의 식 그대로. 위도 보정이 sin φ 로 식 안에 들어 있음
          꼭짓점이 REACH_MIN_RING 보다 적으면 0. 넓이가 없음
          수로 못 읽는 꼭짓점이 하나라도 있으면 0. 반쯤 재지 않음
          도는 방향은 안 봄. 절댓값을 냄
    """
    if not isinstance(ring, list) or len(ring) < REACH_MIN_RING:
        return 0.0

    points = []
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return 0.0
        try:
            points.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            return 0.0

    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(points, points[1:]):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total) * EARTH_RADIUS_M * EARTH_RADIUS_M / 2


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
# **문구를 안 바꿨다.** app/api/services/execute_service.py 의 NO_MATCH_ANSWER
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
