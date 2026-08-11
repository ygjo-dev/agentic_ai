"""노드 등록. 온톨로지 · recipe · menu 를 갱신.
"""

import re
import shutil

import yaml

import paths
from orchestrator.route_resolver import resolve_route

# 쓸 수 있는 property key. 값(value)은 새로워도 되지만 key 는 여기 있는 것만 쓴다.
# key 어휘가 갈라지면 점선(같은 key: value 공유) 조회가 조용히 실패한다.
# LLM 에게 프롬프트로도 알리지만, 어기는 순간을 대비해 코드로도 막는다.
PROPERTY_KEYS = frozenset({"source", "site", "target", "output_kind", "format"})


class DuplicateNode(ValueError):
    """이미 있는 노드 id 다."""


class UnknownInterface(ValueError):
    """온톨로지에 선언되지 않은 인터페이스다."""


class UnknownPropertyKey(ValueError):
    """기존 어휘에 없는 property key 다."""


def add_node(node_id: str, node: dict, path=None) -> None:
    """온톨로지에 노드를 추가한다.

    yaml.dump 로 다시 쓰지 않고 텍스트를 이어 붙인다 — 파일 상단의 구조 원칙
    주석과 기존 들여쓰기를 그대로 두기 위해서다. nodes: 가 파일 마지막이라
    끝에 붙이면 된다.
    """
    path = path or paths.ONTOLOGY_PATH
    ontology = yaml.safe_load(path.read_text(encoding="utf-8"))

    if node_id in ontology["nodes"]:
        raise DuplicateNode(f"이미 있는 노드다: {node_id}")

    interfaces = set(ontology["interfaces"])
    for name in [*node["inputs"], *node["outputs"]]:
        if name not in interfaces:
            raise UnknownInterface(
                f"온톨로지에 없는 인터페이스다: {name}\n"
                f"  쓸 수 있는 것 : {sorted(interfaces)}"
            )

    properties = node.get("properties") or {}
    unknown = set(properties) - PROPERTY_KEYS
    if unknown:
        raise UnknownPropertyKey(
            f"기존 어휘에 없는 property key 다: {sorted(unknown)}\n"
            f"  쓸 수 있는 것 : {sorted(PROPERTY_KEYS)}"
        )

    path.write_text(
        path.read_text(encoding="utf-8").rstrip("\n")
        + "\n\n"
        + _node_block(node_id, node)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _node_block(node_id: str, node: dict) -> str:
    """온톨로지에 적을 노드 한 덩어리. 기존 파일과 같은 들여쓰기."""
    lines = [
        f"  {node_id}:",
        f"    name: {node['name']}",
        f"    description: {node['description']}",
    ]

    for field in ("inputs", "outputs"):
        values = node[field]
        if values:
            lines.append(f"    {field}:")
            lines += [f"      - {value}" for value in values]
        else:
            lines.append(f"    {field}: []")

    properties = node.get("properties") or {}
    if properties:
        lines.append("    properties:")
        lines += [f"      {key}: {value}" for key, value in properties.items()]
    else:
        # 기존 노드와 관계가 없다는 뜻. 억지로 채우지 않는다.
        lines.append("    properties: {}")

    return "\n".join(lines)


# LLM 응답 구조(json). node_id 형식은 코드에서 다시 검증한다.
NODE_REGISTRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "node_id": {"type": "string"},
        "properties": {"type": "object"},
        "reason": {"type": "string"},
    },
    "required": ["node_id", "properties", "reason"],
}

NODE_ID_PATTERN = re.compile(r"^[a-z]+(_[a-z]+)*$")


class InvalidInference(ValueError):
    """LLM 이 쓸 수 없는 값을 돌려줬다."""


def infer_node(form: dict, llm_client, path=None) -> dict:
    """사람이 쓴 노드 정보를 보고 LLM 이 node_id 와 properties 를 정한다.

    "기존 key 중에서 고르기" 가 아니다. 새 노드가 기존 노드 중 무엇과 관계있는지
    판단하고, 그 관계를 점선으로 드러내려면 관계된 노드와 같은 key: value 를
    가져야 하므로 그렇게 쓰는 것이다. 관계가 없으면 비운다.

    Raises:
        InvalidInference: 형식에 맞지 않거나 쓸 수 없는 값을 돌려줬다.
        RouteResolutionError: 응답이 JSON 이 아니거나 필수 key 가 없다.
    """
    path = path or paths.ONTOLOGY_PATH
    nodes = yaml.safe_load(path.read_text(encoding="utf-8"))["nodes"]

    result = resolve_route(
        prompt=paths.NODE_REGISTRATION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={
            "existing_nodes": _describe(nodes),
            "new_node": _describe_form(form),
            "property_keys": ", ".join(sorted(PROPERTY_KEYS)),
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

    properties = result["properties"]
    if not isinstance(properties, dict):
        raise InvalidInference(f"properties 는 객체여야 한다: {properties!r}")

    unknown = set(properties) - PROPERTY_KEYS
    if unknown:
        raise InvalidInference(
            f"기존 어휘에 없는 property key 다: {sorted(unknown)}\n"
            f"  쓸 수 있는 것 : {sorted(PROPERTY_KEYS)}"
        )

    return result


def _describe(nodes: dict) -> str:
    """기존 노드를 프롬프트에 넣을 형태로. properties 가 핵심이라 반드시 넣는다."""
    lines = []
    for node_id, node in nodes.items():
        properties = node.get("properties") or {}
        shown = (
            ", ".join(f"{key}: {value}" for key, value in properties.items()) or "(없음)"
        )
        lines.append(
            f"- {node_id}\n"
            f"    이름 : {node['name']}\n"
            f"    설명 : {node['description']}\n"
            f"    입력 : {node['inputs'] or '없음'} -> 출력 : {node['outputs']}\n"
            f"    properties : {shown}"
        )
    return "\n".join(lines)


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

    def connectable(prev_id: str, next_id: str) -> bool:
        return bool(set(nodes[prev_id]["outputs"]) & set(nodes[next_id]["inputs"]))

    starts = [nid for nid, node in nodes.items() if node["inputs"] == []]

    chains = [[start] for start in starts]
    found = []
    for _ in range(MAX_STEPS):
        found += [chain for chain in chains if node_id in chain]
        chains = [
            [*chain, nxt]
            for chain in chains
            if len(chain) < MAX_STEPS
            for nxt in nodes
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
    """
    inferred = infer_node(form, llm_client=llm_client)
    node_id = inferred["node_id"]

    node = {
        "name": form["name"],
        "description": form["description"],
        "inputs": form["inputs"],
        "outputs": form["outputs"],
        "properties": inferred["properties"],
    }
    add_node(node_id, node, path=paths.ONTOLOGY_PATH)

    nodes = yaml.safe_load(paths.ONTOLOGY_PATH.read_text(encoding="utf-8"))["nodes"]
    chains = new_recipes_for(node_id, nodes)
    recipe_ids = append_recipes(chains, nodes)
    append_menu(recipe_ids, chains, nodes)

    return {**inferred, "node": node, "recipe_ids": recipe_ids, "chains": chains}


def reset_to_init() -> None:
    """_init 사본을 작업 파일로 되돌린다.

    등록으로 늘어난 recipe 도 사라져야 하므로 디렉터리를 통째로 갈아끼운다.
    _init 사본 자체는 절대 건드리지 않는다 — 그것이 망가지면 되돌릴 곳이 없다.
    """
    shutil.copy2(paths.INIT_ONTOLOGY_PATH, paths.ONTOLOGY_PATH)
    shutil.copy2(paths.INIT_MENU_YAML_PATH, paths.MENU_YAML_PATH)
    shutil.copy2(paths.INIT_MENU_MD_PATH, paths.MENU_MD_PATH)

    if paths.RECIPES_DIR.exists():
        shutil.rmtree(paths.RECIPES_DIR)
    shutil.copytree(paths.INIT_RECIPES_DIR, paths.RECIPES_DIR)
