"""대상 : ontology/ontology.py — 게시된 온톨로지를 읽고 관계를 답한다

예전에는 `store.py`(yaml 을 아는 자리)와 `graph.py`(관계 계산)로 나뉘어 있었고
시험도 둘이었다. 한 class 로 합치면서 시험도 합쳤다.

**노드에는 종류가 적혀 있지 않다.** 성격은 관계가 말한다 — hasOutput 이 있으면
실행할 수 있고, about 의 대상으로 등장하면 대상(그룹)이고, 둘 다 아니면 오가는
데이터다. 노드 자신이 말하는 것은 name · description 과 source(밖에서 곧장
들어오는 자리) · tool(무엇으로 실행하는가)뿐이다.

지금 지원하는 관계는 넷이고 저마다 읽는 곳이 있다. 아는 목록은
SUPPORTED_PREDICATES 가 갖는다.
  is-a       경로 생성의 타입 매칭 (상위 타입만 적어도 하위 타입을 받는다)
  about      대상(그룹) 판정 · group 호환성 계산 · 화면 점선
  hasInput   경로 생성
  hasOutput  경로 생성 · 실행 가능 판정

새 관계는 그것을 실제로 읽는 로직과 함께 더한다. 넷이라는 수 자체가
불변식인 것은 아니다.

화면의 선도 원천이 둘이다.
  실선 — recipe 에 실제로 이어져 있는 노드 쌍. "이렇게 실행할 수 있다"
  점선 — 온톨로지 edges 의 about. "이것은 저것에 관한 것이다"

**실선을 edges 에 적지 않는 이유** : 두 곳에 적으면 진실의 원천이 둘이 되고,
어긋났을 때 어느 쪽이 맞는지 알 수 없다. 실행 순서는 recipe 가 정한다.

**쓰는 API 가 없다는 것도 여기서 지킨다.** 게시 자산을 고치는 것은 등록 저장소
일이고, `AGENTIC_ARTIFACT_ROOT` 가 공유 Registry 를 가리킨 배포에서 이쪽 코드가
남의 파일을 고칠 수 있으면 안 된다.
"""

import ast
import pathlib

import yaml

import paths
from ontology import ONTOLOGY, SUPPORTED_PREDICATES, Ontology
from ontology.ontology import ABOUT, IS_A


def recipe_ids() -> list[str]:
    """recipe id 를 파일에서 직접 센다. 재는 대상으로 대상을 재지 않으려는 것."""
    return sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))


def extended(tmp_path, nodes=(), edges=()) -> Ontology:
    """실제 온톨로지에 노드 · 관계를 얹은 임시 사본을 읽는 Ontology.

    입력  nodes  [(node_id, {name, description}), ...]
          edges  [(from, to, predicate), ...]
    규칙  노드는 nodes 블록 끝(edges 앞)에, 관계는 파일 끝에 붙임. 파일에 적힌
          형식 그대로라 다시 읽으면 얹은 것이 보임
    제약  runtime 에 쓰는 API 를 두지 않는다.
          예전에는 store.append_node · append_edge 가 이 일을 했는데 등록
          기능이 밖으로 나간 뒤로 부르는 곳이 시험뿐이었다. 지어내는 온톨로지가
          필요한 것은 시험이므로 그 손은 시험이 갖는다
    """
    text = paths.ONTOLOGY_PATH.read_text(encoding="utf-8")

    block = "".join(
        f"\n  {node_id}:\n    name: {node['name']}\n    description: {node['description']}\n"
        for node_id, node in nodes
    )
    head, marker, tail = text.partition("\nedges:")
    text = head.rstrip("\n") + "\n" + block + marker + tail
    text = text.rstrip("\n") + "\n" + "".join(
        f"  - {{ from: {frm}, to: {to}, predicate: {predicate} }}\n"
        for frm, to, predicate in edges
    )

    path = tmp_path / "ontology.yaml"
    path.write_text(text, encoding="utf-8", newline="\n")
    return Ontology(path)


# ── 읽기 ────────────────────────────────────────────────────────────


def test_reading_gives_the_ontology_as_written(tmp_path):
    """읽기는 원문 그대로. 파일이 바뀌면 다음 읽기가 새 내용을 봐야 함.

    캐시 키가 파일 원문 바이트라서 그렇다. mtime 으로 바꾸면 파일을 복사하거나
    같은 초 안에 여러 번 쓸 때 내용을 못 가른다.
    """
    path = tmp_path / "ontology.yaml"
    path.write_text(paths.ONTOLOGY_PATH.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    ontology = Ontology(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert ontology.document() == raw
    assert ontology.nodes() == raw["nodes"]
    assert ontology.edges() == list(raw["edges"])
    assert ontology.raw_bytes() == path.read_bytes()

    # 파일이 바뀌면 바로 보인다. 캐시가 앞선 파싱을 붙들고 있으면 안 된다.
    path.write_text(
        path.read_text(encoding="utf-8").replace("\nedges:", "\n  probe_node:\n    name: 재는 노드\n    description: 캐시가 내용으로 갈리는지 잰다.\n\nedges:", 1),
        encoding="utf-8",
        newline="\n",
    )
    assert "probe_node" in ontology.nodes()

    # 경로를 안 주면 paths 가 가리키는 게시 자산을 본다. 프로덕션이 그렇게 부른다.
    assert Ontology().document() == yaml.safe_load(
        paths.ONTOLOGY_PATH.read_text(encoding="utf-8")
    )
    assert ONTOLOGY.path == paths.ONTOLOGY_PATH
    assert ONTOLOGY.recipes_dir == paths.RECIPES_DIR


def test_the_ontology_module_only_knows_yaml_and_paths():
    """도메인이 서비스 · 저장소 설정을 알면 순환이 생기고 교체할 때 뜯을 곳이 늘어난다."""
    source = pathlib.Path(Ontology.__module__.replace(".", "/") + ".py")

    imported = set()
    for node in ast.walk(ast.parse((paths.REPO_ROOT / source).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])

    assert imported == {"yaml", "paths", "pathlib"}, imported


def test_the_ontology_has_no_way_to_write_the_published_artifacts():
    """**읽기 전용이다.** 등록 · 게시는 agentic_ai 밖의 저장소 일이다.

    `AGENTIC_ARTIFACT_ROOT` 가 공유 Registry 를 가리키면 이 저장소의 코드가 남의
    게시 파일을 고칠 수 있는 길이 하나도 없어야 한다. 낱말로 막지 않고
    **파일을 여는 호출을 판다** — 이름을 바꿔 되살리면 낱말 검사는 그냥 샌다.
    """
    source = pathlib.Path(Ontology.__module__.replace(".", "/") + ".py")
    tree = ast.parse((paths.REPO_ROOT / source).read_text(encoding="utf-8"))

    쓰는_것 = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"write_text", "write_bytes", "unlink", "mkdir", "rename", "touch"}:
                쓰는_것.append(f"{node.func.attr}:{node.lineno}")
            if node.func.attr == "open":
                쓰는_것.append(f"open:{node.lineno}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            쓰는_것.append(f"open:{node.lineno}")

    assert 쓰는_것 == [], "온톨로지 도메인에 쓰는 길이 생겼다:\n  " + "\n  ".join(쓰는_것)

    # 옛 등록 잔재가 이름으로 되살아나는 것도 막는다.
    되살아난_것 = [
        name for name in ("append_node", "append_edge", "node_block", "edge_line", "save", "publish")
        if hasattr(Ontology, name) or hasattr(ONTOLOGY, name)
    ]
    assert 되살아난_것 == [], f"쓰는 API 가 되살아났다: {되살아난_것}"


# ── 노드와 관계 ──────────────────────────────────────────────────────


def test_a_node_carries_no_kind_and_no_relation():
    """노드에 종류를 적지 않음. 받고 내놓는 것도 적지 않음.

    kind 를 적으면 관계가 이미 말하고 있는 것을 노드에 또 적는 셈이라 둘이
    조용히 어긋날 수 있음. about 이 붙은 노드에 kind: function 이 적혀 있으면
    어느 쪽이 맞는지 알 방법이 없음.

    inputs / outputs 도 마찬가지. 그건 관계라서 edges 에 적힘.
    source 와 tool 은 관계가 아니라 그 노드 자신의 사실이라 노드에 둠.
    tool.parameters 가 semantic 입력을 도구 칸에 넣지만 hasInput 을 대신하지 않음.
    """
    ontology = ONTOLOGY.document()

    assert set(ontology) == {"version", "nodes", "edges"}, "새 top-level 을 만들지 않는다"
    assert ontology["nodes"] and ontology["edges"]

    for node_id, node in ontology["nodes"].items():
        assert {"name", "description"} <= set(node) <= {"name", "description", "source", "tool"}, node_id
        assert node["name"] and node["description"], node_id

    # 파일에 적힌 관계는 전부 시스템이 지원한다고 선언한 것이어야 한다.
    # 관계를 늘리는 것 자체는 막지 않는다 — 늘리려면 SUPPORTED_PREDICATES 에
    # 이름을 더해야 하고, 그 자리가 곧 "읽어서 무엇을 하는가" 에 답하는 자리다.
    predicates = {edge["predicate"] for edge in ontology["edges"]}
    unsupported = predicates - set(SUPPORTED_PREDICATES)
    assert not unsupported, f"읽는 곳이 없는 관계다: {sorted(unsupported)}"

    # 반대쪽도 본다. 선언만 해 두고 쓰이지 않는 관계는 뜻을 잃는다 —
    # "읽는 곳이 없어진 관계는 지운다" 가 이 자리다.
    # ★ is-a 만 예외다. 값의 출처를 말하던 노드가 source 로 들어가며 0줄이 됐고,
    #   읽는 곳(ancestors)은 남아 형식 계층의 하위 타입이 생기면 그대로 쓴다.
    unused = set(SUPPORTED_PREDICATES) - predicates
    assert unused <= {IS_A}, f"선언했지만 온톨로지가 안 쓰는 관계다: {sorted(unused)}"

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
    all_ids = set(ONTOLOGY.nodes())
    groups = set(ONTOLOGY.group_ids())
    functions = {nid for nid in all_ids if ONTOLOGY.is_executable(nid)}
    data = all_ids - groups - functions

    assert groups and functions and data
    assert not groups & functions, "그룹이면서 실행할 수 있는 노드는 없다"

    for group_id in groups:
        assert not ONTOLOGY.inputs_of(group_id) and not ONTOLOGY.outputs_of(group_id), group_id

    for node_id in functions:
        assert ONTOLOGY.outputs_of(node_id), node_id

    # 경로의 시작점이 되는 데이터 노드가 있어야 한다. 하나도 없으면 recipe 가
    # 아무것도 만들어지지 않는다.
    assert [nid for nid in data if not ONTOLOGY.inputs_of(nid)]


def test_a_general_node_accepts_subtypes_through_the_is_a_chain(tmp_path):
    """상위 타입 한 줄만 적어도 하위 타입을 받음. is-a 를 두는 이유.

    지금 온톨로지에는 is-a 가 한 줄도 없어 형식 계층의 하위 타입을 얹어 잰다.
    장소 좌표 변환은 "장소 이름" 만 받는다고 적혀 있는데 "역 이름" 도 받음.
    하위 타입이 생길 때마다 기존 노드를 고치지 않아도 된다는 뜻.

    반대 방향은 안 됨. "장소 이름" 을 내놓는 노드를 "역 이름" 만 받는 노드에
    이을 수는 없음. 그 이름이 역이라는 보장이 없음.
    방향은 바로 아래 ancestors 두 줄이 못 박음.
    """
    ontology = extended(
        tmp_path,
        nodes=[("station_name", {"name": "역 이름", "description": "사람이 부르는 역 이름."})],
        edges=[("station_name", "place_name", IS_A)],
    )

    assert "place_name" in ontology.ancestors("station_name")
    assert ontology.ancestors("place_name") == [], "최상위 타입은 조상이 없다"
    assert "station_name" not in ontology.ancestors("place_name"), "방향이 뒤집혔다"

    assert ontology.inputs_of("geocode_place") == ["place_name"], "이 검사의 전제가 깨졌다"
    assert ontology.can_connect("station_name", "geocode_place")

    # 같은 타입끼리도 이어진다. 장소 좌표 변환이 내놓는 지도 범위를 CCTV 조회가 받는다.
    assert ontology.can_connect("geocode_place", "find_cctv")

    # 타입이 아예 다르면 안 이어진다.
    assert not ontology.can_connect("find_cctv", "geocode_place")


def test_only_a_node_with_an_outside_source_can_start_a_path():
    """경로는 밖에서 곧장 값이 들어오는 노드(source)로 시작함.

    "목록" 은 source 가 없는 형식임. 그것을 시작점으로 삼으면 "목록으로 …" recipe 가
    만들어지는데, 사람이 그걸 골라도 어느 목록인지 아무 데도 안 적혀 있음. 실행하려는
    순간 막히고, 그때는 이미 menu 에 실려 있음.

    source 는 유일한 생성원이 아님. 지점 좌표는 화면에서도 오고 장소 좌표 변환도
    내놓으므로 형식이면서 시작점임. 「형식이면 시작점이 아니다」로 되돌리면 화면에서
    시작하는 경로가 전부 사라짐.
    """
    starts = set(ONTOLOGY.start_ids())
    types = set(ONTOLOGY.type_ids())
    nodes = ONTOLOGY.nodes()

    assert starts, "시작점이 없으면 recipe 가 하나도 안 만들어진다"
    assert starts == {nid for nid, node in nodes.items() if node.get("source")}

    assert not starts & set(ONTOLOGY.group_ids()), "그룹이 시작점에 섞였다"
    assert not [nid for nid in starts if ONTOLOGY.is_executable(nid)]

    # 형식이면서 시작점인 것과 형식이기만 한 것이 둘 다 있다 — 한쪽만 있으면
    # source 로 가르는지 형식으로 가르는지 이 검사가 못 가른다.
    assert {"place_name", "point", "map_extent"} <= starts & types
    assert {"item_list", "station_id", "admin_code"} <= types - starts


def test_an_is_a_cycle_does_not_hang(tmp_path):
    """온톨로지에 순환이 적혀도 화면은 돌아야 함.

    사람이 손으로 적는 파일이라 순환은 언제든 생김. 온톨로지가 잘못 적히는
    것보다 화면이 안 도는 것이 더 나쁨. 시연 중에 서버가 멈춤.
    """
    ontology = extended(
        tmp_path,
        edges=[("point", "place_name", IS_A), ("place_name", "point", IS_A)],
    )

    found = ontology.ancestors("point")

    assert "place_name" in found
    assert len(found) == len(set(found)), "같은 조상을 두 번 담았다"


def test_nodes_connected_in_a_recipe_become_solid_edges():
    """실선은 "타입이 맞는다" 가 아니라 "recipe 에 실제로 있다" 로 정함.

    타입만 보면 생성 노드가 내놓은 문서를 다시 문서 분석에 넣을 수 있어 순환이
    생김. recipe 를 근거로 삼으면 실제로 실행하는 연결만 남음.

    라벨이 없음. 예전에는 두 노드가 무엇을 주고받는지 인터페이스 이름으로
    담았는데, 이제 그 데이터가 경로 안에 노드로 들어 있음.
    """
    edges = ONTOLOGY.solid_edges()

    from_recipes = []
    for recipe_id in recipe_ids():
        chain = ONTOLOGY.recipe_nodes(recipe_id)
        from_recipes += list(zip(chain, chain[1:]))

    assert set(edges) == set(from_recipes)
    assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in edges)

    # 같은 쌍이 여러 recipe 에 나와도 한 번만 담긴다.
    repeated = [pair for pair in set(from_recipes) if from_recipes.count(pair) > 1]
    assert repeated, "중복 제거를 검증하려면 두 recipe 에 나오는 쌍이 있어야 한다"
    assert edges.count(repeated[0]) == 1


def test_only_about_relations_become_dotted_edges(tmp_path):
    """점선은 about 뿐. is-a 와 hasInput / hasOutput 은 그리지 않음.

    셋 다 그리면 17개 노드에 24개 선이 얽혀 무엇이 무엇에 관한 것인지 안 보임.
    화면이 답해야 하는 질문은 "이 경로가 무엇에 관한 것인가" 하나.

    점선은 방향이 없음. (a, b) 와 (b, a) 를 둘 다 담으면 선이 겹쳐 그려지므로
    쌍을 정렬해 한 번만 담음.
    """
    # 지금 온톨로지에는 is-a 가 없어 하나를 얹어 판별력을 만든다.
    ontology = extended(tmp_path, edges=[("district_code", "keyword", IS_A)])

    written = ontology.document()["edges"]
    about = [e for e in written if e["predicate"] == ABOUT]
    edges = ontology.dotted_edges()

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
    assert {pair[0] for pair in edges} | {pair[1] for pair in edges} >= set(ontology.group_ids())


# ── recipe ──────────────────────────────────────────────────────────


def test_a_recipe_becomes_an_ordered_path():
    """실행 경로는 집합이 아니라 리스트.

    부르는 순서가 남아야 하고, recipe 에 루프가 생겨 같은 엣지를 두 번 지날
    때 집합은 그것을 하나로 뭉개버림.
    """
    groups = set(ONTOLOGY.group_ids())
    assert groups, "그룹이 없으면 아래 검사가 무력하다"

    for recipe_id in recipe_ids():
        chain = ONTOLOGY.recipe_nodes(recipe_id)
        edges = list(zip(chain, chain[1:]))

        assert len(edges) == max(len(chain) - 1, 0)

        # 그룹은 실행할 수 없다. 섞이면 아무것도 내놓지 않아 경로가 끊긴다.
        assert not groups & set(chain), (recipe_id, chain)

        # 밖에서 들어오는 데이터로 시작한다. 뒤집히면 경로가 거꾸로 그려진다.
        assert not ONTOLOGY.is_executable(chain[0]), recipe_id
        assert chain[0] in set(ONTOLOGY.start_ids()), recipe_id
        for frm, to in edges:
            assert ONTOLOGY.can_connect(frm, to), (recipe_id, frm, to)

        # 부를 노드는 시작 데이터 노드를 뺀 나머지다. 그것이 값을 준비할 뿐인 자리다.
        assert ONTOLOGY.executable_in(recipe_id) == [
            node_id for node_id in chain if ONTOLOGY.is_executable(node_id)
        ]


def test_a_path_carries_the_names_in_order():
    """경로는 노드 id 와 사람이 읽는 이름과 다음에 건네는 것을 순서대로 들고 있다.

    이름을 붙이는 곳이 여기뿐이다. 두 곳에서 붙이면 조용히 어긋난다.
    """
    everything = ONTOLOGY.paths_for(recipe_ids())

    assert set(everything) == set(recipe_ids())
    for recipe_id, chain in everything.items():
        assert chain == ONTOLOGY.path_of(recipe_id), recipe_id
        assert [entry["node_id"] for entry in chain] == ONTOLOGY.recipe_nodes(recipe_id)
        assert all(entry["name"] and entry["out_type"] for entry in chain), recipe_id

    # 중복은 접고 차례는 유지한다.
    두_번 = ONTOLOGY.paths_for(["recipe_002", "recipe_004", "recipe_002"])
    assert list(두_번) == ["recipe_002", "recipe_004"]


def test_a_path_that_crosses_subjects_is_blocked():
    """★ 대상을 넘나드는 경로는 등록되지 않음. 이것이 그 판정.

    철도 구간의 지도 범위로 충전소를 찾는 경로는 타입상 만들 수 있지만
    실행할 수 없음. 그런 경로는 recipe 파일로 게시되지 않아 화면에도 안 나옴.

    넘나든다의 정의 : 대상이 붙은 노드가 둘 이상인데 공통 대상이 하나도 없음.
    하나 이하면 거짓. 어긋날 상대가 없음. 이 조건이 넓어지면 멀쩡한 경로가
    조용히 사라지므로 양쪽을 다 못 박음.

    지금 온톨로지에는 대상이 둘 붙은 노드가 없어 교집합은 "둘이 같은 대상"
    으로만 잼.
    """
    assert ONTOLOGY.crosses_groups(
        ["place_name", "get_railway_section", "search_ev_stations"]
    )

    # 실제 recipe 는 하나도 넘나들지 않는다. 넘나드는 것은 등록되지 않기 때문이다.
    for recipe_id in recipe_ids():
        assert not ONTOLOGY.crosses_groups(ONTOLOGY.recipe_nodes(recipe_id)), recipe_id

    # 대상이 붙은 노드가 하나뿐이면 넘나드는 것이 아니다. 비교할 상대가 없다.
    # 범용 노드(장소 좌표 변환)는 대상이 안 붙어 이 수에 안 들어간다.
    assert not ONTOLOGY.crosses_groups(
        ["place_name", "geocode_place", "point_to_map_extent", "find_cctv"]
    )
    assert not ONTOLOGY.crosses_groups([])

    # 공통 대상이 있으면 통한다. CCTV 조회와 철도 노선 조회는 둘 다 교통이다.
    assert ONTOLOGY.about_of("find_cctv") & ONTOLOGY.about_of("get_railway_lines")
    assert not ONTOLOGY.crosses_groups(["find_cctv", "get_railway_lines"]), (
        "둘 다 교통에 관한 것이라 통해야 한다"
    )


def test_an_unknown_recipe_is_empty_not_an_error():
    """파일이 없으면 예외 대신 빈 결과. 화면이 죽는 것보다 나음."""
    assert ONTOLOGY.recipe_nodes("recipe_999") == []
    assert ONTOLOGY.path_of("recipe_999") == []
