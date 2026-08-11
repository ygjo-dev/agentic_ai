"""대상 : ontology/registry.py — 화면에서 노드를 등록하면 시스템이 스스로 확장된다

사람은 이름 · 설명 · 입출력 인터페이스만 적는다. 나머지는 시스템이 한다.

  1. LLM 이 노드 id 와 subject(무엇을 다루는가)를 정한다
  2. 온톨로지에 노드를 넣는다
  3. 새 노드를 지나는 실행 경로를 만들어 recipe 파일로 쓴다
  4. menu 에 그 recipe 들의 기능 문장을 더한다

**앞이 실패하면 뒤는 돌지 않는다.** 온톨로지에 못 넣은 노드로 recipe 를 만들면
존재하지 않는 노드를 가리키게 된다.

등록은 실제 저장소 파일을 바꾼다. 모든 테스트가 임시 디렉터리로 격리한다 —
리허설로 만들어둔 시연 상태가 pytest 한 번에 날아가면 시연 당일 사고가 된다.
"""

import json

import pytest
import yaml

import paths
from conftest import REAL_ONTOLOGY_PATH, StubLLMClient, workspace_digest
from ontology import store
from ontology.registry import (
    MAX_STEPS,
    NODE_REGISTRATION_SCHEMA,
    PROPERTY_KEYS,
    DuplicateNode,
    InvalidInference,
    UnknownInterface,
    UnknownPropertyKey,
    add_node,
    append_menu,
    append_recipes,
    function_for,
    infer_node,
    new_recipes_for,
    register_node,
    reset_to_init,
)

FORM = {
    "name": "궤도 결함 이력 요약",
    "description": "궤도 점검 보고서에서 결함이 어떻게 이어져 왔는지 요약한다.",
    "inputs": ["DocumentData"],
    "outputs": ["AnalysisResult"],
}

INFERRED = {
    "node_id": "analyze_crack_trend",
    "properties": {"subject": "궤도"},
    "reason": "궤도 균열 검출과 같은 대상을 다룬다.",
}

NEW_NODE = {**FORM, "properties": INFERRED["properties"]}


def stub(response=None):
    return StubLLMClient(json.dumps(response or INFERRED))


@pytest.fixture(autouse=True)
def isolated(isolated_workspace):
    """등록이 건드리는 파일을 임시 사본으로 바꾼다. 앞뒤로 저장소를 확인한다."""
    before = workspace_digest()
    yield
    assert workspace_digest() == before, "진짜 저장소가 바뀌었다"


def nodes_now():
    return store.nodes()


def recipes_now():
    return {path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml")}


def menu_now():
    return yaml.safe_load(paths.MENU_YAML_PATH.read_text(encoding="utf-8"))["recipes"]


# ================================================================ LLM 판단
def test_the_llm_decides_the_node_id_and_its_subject():
    """사람은 이름과 입출력만 적는다. id 와 subject 는 LLM 이 정한다.

    subject 는 "이 노드가 무엇을 다루는가" 다. 기존 노드와 같은 값을 쓰면
    점선으로 이어지고, 어느 대상에도 매이지 않으면 비운다 — 억지로 끼워
    맞추는 것보다 낫다.
    """
    result = infer_node(FORM, llm_client=stub())

    assert result["node_id"] == "analyze_crack_trend"
    assert result["properties"] == {"subject": "궤도"}
    assert result["reason"]

    # 값은 새로워도 되고 비어도 된다. 막는 것은 key 뿐이다.
    for properties in ({"subject": "터널"}, {}):
        assert infer_node(
            FORM, llm_client=stub({**INFERRED, "properties": properties})
        )["properties"] == properties

    assert set(NODE_REGISTRATION_SCHEMA["required"]) == {
        "node_id", "properties", "reason"
    }


def test_the_prompt_shows_what_the_llm_needs_to_decide_with():
    """기존 노드와 그 properties 가 없으면 관계를 판단할 수 없고,
    허용 key 를 안 알려주면 새 key 를 지어내 점선 조회가 갈라진다.

    프롬프트 파일에 치환자가 없으면 값이 통째로 안 실린다 — 그러면 LLM 이
    아무 근거 없이 답하게 되고, 그 사실이 화면에서는 안 보인다.
    """
    client = stub()
    infer_node(FORM, llm_client=client)
    sent = client.prompts[0]

    nodes = nodes_now()
    for node_id in nodes:
        assert node_id in sent, node_id

    shown = {
        f"{key}: {value}"
        for node in nodes.values()
        for key, value in (node.get("properties") or {}).items()
    }
    assert shown, "온톨로지에 properties 가 없으면 이 검사가 무력하다"
    for pair in shown:
        assert pair in sent, pair

    assert PROPERTY_KEYS
    for key in PROPERTY_KEYS:
        assert key in sent, key

    assert FORM["name"] in sent and FORM["description"] in sent
    assert "DocumentData" in sent

    template = paths.NODE_REGISTRATION_PROMPT_PATH.read_text(encoding="utf-8")
    for placeholder in ("{existing_nodes}", "{new_node}", "{property_keys}"):
        assert placeholder in template, placeholder


def test_a_malformed_llm_answer_is_rejected():
    """LLM 은 계약을 어길 수 있다. 프롬프트로만 막으면 어기는 순간 통과한다.

    id 형식이 깨지면 파일명과 참조가 어긋나고, properties 가 객체가 아니면
    점선 계산이 터진다. 응답이 JSON 이 아니거나 키가 빠지는 것도 여기서 잡는다.
    """
    bad_answers = [
        {**INFERRED, "node_id": "Bad-Id"},          # 대문자와 하이픈
        {**INFERRED, "node_id": "analyze crack"},   # 공백
        {**INFERRED, "properties": ["subject"]},    # 객체가 아니다
    ]
    for answer in bad_answers:
        with pytest.raises(InvalidInference):
            infer_node(FORM, llm_client=stub(answer))

    from orchestrator.route_resolver import RouteResolutionError

    with pytest.raises(RouteResolutionError):
        infer_node(FORM, llm_client=StubLLMClient("JSON 이 아니다"))
    with pytest.raises(RouteResolutionError):
        infer_node(FORM, llm_client=StubLLMClient(json.dumps({"node_id": "x"})))


def test_an_existing_node_id_is_rejected():
    """이미 있는 id 를 주면 온톨로지가 덮어써진다. 원래 노드가 조용히 사라진다."""
    existing = next(iter(nodes_now()))

    with pytest.raises(InvalidInference):
        infer_node(FORM, llm_client=stub({**INFERRED, "node_id": existing}))

    with pytest.raises(DuplicateNode):
        add_node(existing, NEW_NODE)


def test_unknown_interfaces_and_property_keys_are_rejected():
    """온톨로지에 없는 인터페이스를 쓰면 엣지가 아무 데도 안 이어지고,
    새 property key 를 만들면 점선 조회가 조용히 갈라진다.

    거부할 때는 파일을 한 글자도 건드리지 않아야 한다.
    """
    before = paths.ONTOLOGY_PATH.read_bytes()

    for broken in (
        {**NEW_NODE, "inputs": ["SensorStream"]},
        {**NEW_NODE, "outputs": ["Report"]},
    ):
        with pytest.raises(UnknownInterface):
            add_node("x", broken)

    with pytest.raises(UnknownPropertyKey):
        add_node("x", {**NEW_NODE, "properties": {"modality": "video"}})

    assert paths.ONTOLOGY_PATH.read_bytes() == before

    # 지금 쓰이는 key 가 전부 허용 목록 안에 있어야 한다.
    used = set()
    for node in nodes_now().values():
        used |= set(node.get("properties") or {})
    assert used <= PROPERTY_KEYS


# ================================================================ 경로 생성
def test_only_paths_through_the_new_node_are_created():
    """기존 노드끼리의 조합은 이미 recipe 로 있다. 다시 만들면 중복이다.

    이 함수는 파일을 쓰지 않는다 — 경로 목록만 돌려준다.
    """
    nodes = {
        "load_doc": {"inputs": [], "outputs": ["DocumentData"]},
        "load_cctv": {"inputs": [], "outputs": ["VideoData"]},
        "analyze": {"inputs": ["VideoData"], "outputs": ["AnalysisResult"]},
        "generate_word": {"inputs": ["AnalysisResult"], "outputs": ["DocumentData"]},
        "analyze_crack_trend": {"inputs": ["DocumentData"], "outputs": ["AnalysisResult"]},
    }
    before = json.dumps(nodes, sort_keys=True)

    chains = new_recipes_for("analyze_crack_trend", nodes)

    assert chains
    for chain in chains:
        assert "analyze_crack_trend" in chain
    assert len({tuple(chain) for chain in chains}) == len(chains), "중복 경로"

    # 타입이 안 맞는 시작점은 제외된다 — CCTV 는 DocumentData 를 못 내놓는다.
    assert not [chain for chain in chains if chain[0] == "load_cctv"]

    # 산출 노드를 등록하면 그 노드로 끝나는 경로만 나온다.
    endings = new_recipes_for("generate_word", nodes)
    assert endings and all(chain[-1] == "generate_word" for chain in endings)

    assert json.dumps(nodes, sort_keys=True) == before, "입력 dict 를 건드렸다"


def test_a_created_path_is_runnable_and_short():
    """타입이 이어지고, 같은 노드를 두 번 지나지 않고, 최대 3단이다.

    길이를 막는 이유 : 단이 늘수록 경로 수가 폭발하고, menu 가 커지면
    LLM context 를 넘겨 타임아웃한다.
    """
    nodes = {
        "load_doc": {"inputs": [], "outputs": ["DocumentData"]},
        "analyze_crack_trend": {"inputs": ["DocumentData"], "outputs": ["AnalysisResult"]},
        "generate_word": {"inputs": ["AnalysisResult"], "outputs": ["DocumentData"]},
        # 자기 출력을 자기가 받는 노드. 중복 방지가 없으면 [translate, translate]
        # 같은 경로가 나온다 — 이 노드가 없으면 중복 검사가 무력해진다.
        "translate_doc": {"inputs": ["DocumentData"], "outputs": ["DocumentData"]},
    }

    chains = new_recipes_for("translate_doc", nodes)

    assert chains
    assert {len(chain) for chain in chains} == {2, 3}, "2단과 3단이 둘 다 나와야 한다"
    for chain in chains:
        assert len(chain) <= MAX_STEPS
        assert len(set(chain)) == len(chain), f"노드가 중복됐다: {chain}"
        assert nodes[chain[0]]["inputs"] == []
        for frm, to in zip(chain, chain[1:]):
            assert set(nodes[frm]["outputs"]) & set(nodes[to]["inputs"]), (frm, to)


def test_recipe_files_continue_from_the_last_number():
    """기존 번호는 절대 바뀌면 안 된다 — menu 와 시연 샘플이 그 번호를 가리킨다.

    파일 형식도 기존 것과 같아야 한다. steps 아래 node / inputs / outputs 다.
    """
    nodes = {
        "load_doc": {"inputs": [], "outputs": ["DocumentData"]},
        "analyze_crack_trend": {"inputs": ["DocumentData"], "outputs": ["AnalysisResult"]},
    }
    chains = [["load_doc", "analyze_crack_trend"]]
    before_files = {p.name: p.read_bytes() for p in paths.RECIPES_DIR.glob("*.yaml")}
    last = max(int(p.stem.split("_")[1]) for p in paths.RECIPES_DIR.glob("recipe_*.yaml"))

    created = append_recipes(chains, nodes)
    again = append_recipes(chains, nodes)

    assert created == [f"recipe_{last + 1:03d}"]
    assert again == [f"recipe_{last + 2:03d}"]
    for name, content in before_files.items():
        assert (paths.RECIPES_DIR / name).read_bytes() == content, name

    assert append_recipes([], nodes) == []

    old = yaml.safe_load(
        next(iter(sorted(paths.RECIPES_DIR.glob("recipe_*.yaml")))).read_text(encoding="utf-8")
    )
    new = yaml.safe_load(
        (paths.RECIPES_DIR / f"{created[0]}.yaml").read_text(encoding="utf-8")
    )
    assert set(new) == set(old) == {"steps"}
    assert set(new["steps"][0]) == set(old["steps"][0])
    assert [step["node"] for step in new["steps"]] == chains[0]
    assert new["steps"][0]["inputs"] == [] and new["steps"][0]["outputs"] == ["DocumentData"]


# ================================================================ menu
def test_menu_gains_sentences_without_touching_the_old_ones():
    """function 문장은 LLM 이 recipe 를 고르는 유일한 근거다.

    기존 문장이 한 글자라도 바뀌면 이미 검증한 발화들이 다른 recipe 로 갈 수
    있다. 그래서 텍스트째로 두고 뒤에 이어 붙인다.

    문장은 서로 구별돼야 한다 — 같은 문장이 둘이면 LLM 이 고를 근거가 없다.
    menu.yaml 에는 function 만 넣는다. steps 까지 실으면 context 가 커져
    LLM 이 타임아웃한다.
    """
    nodes = {
        "load_doc": {"description": "궤도 점검 보고서를 불러온다."},
        "analyze_crack_trend": {"description": "보고서에서 균열 추세를 분석한다."},
        "generate_word": {"description": "분석 결과를 Word 보고서로 생성한다."},
    }
    chains = [
        ["load_doc", "analyze_crack_trend"],
        ["load_doc", "analyze_crack_trend", "generate_word"],
    ]
    new_ids = ["recipe_090", "recipe_091"]
    before = menu_now()
    before_md = paths.MENU_MD_PATH.read_text(encoding="utf-8")

    append_menu(new_ids, chains, nodes, )

    after = menu_now()
    for recipe_id, sentence in before.items():
        assert after[recipe_id] == sentence, recipe_id
    for recipe_id in new_ids:
        assert after[recipe_id]["function"].strip()
        assert set(after[recipe_id]) == {"function"}

    sentences = [entry["function"] for entry in after.values()]
    assert len(set(sentences)) == len(sentences), "같은 문장이 둘 이상이다"

    # 사람이 읽는 사본도 같은 목록을 담는다.
    md = paths.MENU_MD_PATH.read_text(encoding="utf-8")
    assert md.startswith(before_md[: before_md.index("| Recipe ID")])
    for recipe_id in after:
        assert recipe_id in md, recipe_id

    # 한 단짜리는 그 노드의 설명 그대로, 여러 단은 이어 붙인 한 문장이다.
    assert function_for(["load_doc"], nodes) == "궤도 점검 보고서를 불러온다."
    joined = function_for(chains[1], nodes)
    assert joined.endswith("생성한다.")
    assert joined.count("한다.") == 1, "종결형이 문장 끝에만 있어야 한 문장으로 읽힌다"
    assert function_for(chains[0], nodes) != joined


# ================================================================ 등록 전체
def test_registration_updates_the_ontology_recipes_and_menu_together():
    """셋 중 하나만 바뀌면 화면과 실행이 어긋난다.

    menu 에 있는데 recipe 파일이 없으면 실행 단계에서 깨지고, recipe 는 있는데
    menu 에 없으면 LLM 이 그 경로를 영영 못 고른다.
    """
    before_recipes = recipes_now()

    result = register_node(FORM, llm_client=stub())

    node = nodes_now()["analyze_crack_trend"]
    assert node["name"] == FORM["name"]
    assert node["inputs"] == FORM["inputs"] and node["outputs"] == FORM["outputs"]
    assert node["properties"] == {"subject": "궤도"}

    assert set(result["recipe_ids"]) == recipes_now() - before_recipes
    assert set(menu_now()) == recipes_now()

    for recipe_id in result["recipe_ids"]:
        data = yaml.safe_load(
            (paths.RECIPES_DIR / f"{recipe_id}.yaml").read_text(encoding="utf-8")
        )
        assert "analyze_crack_trend" in [step["node"] for step in data["steps"]]

    # 화면이 쓰는 것들.
    assert result["node_id"] and result["reason"] and result["chains"]

    # 두 번째 등록도 번호를 이어 간다.
    second = register_node(
        {**FORM, "name": "Excel 보고서 생성", "description": "분석 결과를 Excel 표로 생성한다.",
         "inputs": ["AnalysisResult"], "outputs": ["DocumentData"]},
        llm_client=stub({**INFERRED, "node_id": "generate_excel", "properties": {}}),
    )
    assert int(second["recipe_ids"][0].split("_")[1]) > int(
        result["recipe_ids"][-1].split("_")[1]
    )
    assert set(menu_now()) == recipes_now()


def test_a_failure_leaves_nothing_half_written():
    """앞 단계가 실패하면 뒤는 실행되지 않는다.

    온톨로지에 못 넣은 노드로 recipe 를 만들면 존재하지 않는 노드를 가리키고,
    그 recipe 를 LLM 이 고르면 실행 단계에서 터진다.
    """
    before = (
        paths.ONTOLOGY_PATH.read_bytes(),
        recipes_now(),
        paths.MENU_YAML_PATH.read_bytes(),
    )

    # 1단계(LLM 판단)에서 걸리는 경우.
    for answer in (
        {**INFERRED, "node_id": "Bad-Id"},
        {**INFERRED, "properties": {"modality": "x"}},
    ):
        with pytest.raises(InvalidInference):
            register_node(FORM, llm_client=stub(answer))

    # 2단계(온톨로지 쓰기)에서 걸리는 경우. **여기가 순서를 실제로 검사한다.**
    # 모르는 인터페이스는 LLM 판단을 통과하고 add_node 에서 걸린다. recipe 를
    # 먼저 쓰는 구현이면 이 시점에 파일이 이미 늘어나 있다.
    with pytest.raises(UnknownInterface):
        register_node({**FORM, "outputs": ["Report"]}, llm_client=stub())

    assert (
        paths.ONTOLOGY_PATH.read_bytes(),
        recipes_now(),
        paths.MENU_YAML_PATH.read_bytes(),
    ) == before


def test_resetting_removes_everything_a_registration_added():
    """시연에서 여러 번 등록해 보려면 되돌릴 수 있어야 한다.

    개수를 세지 않는다. 초기화의 정의는 "_init 사본과 같아진다" 이다.
    _init 자체는 절대 건드리지 않는다 — 그것이 망가지면 되돌릴 곳이 없다.
    """
    init_before = (
        paths.INIT_ONTOLOGY_PATH.read_bytes(),
        paths.INIT_MENU_YAML_PATH.read_bytes(),
        {p.name: p.read_bytes() for p in paths.INIT_RECIPES_DIR.glob("*.yaml")},
    )
    register_node(FORM, llm_client=stub())
    (paths.RECIPES_DIR / "recipe_099.yaml").write_text("steps: []\n", encoding="utf-8")

    reset_to_init()
    reset_to_init()  # 두 번 돌려도 같아야 한다

    assert "analyze_crack_trend" not in nodes_now()
    assert paths.ONTOLOGY_PATH.read_bytes() == paths.INIT_ONTOLOGY_PATH.read_bytes()
    assert paths.MENU_YAML_PATH.read_bytes() == paths.INIT_MENU_YAML_PATH.read_bytes()
    assert paths.MENU_MD_PATH.read_bytes() == paths.INIT_MENU_MD_PATH.read_bytes()
    assert recipes_now() == {p.stem for p in paths.INIT_RECIPES_DIR.glob("*.yaml")}
    assert not (paths.RECIPES_DIR / "recipe_099.yaml").exists()

    assert (
        paths.INIT_ONTOLOGY_PATH.read_bytes(),
        paths.INIT_MENU_YAML_PATH.read_bytes(),
        {p.name: p.read_bytes() for p in paths.INIT_RECIPES_DIR.glob("*.yaml")},
    ) == init_before

    # 진짜 저장소는 처음부터 끝까지 손대지 않았다.
    assert paths.ONTOLOGY_PATH != REAL_ONTOLOGY_PATH
