"""대상 : ontology/registry.py — 화면에서 노드를 등록하면 시스템이 스스로 확장된다

사람은 이름 · 설명 · 받고 내놓는 타입만 적는다. 나머지는 시스템이 한다.

  1. LLM 이 노드 id 와 무엇에 관한 것인지를 정한다
  2. 온톨로지에 노드를 넣고 관계(hasInput · hasOutput · about)를 붙인다
  3. 새 노드를 지나는 실행 경로를 만든다. **대상이 어긋나는 것은 버린다**
       궤도 검측차 영상으로 승강장 승객을 보는 경로 같은 것들이다
  4. 남은 경로를 recipe 파일로 쓰고 menu 에 기능 문장을 더한다

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
from ontology.graph import ABOUT, HAS_INPUT, HAS_OUTPUT
from ontology.registry import (
    MAX_STEPS,
    MENU_BUDGET,
    NODE_REGISTRATION_SCHEMA,
    DuplicateNode,
    InvalidInference,
    UnknownType,
    _describe_groups,
    add_node,
    all_recipes,
    append_menu,
    append_recipes,
    check_types,
    function_for,
    group_ids,
    infer_node,
    new_recipes_for,
    register_node,
    reset_to_init,
)

FORM = {
    "name": "궤도 침하 검출",
    "description": "이미지에서 궤도 노반의 침하를 검출한다.",
    "inputs": ["image"],
    "outputs": ["analysis"],
}

INFERRED = {
    "node_id": "detect_track_settlement",
    "groups": ["group_track"],
    "reason": "궤도 균열 검출과 같은 대상에 관한 것이다.",
}

NEW_NODE = {"name": FORM["name"], "description": FORM["description"]}


def stub(response=None):
    return StubLLMClient(json.dumps(response or INFERRED))


@pytest.fixture(autouse=True)
def isolated(isolated_workspace):
    """등록이 건드리는 파일을 임시 사본으로 바꿈. 앞뒤로 저장소를 확인함."""
    before = workspace_digest()
    yield
    assert workspace_digest() == before, "진짜 저장소가 바뀌었다"


def nodes_now():
    return store.nodes()


def recipes_now():
    return {path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml")}


def edges_now():
    return store.edges()


def menu_now():
    return yaml.safe_load(paths.MENU_YAML_PATH.read_text(encoding="utf-8"))["recipes"]


# ================================================================ LLM 판단
def test_the_llm_decides_the_node_id_and_what_it_is_about():
    """사람은 이름과 입출력만 적음. id 와 관한 대상은 LLM 이 정함.

    대상은 닫힌 목록에서 고르는 것. 예전에는 자유 문자열(subject 값)을
    쓰게 했는데 "궤도" 대신 "선로" 라고 쓰면 아무와도 안 이어졌음.

    여럿을 고를 수 있음. 한 노드가 여러 대상에 관한 것일 수 있기 때문.
    승강장 CCTV 영상은 승강장에 관한 것이자 CCTV 에 관한 것. 하나만
    받으면 그 사실을 적을 방법이 없음.

    어느 대상에도 매이지 않는 범용 노드는 빈 목록. 형식만 바꾸는 생성
    노드는 어떤 대상의 결과든 받으므로 한 대상에 묶으면 오히려 틀림.
    """
    result = infer_node(FORM, llm_client=stub())

    assert result["node_id"] == "detect_track_settlement"
    assert result["groups"] == ["group_track"]
    assert result["reason"]

    # 여러 개도 정상이다.
    many = infer_node(
        FORM, llm_client=stub({**INFERRED, "groups": ["group_track", "group_cctv"]})
    )
    assert many["groups"] == ["group_track", "group_cctv"]

    # 빈 목록도 정상이다.
    assert infer_node(FORM, llm_client=stub({**INFERRED, "groups": []}))["groups"] == []

    # 같은 대상을 두 번 적으면 점선이 두 줄 생긴다.
    twice = infer_node(
        FORM, llm_client=stub({**INFERRED, "groups": ["group_track", "group_track"]})
    )
    assert twice["groups"] == ["group_track"]

    assert set(NODE_REGISTRATION_SCHEMA["required"]) == {
        "node_id", "groups", "reason"
    }


def test_the_prompt_shows_what_the_llm_needs_to_decide_with():
    """기존 기능 노드가 무엇에 관한 것인지 안 보여주면 비슷한 노드를 보고
    고를 수가 없고, 선택지를 안 알려주면 없는 id 를 지어냄.

    프롬프트 파일에 치환자가 없으면 값이 통째로 안 실림. 그러면 LLM 이
    아무 근거 없이 답하게 되고, 그 사실이 화면에서는 안 보임.
    """
    client = stub()
    infer_node(FORM, llm_client=client)
    sent = client.prompts[0]

    # 기존 **기능** 노드가 다 실려야 한다. 데이터 노드는 이 판단의 근거가
    # 아니다 — 사람이 화면에서 고르는 것이라 LLM 이 정할 것이 없다.
    from ontology.registry import functions

    listed = functions(nodes_now())
    assert listed, "기능 노드가 없으면 이 검사가 무력하다"
    for node_id in listed:
        assert node_id in sent, node_id

    # 고를 수 있는 대상이 id 와 이름으로 다 실려야 한다. id 만 보여주면 뜻을
    # 모르고, 이름만 보여주면 무엇을 적어야 할지 모른다.
    #
    # "id 가 문자열 어딘가에 있다" 로 재면 무력하다 — 아래 기존 노드 설명에도
    # 대상 id 가 나오고, 대상 이름("궤도")은 기능 이름("궤도 균열 검출") 안에도
    # 들어 있다. 실제로 목록을 빼도 통과했다. 블록 자체를 찾는다.
    choices = group_ids()
    assert choices, "대상이 하나도 없으면 이 검사가 무력하다"
    assert _describe_groups(nodes_now(), choices) in sent, "대상 목록이 통째로 빠졌다"

    # 기존 기능이 무엇에 관한 것인지도 보여야 비슷한 것을 보고 고른다.
    attached = {
        edge["from"]: edge["to"] for edge in edges_now() if edge["predicate"] == ABOUT
    }
    assert attached, "about 이 비면 이 검사가 무력하다"
    assert any(f"관한 대상 : {gid}" in sent for gid in attached.values())

    assert FORM["name"] in sent and FORM["description"] in sent

    template = paths.NODE_REGISTRATION_PROMPT_PATH.read_text(encoding="utf-8")
    for placeholder in ("{existing_nodes}", "{new_node}", "{groups}"):
        assert placeholder in template, placeholder


def test_a_malformed_llm_answer_is_rejected():
    """LLM 은 계약을 어길 수 있음. 프롬프트로만 막으면 어기는 순간 통과함.

    id 형식이 깨지면 파일명과 참조가 어긋나고, 없는 대상을 고르면 아무 데도
    안 붙는 관계가 파일에 남음. 응답이 JSON 이 아니거나 키가 빠지는 것도
    여기서 잡음.
    """
    bad_answers = [
        {**INFERRED, "node_id": "Bad-Id"},              # 대문자와 하이픈
        {**INFERRED, "node_id": "analyze crack"},       # 공백
        {**INFERRED, "groups": "group_track"},          # 목록이 아니다
        {**INFERRED, "groups": [["group_track"]]},      # 원소가 문자열이 아니다
        {**INFERRED, "groups": ["group_tunnel"]},       # 온톨로지에 없는 대상
        # 하나만 틀려도 전부 거부한다. 통과시키면 나머지 하나만 붙어
        # "왜 하나만 묶였지" 를 화면에서 알 방법이 없다.
        {**INFERRED, "groups": ["group_track", "group_tunnel"]},
        # 타입 노드는 대상이 아니다. id 라고 다 되는 것이 아니다.
        {**INFERRED, "groups": ["video"]},
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
    """이미 있는 id 를 주면 온톨로지가 덮어써짐. 원래 노드가 조용히 사라짐."""
    existing = next(iter(nodes_now()))

    with pytest.raises(InvalidInference):
        infer_node(FORM, llm_client=stub({**INFERRED, "node_id": existing}))

    with pytest.raises(DuplicateNode):
        add_node(existing, NEW_NODE)


def test_types_that_do_not_exist_are_rejected():
    """없는 타입을 가리키면 그 노드는 아무와도 안 이어짐.

    화면에는 떠 있는데 경로가 하나도 안 생김. 등록은 성공했다고 나오고
    실행할 것만 없음. 사람이 원인을 짚기 가장 어려운 실패.

    거부할 때는 파일을 한 글자도 건드리지 않아야 함.
    """
    before = paths.ONTOLOGY_PATH.read_bytes()

    for broken in (["SensorStream"], ["analysis", "Report"]):
        with pytest.raises(UnknownType):
            check_types(broken)

    # 있는 타입은 통과한다. 위 검사가 무조건 터지는 것이 아님을 보인다.
    check_types(["image", "analysis"])

    assert paths.ONTOLOGY_PATH.read_bytes() == before


# ================================================================ 경로 생성
def test_a_new_node_gets_exactly_its_share_of_all_the_paths():
    """등록이 만드는 경로 = 온톨로지 전체 경로 중 그 노드를 지나는 것.

    두 함수가 갈라지면 안 됨. _init 의 recipe 는 all_recipes 로 만들고
    (tools/rebuild_init.py) 등록은 new_recipes_for 로 만드는데, 규칙이 두
    벌이 되면 menu 문장이 미묘하게 갈림. 그 문장이 발화 매칭의 유일한
    근거라 "초기 recipe 는 되는데 등록한 건 안 되는" 상황이 나오고 원인을
    찾기도 어려움.
    """
    add_node("detect_track_settlement", NEW_NODE)
    store.append_edge("detect_track_settlement", "image", HAS_INPUT)
    store.append_edge("detect_track_settlement", "analysis", HAS_OUTPUT)
    nodes = nodes_now()

    every = all_recipes(nodes)
    mine = new_recipes_for("detect_track_settlement", nodes)

    assert mine, "새 노드를 지나는 경로가 없으면 이 검사가 무력하다"
    assert len(mine) < len(every), "전부가 새 노드를 지나면 비교가 뜻이 없다"
    assert mine == [c for c in every if "detect_track_settlement" in c]


def test_all_recipes_does_not_drop_paths_that_cross_subjects():
    """거르는 것은 부르는 쪽의 일. 여기서 함께 거르면 안 됨.

    all_recipes 가 crosses_groups 까지 걸러 버리면 부르는 쪽이 필터를
    빼먹어도 결과가 멀쩡해 보임. 그러다 조건이 바뀌면 말이 안 되는 경로가
    조용히 _init 에 깔림. 승강장 CCTV 로 궤도 균열을 찾는 것 같은.
    "무엇이 만들어질 수 있는가" 와 "무엇을 남길 것인가" 는 갈라 둠.
    """
    from ontology.graph import crosses_groups

    every = all_recipes(nodes_now())

    assert [chain for chain in every if crosses_groups(chain)], (
        "어긋나는 경로가 하나도 없으면 이 검사가 무력하다"
    )


def test_only_paths_through_the_new_node_are_created():
    """기존 노드끼리의 조합은 이미 recipe 로 있음. 다시 만들면 중복.

    이 함수는 파일을 쓰지 않음. 경로 목록만 돌려줌.
    """
    # 영상만 받는 노드다. 분석결과로는 이 노드에 닿을 길이 없다 — 분석결과를
    # 영상으로 바꾸는 노드가 온톨로지에 없기 때문이다.
    add_node("detect_intrusion", {"name": "선로 침입 검출",
                                  "description": "영상에서 선로 침입을 검출한다."})
    store.append_edge("detect_intrusion", "video", HAS_INPUT)
    store.append_edge("detect_intrusion", "analysis", HAS_OUTPUT)
    nodes = nodes_now()
    before = json.dumps(nodes, sort_keys=True)

    chains = new_recipes_for("detect_intrusion", nodes)

    assert chains
    for chain in chains:
        assert "detect_intrusion" in chain
    assert len({tuple(chain) for chain in chains}) == len(chains), "중복 경로"

    # 닿을 수 없는 자리는 제외된다. 이 노드는 영상만 받으므로 분석결과를
    # 내놓는 노드 뒤에는 절대 붙지 않는다.
    assert not [c for c in chains if "analyze_congestion" in c]
    assert [c for c in chains if c[0] == "platform_cctv_video"]

    # 다른 노드를 넣으면 그 노드를 지나는 경로만 나온다. 새 노드가 안 낀 경로는
    # 이미 recipe 로 있으므로 다시 만들면 중복이다.
    others = new_recipes_for("generate_word", nodes)
    assert others and all("generate_word" in chain for chain in others)
    assert not [c for c in others if "detect_intrusion" in c and "generate_word" not in c]

    # 문서를 받는 노드가 없어 산출물이 다시 입력으로 되먹임되지 않는다.
    # 생성 노드는 경로의 끝이다.
    assert all(c[-1] == "generate_word" for c in others)

    assert json.dumps(nodes_now(), sort_keys=True) == before, "온톨로지를 건드렸다"


def test_a_created_path_is_runnable_and_short():
    """타입이 이어지고, 같은 노드를 두 번 지나지 않고, 최대 MAX_STEPS 단임.

    길이를 막는 이유 : 단이 늘수록 경로 수가 폭발하고, menu 가 커지면
    LLM context 를 넘겨 타임아웃함.

    자기 출력을 자기가 받는 노드를 일부러 등록함. 중복 방지가 없으면
    [번역, 번역, 번역] 같은 경로가 나오는데, 그런 노드가 없으면 중복 검사
    자체가 무력함. 실제로 예전 명세가 그 상태였음.
    """
    from ontology.graph import can_connect

    add_node("enhance_image", {"name": "이미지 보정",
                               "description": "이미지의 품질을 보정한다."})
    store.append_edge("enhance_image", "image", HAS_INPUT)
    store.append_edge("enhance_image", "image", HAS_OUTPUT)
    nodes = nodes_now()

    assert can_connect("enhance_image", "enhance_image"), "이 검사의 전제가 깨졌다"

    chains = new_recipes_for("enhance_image", nodes)

    assert chains
    assert len({len(chain) for chain in chains}) > 1, "여러 길이가 나와야 한다"
    for chain in chains:
        assert len(chain) <= MAX_STEPS
        assert len(set(chain)) == len(chain), f"노드가 중복됐다: {chain}"
        for frm, to in zip(chain, chain[1:]):
            assert can_connect(frm, to), (frm, to)


def test_a_subject_node_never_enters_an_execution_path():
    """대상 노드는 실행할 수 없음. 경로에 섞이면 안 됨.

    그룹은 아무것도 받지도 내놓지도 않음. 걸러내지 않으면 "받는 것이 없는
    노드" 로 보여 recipe 시작점이 됨. 그러면 궤도 -> ??? 같은 실행
    불가능한 recipe 가 만들어지고, menu 에 실려 LLM 이 그것을 고를 수 있게 됨.

    조용히 깨지는 자리. 파일은 멀쩡해 보이고 화면도 그려지는데 실행만 안 됨.
    """
    add_node("detect_track_settlement", NEW_NODE)
    store.append_edge("detect_track_settlement", "image", HAS_INPUT)
    store.append_edge("detect_track_settlement", "analysis", HAS_OUTPUT)
    nodes = nodes_now()

    groups = set(group_ids())
    assert groups, "대상이 없으면 이 검사가 무력하다"

    chains = new_recipes_for("detect_track_settlement", nodes)

    assert chains
    for chain in chains:
        assert not groups & set(chain), f"경로에 대상이 들어갔다: {chain}"

    # 대상 자체를 등록 대상으로 넘겨도 경로를 만들지 않는다.
    assert new_recipes_for("group_track", nodes) == []


def test_new_recipes_get_new_numbers_and_the_old_files_never_change():
    """기존 번호는 절대 바뀌면 안 됨. menu 와 시연 샘플이 그 번호를 가리킴.

    파일 형식도 기존 것과 같아야 함. steps 아래 node 하나뿐. 무엇을
    주고받는지는 온톨로지의 hasInput / hasOutput 이 말하므로 여기 또 적으면
    진실의 원천이 둘이 됨.
    """
    nodes = nodes_now()
    chains = [["track_car_cctv_video", "extract_frames"]]
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
        next(iter(sorted(paths.RECIPES_DIR.glob("recipe_0*.yaml")))).read_text(
            encoding="utf-8"
        )
    )
    new = yaml.safe_load(
        (paths.RECIPES_DIR / f"{created[0]}.yaml").read_text(encoding="utf-8")
    )
    assert set(new) == set(old) == {"steps"}
    assert set(new["steps"][0]) == set(old["steps"][0]) == {"node"}
    assert [step["node"] for step in new["steps"]] == chains[0]


# ================================================================ 말이 안 되는 경로
#
# 등록은 한 번에 끝난다. 만들어진 경로 중 **대상(about)이 어긋나는 것은 버린다** —
# 궤도 검측차 영상으로 승강장 승객의 위험 행동을 찾는 경로 같은 것들이다.
# 화각이 안 맞아 실행할 수 없다.
#
# 예전에는 그런 경로를 화면에 올려 사람이 승인하게 했다(propose/approve).
# 관문이 시연 화면의 절반을 먹었고 걸러지는 것이 전부 진짜 쓰레기였다.
# **사람이 검토하는 절차는 이 화면 밖에 제대로 들어간다** — 그때 crosses_groups 가
# 차단에서 분류로 돌아간다.

# 승강장에 관한 노드인데 이미지를 받는다. 궤도 검측차 영상에서 시작하는 경로도
# 타입상 만들어지고, 그것이 어긋나는 경로다 — 검측차는 주행 중 궤도를
# 내려다보므로 승강장 승객이 화각에 없다.
CROSSING_FORM = {
    "name": "승강장 위험 행동 검출",
    "description": "이미지에서 승강장 승객의 위험 행동을 검출한다.",
    "inputs": ["image"],
    "outputs": ["analysis"],
}

CROSSING_INFERRED = {
    "node_id": "detect_risky_behavior",
    "groups": ["group_platform"],
    "reason": "승강장 승객에 관한 것이다.",
}


def chains_in_recipe_files() -> set[tuple[str, ...]]:
    return {
        tuple(step["node"] for step in yaml.safe_load(p.read_text(encoding="utf-8"))["steps"])
        for p in paths.RECIPES_DIR.glob("recipe_*.yaml")
    }


def test_paths_that_cross_subjects_are_never_registered():
    """★ 대상이 어긋나는 경로는 파일이 되지 않음. 응답에도 안 담김.

    타입만 보면 이어지지만 실행할 수 없는 경로. 그것이 menu 에 실리면 LLM 이
    후보로 보게 되고, 사람이 그걸 고르는 순간 시연이 멈춤.

    차단이지 표시가 아님. 버린 경로를 돌려주지도 않음. 화면이 안 쓰는
    키를 만들지 않음. 몇 개를 버렸는지는 이 테스트가 재서 보여줌.
    """
    from ontology.graph import crosses_groups

    before_files = recipes_now()
    before_menu = set(menu_now())

    result = register_node(CROSSING_FORM, llm_client=stub(CROSSING_INFERRED))

    made = new_recipes_for("detect_risky_behavior", nodes_now())
    dropped = [chain for chain in made if crosses_groups(chain)]
    assert dropped, "버려지는 경로가 없으면 이 검사가 무력하다"
    assert result["chains"] == [c for c in made if not crosses_groups(c)]
    assert len(result["chains"]) < len(made)

    # 남은 것만 파일이 됐다. 버린 것은 어느 파일에도 없다.
    written = chains_in_recipe_files()
    for chain in result["chains"]:
        assert tuple(chain) in written, chain
        assert not crosses_groups(chain), chain
    for chain in dropped:
        assert tuple(chain) not in written, f"어긋나는 경로가 파일이 됐다: {chain}"

    assert recipes_now() - before_files == set(result["recipe_ids"])
    assert set(menu_now()) - before_menu == set(result["recipe_ids"])

    # 승인 관문의 흔적이 없다. 버린 경로도 돌려주지 않는다.
    assert "pending" not in result and "dropped" not in result


def test_a_node_that_agrees_with_everything_loses_no_path():
    """어긋날 상대가 없으면 하나도 안 버림. 차단이 과하면 여기서 잡힘.

    CCTV 화질 저하 진단은 두 영상 모두에 관한 것(group_cctv)이라 어느 시작점에서
    출발해도 대상이 통함. 이런 등록에서 경로가 하나라도 사라지면 차단 조건이
    너무 넓은 것이고, 그러면 시연에서 "왜 이 길은 안 생겼지" 가 됨.
    """
    from ontology.graph import crosses_groups

    result = register_node(
        {"name": "CCTV 화질 저하 진단", "description": "영상에서 CCTV 화질 저하를 진단한다.",
         "inputs": ["video"], "outputs": ["analysis"]},
        llm_client=stub({**INFERRED, "node_id": "analyze_image_quality",
                         "groups": ["group_cctv"]}),
    )

    made = new_recipes_for("analyze_image_quality", nodes_now())
    assert made, "경로가 없으면 이 검사가 무력하다"
    assert not [chain for chain in made if crosses_groups(chain)]
    assert result["chains"] == made
    assert len(result["recipe_ids"]) == len(made)
    assert set(result["recipe_ids"]) <= set(menu_now())


# ================================================================ menu
def test_menu_gains_sentences_without_touching_the_old_ones():
    """function 문장은 LLM 이 recipe 를 고르는 유일한 근거.

    기존 문장이 한 글자라도 바뀌면 이미 검증한 발화들이 다른 recipe 로 갈 수
    있음. 그래서 텍스트째로 두고 뒤에 이어 붙임.

    문장은 서로 구별돼야 함. 같은 문장이 둘이면 LLM 이 고를 근거가 없음.
    menu.yaml 에는 function 만 넣음. steps 까지 실으면 context 가 커져
    LLM 이 타임아웃함.
    """
    nodes = nodes_now()
    chains = [
        ["track_car_cctv_video", "extract_frames"],
        ["track_car_cctv_video", "extract_frames", "detect_track_crack"],
    ]
    new_ids = ["recipe_090", "recipe_091"]
    before = menu_now()
    before_md = paths.MENU_MD_PATH.read_text(encoding="utf-8")

    append_menu(new_ids, chains, nodes)

    after = menu_now()
    for recipe_id, sentence in before.items():
        assert after[recipe_id] == sentence, recipe_id
    for recipe_id in new_ids:
        assert after[recipe_id]["function"].strip()
        assert set(after[recipe_id]) == {"function"}

    # 사람이 읽는 사본도 같은 목록을 담는다.
    md = paths.MENU_MD_PATH.read_text(encoding="utf-8")
    assert md.startswith(before_md[: before_md.index("| Recipe ID")])
    for recipe_id in after:
        assert recipe_id in md, recipe_id


def test_a_menu_sentence_reads_as_one_korean_sentence():
    """경로는 데이터 노드로 시작하는데 그 설명은 명사구.

    설명을 그냥 이어 붙이면 "...촬영한 영상하고 프레임을 추출하고" 가 됨.
    데이터는 이름에 조사를 붙여 앞에 두고 기능 설명만 이음.

    데이터 이름을 빼면 안 됨. 같은 기능을 쓰는 recipe 가 무엇으로 시작하는지
    구분할 근거가 사라져 LLM 이 고를 수 없음.
    """
    nodes = nodes_now()

    one = function_for(["platform_cctv_video", "extract_frames"], nodes)
    two = function_for(
        ["platform_cctv_video", "extract_frames", "analyze_congestion"], nodes
    )

    # 종결형이 문장 끝에만 있어야 한 문장으로 읽힌다.
    for sentence in (one, two):
        assert sentence.count("다.") == 1 and sentence.endswith("다."), sentence
    assert "영상하고" not in one, "명사구를 억지로 연결형으로 바꿨다"
    assert one != two

    # 데이터 이름이 실려야 시작점을 구분할 수 있다.
    assert nodes["platform_cctv_video"]["name"] in one
    other = function_for(["track_car_cctv_video", "extract_frames"], nodes)
    assert other != one, "시작 데이터가 다른데 같은 문장이 됐다"

    # 중간 단계는 연결형이 된다. "검출한다" 는 "검출하고" 다 —
    # 마지막 단계로만 재면 종결형 그대로라 이 규칙이 한 번도 안 불린다.
    chained = function_for(
        ["track_car_cctv_video", "extract_frames", "detect_track_crack"], nodes
    )
    assert "검출하고 " not in chained, "마지막 단계는 종결형이어야 한다"
    assert "추출하고 " in chained, chained
    assert chained.count("다.") == 1 and chained.endswith("다."), chained

    # 조사가 받침을 따라간다. "영상으로" 와 "이미지로" 가 갈린다 —
    # 받침을 안 보면 시연 중에 사람이 먼저 알아챈다.
    assert "궤도 검측차 CCTV 영상으로 " in function_for(
        ["track_car_cctv_video", "extract_frames"], nodes
    )
    assert "승강장 CCTV 영상으로 " in one

    # 실제 menu 문장도 서로 구별된다.
    sentences = [entry["function"] for entry in menu_now().values()]
    assert len(set(sentences)) == len(sentences), "같은 문장이 둘 이상이다"
    for sentence in sentences:
        assert sentence.count("다.") == 1 and sentence.endswith("다."), sentence

    # menu 전체가 예산 안에 있어야 한다. 넘으면 LLM context 를 넘겨 타임아웃한다.
    assert len(paths.MENU_YAML_PATH.read_text(encoding="utf-8")) < MENU_BUDGET


# ================================================================ 등록 전체
def test_registration_updates_the_ontology_recipes_and_menu_together():
    """셋 중 하나만 바뀌면 화면과 실행이 어긋남.

    menu 에 있는데 recipe 파일이 없으면 실행 단계에서 깨지고, recipe 는 있는데
    menu 에 없으면 LLM 이 그 경로를 영영 못 고름.
    """
    before_recipes = recipes_now()

    result = register_node(FORM, llm_client=stub())

    node = nodes_now()["detect_track_settlement"]
    assert set(node) == {"name", "description"}, "노드에 종류나 입출력을 적었다"
    assert node["name"] == FORM["name"]

    # 받고 내놓는 것은 관계로 붙는다. 이게 있어야 경로에 낄 수 있다.
    edges = edges_now()
    for type_id, predicate in (("image", HAS_INPUT), ("analysis", HAS_OUTPUT)):
        assert {
            "from": "detect_track_settlement", "to": type_id, "predicate": predicate
        } in edges

    # 고른 대상에 관계 한 줄이 붙는다. 이게 화면에서 점선이 된다.
    assert {
        "from": "detect_track_settlement", "to": "group_track", "predicate": ABOUT
    } in edges

    assert set(result["recipe_ids"]) == recipes_now() - before_recipes
    assert set(menu_now()) == recipes_now()

    for recipe_id in result["recipe_ids"]:
        data = yaml.safe_load(
            (paths.RECIPES_DIR / f"{recipe_id}.yaml").read_text(encoding="utf-8")
        )
        assert "detect_track_settlement" in [step["node"] for step in data["steps"]]

    # 화면이 쓰는 것들.
    assert result["node_id"] and result["reason"] and result["chains"]

    # 두 번째 등록도 번호를 이어 간다.
    about_count = len([e for e in edges_now() if e["predicate"] == ABOUT])
    second = register_node(
        {"name": "Excel 보고서 생성", "description": "분석 결과를 Excel 문서로 생성한다.",
         "inputs": ["analysis"], "outputs": ["output_report"]},
        llm_client=stub({**INFERRED, "node_id": "generate_excel", "groups": []}),
    )
    # 범용 노드는 어디에도 안 붙는다. 억지로 묶으면 오히려 틀린다.
    assert len([e for e in edges_now() if e["predicate"] == ABOUT]) == about_count
    assert int(second["recipe_ids"][0].split("_")[1]) > int(
        result["recipe_ids"][-1].split("_")[1]
    )
    assert set(menu_now()) == recipes_now()


def test_several_subjects_all_become_dotted_lines():
    """대상을 여럿 고르면 전부 붙음. 하나만 붙이면 나머지가 조용히 사라짐.

    승강장 CCTV 영상이 승강장에도 CCTV 에도 관한 것이라고 판단했는데 한 줄만
    적히면, 화면에서는 왜 한쪽에만 묶였는지 알 방법이 없음.
    """
    register_node(
        FORM,
        llm_client=stub({**INFERRED, "groups": ["group_track", "group_cctv"]}),
    )

    attached = {
        edge["to"]
        for edge in edges_now()
        if edge["from"] == "detect_track_settlement" and edge["predicate"] == ABOUT
    }
    assert attached == {"group_track", "group_cctv"}


def test_a_failure_leaves_nothing_half_written():
    """앞 단계가 실패하면 뒤는 실행되지 않음.

    온톨로지에 못 넣은 노드로 recipe 를 만들면 존재하지 않는 노드를 가리키고,
    그 recipe 를 LLM 이 고르면 실행 단계에서 터짐.
    """
    before = (
        paths.ONTOLOGY_PATH.read_bytes(),
        recipes_now(),
        paths.MENU_YAML_PATH.read_bytes(),
    )

    # 1단계(LLM 판단)에서 걸리는 경우.
    for answer in (
        {**INFERRED, "node_id": "Bad-Id"},
        {**INFERRED, "groups": ["group_tunnel"]},
    ):
        with pytest.raises(InvalidInference):
            register_node(FORM, llm_client=stub(answer))

    # 2단계(온톨로지 쓰기)에서 걸리는 경우. **여기가 순서를 실제로 검사한다.**
    # 모르는 타입은 LLM 판단을 통과하고 쓰기 직전에 걸린다. recipe 를 먼저 쓰는
    # 구현이면 이 시점에 파일이 이미 늘어나 있다.
    with pytest.raises(UnknownType):
        register_node({**FORM, "outputs": ["Report"]}, llm_client=stub())

    # 노드는 썼는데 관계를 못 붙이는 경우도 없어야 한다 — 관계 없는 노드는
    # 화면에 떠 있기만 하고 아무 경로에도 안 낀다.
    assert (
        paths.ONTOLOGY_PATH.read_bytes(),
        recipes_now(),
        paths.MENU_YAML_PATH.read_bytes(),
    ) == before


def test_resetting_removes_everything_a_registration_added():
    """시연에서 여러 번 등록해 보려면 되돌릴 수 있어야 함.

    개수를 세지 않음. 초기화의 정의는 "_init 사본과 같아진다" 임.
    _init 자체는 절대 안 건드림. 그것이 망가지면 되돌릴 곳이 없음.
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

    assert "detect_track_settlement" not in nodes_now()
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
