"""이 프로젝트가 무엇인지 정하는 계약. **한 subsystem 에 안 담기는 것만 둔다.**

읽는 차례가 곧 발화 하나가 지나는 길이다.

    발화
    → LLM 이 static recipe 를 **고른다** (만들지 않는다)
    → recipe = 순서 있는 온톨로지 노드 목록
    → 온톨로지 관계가 이어질 수 있는지 말한다
    → 배선(wiring)이 노드를 MCP 서버 · 도구 · 인자에 잇는다
    → vendor/Gateway 실행
    → 답 · API · 화면

여기서 지키는 것은 그 길의 이음매다.

    LLM 은 MCP 도구 순서를 만들지 않는다 — recipe 를 고른다
    recipe 는 노드만 적는다 — 서버 · 도구 · 인자를 안 가진다
    도메인은 서비스 계층을 모듈 수준에서 안 부른다

이음매의 **반대쪽 끝**은 각 subsystem 이 본다. 여기서 다시 안 본다.

    고른 것을 문맥으로 안 거른다      dev/tests/orchestrator/test_resolve_service.py
    실행 전제는 실행이 본다            dev/tests/execution/test_execute_service.py
    배선이 온톨로지 · 스키마와 맞나    dev/tests/execution/test_wiring_contract.py
    온톨로지 관계가 무엇을 뜻하나      dev/tests/ontology/test_graph.py

LLM 도 Gateway 도 부르지 않는다. 소스와 데이터 파일만 읽는다.
"""

import ast

import yaml

import paths
from ontology import graph
from orchestrator.schemas.response_schema import recipe_selection_schema

# ── LLM 은 recipe 를 고른다 ─────────────────────────────────────────


# LLM 이 채울 수 있는 칸 전부. **이 목록이 곧 「LLM 이 정하는 것」의 범위다.**
#   status · recipe_id · candidate_recipe_ids  어느 recipe 인가
#   argument                                    발화에서 그대로 떼어 온 값
#   reason                                      왜 그렇게 골랐나
# argument 는 실행 인자가 아니다 — 어느 도구의 어느 칸에 실릴지는 배선표가 정하고
# (execution/wiring.yaml 의 arg_field), LLM 은 그것을 모른다.
SELECTION_FIELDS = {"reason", "argument", "candidate_recipe_ids", "status", "recipe_id"}


def test_the_llm_is_asked_to_choose_a_recipe_not_a_tool_sequence():
    """**응답 계약에 도구 순서를 적을 칸이 없다.**

    칸이 없으면 LLM 이 도구 순서를 지어낼 자리가 구조로 없다. 칸이 하나
    생기는 순간 「무엇을 하려는가」와 「무엇을 부르는가」가 한 값에 섞이고,
    배선표가 아니라 회차마다 다른 LLM 출력이 실행을 정하게 된다.

    낱말을 찾지 않고 **칸 목록 전체를 못 박는다.** 낱말로 보면 argument 가
    걸려 멀쩡한 칸이 막히거나, steps 같은 새 칸이 낱말 목록에 없어 그냥 샌다.

    나온 값이 이 계약을 지키는지는 orchestrator 의 test_resolve_service.py
    (test_only_the_contracted_keys_survive)가 본다. 여기서는 계약 쪽을 본다.
    상한 값은 안 본다 — 모델마다 다르고 models.yaml 에서 온다.
    """
    schema = recipe_selection_schema(200)
    fields = set(schema["properties"])

    assert fields == set(schema["required"]), "required 와 properties 가 갈렸다"
    assert fields == SELECTION_FIELDS, (
        f"LLM 이 정하는 것이 달라졌다: {sorted(fields ^ SELECTION_FIELDS)}. "
        "실행을 적는 칸이면 여기서 막고, 아니면 이 목록과 위 주석을 함께 고친다"
    )


# ── recipe 는 노드 목록일 뿐이다 ────────────────────────────────────


def test_a_recipe_is_only_an_ordered_list_of_ontology_nodes():
    """**recipe 파일이 실행을 안 가진다.** 무엇으로 수행하는지는 배선표가 안다.

    recipe 에 서버 · 도구 · 인자를 적으면 진실의 원천이 둘이 된다 — 도구를
    갈아끼울 때 recipe 서른일곱 벌을 함께 고쳐야 하고, 어긋났을 때 어느 쪽이
    맞는지 알 수 없다.

    개수를 안 센다. 「전부 그렇다」가 요구사항이고 recipe 가 늘어도 그대로다.
    """
    files = sorted(paths.RECIPES_DIR.glob("recipe_*.yaml"))
    assert files, "recipe 파일이 없다 — 이 검사가 무력하다"

    nodes = set(graph.load_ontology()["nodes"])
    어긋난_것 = []
    for path in files:
        steps = yaml.safe_load(path.read_text(encoding="utf-8"))["steps"]
        for index, step in enumerate(steps):
            if set(step) != {"node"}:
                어긋난_것.append(f"{path.stem}[{index}]: 칸이 {sorted(step)} 이다")
            elif step["node"] not in nodes:
                어긋난_것.append(f"{path.stem}[{index}]: 온톨로지에 없는 노드 {step['node']}")

    assert 어긋난_것 == [], "recipe 가 노드 말고 다른 것을 적었다:\n  " + "\n  ".join(어긋난_것)


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
