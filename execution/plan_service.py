"""agentic_ai 의 공식 실행 출력. 게시된 recipe 의 execution 과 요청 하나의 값을 묶은 ExecutionRequest.

**여기는 계획을 만들지 않는다.** 어느 노드를 어느 서버 · 도구로 부르고 칸마다 값이
어디서 오는지는 게시할 때 execution/step_service.compile_execution 이 온톨로지와 사람이
받아들인 노드 사슬로 정해 recipe 파일에 적어 두었다. 요청 중에는 그 블록만 읽는다.
온톨로지를 import 하지 않는다.

    Recipe.execution    게시된 정적 기호 계획. 요청과 무관하다
      spoken_needed     발화 인자를 쓰는가. 안 말했으면 부르지 않는다
      unwired           실행 수단이 없는 노드. 있으면 workflow 가 비고 부르지 않는다
      context_needs     화면에서 받아야 하는 시작 노드 -> {from: context.<경로>, fields}
      workflow          차례대로. 도구 단계 {id, node, server_id, tool, transform?, input, outputs?}
                        지도 명령 {node, command, transform?, input}

    ExecutionRequest    request() 가 만든다. 실행 계층에 넘기는 한 벌
      recipe_id         고른 recipe
      spoken            발화 해석이 뽑은 값. {argument, travel_mode, minutes, admin_level}
      context           화면이 보낸 문맥 그대로
      context_needs     게시된 것 그대로. context.<시작 노드>.<칸> 이 화면 값의 어디인지
      workflow          게시된 것 그대로

**ExecutionRequest 는 workflow 를 다시 적지 않는다.** 게시된 workflow 와 context_needs 에
이번 요청의 spoken · context 를 봉투로 붙일 뿐이다. 실제 값은 기호 안에 넣지 않는다.

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

**raw 응답의 어디를 읽을지는 agentic_ai 가 정해 내놓는 쪽에 적는다.** 앞 단계는 그 단계의
outputs(point.lon -> location.0), 화면 값은 context_needs 의 fields 다. 받는 쪽은 semantic
칸만 가리킨다. 실행 계층은 적힌 경로에서 값을 꺼낼 뿐 경로를 짐작하지 않는다.

**transform 은 선언이다.** id 와 입력만 적고 계산은 실행 계층이 id 를 보고 한다.

지금 KRRI_ASAP 은 이 계약을 직접 받지 않는다. execution/legacy_vendor.py 가 옛 입력
(steps · "$s1.location.0" · inputAdapter)으로 바꿔 vendor 실행기에 넘긴다. 그 표현은 여기
오지 않는다.
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

# 계약이 아는 transform id. 실행 계층이 이 id 를 보고 계산한다.
TRANSFORMS = ("builtin/geo.pointRadiusToBbox",)

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

# ExecutionRequest 의 칸. 차례도 이것이다.
_REQUEST_FIELDS = ("recipe_id", "spoken", "context", "context_needs", "workflow")


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


def load(recipe_id: str) -> dict | None:
    """그 recipe 의 execution 블록.

    출력  검사를 통과한 execution dict. recipe 파일이 없으면 None
    규칙  파일이 없는 것은 받아들인 recipe 가 아닌 것임. 부를 것이 없음
          파일이 있는데 execution 이 없거나 알아볼 수 없으면 PlanError
    제약  execution 이 없다고 온톨로지로 계획을 다시 만들지 않는다.
          그러면 게시한 블록과 온톨로지 중 무엇이 원천인지 다시 둘이 됨.
          블록은 registration/publish.py 가 다시 적음
    """
    path = paths.RECIPES_DIR / f"{recipe_id}.yaml"
    if not path.exists():
        return None
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    execution = document.get("execution") if isinstance(document, dict) else None
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
        raise fail("블록이 없다. registration/publish.py 로 게시한다")
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


# ── 요청 하나로 묶는다 ──────────────────────────────────────────


def absent_context(execution: dict, context: dict | None) -> list[str]:
    """이 recipe 가 받아야 하는데 지금 화면 문맥이 안 준 시작 노드.

    입력  execution · KRRI_ASAP 화면이 보낸 context. 없거나 dict 가 아니면 빈 것으로 봄
    출력  노드 id 목록. context_needs 에 적힌 차례
    규칙  칸이 있고 비어 있지 않아야 준 것으로 셈. selectedLocation 이 null 로 오는 것이
          KRRI_ASAP 의 평상시 모양임(우클릭을 안 했을 때)
    제약  값이 좌표로 쓸 만한지 여기서 보지 않는다.
          범위를 재는 것은 vendor 의 _parse_lon_lat 이고, 여기가 또 재면
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


def request(recipe_id: str, execution: dict, argument, options: dict | None = None, context: dict | None = None) -> dict:
    """게시된 execution 한 벌과 이번 요청의 값을 ExecutionRequest 로.

    입력  recipe id · 검사를 통과한 execution · 발화 인자 · 발화 해석이 함께 내놓은
          이름 있는 값 · 화면 문맥
    출력  _REQUEST_FIELDS 차례의 dict. validate_request 를 통과한 것
    규칙  workflow 와 context_needs 는 게시된 것을 복사만 함. 기호를 값으로 안 바꿈
          spoken 은 argument 를 먼저 두고 이름 있는 값을 받은 차례대로 붙임.
          말하지 않은 값(None)도 그대로 둠. 기본값은 기호의 default 가 앎
          context 는 dict 가 아니면 빈 dict
          spoken_needed · unwired 는 안 담음. 실행 전에 부를 수 있는지 가르는 데 쓰였고
          실행 계층이 볼 것이 아님
    제약  조건 · 부르는 순간 · 앞 단계 참조를 여기서 풀지 않는다.
          실행 계층이 받는 모양이 곧 게시된 모양이어야 경로 소유가 안 흐려짐
          게시된 블록을 바꾸지 않는다. 요청마다 같은 블록을 읽음
    """
    built = copy.deepcopy({
        "recipe_id": recipe_id,
        "spoken": {"argument": argument, **(options or {})},
        "context": context if isinstance(context, dict) else {},
        "context_needs": execution["context_needs"],
        "workflow": execution["workflow"],
    })
    validate_request(built)
    return built


def validate_request(built) -> None:
    """ExecutionRequest 한 벌이 계약의 꼴인지.

    규칙  칸은 _REQUEST_FIELDS 그대로. recipe_id 는 빈 문자열이 아님
          spoken 은 argument 가 있는 dict, context 는 dict
          context_needs · workflow 는 validate 와 같은 규칙으로 봄
    제약  실행 계층마다 다른 칸을 받으려고 넓히지 않는다
    """
    where = built.get("recipe_id") if isinstance(built, dict) else None

    def fail(message):
        return PlanError(f"{where}: request {message}")

    if not isinstance(built, dict) or tuple(built) != _REQUEST_FIELDS:
        raise fail(f"칸은 {list(_REQUEST_FIELDS)} 다")
    if not isinstance(where, str) or not where:
        raise fail("recipe_id 가 비었다")
    if not isinstance(built["spoken"], dict) or "argument" not in built["spoken"]:
        raise fail("spoken 에 argument 가 없다")
    if not isinstance(built["context"], dict):
        raise fail("context 가 dict 가 아니다")
    validate({
        "spoken_needed": mentions_argument(built["workflow"]),
        "context_needs": built["context_needs"],
        "workflow": built["workflow"],
    }, where)
