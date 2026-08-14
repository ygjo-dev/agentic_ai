"""대상 : demo/api/main.py — POST /render 의 등록 장면 색

**★ 완성된 SVG 를 본다.** build_dot 에 인자를 더할 때 단위 테스트만 두면
조립부가 그 인자를 안 넘겨도 전부 통과한다 — group_attrs · review_edges 에서
두 번 당했다. 여기서는 /render 응답의 SVG 문자열을 직접 읽는다.

색 하나가 뜻 하나다.

    분홍  새 노드 테두리       (NEW_COLOR)
    보라  새로 생긴 관계(점선)  (NEW_DOTTED_COLOR)
    주황  새 실행 경로 — 고른 것(PATH_NEW) · 빠진 것(PATH_NEW_DIM)
    teal  발화 해석 결과       (HIGHLIGHT_COLOR) — **등록 장면에는 없다**

등록을 실제로 하지는 않는다. 노드를 진짜 등록하면 layout.json 에 좌표가
쓰여 저장소 파일이 바뀐다. 대신 실제 온톨로지의 노드 · 점선 · recipe 로
등록 응답의 모양만 만든다 — 보는 것은 색이고, 색은 어느 recipe 든 같은
규칙으로 칠해진다.
"""

import re
import shutil

import pytest
from fastapi.testclient import TestClient

import demo.api.main as backend_main
from demo.graph_svg import build
from demo.graph_svg.dot import (
    HIGHLIGHT_COLOR,
    NEW_COLOR,
    NEW_DOTTED_COLOR,
    PATH_NEW,
    PATH_NEW_DIM,
)
from demo.api.services.ontology_service import recipe_ids
from ontology.graph import recipe_nodes

pytestmark = pytest.mark.skipif(
    shutil.which("neato") is None, reason="graphviz 가 설치되어 있지 않다"
)


# 끝노드가 갈리는 조합을 고른다. 셋 다 같은 곳에서 끝나면 변형이 한 벌뿐이라
# "좁히면 나머지가 옅어진다" 를 검사할 수 없다.
#
# **번호를 적지 않는다.** 여기 필요한 성질은 "끝나는 곳이 서로 다른 recipe 셋"
# 하나뿐인데, 번호는 온톨로지가 바뀌면 통째로 밀린다. 밀린 번호를 그대로 두면
# 끝노드가 겹쳐 변형이 줄고 검사가 조용히 무력해진다.
#
# 이 값들은 진짜로 등록한 결과가 아니라 /render 에 넘길 mark 를 짓는 재료다.
# 다만 recipe 자체는 실재해야 한다 — recipe_nodes 와 /render 가 파일을 읽는다.
def _by_endpoint(count: int) -> dict[str, str]:
    """끝노드 -> recipe id. 끝노드가 겹치는 것은 첫 번째만 남기고 count 개까지."""
    found: dict[str, str] = {}
    for recipe_id in recipe_ids():
        chain = recipe_nodes(recipe_id)
        if chain and chain[-1] not in found:
            found[chain[-1]] = recipe_id
        if len(found) == count:
            break
    return found


BY_ENDPOINT = _by_endpoint(3)
REGISTERED = list(BY_ENDPOINT.values())

# 좁힐 때 누를 끝노드. 가장 짧은 경로의 끝을 고른다 — 좁히면 짙은 엣지가
# 반드시 줄어드는 것이 보장된다.
NARROW_TO = min(BY_ENDPOINT, key=lambda node: len(recipe_nodes(BY_ENDPOINT[node])))

# 등록 응답에서 그리기가 쓰는 것만 줄인 형태. render_service 가 그대로 받는다.
MARK = {
    "nodes": ["generate_ppt"],
    "solid": [],
    "dotted": [("detect_track_crack", "group_track")],
    "accepted": build.chain_edges([recipe_nodes(r) for r in REGISTERED]),
}


@pytest.fixture
def client():
    build.clear_cache()
    return TestClient(backend_main.app)


@pytest.fixture
def registered(client):
    """노드를 등록한 직후의 화면 한 벌."""
    response = client.post(
        "/render",
        json={"mode": "register", "recipe_ids": REGISTERED, "mark": MARK},
    )
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def resolved(client):
    """발화를 해석한 직후의 화면 한 벌. 같은 후보, 다른 장면."""
    response = client.post(
        "/render",
        json={"mode": "resolve", "recipe_ids": REGISTERED, "mark": None},
    )
    assert response.status_code == 200
    return response.json()


# Graphviz 는 색을 소문자로 낸다. 상수는 대문자라 비교 전에 맞춘다.
def used(colour: str, svg: str) -> bool:
    return colour.lower() in svg.lower()


def edges_of_colour(svg: str, colour: str) -> set[str]:
    """그 색으로 칠해진 엣지 이름들. 화살표 폴리곤은 같은 이름이라 접힌다."""
    found = set()
    for block in re.findall(r'<g id="edge\d+" class="edge">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>(.*?)</title>", block, re.S)
        if title and colour.lower() in block.lower():
            found.add(title.group(1))
    return found


def nodes_of_colour(svg: str, colour: str) -> set[str]:
    found = set()
    for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>(.*?)</title>", block, re.S)
        if title and colour.lower() in block.lower():
            found.add(title.group(1))
    return found


def coordinates(svg: str) -> dict[str, tuple[float, float]]:
    coords = {}
    for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>([a-z_]+)</title>", block)
        pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
        if title and pos:
            coords[title.group(1)] = (float(pos.group(1)), float(pos.group(2)))
    return coords


def canvas(svg: str) -> str:
    return re.search(r'viewBox="([^"]+)"', svg).group(1)


# ------------------------------------------------------------ 검사가 무력하지 않은지
def test_the_registration_actually_draws_paths(registered):
    """변형이 여러 벌이고 경로가 실제로 칠해져야 아래 검사들이 뜻을 가진다."""
    variants = registered["variants"]

    assert len(BY_ENDPOINT) == 3, f"끝노드가 갈리는 recipe 가 셋이 안 된다: {BY_ENDPOINT}"
    assert set(variants) >= {"", *BY_ENDPOINT}
    assert edges_of_colour(variants[""], PATH_NEW)


# ------------------------------------------------------------ 등록 직후
def test_every_new_path_starts_bright(registered):
    """아무것도 안 누른 상태다. 전부 짙은 주황이어야 한다."""
    whole = registered["variants"][""]

    assert used(PATH_NEW, whole)
    assert not used(PATH_NEW_DIM, whole)


def test_narrowing_dims_the_other_recipes(registered):
    """끝노드를 누르면 그것으로 끝나는 경로만 짙게 남는다."""
    variants = registered["variants"]
    narrowed = variants[NARROW_TO]

    assert used(PATH_NEW, narrowed)
    assert used(PATH_NEW_DIM, narrowed)
    assert len(edges_of_colour(narrowed, PATH_NEW)) < len(
        edges_of_colour(variants[""], PATH_NEW)
    )


def test_what_is_new_never_changes_between_variants(registered):
    """"무엇이 새로 생겼는가" 는 어느 후보를 보든 같은 사실이다."""
    variants = list(registered["variants"].values())

    marked_nodes = [nodes_of_colour(svg, NEW_COLOR) for svg in variants]
    marked_dotted = [edges_of_colour(svg, NEW_DOTTED_COLOR) for svg in variants]

    assert marked_nodes[0], "새 노드 테두리가 하나도 없다 — 검사가 무력하다"
    assert marked_dotted[0], "새 점선이 하나도 없다 — 검사가 무력하다"
    assert all(found == marked_nodes[0] for found in marked_nodes)
    assert all(found == marked_dotted[0] for found in marked_dotted)


def test_the_register_scene_has_no_teal(registered):
    """teal 은 발화 해석 결과의 색이다. 등록 화면에 섞이면 뜻이 흐려진다."""
    for name, svg in [("top", registered["top"]), *registered["variants"].items()]:
        assert not used(HIGHLIGHT_COLOR, svg), f"{name or '전체'} 변형에 teal 이 있다"


# ------------------------------------------------------------ 해석 장면은 그대로
def test_the_resolve_scene_still_uses_teal(resolved):
    """장면이 갈렸을 뿐 발화 해석은 예전과 똑같이 그린다."""
    whole = resolved["variants"][""]

    assert used(HIGHLIGHT_COLOR, whole)
    assert not used(PATH_NEW, whole)
    assert not used(PATH_NEW_DIM, whole)


# ------------------------------------------------------------ 배치
def test_all_variants_share_the_layout(registered):
    """좁혀도 노드가 움직이거나 캔버스가 달라지면 안 된다."""
    variants = list(registered["variants"].values())
    base = coordinates(variants[0])

    assert base, "노드 좌표를 하나도 못 읽었다 — 검사가 무력하다"
    for svg in variants[1:]:
        assert coordinates(svg) == base
        assert canvas(svg) == canvas(variants[0])
