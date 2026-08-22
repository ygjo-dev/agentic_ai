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
보여준다.
"""

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
        headline = EMPTY_HEADLINE
    else:
        headline = ERROR_HEADLINE

    if not headline:
        return "\n".join(lines)
    if not lines:
        return headline
    return "\n".join([headline, "", *lines])


def step_line(item: Dict[str, Any]) -> str:
    """단계 하나의 줄. 도구 이름과 결과 한 마디.

    규칙  이름이 칸보다 길어도 TOOL_GAP 만큼은 벌림. 안 벌리면 요약과 붙어
          한 낱말로 읽힘 (adminBoundary.findBoundaryByPoint0건)
          짧은 이름의 정렬은 안 달라짐. 칸을 좁힌 만큼 뒤에 다시 붙임
    """
    tool = str(item.get("tool") or "")
    return f"{tool.ljust(TOOL_COLUMN - TOOL_GAP)}{' ' * TOOL_GAP}{_outcome(item)}"


def summarize(tool_input: Any, result: Any) -> str:
    """결과 모양만 보고 한 마디.

    규칙  위에서부터 걸리는 데서 멈춤
          error 칸이 있으면 오류. 200 으로 돌아온 실패가 이 모양임
          배열이면 건수. 0건도 배열임
          location 이 [lon, lat] 이면 주소와 좌표. 어디를 찍었는지 사람이
          알아볼 수 있어야 함
          건수를 세는 칸이 있으면 건수
          그 밖에는 최상위 칸 이름만
    제약  결과 값을 문자열에 담지 않는다.
          geojson · cctvUrl · features 가 raw JSON 으로 화면에 새던 자리다
    """
    if _has_error(result):
        return FAILED_MARK + _error_text(result["error"])

    if isinstance(result, list):
        return f"{len(result)}건"

    if isinstance(result, dict):
        point = _lon_lat(result.get("location"))
        if point:
            return _place_line(tool_input, result, point)

        counted = _counted(result)
        if counted:
            return _count_line(*counted)

        return _keys_line(result)

    return UNKNOWN_RESULT


def _verdict(trace: List[Dict[str, Any]], failed: bool) -> str:
    """이 실행이 성공인가 빈 결과인가 오류인가.

    입력  vendor 가 쌓은 trace · 부르는 쪽이 이미 아는 실패 여부
    출력  SUCCESS · EMPTY · ERROR 중 하나
    규칙  failed 가 참이면 오류. vendor 는 중단할 때 대개 trace 에 아무것도
          안 남기므로 trace 만으로는 못 가름
          어느 항목이든 error 칸이 있으면 오류. vendor 가 거기서 멈춘 자리임
          어느 항목이든 result 가 200 으로 돌아온 오류면 오류. 다음 도구가 그
          칸을 optional 로 받으면 vendor 가 끝까지 돌고 errors 도 비어 있음
          trace 가 비면 오류. 한 단계도 안 돌았음
          마지막 항목의 센 건수가 0이면 빈 결과. 발화에 답하는 것은 마지막임
          그 밖은 성공
    """
    if failed:
        return ERROR

    for item in trace:
        if "error" in item:
            return ERROR
        if _has_error(item.get("result")):
            return ERROR

    if not trace:
        return ERROR

    counted = _counted(trace[-1].get("result"))
    if counted and counted[0] == 0:
        return EMPTY

    return SUCCESS


def _outcome(item: Dict[str, Any]) -> str:
    """단계 줄의 뒷부분. 실패한 단계면 사유, 아니면 결과 한 마디."""
    if "error" in item:
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


def _count_line(count: int, total: Optional[int]) -> str:
    """건수 한 줄. 받은 것과 전체가 다르면 둘 다."""
    if total is not None and total != count:
        return f"{count}건 (전체 {total:,}건)"
    return f"{count}건"


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


def _clip(text: str) -> str:
    """한 줄로 붙이고 SUMMARY_LIMIT 에서 자름."""
    text = " ".join(text.split())
    return text if len(text) <= SUMMARY_LIMIT else text[:SUMMARY_LIMIT] + "…"


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
