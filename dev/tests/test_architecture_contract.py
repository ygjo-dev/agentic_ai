"""이 프로젝트가 무엇인지 정하는 계약. **한 subsystem 에 안 담기는 것만 둔다.**

읽는 차례가 곧 발화 하나가 지나는 길이다.

    발화
    → LLM 이 static recipe 를 **고른다** (만들지 않는다)
    → recipe = 순서 있는 온톨로지 노드 목록
    → 온톨로지 관계가 이어질 수 있는지 말한다
    → 노드의 tool 이 MCP 서버 · 도구 · 인자에 잇는다 (게시할 때 compile = Recipe.execution)
    → 요청 중에 Recipe.execution + 이번 요청의 값 = KRRI native call_mcp_workflow (materialize)
    → 지금은 legacy 다리가 vendoring 한 KRRI 실행기로 Gateway 실행
    → 답 · API · 화면

여기서 지키는 것은 그 길의 이음매다.

    LLM 은 MCP 도구 순서를 만들지 않는다 — recipe 를 고른다
    recipe 의 steps 는 사람이 받아들인 노드만 적는다 — 실행 계획은 온톨로지로 compile 해 게시한다
    요청 중에는 게시된 실행 계획만 읽는다 — 온톨로지로 계획을 다시 만들지 않는다
    KRRI native 표현은 workflow_materializer 만 만들고 vendor 를 아는 제품 코드는 legacy 다리 하나다
    도메인은 서비스 계층을 모듈 수준에서 안 부른다

이음매의 **반대쪽 끝**은 각 subsystem 이 본다. 여기서 다시 안 본다.

    고른 것을 문맥으로 안 거른다      dev/tests/orchestrator/test_resolve_service.py
    실행 전제는 실행이 본다            dev/tests/execution/test_workflow_materializer.py
    tool 이 스키마 · 권한과 맞나      dev/tests/execution/test_wiring_contract.py
    온톨로지 관계가 무엇을 뜻하나      dev/tests/ontology/test_graph.py

LLM 도 Gateway 도 부르지 않는다. 소스와 데이터 파일만 읽는다.
"""

import ast

import yaml

import paths
from llm_engine.role_config import RESOLVE, get_role_config
from ontology import graph

# ── LLM 은 recipe 를 고른다 ─────────────────────────────────────────


# LLM 이 채울 수 있는 칸 전부. **이 목록이 곧 「LLM 이 정하는 것」의 범위다.**
#   status · recipe_id · candidate_recipe_ids  어느 recipe 인가
#   argument                                    발화에서 그대로 떼어 온 값
#   travel_mode · minutes · admin_level         발화에서 떼어 온 값 중 이름이 있는 것
#   reason                                      왜 그렇게 골랐나
# argument 는 실행 인자가 아니다 — 어느 도구의 어느 칸에 실릴지는 온톨로지 노드의
# tool.parameters 가 정하고, LLM 은 그것을 모른다.
#
# travel_mode · minutes 도 같은 자리다. 사람이 말한 값을 이름을 붙여 떼어 온
# 것일 뿐이고, 그 값이 어느 도구의 어느 칸에 어떤 말로 실릴지는 tool.parameters
# 의 map 이 정한다 — 「도보」가 WALK 가 되는 것을 LLM 은 모른다.
# **도구 순서를 적을 칸은 여전히 없다.** 이 목록이 그것을 지킨다.
SELECTION_FIELDS = {
    "reason",
    "argument",
    "travel_mode",
    "minutes",
    "admin_level",
    "candidate_recipe_ids",
    "status",
    "recipe_id",
}


def test_the_llm_is_asked_to_choose_a_recipe_not_a_tool_sequence():
    """**응답 계약에 도구 순서를 적을 칸이 없다.**

    칸이 없으면 LLM 이 도구 순서를 지어낼 자리가 구조로 없다. 칸이 하나
    생기는 순간 「무엇을 하려는가」와 「무엇을 부르는가」가 한 값에 섞이고,
    배선표가 아니라 회차마다 다른 LLM 출력이 실행을 정하게 된다.

    낱말을 찾지 않고 **칸 목록 전체를 못 박는다.** 낱말로 보면 argument 가
    걸려 멀쩡한 칸이 막히거나, steps 같은 새 칸이 낱말 목록에 없어 그냥 샌다.

    나온 값이 이 계약을 지키는지는 orchestrator 의 test_resolve_service.py
    (test_only_the_contracted_keys_survive)가 본다. 여기서는 계약 쪽을 본다.
    읽는 것은 resolve 역할이 지금 가리키는 response schema 판이다. 칸의 모양
    (type · enum · 길이 상한)은 안 본다. 판을 올릴 때 바뀔 수 있는 값임.
    """
    schema = get_role_config(RESOLVE).response_schema
    fields = set(schema["properties"])

    assert fields == set(schema["required"]), "required 와 properties 가 갈렸다"
    assert fields == SELECTION_FIELDS, (
        f"LLM 이 정하는 것이 달라졌다: {sorted(fields ^ SELECTION_FIELDS)}. "
        "실행을 적는 칸이면 여기서 막고, 아니면 이 목록과 위 주석을 함께 고친다"
    )


def test_the_spoken_options_handed_to_execution_are_fields_the_llm_fills():
    """실행이 spoken.<이름> 으로 읽는 이름 있는 값은 resolve 응답 schema 에 실제로 있는 칸이다.

    칸의 모양은 schema 가 갖고 실행은 이름만 적는다. 이름이 schema 와 갈리면 workflow
    에 늘 기본값이 가는데, 말하지 않은 값도 기본값이라 표에서 안 보인다.
    """
    from execution.workflow_materializer import SPOKEN_OPTIONS

    properties = get_role_config(RESOLVE).response_schema["properties"]

    assert SPOKEN_OPTIONS, "이름 있는 값이 비면 이 검사가 무력하다"
    assert [name for name in SPOKEN_OPTIONS if name not in properties] == [], (
        "실행이 받아 가는 이름이 resolve 응답 schema 에 없다"
    )


# ── recipe 는 사람이 받아들인 노드 목록과 게시된 실행 계획이다 ────────


def test_a_recipe_is_an_accepted_node_list_with_its_plan_compiled_and_published():
    """**사람이 적는 것은 노드 목록과 example 뿐이다.** 실행 계획(execution)은 게시가 붙인다.

    execution 은 온톨로지 노드의 tool 과 사람이 받아들인 steps 로 compile 한 것이라
    원천은 여전히 온톨로지다. 사람이 recipe 에 서버 · 도구 · 인자를 손으로 적으면 진실의
    원천이 둘이 된다 — 도구를 갈아끼울 때 recipe 를 전부 함께 고쳐야 하고, 어긋났을 때
    어느 쪽이 맞는지 알 수 없다. 게시된 블록이 compile 과 같은지는
    dev/tests/execution/test_published_execution.py 가 본다.

    steps 와 execution 말고 둘 수 있는 칸은 example 하나다. 사람이 그 recipe 를
    받아들이며 적은 발화 예시라 실행이 아니다.

    개수를 안 센다. 「전부 그렇다」가 요구사항이고 recipe 가 늘어도 그대로다.
    """
    files = sorted(paths.RECIPES_DIR.glob("recipe_*.yaml"))
    assert files, "recipe 파일이 없다 — 이 검사가 무력하다"

    nodes = set(graph.load_ontology()["nodes"])
    어긋난_것 = []
    for path in files:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not set(document) <= {"steps", "example", "execution"} or "execution" not in document:
            어긋난_것.append(f"{path.stem}: 칸이 {sorted(document)} 이다")
        steps = document["steps"]
        for index, step in enumerate(steps):
            if set(step) != {"node"}:
                어긋난_것.append(f"{path.stem}[{index}]: 칸이 {sorted(step)} 이다")
            elif step["node"] not in nodes:
                어긋난_것.append(f"{path.stem}[{index}]: 온톨로지에 없는 노드 {step['node']}")

    assert 어긋난_것 == [], "recipe 가 노드 · example · 게시된 execution 말고 다른 것을 적었다:\n  " + "\n  ".join(어긋난_것)


# ── 요청 중에는 게시된 계획만 읽는다 ────────────────────────────────

# 요청 중에 고른 recipe 를 실행하는 모듈.
RUNTIME_MODULES = ("app/api/main.py", "execution/workflow_materializer.py", "execution/legacy_vendor.py")

# 게시할 때만 부르는 compile 모듈의 이름.
BUILDER = "recipe_execution_builder"


def imported_names(tree):
    """모듈 안 어디서든(함수 안까지) import 하는 이름. "registration.recipe_execution_builder" 꼴."""
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names += [f"{node.module}.{alias.name}" for alias in node.names]
    return names


def test_the_runtime_executes_the_published_plan_and_never_plans_from_the_ontology():
    """**고른 recipe 를 실행하려고 온톨로지를 다시 훑어 계획을 만들지 않는다.**

    요청 중에 계획을 다시 만들면 사람이 받아들여 게시한 실행 계획과 온톨로지 중 무엇이
    실행을 정하는지 둘이 된다. 그래서 요청 중의 모듈은 compile 하는 recipe_execution_builder 를
    import 하지 않는다. 게시된 블록을 workflow 로 만드는 workflow_materializer 와 그것을 부르는
    legacy_vendor 는 온톨로지도 게시도 import 하지 않고, 창구(main)는 온톨로지를 import 하지 않는다.

    고른 recipe 가 없는 답에 적을 온톨로지 이름은 resolve_service 가 모은다. 그것은
    계획이 아니라 여기서 막지 않는다. 계획을 안 지나는지는
    dev/tests/app/api/test_common_entry.py 가 온톨로지 읽기를 막고 돌려 본다.
    """
    from paths import REPO_ROOT

    offenders = []
    for relative in RUNTIME_MODULES:
        tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
        names = imported_names(tree)
        offenders += [f"{relative} -> {name}" for name in names if BUILDER in name]
        offenders += [
            f"{relative} -> {BUILDER}.{node.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == BUILDER
        ]
        forbidden = ("ontology", "registration") if relative.startswith("execution/") else ("ontology",)
        offenders += [f"{relative} -> {name}" for name in names if name.split(".")[0] in forbidden]

    assert offenders == [], "요청 중의 실행이 계획을 다시 만들 수 있다:\n  " + "\n  ".join(offenders)


# ── native 표현은 materializer 가, vendor 는 legacy 다리가 ─────────────

# KRRI native workflow 에만 있는 표현과 옛 vendor 답 지시. 코드 속 문자열(docstring · 주석 제외)로 판다.
NATIVE_FORMS = ("inputAdapter", "point_radius_to_bbox", "call_mcp_workflow", "$s", "$context")
LEGACY_ANSWER_FORM = "answer_instruction"

# vendor 를 아는 유일한 제품 모듈.
LEGACY_ADAPTER = "execution/legacy_vendor.py"

# KRRI native 표현을 적는 유일한 제품 모듈.
MATERIALIZER = "execution/workflow_materializer.py"


def code_strings(tree):
    """docstring 을 뺀 문자열 상수."""
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def test_only_the_materializer_writes_native_forms_and_only_the_legacy_bridge_knows_the_vendor():
    """**KRRI native workflow 는 workflow_materializer 가 만들고, vendor 는 legacy 다리 뒤에만 있다.**

    vendor 를 여러 곳에서 부르면 KRRI_ASAP 실행기에 workflow 를 직접 넘기게 됐을 때 걷어낼
    자리를 못 찾는다. "$s1.location.0" · inputAdapter 를 compile · 다리 · 창구가 적기 시작하면
    raw 참조와 어댑터 결정이 여러 곳에 흩어지고, 게시된 Recipe.execution 이 semantic IR 로
    남지 않는다. 옛 vendor 답 지시(answer_instruction)는 어디에도 되살리지 않는다.

    import 문과 코드 속 문자열을 판다. 제품 폴더(도메인 · 서비스) 전부를 훑는다.
    """
    from paths import REPO_ROOT

    importers, leaks, scanned = [], [], 0
    for folder in DOMAIN_DIRS + SERVICE_PACKAGES:
        for path in sorted((REPO_ROOT / folder).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            scanned += 1
            relative = path.relative_to(REPO_ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if relative != LEGACY_ADAPTER:
                importers += [f"{relative} -> {name}" for name in imported_names(tree) if name.startswith("vendor_to_be_deleted")]
            if folder in ("execution", "registration"):
                forms = (LEGACY_ANSWER_FORM,) if relative == MATERIALIZER else NATIVE_FORMS + (LEGACY_ANSWER_FORM,)
                leaks += [
                    f"{relative}:{node.lineno} -> {node.value!r}"
                    for node in code_strings(tree)
                    if any(form in node.value for form in forms)
                ]

    assert scanned and (REPO_ROOT / LEGACY_ADAPTER).is_file() and (REPO_ROOT / MATERIALIZER).is_file(), (
        "훑은 파일이 없거나 다리 · materializer 가 없다 — 이 검사가 무력하다"
    )
    assert importers == [], "legacy 다리 밖에서 vendor 를 부른다:\n  " + "\n  ".join(importers)
    assert leaks == [], "KRRI native 표현을 materializer 밖 코드가 적는다:\n  " + "\n  ".join(leaks)


# ── 도메인이 서비스를 안 부른다 ─────────────────────────────────────
#
# CLAUDE.md 「폴더가 말하는 여섯 갈래」에서 그대로 온다.
# 이름이 또 갈리면 아래 exists 확인이 먼저 빨간불이 된다 — 조용히 통과하지 않는다.
DOMAIN_DIRS = ("ontology", "registration", "orchestrator", "execution",
               "llm_engine", "workflows")
SERVICE_PACKAGES = ("app",)


def module_level_statements(tree):
    """함수 · 클래스 몸통 안으로는 안 들어간다. try · if 는 들어간다.

    함수 안의 늦은 import 는 순환을 푸는 흔한 손이라 여기서 안 본다.
    막으려는 것은 **모듈을 읽는 순간** 서비스 계층이 딸려 오는 것이다.
    """
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        stack.extend(c for c in ast.iter_child_nodes(node) if isinstance(c, ast.stmt))


def imported_roots(node):
    """import 문 하나가 부르는 최상위 패키지 이름들. import 문이 아니면 빈 것."""
    if isinstance(node, ast.Import):
        return [alias.name.split(".", 1)[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0:
        return [(node.module or "").split(".", 1)[0]]
    return []


def test_the_domain_does_not_import_the_service_layer_at_module_level():
    """도메인이 서비스를 모듈 수준에서 부르면 서비스를 갈아 끼울 수 없다.

    낱말을 찾지 않고 **import 문을 판다.** 옛 몸통은 `ontology/registry.py`
    머리에 "demo" 라는 글자가 있는지만 봤는데, 계층 이름이 `app` 으로 갈리자
    그 assert 는 늘 참이 되어 아무것도 안 지키게 됐다 — 조용히 죽었다.
    여기서는 이름이 갈리면 아래 exists 확인이 먼저 깨지므로 그 일이 안 난다.
    """
    from paths import REPO_ROOT

    for name in DOMAIN_DIRS + SERVICE_PACKAGES:
        assert (REPO_ROOT / name).is_dir(), (
            f"{name}/ 이 없다. 계층 이름이 갈렸으면 이 시험의 목록부터 고친다"
        )

    offenders = []
    scanned = 0
    for folder in DOMAIN_DIRS:
        for path in sorted((REPO_ROOT / folder).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            scanned += 1
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in module_level_statements(tree):
                for root in imported_roots(node):
                    if root in SERVICE_PACKAGES:
                        rel = path.relative_to(REPO_ROOT)
                        offenders.append(f"{rel}:{node.lineno} -> {root}")

    assert scanned, "도메인에서 판 파일이 하나도 없다 — 경로가 어긋난 것이다"
    assert not offenders, "도메인이 서비스를 모듈 수준에서 부른다:\n" + "\n".join(offenders)


# ── 발화에서 인자를 뽑는 곳은 하나다 ────────────────────────────────


def test_the_utterance_argument_is_extracted_only_by_the_llm():
    """**실행 경로가 발화 문자열을 다시 훑어 인자를 만들지 않는다.**

    인자는 발화 해석 LLM 이 argument 로 내놓는 것 하나뿐이다. 파이썬 정규식
    대비책이 있으면 같은 발화의 인자가 두 곳에서 나오고, 어느 값이 어디서
    왔는지 표에서 안 갈린다. 실제로 그 대비책은 "충북대 근처" 를 못 잡으면서
    "지금 화면에 든 읍면동 경계" 의 「읍면동」을 장소로 집었다.

    낱말을 찾지 않고 **정규식 리터럴을 판다.** 이름을 바꿔 되살리는 것을
    막으려는 것이라 함수 이름으로 보면 안 걸린다. 한글 음절 범위를 담은
    패턴이 실행 계층에 새로 생기면 여기가 먼저 빨개진다.
    """
    from paths import REPO_ROOT

    offenders = []
    scanned = 0
    for path in sorted((REPO_ROOT / "execution").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        scanned += 1
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "가-힣" in node.value:
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}:{node.lineno} -> {node.value!r}")

    assert scanned, "execution 에서 판 파일이 하나도 없다 — 경로가 어긋난 것이다"
    assert not offenders, (
        "발화에서 인자를 뽑는 정규식이 실행 계층에 있다:\n" + "\n".join(offenders)
    )
