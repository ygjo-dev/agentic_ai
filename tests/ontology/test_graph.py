"""대상 : ontology/graph.py — 온톨로지에서 그래프를 계산한다

**노드에는 종류가 적혀 있지 않다.** name 과 description 뿐이고, 성격은 관계가
말한다 — hasOutput 이 있으면 실행할 수 있고, about 의 대상으로 등장하면 대상
(그룹)이고, 둘 다 아니면 오가는 데이터다.

관계는 넷뿐이고 저마다 읽는 곳이 있다.
  is-a       경로 생성의 타입 매칭 (상위 타입만 적어도 하위 타입을 받는다)
  about      대상(그룹) 판정 · 말이 안 되는 경로 차단 · 화면 점선
  hasInput   경로 생성
  hasOutput  경로 생성 · 실행 가능 판정

화면의 선도 원천이 둘이다.
  실선 — recipe 에 실제로 이어져 있는 노드 쌍. "이렇게 실행할 수 있다"
  점선 — 온톨로지 edges 의 about. "이것은 저것에 관한 것이다"

**실선을 edges 에 적지 않는 이유** : 두 곳에 적으면 진실의 원천이 둘이 되고,
어긋났을 때 어느 쪽이 맞는지 알 수 없다. 실행 순서는 recipe 가 정한다.
"""

import paths
from ontology import store
from ontology.graph import (
    ABOUT,
    HAS_INPUT,
    HAS_OUTPUT,
    IS_A,
    about_of,
    ancestors,
    can_connect,
    crosses_groups,
    dotted_edges,
    group_ids,
    highlight_edges,
    inputs_of,
    is_executable,
    load_ontology,
    outputs_of,
    recipe_nodes,
    solid_edges,
    start_ids,
    type_ids,
)


def recipe_ids() -> list[str]:
    return sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))


def test_a_node_carries_only_a_name_and_a_description():
    """노드에 종류를 적지 않음.

    kind 를 적으면 관계가 이미 말하고 있는 것을 노드에 또 적는 셈이라 둘이
    조용히 어긋날 수 있음. about 이 붙은 노드에 kind: function 이 적혀 있으면
    어느 쪽이 맞는지 알 방법이 없음.

    inputs / outputs 도 마찬가지. 그건 관계라서 edges 에 적힘.
    """
    ontology = load_ontology()

    assert set(ontology) >= {"nodes", "edges"}
    assert ontology["nodes"] and ontology["edges"]

    for node_id, node in ontology["nodes"].items():
        assert set(node) == {"name", "description"}, node_id
        assert node["name"] and node["description"], node_id

    # 관계는 넷뿐이다. 늘리려면 "읽어서 무엇을 하는가" 에 답할 수 있어야 한다.
    predicates = {edge["predicate"] for edge in ontology["edges"]}
    assert predicates == {IS_A, ABOUT, HAS_INPUT, HAS_OUTPUT}, predicates

    # 관계의 양끝은 전부 실재해야 한다. 없는 노드를 가리키면 그 관계는
    # 파일에는 있는데 화면에도 경로에도 나타나지 않는다.
    for edge in ontology["edges"]:
        assert edge["from"] in ontology["nodes"], edge
        assert edge["to"] in ontology["nodes"], edge


def test_a_nodes_character_comes_from_its_relations():
    """세 부류로 갈리고 서로 겹치지 않음.

    데이터 노드는 받지도 내놓지도 않음. 그 자체로 존재하는 것.
    그룹 노드도 마찬가지지만 about 의 대상으로 등장한다는 점이 다름.
    """
    all_ids = set(store.nodes())
    groups = set(group_ids())
    functions = {nid for nid in all_ids if is_executable(nid)}
    data = all_ids - groups - functions

    assert groups and functions and data
    assert not groups & functions, "그룹이면서 실행할 수 있는 노드는 없다"

    for group_id in groups:
        assert not inputs_of(group_id) and not outputs_of(group_id), group_id

    for node_id in functions:
        assert outputs_of(node_id), node_id

    # 경로의 시작점이 되는 데이터 노드가 있어야 한다. 하나도 없으면 recipe 가
    # 아무것도 만들어지지 않는다.
    assert [nid for nid in data if not inputs_of(nid)]


def test_a_general_node_accepts_subtypes_through_the_is_a_chain():
    """상위 타입 한 줄만 적어도 하위 타입을 받음. is-a 를 두는 이유.

    프레임 추출은 "영상" 만 받는다고 적혀 있는데 승강장 CCTV 영상도 궤도
    검측차 영상도 받음. 하위 타입이 생길 때마다 기존 노드를 고치지 않아도
    된다는 뜻.

    반대 방향은 안 됨. "영상" 을 내놓는 노드를 "승강장 CCTV 영상" 만 받는
    노드에 이을 수는 없음. 그 영상이 승강장 것이라는 보장이 없음.
    """
    assert "video" in ancestors("platform_cctv_video")
    assert ancestors("video") == [], "최상위 타입은 조상이 없다"
    assert "platform_cctv_video" not in ancestors("video"), "방향이 뒤집혔다"

    assert inputs_of("extract_frames") == ["video"], "이 검사의 전제가 깨졌다"
    assert can_connect("platform_cctv_video", "extract_frames")
    assert can_connect("track_car_cctv_video", "extract_frames")

    # 같은 타입끼리도 이어진다.
    assert can_connect("extract_frames", "analyze_congestion")

    # 타입이 아예 다르면 안 이어진다.
    assert not can_connect("extract_frames", "generate_word")
    # 상위 -> 하위 는 안 된다. is-a 를 양방향으로 타면 여기서 통과해버린다.
    assert not can_connect("track_inspection_doc", "extract_frames")


def test_only_concrete_data_can_start_a_path():
    """경로는 손에 잡히는 데이터로 시작함. 형식으로는 시작할 수 없음.

    "영상" 은 형식이지 데이터가 아님. 그것을 시작점으로 삼으면
    "영상으로 프레임을 추출하고 혼잡도를 분석한다" 는 recipe 가 만들어지는데,
    사람이 그걸 골라도 어느 영상인지 아무 데도 안 적혀 있음. 실행하려는
    순간 막히고, 그때는 이미 menu 에 실려 있음.

    조용히 깨지는 자리. "받는 것도 내놓는 것도 없는 노드" 로 시작점을 잡으면
    형식 노드가 전부 여기 걸림.
    """
    starts = set(start_ids())
    types = set(type_ids())

    assert starts, "시작점이 없으면 recipe 가 하나도 안 만들어진다"
    assert types, "형식이 없으면 이 검사가 무력하다"

    assert not starts & types, f"형식이 시작점에 섞였다: {starts & types}"
    assert not starts & set(group_ids()), "그룹이 시작점에 섞였다"
    assert not [nid for nid in starts if is_executable(nid)]

    # 형식은 실제로 존재하는 노드들이다 — 없는 것을 뺐다고 통과하면 안 된다.
    assert {"video", "image", "analysis"} <= types
    assert "platform_cctv_video" in starts


def test_an_is_a_cycle_does_not_hang(isolated_workspace):
    """온톨로지에 순환이 적혀도 화면은 돌아야 함.

    사람이 손으로 적는 파일이라 순환은 언제든 생김. 온톨로지가 잘못 적히는
    것보다 화면이 안 도는 것이 더 나쁨. 시연 중에 서버가 멈춤.
    """
    store.append_edge("video", "platform_cctv_video", IS_A)

    found = ancestors("platform_cctv_video")

    assert "video" in found
    assert len(found) == len(set(found)), "같은 조상을 두 번 담았다"


def test_nodes_connected_in_a_recipe_become_solid_edges():
    """실선은 "타입이 맞는다" 가 아니라 "recipe 에 실제로 있다" 로 정함.

    타입만 보면 생성 노드가 내놓은 문서를 다시 문서 분석에 넣을 수 있어 순환이
    생김. recipe 를 근거로 삼으면 실제로 실행하는 연결만 남음.

    라벨이 없음. 예전에는 두 노드가 무엇을 주고받는지 인터페이스 이름으로
    담았는데, 이제 그 데이터가 경로 안에 노드로 들어 있음.
    """
    edges = solid_edges()

    from_recipes = []
    for recipe_id in recipe_ids():
        chain = recipe_nodes(recipe_id)
        from_recipes += list(zip(chain, chain[1:]))

    assert set(edges) == set(from_recipes)
    assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in edges)

    # 같은 쌍이 여러 recipe 에 나와도 한 번만 담긴다.
    repeated = [pair for pair in set(from_recipes) if from_recipes.count(pair) > 1]
    assert repeated, "중복 제거를 검증하려면 두 recipe 에 나오는 쌍이 있어야 한다"
    assert edges.count(repeated[0]) == 1


def test_only_about_relations_become_dotted_edges():
    """점선은 about 뿐. is-a 와 hasInput / hasOutput 은 그리지 않음.

    셋 다 그리면 17개 노드에 24개 선이 얽혀 무엇이 무엇에 관한 것인지 안 보임.
    화면이 답해야 하는 질문은 "이 경로가 무엇에 관한 것인가" 하나.

    점선은 방향이 없음. (a, b) 와 (b, a) 를 둘 다 담으면 선이 겹쳐 그려지므로
    쌍을 정렬해 한 번만 담음.
    """
    written = load_ontology()["edges"]
    about = [e for e in written if e["predicate"] == ABOUT]
    edges = dotted_edges()

    assert about, "about 이 없으면 이 검사가 무력하다"
    assert len(edges) == len(about)

    for pair, labels in edges.items():
        assert list(pair) == sorted(pair), f"정렬되지 않은 쌍: {pair}"
        assert (pair[1], pair[0]) not in edges, f"양방향 중복: {pair}"
        assert pair[0] != pair[1]
        assert labels == [ABOUT], pair

    for edge in about:
        assert tuple(sorted((edge["from"], edge["to"]))) in edges, edge

    # is-a 로만 이어진 쌍은 점선에 없어야 한다. 이게 실제 판별력이다 —
    # 술어를 안 걸러도 위 개수 검사는 통과할 수 있다.
    only_is_a = [
        tuple(sorted((e["from"], e["to"])))
        for e in written
        if e["predicate"] == IS_A
    ]
    assert only_is_a, "is-a 가 없으면 이 검사가 무력하다"
    for pair in only_is_a:
        assert pair not in edges, f"is-a 가 점선으로 샜다: {pair}"

    # about 의 대상은 전부 그룹이다. 그룹의 정의가 곧 이것이다.
    assert {pair[0] for pair in edges} | {pair[1] for pair in edges} >= set(group_ids())


def test_a_recipe_becomes_an_ordered_path():
    """실행 경로는 집합이 아니라 리스트.

    순번 라벨(1, 2, 3)을 붙이려면 순서가 남아야 하고, recipe 에 루프가 생겨
    같은 엣지를 두 번 지날 때 집합은 그것을 하나로 뭉개버림.
    """
    groups = set(group_ids())
    assert groups, "그룹이 없으면 아래 검사가 무력하다"

    for recipe_id in recipe_ids():
        chain = recipe_nodes(recipe_id)
        edges = highlight_edges(recipe_id)

        assert isinstance(edges, list)
        assert edges == list(zip(chain, chain[1:]))
        assert len(edges) == max(len(chain) - 1, 0)

        # 그룹은 실행할 수 없다. 섞이면 아무것도 내놓지 않아 경로가 끊긴다.
        assert not groups & set(chain), (recipe_id, chain)

        # 데이터로 시작한다. 뒤집히면 경로가 거꾸로 그려진다.
        assert not is_executable(chain[0]), recipe_id
        for frm, to in edges:
            assert can_connect(frm, to), (recipe_id, frm, to)


def test_a_path_that_crosses_subjects_is_blocked():
    """★ 대상을 넘나드는 경로는 등록되지 않음. 이것이 그 판정.

    승강장 CCTV 로 궤도 균열을 찾는 경로는 타입상 만들 수 있지만 화각이
    안 맞음. registry 가 이 판정으로 그런 경로를 버림. 파일이 안 생기고
    화면에도 안 나옴.

    넘나든다의 정의 : 대상이 붙은 노드가 둘 이상인데 공통 대상이 하나도 없음.
    하나 이하면 거짓. 어긋날 상대가 없음. 이 조건이 넓어지면 멀쩡한 경로가
    조용히 사라지므로 양쪽을 다 못 박음.
    """
    assert crosses_groups(
        ["platform_cctv_video", "extract_frames", "detect_track_crack"]
    )

    # 실제 recipe 는 하나도 넘나들지 않는다. 넘나드는 것은 등록되지 않기 때문이다.
    for recipe_id in recipe_ids():
        assert not crosses_groups(recipe_nodes(recipe_id)), recipe_id

    # 대상이 붙은 노드가 하나뿐이면 넘나드는 것이 아니다. 비교할 상대가 없다.
    assert not crosses_groups(["platform_cctv_video", "extract_frames"])
    assert not crosses_groups([])

    # 한 노드가 여러 대상에 관한 것일 수 있다. 승강장 CCTV 영상은 승강장에도
    # CCTV 에도 관한 것이라, 그 교집합으로 걸러진다.
    assert len(about_of("platform_cctv_video")) > 1
    assert not crosses_groups(["platform_cctv_video", "track_car_cctv_video"]), (
        "둘 다 CCTV 에 관한 것이라 통해야 한다"
    )


def test_an_unknown_recipe_is_empty_not_an_error():
    """파일이 없으면 예외 대신 빈 결과. 화면이 죽는 것보다 나음."""
    assert recipe_nodes("recipe_999") == []
    assert highlight_edges("recipe_999") == []
