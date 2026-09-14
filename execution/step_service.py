"""recipe 의 노드 사슬을 게시할 execution 블록으로 compile 한다. **요청 중에 부르지 않는다.**

    온톨로지 + 사람이 받아들인 노드 사슬
      -> compile_execution
      -> recipe 파일의 execution 블록        (registration/publish.py 가 적는다)
      -> execution/plan_service.py 가 읽어 vendor 계획으로 채운다

**도구 식별과 입력 배선은 온톨로지 노드의 tool 이 갖는다.** 여기는 그것을 읽어
경로의 한 자리에서 칸마다 값이 어디서 오는지를 기호로 적는다.

    tool.id          "<server_id>/<도구>"   Gateway 의 MCP 도구
                     "builtin/<이름>"       vendor 어댑터로 뒤 단계에 얹는 transform
                     "frontend/<명령>"      도구를 안 부르고 내는 지도 명령
    tool.parameters  도구 칸 -> 값
    tool.outputs     semantic 타입 -> 그 도구의 raw 응답 안에서 그 값을 읽는 경로

**값이 어디서 오는가는 경로가 정한다.** 한 노드가 이 자리에서 받는 semantic 타입은
앞 노드가 건네는 것이고(graph.handed_types), 그 값의 출처는 셋 중 하나다.

    source    앞 노드가 경로의 시작 노드다. 그 노드의 source 가 말한다
                spoken.argument   -> {from: spoken.argument}
                context.<경로>    -> {from: context.<시작 노드>.<칸>}
    step      앞 노드가 도구 단계다  -> {from: s<N>.<타입>.<칸>}
    adapter   앞 노드가 builtin 이다 -> 뒤 단계의 transform 과 {from: transform.<타입>.<칸>}

그 자리에서 건네받지 않은 타입을 가리키는 칸은 안 적는다. 전기차 충전소 검색은
키워드 뒤에서는 query 만, 지도 범위 뒤에서는 범위 네 칸만 나간다.

**semantic 칸이 raw 값의 어디 있는지는 값을 내놓는 쪽이 적는다.** 받는 쪽 기호는
semantic 칸만 적고, 경로는 내놓는 쪽 선언에서 뒤 노드가 실제로 읽는 칸만 옮긴다.

    step      내놓는 노드의 tool.outputs  -> 그 단계의 outputs      point.lon -> location.0
    source    semantic 노드의 source.fields -> context_needs 의 선언  minLon -> 0.0

**선언이 없는 칸을 이름으로 짐작하지 않는다.** 그 자리는 실행 수단이 없는 것으로
센다(binding_at). 앞 단계가 없는 자리를 가리키거나 발화 인자가 아닌 값에 조건을
걸면 compile 이 터진다. 조용히 칸을 빼지 않는다.
"""

import copy
import datetime
import re

import paths
from execution import plan_service
from execution.plan_service import (
    CENTER_KEYS,
    CONTEXT_SOURCE,
    POINT_RADIUS_TO_BBOX,
    RUNTIME_NOW,
    SPOKEN_ARGUMENT,
    SPOKEN_SOURCE,
    TRANSFORM,
    TRANSFORM_ADAPTERS,
)
from ontology import graph

# 밖(계기판 · 시험)이 이 모듈 이름으로 읽는 것. 원천은 plan_service 다.
__all__ = ["CENTER_KEYS", "POINT_RADIUS_TO_BBOX"]

# ── 이름 ──────────────────────────────────────────────────────────

# tool.id 의 예약 namespace. 나머지는 Gateway 서버 id 다.
BUILTIN_NAMESPACE = "builtin"
FRONTEND_NAMESPACE = "frontend"

# 실행 수단 셋.
MCP = "mcp"
BUILTIN = "builtin"
COMMAND = "command"

# builtin 계산 -> 그 transform 이 도구 input 에 만드는 칸.
#
# 온톨로지에는 논리 식별(builtin/geo.pointRadiusToBbox)만 적는다. 그 계산은 지금
# vendor 의 _point_radius_to_bbox_input 이 갖고 있어서(plan_service.TRANSFORM_ADAPTERS),
# builtin 노드는 따로 부르지 않고 바로 뒤 도구 단계의 transform 으로 얹힌다.
#
# **만드는 칸이 정해져 있다.** 어댑터는 중심 · 반경 칸을 지우고 minLon · minLat ·
# maxLon · maxLat 넷을 평평하게 만든다. 뒤 도구가 지도 범위를 bbox 배열 한 칸으로
# 받으면(행정구역 조회 · 인구 통계 조회 …) 그 넷은 모르는 칸이라 버려지고 도구는
# 범위 없이 돈다. 그래서 뒤 노드가 이 넷을 그 이름 그대로 받을 때만 잇는다
# (_fits_adapter).
BUILTIN_ADAPTERS = {
    "builtin/geo.pointRadiusToBbox": ("minLon", "minLat", "maxLon", "maxLat"),
}

# 값의 출처 셋.
SOURCE = "source"
STEP = "step"
ADAPTER = "adapter"

# parameters 의 dict 꼴 둘 · tool · outputs 한 줄 · source 가 가질 수 있는 칸. 오타가
# 조용히 넘어가면 기본값 · 조건 · 읽는 법이 소리 없이 사라진다.
_EXTERNAL_FIELDS = ("from", "default", "map")
_CONDITIONAL_FIELDS = ("value", "if_endswith", "unless_endswith")
_TOOL_FIELDS = ("id", "parameters", "outputs")
_OUTPUT_FIELDS = ("list", "pick", "value", "fields")
_SOURCE_FIELDS = ("from", "description", "fields")

# outputs 의 pick -> 목록에서 고르는 칸 번호. 여기 없는 pick 은 터진다.
PICKS = {"first": "0"}

# outputs · source.fields 의 경로를 이루는 마디. vendor 의 참조 패턴이 한 마디로 받는
# 글자와 같다 — 이 밖의 글자가 섞이면 vendor 가 참조가 아니라 글 틀로 읽어 값이
# 문자열로 바뀐다.
_SEGMENT = r"[0-9A-Za-z_-]+"
_RAW_PATH = re.compile(rf"{_SEGMENT}(?:\.{_SEGMENT})*")
_FIELD_NAME = re.compile(_SEGMENT)

# _symbolic 이 "이 칸은 이 자리에서 안 적는다" 를 알리는 표시.
_OMIT = object()


# ── 온톨로지의 tool 과 source 를 읽는다 ──────────────────────────────


def binding_of(node_id: str) -> dict | None:
    """온톨로지 노드의 tool 을 실행에 쓸 모양으로.

    출력  {kind, id, parameters} 에 kind 마다 칸이 더 붙음
            mcp      server_id · tool · outputs (안 적었으면 빈 dict)
            builtin  adapter · produces (그 어댑터가 만드는 칸)
            command  command
          tool 이 없는 노드는 None
    규칙  id 의 첫 "/" 앞이 namespace 임. builtin · frontend 는 예약이고 나머지는
          Gateway 서버 id 임. 뒤는 도구 이름이라 점이 들어 있어도 됨
          builtin 은 BUILTIN_ADAPTERS 에 있는 것만 받음
          parameters 는 읽을 때 한 번 다 봄(_check_expression)
          outputs 도 읽을 때 한 번 다 봄(_check_output). raw 응답을 읽는 법이라
          mcp 도구에만 둠
    제약  모르는 꼴을 조용히 넘기지 않는다.
          오타 난 칸 · 없는 타입 참조가 문자열 그대로 도구에 실려 나가고, 0건이
          오지 오류가 오지 않는다
    """
    tool = graph.tool_of(node_id)
    if tool is None:
        return None

    where = f"{paths.ONTOLOGY_PATH.name}: {node_id}.tool"
    unknown = [key for key in tool if key not in _TOOL_FIELDS]
    if unknown:
        raise ValueError(f"{where} 에 모르는 칸 {unknown}")

    tool_id = tool.get("id")
    namespace, _, name = str(tool_id or "").partition("/")
    if not isinstance(tool_id, str) or not namespace or not name:
        raise ValueError(f"{where}.id 가 '<namespace>/<이름>' 이 아니다: {tool_id!r}")

    parameters = tool.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise ValueError(f"{where}.parameters 가 dict 가 아니다")
    inputs = graph.inputs_of(node_id)
    known = set(graph.node_ids())
    for field, expression in parameters.items():
        _check_expression(f"{where}.parameters.{field}", expression, inputs, known)

    outputs = tool.get("outputs")
    if outputs is not None:
        if namespace in (BUILTIN_NAMESPACE, FRONTEND_NAMESPACE):
            raise ValueError(f"{where}.outputs 는 MCP 도구에만 둔다. {namespace} 는 읽을 응답이 없다")
        if not isinstance(outputs, dict):
            raise ValueError(f"{where}.outputs 가 dict 가 아니다")
        produced = graph.outputs_of(node_id)
        for type_id, reading in outputs.items():
            _check_output(f"{where}.outputs.{type_id}", type_id, reading, produced)

    if namespace == BUILTIN_NAMESPACE:
        if tool_id not in BUILTIN_ADAPTERS or tool_id not in TRANSFORM_ADAPTERS:
            raise ValueError(f"{where}.id 는 모르는 builtin 이다: {tool_id}")
        return {
            "kind": BUILTIN,
            "id": tool_id,
            "adapter": TRANSFORM_ADAPTERS[tool_id],
            "produces": BUILTIN_ADAPTERS[tool_id],
            "parameters": parameters,
        }
    if namespace == FRONTEND_NAMESPACE:
        return {"kind": COMMAND, "id": tool_id, "command": name, "parameters": parameters}
    return {
        "kind": MCP,
        "id": tool_id,
        "server_id": namespace,
        "tool": name,
        "parameters": parameters,
        "outputs": outputs or {},
    }


def _check_expression(where: str, expression, inputs: list[str], known: set, in_list: bool = False) -> None:
    """parameters 의 값 하나가 아는 꼴인지.

    규칙  문자열   runtime.now.<이름> · semantic 참조 · 그 밖은 상수
                   뿌리가 온톨로지 노드 id 이면 semantic 참조로 봄. 그 노드의
                   hasInput 이어야 함
          목록     안의 것은 문자열 · 수만. 목록 · dict 를 겹치지 않음
          dict     from 이 있으면 밖에서 온 값. spoken.<이름> 은 default 가
                   있어야 하고 map 이 있으면 default 가 그 key 여야 함.
                   context.<경로> 는 from 하나만
                   value 가 있으면 조건. if_endswith · unless_endswith 중 하나와
                   semantic 참조 하나
          수 · 참거짓  그대로
    제약  발화 인자를 from 으로 가리키지 않는다.
          spoken.argument 는 semantic 노드의 source 가 말함. 두 길을 열면 같은 값이
          어디서 왔는지 안 갈림
    """
    if isinstance(expression, bool) or isinstance(expression, (int, float)):
        return

    if isinstance(expression, str):
        if expression.startswith(RUNTIME_NOW.split(".")[0] + "."):
            try:
                plan_service.now_field(expression, None)
            except ValueError as error:
                raise ValueError(f"{where}: {error}") from None
            return
        root = expression.split(".", 1)[0]
        if root in known and root not in inputs:
            raise ValueError(f"{where}: {root} 는 이 노드의 hasInput 이 아니다")
        return

    if isinstance(expression, list):
        if in_list:
            raise ValueError(f"{where}: 목록 안에 목록을 두지 않는다")
        for item in expression:
            if isinstance(item, dict):
                raise ValueError(f"{where}: 목록 안에 dict 를 두지 않는다")
            _check_expression(where, item, inputs, known, in_list=True)
        return

    if isinstance(expression, dict) and not in_list:
        if "from" in expression:
            unknown = [key for key in expression if key not in _EXTERNAL_FIELDS]
            if unknown:
                raise ValueError(f"{where}: 모르는 칸 {unknown}")
            source = expression["from"]
            if not isinstance(source, str):
                raise ValueError(f"{where}.from 이 문자열이 아니다")
            if source.startswith(CONTEXT_SOURCE):
                if set(expression) != {"from"}:
                    raise ValueError(f"{where}: 화면 값에는 default · map 을 두지 않는다")
                return
            if not source.startswith(SPOKEN_SOURCE) or source == SPOKEN_ARGUMENT:
                raise ValueError(f"{where}.from 은 spoken.<이름> 이나 context.<경로> 여야 한다: {source}")
            if "default" not in expression:
                raise ValueError(f"{where}: {source} 에 default 가 없다")
            mapping = expression.get("map")
            if mapping is not None and (
                not isinstance(mapping, dict) or expression["default"] not in mapping
            ):
                raise ValueError(f"{where}: default 가 map 의 key 가 아니다")
            return
        if "value" in expression:
            unknown = [key for key in expression if key not in _CONDITIONAL_FIELDS]
            conditions = [key for key in ("if_endswith", "unless_endswith") if key in expression]
            if unknown or len(conditions) != 1 or not isinstance(expression[conditions[0]], str):
                raise ValueError(f"{where}: 조건은 value 와 if_endswith · unless_endswith 중 하나다")
            value = expression["value"]
            if not isinstance(value, str) or value.split(".", 1)[0] not in inputs:
                raise ValueError(f"{where}.value 는 이 노드의 hasInput 참조여야 한다")
            return

    raise ValueError(f"{where}: 모르는 꼴 {expression!r}")


def _check_output(where: str, type_id: str, reading, produced: list[str]) -> None:
    """outputs 의 한 줄이 아는 꼴인지.

    입력  어디인지 · 그 줄의 key(semantic 타입) · 그 줄 · 이 노드의 hasOutput 타입
    규칙  key 는 이 노드의 hasOutput 타입이어야 함
          value 와 fields 중 하나만. value 는 값 하나의 경로, fields 는 semantic 칸 -> 경로
          list 와 pick 은 함께. list 는 목록의 경로이고 pick 은 PICKS 에 있는 것만
          경로는 전부 _check_path 를 통과해야 함
    제약  아무도 안 받는 hasOutput 타입까지 적으라고 하지 않는다.
          여기는 적힌 줄의 꼴만 봄. 받는 노드가 읽는 칸이 적혀 있는지는
          check_bindings 가 봄
    """
    if type_id not in produced:
        raise ValueError(f"{where}: {type_id} 는 이 노드의 hasOutput 이 아니다")
    if not isinstance(reading, dict):
        raise ValueError(f"{where} 가 dict 가 아니다")
    unknown = [key for key in reading if key not in _OUTPUT_FIELDS]
    if unknown:
        raise ValueError(f"{where} 에 모르는 칸 {unknown}")

    if ("value" in reading) == ("fields" in reading):
        raise ValueError(f"{where}: value 와 fields 중 하나만 둔다")
    if "value" in reading:
        _check_path(f"{where}.value", reading["value"])
    else:
        _check_fields(f"{where}.fields", reading["fields"])

    if ("list" in reading) != ("pick" in reading):
        raise ValueError(f"{where}: list 와 pick 은 함께 둔다")
    if "list" in reading:
        _check_path(f"{where}.list", reading["list"])
        if reading["pick"] not in PICKS:
            raise ValueError(f"{where}.pick 은 {sorted(PICKS)} 중 하나다: {reading['pick']!r}")


def _check_fields(where: str, fields) -> None:
    """semantic 칸 -> 경로 한 벌이 아는 꼴인지. outputs 의 fields 와 source.fields 가 같이 씀.

    규칙  비어 있지 않은 dict. 칸 이름은 한 마디 문자열이고 경로는 _check_path 를 통과함
    """
    if not isinstance(fields, dict) or not fields:
        raise ValueError(f"{where} 가 비었거나 dict 가 아니다")
    for name, path in fields.items():
        if not isinstance(name, str) or not _FIELD_NAME.fullmatch(name):
            raise ValueError(f"{where}: 칸 이름이 한 마디가 아니다: {name!r}")
        _check_path(f"{where}.{name}", path)


def _check_path(where: str, path) -> None:
    """raw 값 안의 경로인지.

    규칙  점으로 이은 마디. 마디는 dict 키 이름이거나 목록 번호임(location.0 · bbox.1.0 · items)
    제약  수를 경로로 받지 않는다.
          YAML 에서 따옴표 없이 적은 1.10 은 수 1.1 이 되어 경로가 조용히 바뀜
    """
    if not isinstance(path, str) or not _RAW_PATH.fullmatch(path):
        raise ValueError(f"{where} 가 응답 안의 경로가 아니다: {path!r}")


def _source_of(node_id: str) -> dict | None:
    """그 노드의 source 를 실행에 쓸 모양으로.

    출력  온톨로지의 source 그대로({from, description, fields?}). 없으면 None
    규칙  from 은 문자열이어야 함
          fields 는 semantic 칸 -> 화면 값 안의 경로(_check_fields). 화면 값에만 둠.
          발화 인자는 칸이 없는 값 하나임
    제약  모르는 칸을 조용히 넘기지 않는다.
          fields 오타는 칸 없는 값으로 읽혀 그 source 로 시작하는 자리가 소리 없이
          unwired 가 됨
    """
    source = graph.source_of(node_id)
    if source is None:
        return None

    where = f"{paths.ONTOLOGY_PATH.name}: {node_id}.source"
    unknown = [key for key in source if key not in _SOURCE_FIELDS]
    if unknown:
        raise ValueError(f"{where} 에 모르는 칸 {unknown}")
    origin = source.get("from")
    if not isinstance(origin, str):
        raise ValueError(f"{where}.from 이 문자열이 아니다")
    if "fields" in source:
        if not origin.startswith(CONTEXT_SOURCE):
            raise ValueError(f"{where}.fields 는 화면 값에만 둔다. {origin} 은 칸이 없는 값 하나다")
        _check_fields(f"{where}.fields", source["fields"])
    return source


def _referenced_types(parameters: dict, inputs: list[str]) -> list[str]:
    """parameters 가 가리키는 hasInput 타입. 처음 나온 차례."""
    found = []

    def visit(expression):
        if isinstance(expression, str):
            root = expression.split(".", 1)[0]
            if root in inputs and root not in found:
                found.append(root)
        elif isinstance(expression, list):
            for item in expression:
                visit(item)
        elif isinstance(expression, dict) and "value" in expression:
            visit(expression["value"])

    for expression in parameters.values():
        visit(expression)
    return found


def _read_fields(parameters: dict, type_id: str) -> set[str]:
    """parameters 가 그 타입에서 읽는 칸.

    출력  칸 이름 집합. 타입을 통째로 가리키면(place_name) 빈 문자열이 들어감
    규칙  목록 안과 조건의 value 까지 봄
    """
    found = set()

    def visit(expression):
        if isinstance(expression, str):
            root, _, field = expression.partition(".")
            if root == type_id:
                found.add(field)
        elif isinstance(expression, list):
            for item in expression:
                visit(item)
        elif isinstance(expression, dict) and "value" in expression:
            visit(expression["value"])

    for expression in parameters.values():
        visit(expression)
    return found


def _provides(reading: dict | None, fields: set[str]) -> bool:
    """읽는 법 하나가 그 칸을 다 주는가.

    입력  outputs 의 한 줄 또는 source · 받는 노드가 읽는 칸(_read_fields)
    출력  참이면 그 칸을 전부 경로로 적을 수 있음
    규칙  fields 가 없으면 값 하나임. 타입을 통째로 가리킬 때만 줌
          fields 가 있으면 칸이 있는 값임. 적힌 칸만 주고 통째로는 안 줌
          읽는 법이 없으면(None) 아무것도 안 줌
    제약  semantic 칸 이름을 raw 경로로 짐작하지 않는다.
          point.lon 을 $s1.lon 으로 적으면 vendor 의 이름 특례가 풀어 줄 때만 맞음
    """
    if reading is None:
        return False
    declared = reading.get("fields")
    if declared is None:
        return fields == {""}
    return "" not in fields and fields <= set(declared)


def _path_of(where: str, reading: dict | None, field: str) -> str | None:
    """읽는 법 하나에서 그 칸의 경로.

    입력  어디의 읽는 법인지 · outputs 의 한 줄 또는 source · 칸 이름(통째면 빈 문자열)
    출력  점 경로. 칸이 없는 source 를 통째로 가리키면 None
    규칙  fields 가 있으면 그 칸의 경로, 없으면 value 의 경로
          list 가 있으면 "<list>.<PICKS[pick]>." 을 앞에 붙임
    제약  못 주는 칸을 짐작하지 않는다. _provides 가 거짓인 자리는 터진다
    """
    if not _provides(reading, {field}):
        raise ValueError(f"{where} 가 {field or '통째 값'} 을 안 준다")
    declared = reading.get("fields")
    path = declared[field] if declared is not None else reading.get("value")
    if "list" in reading:
        path = f"{reading['list']}.{PICKS[reading['pick']]}.{path}"
    return path


def bound_inputs(node_id: str) -> list[str]:
    """tool.parameters 가 실제로 가리키는 hasInput 타입.

    출력  타입 id 목록. tool 이 없으면 빈 목록
    규칙  hasInput 인데 여기 없는 타입은 그 자리에서 부를 수 없음.
          dev/tools/check_wiring.py 가 그것을 C 로 셈
    """
    binding = binding_of(node_id)
    if binding is None:
        return []
    return _referenced_types(binding["parameters"], graph.inputs_of(node_id))


def _fits_adapter(parameters: dict, type_id: str, produces: tuple) -> bool:
    """앞 builtin 어댑터가 만드는 칸을 이 노드가 그 이름 그대로 받는가.

    출력  참이면 이을 수 있음
    규칙  type_id 를 가리키는 칸이 전부 "<타입>.<칸>" 한 줄이고 그 칸이 produces 에
          있어야 함. 칸 이름도 같아야 함(minLon 칸에 map_extent.minLon)
          목록 칸(bbox 배열) · 조건 칸으로 가리키면 거짓. 어댑터가 그 모양을 안 만듦
    """
    for field, expression in parameters.items():
        items = expression if isinstance(expression, list) else [expression]
        for item in items:
            value = item.get("value") if isinstance(item, dict) else item
            if not isinstance(value, str) or value.split(".", 1)[0] != type_id:
                continue
            _, _, name = value.partition(".")
            if isinstance(expression, list) or isinstance(item, dict) or name != field or name not in produces:
                return False
    return True


def _readable(parameters: dict, source_id: str, type_id: str) -> bool:
    """앞 노드가 건네는 그 타입을 이 노드의 parameters 가 읽을 수 있는가.

    입력  받는 노드의 parameters · 앞 노드 id · 건네는 타입
    출력  참이면 이을 수 있음
    규칙  앞 노드가 builtin      그 어댑터가 만드는 칸을 그 이름 그대로 받아야 함(_fits_adapter)
          앞 노드가 도구 · 명령  그 tool.outputs 가 읽는 칸을 다 줘야 함. 명령은 outputs 가 없음
          앞 노드에 source 가 있음  그 source 가 읽는 칸을 다 줘야 함
          tool 도 source 도 없는 노드  참. 그 자리에서 가리킬 step 이 없어 compile 이
          터짐. 그 노드 자신이 unwired 로 세어짐
    """
    source = binding_of(source_id)
    if source is not None and source["kind"] == BUILTIN:
        return _fits_adapter(parameters, type_id, source["produces"])
    fields = _read_fields(parameters, type_id)
    if source is not None:
        return _provides(source.get("outputs", {}).get(type_id), fields)
    start = _source_of(source_id)
    if start is not None:
        return _provides(start, fields)
    return True


def binding_at(node_id: str, source_id: str) -> tuple[dict, str] | None:
    """앞 노드가 건네는 것 중 이 노드의 tool 이 받는 타입을 고름.

    입력  부를 노드 id · 그 앞에 선 노드 id
    출력  (binding_of 의 결과, 이 자리에서 받는 타입). 못 받으면 None
    규칙  앞 노드가 건네는 타입을 hasOutput 차례대로 보고 parameters 가 가리키는
          첫 타입을 씀. 장소 좌표 변환은 지점 좌표를 먼저 내놓음
          tool 이 없는 노드는 None. 그 자리는 unwired 로 셈해짐
          그 타입에서 읽는 칸을 앞 노드가 못 주면 None(_readable). builtin 이 만드는
          칸 · 도구의 outputs · 시작 노드의 source 가 그 판정임
    제약  타입 판정을 여기서 다시 적지 않는다. ontology.graph 가 함
    """
    binding = binding_of(node_id)
    if binding is None:
        return None
    referenced = _referenced_types(binding["parameters"], graph.inputs_of(node_id))
    for type_id in graph.handed_types(source_id):
        if type_id in referenced:
            if not _readable(binding["parameters"], source_id, type_id):
                return None
            return binding, type_id
    return None


def context_sources() -> dict[str, tuple[str, ...]]:
    """화면 문맥에서 곧장 들어오는 시작 노드와 그 값의 자리.

    출력  {노드 id: context 안의 칸 경로}. 온톨로지에 적힌 차례
          지점 좌표 -> ("selectedLocation",) · 지도 범위 -> ("view", "bbox")
    규칙  source.from 이 context. 으로 시작하는 노드만 담음
    제약  노드 id 를 코드에 적지 않는다.
          어느 노드가 화면에서 오는지는 온톨로지의 source 가 말함
    """
    found = {}
    for node_id in graph.start_ids():
        origin = (graph.source_of(node_id) or {}).get("from")
        if isinstance(origin, str) and origin.startswith(CONTEXT_SOURCE):
            found[node_id] = tuple(origin[len(CONTEXT_SOURCE):].split("."))
    return found


# ★ **발화에서 인자를 뽑는 자리는 여기 없다.** 발화 해석 LLM 이 argument 와 이름
#   있는 값을 함께 내놓는 것 하나뿐이다. 같은 일을 정규식으로 되살리지 않는다.


# ── 한 자리의 input 을 기호로 적는다 ───────────────────────────────


def _new_state() -> dict:
    """compile 하나가 모으는 것. 도구 단계 · 단계마다 읽힌 칸 · 화면 값마다 읽힌 칸."""
    return {"steps": {}, "reads": {}, "context": {}}


def _joined(*parts: str) -> str:
    """빈 마디를 뺀 점 경로."""
    return ".".join(part for part in parts if part)


def _reference(node_id: str, type_id: str, field: str, origin, state: dict) -> dict:
    """이 자리에서 받은 semantic 값을 가리키는 기호.

    입력  받는 노드 · 참조의 뿌리 타입(point) · 뿌리 뒤 칸 이름(lon. 없으면 빈 문자열) ·
          값의 출처 · compile 상태
    출력  {from: spoken.argument} · {from: context.<시작 노드>.<칸>} ·
          {from: s<N>.<타입>.<칸>} · {from: transform.<타입>.<칸>}
    규칙  출처는 (source, 시작 노드) · (step, step id, 내놓은 노드) · (adapter, …) 임
          source 와 step 은 내놓는 쪽이 그 칸을 주는지 봄(_path_of). 준다면 그 칸을
          state 에 남겨 게시할 선언에 옮김
    제약  가리킬 단계가 없는 자리에서 칸을 조용히 빼지 않는다. 터진다
          읽는 법이 안 적힌 칸을 이름으로 짐작하지 않는다
    """
    kind = origin[0] if origin else None

    if kind == SOURCE:
        start = origin[1]
        source = _source_of(start)
        if source["from"] == SPOKEN_ARGUMENT:
            if field:
                raise ValueError(f"{node_id}: 발화 인자에는 칸이 없다 ({type_id}.{field})")
            return {"from": SPOKEN_ARGUMENT}
        if source["from"].startswith(CONTEXT_SOURCE):
            _path_of(f"{node_id}: {start}.source", source, field)
            state["context"].setdefault(start, set()).add(field)
            return {"from": _joined("context", start, field)}
        raise ValueError(f"{node_id}: 모르는 source {source['from']!r}")

    if kind == STEP:
        step_id, producer = origin[1], origin[2]
        if step_id is None:
            after = f" ({producer} 뒤)" if producer else ""
            raise ValueError(f"{node_id}: {type_id} 를 내놓은 도구 단계가 없다{after}")
        reading = ((binding_of(producer) or {}).get("outputs") or {}).get(type_id)
        _path_of(f"{node_id}: {producer}.tool.outputs.{type_id}", reading, field)
        state["reads"].setdefault(step_id, {}).setdefault(type_id, set()).add(field)
        return {"from": _joined(step_id, type_id, field)}

    if kind == ADAPTER:
        return {"from": _joined(TRANSFORM, type_id, field)}

    raise ValueError(f"{node_id}: {type_id} 의 출처가 없다")


def _screen_reference(node_id: str, source: str, state: dict) -> dict:
    """parameters 가 {from: context.<경로>} 로 곧장 가리킨 화면 값을 시작 노드의 기호로.

    출력  {from: context.<시작 노드>.<칸>}. 통째면 칸 없이
    규칙  경로가 context_sources 의 자리로 시작해야 함. 그 뒤 경로는 그 시작 노드
          source.fields 의 한 칸 경로와 똑같아야 함
          경로 탐색의 출발지(context.selectedLocation.lat)가 그 자리임. 지점 좌표의
          lat 칸이라 context.point.lat 이 됨
    제약  어느 칸인지 하나로 안 정해지면 터진다. 비슷한 이름으로 고르지 않는다
    """
    path = tuple(source[len(CONTEXT_SOURCE):].split("."))
    for start, base in context_sources().items():
        if path[:len(base)] != base:
            continue
        rest = ".".join(path[len(base):])
        declared = _source_of(start)
        field = ""
        if rest:
            names = [name for name, raw in (declared.get("fields") or {}).items() if raw == rest]
            if len(names) != 1:
                raise ValueError(f"{node_id}: {source} 가 {start}.source.fields 의 어느 칸인지 하나로 안 정해진다")
            field = names[0]
        _path_of(f"{node_id}: {start}.source", declared, field)
        state["context"].setdefault(start, set()).add(field)
        return {"from": _joined("context", start, field)}
    raise ValueError(f"{node_id}: {source} 는 화면 값 source 가 선언한 자리가 아니다")


def _symbolic(expression, node_id: str, type_id: str, origin, state: dict):
    """parameters 의 값 하나를 이 자리의 기호로.

    출력  plan_service 가 읽는 꼴의 기호. 이 자리에서 안 보내는 칸이면 _OMIT
    규칙  runtime.now.<이름>   {from: runtime.now.<이름>}
          semantic 참조        이 자리에서 받는 타입이면 _reference. 다른 타입이면 _OMIT
          그 밖의 문자열 · 수  {value: …}
          목록                 안에 _OMIT 이 하나라도 있으면 칸 전체를 뺌.
                               전부 상수면 {value: [...]} 하나로 적음
          from spoken.<이름>   그대로(default · map 까지)
          from context.<경로>  _screen_reference
          조건                 안의 기호가 발화 인자여야 함. {from: spoken.argument, <조건>}
    제약  앞 단계 결과에 조건을 걸지 않는다.
          그 값은 vendor 가 나중에 풀어서 부르기 전에 어미를 볼 수 없음
    """
    if isinstance(expression, bool) or isinstance(expression, (int, float)):
        return {"value": expression}

    if isinstance(expression, str):
        if expression.startswith(RUNTIME_NOW + "."):
            plan_service.now_field(expression, None)
            return {"from": expression}
        root, _, field = expression.partition(".")
        if root not in graph.inputs_of(node_id):
            return {"value": expression}
        if root != type_id:
            return _OMIT
        return _reference(node_id, root, field, origin, state)

    if isinstance(expression, list):
        values = [_symbolic(item, node_id, type_id, origin, state) for item in expression]
        if any(value is _OMIT for value in values):
            return _OMIT
        if all(set(value) == {"value"} for value in values):
            return {"value": [value["value"] for value in values]}
        return values

    if isinstance(expression, dict) and "from" in expression:
        if expression["from"].startswith(CONTEXT_SOURCE):
            return _screen_reference(node_id, expression["from"], state)
        return copy.deepcopy(expression)

    if isinstance(expression, dict) and "value" in expression:
        inner = _symbolic(expression["value"], node_id, type_id, origin, state)
        if inner is _OMIT:
            return _OMIT
        if inner != {"from": SPOKEN_ARGUMENT}:
            raise ValueError(f"{node_id}: 값을 보고 칸을 고르려면 발화 인자여야 한다")
        condition = "if_endswith" if "if_endswith" in expression else "unless_endswith"
        return {"from": SPOKEN_ARGUMENT, condition: expression[condition]}

    raise ValueError(f"{node_id}: 모르는 꼴 {expression!r}")


def _symbolic_input(binding: dict, node_id: str, type_id: str, origin, state: dict) -> dict:
    """한 자리의 input 기호 한 벌. parameters 차례대로, _OMIT 인 칸은 뺌."""
    filled = {}
    for field, expression in binding["parameters"].items():
        value = _symbolic(expression, node_id, type_id, origin, state)
        if value is not _OMIT:
            filled[field] = value
    return filled


def _reading_of(where: str, reading: dict, fields: set[str]) -> dict:
    """내놓는 쪽 읽는 법에서 실제로 읽힌 칸만 경로로 편 한 줄.

    출력  {value: 경로} 또는 {fields: {칸: 경로}}. list · pick 은 경로 안에 펴 넣음
    규칙  칸 차례는 내놓는 쪽 선언의 차례
    """
    if "" in fields:
        return {"value": _path_of(where, reading, "")}
    return {"fields": {name: _path_of(where, reading, name) for name in reading["fields"] if name in fields}}


def _finish(workflow: list[dict], state: dict) -> dict:
    """모은 것으로 게시할 블록을 닫음. 단계마다 outputs, 화면 값 선언, 발화 인자 사용."""
    for step_id, reads in state["reads"].items():
        entry = state["steps"][step_id]
        declared = binding_of(entry["node"])["outputs"]
        entry["outputs"] = {
            type_id: _reading_of(f"{entry['node']}.tool.outputs.{type_id}", declared[type_id], reads[type_id])
            for type_id in declared
            if type_id in reads
        }

    needs = {}
    for start in context_sources():
        if start not in state["context"]:
            continue
        source = _source_of(start)
        declaration = {"from": source["from"]}
        read = state["context"][start]
        if "" not in read:
            declaration["fields"] = {name: path for name, path in source["fields"].items() if name in read}
        needs[start] = declaration

    return copy.deepcopy({
        "spoken_needed": plan_service.mentions_argument(workflow),
        "context_needs": needs,
        "workflow": workflow,
    })


# ── 게시할 execution 블록 ──────────────────────────────────────────


def compile_execution(chain: list[str]) -> dict:
    """노드 사슬 하나를 게시할 execution 블록으로.

    입력  사람이 받아들인 recipe 의 노드 id 목록
    출력  plan_service 가 읽는 execution dict. 같은 온톨로지 · 같은 사슬이면 늘 같은 것
    규칙  실행 수단이 없는 노드가 있으면(unwired_in) 그 목록만 적고 workflow 는 비움.
          부르는 쪽이 하나도 안 부르고 그렇다고 답함
          step id 는 s1 · s2 … 로 붙음
          첫 노드는 시작 데이터라 부를 것이 없음. 둘째 노드의 값은 그 source 에서 옴
          앞 단계 참조는 step id 와 그 step 을 만든 노드를 함께 들고 감. 같은 타입을
          화면과 앞 단계가 둘 다 줄 수 있어(경로 탐색의 출발 · 도착) 타입만으로는
          어느 쪽 값인지 안 갈림
          frontend 노드는 명령 항목이 됨. 그 뒤 노드가 가리킬 단계가 없음
          builtin 노드는 단계를 안 만듦. 그 입력이 바로 뒤 항목의 transform 이 됨
          tool 이 없는 데이터 노드는 건너뜀. 그 뒤에서도 가리킬 단계가 없음
          spoken_needed 는 workflow 가 발화 인자를 가리키는지. 지도 명령과 transform 까지 봄
          context_needs 는 기호가 실제로 읽는 화면 값뿐임. 지점 좌표는 화면에서도 오고
          장소 좌표 변환에서도 오므로 쓰이지도 않을 source 를 세지 않음
    제약  건너뛴 노드 · 명령 노드 뒤에서 그보다 앞 단계를 대신 가리키지 않는다.
          그 앞 단계는 뒤 노드가 받는 타입을 낸 노드가 아님
          온톨로지에 없는 노드를 tool 이 없는 노드처럼 건너뛰지 않는다. 터진다
          recipe id · 도구 id 로 가르지 않는다
          시각 · 파일 순서 · 난수에 기대지 않는다
    """
    known = set(graph.node_ids())
    strangers = [node_id for node_id in chain if node_id not in known]
    if strangers:
        raise ValueError(f"온톨로지에 없는 노드 {strangers}")

    missing = unwired_in(chain)
    if missing:
        return {"spoken_needed": False, "unwired": missing, "context_needs": {}, "workflow": []}

    state = _new_state()
    workflow: list[dict] = []
    origin = (SOURCE, chain[0]) if chain and _source_of(chain[0]) else (STEP, None, None)

    for source_id, node_id in zip(chain, chain[1:]):
        found = binding_at(node_id, source_id)
        if found is None:
            origin = (STEP, None, node_id)
            continue

        binding, type_id = found
        if binding["kind"] == BUILTIN and origin[0] == ADAPTER:
            raise ValueError(f"{node_id}: builtin 뒤에 builtin 을 잇지 않는다")
        symbolic = _symbolic_input(binding, node_id, type_id, origin, state)

        if binding["kind"] == BUILTIN:
            origin = (ADAPTER, {"id": binding["id"], "node": node_id, "input": symbolic})
            continue

        if binding["kind"] == COMMAND:
            entry = {"node": node_id, "command": binding["command"]}
        else:
            step_id = f"s{len(state['steps']) + 1}"
            entry = {"id": step_id, "node": node_id, "server_id": binding["server_id"], "tool": binding["tool"]}
        if origin[0] == ADAPTER:
            entry["transform"] = origin[1]
        entry["input"] = symbolic
        workflow.append(entry)

        if binding["kind"] == COMMAND:
            origin = (STEP, None, node_id)
        else:
            state["steps"][step_id] = entry
            origin = (STEP, step_id, node_id)

    return _finish(workflow, state)


# ── 이 사슬에 실행 수단이 다 붙었는가 ───────────────────────────────


def unwired(recipe_id: str) -> list[str]:
    """아직 실행 수단이 안 붙은 노드. recipe 파일의 사슬로.

    출력  이 자리에서 받는 타입에 맞는 tool 이 없는 실행 노드 id 목록. 경로 순서.
          전부 있으면 빈 목록
    규칙  경로를 recipe 파일에서 읽어 unwired_in 에 넘김. 게시 · 계기판이 씀
          요청 중의 판정은 게시된 execution 의 unwired 를 봄
    """
    return unwired_in(graph.recipe_nodes(recipe_id))


def unwired_in(chain: list[str]) -> list[str]:
    """노드 사슬 하나에서 실행 수단이 안 붙은 노드.

    입력  노드 id 목록. recipe 파일로 아직 안 쓴 후보도 받음
    출력  unwired 와 같은 모양
    규칙  실행 노드만 셈. 시작 데이터 노드는 부를 것이 없어 세지 않음
          tool 이 있어도 이 자리에서 건네받는 타입을 parameters 가 안 가리키면 셈
          앞 builtin 이 만드는 칸을 못 받는 자리도 셈
          앞 노드가 이 노드가 읽는 칸의 경로를 적지 않은 자리도 셈(binding_at)
    """
    return [
        node_id
        for source_id, node_id in zip(chain, chain[1:])
        if graph.is_executable(node_id) and binding_at(node_id, source_id) is None
    ]


# ── 계기판 · 시험이 도구 스키마와 맞대는 input 벌 ─────────────────

# variants 가 발화 인자 자리에 심는 값. 사람이 말할 수 없는 글자로 짓는다 —
# 발화에서 올 수 있는 값과 겹치면 「인자를 안 썼다」를 「썼다」로 잘못 세게 된다.
_SPOKEN_PROBE = "\x00spoken-probe\x00"


def _holds_probe(value) -> bool:
    """input 조각 어딘가에 발화 인자가 들어갔는가. 중첩된 dict · list 까지."""
    if isinstance(value, dict):
        return any(_holds_probe(item) for item in value.values())
    if isinstance(value, list):
        return any(_holds_probe(item) for item in value)
    return isinstance(value, str) and value.startswith(_SPOKEN_PROBE)


def variants(node_id: str) -> list[dict]:
    """그 노드가 보낼 수 있는 input 벌 전부.

    출력  [{node, type, origin, suffix, input, adapter, spoken}, ...]
          origin 은 source · step · adapter 중 그 타입이 실제로 올 수 있는 것
          suffix 는 조건 칸의 어미 갈래. 기본 벌은 빈 문자열
          spoken 은 발화 인자가 들어갔는지
    규칙  출처마다 compile 과 같은 함수로 그 자리의 기호를 적고, 요청 중에 쓰는
          plan_service.bind_input 으로 채움. 계기판이 규칙을 따로 옮겨 적으면
          실행과 표가 조용히 어긋남
          출처는 _origins 가 정함. 이 노드가 그 타입에서 읽는 칸을 줄 수 있는 출처만 담음
          조건 칸이 있으면 그 어미로 끝나는 인자로 한 벌을 더 만듦. 같은 벌은 안 담음
          이름 있는 값은 전부 default 로 채움. 부르는 순간은 고정된 한 시각임
    """
    binding = binding_of(node_id)
    if binding is None:
        return []

    now = datetime.datetime(2026, 1, 1, 9, 0, tzinfo=plan_service.RUNTIME_ZONE)
    inputs = graph.inputs_of(node_id)
    arguments = [("", _SPOKEN_PROBE)] + [
        (suffix, _SPOKEN_PROBE + suffix) for suffix in _suffixes(binding["parameters"])
    ]

    rows = []
    for type_id in _referenced_types(binding["parameters"], inputs):
        for origin_name, execution, entry in _origins(node_id, binding, type_id):
            seen = []
            for suffix, argument in arguments:
                filled, adapter = plan_service.bind_input(entry, execution, argument, None, now)
                if (filled, adapter) in seen:
                    continue
                seen.append((filled, adapter))
                rows.append({
                    "node": node_id,
                    "type": type_id,
                    "origin": origin_name,
                    "suffix": suffix,
                    "input": filled,
                    "adapter": adapter,
                    "spoken": _holds_probe(filled),
                })
    return rows


def _suffixes(parameters: dict) -> list[str]:
    """조건 칸이 보는 어미. 처음 나온 차례."""
    found = []
    for expression in parameters.values():
        if isinstance(expression, dict):
            for key in ("if_endswith", "unless_endswith"):
                if key in expression and expression[key] not in found:
                    found.append(expression[key])
    return found


def _step_producer(type_id: str, fields: set[str]) -> str | None:
    """그 타입의 그 칸을 tool.outputs 로 주는 첫 도구 노드. 없으면 None. 온톨로지에 적힌 차례."""
    for node_id in graph.node_ids():
        if type_id not in graph.outputs_of(node_id):
            continue
        binding = binding_of(node_id)
        if binding is not None and binding["kind"] == MCP and _provides(binding["outputs"].get(type_id), fields):
            return node_id
    return None


def _variant(node_id: str, consumer: dict, type_id: str, producer: str | None = None, builtin: tuple | None = None):
    """출처 하나를 둔 한 자리 execution. (execution, 그 노드의 항목).

    규칙  producer 가 있으면 그것을 s1 로 두고 그 뒤에 섬
          builtin 이 (노드, binding, 받는 타입) 이면 그 입력을 s1 뒤 transform 으로 얹음
          둘 다 없으면 그 타입의 source 에서 곧장 받음
    """
    state = _new_state()
    workflow: list[dict] = []
    origin = (SOURCE, type_id)
    if producer is not None:
        entry = {"id": "s1", "node": producer, "input": {}}
        state["steps"]["s1"] = entry
        workflow.append(entry)
        origin = (STEP, "s1", producer)
    if builtin is not None:
        builtin_id, builtin_binding, inner_type = builtin
        transform_input = _symbolic_input(builtin_binding, builtin_id, inner_type, origin, state)
        origin = (ADAPTER, {"id": builtin_binding["id"], "node": builtin_id, "input": transform_input})

    entry = {"node": node_id}
    if origin[0] == ADAPTER:
        entry["transform"] = origin[1]
    entry["input"] = _symbolic_input(consumer, node_id, type_id, origin, state)
    workflow.append(entry)
    return _finish(workflow, state), entry


def _origins(node_id: str, consumer: dict, type_id: str) -> list[tuple[str, dict, dict]]:
    """그 타입의 값이 올 수 있는 출처. variants 가 벌을 가르는 데 씀.

    출력  [(출처 이름, execution, 그 노드의 항목), ...]
    규칙  source 는 그 타입의 source 가 받는 노드(consumer)가 읽는 칸을 줄 때만 담음
          step 은 그 칸을 outputs 로 주는 첫 도구 노드가 내놓은 것으로 봄
          builtin 출처는 consumer 가 그 어댑터의 칸을 받을 때만 담음. 그 builtin 의
          입력도 같은 규칙으로 앞 도구 단계에서 받은 모양임
    """
    fields = _read_fields(consumer["parameters"], type_id)
    found = []

    source = _source_of(type_id)
    if source is not None and _provides(source, fields):
        found.append((SOURCE, *_variant(node_id, consumer, type_id)))

    producer = _step_producer(type_id, fields)
    if producer is not None:
        found.append((STEP, *_variant(node_id, consumer, type_id, producer=producer)))

    for builtin_id in graph.node_ids():
        if type_id not in graph.outputs_of(builtin_id):
            continue
        binding = binding_of(builtin_id)
        if binding is None or binding["kind"] != BUILTIN:
            continue
        if not _fits_adapter(consumer["parameters"], type_id, binding["produces"]):
            continue
        inner = _referenced_types(binding["parameters"], graph.inputs_of(builtin_id))
        if not inner:
            continue
        inner_producer = _step_producer(inner[0], _read_fields(binding["parameters"], inner[0]))
        if inner_producer is None:
            continue
        found.append((ADAPTER, *_variant(
            node_id, consumer, type_id, producer=inner_producer, builtin=(builtin_id, binding, inner[0])
        )))
        break
    return found


def check_bindings() -> list[str]:
    """온톨로지의 tool · source 와 배선표에 남은 것이 서로 맞는지 전부 봄.

    출력  문제 문장 목록. 다 맞으면 빈 목록
    규칙  tool 이 있는 노드마다 binding_of 가, source 가 있는 노드마다 _source_of 가
          통과해야 함
          도구 · 명령 노드에는 headline 이 있어야 하고 builtin 노드에는 없어야 함
          headline 이 tool 없는 노드를 가리키면 안 됨
          받는 노드가 읽는 칸을 내놓는 쪽이 적어 두어야 함(_unreadable).
          안 적힌 칸은 짐작하지 않으므로 그 자리는 조용히 unwired 가 됨
    """
    plan_service.reload_wiring()
    headline = plan_service.HEADLINE
    problems = []
    bindings, sources = {}, {}

    for node_id in graph.node_ids():
        try:
            source = _source_of(node_id)
        except ValueError as error:
            problems.append(str(error))
        else:
            if source is not None:
                sources[node_id] = source

        try:
            binding = binding_of(node_id)
        except ValueError as error:
            problems.append(str(error))
            continue

        if binding is None:
            if node_id in headline:
                problems.append(f"headline: {node_id} 에 tool 이 없다")
            continue
        bindings[node_id] = binding

        if binding["kind"] == BUILTIN and node_id in headline:
            problems.append(f"headline: builtin {node_id} 은 답을 말하지 않는다")
        if binding["kind"] != BUILTIN and node_id not in headline:
            problems.append(f"headline: {node_id} 이 없다")

    return problems + _unreadable(bindings, sources)


def _unreadable(bindings: dict, sources: dict) -> list[str]:
    """받는 노드가 읽는 칸을 내놓는 쪽이 안 적은 자리.

    입력  읽힌 binding {노드: binding} · 읽힌 source {노드: source}
    출력  문제 문장 목록
    규칙  받는 노드마다 parameters 가 가리키는 타입과 그 타입에서 읽는 칸을 셈
          그 타입의 source 는 그 칸을 다 줘야 함
          그 타입을 hasOutput 으로 내놓는 mcp 도구 노드는 tool.outputs 가 그 칸을 다 줘야 함
          builtin 은 안 봄. 만드는 칸이 BUILTIN_ADAPTERS 에 정해져 있고, 못 받는 자리는
          일부러 unwired 로 둔 것임(_fits_adapter)
          명령 노드는 안 봄. 읽을 응답이 없음
          아무도 안 읽는 타입은 적으라고 하지 않음
    """
    problems = []
    for consumer, binding in bindings.items():
        parameters = binding["parameters"]
        for type_id in _referenced_types(parameters, graph.inputs_of(consumer)):
            fields = _read_fields(parameters, type_id)
            wanted = ", ".join(sorted(f"{type_id}.{field}" if field else type_id for field in fields))
            if type_id in sources and not _provides(sources[type_id], fields):
                problems.append(f"source: {type_id} 의 source 가 {consumer} 가 읽는 {wanted} 를 안 준다")
            for producer, produced in bindings.items():
                if produced["kind"] != MCP or type_id not in graph.outputs_of(producer):
                    continue
                if not _provides(produced["outputs"].get(type_id), fields):
                    problems.append(f"outputs: {producer} 가 {consumer} 가 읽는 {wanted} 를 안 준다")
    return problems
