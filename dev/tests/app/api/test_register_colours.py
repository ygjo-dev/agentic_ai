"""대상 : POST /render 의 등록 장면 색

**★ 화면에 실제로 실리는 스타일 표를 본다.** 서버 payload 만 보면 조립부가
그 칸을 안 읽어도 전부 통과한다 — group_attrs · review_edges 에서 두 번 당했다.
그래서 /render 응답을 `network.node_styles` · `network.solid_styles` 에 그대로
넣어 나온 색을 읽는다. 그 둘이 vis-network 에 넘어가는 바로 그 표다.

색 하나가 뜻 하나다.

    분홍  새 노드 테두리 · 새로 생긴 관계(점선)  (NEW_COLOR)
    주황  새 실행 경로 — 고른 것(PATH_NEW) · 빠진 것(PATH_NEW_DIM)
    teal  발화 해석 결과                        (HIGHLIGHT_COLOR) — **등록 장면에는 없다**

등록을 실제로 하지는 않는다. 노드를 진짜 등록하면 layout.json 에 좌표가
쓰여 저장소 파일이 바뀐다. 대신 실제 온톨로지의 노드 · 점선 · recipe 로
등록 응답의 모양만 만든다 — 보는 것은 색이고, 색은 어느 recipe 든 같은
규칙으로 칠해진다.
"""

import re

import pytest

from app.api.services.streamlit import screen_service
from app.api.services.streamlit.screen_service import recipe_ids
from app.ui.components import network
from app.ui.graph.dot import (
    HIGHLIGHT_COLOR,
    NEW_COLOR,
    PATH_NEW,
    PATH_NEW_DIM,
)
from ontology.graph import recipe_nodes


# 끝노드가 갈리는 조합을 고른다. 다 같은 곳에서 끝나면 좁혀도 짙은 엣지가
# 안 줄어 "좁히면 나머지가 옅어진다" 를 검사할 수 없다.
#
# **번호를 적지 않는다.** 여기 필요한 성질은 "끝나는 곳이 서로 다른 recipe 둘"
# 하나뿐인데, 번호는 온톨로지가 바뀌면 통째로 밀린다. 밀린 번호를 그대로 두면
# 끝노드가 겹쳐 검사가 조용히 무력해진다.
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


BY_ENDPOINT = _by_endpoint(2)
REGISTERED = list(BY_ENDPOINT.values())

# 좁힐 때 누를 후보. 가장 짧은 경로를 고른다 — 좁히면 짙은 엣지가 반드시 준다.
NARROW_TO = min(REGISTERED, key=lambda recipe_id: len(recipe_nodes(recipe_id)))

# 등록 응답에서 그리기가 쓰는 것만 줄인 형태. screen_service 가 그대로 받는다.
#
# ★ **등록 장면인지는 여기 안 적는다.** 2026-09-06 까지는 "accepted" 키의
# 유무가 그 표시였는데, 지금은 mode="register" 가 그것을 명시한다.
MARK = {
    "nodes": ["find_cctv"],
    "solid": [],
    "dotted": [("find_cctv", "group_transport")],
}


@pytest.fixture(scope="module")
def colors():
    return screen_service.screen_payload()["colors"]


@pytest.fixture(scope="module")
def registered():
    """노드를 등록한 직후의 화면 한 벌."""
    return screen_service.render("register", REGISTERED, MARK)["network"]


@pytest.fixture(scope="module")
def resolved():
    """발화를 해석한 직후의 화면 한 벌. 같은 후보, 다른 장면."""
    return screen_service.render("resolve", REGISTERED)["network"]


def edges_of_colour(model, colors, variant, colour) -> set[str]:
    """그 색으로 칠해진 엣지 (from, to) 들."""
    return {
        (style["from"], style["to"])
        for style in network.solid_styles(model, colors, variant)
        if style["color"] == colour
    }


def nodes_of_colour(model, colors, variant, colour) -> set[str]:
    """그 색 테두리를 가진 노드 id 들. 하단 기준."""
    return {
        style["id"]
        for style in network.node_styles(model, colors, variant, top=False)
        if style["color"]["border"] == colour
    }


def dotted_of_colour(model, colors, colour) -> set[tuple]:
    """그 색 점선. 새 점선은 build_network 와 같은 규칙으로 고른다."""
    return {
        tuple(entry["edge"])
        for entry in model.get("dotted") or ()
        if (colors["new"] if entry.get("new") else colors["dotted_bottom"]) == colour
    }


# ------------------------------------------------------------ 검사가 무력하지 않은지
def test_the_registration_actually_draws_paths(registered, colors):
    """변형이 여러 벌이고 경로가 실제로 칠해져야 아래 검사들이 뜻을 가짐."""
    assert len(BY_ENDPOINT) == 2, f"끝노드가 갈리는 recipe 가 둘이 안 된다: {BY_ENDPOINT}"
    assert set(registered["variants"]) == {"", *REGISTERED}
    assert registered["registering"] is True
    assert edges_of_colour(registered, colors, "", PATH_NEW)


# ------------------------------------------------------------ 등록 직후
def test_every_new_path_starts_bright(registered, colors):
    """아무것도 안 누른 상태. 전부 짙은 주황이어야 함."""
    assert edges_of_colour(registered, colors, "", PATH_NEW)
    assert edges_of_colour(registered, colors, "", PATH_NEW_DIM) == set()


def test_narrowing_dims_the_other_recipes(registered, colors):
    """후보를 누르면 그것의 경로만 짙게 남음."""
    assert edges_of_colour(registered, colors, NARROW_TO, PATH_NEW)
    assert edges_of_colour(registered, colors, NARROW_TO, PATH_NEW_DIM)
    assert len(edges_of_colour(registered, colors, NARROW_TO, PATH_NEW)) < len(
        edges_of_colour(registered, colors, "", PATH_NEW)
    )


def test_what_is_new_never_changes_between_variants(registered, colors):
    """"무엇이 새로 생겼는가" 는 어느 후보를 보든 같은 사실."""
    변형들 = list(registered["variants"])
    새_노드 = [nodes_of_colour(registered, colors, key, NEW_COLOR) for key in 변형들]

    assert 새_노드[0], "새 노드 테두리가 하나도 없다 — 검사가 무력하다"
    assert all(found == 새_노드[0] for found in 새_노드)

    # 새 점선은 변형별 표가 아니라 모형 한 곳에 있다 — 구조상 안 갈린다.
    assert dotted_of_colour(registered, colors, NEW_COLOR), "새 점선이 하나도 없다"


def test_the_register_scene_has_no_teal(registered, colors):
    """teal 은 발화 해석 결과의 색. 등록 화면에 섞이면 뜻이 흐려짐."""
    for key in registered["variants"]:
        assert edges_of_colour(registered, colors, key, HIGHLIGHT_COLOR) == set()
        assert nodes_of_colour(registered, colors, key, HIGHLIGHT_COLOR) == set()

    # 상단은 어느 장면에서도 해석 결과를 안 보여준다.
    assert colors["highlight"] not in network.top_html(registered, colors, height=400)


# ------------------------------------------------------------ 해석 장면은 그대로
def test_the_resolve_scene_still_uses_teal(resolved, colors):
    """장면이 갈렸을 뿐 발화 해석은 예전과 똑같이 그림."""
    assert resolved["registering"] is False
    assert edges_of_colour(resolved, colors, "", HIGHLIGHT_COLOR)
    assert edges_of_colour(resolved, colors, "", PATH_NEW) == set()
    assert edges_of_colour(resolved, colors, "", PATH_NEW_DIM) == set()


# ------------------------------------------------------------ 배치
def test_all_variants_share_the_layout(registered, colors):
    """좁혀도 노드가 움직이면 안 됨.

    ★ 좌표는 변형과 무관하게 모형 한 곳(positions)에서 온다. 그래도 화면에
    실리는 문서까지 따라가 본다 — 옛 SVG 판이 캔버스와 좌표를 맞대던 자리다.
    """
    assert registered["positions"], "좌표를 하나도 못 읽었다 — 검사가 무력하다"

    def 박힌_좌표(key):
        html = network.network_html(
            registered, colors, top=False, variant=key, height=400
        )
        return sorted(re.findall(r'"x": (-?[\d.]+), "y": (-?[\d.]+)', html))

    변형들 = list(registered["variants"])
    기준 = 박힌_좌표(변형들[0])

    assert len(기준) == len(registered["nodes"]), "좌표를 문서에서 못 읽었다"
    for key in 변형들[1:]:
        assert 박힌_좌표(key) == 기준
