# -*- coding: utf-8 -*-
"""Generic MCP executor for direct registered-tool orchestration."""

from datetime import datetime
import json
import math
import re
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from vendor.asap.config import settings
from vendor.asap.command_renderer import build_commands_from_artifacts
from vendor.asap.mcp_result_inspector import inspect_mcp_result, inspect_mcp_trace
from logging import getLogger as get_logger
from vendor.asap.mcp_client import mcp_client
from vendor.asap.workflow_answer import compose_workflow_answer

logger = get_logger("core.generic_mcp_executor")

GENERIC_MCP_ACTION = "call_mcp_tool"
GENERIC_MCP_WORKFLOW_ACTION = "call_mcp_workflow"
_BLOCKED_TOOL_WORDS = ("delete", "remove", "update", "upload", "write", "patch", "create")
_MAX_PROMPT_TOOLS = 32
_MAX_RESULT_CHARS = 12000
_MAX_WORKFLOW_STEPS = 8


def is_generic_mcp_intent(action: Optional[str]) -> bool:
    """Return True when the intent should be handled by the generic MCP executor."""
    return action in {GENERIC_MCP_ACTION, GENERIC_MCP_WORKFLOW_ACTION}


def build_generic_mcp_prompt_lines(
    allowed_server_ids: Optional[List[str]] = None,
    allowed_tool_refs: Optional[List[str]] = None,
) -> List[str]:
    """Render registered MCP tools into the intent parser prompt."""
    tools = _load_prompt_tools(allowed_server_ids, allowed_tool_refs)
    today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    lines = [
        "- call_mcp_tool: Use a registered MCP tool directly when no specialized Harness or Plugin is a better match.",
        '  Fields: { "action": "call_mcp_tool", "server_id": "<MCP server id>", "tool": "<tool name>", "input": <JSON object matching the tool inputSchema>, "answer_instruction": "<short Korean instruction>" }',
        "- call_mcp_workflow: Use multiple registered MCP tools in sequence when one tool needs data produced by another tool.",
        '  Fields: { "action": "call_mcp_workflow", "steps": [{ "id": "<short id>", "server_id": "<MCP server id>", "tool": "<tool name>", "input": <JSON object>, "inputAdapter": "<optional adapter>" }], "answer_instruction": "<short Korean instruction>" }',
        "  Workflow references: later step inputs may reference previous step outputs with $<step_id>.<path>. For arrays, use numeric path parts such as $from.location.1 for latitude and $from.location.0 for longitude.",
        "  Context references: use $context.selectedLocation.lon and $context.selectedLocation.lat when the user refers to the selected map interest point.",
        "  Important: geo.geocode returns location as [lon, lat], not {lat, lon}; it also returns bbox as [[minLon, minLat], [maxLon, maxLat]].",
        "  For route tools use from_lat=$origin.location.1 and from_lon=$origin.location.0.",
        "  For bbox tools use minLon=$place.bbox.0.0, minLat=$place.bbox.0.1, maxLon=$place.bbox.1.0, maxLat=$place.bbox.1.1.",
        '  If the user specifies a radius such as "2km around", do not use the geocode bbox. Use inputAdapter="point_radius_to_bbox" with input { "center": "$place.location", "radiusMeters": 2000 } for bbox-based tools.',
        f"  Current date for date/time tool inputs is {today} in Asia/Seoul (KST). If the user says today/tomorrow, resolve it using this KST date.",
        "  Example route workflow: geocode origin -> geocode destination -> call route planning tool with from_lat/from_lon/to_lat/to_lon from geocode results.",
        "  Example nearby CCTV workflow: geocode place -> call CCTV/bbox tool with minLon/minLat/maxLon/maxLat from geocode bbox.",
        '  Example EV charger workflow: geocode place -> call ev.searchStations with inputAdapter="point_radius_to_bbox" and input { "center": "$place.location", "radiusMeters": 2000, "availableOnly": false, "limit": 50 }.',
        "  Example election district workflow: if the user gives a place/address/station instead of an exact district name, call geo.geocode first, then call election.findDistrictByPoint with lon=$place.location.0 and lat=$place.location.1.",
        "  Administrative boundaries are always-available system tools. Use adminBoundary.searchBoundaries for names/codes and adminBoundary.findBoundaryByPoint for a selected or geocoded location.",
        "  Keep includeGeometry=false for administrative-boundary reference answers. Set includeGeometry=true only when the user asks to show or apply the boundary on the map.",
        "  Example web research workflow: when registered MCP/domain tools cannot answer, or the user asks for latest/current/public web information, call web.search first. Use web.fetch on one or two relevant search result URLs only when the snippets are insufficient.",
        '  For web.search, query is required. If a previous MCP step provides the search entity, combine it with the user topic, e.g. { "query": "$district.item.name 공약" }.',
        "  Web answers must mention source URLs from web.search/web.fetch results and must not invent facts beyond those results.",
        "  Note: Prefer read-only/status/search/planning tools. Do not use mutating tools unless the user explicitly asks for that exact operation.",
    ]

    if not tools:
        lines.append("  Available MCP tools: none loaded from Gateway.")
        return lines

    lines.append("  Available MCP tools:")
    for tool in tools[:_MAX_PROMPT_TOOLS]:
        lines.extend(_format_tool_for_prompt(tool))

    if len(tools) > _MAX_PROMPT_TOOLS:
        lines.append(f"  ...and {len(tools) - _MAX_PROMPT_TOOLS} more tools.")

    return lines


def build_generic_mcp_fallback_intent(
    text: str,
    allowed_server_ids: Optional[List[str]] = None,
    allowed_tool_refs: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Build a deterministic no-argument MCP intent when LLM parsing is unavailable."""
    normalized_text = _normalize(text)
    if not normalized_text:
        return None

    best_tool: Optional[Dict[str, Any]] = None
    best_score = 0

    for tool in _load_prompt_tools(allowed_server_ids, allowed_tool_refs):
        required = ((tool.get("inputSchema") or {}).get("required") or [])
        if required:
            continue

        score = _score_tool_match(normalized_text, tool)
        if score > best_score:
            best_tool = tool
            best_score = score

    if not best_tool or best_score <= 0:
        return None

    return {
        "action": GENERIC_MCP_ACTION,
        "server_id": best_tool.get("serverId"),
        "tool": best_tool.get("name"),
        "input": {},
        "answer_instruction": "도구 실행 결과를 사용자가 이해하기 쉽게 한국어로 요약한다.",
    }


async def execute_generic_mcp(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute one MCP tool or one MCP workflow chosen by the LLM."""
    intent = state.get("intent") or {}
    if intent.get("action") == GENERIC_MCP_WORKFLOW_ACTION:
        return await _execute_generic_mcp_workflow(state, intent)

    tool_name = _string_value(intent.get("tool") or intent.get("tool_name") or intent.get("qualifiedName"))
    server_id = _string_value(intent.get("server_id") or intent.get("serverId"))
    tool_input = intent.get("input") or intent.get("arguments") or {}
    allowed_server_ids = _allowed_mcp_server_ids(state)
    allowed_tool_refs = _allowed_mcp_tool_refs(state)

    if not tool_name:
        return _failed_result("호출할 MCP tool 이름이 없습니다.", intent)
    tool_name, server_id = _resolve_registered_tool_ref(tool_name, server_id, allowed_server_ids, allowed_tool_refs)
    if not _is_tool_allowed_by_values(server_id, tool_name, allowed_server_ids, allowed_tool_refs):
        return _failed_result("선택되지 않은 MCP tool은 실행할 수 없습니다.", intent, tool_name, server_id)
    if not isinstance(tool_input, dict):
        return _failed_result("MCP tool 입력값은 JSON object여야 합니다.", intent)

    try:
        tool_input = _resolve_value(tool_input, _build_resolution_scope(state))
    except Exception as exc:
        return _failed_result(f"MCP tool 입력 참조를 해석하지 못했습니다: {exc}", intent, tool_name, server_id)

    if not isinstance(tool_input, dict):
        return _failed_result("해석된 MCP tool 입력값은 JSON object여야 합니다.", intent, tool_name, server_id)

    tool_input = _prepare_tool_input(tool_input, server_id, tool_name, state, _build_resolution_scope(state))
    missing_fields = _validate_required_inputs(server_id, tool_name, tool_input)
    if missing_fields:
        return _failed_result(f"MCP tool 필수 입력값이 비어 있습니다: {', '.join(missing_fields)}", intent, tool_name, server_id)

    try:
        result = mcp_client.execute_tool(
            tool_name,
            tool_input,
            user_context=_execution_user_context(state),
            server_id=server_id or None,
        )
    except Exception as exc:
        raw_error = str(exc)
        logger.error("Generic MCP tool execution failed: %s", raw_error)
        return _failed_result(_friendly_mcp_error(tool_name, raw_error), intent, tool_name, server_id)

    display_artifacts = inspect_mcp_result(result, {
        "tool": tool_name,
        "server_id": server_id,
    })
    commands = build_commands_from_artifacts(display_artifacts)
    answer = await _compose_answer(state, tool_name, server_id, tool_input, result)
    return {
        "artifacts": {
            **dict(state.get("artifacts", {}) or {}),
            "mcp_result": result,
            "display_artifacts": display_artifacts,
        },
        "executor_state": {
            "status": "success",
            "generic_mcp": True,
            "mcp_servers": [server_id] if server_id else [],
            "mcp_tools": [_qualified_tool_label(server_id, tool_name)],
            "display_artifacts": _artifact_kind_labels(display_artifacts),
        },
        "commands": commands,
        "answer_draft": answer,
        "errors": [],
    }


async def _execute_generic_mcp_workflow(state: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a sequence of MCP tool calls with reference-based data flow."""
    steps = intent.get("steps") or []
    if not isinstance(steps, list) or not steps:
        return _failed_result("MCP workflow 단계가 없습니다.", intent)
    if len(steps) > _MAX_WORKFLOW_STEPS:
        return _failed_result(f"MCP workflow 단계가 너무 많습니다. 최대 {_MAX_WORKFLOW_STEPS}개까지 허용합니다.", intent)

    scope: Dict[str, Any] = _build_resolution_scope(state)
    trace: List[Dict[str, Any]] = []
    used_servers: List[str] = []
    used_tools: List[str] = []
    used_adapters: List[str] = []
    allowed_server_ids = _allowed_mcp_server_ids(state)
    allowed_tool_refs = _allowed_mcp_tool_refs(state)

    for index, raw_step in enumerate(steps):
        if not isinstance(raw_step, dict):
            return _failed_workflow_result("MCP workflow step은 JSON object여야 합니다.", intent, trace, used_servers, used_tools)

        step_id = _safe_step_id(raw_step.get("id") or raw_step.get("save_as") or f"step_{index + 1}")
        tool_name = _string_value(raw_step.get("tool") or raw_step.get("tool_name") or raw_step.get("qualifiedName"))
        server_id = _string_value(raw_step.get("server_id") or raw_step.get("serverId"))
        input_adapter = _string_value(raw_step.get("inputAdapter") or raw_step.get("input_adapter") or raw_step.get("adapter"))
        step_input = raw_step.get("input") or raw_step.get("arguments") or {}

        if not tool_name:
            return _failed_workflow_result(f"{step_id} 단계에 MCP tool 이름이 없습니다.", intent, trace, used_servers, used_tools)
        tool_name, server_id = _resolve_registered_tool_ref(tool_name, server_id, allowed_server_ids, allowed_tool_refs)
        if not _is_tool_allowed_by_values(server_id, tool_name, allowed_server_ids, allowed_tool_refs):
            return _failed_workflow_result(f"{step_id} 단계는 선택되지 않은 MCP tool을 실행할 수 없습니다.", intent, trace, used_servers, used_tools)
        if not isinstance(step_input, dict):
            return _failed_workflow_result(f"{step_id} 단계의 입력값은 JSON object여야 합니다.", intent, trace, used_servers, used_tools)

        try:
            resolved_input = _resolve_value(step_input, scope)
        except Exception as exc:
            return _failed_workflow_result(f"{step_id} 단계 입력 참조를 해석하지 못했습니다: {exc}", intent, trace, used_servers, used_tools)

        if not isinstance(resolved_input, dict):
            return _failed_workflow_result(f"{step_id} 단계의 해석된 입력값은 JSON object여야 합니다.", intent, trace, used_servers, used_tools)

        try:
            resolved_input, applied_adapter = _apply_input_adapter(
                input_adapter,
                resolved_input,
                server_id,
                tool_name,
            )
        except Exception as exc:
            return _failed_workflow_result(
                _friendly_workflow_input_error(step_id, tool_name, str(exc)),
                intent,
                trace,
                used_servers,
                used_tools,
            )

        resolved_input = _prepare_tool_input(resolved_input, server_id, tool_name, state, scope, step_id)
        label = _qualified_tool_label(server_id, tool_name)
        used_servers.append(server_id)
        used_tools.append(label)
        if applied_adapter:
            used_adapters.append(applied_adapter)

        missing_fields = _validate_required_inputs(server_id, tool_name, resolved_input)
        if missing_fields:
            message = f"{step_id} 단계 필수 입력값이 비어 있습니다: {', '.join(missing_fields)}"
            trace.append({
                "id": step_id,
                "server_id": server_id,
                "tool": tool_name,
                "inputAdapter": applied_adapter or input_adapter or None,
                "input": resolved_input,
                "error": message,
            })
            return _failed_workflow_result(message, intent, trace, used_servers, used_tools)

        try:
            result = mcp_client.execute_tool(
                tool_name,
                resolved_input,
                user_context=_execution_user_context(state),
                server_id=server_id or None,
            )
        except Exception as exc:
            raw_error = str(exc)
            friendly_error = _friendly_workflow_tool_error(step_id, tool_name, raw_error)
            logger.error("Generic MCP workflow step failed (%s): %s", step_id, raw_error)
            trace.append({
                "id": step_id,
                "server_id": server_id,
                "tool": tool_name,
                "inputAdapter": applied_adapter or input_adapter or None,
                "input": resolved_input,
                "error": friendly_error,
                "error_detail": raw_error,
            })
            return _failed_workflow_result(friendly_error, intent, trace, used_servers, used_tools)

        scope[step_id] = result
        trace.append({
            "id": step_id,
            "server_id": server_id,
            "tool": tool_name,
            "inputAdapter": applied_adapter or input_adapter or None,
            "input": resolved_input,
            "result": result,
        })

    display_artifacts = inspect_mcp_trace(trace)
    commands = build_commands_from_artifacts(display_artifacts)
    answer = await _compose_workflow_answer(state, intent, trace)
    return {
        "artifacts": {
            **dict(state.get("artifacts", {}) or {}),
            "mcp_workflow_results": {
                item["id"]: item.get("result")
                for item in trace
                if "result" in item
            },
            "mcp_workflow_trace": trace,
            "display_artifacts": display_artifacts,
        },
        "executor_state": {
            "status": "success",
            "generic_mcp": True,
            "mcp_workflow": True,
            "mcp_servers": _dedupe_strings(used_servers),
            "mcp_tools": _dedupe_strings(used_tools),
            "workflow_steps": [item["id"] for item in trace],
            "input_adapters": _dedupe_strings(used_adapters),
            "display_artifacts": _artifact_kind_labels(display_artifacts),
        },
        "commands": commands,
        "answer_draft": answer,
        "errors": [],
    }


async def _compose_answer(
    state: Dict[str, Any],
    tool_name: str,
    server_id: str,
    tool_input: Dict[str, Any],
    result: Any,
) -> str:
    """Use Gemini to turn raw MCP output into a concise Korean answer."""
    if not settings.GEMINI_API_KEY:
        return _fallback_answer(tool_name, server_id, result)

    result_text = _json_preview(result, _MAX_RESULT_CHARS)
    input_text = _json_preview(tool_input, 3000)
    intent = state.get("intent") or {}
    instruction = intent.get("answer_instruction") or "도구 실행 결과를 한국어로 간결하게 설명한다."
    prompt = (
        "You are the final answer writer for an MCP-powered orchestration system.\n"
        "Answer in Korean Markdown.\n"
        "Use only the MCP result below. Do not invent missing facts.\n"
        "If the result is an error or empty, say what failed and what information is missing.\n\n"
        f"User request:\n{state.get('user_text')}\n\n"
        f"MCP server: {server_id or '(auto-routed)'}\n"
        f"MCP tool: {tool_name}\n"
        f"Tool input JSON:\n{input_text}\n\n"
        f"Answer instruction:\n{instruction}\n\n"
        f"MCP result JSON:\n{result_text}\n"
    )

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as exc:
        logger.error("Generic MCP answer composition failed: %s", exc)
        return _fallback_answer(tool_name, server_id, result)


async def _compose_workflow_answer(state: Dict[str, Any], intent: Dict[str, Any], trace: List[Dict[str, Any]]) -> str:
    """Compose the Korean answer from the workflow trace.

    agentic_ai replacement: the original called Gemini and fell back to a raw
    JSON dump. We do not use that API key, and the call order is what this
    system has to show, so the answer is built in vendor/asap/workflow_answer.py.
    """
    return compose_workflow_answer(intent, trace)


def _load_prompt_tools(
    allowed_server_ids: Optional[List[str]] = None,
    allowed_tool_refs: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Load safe-ish registered tools for generic prompt exposure."""
    try:
        tools = mcp_client.get_tools()
    except Exception as exc:
        logger.warning("Failed to load MCP tools for generic prompt: %s", exc)
        return []

    return [
        tool for tool in tools
        if _is_prompt_safe_tool(tool) and _is_tool_allowed(tool, allowed_server_ids, allowed_tool_refs)
    ]


def _is_prompt_safe_tool(tool: Dict[str, Any]) -> bool:
    """Avoid exposing obvious mutating tools to generic LLM routing by default."""
    name = str(tool.get("name") or "").lower()
    description = str(tool.get("description") or "").lower()
    haystack = f"{name} {description}"
    return not any(word in haystack for word in _BLOCKED_TOOL_WORDS)


def _resolve_registered_tool_ref(
    tool_name: str,
    server_id: str = "",
    allowed_server_ids: Optional[List[str]] = None,
    allowed_tool_refs: Optional[List[str]] = None,
) -> tuple[str, str]:
    """Normalize short LLM tool names such as `search` to registered names like `web.search`."""
    try:
        tools = mcp_client.get_tools()
    except Exception as exc:
        logger.warning("Failed to resolve registered MCP tool name: %s", exc)
        return tool_name, server_id

    parsed_server_id = server_id
    parsed_tool_name = tool_name
    if "/" in parsed_tool_name:
        maybe_server, maybe_tool = parsed_tool_name.split("/", 1)
        if maybe_server and maybe_tool:
            parsed_server_id = parsed_server_id or maybe_server
            parsed_tool_name = maybe_tool

    scoped_tools = [
        tool for tool in tools
        if _is_tool_allowed(tool, allowed_server_ids, allowed_tool_refs)
    ]
    matches = _registered_tool_matches(parsed_tool_name, parsed_server_id, scoped_tools)
    if not matches:
        return tool_name, server_id

    match = matches[0]
    resolved_name = str(match.get("name") or parsed_tool_name)
    resolved_server = str(match.get("serverId") or parsed_server_id or server_id)
    if resolved_name != tool_name or resolved_server != server_id:
        logger.info(
            "Resolved MCP tool alias '%s' (server=%s) to '%s' (server=%s)",
            tool_name,
            server_id or "auto",
            resolved_name,
            resolved_server or "auto",
        )
    return resolved_name, resolved_server


def _registered_tool_matches(tool_name: str, server_id: str, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_name = _normalize_tool_ref(tool_name)
    scoped_tools = [
        tool for tool in tools
        if not server_id or _is_server_scope_match(tool, server_id)
    ]

    exact_matches = [
        tool for tool in scoped_tools
        if _normalize_tool_ref(tool.get("name")) == normalized_name
        or _normalize_tool_ref(tool.get("qualifiedName")) == normalized_name
    ]
    if exact_matches:
        return exact_matches

    return [
        tool for tool in scoped_tools
        if _normalize_tool_ref(str(tool.get("name") or "").split(".")[-1]) == normalized_name
        or (
            server_id
            and _normalize_tool_ref(f"{tool.get('serverId')}/{str(tool.get('name') or '').split('.')[-1]}") == normalized_name
        )
    ]


def _is_server_scope_match(tool: Dict[str, Any], server_id: str) -> bool:
    normalized_server_id = _normalize_tool_ref(server_id)
    tool_server_id = _normalize_tool_ref(tool.get("serverId"))
    tool_name = _normalize_tool_ref(tool.get("name"))
    tool_namespace = tool_name.split(".", 1)[0] if "." in tool_name else ""
    qualified_server_id = _normalize_tool_ref(tool.get("qualifiedName")).split("/", 1)[0]

    return (
        tool_server_id == normalized_server_id
        or tool_namespace == normalized_server_id
        or qualified_server_id == normalized_server_id
    )


def _normalize_tool_ref(value: Any) -> str:
    return str(value or "").strip().lower()


def _allowed_mcp_server_ids(state: Dict[str, Any]) -> Optional[List[str]]:
    """Return the user's applied MCP server IDs, or None when no scope was provided."""
    value = state.get("enabled_mcp_server_ids")
    if not isinstance(value, list):
        return None
    return [str(item).strip() for item in value if str(item).strip()]


def _allowed_mcp_tool_refs(state: Dict[str, Any]) -> Optional[List[str]]:
    """Return the user's applied MCP tool refs, or None when no tool-level scope was provided."""
    value = state.get("enabled_mcp_tool_refs")
    if not isinstance(value, list):
        return None
    return [_normalize_tool_ref(item) for item in value if _normalize_tool_ref(item)]


def _is_server_allowed(server_id: str, allowed_server_ids: Optional[List[str]]) -> bool:
    if allowed_server_ids is None:
        return True
    normalized_server_id = _normalize_tool_ref(server_id)
    return normalized_server_id in {_normalize_tool_ref(item) for item in allowed_server_ids}


def _is_tool_allowed(
    tool: Dict[str, Any],
    allowed_server_ids: Optional[List[str]],
    allowed_tool_refs: Optional[List[str]],
) -> bool:
    server_id = str(tool.get("serverId") or "")
    tool_name = str(tool.get("name") or "")
    qualified_name = str(tool.get("qualifiedName") or "")
    return _is_tool_allowed_by_values(server_id, tool_name, allowed_server_ids, allowed_tool_refs, qualified_name)


def _is_tool_allowed_by_values(
    server_id: str,
    tool_name: str,
    allowed_server_ids: Optional[List[str]],
    allowed_tool_refs: Optional[List[str]],
    qualified_name: str = "",
) -> bool:
    if allowed_tool_refs is not None:
        return _is_tool_ref_allowed(server_id, tool_name, qualified_name, allowed_tool_refs)
    return _is_server_allowed(server_id, allowed_server_ids)


def _is_tool_ref_allowed(
    server_id: str,
    tool_name: str,
    qualified_name: str,
    allowed_tool_refs: List[str],
) -> bool:
    normalized_server_id = _normalize_tool_ref(server_id)
    normalized_tool_name = _normalize_tool_ref(tool_name)
    normalized_qualified = _normalize_tool_ref(qualified_name or f"{server_id}/{tool_name}")
    exact_ref = f"{normalized_server_id}/{normalized_tool_name}"
    normalized_refs = {_normalize_tool_ref(item) for item in allowed_tool_refs if _normalize_tool_ref(item)}

    return (
        f"{normalized_server_id}/*" in normalized_refs
        or exact_ref in normalized_refs
        or normalized_qualified in normalized_refs
    )


def _execution_user_context(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Attach the MCP selection scope when calling Gateway tools."""
    user_context = dict(state.get("user_context") or {})
    allowed_server_ids = state.get("enabled_mcp_server_ids")
    if isinstance(allowed_server_ids, list):
        user_context["selected_mcp_server_ids"] = [
            str(item).strip()
            for item in allowed_server_ids
            if str(item).strip()
        ]
    allowed_tool_refs = state.get("enabled_mcp_tool_refs")
    if isinstance(allowed_tool_refs, list):
        user_context["selected_mcp_tool_refs"] = [
            _normalize_tool_ref(item)
            for item in allowed_tool_refs
            if _normalize_tool_ref(item)
        ]
    return user_context or None


def _format_tool_for_prompt(tool: Dict[str, Any]) -> List[str]:
    name = tool.get("name")
    server_id = tool.get("serverId")
    description = " ".join(str(tool.get("description") or "").split())
    schema = tool.get("inputSchema") or {}
    required = schema.get("required") or []
    properties = schema.get("properties") or {}

    lines = [
        f"    - server_id={server_id}, tool={name}: {_truncate(description, 220)}",
    ]

    if properties:
        field_bits = []
        for field_name, field_schema in list(properties.items())[:12]:
            field_type = field_schema.get("type") if isinstance(field_schema, dict) else None
            required_mark = " required" if field_name in required else ""
            field_bits.append(f"{field_name}:{field_type or 'any'}{required_mark}")
        lines.append(f"      input fields: {', '.join(field_bits)}")
    else:
        lines.append("      input fields: none")

    return lines


def _failed_result(
    message: str,
    intent: Dict[str, Any],
    tool_name: str = "",
    server_id: str = "",
) -> Dict[str, Any]:
    return {
        "artifacts": {},
        "executor_state": {
            "status": "failed",
            "generic_mcp": True,
            "mcp_servers": [server_id] if server_id else [],
            "mcp_tools": [_qualified_tool_label(server_id, tool_name)] if tool_name else [],
            "intent": intent,
        },
        "commands": [],
        "answer_draft": message,
        "errors": [message],
    }


def _friendly_mcp_error(tool_name: str, raw_error: str) -> str:
    """Convert low-level MCP errors into compact user-facing messages."""
    normalized = raw_error.lower()
    if tool_name == "road.getCctv":
        if "외부 api 연동 실패 (its)" in normalized or "internal server error" in normalized or "503" in normalized:
            return "ITS CCTV 외부 API 연동이 일시적으로 실패했습니다. 잠시 후 다시 시도해 주세요."
        if "center/location" in raw_error or "필수 입력값" in raw_error:
            return "CCTV를 조회할 기준 지도 범위 또는 중심 좌표가 없습니다."
    return f"MCP tool 실행에 실패했습니다: {raw_error}"


def _friendly_workflow_input_error(step_id: str, tool_name: str, raw_error: str) -> str:
    """Convert workflow input adapter failures into actionable messages."""
    if tool_name == "road.getCctv" and "center/location" in raw_error:
        return f"{step_id} 단계에서 CCTV를 조회할 기준 중심 좌표를 찾지 못했습니다."
    return f"{step_id} 단계 입력 변환에 실패했습니다: {raw_error}"


def _friendly_workflow_tool_error(step_id: str, tool_name: str, raw_error: str) -> str:
    """Convert workflow tool execution failures into actionable messages."""
    normalized = raw_error.lower()
    if tool_name == "road.getCctv":
        if "외부 api 연동 실패 (its)" in normalized or "internal server error" in normalized or "503" in normalized:
            return "ITS CCTV 외부 API 연동이 일시적으로 실패했습니다. 잠시 후 다시 시도해 주세요."
        if "center/location" in raw_error or "필수 입력값" in raw_error:
            return f"{step_id} 단계에서 CCTV를 조회할 기준 지도 범위 또는 중심 좌표가 없습니다."
    return f"{step_id} 단계 MCP tool 실행에 실패했습니다: {raw_error}"


def _failed_workflow_result(
    message: str,
    intent: Dict[str, Any],
    trace: List[Dict[str, Any]],
    used_servers: List[str],
    used_tools: List[str],
) -> Dict[str, Any]:
    return {
        "artifacts": {
            "mcp_workflow_trace": trace,
        },
        "executor_state": {
            "status": "failed",
            "generic_mcp": True,
            "mcp_workflow": True,
            "mcp_servers": _dedupe_strings(used_servers),
            "mcp_tools": _dedupe_strings(used_tools),
            "intent": intent,
        },
        "commands": [],
        "answer_draft": message,
        "errors": [message],
    }


def _fallback_answer(tool_name: str, server_id: str, result: Any) -> str:
    result_text = _json_preview(result, 4000)
    label = _qualified_tool_label(server_id, tool_name)
    return f"**{label}** MCP 실행 결과입니다.\n\n```json\n{result_text}\n```"


def _fallback_workflow_answer(trace: List[Dict[str, Any]]) -> str:
    result_text = _json_preview(trace, 6000)
    return f"**MCP workflow** 실행 결과입니다.\n\n```json\n{result_text}\n```"


def _qualified_tool_label(server_id: str, tool_name: str) -> str:
    return f"{server_id}/{tool_name}" if server_id else tool_name


def _artifact_kind_labels(display_artifacts: List[Dict[str, Any]]) -> List[str]:
    """Return compact labels for generation-process UI/debugging."""
    labels: List[str] = []
    for artifact in display_artifacts:
        kind = str(artifact.get("kind") or "").strip()
        title = str(artifact.get("title") or "").strip()
        if kind and title:
            labels.append(f"{title} ({kind})")
        elif kind:
            labels.append(kind)
    return _dedupe_strings(labels)


def _json_preview(value: Any, limit: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        text = str(value)
    return _truncate(text, limit)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _score_tool_match(normalized_text: str, tool: Dict[str, Any]) -> int:
    haystack = _normalize(
        f"{tool.get('serverId', '')} {tool.get('name', '')} {tool.get('description', '')}"
    )
    score = 0
    for token in _tokens(normalized_text):
        if token in haystack:
            score += 10
    return score


def _normalize(text: str) -> str:
    return " ".join(str(text).strip().lower().split())


def _tokens(text: str) -> List[str]:
    return [token for token in re.split(r"[^0-9a-zA-Z가-힣_.-]+", text) if token]


def _string_value(value: Any) -> str:
    return str(value).strip() if value not in (None, "", [], {}) else ""


def _safe_step_id(value: Any) -> str:
    text = re.sub(r"[^0-9a-zA-Z_-]+", "_", str(value or "").strip())
    return text or "step"


def _build_resolution_scope(state: Dict[str, Any]) -> Dict[str, Any]:
    """Build reference scope for workflow outputs and frontend context."""
    context = state.get("context") if isinstance(state, dict) else {}
    if not isinstance(context, dict):
        context = {}

    scope: Dict[str, Any] = {"context": context}
    selected_location = context.get("selectedLocation")
    if isinstance(selected_location, dict):
        scope["selectedLocation"] = selected_location
    return scope


def _resolve_value(value: Any, scope: Dict[str, Any]) -> Any:
    """Resolve `$step.path` and `$context.path` references recursively."""
    if isinstance(value, dict):
        return {key: _resolve_value(item, scope) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, scope) for item in value]
    if isinstance(value, str) and "$" in value:
        return _resolve_string_references(value, scope)
    return value


_REFERENCE_PATTERN = re.compile(r"\$[A-Za-z_][0-9A-Za-z_-]*(?:\.[0-9A-Za-z_-]+|\[\d+\])*")


def _resolve_string_references(value: str, scope: Dict[str, Any]) -> Any:
    """Resolve both pure references and mixed text templates.

    Pure references keep their original type, e.g. "$origin.location.1" -> 37.5.
    Mixed templates become strings, e.g. "$district.item.name 공약" -> "경기 의왕과천 공약".
    """
    text = value.strip()
    if _REFERENCE_PATTERN.fullmatch(text):
        return _resolve_reference(text, scope)

    def replace(match: re.Match[str]) -> str:
        resolved = _resolve_reference(match.group(0), scope)
        if resolved in (None, "", [], {}):
            return ""
        if isinstance(resolved, (dict, list)):
            return json.dumps(resolved, ensure_ascii=False)
        return str(resolved)

    return " ".join(_REFERENCE_PATTERN.sub(replace, value).split())


def _resolve_reference(reference: str, scope: Dict[str, Any]) -> Any:
    ref = reference.strip()[1:]
    if ref.startswith("steps."):
        ref = ref[len("steps."):]
    ref = re.sub(r"\[(\d+)\]", r".\1", ref)
    path = [part for part in ref.split(".") if part]
    if not path:
        return None

    current: Any = scope.get(path[0])
    for key in path[1:]:
        if current is None:
            return None
        if isinstance(current, dict):
            if key in {"lat", "latitude"} and "location" in current:
                current = _coordinate_component(current.get("location"), 1)
                continue
            if key in {"lon", "lng", "longitude"} and "location" in current:
                current = _coordinate_component(current.get("location"), 0)
                continue
            if key in {"minLon", "minX"} and "bbox" in current:
                current = _bbox_component(current.get("bbox"), 0, 0)
                continue
            if key in {"minLat", "minY"} and "bbox" in current:
                current = _bbox_component(current.get("bbox"), 0, 1)
                continue
            if key in {"maxLon", "maxX"} and "bbox" in current:
                current = _bbox_component(current.get("bbox"), 1, 0)
                continue
            if key in {"maxLat", "maxY"} and "bbox" in current:
                current = _bbox_component(current.get("bbox"), 1, 1)
                continue
            current = current.get(key)
            continue
        if isinstance(current, list) and key.isdigit():
            index = int(key)
            current = current[index] if 0 <= index < len(current) else None
            continue
        if isinstance(current, list) and key in {"lat", "latitude"}:
            current = _coordinate_component(current, 1)
            continue
        if isinstance(current, list) and key in {"lon", "lng", "longitude"}:
            current = _coordinate_component(current, 0)
            continue
        return None
    return current


def _coordinate_component(value: Any, index: int) -> Any:
    """Read lon/lat component from common coordinate shapes."""
    if isinstance(value, list) and len(value) > index:
        return value[index]
    if isinstance(value, tuple) and len(value) > index:
        return value[index]
    if isinstance(value, dict):
        if index == 0:
            return value.get("lon") or value.get("lng") or value.get("longitude") or value.get("x")
        return value.get("lat") or value.get("latitude") or value.get("y")
    return None


def _bbox_component(value: Any, corner_index: int, coord_index: int) -> Any:
    """Read a bbox component from [[minLon, minLat], [maxLon, maxLat]]."""
    if isinstance(value, list) and len(value) > corner_index:
        corner = value[corner_index]
        if isinstance(corner, list) and len(corner) > coord_index:
            return corner[coord_index]
    return None


def _prepare_tool_input(
    tool_input: Dict[str, Any],
    server_id: str,
    tool_name: str,
    state: Dict[str, Any],
    scope: Dict[str, Any],
    step_id: str = "",
) -> Dict[str, Any]:
    """Apply safe last-mile input repairs before required-field validation."""
    if not _is_web_search_tool(server_id, tool_name):
        return tool_input
    if not _is_empty_value(tool_input.get("query")):
        return tool_input

    query = _build_web_search_query(state, scope, step_id)
    if not query:
        return tool_input

    repaired = dict(tool_input)
    repaired["query"] = query
    logger.info("Filled missing web.search query for step '%s': %s", step_id or "single", query)
    return repaired


def _is_web_search_tool(server_id: str, tool_name: str) -> bool:
    normalized_tool = _normalize_tool_ref(tool_name)
    normalized_server = _normalize_tool_ref(server_id)
    return normalized_tool in {"web.search", "search"} and normalized_server in {"", "web", "web-search"}


def _build_web_search_query(state: Dict[str, Any], scope: Dict[str, Any], step_id: str = "") -> str:
    user_text = " ".join(str(state.get("user_text") or "").split())
    if not user_text:
        return ""

    entities = _extract_search_entities(scope)
    keywords = _extract_search_keywords(user_text, step_id)
    if not entities:
        return keywords or user_text

    return _join_query_parts([entities[0], keywords or user_text])


def _extract_search_keywords(user_text: str, step_id: str = "") -> str:
    text = user_text
    replacements = [
        "관심 지점",
        "선택한 위치",
        "이 위치",
        "이곳",
        "여기",
        "검색해줘",
        "검색해 줘",
        "검색",
        "찾아줘",
        "찾아 줘",
        "알려줘",
        "알려 줘",
        "보여줘",
        "보여 줘",
        "조회해줘",
        "조회해 줘",
        "확인해줘",
        "확인해 줘",
    ]
    for token in replacements:
        text = text.replace(token, " ")

    text = " ".join(text.split())
    if "promise" in _normalize_tool_ref(step_id) and "공약" not in text:
        text = _join_query_parts([text, "공약"])
    if text:
        return text

    if "공약" in user_text or "promise" in _normalize_tool_ref(step_id):
        return "공약"
    return user_text


def _extract_search_entities(scope: Dict[str, Any]) -> List[str]:
    """Prioritize human-readable names from previous MCP outputs for web search."""
    entities: List[str] = []
    for value in scope.values():
        _collect_election_entities(value, entities)
    return _dedupe_strings(entities)


def _collect_election_entities(value: Any, entities: List[str]) -> None:
    if isinstance(value, dict):
        item = value.get("item")
        if isinstance(item, dict):
            name = _string_value(item.get("name"))
            sido = _string_value(item.get("sido"))
            district = _string_value(item.get("district"))
            if name:
                entities.append(name)
            if sido and district:
                entities.append(f"{sido} {district}")
            if district:
                entities.append(district)

        for feature in value.get("features") or []:
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties") or {}
            if not isinstance(props, dict):
                continue
            for key in ("SIDO_SGG", "name", "label", "SGG"):
                text = _string_value(props.get(key))
                if text:
                    entities.append(text)

        for child in value.values():
            if isinstance(child, (dict, list)):
                _collect_election_entities(child, entities)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                _collect_election_entities(item, entities)


def _join_query_parts(parts: List[str]) -> str:
    query_parts: List[str] = []
    normalized_query = ""
    for part in parts:
        text = " ".join(str(part or "").split())
        if not text:
            continue
        normalized_text = _normalize(text).replace(" ", "")
        if normalized_text and normalized_text in normalized_query:
            continue
        query_parts.append(text)
        normalized_query = _normalize(" ".join(query_parts)).replace(" ", "")
    return " ".join(query_parts)


def _is_empty_value(value: Any) -> bool:
    return value in (None, "", [], {})


def _apply_input_adapter(
    adapter_name: str,
    tool_input: Dict[str, Any],
    server_id: str,
    tool_name: str,
) -> tuple[Dict[str, Any], str]:
    """Apply deterministic workflow input adapters before MCP execution."""
    normalized_adapter = _normalize_adapter_name(adapter_name)
    if normalized_adapter:
        if normalized_adapter == "point_radius_to_bbox":
            return _point_radius_to_bbox_input(tool_input), normalized_adapter
        raise ValueError(f"지원하지 않는 inputAdapter입니다: {adapter_name}")

    if _should_auto_apply_point_radius_to_bbox(server_id, tool_name, tool_input):
        return _point_radius_to_bbox_input(tool_input), "point_radius_to_bbox:auto"

    return tool_input, ""


def _normalize_adapter_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("-", "_")


def _should_auto_apply_point_radius_to_bbox(
    server_id: str,
    tool_name: str,
    tool_input: Dict[str, Any],
) -> bool:
    """Auto-apply radius conversion for bbox tools when the shape is obvious."""
    if _extract_center_point(tool_input) is None:
        return False
    if _extract_radius_meters(tool_input, default=None) is None:
        return False

    schema = _find_tool_schema(server_id, tool_name)
    required = set(schema.get("required") or []) if isinstance(schema, dict) else set()
    bbox_required = {"minLon", "minLat", "maxLon", "maxLat"}
    return bbox_required.issubset(required)


def _point_radius_to_bbox_input(tool_input: Dict[str, Any]) -> Dict[str, float]:
    """Convert center + radiusMeters into road.getCctv-style bbox fields."""
    center = _extract_center_point(tool_input)
    if center is None:
        raise ValueError("point_radius_to_bbox에는 center/location 좌표가 필요합니다.")

    radius_meters = _extract_radius_meters(tool_input, default=1000.0)
    if radius_meters <= 0:
        raise ValueError("radiusMeters는 0보다 커야 합니다.")

    lon, lat = center
    delta_lat = radius_meters / 111_320.0
    lon_scale = 111_320.0 * max(math.cos(math.radians(lat)), 0.01)
    delta_lon = radius_meters / lon_scale

    passthrough = {
        key: value
        for key, value in tool_input.items()
        if key
        not in {
            "center",
            "point",
            "coordinate",
            "coordinates",
            "location",
            "radius",
            "radiusMeters",
            "radius_meters",
            "radiusKm",
            "radius_km",
            "distance",
            "distanceMeters",
            "distance_meters",
            "distanceKm",
            "distance_km",
        }
    }

    return {
        **passthrough,
        "minLon": round(lon - delta_lon, 7),
        "minLat": round(lat - delta_lat, 7),
        "maxLon": round(lon + delta_lon, 7),
        "maxLat": round(lat + delta_lat, 7),
    }


def _extract_center_point(tool_input: Dict[str, Any]) -> Optional[tuple[float, float]]:
    """Extract lon/lat from common center payload shapes."""
    for key in ("center", "point", "coordinate", "coordinates", "location"):
        point = _parse_lon_lat(tool_input.get(key))
        if point is not None:
            return point

    return _parse_lon_lat(tool_input)


def _parse_lon_lat(value: Any) -> Optional[tuple[float, float]]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        if _is_number(value[0]) and _is_number(value[1]):
            lon = float(value[0])
            lat = float(value[1])
            if -180 <= lon <= 180 and -90 <= lat <= 90:
                return lon, lat
        return None

    if isinstance(value, dict):
        location = _first_present(value, "location", "coordinates")
        nested = _parse_lon_lat(location)
        if nested is not None:
            return nested

        lon_value = _first_present(value, "lon", "lng", "longitude", "x")
        lat_value = _first_present(value, "lat", "latitude", "y")
        if _is_number(lon_value) and _is_number(lat_value):
            lon = float(lon_value)
            lat = float(lat_value)
            if -180 <= lon <= 180 and -90 <= lat <= 90:
                return lon, lat

    return None


def _first_present(value: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        item = value.get(key)
        if item not in (None, ""):
            return item
    return None


def _extract_radius_meters(tool_input: Dict[str, Any], default: Optional[float]) -> Optional[float]:
    """Extract a radius in meters from common meter/km field names."""
    for key in ("radiusMeters", "radius_meters", "distanceMeters", "distance_meters"):
        value = tool_input.get(key)
        if value not in (None, ""):
            return _parse_distance_meters(value, default)

    for key in ("radiusKm", "radius_km", "distanceKm", "distance_km"):
        value = tool_input.get(key)
        if value not in (None, ""):
            meters = _parse_distance_meters(value, default)
            return meters * 1000 if meters is not None and _is_number(value) else meters

    for key in ("radius", "distance"):
        value = tool_input.get(key)
        if value not in (None, ""):
            return _parse_distance_meters(value, default)

    return default


def _parse_distance_meters(value: Any, default: Optional[float]) -> Optional[float]:
    if _is_number(value):
        return float(value)

    text = str(value or "").strip().lower().replace(",", "")
    if not text:
        return default

    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(km|킬로미터|키로미터|m|meter|meters|미터)?", text)
    if not match:
        return default

    amount = float(match.group(1))
    unit = match.group(2) or "m"
    if unit in {"km", "킬로미터", "키로미터"}:
        return amount * 1000
    return amount


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _validate_required_inputs(server_id: str, tool_name: str, tool_input: Dict[str, Any]) -> List[str]:
    """Validate top-level required fields from the Gateway tool schema before execution."""
    schema = _find_tool_schema(server_id, tool_name)
    required = schema.get("required") if isinstance(schema, dict) else []
    if not isinstance(required, list):
        return []

    missing = []
    for field in required:
        value = tool_input.get(field)
        if value in (None, "", [], {}):
            missing.append(str(field))
    return missing


def _find_tool_schema(server_id: str, tool_name: str) -> Dict[str, Any]:
    """Find one registered tool inputSchema for validation."""
    try:
        tools = mcp_client.get_tools()
    except Exception:
        return {}

    for tool in tools:
        if tool.get("name") != tool_name:
            continue
        if server_id and tool.get("serverId") != server_id:
            continue
        schema = tool.get("inputSchema")
        return schema if isinstance(schema, dict) else {}
    return {}


def _dedupe_strings(values: List[str]) -> List[str]:
    seen = set()
    items: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items
