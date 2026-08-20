"""발화를 recipe 로 해석하고 그 노드 순서대로 MCP 도구를 부른다.

**온톨로지는 무엇을 어떤 순서로 하는지만 말한다.** 그 노드가 어느 도구인지,
input 을 어떻게 채우는지는 온톨로지에 없다 — 아래 TOOL_OF 표가 갖는다.
온톨로지에 도구 이름을 적으면 노드가 특정 MCP 서버에 묶여, 같은 일을 하는
도구로 갈아끼울 때 도메인을 고쳐야 한다.

Gateway 와의 통신은 gateway_client 가 맡는다. 여기는 "무엇을 부를지" 만 안다.

answer 는 LLM 으로 만들지 않는다. 호출 순서가 그대로 보여야 하고, 그것이
지금 증명하려는 것이다. LLM 이 다시 쓰면 순서가 문장에 녹아 사라진다.
"""

import json

from demo.api.services import gateway_client, ontology_service, resolve_service
from demo.api.services.gateway_client import GatewayError

# 발화에서 장소를 뽑는 코드가 아직 없다. **고정값이다.**
#
# 지금 재는 것은 "온톨로지가 정한 순서대로 실제 MCP 가 불리는가" 하나이고,
# 장소 추출은 그것과 독립이다. 먼저 넣으면 추출이 틀렸을 때 배선이 틀린
# 것인지 추출이 틀린 것인지 갈리지 않는다.
#
# 다음에 이 자리에 들어갈 것 : 발화에서 "역/站" 로 끝나는 말을 정규식으로
# 집는 것이 가장 싸고, 그것으로 안 되는 발화("청주 시내 CCTV")가 나오면
# LLM 추출로 간다. 어느 쪽이든 여기 상수 하나를 함수 하나로 바꾸면 된다.
PLACE = "오송역"

# geocode 가 주는 bbox 는 한 변이 약 1km 다. 그대로 road.getCctv 에 넘기면
# 0건이 나온다 — 고속도로 CCTV 가 역사 반경 1km 안에 없기 때문이다.
# 0.15도(약 15km)로 넓히면 95건이 나온다(실측).
BBOX_PADDING = 0.15

# answer 의 단계 줄에서 도구 이름 칸의 폭. 도구 이름은 전부 ASCII 라 ljust 로 맞는다.
TOOL_COLUMN = 18


def _geocode_input(place: str, previous) -> dict:
    """geo.geocode 가 받는 input. 장소 이름 하나."""
    return {"query": place}


def _cctv_input(place: str, previous) -> dict:
    """road.getCctv 가 받는 input. 앞 단계의 bbox 를 평탄하게 풀고 넓힘.

    입력  장소 이름(안 씀) · 앞 단계 결과
    출력  minLon · minLat · maxLon · maxLat
    규칙  bbox 는 [[minLon, minLat], [maxLon, maxLat]] 형태임
          BBOX_PADDING 만큼 넓힘. 안 넓히면 0건이 나옴
    제약  앞 단계 없이 부르지 않는다. 받을 bbox 가 없음
    """
    bbox = (previous or {}).get("bbox") if isinstance(previous, dict) else None
    if not bbox:
        raise GatewayError(
            "앞 단계가 bbox 를 주지 않았다. road.getCctv 는 좌표 범위 없이 부를 수 없다 : "
            f"{json.dumps(previous, ensure_ascii=False)}"
        )

    (min_lon, min_lat), (max_lon, max_lat) = bbox
    return {
        "minLon": min_lon - BBOX_PADDING,
        "minLat": min_lat - BBOX_PADDING,
        "maxLon": max_lon + BBOX_PADDING,
        "maxLat": max_lat + BBOX_PADDING,
    }


def _geocode_summary(place: str, result) -> str:
    """geo.geocode 결과 한 줄. 장소와 좌표."""
    lon, lat = result["location"]
    return f"{place} → {lon:.4f}, {lat:.4f}"


def _cctv_summary(place: str, result) -> str:
    """road.getCctv 결과 한 줄. 건수.

    규칙  0건도 성공임. 빈 배열이 그 뜻
    """
    return f"{len(result)}건"


# 노드 -> 도구. **온톨로지 밖이다.**
#
#   server_id · tool  Gateway 에 보낼 것
#   input             (장소, 앞 결과) -> 그 도구가 받는 input
#   summary           (장소, 결과) -> answer 의 단계 줄에 적을 한 마디
#   headline · failed  그 노드에서 끝나는 경로의 첫 줄. 성공했을 때와 실패했을 때
#
# 첫 줄을 둘로 나눠 적는다. 성공 문장을 문자열 치환으로 뒤집으면 조사가
# 어긋난다 ("좌표를 조회했습니다" -> "좌표를 조회에 실패했습니다").
TOOL_OF = {
    "geocode_place": {
        "server_id": "asap-mcp-core",
        "tool": "geo.geocode",
        "input": _geocode_input,
        "summary": _geocode_summary,
        "headline": "{place} 좌표를 조회했습니다.",
        "failed": "{place} 좌표 조회에 실패했습니다.",
    },
    "find_cctv": {
        "server_id": "asap-mcp-core",
        "tool": "road.getCctv",
        "input": _cctv_input,
        "summary": _cctv_summary,
        "headline": "{place} CCTV 를 조회했습니다.",
        "failed": "{place} CCTV 조회에 실패했습니다.",
    },
}


def _step_lines(steps: list[dict]) -> list[str]:
    """단계마다 한 줄. 번호 · 도구 이름 · 요약.

    입력  기록된 단계들
    출력  줄 목록. 실패한 단계는 input 과 응답 본문을 아래에 덧붙임
    규칙  실패한 단계에만 원문을 붙임. 성공한 것까지 붙이면 답이 안 읽힘
    """
    lines = []
    for index, step in enumerate(steps, start=1):
        summary = step.get("summary") or "실패"
        lines.append(f"{index}. {step['tool']:<{TOOL_COLUMN}}{summary}")
        if step.get("error"):
            lines.append(f"   input  {json.dumps(step['input'], ensure_ascii=False)}")
            lines.append(f"   응답   {step['error']}")
    return lines


def _answer(steps: list[dict], place: str) -> str:
    """실행 결과 한 벌을 사람이 읽는 답으로.

    입력  기록된 단계들 · 장소 이름
    출력  첫 줄에 무엇을 했는지, 빈 줄, 그다음 단계 목록
    규칙  마지막 단계가 실패했으면 첫 줄이 실패를 말함
          부른 것이 하나도 없으면 단계 목록이 비고 첫 줄만 남음
    제약  LLM 으로 다시 쓰지 않는다. 호출 순서가 그대로 보여야 함
    """
    if not steps:
        return "부를 도구가 없습니다."

    last = steps[-1]
    wiring = TOOL_OF[last["node"]]
    headline = wiring["failed" if last.get("error") else "headline"].format(place=place)

    return "\n".join([headline, "", *_step_lines(steps)])


def run(recipe_id: str, place: str = PLACE):
    """recipe 의 노드 순서대로 도구를 부름. 이벤트를 차례로 냄.

    입력  recipe id · 장소 이름
    출력  이벤트 dict 를 순서대로 냄. 마지막은 반드시 type=result
          step_start / step_end 는 실행 노드마다 한 쌍
    규칙  첫 노드(spoken_place)는 데이터 노드라 부르지 않음. 장소 이름이
          그 자리를 대신함. TOOL_OF 에 없는 노드는 전부 그렇게 건너뜀
          앞 단계 결과를 다음 input 에 넘김
          한 단계가 실패하면 거기서 멈춤. 뒷 단계가 앞 결과를 받으므로
          계속 갈 수 없음
    제약  실패를 조용히 삼키지 않는다. 응답 본문을 그대로 answer 에 실음
    """
    steps: list[dict] = []
    previous = None

    for entry in ontology_service.path_of(recipe_id):
        node_id = entry["node_id"]
        wiring = TOOL_OF.get(node_id)
        if wiring is None:
            continue

        tool = wiring["tool"]
        yield {"type": "step_start", "node": node_id, "message": f"{tool} 호출 중입니다..."}

        step = {"node": node_id, "tool": tool, "input": None, "summary": None, "error": None}
        steps.append(step)

        try:
            step["input"] = wiring["input"](place, previous)
            result = gateway_client.execute_tool(
                wiring["server_id"], tool, step["input"]
            )
            step["summary"] = wiring["summary"](place, result)
        except GatewayError as exc:
            step["error"] = str(exc)
            yield {"type": "step_end", "node": node_id, "message": f"{tool} 실패"}
            break

        previous = result
        yield {"type": "step_end", "node": node_id, "message": f"{tool} 완료"}

    yield {"type": "result", "answer": _answer(steps, place), "commands": []}


def chat(text: str, llm_client, reason_max_length: int):
    """발화 한 건을 끝까지. 해석하고 부르고 답을 만듦.

    입력  발화 · LLM 클라이언트 · reason 길이 상한
    출력  이벤트 dict 를 순서대로 냄. 마지막은 반드시 type=result
    규칙  해석도 한 단계로 냄. 저쪽 화면이 진행 상황을 그림
          SELECT 가 아니면 도구를 하나도 안 부름. CLARIFY 는 후보가 여럿이라
          무엇을 부를지 정해지지 않았고, NO_MATCH 는 부를 것이 없음
    제약  여기서 LLM 클라이언트를 만들지 않는다.
          demo.api.main 의 make_client 를 갈아끼우는 테스트가 죽음
    """
    yield {"type": "step_start", "node": "resolve", "message": "발화를 해석하고 있습니다..."}
    resolved = resolve_service.resolve(
        text, llm_client=llm_client, reason_max_length=reason_max_length
    )
    recipe_id = resolved.get("recipe_id")
    yield {
        "type": "step_end",
        "node": "resolve",
        "message": f"{resolved.get('status')} {recipe_id or ''}".strip(),
    }

    if resolved.get("status") != "SELECT" or not recipe_id:
        yield {
            "type": "result",
            "answer": _no_recipe_answer(resolved),
            "commands": [],
        }
        return

    yield from run(recipe_id)


def _no_recipe_answer(resolved: dict) -> str:
    """고른 recipe 가 없을 때의 답.

    입력  resolve 결과
    출력  왜 못 골랐는지와 LLM 이 적은 이유
    규칙  후보가 있으면 무엇들 사이에서 갈렸는지 적음. 없으면 영역 밖이라고 함
    """
    candidates = resolved.get("candidate_recipe_ids") or []
    reason = resolved.get("reason") or ""

    if candidates:
        head = "무엇을 원하시는지 하나로 좁히지 못했습니다. 후보 : " + " · ".join(candidates)
    else:
        head = "지금 할 수 있는 일 중에 맞는 것이 없습니다."

    return f"{head}\n\n{reason}".rstrip()
