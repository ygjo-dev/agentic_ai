"""노드 등록. 온톨로지 · recipe · menu 를 갱신.

온톨로지 읽기와 쓰기는 store 에게 맡긴다. 이 파일은 ontology.yaml 을 직접
열지 않는다 — 저장소가 그래프DB 로 바뀌어도 등록 규칙은 그대로여야 한다.
recipe 와 menu 는 아직 store 가 맡는 자산이 아니라 여기서 직접 쓴다.
"""

import re
import shutil

import paths
from ontology import store
from orchestrator.route_resolver import resolve_route

# 새 노드가 속할 대상을 가리키는 관계 이름. 지금은 이것 하나뿐이다.
#
# "A 는 B 에 관한 것이다" — Dublin Core 의 dcterms:subject 와 같은 뜻이다.
# is-a(한 종류다) 도 part-of(부분이다) 도 아니다. 궤도 검측 이미지는 궤도의
# 한 종류도 부분도 아니고, 궤도에 관한 것이다.
ABOUT = "about"

FUNCTION, GROUP = "function", "group"


def group_ids(nodes: dict) -> list[str]:
    """지금 있는 group 노드 id. LLM 이 고를 수 있는 선택지 전부다."""
    return [nid for nid, node in nodes.items() if node.get("kind") == GROUP]


def functions(nodes: dict) -> dict:
    """실행할 수 있는 노드만. group 은 recipe 에 들어가지 않는다."""
    return {nid: node for nid, node in nodes.items() if node.get("kind") != GROUP}


class DuplicateNode(ValueError):
    """이미 있는 노드 id 다."""


class UnknownInterface(ValueError):
    """온톨로지에 선언되지 않은 인터페이스다."""


class UnknownGroup(ValueError):
    """온톨로지에 없는 group 노드 id 다."""


def add_node(node_id: str, node: dict, path=None) -> None:
    """온톨로지에 노드를 추가한다.

    여기서 보는 것은 등록 규칙뿐이다 — 중복인가, 아는 인터페이스인가.
    파일에 어떻게 적히는지는 store 가 안다.
    """
    ontology = store.read(path)

    if node_id in ontology["nodes"]:
        raise DuplicateNode(f"이미 있는 노드다: {node_id}")

    interfaces = set(ontology["interfaces"])
    for name in [*node["inputs"], *node["outputs"]]:
        if name not in interfaces:
            raise UnknownInterface(
                f"온톨로지에 없는 인터페이스다: {name}\n"
                f"  쓸 수 있는 것 : {sorted(interfaces)}"
            )

    store.append_node(node_id, node, path)


# LLM 응답 구조(json). node_id 형식은 코드에서 다시 검증한다.
NODE_REGISTRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "node_id": {"type": "string"},
        # 속할 group 노드 id. 어느 대상에도 매이지 않으면 빈 문자열.
        "group": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["node_id", "group", "reason"],
}

NODE_ID_PATTERN = re.compile(r"^[a-z]+(_[a-z]+)*$")


class InvalidInference(ValueError):
    """LLM 이 쓸 수 없는 값을 돌려줬다."""


def infer_node(form: dict, llm_client, path=None) -> dict:
    """사람이 쓴 노드 정보를 보고 LLM 이 node_id 와 속할 group 을 정한다.

    group 은 **닫힌 목록에서 고르는 것**이다. 예전에는 자유 문자열(subject 값)을
    쓰게 했는데, "궤도" 대신 "선로" 라고 쓰면 아무와도 안 이어졌다. 지금은
    존재하는 group 노드 id 중 하나이거나 빈 문자열이다.

    어느 대상에도 매이지 않는 범용 노드(형식만 바꾸는 생성 노드 등)는 빈 문자열이다.
    억지로 고르는 것보다 낫다.

    Raises:
        InvalidInference: 형식에 맞지 않거나 쓸 수 없는 값을 돌려줬다.
        RouteResolutionError: 응답이 JSON 이 아니거나 필수 key 가 없다.
    """
    nodes = store.nodes(path)
    choices = group_ids(nodes)

    result = resolve_route(
        prompt=paths.NODE_REGISTRATION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={
            "existing_nodes": _describe(nodes, _group_of(store.edges(path))),
            "new_node": _describe_form(form),
            "groups": _describe_groups(nodes, choices),
        },
        response_schema=NODE_REGISTRATION_SCHEMA,
        llm_client=llm_client,
    )

    node_id = result["node_id"]
    if not isinstance(node_id, str) or not NODE_ID_PATTERN.match(node_id):
        raise InvalidInference(
            f"노드 id 형식이 맞지 않다: {node_id!r}\n"
            "  소문자 영문과 언더스코어만 쓴다."
        )
    if node_id in nodes:
        raise InvalidInference(f"이미 있는 노드 id 다: {node_id}")

    group = result["group"]
    if not isinstance(group, str):
        raise InvalidInference(f"group 은 문자열이어야 한다: {group!r}")

    # 빈 문자열은 "어느 대상에도 안 속한다" 는 뜻이라 허용한다.
    if group and group not in choices:
        raise InvalidInference(
            f"온톨로지에 없는 group 이다: {group!r}\n"
            f"  고를 수 있는 것 : {choices}"
        )

    return result


def _group_of(edges: list[dict]) -> dict[str, str]:
    """기능 노드 -> 속한 group id. 프롬프트에 보여줄 용도다."""
    return {edge["from"]: edge["to"] for edge in edges if edge.get("type") == ABOUT}


def _describe(nodes: dict, belongs: dict[str, str]) -> str:
    """기존 기능 노드를 프롬프트에 넣을 형태로.

    어느 group 에 속하는지가 핵심이라 반드시 넣는다 — LLM 이 비슷한 노드를
    보고 고른다. group 노드 자체는 여기 넣지 않는다. 선택지는 따로 보여준다.
    """
    lines = []
    for node_id, node in functions(nodes).items():
        lines.append(
            f"- {node_id}\n"
            f"    이름 : {node['name']}\n"
            f"    설명 : {node['description']}\n"
            f"    입력 : {node['inputs'] or '없음'} -> 출력 : {node['outputs']}\n"
            f"    속한 대상 : {belongs.get(node_id) or '(없음)'}"
        )
    return "\n".join(lines)


def _describe_groups(nodes: dict, choices: list[str]) -> str:
    """고를 수 있는 group 목록. id 와 이름을 함께 보여준다.

    id 만 보여주면 LLM 이 뜻을 모르고, 이름만 보여주면 무엇을 적어야 할지
    모른다. 적어야 하는 것은 id 다.
    """
    return "\n".join(
        f"- {group_id}  ({nodes[group_id]['name']} — {nodes[group_id]['description']})"
        for group_id in choices
    )


def _describe_form(form: dict) -> str:
    return (
        f"    이름 : {form['name']}\n"
        f"    설명 : {form['description']}\n"
        f"    입력 : {form['inputs'] or '없음'} -> 출력 : {form['outputs']}"
    )


MAX_STEPS = 3


def new_recipes_for(node_id: str, nodes: dict) -> list[list[str]]:
    """새 노드를 지나는 경로만 만든다. 파일은 쓰지 않는다.

    기존 노드끼리의 조합은 이미 recipe 로 있으니 다시 만들면 중복이다.
    연결 규칙은 ontology/graph.py 의 solid_edges 와 같다 —
    앞 노드 outputs 와 뒤 노드 inputs 에 교집합이 있으면 이어진다.
    """

    # group 은 실행 대상이 아니다. 걸러내지 않으면 inputs 가 없어 KeyError 가
    # 나거나, .get() 으로 넘기면 "입력이 없는 노드" 로 보여 recipe 시작점이 된다.
    # 그러면 "궤도 -> ???" 같은 실행 불가능한 recipe 가 만들어진다.
    runnable = functions(nodes)

    def connectable(prev_id: str, next_id: str) -> bool:
        return bool(
            set(runnable[prev_id]["outputs"]) & set(runnable[next_id]["inputs"])
        )

    if node_id not in runnable:
        return []

    starts = [nid for nid, node in runnable.items() if node["inputs"] == []]

    chains = [[start] for start in starts]
    found = []
    for _ in range(MAX_STEPS):
        found += [chain for chain in chains if node_id in chain]
        chains = [
            [*chain, nxt]
            for chain in chains
            if len(chain) < MAX_STEPS
            for nxt in runnable
            if nxt not in chain and connectable(chain[-1], nxt)
        ]

    return found


def append_recipes(chains: list[list[str]], nodes: dict, directory=None) -> list[str]:
    """경로를 recipe 파일로 쓰고 만들어진 id 를 돌려준다.

    기존 번호는 건드리지 않고 가장 큰 번호 다음부터 이어 붙인다 —
    menu 와 frontend 의 SAMPLES 가 그 번호를 가리키고 있다.
    """
    directory = directory or paths.RECIPES_DIR

    last = max(
        (int(path.stem.split("_")[1]) for path in directory.glob("recipe_*.yaml")),
        default=0,
    )

    created = []
    for offset, chain in enumerate(chains, start=1):
        recipe_id = f"recipe_{last + offset:03d}"
        body = "steps:\n\n" + "\n\n".join(_step_block(nodes[n], n) for n in chain) + "\n"
        (directory / f"{recipe_id}.yaml").write_text(body, encoding="utf-8", newline="\n")
        created.append(recipe_id)

    return created


def _step_block(node: dict, node_id: str) -> str:
    """recipe 파일의 step 한 덩어리. 기존 28개와 같은 형식."""
    lines = [f"  - node: {node_id}"]

    if node["inputs"]:
        lines.append("    inputs:")
        lines += [f"      - {value}" for value in node["inputs"]]
    else:
        lines.append("    inputs: []")

    lines.append("    outputs:")
    lines += [f"      - {value}" for value in node["outputs"]]

    return "\n".join(lines)


# menu.yaml 크기 상한. 넘으면 num_ctx(8192) 를 넘겨 LLM 이 타임아웃한다.
# tests/context_loading 의 상한과 같은 값이다.
# 프로덕션에서 부르는 곳은 없다. 등록 뒤 menu 가 이 선을 넘지 않는지
# tests/node_registration/test_append_menu.py 가 보는 기준값이라 남긴다.
MENU_BUDGET = 6000


def _to_connective(sentence: str) -> str:
    """종결형을 연결형으로. "분석한다" -> "분석하고", "불러온다" -> "불러와".

    한글 "~ㄴ다" 는 어간 끝 음절에 종성 ㄴ 이 붙은 형태다. 그 종성을 떼고
    "고" 를 붙이면 연결형이 된다. 불러오기는 기존 menu 가 쓰는 "불러와" 를 따른다.
    """
    if sentence.endswith("불러온다"):
        return sentence[: -len("불러온다")] + "불러와"

    if not sentence.endswith("다") or len(sentence) < 2:
        return sentence + "하고"

    stem_end = sentence[-2]
    code = ord(stem_end) - 0xAC00
    if 0 <= code < 11172 and code % 28:  # 종성이 있는 한글 음절
        stem_end = chr(ord(stem_end) - code % 28)  # 종성 제거 : 한 -> 하

    return sentence[:-2] + stem_end + "고"


def function_for(chain: list[str], nodes: dict) -> str:
    """recipe 가 하는 일 한 문장. LLM 이 recipe 를 고르는 유일한 근거다.

    각 노드의 description 을 이어 붙이되 문장이 어색하지 않게 다듬는다.
    기존 문장들과 명확히 구분되어야 한다.
    """
    descriptions = [nodes[node_id]["description"].rstrip(".") for node_id in chain]

    if len(descriptions) == 1:
        return descriptions[0] + "."

    # 마지막만 종결형으로 두고 앞은 모두 연결형으로 잇는다.
    clauses = [_to_connective(text) for text in descriptions[:-1]]

    return " ".join([*clauses, descriptions[-1]]) + "."


def append_menu(
    recipe_ids: list[str],
    chains: list[list[str]],
    nodes: dict,
    yaml_path=None,
    md_path=None,
) -> None:
    """menu.yaml 과 menu.md 에 새 recipe 를 추가한다.

    기존 항목은 텍스트째로 두고 뒤에 이어 붙인다 — function 문장이 한 글자라도
    바뀌면 이미 검증한 발화들이 다른 recipe 로 갈 수 있다.
    """
    yaml_path = yaml_path or paths.MENU_YAML_PATH
    md_path = md_path or paths.MENU_MD_PATH

    functions = {
        recipe_id: function_for(chain, nodes)
        for recipe_id, chain in zip(recipe_ids, chains)
    }

    # ---------------------------------------------------------- menu.yaml
    blocks = [
        f"  {recipe_id}:\n    function: {sentence}\n"
        for recipe_id, sentence in functions.items()
    ]
    yaml_path.write_text(
        yaml_path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + "\n".join(blocks),
        encoding="utf-8",
        newline="\n",
    )

    # ---------------------------------------------------------- menu.md
    # 목차 표 끝에 행을 넣고, 본문 섹션은 문서 끝에 붙인다.
    md = md_path.read_text(encoding="utf-8")
    rows = "".join(
        f"| {recipe_id} | {sentence} |\n" for recipe_id, sentence in functions.items()
    )
    marker = "\n\n---\n\n# Recipe "
    head, sep, tail = md.partition(marker)
    md = head.rstrip("\n") + "\n" + rows.rstrip("\n") + sep + tail

    sections = "".join(
        f"\n\n---\n\n# Recipe {recipe_id.split('_')[1]}\n\n## 기능\n\n{sentence}"
        for recipe_id, sentence in functions.items()
    )
    md_path.write_text(md.rstrip("\n") + sections + "\n", encoding="utf-8", newline="\n")


def register_node(form: dict, llm_client) -> dict:
    """노드 등록 전체. LLM 판단 -> 온톨로지 -> recipe -> menu.

    앞 단계가 실패하면 뒤는 실행되지 않는다. 온톨로지에 못 넣은 노드로
    recipe 를 만들면 존재하지 않는 노드를 가리키게 된다.

    group 을 골랐으면 노드를 쓴 **뒤에** 관계를 잇는다. 순서가 바뀌면 아직
    없는 노드를 가리키는 edge 가 파일에 남는다.
    """
    inferred = infer_node(form, llm_client=llm_client)
    node_id = inferred["node_id"]

    node = {
        "kind": FUNCTION,
        "name": form["name"],
        "description": form["description"],
        "inputs": form["inputs"],
        "outputs": form["outputs"],
    }
    add_node(node_id, node)

    if inferred["group"]:
        store.append_edge(node_id, inferred["group"], ABOUT)

    nodes = store.nodes()
    chains = new_recipes_for(node_id, nodes)
    recipe_ids = append_recipes(chains, nodes)
    append_menu(recipe_ids, chains, nodes)

    return {**inferred, "node": node, "recipe_ids": recipe_ids, "chains": chains}


def reset_to_init() -> None:
    """_init 사본을 작업 파일로 되돌린다.

    등록으로 늘어난 recipe 도 사라져야 하므로 디렉터리를 통째로 갈아끼운다.
    _init 사본 자체는 절대 건드리지 않는다 — 그것이 망가지면 되돌릴 곳이 없다.
    """
    store.restore_from_init()
    shutil.copy2(paths.INIT_MENU_YAML_PATH, paths.MENU_YAML_PATH)
    shutil.copy2(paths.INIT_MENU_MD_PATH, paths.MENU_MD_PATH)

    if paths.RECIPES_DIR.exists():
        shutil.rmtree(paths.RECIPES_DIR)
    shutil.copytree(paths.INIT_RECIPES_DIR, paths.RECIPES_DIR)
