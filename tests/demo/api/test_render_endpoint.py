"""대상 : demo/api/main.py — POST /render

demo/api/main.py 의 /render 엔드포인트 검증.

그리기가 서버로 들어왔다. 화면은 이 응답을 받아 iframe 에 넣고 고르기만 한다.

가장 중요한 것은 **변형들의 노드 좌표와 캔버스 크기가 같은지**다. 노드를 눌러
후보를 좁힐 때 좌표가 흔들리면 화면이 튀고, 보던 자리를 잃는다. 좌표를 전부
고정하고 neato -n 으로 그리므로 구조적으로 보장되지만, 그 보장이 깨지는 순간
화면에서만 드러나므로 여기서 못을 박아둔다.
"""

import re
import shutil

import pytest
from fastapi.testclient import TestClient

import paths
import demo.api.main as backend_main
from demo.graph_svg import build

pytestmark = pytest.mark.skipif(
    shutil.which("neato") is None, reason="graphviz 가 설치되어 있지 않다"
)


@pytest.fixture
def client():
    return TestClient(backend_main.app)


def existing_recipe_ids(count: int) -> list[str]:
    """지금 저장소에 있는 recipe id 를 앞에서부터.

    번호를 박아두지 않는다 — 필요한 것은 특정 recipe 가 아니라 "서로 다른
    후보 몇 개" 이고, 온톨로지를 바꾸면 번호가 통째로 달라진다.
    """
    ids = sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))
    assert len(ids) >= count, f"recipe 가 {count}개는 있어야 한다: {ids}"
    return ids[:count]


@pytest.fixture
def recipe_ids():
    """후보가 여럿인 장면을 만든다. 끝나는 노드가 서로 달라야 변형이 여러 벌 나온다."""
    from ontology.graph import recipe_nodes

    ids = sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))
    picked, endings = [], set()
    for recipe_id in ids:
        last = recipe_nodes(recipe_id)[-1]
        if last not in endings:
            endings.add(last)
            picked.append(recipe_id)
        if len(picked) == 3:
            break

    assert len(picked) == 3, f"끝나는 노드가 다른 recipe 가 셋은 있어야 한다: {ids}"
    return picked


def post(client, **body):
    response = client.post("/render", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def node_coords(svg: str) -> dict[str, tuple[float, float]]:
    """SVG 에서 노드 중심 좌표를 뽑는다."""
    coords = {}
    for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>([a-z_]+)</title>", block)
        pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
        if title and pos:
            coords[title.group(1)] = (float(pos.group(1)), float(pos.group(2)))
    return coords


def canvas(svg: str) -> str:
    """viewBox. 크기 속성은 fit_svg 가 뺐으므로 이것이 캔버스다."""
    found = re.search(r'viewBox="([^"]+)"', svg)
    return found.group(1) if found else ""


# ------------------------------------------------------------ 형태
def test_plain_returns_200(client):
    assert client.post("/render", json={"mode": "plain"}).status_code == 200


def test_contract_keys(client):
    assert set(post(client, mode="plain")) == {
        "version",
        "top",
        "variants",
        "focus",
        "chips",
    }


def test_every_mode_renders(client, recipe_ids):
    """세 장면 모두 그려져야 한다. 하나라도 빠지면 시연 중에 화면이 빈다."""
    for mode, ids in (
        ("plain", []),
        ("resolve", recipe_ids),
        ("register", recipe_ids),
    ):
        payload = post(client, mode=mode, recipe_ids=ids)
        assert payload["top"].lstrip().startswith("<?xml"), mode
        assert payload["variants"][""], mode


def test_unknown_mode_is_rejected(client):
    """오타가 조용히 plain 으로 떨어지면 '왜 강조가 안 되지' 를 한참 찾게 된다."""
    response = client.post("/render", json={"mode": "resolv"})

    assert response.status_code == 422


def test_svg_has_no_size_attributes(client):
    """폭·높이가 박혀 있으면 고정 높이 패널에서 여백이 뜨거나 잘린다."""
    payload = post(client, mode="plain")

    assert 'width="' not in payload["top"][: payload["top"].index(">", 200)]
    assert "viewBox" in payload["top"]


# ------------------------------------------------------------ 좌표 (핵심)
def test_every_variant_shares_the_node_coordinates(client, recipe_ids):
    """노드를 눌러 좁혀도 지도가 그대로여야 한다."""
    variants = post(client, mode="resolve", recipe_ids=recipe_ids)["variants"]
    assert len(variants) > 1, "후보 3개면 변형이 여러 벌 나와야 한다"

    base = node_coords(variants[""])
    assert base, "노드 좌표를 하나도 못 읽었다 — 검사가 무력하다"
    for key, svg in variants.items():
        assert node_coords(svg) == base, key


def test_every_variant_shares_the_canvas(client, recipe_ids):
    """캔버스가 달라지면 축소 배율이 바뀌어 그래프가 커졌다 작아졌다 한다."""
    variants = post(client, mode="resolve", recipe_ids=recipe_ids)["variants"]

    assert len({canvas(svg) for svg in variants.values()}) == 1


def test_top_and_bottom_share_the_coordinates(client, recipe_ids):
    """상단과 하단이 같은 지도여야 위아래가 같은 장면을 말한다."""
    payload = post(client, mode="resolve", recipe_ids=recipe_ids)

    assert node_coords(payload["top"]) == node_coords(payload["variants"][""])


def test_group_nodes_are_drawn_as_ellipses_in_both_graphs(client):
    """대상 노드가 기능 노드와 한눈에 갈려야 한다.

    build_dot 을 직접 부르는 검사만으로는 부족하다 — 조립하는 쪽(build.py)이
    group_attrs 를 안 넘기면 화면에는 그대로 사각형이 뜨는데 그 검사들은
    전부 통과한다(실제로 확인했다). 완성된 SVG 를 본다.

    상단과 하단 둘 다여야 한다. 한쪽만 바뀌면 같은 노드가 위아래에서 달라 보인다.
    """
    from demo.api.services.ontology_service import drawn_nodes
    from demo.graph_svg.dot import GROUP_COLOR, GROUP_COLOR_TOP

    # kind 는 온톨로지에 없다. 그리는 쪽이 관계를 보고 만들어 붙인다 —
    # 파일에서 읽으면 이 검사는 영원히 빈 목록을 보고 조용히 통과한다.
    nodes = drawn_nodes()
    groups = [nid for nid, node in nodes.items() if node["kind"] == "group"]
    assert groups and len(groups) < len(nodes), "group 이 없거나 전부면 검사가 무력하다"

    payload = post(client, mode="plain")

    for label, svg, color in (
        ("top", payload["top"], GROUP_COLOR_TOP),
        ("bottom", payload["variants"][""], GROUP_COLOR),
    ):
        # 타원은 정확히 group 수만큼. 기능 노드는 둥근 사각형(<path>)으로 남는다.
        assert svg.count("<ellipse") == len(groups), label
        assert svg.count('class="node"') == len(nodes), label
        assert color.lower() in svg.lower(), label


# ------------------------------------------------------------ 변형과 칩
def test_chips_and_variants_have_the_same_keys(client, recipe_ids):
    """키가 어긋나면 그래프만 좁혀지고 목록은 그대로 남는다."""
    payload = post(client, mode="resolve", recipe_ids=recipe_ids)

    assert set(payload["chips"]) == set(payload["variants"])


def test_variant_keys_are_the_last_nodes(client, recipe_ids):
    payload = post(client, mode="resolve", recipe_ids=recipe_ids)

    assert set(payload["variants"]) == {""} | set(payload["focus"]["last_nodes"])


def test_clickable_nodes_are_only_the_last_ones(client, recipe_ids):
    """마지막이 아닌 노드를 누르면 남는 recipe 가 0개라 화면이 빈다."""
    focus = post(client, mode="resolve", recipe_ids=recipe_ids)["focus"]

    assert set(focus["recipes_by_last_node"]) == set(focus["last_nodes"])
    for node_id, ids in focus["recipes_by_last_node"].items():
        assert ids, node_id


def test_chips_carry_names_not_ids(client, recipe_ids):
    """칩에 id 가 뜨면 비전공자에게는 읽히지 않는다."""
    chains = post(client, mode="resolve", recipe_ids=recipe_ids)["chips"][""]

    from ontology.graph import load_ontology

    names = {node["name"] for node in load_ontology()["nodes"].values()}
    ids = set(load_ontology()["nodes"])

    assert chains and all(chain for chain in chains)
    for chain in chains:
        for name in chain:
            assert name in names, name
            assert name not in ids, f"id 가 그대로 실렸다: {name}"


def test_plain_has_one_variant_and_no_clicks(client):
    """실행 전에는 지도만 떠 있다. 좁힐 것이 없다."""
    payload = post(client, mode="plain")

    assert list(payload["variants"]) == [""]
    assert payload["focus"]["last_nodes"] == []


# ------------------------------------------------------------ 캐시
def test_same_request_is_served_from_cache(client, recipe_ids):
    """같은 화면을 두 번 그리지 않는다. 캐시가 안 물면 Graphviz 를 매번 돈다."""
    build.clear_cache()
    first = post(client, mode="resolve", recipe_ids=recipe_ids)
    size = len(build._CACHE)

    second = post(client, mode="resolve", recipe_ids=recipe_ids)

    assert second == first
    assert len(build._CACHE) == size, "같은 요청인데 칸이 늘었다"


def test_recipe_order_does_not_split_the_cache(client):
    """후보 순서만 다른데 캐시가 헛돌면 같은 그림을 매번 다시 만든다."""
    build.clear_cache()
    first, second = existing_recipe_ids(2)
    post(client, mode="resolve", recipe_ids=[first, second])
    post(client, mode="resolve", recipe_ids=[second, first])

    assert len(build._CACHE) == 1


def test_mode_is_part_of_the_cache_key(recipe_ids):
    """같은 후보라도 장면이 다르면 다른 칸에 담겨야 한다.

    엔드포인트로 재면 무력하다 — plain 은 후보가 비어 있어서 mode 를 키에서
    빼도 후보 차이만으로 칸이 갈린다(실측으로 확인했다). 나머지를 전부 똑같이
    두고 mode 하나만 바꿔서 본다.
    """
    same = dict(version="v", layout="L", recipe_ids=recipe_ids, mark=None)

    assert build.cache_key(mode="resolve", **same) != build.cache_key(
        mode="register", **same
    )


def test_cache_is_bounded(client):
    """시연이 길어지면 조합이 계속 쌓인다."""
    build.clear_cache()
    for index in range(build.CACHE_LIMIT + 3):
        post(client, mode="resolve", recipe_ids=[f"recipe_{index:03d}"])

    assert len(build._CACHE) == build.CACHE_LIMIT


# ------------------------------------------------------------ 등록 강조
def test_register_accepts_the_raw_nodes_response(client):
    """UI 가 POST /nodes 응답을 그대로 넘긴다. 줄이는 일은 서버가 한다."""
    raw = {
        "node_id": "generate_word",
        "new_solid_edges": [{"from": "analyze_congestion", "to": "generate_word",
                             "interface": "AnalysisResult"}],
        "new_dotted_edges": [],
    }

    payload = post(client, mode="register", recipe_ids=[], mark=raw)

    assert build.mark_key(build.mark_from_registration(raw)) != "plain"
    assert payload["top"]


def test_register_mark_changes_the_picture(client):
    """강조가 그림에 반영돼야 한다. 안 그러면 등록 장면이 평소와 똑같아 보인다."""
    plain = post(client, mode="plain")
    marked = post(client, mode="register", mark={
        "node_id": "generate_word", "new_solid_edges": [], "new_dotted_edges": [],
    })

    assert marked["top"] != plain["top"]


def test_marking_does_not_move_a_node(client):
    """강조는 색과 굵기만 바꾼다. 좌표가 움직이면 등록 순간 지도가 튄다."""
    plain = post(client, mode="plain")
    marked = post(client, mode="register", mark={
        "node_id": "generate_word", "new_solid_edges": [], "new_dotted_edges": [],
    })

    assert node_coords(marked["top"]) == node_coords(plain["top"])


PENDING_MARK = {
    "node_id": "generate_word", "new_solid_edges": [], "new_dotted_edges": [],
    "pending": [{
        "chain": ["track_inspection_doc", "find_weak_section", "generate_ppt"],
        "steps": [],
    }],
}


def test_pending_paths_never_reach_the_relation_map(client):
    """검토 표시는 실선 위에 얹는 것이다. 실선이 없는 상단에는 갈 곳이 없다.

    상단은 "무엇이 무엇과 관련되는가" 만 말한다. 아직 답이 아닌 것은 경로를
    보여주는 자리(하단)에 있는 편이 맞다.
    """
    from demo.graph_svg.dot import NEW_COLOR, REVIEW_COLOR

    plain = post(client, mode="plain")

    reviewed = post(client, mode="register", mark=PENDING_MARK)

    assert REVIEW_COLOR.lower() != NEW_COLOR.lower(), "이 검사의 전제가 깨졌다"
    assert REVIEW_COLOR.lower() not in reviewed["top"].lower()
    assert node_coords(reviewed["top"]) == node_coords(plain["top"])


# ------------------------------------------------------------ 상단 = 관계 지도
def edge_blocks(svg: str) -> list[str]:
    return re.findall(r'<g id="edge\d+" class="edge">(.*?)</g>', svg, re.S)


def test_the_top_graph_draws_only_dotted_edges(client):
    """★ 상단은 관계 지도다 — 점선만 그린다.

    build_dot 만 검사하면 조립부(build.py)가 draw_solid 를 안 넘겨도 통과한다
    (작업 17·18 에서 두 번 반복된 실패 모드다). 완성된 SVG 를 본다.

    Graphviz 는 style=dashed 를 stroke-dasharray="5,2" 로 내보낸다. 상단의 모든
    엣지가 그것을 갖고 있어야 하고, 실선 색(EDGE_COLOR_TOP)은 아예 없어야 한다.
    """
    from demo.graph_svg.dot import EDGE_COLOR_TOP

    payload = post(client, mode="plain")
    edges = edge_blocks(payload["top"])

    assert edges, "엣지를 하나도 못 읽었다 — 검사가 무력하다"
    for block in edges:
        assert "stroke-dasharray" in block, block[:200]
    assert EDGE_COLOR_TOP.lower() not in payload["top"].lower()


def test_the_bottom_graph_still_draws_the_solid_edges(client):
    """실선이 하단에서도 사라지면 실행 경로를 그릴 바탕이 없어진다."""
    payload = post(client, mode="plain")

    solid = [b for b in edge_blocks(payload["variants"][""]) if "dasharray" not in b]

    assert solid, "하단 배경 실선이 사라졌다"
    assert len(solid) < len(edge_blocks(payload["variants"][""])), "점선도 있어야 한다"


def test_the_top_dotted_lines_are_thicker_than_the_bottom_ones(client):
    """상단은 점선이 유일한 선이라 주인공이다. 하단 점선은 배경이다."""
    def widths(svg):
        return {
            float(found.group(1))
            for block in edge_blocks(svg)
            if "dasharray" in block
            for found in [re.search(r'stroke-width="([\d.]+)"', block)]
            if found
        }

    payload = post(client, mode="plain")
    top, bottom = widths(payload["top"]), widths(payload["variants"][""])

    assert len(top) == 1 and len(bottom) == 1, (top, bottom)
    assert min(top) > min(bottom), (top, bottom)


def test_dropping_the_solid_edges_keeps_the_top_and_bottom_aligned(client):
    """★ 실선을 빼도 좌표와 캔버스가 그대로여야 한다.

    상단과 하단은 한 화면에 함께 뜨고 같은 좌표 파일을 쓴다. 상단에서만 선을
    걷어냈는데 배치가 달라지면 위아래가 서로 다른 자리를 가리킨다.
    """
    payload = post(client, mode="plain")

    assert node_coords(payload["top"]) == node_coords(payload["variants"][""])
    assert canvas(payload["top"]) == canvas(payload["variants"][""])
