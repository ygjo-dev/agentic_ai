"""게시된 Recipe.execution 과 요청 하나의 값으로 KRRI_ASAP native call_mcp_workflow 를 만든다.

**여기는 계획을 만들지 않는다.** 어느 노드를 어느 서버 · 도구로 부르고 칸마다 값이
어디서 오는지는 agentic_ai 밖의 등록 저장소가 온톨로지와 사람이 받아들인 노드 사슬로
compile 해 recipe 파일에 게시해 두었다. 요청 중에는 그 블록만 읽는다.
온톨로지를 import 하지 않는다.

    Recipe.execution    게시된 정적 기호 계획. agentic_ai 안의 semantic IR 이고 요청과 무관하다
      spoken_needed     발화 인자를 쓰는가. 안 말했으면 부르지 않는다
      unwired           실행 수단이 없는 노드. 있으면 workflow 가 비고 부르지 않는다
      context_needs     화면에서 받아야 하는 시작 노드 -> {from: context.<경로>, fields}
      workflow          차례대로. 도구 단계 {id, node, server_id, tool, transform?, input, outputs?}
                        지도 명령 {node, command, transform?, input}

    materialize         Recipe.execution + 이번 요청의 spoken · context · 부르는 순간
      status            READY 가 아니면 무엇이 모자란지(missing)만 적고 workflow 가 없다
      workflow          {action: call_mcp_workflow, steps}. KRRI_ASAP 실행기가 받는 한 벌 그대로
      nodes             steps 와 같은 길이. steps[i] 를 만든 노드
      commands          도구를 안 부르고 곧장 내는 지도 명령. command_nodes 가 같은 길이
      context           실행기가 $context.… 를 풀 화면 문맥

Recipe.execution 의 값 하나는 이 꼴 중 하나다.

    {value: <상수>}
    {from: spoken.argument}                         발화 인자
    {from: spoken.argument, if_endswith: 선}         그 어미로 끝날 때만(unless_endswith 는 반대)
    {from: spoken.<이름>, default: …, map: {…}}      발화 해석이 함께 뽑은 이름 있는 값
    {from: context.<시작 노드>.<칸>}                 context_needs 의 선언으로 읽는 화면 값
    {from: s<N>.<타입>.<칸>}                         앞 단계 s<N> 이 outputs 로 내놓은 값
    {from: transform.<타입>.<칸>}                    이 단계의 transform 이 만드는 값
    {from: runtime.now.<date|time>}                  부르는 순간
    [ … ]                                            위 꼴의 목록

**같은 타입이라도 누가 내놓았는지가 기호에 남는다.** 화면에서 찍은 지점은
context.point.lat, 앞 단계가 찾은 지점은 s1.point.lat 이다.

**raw 응답의 어디를 읽을지는 내놓는 쪽에 적는다.** 앞 단계는 그 단계의
outputs(point.lon -> location.0), 화면 값은 context_needs 의 fields 다. 받는 쪽은 semantic
칸만 가리키고, 여기서 두 선언을 이어 raw 참조를 적는다. 경로를 짐작하지 않는다.

KRRI native 표현은 여기서만 생긴다.

    발화 인자 · 이름 있는 값 · 부르는 순간     값으로 채움
    조건(if_endswith · unless_endswith)      지금 인자로 가려 칸을 빼거나 둠
    앞 단계 참조 s1.point.lon                 그 단계 outputs 의 경로로 "$s1.location.0"
    화면 값 context.point.lon                 context_needs 의 선언으로 "$context.selectedLocation.lon"
    transform                                 그 입력을 칸에 두고 inputAdapter 를 명시로 걺
    지도 명령                                 인자를 채워 workflow 밖 commands 로 냄

**KRRI 실행기의 편의 추론에 기대지 않는다.** 서버 · 도구 이름은 게시된 그대로 적고,
참조는 dict 키 · 목록 번호 경로만 쓰고, 범위 변환은 inputAdapter 로 건다. 짧은 도구 이름
정규화 · 자동 bbox 변환 · 참조 이름 특례 · web.search 질의 보수가 없어도 같은 호출이 나간다.

**사람에게 보일 문장을 만들지 않는다.** 부를 수 없으면 status 와 missing 만 돌려준다.
"""

import copy
import datetime
import re
import zoneinfo

import yaml

import paths

# ── 이름 ──────────────────────────────────────────────────────────

# 기호의 머리.
SPOKEN_ARGUMENT = "spoken.argument"
SPOKEN_SOURCE = "spoken."
CONTEXT_SOURCE = "context."
TRANSFORM = "transform"

# 발화 해석 결과에서 spoken.<이름> 으로 읽는 이름 있는 값.
#
# 칸의 모양(type · enum)은 resolve 역할의 response schema 가 갖는다. 여기는
# 무엇을 받아 가는가만 적는다. 온톨로지 노드의 tool.parameters 가 그 이름을
# {from: spoken.<이름>} 으로 불러 제 칸에 넣는다.
SPOKEN_OPTIONS = (
    "travel_mode",
    "minutes",
    "admin_level",
)

# 부르는 순간의 값을 가리키는 기호. 고정된 날짜를 박으면 그날이 지나는 순간
# 거짓이 된다.
#
# **Asia/Seoul 이다.** otp_plan_trip 이 설명에서 KST 를 명시적으로 요구한다
# ("서버 로케일이나 UTC 기준으로 넣으면 자정 근처에서 하루가 어긋날 수 있다").
RUNTIME_NOW = "runtime.now"

RUNTIME_ZONE = zoneinfo.ZoneInfo("Asia/Seoul")

# runtime.now 뒤에 올 수 있는 이름과 그 형식. 여기 없는 이름은 터진다.
RUNTIME_FIELDS = {
    "date": "%Y-%m-%d",
    "time": "%H:%M",
}

# 중심 좌표와 반경을 bbox 넷으로 바꾸는 KRRI 실행기 inputAdapter 의 이름.
POINT_RADIUS_TO_BBOX = "point_radius_to_bbox"

# 계약이 아는 transform id -> 그것을 계산하는 KRRI 실행기 inputAdapter.
TRANSFORM_ADAPTERS = {
    "builtin/geo.pointRadiusToBbox": POINT_RADIUS_TO_BBOX,
}
TRANSFORMS = tuple(TRANSFORM_ADAPTERS)

# point_radius_to_bbox 가 중심 좌표를 찾는 칸 이름. KRRI 실행기의
# _extract_center_point 가 보는 것과 같은 순서 · 같은 이름이다.
#
# 이 중 하나도 안 남으면 어댑터가 ValueError 를 올린다("point_radius_to_bbox에는
# center/location 좌표가 필요합니다"). 그래서 어댑터를 걸기 전에 본다.
CENTER_KEYS = ("center", "point", "coordinate", "coordinates", "location")

# KRRI 실행기가 steps 를 workflow 로 알아보게 하는 이름.
WORKFLOW_ACTION = "call_mcp_workflow"

# native 참조의 머리. KRRI 실행기가 state["context"] 를 scope["context"] 에, 앞 단계
# 결과를 scope["s<N>"] 에 얹고 제자리에서 푼다.
REFERENCE = "$"

# materialize 의 판정. READY 말고는 부르지 않는다.
READY = "READY"
NOT_ACCEPTED = "NOT_ACCEPTED"          # recipe 파일이 없다. 받아들인 recipe 가 아님
MISSING_ARGUMENT = "MISSING_ARGUMENT"  # 발화 인자가 필요한데 없다. missing = [시작 노드]
UNWIRED = "UNWIRED"                    # 실행 수단이 없는 노드가 있다. missing = 그 노드들
MISSING_CONTEXT = "MISSING_CONTEXT"    # 화면 값이 안 왔다. missing = 그 시작 노드들
NOTHING_TO_CALL = "NOTHING_TO_CALL"    # 부를 도구도 지도 명령도 없다

# 칸 이름 · 경로 마디. 점으로 이은 dict 키 · 목록 번호다(location.0 · bbox.1.0).
_SEGMENT = r"[0-9A-Za-z_-]+"
_RAW_PATH = re.compile(rf"{_SEGMENT}(?:\.{_SEGMENT})*")
_FIELD_NAME = re.compile(_SEGMENT)
_STEP_ID = re.compile(r"s[1-9][0-9]*")

# execution 과 그 조각이 가질 수 있는 칸.
_EXECUTION_FIELDS = ("spoken_needed", "unwired", "context_needs", "workflow")
_STEP_FIELDS = ("id", "node", "server_id", "tool", "transform", "input", "outputs")
_COMMAND_FIELDS = ("node", "command", "transform", "input")
_TRANSFORM_FIELDS = ("id", "node", "input")
_CONTEXT_FIELDS = ("from", "fields")
_CONDITIONS = ("if_endswith", "unless_endswith")

# _bound 가 "이 칸은 이 자리에서 안 보낸다" 를 알리는 표시.
#
# None 을 쓰지 않는다. None 은 도구가 받는 값일 수 있어 "빼라" 와 "null 을
# 보내라" 가 안 갈린다.
_OMIT = object()


class PlanError(ValueError):
    """recipe 파일의 execution 블록이 없거나 알아볼 수 없다. 게시 오류다."""


def now_field(reference: str, now: datetime.datetime | None) -> str | None:
    """"runtime.now.date" 같은 기호를 부르는 순간의 값으로.

    입력  기호 · 부르는 순간. now 가 None 이면 이름만 검사함
    출력  RUNTIME_FIELDS 의 형식으로 찍은 문자열
    규칙  runtime.now 뒤 이름 하나만 봄. "runtime.now" 만 적은 것도 모르는 이름으로 봄
    제약  모르는 이름을 조용히 넘기지 않는다.
          그대로 두면 "runtime.now.datetime" 이라는 문자열이 도구에 그대로 실려
          나가고, 0건이 오지 오류가 오지 않는다
          시각을 여기서 읽지 않는다.
          부르는 쪽이 계획 하나에 한 번 읽어 넘김. 칸마다 읽으면 자정 언저리에서
          date 와 time 이 어긋남
    """
    head, _, field = reference.partition(RUNTIME_NOW + ".")
    if head or field not in RUNTIME_FIELDS:
        raise ValueError(f"모르는 {RUNTIME_NOW} 이름 {reference!r}")
    return now.strftime(RUNTIME_FIELDS[field]) if now is not None else None


def mentions_argument(value) -> bool:
    """execution 조각 어딘가가 발화 인자를 가리키는가. 중첩된 dict · list 까지."""
    if isinstance(value, dict):
        return value.get("from") == SPOKEN_ARGUMENT or any(mentions_argument(item) for item in value.values())
    if isinstance(value, list):
        return any(mentions_argument(item) for item in value)
    return False


# ── recipe 파일에서 읽는다 ──────────────────────────────────────────


def _document(recipe_id: str) -> dict | None:
    """recipe 파일 한 벌. 파일이 없으면 None."""
    path = paths.RECIPES_DIR / f"{recipe_id}.yaml"
    if not path.exists():
        return None
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else {}


def load(recipe_id: str) -> dict | None:
    """그 recipe 의 execution 블록.

    출력  검사를 통과한 execution dict. recipe 파일이 없으면 None
    규칙  파일이 없는 것은 받아들인 recipe 가 아닌 것임. 부를 것이 없음
          파일이 있는데 execution 이 없거나 알아볼 수 없으면 PlanError
    제약  execution 이 없다고 온톨로지로 계획을 다시 만들지 않는다.
          그러면 게시한 블록과 온톨로지 중 무엇이 원천인지 다시 둘이 됨.
          블록은 등록 저장소가 다시 게시함
    """
    document = _document(recipe_id)
    if document is None:
        return None
    execution = document.get("execution")
    validate(execution, recipe_id)
    return execution


def validate(execution, where: str) -> None:
    """execution 블록이 지금 recipe 들이 쓰는 꼴인지.

    규칙  칸 · 타입 · step id 중복 · 앞 단계가 아닌 s<N> 참조 · 선언 안 된 화면 값 ·
          앞 단계 outputs 에 없는 타입과 칸 · transform 없는 transform 참조 ·
          모르는 transform · 모르는 runtime.now 이름을 봄
          spoken_needed 는 workflow 가 발화 인자를 가리키는지와 같아야 함
          unwired 가 있으면 workflow 가 비어야 함
    제약  모든 워크플로 언어를 받으려고 넓히지 않는다. 지금 게시하는 꼴만 받는다
    """

    def fail(message):
        return PlanError(f"{where}: execution {message}")

    if not isinstance(execution, dict):
        raise fail("블록이 없다. 게시된 Recipe.execution 이 필요하다")
    unknown = [key for key in execution if key not in _EXECUTION_FIELDS]
    if unknown:
        raise fail(f"에 모르는 칸 {unknown}")

    if not isinstance(execution.get("spoken_needed"), bool):
        raise fail("spoken_needed 가 참거짓이 아니다")
    unwired = execution.get("unwired", [])
    if not isinstance(unwired, list) or not all(isinstance(node, str) for node in unwired):
        raise fail("unwired 가 노드 id 목록이 아니다")

    needs = execution.get("context_needs")
    if not isinstance(needs, dict):
        raise fail("context_needs 가 dict 가 아니다")
    for start, declaration in needs.items():
        _check_context(f"context_needs.{start}", declaration, fail)

    workflow = execution.get("workflow")
    if not isinstance(workflow, list):
        raise fail("workflow 가 목록이 아니다")
    if unwired and workflow:
        raise fail("unwired 가 있는데 workflow 가 비지 않았다")

    outputs: dict[str, dict] = {}
    for index, entry in enumerate(workflow):
        at = f"workflow[{index}]"
        if not isinstance(entry, dict) or not isinstance(entry.get("node"), str):
            raise fail(f"{at} 에 node 가 없다")
        command = "command" in entry
        allowed = _COMMAND_FIELDS if command else _STEP_FIELDS
        unknown = [key for key in entry if key not in allowed]
        if unknown:
            raise fail(f"{at} 에 모르는 칸 {unknown}")

        if command:
            if not isinstance(entry["command"], str) or not entry["command"]:
                raise fail(f"{at}.command 가 비었다")
        else:
            step_id = entry.get("id")
            if not isinstance(step_id, str) or not _STEP_ID.fullmatch(step_id):
                raise fail(f"{at}.id 가 s<N> 이 아니다: {step_id!r}")
            if step_id in outputs:
                raise fail(f"{at}.id {step_id} 가 겹친다")
            for key in ("server_id", "tool"):
                if not isinstance(entry.get(key), str) or not entry[key]:
                    raise fail(f"{at}.{key} 가 비었다")

        transform = entry.get("transform")
        if transform is not None:
            if not isinstance(transform, dict) or set(transform) != set(_TRANSFORM_FIELDS):
                raise fail(f"{at}.transform 은 {list(_TRANSFORM_FIELDS)} 다")
            if transform["id"] not in TRANSFORMS:
                raise fail(f"{at}.transform.id 는 모르는 transform 이다: {transform['id']!r}")
            _check_input(f"{at}.transform.input", transform["input"], needs, outputs, False, fail)

        _check_input(f"{at}.input", entry.get("input"), needs, outputs, transform is not None, fail)

        if not command:
            declared = entry.get("outputs", {})
            if not isinstance(declared, dict):
                raise fail(f"{at}.outputs 가 dict 가 아니다")
            for type_id, reading in declared.items():
                _check_reading(f"{at}.outputs.{type_id}", reading, fail)
            outputs[step_id] = declared

    if mentions_argument(workflow) != execution["spoken_needed"]:
        raise fail("spoken_needed 가 workflow 의 발화 인자 참조와 어긋난다")


def _check_context(at: str, declaration, fail) -> None:
    """context_needs 의 선언 하나. {from: context.<경로>, fields?: {칸: 경로}}."""
    if not isinstance(declaration, dict) or "from" not in declaration:
        raise fail(f"{at} 에 from 이 없다")
    unknown = [key for key in declaration if key not in _CONTEXT_FIELDS]
    if unknown:
        raise fail(f"{at} 에 모르는 칸 {unknown}")
    origin = declaration["from"]
    if not isinstance(origin, str) or not origin.startswith(CONTEXT_SOURCE) or not _RAW_PATH.fullmatch(origin):
        raise fail(f"{at}.from 이 context.<경로> 가 아니다: {origin!r}")
    if "fields" in declaration:
        _check_fields(f"{at}.fields", declaration["fields"], fail)


def _check_reading(at: str, reading, fail) -> None:
    """outputs 의 한 줄. {value: 경로} 또는 {fields: {칸: 경로}}."""
    if not isinstance(reading, dict) or len(reading) != 1:
        raise fail(f"{at} 는 value 와 fields 중 하나다")
    if "value" in reading:
        if not isinstance(reading["value"], str) or not _RAW_PATH.fullmatch(reading["value"]):
            raise fail(f"{at}.value 가 응답 안의 경로가 아니다")
    elif "fields" in reading:
        _check_fields(f"{at}.fields", reading["fields"], fail)
    else:
        raise fail(f"{at} 는 value 와 fields 중 하나다")


def _check_fields(at: str, fields, fail) -> None:
    """칸 -> 경로 한 벌."""
    if not isinstance(fields, dict) or not fields:
        raise fail(f"{at} 가 비었거나 dict 가 아니다")
    for name, path in fields.items():
        if not isinstance(name, str) or not _FIELD_NAME.fullmatch(name):
            raise fail(f"{at}: 칸 이름이 한 마디가 아니다: {name!r}")
        if not isinstance(path, str) or not _RAW_PATH.fullmatch(path):
            raise fail(f"{at}.{name} 가 경로가 아니다: {path!r}")


def _check_input(at: str, fields, needs: dict, outputs: dict, has_transform: bool, fail) -> None:
    """input 한 벌. 칸마다 _check_value."""
    if not isinstance(fields, dict):
        raise fail(f"{at} 가 dict 가 아니다")
    for field, expression in fields.items():
        _check_value(f"{at}.{field}", expression, needs, outputs, has_transform, fail)


def _check_value(at: str, expression, needs: dict, outputs: dict, has_transform: bool, fail, in_list: bool = False) -> None:
    """input 의 값 하나가 모듈 설명에 적은 꼴인지."""
    if isinstance(expression, list) and not in_list:
        for item in expression:
            _check_value(at, item, needs, outputs, has_transform, fail, in_list=True)
        return
    if not isinstance(expression, dict):
        raise fail(f"{at}: 모르는 꼴 {expression!r}")

    if "value" in expression:
        if set(expression) != {"value"}:
            raise fail(f"{at}: value 에 다른 칸을 두지 않는다")
        return

    origin = expression.get("from")
    if not isinstance(origin, str):
        raise fail(f"{at}: value 도 from 도 아니다")
    extra = set(expression) - {"from"}
    head, *rest = origin.split(".")

    if origin == SPOKEN_ARGUMENT:
        if extra and (in_list or len(extra) != 1 or not extra <= set(_CONDITIONS)
                      or not isinstance(expression[next(iter(extra))], str)):
            raise fail(f"{at}: 발화 인자에 붙는 것은 조건 하나다")
        return
    if origin.startswith(SPOKEN_SOURCE):
        if "default" not in expression or not extra <= {"default", "map"}:
            raise fail(f"{at}: {origin} 에는 default 가 있고 map 만 더 붙는다")
        mapping = expression.get("map")
        if mapping is not None and (not isinstance(mapping, dict) or expression["default"] not in mapping):
            raise fail(f"{at}: default 가 map 의 key 가 아니다")
        return
    if extra:
        raise fail(f"{at}: {origin} 에는 from 하나만 둔다")

    if origin.startswith(RUNTIME_NOW + "."):
        try:
            now_field(origin, None)
        except ValueError as error:
            raise fail(f"{at}: {error}") from None
        return
    if head == "context":
        declaration = needs.get(rest[0]) if rest else None
        if declaration is None:
            raise fail(f"{at}: context_needs 에 선언 안 된 화면 값 {origin}")
        _check_field(at, origin, declaration.get("fields"), rest[1:], fail)
        return
    if head == TRANSFORM:
        if not has_transform or in_list or len(rest) != 2:
            raise fail(f"{at}: {origin} 은 transform 이 있는 단계의 칸 하나로만 받는다")
        return
    if _STEP_ID.fullmatch(head):
        if head not in outputs:
            raise fail(f"{at}: {head} 는 이 단계보다 앞선 도구 단계가 아니다")
        reading = outputs[head].get(rest[0]) if rest else None
        if reading is None:
            raise fail(f"{at}: {head}.outputs 에 {rest[0] if rest else '타입'} 이 없다")
        _check_field(at, origin, reading.get("fields"), rest[1:], fail)
        return
    raise fail(f"{at}: 모르는 기호 {origin}")


def _check_field(at: str, origin: str, fields, rest: list[str], fail) -> None:
    """참조 뒤 칸이 선언과 맞는지. 칸이 있는 값은 칸 하나로, 없는 값은 통째로만."""
    if fields is None:
        if rest:
            raise fail(f"{at}: {origin} 는 칸이 없는 값이다")
        return
    if len(rest) != 1 or rest[0] not in fields:
        raise fail(f"{at}: {origin} 의 칸이 선언에 없다")


# ── 요청 하나를 KRRI native workflow 로 ─────────────────────────────


def absent_context(execution: dict, context: dict | None) -> list[str]:
    """이 recipe 가 받아야 하는데 지금 화면 문맥이 안 준 시작 노드.

    입력  execution · KRRI_ASAP 화면이 보낸 context. 없거나 dict 가 아니면 빈 것으로 봄
    출력  노드 id 목록. context_needs 에 적힌 차례
    규칙  칸이 있고 비어 있지 않아야 준 것으로 셈. selectedLocation 이 null 로 오는 것이
          KRRI_ASAP 의 평상시 모양임(우클릭을 안 했을 때)
    제약  값이 좌표로 쓸 만한지 여기서 보지 않는다.
          범위를 재는 것은 KRRI 실행기의 _parse_lon_lat 이고, 여기가 또 재면
          두 곳이 다른 기준을 갖게 됨
    """
    absent = []
    for start, declaration in execution["context_needs"].items():
        value = context if isinstance(context, dict) else None
        for key in declaration["from"][len(CONTEXT_SOURCE):].split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if value in (None, "", [], {}):
            absent.append(start)
    return absent


def materialize(recipe_id: str, spoken: dict, context: dict | None = None, now: datetime.datetime | None = None) -> dict:
    """고른 recipe 하나를 이번 요청의 값으로 KRRI native workflow 로.

    입력  recipe id · 발화 해석 결과(argument 와 SPOKEN_OPTIONS 만 읽음) · 화면 문맥 ·
          부르는 순간(안 주면 지금)
    출력  {status, recipe_id, missing, workflow, nodes, commands, command_nodes, context}
          READY 가 아니면 workflow 가 None 이고 목록들이 빔
    규칙  판정 차례는 NOT_ACCEPTED · MISSING_ARGUMENT · UNWIRED · MISSING_CONTEXT ·
          NOTHING_TO_CALL · READY
          recipe 파일이 없으면 NOT_ACCEPTED. 받아들인 recipe 가 아님
          인자는 발화 해석 LLM 이 argument 로 준 것 하나뿐임. 비었는데 게시된
          execution 이 발화 인자를 쓰면 MISSING_ARGUMENT 이고 missing 은 recipe 의
          시작 노드임. 무엇을 더 말해야 하는지가 그 노드임
          발화 인자를 안 쓰는 recipe 는 인자가 없어도 감
          경로에 도구가 안 붙은 노드가 있으면 UNWIRED. 부르는 것만 부르면 반쪽 결과를
          온전한 답인 것처럼 내놓게 됨
          게시된 context_needs 가 읽는 화면 값이 안 왔으면 MISSING_CONTEXT. 없는 좌표로
          부르면 전국이 나오거나 required 가 빈 채로 도구가 거부함
          context 는 dict 가 아니면 빈 dict
    제약  파일은 있는데 execution 이 없거나 깨졌으면 status 로 삼키지 않는다.
          PlanError 가 그대로 올라감. 게시 오류라 조용히 넘기면 아무도 모름
          게시된 execution 이 없다고 온톨로지로 계획을 다시 만들지 않는다
          고른 recipe 를 다른 recipe 로 바꾸지 않는다. 못 부르면 그렇다고만 돌려줌
          사람에게 보일 문장을 만들지 않는다
    """
    document = _document(recipe_id)
    if document is None:
        return _unready(recipe_id, NOT_ACCEPTED)

    execution = document.get("execution")
    validate(execution, recipe_id)

    said = {"argument": spoken.get("argument"), **{name: spoken.get(name) for name in SPOKEN_OPTIONS}}
    if not said["argument"] and execution["spoken_needed"]:
        start = [step.get("node") for step in document.get("steps") or []][:1]
        return _unready(recipe_id, MISSING_ARGUMENT, start)

    if execution.get("unwired"):
        return _unready(recipe_id, UNWIRED, execution["unwired"])

    absent = absent_context(execution, context)
    if absent:
        return _unready(recipe_id, MISSING_CONTEXT, absent)

    if not execution["workflow"]:
        return _unready(recipe_id, NOTHING_TO_CALL)

    return {
        "status": READY,
        "recipe_id": recipe_id,
        "missing": [],
        **workflow_of(execution, said, now),
        "context": copy.deepcopy(context) if isinstance(context, dict) else {},
    }


def _unready(recipe_id: str, status: str, missing: list[str] | None = None) -> dict:
    """부를 수 없는 요청의 결과. workflow 없이 판정과 모자란 것만."""
    return {
        "status": status,
        "recipe_id": recipe_id,
        "missing": list(missing or []),
        "workflow": None,
        "nodes": [],
        "commands": [],
        "command_nodes": [],
        "context": {},
    }


def workflow_of(execution: dict, spoken: dict, now: datetime.datetime | None = None) -> dict:
    """검사를 통과한 execution 한 벌을 KRRI native workflow 로.

    입력  execution · 발화 값({argument, 이름 있는 값...}) · 부르는 순간(안 주면 지금)
    출력  workflow  {action: call_mcp_workflow, steps}. steps 는 KRRI 실행기의 intent["steps"] 그대로
          nodes  steps 와 같은 길이. steps[i] 를 만든 노드 id
          commands  도구를 안 부르고 곧장 내는 지도 명령
          command_nodes  commands 와 같은 길이
    규칙  workflow 차례 그대로 step · 명령을 냄. step id · server_id · tool 은 게시된 것 그대로
          부르는 순간은 계획 하나에 한 번만 읽음
          실행 전제(인자 · 화면 값 · 배선)는 안 봄. materialize 가 먼저 봄
    제약  execution 을 바꾸지 않는다. native 표현은 새 dict 에만 적음
    """
    # 계획 하나에 한 번만 읽는다. 단계마다 읽으면 자정 언저리에서 date 와
    # time 이 서로 다른 날을 가리킬 수 있다.
    now = now or datetime.datetime.now(RUNTIME_ZONE)

    steps: list[dict] = []
    nodes: list[str] = []
    commands: list[dict] = []
    command_nodes: list[str] = []

    for entry in execution["workflow"]:
        filled, adapter = bind_input(entry, execution, spoken, now)

        if "command" in entry:
            commands.append({"op": entry["command"], "args": filled})
            command_nodes.append(entry["node"])
            continue

        step = {"id": entry["id"], "server_id": entry["server_id"], "tool": entry["tool"], "input": filled}
        if adapter:
            step["inputAdapter"] = adapter
        steps.append(step)
        nodes.append(entry["node"])

    return {
        "workflow": {"action": WORKFLOW_ACTION, "steps": steps},
        "nodes": nodes,
        "commands": commands,
        "command_nodes": command_nodes,
    }


def bind_input(entry: dict, execution: dict, spoken: dict, now: datetime.datetime) -> tuple[dict, str | None]:
    """workflow 항목 하나의 native input 과 걸 inputAdapter.

    입력  workflow 항목 · 그 항목이 든 execution(context_needs · workflow 를 읽음) · 발화 값 · 부르는 순간
    출력  (input, inputAdapter 이름 또는 None)
    규칙  input 차례대로 _bound 를 부르고 _OMIT 인 칸은 뺌
          transform 이 있으면 그 입력을 먼저 두고 이 항목의 나머지 칸을 이어 붙임.
          transform 이 만드는 칸(transform.<타입>.<칸>)은 inputAdapter 가 만들어 안 보냄
          중심 좌표 칸이 남았을 때만 inputAdapter 를 명시로 걺
    """
    outputs = {item["id"]: item.get("outputs") or {} for item in execution["workflow"] if "id" in item}

    def fill(fields):
        filled = {}
        for field, expression in fields.items():
            value = _bound(expression, execution, spoken, outputs, now)
            if value is not _OMIT:
                filled[field] = value
        return filled

    filled = fill(entry["input"])
    transform = entry.get("transform")
    if transform is None:
        return filled, None
    filled = {**fill(transform["input"]), **filled}
    return filled, TRANSFORM_ADAPTERS[transform["id"]] if _has_center(filled) else None


def _bound(expression, execution: dict, spoken: dict, outputs: dict, now):
    """기호 하나를 KRRI 실행기에 넘길 값으로. 이 자리에서 안 보내면 _OMIT."""
    if isinstance(expression, list):
        values = [_bound(item, execution, spoken, outputs, now) for item in expression]
        return _OMIT if any(value is _OMIT for value in values) else values

    if "value" in expression:
        return copy.deepcopy(expression["value"])

    origin = expression["from"]
    if origin == SPOKEN_ARGUMENT:
        argument = spoken.get("argument")
        text = str(argument or "")
        if "if_endswith" in expression and not text.endswith(expression["if_endswith"]):
            return _OMIT
        if "unless_endswith" in expression and text.endswith(expression["unless_endswith"]):
            return _OMIT
        return copy.deepcopy(argument)

    if origin.startswith(SPOKEN_SOURCE):
        said = spoken.get(origin[len(SPOKEN_SOURCE):])
        chosen = said if said not in (None, "", [], {}) else expression["default"]
        mapping = expression.get("map")
        if mapping is None:
            return copy.deepcopy(chosen)
        return mapping.get(chosen, mapping[expression["default"]])

    head, *rest = origin.split(".")
    if origin.startswith(RUNTIME_NOW + "."):
        return now_field(origin, now)
    if head == TRANSFORM:
        return _OMIT
    if head == "context":
        declaration = execution["context_needs"][rest[0]]
        base = f"{REFERENCE}{declaration['from']}"
        return f"{base}.{declaration['fields'][rest[1]]}" if len(rest) > 1 else base

    reading = outputs[head][rest[0]]
    path = reading["fields"][rest[1]] if len(rest) > 1 else reading["value"]
    return f"{REFERENCE}{head}.{path}"


def _has_center(tool_input: dict) -> bool:
    """point_radius_to_bbox 가 걸 중심 좌표가 input 에 남았는지.

    규칙  CENTER_KEYS 중 하나라도 있으면 참. 값이 무엇인지는 안 봄.
          ["$s1.location.0", "$s1.location.1"] 처럼 실행기가 나중에 푸는 참조라
          지금 판정할 수 없음
    """
    return any(key in tool_input for key in CENTER_KEYS)
