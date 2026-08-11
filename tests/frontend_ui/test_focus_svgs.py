"""하단 해석 그래프 SVG 변형 검증.

핵심 성질 : 어느 변형이든 노드 좌표와 캔버스 크기가 같아야 한다.
좌표 고정 + neato -n 이라 구조적으로 보장되지만, 그 구조가 깨지면 화면이
클릭할 때마다 흔들린다.
"""

import re
import shutil

import pytest

from frontend import config
from frontend.components.focus_panel import embed_json, focus_html, focus_inputs
from frontend.components.graph_section import (
    build_focus_svgs,
    ensure_positions,
    focus_key,
)

pytestmark = pytest.mark.skipif(
    shutil.which("neato") is None, reason="graphviz 가 설치되어 있지 않다"
)

GRAPH = {
    "version": "test",
    "interfaces": ["MediaData", "AnalysisResult", "DocumentData"],
    "nodes": {
        "load_cctv": {"name": "승강장 CCTV 불러오기", "description": "", "inputs": [],
                      "outputs": ["MediaData"], "properties": {"source": "cctv"}},
        "load_car": {"name": "검측차 이미지 불러오기", "description": "", "inputs": [],
                     "outputs": ["MediaData"], "properties": {"source": "cctv"}},
        "analyze": {"name": "승강장 혼잡도 분석", "description": "", "inputs": ["MediaData"],
                    "outputs": ["AnalysisResult"], "properties": {}},
        "generate_word": {"name": "Word 생성", "description": "", "inputs": ["AnalysisResult"],
                          "outputs": ["DocumentData"], "properties": {}},
    },
    "solid_edges": [
        {"from": "load_cctv", "to": "analyze", "interface": "MediaData"},
        {"from": "load_car", "to": "analyze", "interface": "MediaData"},
        {"from": "analyze", "to": "generate_word", "interface": "AnalysisResult"},
    ],
    "dotted_edges": [{"a": "load_cctv", "b": "load_car", "labels": ["source: cctv"]}],
}


def steps(*ids):
    return [{"node_id": i, "name": GRAPH["nodes"][i]["name"], "out_interface": "X"} for i in ids]


PATHS = {
    "recipe_a": steps("load_cctv", "analyze"),
    "recipe_b": steps("load_car", "analyze"),
    "recipe_c": steps("load_cctv", "analyze", "generate_word"),
}
IDS = ["recipe_a", "recipe_b", "recipe_c"]


@pytest.fixture
def positions(tmp_path, monkeypatch):
    from frontend import layout_store

    monkeypatch.setattr(layout_store, "LAYOUT_PATH", tmp_path / "layout.json")
    return ensure_positions(GRAPH)


@pytest.fixture
def svgs(positions):
    build_focus_svgs.clear()
    return build_focus_svgs(
        _graph=GRAPH, _positions=positions, _paths=PATHS,
        _recipe_ids=tuple(IDS), version="v1",
    )


def node_coords(svg: str) -> dict:
    out = {}
    for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>([a-z_]+)</title>", block)
        pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
        if title and pos:
            out[title.group(1)] = (round(float(pos.group(1)), 2), round(float(pos.group(2)), 2))
    return out


def canvas(svg: str):
    return re.search(r'<svg width="(\d+)pt" height="(\d+)pt"', svg).groups()


def embedded_data(html: str) -> dict:
    """문서 안의 const DATA = {...} 를 되읽는다."""
    import json

    match = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    assert match, "JS 데이터를 찾지 못했다."
    # embed_json 이 "</" 를 "<\/" 로 바꿔둔 것을 되돌린다.
    return json.loads(match.group(1).replace("<\\/", "</"))


# ------------------------------------------------------------ 변형 키
def test_variant_keys_are_all_plus_last_nodes(svgs):
    assert set(svgs) == {"", "analyze", "generate_word"}


def test_every_variant_is_an_svg(svgs):
    for key, svg in svgs.items():
        assert "<svg" in svg, key


# ------------------------------------------------------------ 핵심 성질
def test_all_variants_share_the_same_node_coordinates(svgs):
    """클릭할 때마다 노드가 움직이면 어디를 보던 중이었는지 잃는다."""
    base = node_coords(svgs[""])

    assert len(base) == len(GRAPH["nodes"])
    for key, svg in svgs.items():
        assert node_coords(svg) == base, key


def test_all_variants_share_the_same_canvas(svgs):
    base = canvas(svgs[""])

    for key, svg in svgs.items():
        assert canvas(svg) == base, key


# ------------------------------------------------------------ 후보 0개
@pytest.fixture
def empty_svgs(positions):
    """실행 전 · NO_MATCH. 후보가 없어도 지도는 떠 있어야 한다."""
    build_focus_svgs.clear()
    return build_focus_svgs(
        _graph=GRAPH, _positions=positions, _paths={}, _recipe_ids=(), version="v0",
    )


def test_no_candidates_still_draws_the_map(empty_svgs):
    """하단이 텅 비면 화면이 고장난 것처럼 보인다. 설명글을 없앴으니 더 그렇다."""
    assert set(empty_svgs) == {""}
    assert "<svg" in empty_svgs[""]


def test_no_candidates_draws_every_node(empty_svgs):
    assert len(node_coords(empty_svgs[""])) == len(GRAPH["nodes"])


def test_no_candidates_highlights_nothing(empty_svgs):
    """지도는 떠 있는데 켜지는 길이 하나도 없다 — 문구 없이 그림으로 읽힌다."""
    assert config.HIGHLIGHT_COLOR.lower() not in empty_svgs[""].lower()


def test_empty_map_shares_the_candidate_coordinates(empty_svgs, svgs):
    """Run 을 눌러도 지도가 안 흔들려야 한다."""
    assert node_coords(empty_svgs[""]) == node_coords(svgs[""])


# ------------------------------------------------------------ 강조 내용
def test_narrowed_to_one_recipe_gets_order_numbers(svgs):
    """하나로 좁혀지면 순번이 붙는다 — build_dot 의 기존 규칙."""
    assert ">1<" in svgs["generate_word"]


def test_multiple_survivors_have_no_order_numbers(svgs):
    """여러 경로가 같은 엣지를 공유하면 순번이 겹쳐 읽을 수 없다."""
    assert ">1<" not in svgs["analyze"]


def test_every_variant_highlights_something(svgs):
    for key, svg in svgs.items():
        assert config.HIGHLIGHT_COLOR.lower() in svg.lower(), key


# ------------------------------------------------------------ 캐시 키
def test_key_reflects_the_candidate_set():
    assert focus_key(["r1", "r2"], None) != focus_key(["r1"], None)


def test_key_ignores_candidate_order():
    """순서만 다른데 캐시가 헛돌면 같은 그림을 매번 다시 만든다."""
    assert focus_key(["r1", "r2"], None) == focus_key(["r2", "r1"], None)


def test_key_reflects_the_mode():
    mark = {"nodes": ["x"], "solid": [], "dotted": []}

    assert focus_key(["r1"], None) != focus_key(["r1"], mark)


# ------------------------------------------------------------ view 해석
def test_focus_inputs_uses_highlight_colour_for_resolve():
    view = {"kind": "resolve", "result": {"recipe_id": "r1", "candidate_recipe_ids": ["r1"],
                                          "paths": PATHS}}
    _, ids, color = focus_inputs(view)

    assert ids == ["r1"]
    assert color == config.HIGHLIGHT_COLOR


def test_focus_inputs_uses_new_colour_for_register():
    view = {"kind": "register", "result": {"recipe_ids": ["r9"], "paths": PATHS}}
    _, ids, color = focus_inputs(view)

    assert ids == ["r9"]
    assert color == config.NEW_COLOR


@pytest.mark.parametrize("view", [None, {}, {"error": "터졌다"}], ids=["없음", "빈값", "오류"])
def test_focus_inputs_of_nothing(view):
    paths, ids, _ = focus_inputs(view)

    assert paths == {} and ids == []


# ------------------------------------------------------------ iframe 문서
@pytest.fixture
def html(svgs):
    from frontend.components.path_panel import chips_markup
    from frontend import focus

    variants = focus.focus_variants(PATHS, IDS)
    return focus_html(
        svgs,
        {k: chips_markup(PATHS, ids, "#fff") for k, ids in variants.items()},
        0.6,
        focus.last_nodes(PATHS, IDS),
    )


# 웹 스토리지 금지 테스트는 지웠다. 다른 실행 환경의 제약을 그대로 옮겨온
# 것이었고, Streamlit 컴포넌트 iframe 의 샌드박스는
# `allow-same-origin allow-scripts allow-downloads` 라 세션 저장소가 동작한다.
# 지금 지켜야 할 것은 "안 쓴다" 가 아니라 "막혀도 안 죽는다" 이고,
# 그것은 tests/frontend_ui/test_zoom.py 가 본다.


def test_iframe_holds_both_panes(html):
    assert 'id="graph"' in html and 'id="list"' in html
    assert "<svg" in html


def test_chip_list_scrolls_when_it_overflows(html):
    """넘치면 잘리게 두지 않는다."""
    assert "overflow-y: auto" in html


def test_iframe_embeds_every_variant(html):
    """JS 는 고르기만 한다. 변형은 파이썬이 다 만들어 넣는다."""
    data = embedded_data(html)

    assert set(data["svgs"]) == {"", "analyze", "generate_word"}
    assert set(data["chips"]) == set(data["svgs"])


def test_iframe_marks_only_last_nodes_clickable(html):
    """마지막이 아닌 노드를 누르면 남는 recipe 가 0개가 되어 화면이 빈다."""
    data = embedded_data(html)

    assert set(data["clickable"]) == {"analyze", "generate_word"}
    assert "load_cctv" not in data["clickable"]
    assert "load_car" not in data["clickable"]


def test_narrowed_chip_list_shrinks(html):
    """그래프를 좁히면 목록도 같이 줄어든다."""
    data = embedded_data(html)

    assert data["chips"][""].count('class="chain"') == 3
    assert data["chips"]["analyze"].count('class="chain"') == 2
    assert data["chips"]["generate_word"].count('class="chain"') == 1


def test_iframe_click_handler_exists(html):
    assert "addEventListener" in html
    assert "picked" in html


def test_embed_json_cannot_close_the_script_tag():
    """값 안의 </script> 가 문서를 거기서 끊으면 화면이 깨진다."""
    payload = embed_json({"x": "</script><script>alert(1)</script>"})

    assert "</script>" not in payload
    assert "<\\/script>" in payload


def test_embed_json_round_trips():
    import json

    payload = {"a": ["b", "c"], "한글": 1}

    assert json.loads(embed_json(payload)) == payload
