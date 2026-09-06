"""대상 : app/ui/components/network.py — 그래프가 **라이브러리**로 그려지는가

★ 2026-09-06 에 Graphviz SVG + 자체 JS 를 vis-network(pyvis)로 갈았다.
그 전에는 서버가 완성한 정지 SVG 위에 우리가 쓴 JS 가 CSS transform 을 얹어
확대 · 끌기를 흉내 냈다. 노드를 집어 옮길 수는 없었다.

여기서 지키는 것은 여섯이다.

    라이브러리로 그린다     vis-network 가 문서에 실려 있고 우리가 캔버스를
                            직접 그리지 않는다
    손으로 움직인다         노드 끌기 · 화면 끌기 · 휠 확대가 켜져 있다
    지도가 안 흔들린다      물리 시뮬레이션이 꺼져 있고 서버 좌표를 그대로 쓴다
    두 패널의 역할이 다르다  상단은 중립 overview · 하단만 해석 결과를 보여준다
    좌표는 하나 화면은 둘    끌린 좌표는 나눠 갖고 카메라는 따로 논다
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


def test_only_the_bottom_shows_what_the_utterance_chose(model, colors):
    """★ 상단은 중립 overview 임. 하단만 해석 결과를 보여줌.

    둘 다 강조를 받으면 같은 그림이 두 번 뜨고 두 패널이 각각 무엇을
    말하는지 구분되지 않음. 옛 top_svg / variant_svgs 가 나누던 역할임.
    """
    강조_노드 = set(model["variants"][""]["nodes"])
    assert 강조_노드, "이 시험은 경로가 있는 모형이라야 뜻이 있다"

    def 굵은_것(top):
        return {s["id"] for s in network.node_styles(model, colors, "", top=top)
                if s["borderWidth"] == network.NODE_BORDER_WIDTH_MARKED}

    assert 굵은_것(top=False) == 강조_노드
    assert 굵은_것(top=True) == set()
    assert colors["highlight"] not in network.top_html(model, colors, height=400)


def test_the_chosen_path_is_the_only_thing_the_bottom_lights_up(model, colors):
    """강조가 유실되지도, 엉뚱한 데 묻지도 않음. 흐르는 표시도 같은 것을 씀.

    색이나 굵기로 고르지 않음 — 서버가 갈라 보낸 highlight 를 그대로 씀.
    옛 판이 class="flow" 손잡이로 고르던 자리와 같음.
    """
    강조 = {tuple(e) for e in model["variants"][""]["highlight"]}

    칠해진_것 = {
        tuple(style["id"].split(">"))
        for style in network.solid_styles(model, colors, "")
        if style["color"] == colors["highlight"]
    }
    흐르는_것 = {(s["from"], s["to"]) for s in network.flowing_edges(model, "")}

    assert 칠해진_것 == 강조
    assert 흐르는_것 == 강조   # ★ 화살촉은 마지막에만 있어도 흐름은 모든 구간에


def test_the_subject_nodes_keep_their_own_border_on_both_panels(model, colors):
    """★ 대상(교통 · 선거 · 인구 · 전기차 충전) 노드가 기능 노드와 갈려야 함.

    실행할 수 있는 것과 개념은 다른 것임. 옛 dot.GROUP_ATTRS 그대로 —
    타원 · 굵기 2 · 테두리와 글자가 같은 금색. 상단은 한 단계 낮은 금색임.
    """
    대상 = {nid for nid, node in model["nodes"].items() if node["kind"] == "group"}
    assert 대상, "온톨로지에 대상 노드가 있어야 이 시험이 뜻이 있다"

    for top, 금색 in ((False, colors["group"]), (True, colors["group_top"])):
        표 = {s["id"]: s for s in network.node_styles(model, colors, "", top=top)}
        for node_id in 대상:
            style = 표[node_id]
            assert style["shape"] == network.GROUP_SHAPE
            assert style["borderWidth"] == network.GROUP_BORDER_WIDTH
            assert style["color"]["border"] == 금색
            assert style["font"]["color"] == 금색


def test_the_graph_carries_no_sequence_numbers(model, colors):
    """★ 그래프 위에 숫자를 안 올림. 실행 방향은 흐르는 표시가 말함.

    「쉰셋째」에 이미 순번(xlabel)을 뺐고 그 자리를 흐름 표시가 맡았음.
    """
    assert "order" not in model["variants"][""]
    assert not any("label" in s for s in network.solid_styles(model, colors, ""))


def test_narrowing_to_a_last_node_keeps_the_other_variants_available(model, colors):
    """변형마다 스타일 한 벌. 누르면 그중 하나로 갈아끼움."""
    patches = network.variant_patches(model, colors)

    assert set(patches) == set(model["variants"])
    for 칸 in patches.values():
        assert len(칸["edges"]) == len(model["solid"])
        assert len(칸["nodes"]) == len(model["nodes"])
        # 좁혀 들어갈 대상과 흐를 엣지도 변형마다 함께 온다
        assert set(칸["focus"]) <= set(model["nodes"])


# ── 파이썬이 칠한다 ─────────────────────────────────────────────────


def test_the_script_knows_no_colour_at_all(model, colors):
    """**JS 는 고르기만 한다.** 색 · 굵기 규칙이 두 곳으로 갈라지면 안 됨.

    예전 SVG 판의 「파이썬이 변형을 만들고 JS 는 고르기만 한다」와 같은 규칙이다.
    """
    script = network.GRAPH_SCRIPT

    assert "highlight" not in script
    assert "update" in script
    # 색은 하나도 없다. 흐르는 표시의 흰색도 파이썬이 넘긴다.
    # (그냥 "#" 을 세면 #list 같은 선택자에 걸리므로 색 꼴만 본다)
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", script)
    assert network.FLOW_SHEEN not in script
    # 굵기 · 배율도 파이썬이 넘긴다
    assert "CFG.arrowScale" in script and "CFG.edgeWidth" in script


def test_the_bottom_document_carries_the_graph_and_the_chips_together(model, colors):
    """나누면 클릭마다 Streamlit 재실행이라 반응이 굼뜸.

    칩 칸은 pyvis 의 .card 옆에 나란히 섬 — 그 안에 끼워 넣으면 pyvis 판이
    바뀔 때 조용히 깨짐.
    """
    html = network.bottom_html(
        model, colors, "<div id=chip>칩</div>", left_ratio=0.62, height=500,
    )

    assert 'id="list"' in html
    assert "mynetwork" in html


def test_the_bottom_flows_and_zooms_but_the_top_does_neither(model, colors):
    """★ 하얀 흐름 표시와 좁혀 들어가기는 하단만의 일임.

    좌표를 나눠 갖는 통로는 둘 다 엶 — 어느 쪽에서 끌든 상대가 따라와야 함.
    """
    상단 = network.top_html(model, colors, height=400)
    하단 = network.bottom_html(model, colors, "", left_ratio=0.6, height=500)

    assert '"flow": true' in 하단 and network.FLOW_SHEEN in 하단
    assert "afterDrawing" in 하단 and "network.fit(" in 하단
    assert '"flow": false' in 상단
    assert '"split": true' in 하단 and '"split": false' in 상단

    # 좌표는 나눠 갖고 카메라는 따로 논다
    for 문서 in (상단, 하단):
        assert network.POSITION_CHANNEL in 문서
        assert "moveNode" in 문서
        assert '"dragging"' in 문서 and '"dragEnd"' in 문서


def test_the_same_answer_is_only_zoomed_into_once(model, colors):
    """★ 같은 해석 결과로는 좁혀 들어가기가 한 번만 돈다.

    「이미 보여줬다」를 문서 안 변수로 두면 안 된다 — Streamlit 은 무엇을
    누르든 스크립트를 다시 돌리고 그때 iframe 이 통째로 새로 만들어져 그
    변수가 사라진다. 창 저장소에 맡기고, 막히면 부모 창으로 떨어진다.
    """
    하단 = network.bottom_html(model, colors, "", left_ratio=0.6, height=500,
                              signature="sig-a")

    assert "sessionStorage.getItem(CFG.memory)" in 하단
    assert "__graphFocus" in 하단
    assert '"sig": "sig-a"' in 하단
    # 상단과 하단이 서로의 기억을 덮지 않는다
    assert '"memory": "recipe_graph_focus_bottom"' in 하단
    assert '"memory": "recipe_graph_focus_top"' in network.top_html(
        model, colors, height=400)


# ── ★ 카메라를 누가 움직이나 ────────────────────────────────────────
#
# 사람이 아무것도 안 하는 동안 하단 화면이 전체와 고른 자리를 오갔다.
# 아래 둘이 그 자리를 구조로 막는다 — 문자열 하나하나가 아니라
# 「카메라를 부르는 함수가 무엇인가」를 본다.

def _functions(script):
    """스크립트를 함수 단위로 자름. {이름: 본문}."""
    lines = script.splitlines()
    heads = [i for i, l in enumerate(lines) if re.match(r"  (function \w+|const camera)", l)]
    out = {}
    for n, i in enumerate(heads):
        j = heads[n + 1] if n + 1 < len(heads) else len(lines)
        out[re.match(r"  (?:function )?(\w+)", lines[i]).group(1)] = "\n".join(lines[i:j])
    return out


# 카메라를 움직이는 말들. 이 셋 말고는 화면이 안 움직인다.
CAMERA_CALLS = ("network.fit(", "glide(", "focusOnce(")

# 사람이 아무것도 안 해도 도는 것들. **하나도 카메라를 부르면 안 된다.**
# poll(좌표 폴링)은 listen 안에 있어 listen 을 보면 함께 걸린다.
IDLE = ("animate", "paint", "sizeLayer", "receive", "makeLayer",
        "share", "listen", "border", "mark", "repaint")


def test_nothing_that_runs_by_itself_can_move_the_camera():
    """★ 사람이 아무것도 안 하는 동안 카메라를 부르는 자리가 0 이어야 한다.

    좌표 나누기 폴링 · 흐름 애니메이션 · 칸 크기 맞추기 · 좌표 받기가 전부
    끊임없이 돈다. 그중 하나라도 화면을 움직이면 사람이 손을 놓고 있어도
    화면이 왔다 갔다 한다. 실제로 그렇게 됐었다.
    """
    함수 = _functions(network.GRAPH_SCRIPT)

    for name in IDLE:
        assert name in 함수, f"{name} 이 없어졌다 — 이 시험을 고쳐야 한다"
        부르는_것 = [w for w in CAMERA_CALLS if w in 함수[name]]
        assert not 부르는_것, f"{name} 이 카메라를 부른다: {부르는_것}"

    # 끊임없이 도는 rAF 고리가 셋이다. 셋 다 카메라와 무관해야 한다
    assert "requestAnimationFrame(poll)" in 함수["listen"]
    assert "requestAnimationFrame(animate)" in network.GRAPH_SCRIPT


def test_only_three_events_own_the_bottom_camera():
    """★ 하단 카메라를 움직이는 자리는 셋뿐이다 — 새 해석 · 후보 누르기 · 배경 누르기.

    셋 다 glide 하나를 지난다. 그리고 도는 중에 다시 들어오면 앞의 것을 버리고
    새 것 하나만 돈다 — 겹쳐 돌면 vis-network 가 앞 애니메이션을 도착점으로
    튕겨 화면이 전체와 고른 자리를 오간다.
    """
    함수 = _functions(network.GRAPH_SCRIPT)

    # 카메라를 실제로 부르는 함수는 이 넷뿐이다
    부르는_함수 = {n for n, body in 함수.items()
                if any(w in body for w in CAMERA_CALLS)}
    assert 부르는_함수 == {"glide", "focusOnce", "clicked", "overview", "start"}

    # 화면을 실제로 움직이는 것(network.fit)은 glide 와 상단 전용 overview 뿐
    옮기는_함수 = {n for n, body in 함수.items() if "network.fit(" in body}
    assert 옮기는_함수 == {"glide", "overview"}

    # 겹쳐 돌지 않는다
    assert "camera.token" in 함수["glide"] and "mine !== camera.token" in 함수["glide"]


def test_the_flow_layer_is_cleared_in_real_pixels_not_scaled_ones():
    """★ 덮은 캔버스를 지울 때는 실제 픽셀 좌표라야 한다.

    그리기는 setTransform(dpr, …) 을 건 논리 좌표에서 하지만, 지우기까지
    그 변형 아래에서 하면 넘긴 백킹 크기에 dpr 이 한 번 더 곱해진다.
    dpr 이 1 보다 작으면 캔버스의 오른쪽과 아래가 안 지워지고 앞 프레임의
    흰 대시가 허공에 남는다.

    실측 (2026-09-06 · Chrome) : box 667x523 · layer 534x418 · dpr 0.8 에서
    427x334 만 지워져 오른쪽 107px · 아래 84px 에 잔상이 남았다.
    """
    함수 = _functions(network.GRAPH_SCRIPT)

    # 지우는 자리는 하나뿐이고 그 안에서 변형을 먼저 푼다 (주석은 빼고 센다)
    코드 = "\n".join(l for l in network.GRAPH_SCRIPT.splitlines()
                    if not l.strip().startswith("//"))
    assert 코드.count("clearRect") == 1
    지우개 = 함수["clearFlowLayer"]
    assert "setTransform(1, 0, 0, 1, 0, 0)" in 지우개
    assert 지우개.index("setTransform(1, 0, 0, 1, 0, 0)") < 지우개.index("clearRect")
    assert "pen.save()" in 지우개 and "pen.restore()" in 지우개

    # 그리는 쪽은 지우개를 부를 뿐 스스로 지우지 않는다
    assert "clearFlowLayer()" in 함수["paint"]
    assert "clearRect" not in 함수["paint"]

    # 그리기는 그대로 dpr 변형 아래에서 한다
    assert "setTransform(dpr, 0, 0, dpr, 0, 0)" in 함수["sizeLayer"]


def test_the_flow_animation_no_longer_drives_the_engine():
    """★ 흐르는 표시가 라이브러리의 그리기 루프를 안 쓴다.

    예전에는 afterDrawing 에 얹고 프레임마다 network.redraw() 를 불렀다.
    그 redraw 는 카메라 애니메이션을 돌리는 것과 같은 루프다 —
    vis-network 의 "_redraw" 는 renderingActive 가 거짓일 때만 듣는다.
    그리기와 카메라가 한 루프를 나눠 쓰면 서로를 밀어낸다.
    지금은 위에 덮은 캔버스 한 장에 우리 rAF 로만 그린다.
    """
    코드 = "\n".join(l for l in network.GRAPH_SCRIPT.splitlines()
                    if not l.strip().startswith("//"))

    assert "network.redraw" not in 코드
    assert "afterDrawing" not in 코드
    assert "flowlayer" in 코드 and "canvasToDOM" in 코드


def test_only_the_top_fits_itself_when_the_panel_resizes(model, colors):
    """★ 칸 크기가 바뀌어도 하단 화면은 안 움직인다.

    하단에도 ResizeObserver 가 있지만 그것은 덮은 캔버스 크기만 맞춘다.
    화면을 맞추는 것은 상단 전용 overview 안에만 있다.
    """
    함수 = _functions(network.GRAPH_SCRIPT)

    assert "network.fit(" in 함수["overview"]
    assert "network.fit(" not in 함수["sizeLayer"]
    assert '"overview": true' in network.top_html(model, colors, height=400)
    assert '"overview": false' in network.bottom_html(
        model, colors, "", left_ratio=0.6, height=500)


def test_the_first_zoom_is_once_per_resolve_not_per_recipe_set(model, colors):
    """★ 「다시 보여줄까」의 기준이 해석 한 번이지 recipe 묶음이 아님.

    서로 다른 발화가 우연히 같은 후보를 골라도 그때는 새 해석이라 다시
    한 번 보여줘야 한다. 반대로 화면만 다시 그린 것은 같은 해석이다.
    """
    from app.ui.components import focus_panel as fp

    둘 = screen_service.render("resolve", ["recipe_012", "recipe_045"])
    하나 = screen_service.render("resolve", ["recipe_061"])

    말 = {"utterance": "서울 인구 알려줘", "elapsed": 1.23}
    같은_화면 = {"utterance": "서울 인구 알려줘", "elapsed": 1.23}
    다른_발화 = {"utterance": "부산 인구 알려줘", "elapsed": 4.56}
    다시_누름 = {"utterance": "서울 인구 알려줘", "elapsed": 9.99}

    assert fp._signature(둘, 말) == fp._signature(둘, 같은_화면)
    assert fp._signature(둘, 말) != fp._signature(둘, 다른_발화)
    assert fp._signature(둘, 말) != fp._signature(둘, 다시_누름)
    assert fp._signature(둘, 말) != fp._signature(하나, 말)


def test_only_a_node_belonging_to_one_candidate_narrows_the_choice(model, colors):
    """★ CLARIFY 에서 후보를 좁히는 규칙.

    그 노드를 가진 후보가 하나면 그 후보로 좁히고, 여럿이 함께 쓰는 노드는
    어느 후보인지 가릴 근거가 없어 아무 일도 하지 않는다.

    옛 판은 「마지막 노드」로 갈랐는데, 후보들이 마지막 노드를 함께 쓰면
    (인구 둘이 그렇다) 좁힌 것이 전체와 똑같아져 고를 뜻이 없었다.
    """
    둘 = screen_service.render("resolve", ["recipe_012", "recipe_045"])["network"]
    picks = 둘["picks"]

    # 각 후보만 가진 노드는 그 후보를 가리킨다
    assert picks["spoken_keyword"] == "recipe_012"
    assert picks["spoken_place"] == "recipe_045"
    # 둘 다 지나는 노드는 아예 안 담긴다 — 눌러도 아무 일이 없어야 한다
    assert "search_population_statistics" not in picks
    # 좁힐 자리는 후보마다 한 벌씩 있다. 배경으로 돌아갈 자리는 빈 키다
    assert set(둘["variants"]) == {"", "recipe_012", "recipe_045"}


def test_the_recipe_panel_numbers_candidates_not_nodes(model, colors):
    """★ 번호가 후보 하나에 하나임. 노드마다가 아님.

    사람이 읽고 싶은 것은 「몇 번째 후보인가」이고 후보 안의 차례는 화살표가
    말한다. 번호는 이 패널 안에서만 산다 — 그래프 위에는 안 올린다.

        [1] 말한 키워드 → 인구 통계 조회
        [2] 말한 장소 → 장소 좌표 변환 → 인구 통계 조회
    """
    하단 = network.bottom_html(model, colors, "", left_ratio=0.6, height=500)

    assert "counter-increment: candidate" in 하단
    assert ".chain::before" in 하단
    assert ".arrow-line::after" in 하단          # 후보 안의 차례는 화살표가 말한다
    assert "counter(step)" not in 하단           # 노드마다 번호를 안 붙인다
    assert "counter(candidate)" not in network.top_html(model, colors, height=400)


def test_the_top_fills_the_panel_it_is_given(model, colors):
    """★ 상단이 칸을 다 씀.

    pyvis 는 #mynetwork 에 픽셀 높이를 박고 우리가 그것을 100% 로 덮는데,
    부모인 .card 에 높이가 없으면 백분율이 풀릴 기준이 없어 캔버스가 작아진다.
    그리고 pyvis 는 fit 을 한 번도 안 부른다 — 카메라가 기본값에 머문다.
    둘 다 고쳐야 칸이 넓어져도 그래프가 따라 커진다.
    """
    상단 = network.top_html(model, colors, height=400)

    assert "body > .card { height: 100%" in 상단
    assert '"overview": true' in 상단
    assert "ResizeObserver" in 상단
    # 하단은 고른 경로로 좁혀 들어가는 쪽이라 전체 맞추기를 안 켠다
    assert '"overview": false' in network.bottom_html(
        model, colors, "", left_ratio=0.6, height=500)


def test_a_chip_markup_with_a_closing_script_tag_cannot_break_the_document(model, colors):
    """값 안의 "</" 를 그대로 두면 문서가 거기서 끊김."""
    html = network.bottom_html(
        model, colors, "</script><b>깨짐</b>", left_ratio=0.6, height=400,
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
