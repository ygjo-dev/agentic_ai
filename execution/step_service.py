"""recipe 의 노드 사슬을 vendor 실행기가 받는 steps 배열로 바꾼다.

**도구 식별과 입력 배선은 온톨로지 노드의 tool 이 갖는다.** 여기는 그것을 읽어
경로의 한 자리에서 실제 input 을 만든다.

    tool.id          "<server_id>/<도구>"   Gateway 의 MCP 도구
                     "builtin/<이름>"       우리 쪽 계산. vendor 어댑터로 뒤 단계에 얹는다
                     "frontend/<명령>"      도구를 안 부르고 내는 지도 명령
    tool.parameters  도구 칸 -> 값
    tool.outputs     semantic 타입 -> 그 도구의 raw 응답 안에서 그 값을 읽는 경로

**값이 어디서 오는가는 경로가 정한다.** 한 노드가 이 자리에서 받는 semantic 타입은
앞 노드가 건네는 것이고(graph.handed_types), 그 값의 출처는 셋 중 하나다.

    source    앞 노드가 경로의 시작 노드다. 그 노드의 source 가 말한다
                spoken.argument   발화 해석 LLM 이 argument 로 내놓은 값
                context.<경로>    화면이 보낸 값. $context.… 로 적어 vendor 가 푼다
    step      앞 노드가 도구 단계다. $s1 · $s2 … 로 적어 vendor 가 푼다
    adapter   앞 노드가 builtin 계산이다. 그 입력을 이 단계에 얹고 어댑터를 건다

그 자리에서 건네받지 않은 타입을 가리키는 칸은 안 보낸다. 전기차 충전소 검색은
키워드 뒤에서는 query 만, 지도 범위 뒤에서는 범위 네 칸만 나간다.

**semantic 칸이 raw 값의 어디 있는지는 값을 내놓는 쪽이 적는다.**

    step      내놓는 노드의 tool.outputs      point.lon         -> $s1.location.0
                                               admin_code.code   -> $s2.items.0.code
    source    semantic 노드의 source.fields   map_extent.minLon -> $context.view.bbox.0.0

받는 노드의 parameters 는 semantic 칸(point.lon)만 알고, 그 칸이 앞 도구 응답이나
화면 값의 어디 있는지는 내놓는 쪽의 선언이 안다. 둘 사이에 공통 모양의 값을 만들지
않는다 — 칸 하나씩 경로 참조로 적을 뿐이다. **선언이 없는 칸을 이름으로 짐작하지
않는다.** 그 자리는 실행 수단이 없는 것으로 센다(binding_at).

vendor 의 _resolve_reference 에는 이름으로 좌표를 찾는 특례(lon 을 location 에서 ·
minLon 을 bbox 에서)가 남아 있다. 여기서 만드는 참조는 dict 키와 목록 번호로만 된
경로라 그 특례를 안 지난다.

**실행은 여기서 끝난다.** 참조 해석 · 입력 어댑터 · 도구 호출은 vendor 의
_execute_generic_mcp_workflow 가 steps 배열 하나를 받아 한다.
"""

import datetime
import re
import zoneinfo

import yaml

import paths
from ontology import graph

# ── 이름 ──────────────────────────────────────────────────────────

# tool.id 의 예약 namespace. 나머지는 Gateway 서버 id 다.
BUILTIN_NAMESPACE = "builtin"
FRONTEND_NAMESPACE = "frontend"

# 실행 수단 셋.
MCP = "mcp"
BUILTIN = "builtin"
COMMAND = "command"

# 중심 좌표와 반경을 bbox 넷으로 바꾸는 vendor 어댑터의 이름.
POINT_RADIUS_TO_BBOX = "point_radius_to_bbox"

# builtin 계산 -> (그것을 실제로 하는 vendor 어댑터, 그 어댑터가 도구 input 에 만드는 칸).
# **legacy vendor 의존이다.**
#
# 온톨로지에는 논리 식별(builtin/geo.pointRadiusToBbox)만 적는다. 그 계산은 지금
# vendor 의 _point_radius_to_bbox_input 이 갖고 있어서, builtin 노드는 따로 부르지
# 않고 바로 뒤 도구 단계의 inputAdapter 로 얹힌다. 계산을 우리 쪽으로 옮기면
# 이 표가 사라진다.
#
# **만드는 칸이 정해져 있다.** 어댑터는 중심 · 반경 칸을 지우고 minLon · minLat ·
# maxLon · maxLat 넷을 평평하게 만든다. 뒤 도구가 지도 범위를 bbox 배열 한 칸으로
# 받으면(행정구역 조회 · 인구 통계 조회 …) 그 넷은 모르는 칸이라 버려지고 도구는
# 범위 없이 돈다. 그래서 뒤 노드가 이 넷을 그 이름 그대로 받을 때만 잇는다
# (_fits_adapter). 지도 범위를 어떤 모양으로 건넬지 정하는 것은 다음 판의 일이다.
BUILTIN_ADAPTERS = {
    "builtin/geo.pointRadiusToBbox": (POINT_RADIUS_TO_BBOX, ("minLon", "minLat", "maxLon", "maxLat")),
}

# point_radius_to_bbox 가 중심 좌표를 찾는 칸 이름. vendor 의
# _extract_center_point 가 보는 것과 같은 순서 · 같은 이름이다.
#
# 이 중 하나도 안 남으면 어댑터가 ValueError 를 올린다("point_radius_to_bbox에는
# center/location 좌표가 필요합니다"). 그래서 plan 이 어댑터를 걸기 전에 본다.
CENTER_KEYS = ("center", "point", "coordinate", "coordinates", "location")

# 값의 출처 셋.
SOURCE = "source"
STEP = "step"
ADAPTER = "adapter"

# source.from 과 parameters 의 from 이 쓰는 머리.
SPOKEN_SOURCE = "spoken."
SPOKEN_ARGUMENT = "spoken.argument"
CONTEXT_SOURCE = "context."

# vendor 에 넘기는 화면 문맥 참조의 머리. **여기서 값을 안 채운다.** vendor 의
# _build_resolution_scope 가 state["context"] 를 scope["context"] 에 얹고
# _resolve_reference 가 제자리에서 푼다. 우리가 채우면 같은 일을 두 곳이 하게 되고,
# 문맥이 빈 요청에서 어느 쪽이 비운 것인지 알 수 없어진다.
CONTEXT_VALUE = "$context"

# 부르는 순간의 값을 가리키는 참조. 고정된 날짜를 박으면 그날이 지나는 순간
# 거짓이 된다.
#
# **Asia/Seoul 이다.** otp_plan_trip 이 설명에서 KST 를 명시적으로 요구한다
# ("서버 로케일이나 UTC 기준으로 넣으면 자정 근처에서 하루가 어긋날 수 있다").
# 서버 시간대에 기대지 않는다.
RUNTIME_NOW = "runtime.now"

RUNTIME_ZONE = zoneinfo.ZoneInfo("Asia/Seoul")

# runtime.now 뒤에 올 수 있는 이름과 그 형식. 여기 없는 이름은 터진다 —
# 조용히 넘기면 "runtime.now.datetime" 이 문자열 그대로 도구에 실려 나간다.
RUNTIME_FIELDS = {
    "date": "%Y-%m-%d",
    "time": "%H:%M",
}

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

# _resolved 가 "이 칸은 이 자리에서 안 보낸다" 를 알리는 표시.
#
# None 을 쓰지 않는다. None 은 도구가 받는 값일 수 있어 "빼라" 와 "null 을
# 보내라" 가 안 갈린다.
_OMIT = object()


# ── 배선표에 남은 것을 파일에서 읽는다 ──────────────────────────────

# YAML 의 절 이름. 여기 없는 절이 오면 터진다 — 오타 난 절은 조용히 빈 표가 되고,
# 그것이 「계기판이 조용히 죽는다」의 모양이다.
_SECTIONS = ("headline",)

# **밖에서 이 이름을 import 한다** — 계기판과 시험. 그래서 다시 읽을 때 객체를
# 갈아 끼우지 않고 **같은 dict 를 비우고 다시 채운다.** 먼저 import 해 간 쪽이 옛
# 객체를 쥐면 조용히 어긋난다.
HEADLINE: dict = {}

_wiring_mtime = None


def _load_wiring() -> None:
    """wiring.yaml 을 파서 HEADLINE 을 채움.

    규칙  _SECTIONS 의 절이 다 있어야 하고 그 밖의 절은 없어야 함. 값은 전부 문자열임
    제약  표를 다 검사한 뒤에 갈아 넣는다.
          중간에 터지면 반만 바뀐 표가 남고, 그것은 빈 표보다 나쁘다
          객체를 새로 만들지 않는다. 먼저 import 해 간 쪽이 옛 dict 를 쥔다
          온톨로지와 맞는지는 여기서 안 본다. 등록으로 온톨로지가 바뀌는 사이에
          파일 읽기가 터지면 안 됨. 맞대는 것은 check_bindings 임
    """
    name = paths.WIRING_PATH.name
    document = yaml.safe_load(paths.WIRING_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{name}: 최상위가 dict 가 아니다")

    unknown = [key for key in document if key not in _SECTIONS]
    if unknown:
        raise ValueError(f"{name}: 모르는 절 {unknown}")
    for section in _SECTIONS:
        if not isinstance(document.get(section), dict):
            raise ValueError(f"{name}: {section} 절이 없다")

    headline = document["headline"]
    for node_id, text in headline.items():
        if not isinstance(text, str):
            raise ValueError(f"{name}: headline {node_id} 이 문자열이 아니다")

    HEADLINE.clear()
    HEADLINE.update(headline)


def reload_wiring() -> None:
    """파일이 바뀌었으면 다시 판다.

    규칙  mtime 이 그대로면 아무것도 안 함. 요청마다 파일을 통째로 파지 않음
          파일을 고치면 서버를 안 내리고 반영되어야 함
    제약  판정이 끝난 뒤에 mtime 을 적는다.
          터진 파일에 mtime 만 먼저 적으면 다음 요청이 「안 바뀌었다」고 보고
          조용히 옛 표로 돈다
          경로 하나를 만드는 도중에는 안 부른다. plan 이 도는 사이에 표가
          갈리면 앞 단계와 뒷 단계가 다른 표를 쓴다
    """
    global _wiring_mtime

    mtime = paths.WIRING_PATH.stat().st_mtime_ns
    if mtime == _wiring_mtime:
        return

    _load_wiring()
    _wiring_mtime = mtime


# import 하는 때에 한 번 판다. 계기판은 표를 import 해서 곧장 읽을 뿐 아무 함수도
# 안 부른다 — 여기서 안 채우면 빈 표를 본다.
reload_wiring()


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
          mcp 도구에만 둠. builtin 은 만드는 칸이 BUILTIN_ADAPTERS 에 있고 명령은
          읽을 응답이 없음
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
        if tool_id not in BUILTIN_ADAPTERS:
            raise ValueError(f"{where}.id 는 모르는 builtin 이다: {tool_id}")
        adapter, produces = BUILTIN_ADAPTERS[tool_id]
        return {"kind": BUILTIN, "id": tool_id, "adapter": adapter, "produces": produces, "parameters": parameters}
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
            _now_field(expression, None)
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
          tool 도 source 도 없는 노드  참. 그 자리에서 가리킬 step 이 없어 plan 이 칸을 뺌.
          그 노드 자신이 unwired 로 세어짐
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


# ── 발화와 화면에서 온 값 ────────────────────────────────────────

# ★ **발화에서 인자를 뽑는 자리는 여기 없다.** 발화 해석 LLM 이 argument 와 이름
#   있는 값을 함께 내놓는 것 하나뿐이다. 두 곳이 인자를 뽑으면 어느 값이 어디서
#   왔는지 표에서 안 갈린다. 같은 일을 정규식으로 되살리지 않는다.


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


def context_starts(context: dict | None) -> list[str]:
    """지금 화면 문맥이 값을 줄 수 있는 시작 노드.

    입력  KRRI_ASAP 화면이 보낸 context. 없거나 dict 가 아니면 빈 것으로 봄
    출력  노드 id 목록. context_sources 의 차례
    규칙  칸이 있고 비어 있지 않아야 셈. selectedLocation 이 null 로 오는 것이
          KRRI_ASAP 의 평상시 모양임(우클릭을 안 했을 때)
    제약  값이 좌표로 쓸 만한지 여기서 보지 않는다.
          범위를 재는 것은 vendor 의 _parse_lon_lat 이고, 여기가 또 재면
          두 곳이 다른 기준을 갖게 됨
    """
    found = []
    for node_id, path in context_sources().items():
        value = context if isinstance(context, dict) else None
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if value not in (None, "", [], {}):
            found.append(node_id)
    return found


# ── 한 자리의 input 을 만든다 ──────────────────────────────────────


def _now_field(reference: str, now: datetime.datetime | None) -> str | None:
    """"runtime.now.date" 같은 참조를 부르는 순간의 값으로.

    입력  참조 · 부르는 순간. now 가 None 이면 이름만 검사함
    출력  RUNTIME_FIELDS 의 형식으로 찍은 문자열
    규칙  runtime.now 뒤 이름 하나만 봄. "runtime.now" 만 적은 것도 모르는 이름으로 봄
    제약  모르는 이름을 조용히 넘기지 않는다.
          그대로 두면 "runtime.now.datetime" 이라는 문자열이 도구에 그대로 실려
          나가고, 0건이 오지 오류가 오지 않는다
          시각을 여기서 읽지 않는다.
          부르는 쪽이 경로 하나에 한 번 읽어 넘김. 여기서 읽으면 칸마다
          다른 순간이 되어 자정 언저리에서 date 와 time 이 어긋남
    """
    head, _, field = reference.partition(RUNTIME_NOW + ".")
    if head or field not in RUNTIME_FIELDS:
        raise ValueError(f"{paths.ONTOLOGY_PATH.name}: 모르는 {RUNTIME_NOW} 이름 {reference!r}")
    return now.strftime(RUNTIME_FIELDS[field]) if now is not None else None


def _semantic(node_id: str, type_id: str, field: str, origin, argument):
    """이 자리에서 받은 semantic 값을 가리키는 것.

    입력  받는 노드 · 참조의 뿌리 타입(point) · 뿌리 뒤 칸 이름(lon. 없으면 빈 문자열) ·
          값의 출처 · 발화 인자
    출력  발화 인자 그대로 · "$context.…" · "$s1.…". 못 가리키면 _OMIT
    규칙  출처는 (source, 시작 노드) · (step, step id, 내놓은 노드) · (adapter, …) 임
          source spoken.argument  인자 그대로. 칸 이름이 붙으면 오류
          source context.<경로>   "$context.<경로>.<source.fields 의 그 칸 경로>".
                                  칸 없이 통째로 가리키면 "$context.<경로>"
          step                    "$<step id>.<내놓은 노드 tool.outputs 의 그 칸 경로>".
                                  list 가 있으면 "<list>.<고른 번호>." 가 앞에 붙음
          step 인데 가리킬 step 이 없음 · adapter  _OMIT
    제약  값을 지어내지 않는다. 앞 단계가 없을 때 좌표를 만들어 넣지 않고 칸을 뺀다
          읽는 법이 안 적힌 칸을 이름으로 짐작하지 않는다. binding_at 이 먼저 거르고,
          여기까지 오면 터진다
    """
    kind = origin[0] if origin else None

    if kind == SOURCE:
        source = _source_of(origin[1])
        if source["from"] == SPOKEN_ARGUMENT:
            if field:
                raise ValueError(f"{node_id}: 발화 인자에는 칸이 없다 ({type_id}.{field})")
            return argument
        if source["from"].startswith(CONTEXT_SOURCE):
            path = _path_of(f"{node_id}: {origin[1]}.source", source, field)
            return f"${source['from']}.{path}" if path else f"${source['from']}"
        raise ValueError(f"{node_id}: 모르는 source {source['from']!r}")

    if kind == STEP and origin[1] is not None:
        step_id, producer = origin[1], origin[2]
        reading = ((binding_of(producer) or {}).get("outputs") or {}).get(type_id)
        path = _path_of(f"{node_id}: {producer}.tool.outputs.{type_id}", reading, field)
        return f"${step_id}.{path}"

    return _OMIT


def _resolved(expression, node_id: str, type_id: str, origin, argument, options, now):
    """parameters 의 값 하나를 이 자리의 실제 값으로.

    출력  보낼 값. 이 자리에서 안 보내는 칸이면 _OMIT
    규칙  runtime.now.<이름>   부르는 순간의 값
          semantic 참조        이 자리에서 받는 타입이면 _semantic. 다른 타입이면 _OMIT
          그 밖의 문자열 · 수  그대로
          목록                 안에 _OMIT 이 하나라도 있으면 칸 전체를 뺌
          from spoken.<이름>   말한 값. 안 말했으면(None · 빈 것) default. map 이
                               있으면 도구가 쓰는 말로 바꾸고, 모르는 말은 default 의 것
          from context.<경로>  "$context.<경로>"
          조건                 값이 어미로 끝나는지 보고 보내거나 뺌
    제약  조건을 부르기 전에 모르는 값에 걸지 않는다.
          앞 단계 결과는 vendor 가 나중에 풀어서 여기서 어미를 볼 수 없음
    """
    if isinstance(expression, str):
        if expression.startswith(RUNTIME_NOW + "."):
            return _now_field(expression, now)
        root, _, field = expression.partition(".")
        if root not in graph.inputs_of(node_id):
            return expression
        if root != type_id:
            return _OMIT
        return _semantic(node_id, root, field, origin, argument)

    if isinstance(expression, list):
        values = [_resolved(item, node_id, type_id, origin, argument, options, now) for item in expression]
        return _OMIT if any(value is _OMIT for value in values) else values

    if isinstance(expression, dict) and "from" in expression:
        source = expression["from"]
        if source.startswith(CONTEXT_SOURCE):
            return f"${source}"
        said = (options or {}).get(source[len(SPOKEN_SOURCE):])
        chosen = said if said not in (None, "", [], {}) else expression["default"]
        mapping = expression.get("map")
        if mapping is None:
            return chosen
        return mapping.get(chosen, mapping[expression["default"]])

    if isinstance(expression, dict) and "value" in expression:
        value = _resolved(expression["value"], node_id, type_id, origin, argument, options, now)
        if value is _OMIT:
            return _OMIT
        if origin is None or origin[0] != SOURCE or _source_of(origin[1])["from"] != SPOKEN_ARGUMENT:
            raise ValueError(f"{node_id}: 값을 보고 칸을 고르려면 발화 인자여야 한다")
        text = str(value or "")
        if "if_endswith" in expression:
            keep = text.endswith(expression["if_endswith"])
        else:
            keep = not text.endswith(expression["unless_endswith"])
        return value if keep else _OMIT

    return expression


def _has_center(tool_input: dict) -> bool:
    """point_radius_to_bbox 가 걸 중심 좌표가 input 에 남았는지.

    규칙  CENTER_KEYS 중 하나라도 있으면 참. 값이 무엇인지는 안 봄.
          ["$s1.location.0", "$s1.location.1"] 처럼 vendor 가 나중에 푸는 참조라
          지금 판정할 수 없음
    """
    return any(key in tool_input for key in CENTER_KEYS)


def _step_input(binding: dict, node_id: str, type_id: str, origin, argument, options, now) -> tuple[dict, str | None]:
    """한 자리의 input 과 걸 어댑터.

    입력  binding_of 의 결과 · 노드 · 이 자리에서 받는 타입 · 값의 출처 · 발화 인자 ·
          이름 있는 값 · 부르는 순간
    출력  (input, 어댑터 이름 또는 None)
    규칙  parameters 차례대로 _resolved 를 부르고 _OMIT 인 칸은 뺌
          출처가 adapter 면 앞 builtin 노드의 input 을 먼저 두고 이 노드의 나머지
          칸을 이어 붙임. 중심 좌표 칸이 남았을 때만 어댑터를 걺
          걸 것이 없는데 걸면 vendor 어댑터가 ValueError 를 올림
    """
    filled = {}
    for field, expression in binding["parameters"].items():
        value = _resolved(expression, node_id, type_id, origin, argument, options, now)
        if value is not _OMIT:
            filled[field] = value

    if origin is not None and origin[0] == ADAPTER:
        filled = {**origin[1]["input"], **filled}
        return filled, origin[1]["adapter"] if _has_center(filled) else None
    return filled, None


def _headline(template: str, argument: str) -> str:
    """답의 첫 줄. 인자가 이미 문장 안에 있으면 앞에 안 붙임.

    입력  HEADLINE 의 틀 · 발화에서 뽑은 인자
    규칙  틀은 전부 "{arg} …" 꼴이라 뒤 문장이 인자로 시작하면 같은 말이 두 번
          나감. "전기차 충전소 전기차 충전소를 조회했습니다." 가 그것임
          (2026-08-25 화면 실측)
          겹침은 앞머리 일치로만 봄. 포함으로 보면 "역" 같은 짧은 인자가
          "국회의원 지역구" 안에 걸려 멀쩡한 인자까지 빠짐
          겹치면 인자를 빼고 뒤 문장만. 인자가 비어도 마찬가지임
    제약  headline 줄들을 고치지 않는다.
          겹치는 것은 한 줄이 아니라 「인자 + 도구 이름」이 만나는 자리임.
          줄마다 고치면 발화가 바뀔 때 또 겹침
    """
    rest = template.format(arg="").strip()
    if not argument or rest.startswith(argument):
        return rest
    return template.format(arg=argument)


# ── 실행 계획 ──────────────────────────────────────────────────


def plan(recipe_id: str, argument: str, options: dict | None = None) -> dict:
    """recipe 한 벌을 vendor 가 받는 실행 계획으로.

    입력  recipe id · 발화에서 뽑은 인자. 장소인지 키워드인지 식별자인지는
          여기서 안 가름
          options 는 발화 해석이 함께 내놓은 이름 있는 값임. 안 주면 parameters 의
          default 만 씀
    출력  steps  vendor 의 intent["steps"] 에 그대로 들어갈 배열
          nodes  steps 와 같은 길이. steps[i] 를 만든 노드 id
          commands  도구를 안 부르고 곧장 내는 지도 명령
          command_nodes  commands 와 같은 길이. commands[i] 를 만든 노드 id
          headline  답의 첫 줄. 경로의 마지막 도구 · 명령 노드가 정함
    규칙  step id 는 s1 · s2 … 로 붙음. 앞 단계 참조를 그 id 로 적음
          첫 노드는 시작 데이터라 부를 것이 없음. 둘째 노드의 값은 그 source 에서 옴
          앞 단계 참조는 step id 와 그 step 을 만든 노드를 함께 들고 감. 같은 타입을
          화면과 앞 단계가 둘 다 줄 수 있어(경로 탐색의 출발 · 도착) 타입만으로는
          어느 쪽 값인지 안 갈림
          frontend 노드는 step 이 아니라 지도 명령이 됨. vendor 에 넘어간 step 이 없어
          그 뒤 노드가 가리킬 것이 없음
          builtin 노드는 step 을 안 만듦. 그 입력과 어댑터가 바로 뒤 노드에 얹힘
          tool 이 없거나 받는 타입이 안 맞는 노드는 건너뜀. 부를지 말지는
          unwired 로 부르는 쪽이 먼저 봄. 건너뛴 노드 뒤에서도 가리킬 step 이 없음
          맨 앞에서 한 번만 wiring.yaml 을 다시 읽음. 경로를 만드는 도중에
          표가 갈리면 앞 단계와 뒷 단계가 다른 표를 씀
    제약  건너뛴 노드 · 명령 노드 뒤에서 그보다 앞 단계를 대신 가리키지 않는다.
          그 앞 단계는 뒤 노드가 받는 타입을 낸 노드가 아님
    """
    reload_wiring()

    # 경로 하나에 한 번만 읽는다. 단계마다 읽으면 자정 언저리에서 date 와
    # time 이 서로 다른 날을 가리킬 수 있다.
    now = datetime.datetime.now(RUNTIME_ZONE)

    steps: list[dict] = []
    nodes: list[str] = []
    commands: list[dict] = []
    command_nodes: list[str] = []
    headline = ""

    chain = [entry["node_id"] for entry in graph.path_of(recipe_id)]
    origin = (SOURCE, chain[0]) if chain and _source_of(chain[0]) else (STEP, None, None)

    for source_id, node_id in zip(chain, chain[1:]):
        found = binding_at(node_id, source_id)
        if found is None:
            origin = (STEP, None, node_id)
            continue

        binding, type_id = found
        filled, adapter = _step_input(binding, node_id, type_id, origin, argument, options, now)

        if binding["kind"] == BUILTIN:
            origin = (ADAPTER, {"adapter": binding["adapter"], "input": filled})
            continue

        headline = _headline(HEADLINE[node_id], argument)

        if binding["kind"] == COMMAND:
            commands.append({"op": binding["command"], "args": filled})
            command_nodes.append(node_id)
            origin = (STEP, None, node_id)
            continue

        step_id = f"s{len(steps) + 1}"
        step = {
            "id": step_id,
            "server_id": binding["server_id"],
            "tool": binding["tool"],
            "input": filled,
        }
        if adapter:
            step["inputAdapter"] = adapter
        steps.append(step)
        nodes.append(node_id)
        origin = (STEP, step_id, node_id)

    return {
        "steps": steps,
        "nodes": nodes,
        "commands": commands,
        "command_nodes": command_nodes,
        "headline": headline,
    }


# ── 이 recipe 를 지금 부를 수 있는가 ───────────────────────────

# spoken_needed 가 계획에 심어 보는 값. parameters 가 발화 인자를 실제로 쓰면 만들어진
# input 에 이 문자열이 그대로 남는다.
#
# **발화에서 올 수 있는 값과 겹치지 않아야 한다.** 사람이 말할 수 없는 글자로
# 짓는다 — 겹치면 「인자를 안 썼다」를 「썼다」로 잘못 세게 된다.
_SPOKEN_PROBE = "\x00spoken-probe\x00"


def spoken_needed(recipe_id: str) -> bool:
    """그 recipe 가 발화에서 온 값을 실제로 쓰는가.

    출력  참이면 인자가 없을 때 부르면 안 됨
    규칙  실제 계획을 봄. 온톨로지를 통째로 훑지 않음. 어느 타입을 받는지는 앞
          노드가 건네는 것이 정함
          지도 명령의 args 도 봄. 도구를 안 부르고 명령만 내는 노드도 발화에서
          온 값을 쓸 수 있음(시설물 화면이 그것임)
          문맥에서 시작하는 recipe 라도 뒤 단계가 발화 인자를 쓰면 참임.
          경로 탐색(출발지는 찍은 지점 · 도착지는 말한 장소)이 그 자리임
    제약  recipe id 로 가르지 않는다.
          특수분기를 두면 recipe 가 늘 때마다 여기를 고쳐야 하고, 온톨로지만 바꾼
          자리는 조용히 어긋남
    """
    plan_result = plan(recipe_id, _SPOKEN_PROBE)

    sources = [step["input"] for step in plan_result["steps"]]
    sources += [command["args"] for command in plan_result["commands"]]
    return any(_holds_probe(value) for value in sources)


def _holds_probe(value) -> bool:
    """계획 조각 어딘가에 발화 인자가 들어갔는가. 중첩된 dict · list 까지."""
    if isinstance(value, dict):
        return any(_holds_probe(item) for item in value.values())
    if isinstance(value, list):
        return any(_holds_probe(item) for item in value)
    return isinstance(value, str) and value.startswith(_SPOKEN_PROBE)


def context_needs(recipe_id: str) -> set[str]:
    """그 recipe 가 화면 문맥에서 값을 받아야 하는 시작 노드.

    출력  노드 id 집합. 문맥을 안 쓰는 recipe 는 빈 집합
    규칙  실제로 만들어진 step 의 input 을 봄. 온톨로지를 통째로 훑지 않음.
          지점 좌표는 화면에서도 오고 장소 좌표 변환에서도 오므로, 쓰이지도 않을
          source 를 세면 「장소 이름 -> 좌표 -> 충전소」가 찍은 지점을 요구하게 됨
          "$context.<칸>" 의 첫 칸 이름으로 가름. 그 이름이 어느 시작 노드인지는
          context_sources 가 앎
          지도 명령의 args 도 봄
    제약  경로의 첫 칸만 보지 않는다.
          문맥 값이 첫 단계에만 온다는 보장이 없음. 경로 탐색은 출발지를
          둘째 단계에서 받으므로 첫 칸만 보면 찍은 지점이 없어도 후보로 남아
          required 가 빈 채로 도구를 부름
    """
    plan_result = plan(recipe_id, "")
    sources_by_root = context_sources()

    found: set[str] = set()
    sources = [step["input"] for step in plan_result["steps"]]
    sources += [command["args"] for command in plan_result["commands"]]
    for value in sources:
        _context_roots(value, found, sources_by_root)
    return found


def _context_roots(value, found: set[str], sources_by_root: dict) -> None:
    """input 조각에 든 "$context.<칸>" 의 칸 이름을 시작 노드로.

    규칙  중첩된 dict · list 까지 내려감
          context_sources 에 없는 칸 이름은 담지 않음. 시작 노드가 아닌 문맥
          값을 읽는 칸은 판정할 것이 없음
    """
    if isinstance(value, dict):
        for item in value.values():
            _context_roots(item, found, sources_by_root)
        return
    if isinstance(value, list):
        for item in value:
            _context_roots(item, found, sources_by_root)
        return
    if not isinstance(value, str) or not value.startswith(CONTEXT_VALUE + "."):
        return

    root = value[len(CONTEXT_VALUE) + 1:].split(".")[0]
    for node_id, path in sources_by_root.items():
        if path[0] == root:
            found.add(node_id)


def unwired(recipe_id: str) -> list[str]:
    """아직 실행 수단이 안 붙은 노드.

    출력  이 자리에서 받는 타입에 맞는 tool 이 없는 실행 노드 id 목록. 경로 순서.
          전부 있으면 빈 목록
    규칙  경로를 recipe 파일에서 읽어 unwired_in 에 넘김
          부르는 쪽(execute_service.run)이 비어 있지 않으면 도구를 하나도
          안 부름. tool 을 안 적은 노드와 그 이유는 온톨로지의 그 노드 곁에 있음
    """
    return unwired_in([entry["node_id"] for entry in graph.path_of(recipe_id)])


def unwired_in(chain: list[str]) -> list[str]:
    """노드 사슬 하나에서 실행 수단이 안 붙은 노드.

    입력  노드 id 목록. recipe 파일로 아직 안 쓴 후보도 받음
    출력  unwired 와 같은 모양
    규칙  실행 노드만 셈. 시작 데이터 노드는 부를 것이 없어 세지 않음
          tool 이 있어도 이 자리에서 건네받는 타입을 parameters 가 안 가리키면 셈
          앞 builtin 이 만드는 칸을 못 받는 자리도 셈
          앞 노드가 이 노드가 읽는 칸의 경로를 적지 않은 자리도 셈(binding_at)
    """
    reload_wiring()
    return [
        node_id
        for source_id, node_id in zip(chain, chain[1:])
        if graph.is_executable(node_id) and binding_at(node_id, source_id) is None
    ]


# ── 계기판 · 시험이 도구 스키마와 맞대는 input 벌 ─────────────────


def variants(node_id: str) -> list[dict]:
    """그 노드가 보낼 수 있는 input 벌 전부.

    출력  [{node, type, origin, suffix, input, adapter, spoken}, ...]
          origin 은 source · step · adapter 중 그 타입이 실제로 올 수 있는 것
          suffix 는 조건 칸의 어미 갈래. 기본 벌은 빈 문자열
          spoken 은 발화 인자가 들어갔는지
    규칙  plan 이 쓰는 _step_input 을 그대로 부름. 계기판이 규칙을 따로 옮겨 적으면
          실행과 표가 조용히 어긋남
          출처는 _origins 가 정함. 이 노드가 그 타입에서 읽는 칸을 줄 수 있는 출처만 담음
          조건 칸이 있으면 그 어미로 끝나는 인자로 한 벌을 더 만듦. 같은 벌은 안 담음
          이름 있는 값은 전부 default 로 채움. 부르는 순간은 고정된 한 시각임
    """
    reload_wiring()
    binding = binding_of(node_id)
    if binding is None:
        return []

    now = datetime.datetime(2026, 1, 1, 9, 0, tzinfo=RUNTIME_ZONE)
    inputs = graph.inputs_of(node_id)
    arguments = [("", _SPOKEN_PROBE)] + [
        (suffix, _SPOKEN_PROBE + suffix) for suffix in _suffixes(binding["parameters"])
    ]

    rows = []
    for type_id in _referenced_types(binding["parameters"], inputs):
        for origin_name, origin in _origins(binding, type_id, now):
            seen = []
            for suffix, argument in arguments:
                filled, adapter = _step_input(binding, node_id, type_id, origin, argument, None, now)
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


def _origins(consumer: dict, type_id: str, now: datetime.datetime) -> list[tuple[str, tuple]]:
    """그 타입의 값이 올 수 있는 출처. variants 가 벌을 가르는 데 씀.

    규칙  source 는 그 타입의 source 가 받는 노드(consumer)가 읽는 칸을 줄 때만 담음
          step 은 그 칸을 outputs 로 주는 첫 도구 노드가 내놓은 것으로 봄
          builtin 출처는 consumer 가 그 어댑터의 칸을 받을 때만 담음. 그 builtin 의
          입력도 같은 규칙으로 앞 도구 단계에서 받은 모양임
    """
    fields = _read_fields(consumer["parameters"], type_id)
    found = []

    source = _source_of(type_id)
    if source is not None and _provides(source, fields):
        found.append((SOURCE, (SOURCE, type_id)))

    producer = _step_producer(type_id, fields)
    if producer is not None:
        found.append((STEP, (STEP, "s1", producer)))

    for node_id in graph.node_ids():
        if type_id not in graph.outputs_of(node_id):
            continue
        binding = binding_of(node_id)
        if binding is None or binding["kind"] != BUILTIN:
            continue
        if not _fits_adapter(consumer["parameters"], type_id, binding["produces"]):
            continue
        inner = _referenced_types(binding["parameters"], graph.inputs_of(node_id))
        if not inner:
            continue
        inner_producer = _step_producer(inner[0], _read_fields(binding["parameters"], inner[0]))
        if inner_producer is None:
            continue
        origin = (STEP, "s1", inner_producer)
        filled, _ = _step_input(binding, node_id, inner[0], origin, _SPOKEN_PROBE, None, now)
        found.append((ADAPTER, (ADAPTER, {"adapter": binding["adapter"], "input": filled})))
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
    reload_wiring()
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
            if node_id in HEADLINE:
                problems.append(f"headline: {node_id} 에 tool 이 없다")
            continue
        bindings[node_id] = binding

        if binding["kind"] == BUILTIN and node_id in HEADLINE:
            problems.append(f"headline: builtin {node_id} 은 답을 말하지 않는다")
        if binding["kind"] != BUILTIN and node_id not in HEADLINE:
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
