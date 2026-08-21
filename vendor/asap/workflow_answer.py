"""workflow trace 를 사람이 읽는 답으로. **우리 코드다.** 원본에는 없다.

generic_mcp_executor._compose_workflow_answer 가 Gemini 로 답을 다듬던 자리를
대신한다. 우리는 그 키를 쓰지 않고, 무엇보다 **호출 순서가 그대로 보여야 한다** —
지금 증명하려는 것이 "온톨로지가 실행 순서를 정한다" 이기 때문이다. LLM 이 다시
쓰면 순서가 문장에 녹아 사라진다.

여기는 도구 이름을 모른다. trace 의 result 모양만 보고 한 줄을 만든다. 도구가
늘어도 이 파일은 그대로다.
"""

import json
from typing import Any, Dict, List

# 단계 줄에서 도구 이름 칸의 폭. 도구 이름은 전부 ASCII 라 ljust 로 맞는다.
TOOL_COLUMN = 18

# 요약이 dict 나 문자열일 때 잘라내는 길이.
SUMMARY_LIMIT = 120


def compose_workflow_answer(intent: Dict[str, Any], trace: List[Dict[str, Any]]) -> str:
    """실행 결과 한 벌을 답으로.

    입력  intent(answer_instruction 이 첫 줄) · vendor 가 쌓은 trace
    출력  첫 줄에 무엇을 했는지, 빈 줄, 그다음 단계 목록
    규칙  첫 줄은 intent.answer_instruction 을 그대로 씀. 노드가 아는 문장이라
          도구 이름으로는 만들 수 없음
          answer_instruction 이 없으면 단계 목록만 남음
    제약  실패한 실행을 여기서 다루지 않는다.
          vendor 의 _failed_workflow_result 가 자기 문구로 먼저 돌아가므로
          이 함수는 성공한 trace 만 받음
    """
    lines = [f"{index}. {step_line(item)}" for index, item in enumerate(trace, start=1)]
    headline = str(intent.get("answer_instruction") or "").strip()

    if not headline:
        return "\n".join(lines)
    return "\n".join([headline, "", *lines])


def step_line(item: Dict[str, Any]) -> str:
    """단계 하나의 줄. 도구 이름과 결과 한 마디."""
    tool = str(item.get("tool") or "")
    return f"{tool:<{TOOL_COLUMN}}{summarize(item.get('input'), item.get('result'))}"


def summarize(tool_input: Any, result: Any) -> str:
    """결과 모양만 보고 한 마디.

    규칙  배열이면 건수. 0건도 성공임 — 빈 배열이 그 뜻
          location 을 가진 dict 면 좌표. input 에 query 가 있으면 앞에 붙임
          그 밖에는 JSON 을 잘라서 그대로 보임
    """
    if isinstance(result, list):
        return f"{len(result)}건"

    if isinstance(result, dict):
        point = _lon_lat(result.get("location"))
        if point:
            query = (tool_input or {}).get("query") if isinstance(tool_input, dict) else None
            coordinates = f"{point[0]:.4f}, {point[1]:.4f}"
            return f"{query} → {coordinates}" if query else coordinates

    return _preview(result)


def _lon_lat(value: Any):
    """[lon, lat] 이면 그 둘. 아니면 None."""
    if not isinstance(value, list) or len(value) < 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def _preview(value: Any) -> str:
    """무엇인지 모르는 결과를 한 줄로."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)

    text = " ".join(text.split())
    return text if len(text) <= SUMMARY_LIMIT else text[:SUMMARY_LIMIT] + "…"
