"""대상 : app/ui/components/network.py — 그래프가 **라이브러리**로 그려지는가

★ 2026-09-06 에 Graphviz SVG + 자체 JS 를 vis-network(pyvis)로 갈았다.
그 전에는 서버가 완성한 정지 SVG 위에 우리가 쓴 JS 가 CSS transform 을 얹어
확대 · 끌기를 흉내 냈다. 노드를 집어 옮길 수는 없었다.

여기서 지키는 것은 다섯이다.

    라이브러리로 그린다     vis-network 가 문서에 실려 있고 우리가 캔버스를
                            직접 그리지 않는다
    손으로 움직인다         노드 끌기 · 화면 끌기 · 휠 확대가 켜져 있다
    지도가 안 흔들린다      물리 시뮬레이션이 꺼져 있고 서버 좌표를 그대로 쓴다
    뜻이 안 샌다            노드 · 엣지 수가 원본과 같고 강조가 유실되지 않는다
    파이썬이 칠한다         JS 가 색 · 굵기 규칙을 하나도 모른다

브라우저를 안 띄운다. 만들어진 문서와 파이썬이 만든 스타일 표만 본다 —
실제 손맛은 사람이 화면에서 본다.
"""

import json
import re

import pytest

from app.api.services.streamlit import screen_service
from app.ui.components import network


@pytest.fixture(scope="module")
def colors():
    return screen_service.screen_payload()["colors"]


@pytest.fixture(scope="module")
def model():
    """실제 온톨로지로 만든 모형. 경로가 하나라 순번도 함께 온다."""
    return screen_service.render("resolve", [_two_step_recipe()])["network"]


def _two_step_recipe():
    """단계가 정확히 둘인 recipe 하나. 순번이 붙는 자리를 잡으려는 것."""
    for recipe_id in screen_service.recipe_ids():
        if len(screen_service.path_of(recipe_id)) == 3:
            return recipe_id
    return screen_service.recipe_ids()[0]


# ── 라이브러리로 그린다 ──────────────────────────────────────────────


def test_the_document_ships_the_graph_library_itself(model, colors):
    """정지 그림이 아니라 라이브러리가 그린다. 그 증거가 문서 안에 있음."""
    html = network.network_html(model, colors, top=True, height=400)

    assert "vis-network" in html
    assert "DataSet" in html


def test_the_library_comes_from_the_package_not_the_internet(model, colors):
    """CDN 을 안 부름. 시연 장소의 망을 안 믿음.

    pyvis 는 제 패키지 안에 vis-network 를 들고 있고 cdn_resources="in_line"
    이 그것을 문서에 넣는다. 우리가 번들을 베껴 오지 않는다.
    """
    html = network.network_html(model, colors, top=True, height=400)
    바깥 = re.findall(r"https?://[^\"\'\s)]+", html)

    assert not [u for u in 바깥 if "jsdelivr" in u or "cdnjs" in u or "unpkg" in u]


# ── 손으로 움직인다 ─────────────────────────────────────────────────


def test_the_three_gestures_are_all_on():
    """노드 끌기 · 화면 끌기 · 휠 확대. 요구가 그 셋임."""
    opts = json.loads(network.options())["interaction"]

    assert opts["dragNodes"] is True
    assert opts["dragView"] is True
    assert opts["zoomView"] is True


def test_hovering_a_node_tells_what_it_is(model, colors):
    """노드 설명이 문서에 실림. 예순 남짓이라 이름만으로는 안 읽힘.

    라이브러리가 노드를 JSON 으로 실으면서 한글을 \\uXXXX 로 이스케이프한다.
    그래서 원문이 아니라 이스케이프한 꼴로 찾는다 — 원문으로 찾으면 실려
    있는데도 못 찾는다.
    """
    html = network.network_html(model, colors, top=True, height=400)
    설명 = model["nodes"]["geocode_place"]["title"]

    assert 설명
    assert json.dumps(설명, ensure_ascii=True)[1:-1] in html


# ── 지도가 안 흔들린다 ───────────────────────────────────────────────


def test_the_library_never_lays_the_map_out_again():
    """물리 시뮬레이션이 꺼져 있음.

    켜면 노드를 등록할 때마다 지도가 통째로 다시 흔들려서 「기존 노드가
    0.0000pt 움직인다」는 시연의 핵심 장면이 없어진다.
    """
    assert json.loads(network.options())["physics"]["enabled"] is False


def test_every_node_is_pinned_at_the_coordinate_the_server_gave(model, colors):
    """좌표를 라이브러리가 다시 잡지 않음. 서버의 layout.json 그대로임."""
    net = network.build_network(model, colors, top=True, height=400)
    놓인_것 = {node["id"]: (node["x"], node["y"]) for node in net.nodes}

    for node_id, (x, y) in model["positions"].items():
        # y 는 뒤집는다. Graphviz 는 위로, vis-network 는 아래로 y 가 큼
        assert 놓인_것[node_id] == (x * network.COORD_SCALE, -y * network.COORD_SCALE)


# ── 뜻이 안 샌다 ────────────────────────────────────────────────────


def test_the_node_count_matches_the_source(model, colors):
    """한 노드도 안 빠지고 안 늘어남."""
    net = network.build_network(model, colors, top=False, height=400)

    assert len(net.nodes) == len(model["nodes"])


def test_the_edge_count_matches_the_source(model, colors):
    """상단은 점선만, 하단은 점선과 실선을 함께 그림. SVG 때의 규칙 그대로임."""
    top = network.build_network(model, colors, top=True, height=400)
    bottom = network.build_network(model, colors, top=False, height=400)

    assert len(top.edges) == len(model["dotted"])
    assert len(bottom.edges) == len(model["dotted"]) + len(model["solid"])


def test_the_chosen_path_is_the_only_thing_wearing_the_highlight(model, colors):
    """강조가 유실되지도, 엉뚱한 데 묻지도 않음."""
    강조 = {tuple(e) for e in model["variants"][""]["highlight"]}
    assert 강조, "이 시험은 경로가 있는 모형이라야 뜻이 있다"

    칠해진_것 = {
        tuple(style["id"].split(network.ORDER_SEP))
        for style in network.solid_styles(model, colors, "")
        if style["color"] == colors["highlight"]
    }

    assert 칠해진_것 == 강조


def test_the_highlighted_nodes_get_a_thicker_border(model, colors):
    """경로 위의 노드가 눈에 띄어야 함. 엣지만 칠하면 끝점이 안 읽힘."""
    강조_노드 = set(model["variants"][""]["nodes"])
    굵은_것 = {
        style["id"] for style in network.node_styles(model, colors, "")
        if style["borderWidth"] == network.NODE_BORDER_WIDTH_MARKED
    }

    assert 굵은_것 == 강조_노드


def test_a_single_path_is_numbered_in_order(model, colors):
    """경로가 정확히 하나면 순번이 붙음. 방향을 화살촉만으로 읽기 어려움."""
    붙은_것 = [
        style["label"] for style in network.solid_styles(model, colors, "")
        if style["label"]
    ]

    assert sorted(붙은_것) == [str(n) for n in range(1, len(붙은_것) + 1)]


def test_narrowing_to_a_last_node_keeps_the_other_variants_available(model, colors):
    """변형마다 스타일 한 벌. 누르면 그중 하나로 갈아끼움."""
    patches = network.variant_patches(model, colors)

    assert set(patches) == set(model["variants"])
    for 칸 in patches.values():
        assert len(칸["edges"]) == len(model["solid"])
        assert len(칸["nodes"]) == len(model["nodes"])


# ── 파이썬이 칠한다 ─────────────────────────────────────────────────


def test_the_script_knows_no_colour_at_all(model, colors):
    """**JS 는 고르기만 한다.** 색 · 굵기 규칙이 두 곳으로 갈라지면 안 됨.

    예전 SVG 판의 「파이썬이 변형을 만들고 JS 는 고르기만 한다」와 같은 규칙이다.
    """
    script = network.PICK_SCRIPT

    assert "#" not in script.replace("</", "")
    assert "highlight" not in script
    assert "update" in script


def test_the_bottom_document_carries_the_graph_and_the_chips_together(model, colors):
    """나누면 클릭마다 Streamlit 재실행이라 반응이 굼뜸."""
    html = network.bottom_html(
        model, colors, {"": "<div id=chip>칩</div>"},
        left_ratio=0.62, clickable=[], height=500,
    )

    assert 'id="wrap"' in html
    assert 'id="list"' in html
    assert "mynetwork" in html


def test_a_chip_markup_with_a_closing_script_tag_cannot_break_the_document(model, colors):
    """값 안의 "</" 를 그대로 두면 문서가 거기서 끊김."""
    html = network.bottom_html(
        model, colors, {"": "</script><b>깨짐</b>"},
        left_ratio=0.6, clickable=[], height=400,
    )

    assert "</script><b>" not in html


# ── 창구 계약 ───────────────────────────────────────────────────────


def test_the_screen_contract_did_not_move():
    """★ 그래프를 갈면서 /screen 을 안 건드렸다.

    라이브러리로 갈아도 백엔드가 내는 것은 그대로여야 한다. 화면을 편하게
    하자고 도메인 창구를 굽히지 않는다는 규칙이 여기서 지켜진다.
    노드 · 엣지 모형은 이미 /screen 이 갖고 있었다 — 서버가 그리게 된 뒤로
    아무도 안 읽던 세 칸이 그것이고, 이번에 다시 읽히게 됐다.
    """
    payload = screen_service.screen_payload()

    assert set(payload) == {
        "version", "colors", "types", "nodes", "solid_edges", "dotted_edges",
    }


def test_the_static_svg_path_is_still_there():
    """정지 그림을 지우지 않았다.

    dev/tools/export_graph.py 가 그것을 쓴다. interactive 로 갈았다고 내보내기
    길까지 없애면 보도자료 · 문서에 넣을 그림을 만들 데가 사라진다.
    """
    payload = screen_service.render("plain")

    assert "<svg" in payload["top"]
    assert "<svg" in payload["variants"][""]
