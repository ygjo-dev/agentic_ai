"""온톨로지 그래프를 **interactive graph library** 로 그린다.

    pyvis (vis-network 9.1.2) 를 쓴다.

## 서비스 화면의 그래프는 하나다

    본 그래프     온톨로지 전체. 발화 해석 결과(후보 recipe)를 그 위에 강조하고
                  흐르는 표시 · 좁혀 들어가기 · 후보 고르기가 전부 여기서 돈다
    미니맵        본 그래프 안 오른쪽 아래의 캔버스 한 장. 온톨로지 전체를 줄여
                  그리고 본 그래프가 지금 보는 자리를 상자로 얹는다
    살펴보기 칸   같은 문서의 오른쪽 칸. 후보 recipe 목록과 누른 노드의 설명

셋을 한 문서(iframe 하나)에 둔다. 나누면 클릭마다 Streamlit 재실행이라 반응이
굼뜨고, iframe 끼리는 같은 network 객체를 못 본다. 전체 그림은 미니맵이 맡으므로
본 그래프는 마음대로 확대 · 이동해도 된다.

## 무엇이 그대로인가

    /screen 응답      한 칸도 안 바뀌었다
    온톨로지 · 배선   안 건드렸다
    좌표의 출처       서버의 layout.json. 물리 시뮬레이션을 끈다
    색                dot.COLORS 한 곳에서만 온다
    Graphviz          좌표 계산에만 남는다. 2026-09-06 에 그림 만들기를 걷었다

**좌표를 라이브러리가 다시 잡게 두지 않는다.** 물리 시뮬레이션을 켜면 노드를
등록할 때마다 지도가 통째로 흔들려서 「노드를 등록해도 기존 노드가 0.0000pt
움직인다」는 시연의 핵심 장면이 없어진다.

**y 를 뒤집는다.** Graphviz 는 위로 갈수록 y 가 커지고 vis-network 는 아래로
갈수록 커진다. 안 뒤집으면 지도가 상하로 뒤집힌 채 뜬다.
"""

import json
import re

from pyvis.network import Network

# 노드 이름의 줄바꿈. DOT 는 역슬래시와 n 두 글자로 적는데 라이브러리는 진짜
# 줄바꿈을 받는다. 서버가 만든 라벨을 그대로 쓰되 이 한 가지만 바꾼다.
DOT_NEWLINE = "\\n"

# 노드 상자.
NODE_FONT_SIZE = 15
NODE_SHAPE = "box"
NODE_MARGIN = 8
NODE_BORDER_WIDTH = 1

# 고른 경로에 든 노드의 테두리 굵기. 옛 dot.HIGHLIGHT_NODE_PENWIDTH 와 같은 값이다.
NODE_BORDER_WIDTH_MARKED = 6

# 대상(group) 노드. **기능 노드와 한눈에 갈려야 한다** — 실행할 수 있는 것과
# 개념은 다른 것이다. 옛 dot.GROUP_ATTRS 그대로다 : 타원 · 굵기 2 ·
# 테두리와 글자가 같은 금색. 색은 /screen 의 colors 에서 온다(group).
GROUP_SHAPE = "ellipse"
GROUP_BORDER_WIDTH = 2

# 엣지 굵기. 옛 dot 의 값 그대로다 — 배경 실선 1.6 · 고른 경로 8.
EDGE_WIDTH = 1.6
EDGE_WIDTH_HIGHLIGHT = 8

# 배경 실선을 얼마나 물러나게 둘까. 강조가 그 위에 떠 보여야 한다.
DIM_OPACITY = 0.45

# 화살촉 크기. **이 값이 흐르는 표시가 멈출 자리를 정한다** —
# vis-network 는 화살촉 길이를 `15 * scaleFactor + 3 * 선굵기` 로 잡는다
# (vis-network 9.1.2 의 getArrowData 실측). 그래서 여기 값을 바꾸면
# 흰 표시가 멈추는 자리도 함께 따라온다.
ARROW_SCALE = 0.6

# 고른 경로에서 화살촉이 붙는 자리. **후보마다 마지막 엣지 하나뿐이다.**
# 중간 방향은 흐르는 표시가 말하므로 엣지마다 화살촉을 되풀이하면 복잡하다.
# 배경 실선에는 아예 안 붙는다 — 옛 판의 dir=none 과 같은 자리다.
ARROW_TO = {"to": {"enabled": True, "scaleFactor": ARROW_SCALE}}
ARROW_NONE = {"to": {"enabled": False}}

# 서버 좌표를 라이브러리 화면 좌표로 옮길 때의 배율. 1.0 이면 그대로다.
COORD_SCALE = 1.0

# ------------------------------------------------------------ 흐르는 표시
# **옛 app/ui/components/flow.py 의 값 그대로다.** 단위도 같다 — 그때는 SVG
# 사용자 단위(= DOT 포인트)였고 지금은 캔버스가 같은 좌표계로 변형된 뒤에
# 그리므로 화면에서 같은 크기로 보인다.
#
#   DASH 50 · GAP 50   주기의 절반씩. 칸이 있어야 아래 teal 실선이 계속 보인다 —
#                      주인공은 여전히 원본 선이고 이것은 그 위를 지나가는 표시다
#   PERIOD 1.1초       한 칸을 지나는 시간. 걷는 속도로 읽히고 시선을 뺏지 않는다
#   WIDTH 4            EDGE_WIDTH_HIGHLIGHT(8)의 절반. 양옆에 teal 이 2씩 남아
#                      원본 선이 테두리처럼 계속 보인다
#   SHEEN 순백         색상(hue)이 없어 새 뜻을 만들지 않는다. 팔레트의 다른
#                      색은 전부 뜻이 있다 — 금색 「대상」 · 분홍 「새로 생긴 것」 ·
#                      보라 「관련」. 사람이 화면을 보고 순백을 골랐다
#                      (2026-08-30 · NOTES 「쉰넷째」)
FLOW_DASH = 50
FLOW_GAP = 50
FLOW_PERIOD_SECONDS = 1.1
FLOW_WIDTH = 4
FLOW_SHEEN = "#FFFFFF"

# ------------------------------------------------------------ 좁혀 들어가기
# **옛 zoom.py 의 값 그대로다.** 곧장 확대하지 않고 전체 그림을 잠깐 보여준 뒤
# 그 자리로 좁혀 들어간다.
#
#   HOLD 0.35초  전체 그림에 머무는 시간. 눈이 한 번 훑기에 이만큼은 필요하다
#   MOVE 1.0초   좁혀 들어가는 시간. 합쳐서 1.35초라 영상이 안 늘어진다
#   MAX_SCALE    옛 zoom.py 의 천장과 같다
FOCUS_HOLD_MS = 350
FOCUS_MOVE_MS = 1000
FOCUS_MAX_SCALE = 3.5

# 좁힐 때 강조 상자 둘레에 남기는 여백(화면 px, 한 변). 옛 zoom.FIT_PAD 다.
FOCUS_PAD = 24

# 두 단계 사이의 여유. **앞 단계가 끝나기 전에 뒤 단계를 걸면 안 된다** —
# vis-network 의 animateView 는 애니메이션이 도는 중에 다시 불리면 앞 것을
# 도착점으로 튕기고 새로 시작한다. 그러면 화면이 전체와 고른 자리를 오간다.
FOCUS_GAP_MS = 80

# ★ **진단판 스위치.** 켜면 브라우저 콘솔에 그래프 런타임의 일이 전부 찍힌다.
#
#   [graph-debug]   iframe 이 생기고 없어진 것 · 저장소 읽기/쓰기
#   [graph-camera]  화면을 움직인 자리 전부
#   [graph-flow]    흰 표시 캔버스의 일생과 좌표 표본
#
# 콘솔 filter 에 `graph-` 만 치면 셋이 다 보인다.
#
# ★ 이것은 **관찰만 한다.** 켜고 끄는 것으로 동작이 달라지지 않는다 —
# 찍는 값은 전부 읽기이고 흐름을 바꾸는 자리가 없다.
# 평소에는 끈다. 콘솔이 시끄럽고 시연에 쓸 것이 아니다.
DEBUG_GRAPH_RUNTIME = False

# 옛 이름. 위 스위치 하나로 카메라와 흐름 진단이 함께 켜진다.
CAMERA_TRACE = DEBUG_GRAPH_RUNTIME

# 흐름 좌표 표본을 몇 밀리초에 한 번 찍을까. 프레임마다 찍으면 콘솔이 죽는다.
FLOW_SAMPLE_MS = 1500

# 끌기 · 좌표 받기처럼 잦은 것도 같은 간격으로 줄인다. 시작과 끝은 늘 찍는다.
BUSY_SAMPLE_MS = 1000

# 「이 결과는 이미 보여줬다」와 마지막 카메라를 적어 두는 자리. **iframe 밖에
# 있어야 한다** — Streamlit 은 무엇을 누르든 스크립트를 다시 돌리고 그때 iframe 이
# 새로 만들어지면 문서 안의 변수가 사라진다. 카메라는 뒤에 "_view" 를 붙인 칸이다.
FOCUS_MEMORY = "recipe_graph_focus"

# ------------------------------------------------------------ 미니맵
#   MARGIN   본 그래프 오른쪽 · 아래 모서리에서 띄우는 거리(px)
#   SHARE    본 그래프 폭 가운데 미니맵이 차지하는 몫. 아래 최소 · 최대 폭 안에서
#   PAD      미니맵 안쪽 여백(px). 가장자리 노드가 테두리에 붙지 않게
#   DOT      노드 점 한 변의 절반(px). 강조된 노드는 LIT_DOT
MINIMAP_MARGIN = 10
MINIMAP_SHARE = 0.2
MINIMAP_MIN_WIDTH = 150
MINIMAP_MAX_WIDTH = 240
MINIMAP_MAX_HEIGHT = 170
MINIMAP_PAD = 7
MINIMAP_DOT = 1.8
MINIMAP_LIT_DOT = 2.8

# 살펴보기 칸이 노드 종류를 적는 말. network 모형의 kind 값 그대로를 옮긴다.
KIND_LABELS = {"group": "대상", "function": "기능"}


def _label(name: str) -> str:
    """DOT 라벨을 라이브러리 라벨로. 줄바꿈 표기만 바꿈."""
    return name.replace(DOT_NEWLINE, "\n")


def _rgba(hex_color: str, alpha: float) -> str:
    """#RRGGBB 를 rgba() 로. 배경 선을 물러나게 두는 데만 씀."""
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def options(hover: bool = True) -> str:
    """vis-network 설정. **손맛이 전부 여기서 나온다.**

    입력  마우스를 올렸을 때 설명을 띄울지
    출력  set_options 에 넣을 JSON 문자열
    규칙  physics 를 끔. 서버 좌표를 그대로 쓰기 위함
          dragNodes · dragView · zoomView 셋을 켬. 요구가 그 셋임
          selectConnectedEdges 를 끔. 노드를 누르면 이어진 엣지까지 색이
          바뀌어 강조 규칙과 섞임
          엣지를 곧은 선으로 둠. 흐르는 표시가 두 끝점을 잇는 직선 위를
          지나므로 곡선이면 표시가 선에서 벗어남
          화살표를 전역으로 안 켬. 붙일 자리를 엣지마다 따로 정함
    제약  physics 를 켜지 않는다.
          켜면 노드를 등록할 때마다 지도가 통째로 흔들림
    """
    return json.dumps({
        "physics": {"enabled": False},
        "interaction": {
            "dragNodes": True,
            "dragView": True,
            "zoomView": True,
            "hover": hover,
            "tooltipDelay": 200,
            "selectConnectedEdges": False,
            "navigationButtons": False,
            "keyboard": False,
        },
        "edges": {
            "smooth": {"enabled": False},
            "arrows": ARROW_NONE,
        },
    })


def edge_id(a: str, b: str) -> str:
    """실선 엣지 하나의 id. JS 가 이 id 로만 스타일을 갈아끼운다."""
    return f"{a}>{b}"


def node_styles(model: dict, colors: dict, variant: str) -> list[dict]:
    """한 변형에서 노드가 어떻게 보여야 하는가.

    입력  network 모형 · 색 · 변형 키
    출력  vis-network 노드 dict 목록. id · shape · color · borderWidth · font
    규칙  대상(group) 노드는 타원에 금색
          고른 경로의 노드는 청록 굵은 테두리. 실행 전(plain)에는 변형이 비어 아무것도 안 굵어짐
    """
    칸 = (model.get("variants") or {}).get(variant) or {}
    강조_노드 = set(칸.get("nodes") or ())
    배경 = colors.get("node_fill", "#171B26")
    테두리 = colors.get("node_border", "#A9B1C0")
    글자 = colors.get("plain", "#8C93A1")
    금색 = colors.get("group", "#D9A441")

    out = []
    for node_id, node in (model.get("nodes") or {}).items():
        대상 = node.get("kind") == "group"
        짚음 = node_id in 강조_노드

        if 짚음:
            선색 = colors.get("highlight", "#14B8A6")
        elif 대상:
            선색 = 금색
        else:
            선색 = 테두리

        if 짚음:
            굵기 = NODE_BORDER_WIDTH_MARKED
        elif 대상:
            굵기 = GROUP_BORDER_WIDTH
        else:
            굵기 = NODE_BORDER_WIDTH

        칠 = {"border": 선색, "background": 배경,
              "highlight": {"border": 선색, "background": 배경},
              "hover": {"border": 선색, "background": 배경}}
        out.append({
            "id": node_id,
            "shape": GROUP_SHAPE if 대상 else NODE_SHAPE,
            "borderWidth": 굵기,
            "color": 칠,
            "font": {"size": NODE_FONT_SIZE,
                     # 대상 노드는 글자도 금색이다. 옛 GROUP_ATTRS 의 fontcolor 다.
                     "color": 금색 if 대상 else 글자,
                     "face": "sans-serif"},
        })
    return out


def solid_styles(model: dict, colors: dict, variant: str) -> list[dict]:
    """한 변형에서 배경 실선이 어떻게 보여야 하는가.

    출력  vis-network 엣지 dict 목록. id · from · to · color · width
    규칙  teal(해석 경로) > 물러난 배경 차례로 걸림
    제약  무엇이 강조인지 여기서 판단하지 않는다.
          서버(build.network_payload)가 이미 갈라 보냄
          순번을 붙이지 않는다. 그래프 위의 숫자는 흐르는 표시가 대신함
          화살촉을 중간 엣지에 붙이지 않는다.
          후보마다 마지막 엣지 하나뿐임. 중간 방향은 흐르는 표시가 말함
    """
    칸 = (model.get("variants") or {}).get(variant) or {}
    실선색 = colors.get("edge", "#4A5262")
    강조 = {tuple(e) for e in 칸.get("highlight") or ()}
    끝 = {tuple(e) for e in 칸.get("final") or ()}

    out = []
    for a, b in (tuple(e) for e in model.get("solid") or ()):
        if (a, b) in 강조:
            색, 굵기 = colors.get("highlight", "#14B8A6"), EDGE_WIDTH_HIGHLIGHT
        else:
            색, 굵기 = _rgba(실선색, DIM_OPACITY), EDGE_WIDTH
        out.append({
            "id": edge_id(a, b), "from": a, "to": b, "color": 색, "width": 굵기,
            "arrows": ARROW_TO if (a, b) in 끝 else ARROW_NONE,
        })
    return out


def flowing_edges(model: dict, variant: str) -> list[dict]:
    """흐르는 표시를 얹을 구간. 고른 해석 경로 전부다.

    출력  [{"from": a, "to": b, "arrow": 마지막 엣지인가}, …]
    규칙  색이나 굵기로 안 고름. 서버가 갈라 보낸 highlight 를 그대로 씀 —
          옛 판이 class="flow" 손잡이로 고르던 것과 같은 자리임
          화살촉이 마지막에만 있어도 흐름은 모든 구간에 둠. 그래야 중간
          방향이 읽힘
          arrow 는 그 구간이 어디서 멈춰야 하는지를 말함. 화살촉이 있으면
          그 앞에서, 없으면 노드 경계에서 멈춤
    """
    칸 = (model.get("variants") or {}).get(variant) or {}
    끝 = {tuple(e) for e in 칸.get("final") or ()}
    return [
        {"from": a, "to": b, "arrow": (a, b) in 끝}
        for a, b in (tuple(e) for e in 칸.get("highlight") or ())
    ]


def variant_patches(model: dict, colors: dict) -> dict:
    """변형마다의 스타일 한 벌. **파이썬이 만들고 JS 는 고르기만 한다.**

    출력  {변형 키: {"edges": [...], "nodes": [...], "flow": [...], "focus": [...]}}
    규칙  JS 가 색 · 굵기 규칙을 하나도 모르게 함. 누르면 이 표에서 골라
          vis-network 의 DataSet.update 에 그대로 넘김
    제약  JS 에서 다시 칠하지 않는다.
          규칙이 두 곳으로 갈라지면 한쪽만 고쳤을 때 조용히 어긋남
    """
    return {
        key: {
            "edges": solid_styles(model, colors, key),
            "nodes": node_styles(model, colors, key),
            "flow": flowing_edges(model, key),
            # 좁혀 들어갈 대상. 고른 경로의 노드다
            "focus": sorted((model.get("variants") or {}).get(key, {}).get("nodes") or ()),
        }
        for key in (model.get("variants") or {})
    }


def build_network(model, colors, *, variant="", height=480):
    """/render 의 network 모형을 vis-network 그래프로.

    입력  model    render 응답의 "network"
          colors   /screen 의 colors. 팔레트의 주인은 서버임
          variant  처음 보여줄 변형 키. 빈 키가 후보 전부
          height   픽셀 높이
    출력  pyvis Network
    규칙  점선(about) 위에 배경 실선을 깔고, 변형의 강조를 그 실선에 얹음.
          실행 전에도 실선을 그림. 강조는 있는 엣지의 색 · 굵기만 바꾸므로
          엣지가 처음부터 있어야 함
    제약  색을 여기서 새로 정하지 않는다.
          출처가 둘이면 칩과 그래프가 조용히 어긋남
    """
    net = Network(
        height=f"{height}px",
        width="100%",
        bgcolor="transparent",
        font_color=colors.get("plain", "#8C93A1"),
        directed=True,
        cdn_resources="in_line",
        notebook=False,
    )

    for style in node_styles(model, colors, variant):
        node_id = style.pop("id")
        node = model["nodes"][node_id]
        x, y = model["positions"][node_id]
        net.add_node(
            node_id,
            label=_label(node["label"]),
            title=node.get("title") or "",
            x=x * COORD_SCALE,
            # Graphviz 는 위로, vis-network 는 아래로 y 가 큼.
            y=-y * COORD_SCALE,
            margin=NODE_MARGIN,
            **style,
        )

    for entry in model.get("dotted") or ():
        a, b = entry["edge"]
        net.add_edge(
            a, b,
            color=colors.get("dotted_bottom", "#8B84E8"),
            width=EDGE_WIDTH,
            dashes=True,
            arrows="",
        )

    for style in solid_styles(model, colors, variant):
        net.add_edge(style.pop("from"), style.pop("to"), **style)

    net.set_options(options())
    return net


def node_details(model: dict) -> dict:
    """살펴보기 칸이 노드를 누르면 적을 것.

    출력  {node_id: {"name", "kind", "group", "text"}}
    규칙  이름은 두 줄로 접힌 라벨을 한 줄로 폄. 칩 이름과 같은 꼴임
          text 는 network 모형의 title(온톨로지 description) 그대로
    제약  모형에 없는 설명을 지어내지 않는다.
          도구 · 서버 이름은 화면 모형에 없어서 안 적음
    """
    return {
        node_id: {
            "name": _label(node.get("label") or node_id).replace("\n", " "),
            "kind": KIND_LABELS.get(node.get("kind", ""), ""),
            "group": node.get("kind") == "group",
            "text": node.get("title") or "",
        }
        for node_id, node in (model.get("nodes") or {}).items()
    }


def minimap_links(model: dict) -> list[list[str]]:
    """미니맵에 그릴 엣지 전부. 실선과 점선을 가리지 않음."""
    return ([list(e) for e in model.get("solid") or ()]
            + [list(entry["edge"]) for entry in model.get("dotted") or ()])


def minimap_colors(colors: dict) -> dict:
    """미니맵 색. 전부 /screen 팔레트에서 옴.

    규칙  배경 · 테두리 · 보는 자리 상자는 색상이 없는 흰색 · 검정의 투명도만 씀.
          뜻 있는 색(청록 · 금색)은 그래프와 같은 것을 씀
    """
    return {
        "bg": "rgba(14,17,23,0.82)",
        "frame": "rgba(255,255,255,0.14)",
        "edge": _rgba(colors.get("edge", "#4A5262"), 0.9),
        "node": colors.get("plain", "#8C93A1"),
        "group": colors.get("group", "#D9A441"),
        "lit": colors.get("highlight", "#14B8A6"),
        "view": "rgba(255,255,255,0.85)",
        "viewFill": "rgba(255,255,255,0.07)",
    }


# ── 문서 조립 ────────────────────────────────────────────────────────
#
# pyvis 가 낸 문서를 감싸서 쓴다. **그 안의 마크업을 헤집지 않는다** —
# pyvis 판이 바뀌면 태그 차례가 달라져 조용히 깨진다. body 를 가로로 눕히고
# 오른쪽 칸 하나를 </body> 앞에 덧붙이는 것이 전부다.

# JSON 을 <script> 안에 넣을 때 "</script>" 가 섞이면 문서가 거기서 끊긴다.
SCRIPT_CLOSE = "</"
SCRIPT_CLOSE_SAFE = "<\\/"

# pyvis 문서가 CDN 에서 끌어오는 것. **vis-network 는 여기 없다** — 그것은
# cdn_resources="in_line" 로 문서 안에 실려 있고, 이 둘은 pyvis 가 제 버튼과
# 선택 상자를 꾸미는 데 쓰는 Bootstrap 이다. 우리는 그 UI 를 안 쓴다.
# 남겨 두면 인터넷이 없을 때 브라우저가 두 번 기다렸다 실패한다.
def _without_cdn(html: str) -> str:
    """CDN 태그를 뺌. 속성 차례가 판마다 다르므로 통째로 훑는다."""
    html = re.sub(r"<script[^>]+cdn\.jsdelivr\.net[^>]*>\s*</script>", "", html)
    html = re.sub(r"<link[^>]+cdn\.jsdelivr\.net[^>]*>", "", html)
    return html


# ★ **.card 에 높이를 준다.** pyvis 는 `#mynetwork` 에 `height: 400px` 처럼
# 픽셀을 박아 두는데 우리가 그것을 `height: 100%` 로 덮는다. 그런데 그 부모인
# pyvis 의 `.card` 에는 높이가 없어서(인라인 `width: 100%` 뿐) 백분율이 풀릴
# 기준이 없고, 캔버스가 칸을 다 못 쓴 채 작게 그려졌다.
BASE_CSS = """
html, body { background: transparent !important; margin: 0; padding: 0;
  height: 100%; overflow: hidden;
  font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
  color: #E6E8EB; }
.card, .container, .container-fluid { background: transparent !important;
  border: none !important; padding: 0 !important; margin: 0 !important; }
body > .card { height: 100%; min-width: 0; }
#mynetwork { background: transparent !important; border: none !important;
  width: 100% !important; height: 100% !important; }
"""

# 가로로 눕힌다. 왼쪽이 pyvis 의 .card(본 그래프), 오른쪽이 살펴보기 칸이다.
# **pyvis 마크업을 안 건드리고 flex 로만 나눈다.**
# pyvis 는 빈 제목(<center><h1>)을 head 에 두고 브라우저가 그것을 body 로 옮긴다.
# flex 칸이 되어 gap 만큼 그래프를 오른쪽으로 민다 — 감춘다.
SPLIT_CSS = """
body {{ display: flex; flex-direction: row; gap: 14px; }}
body > center {{ display: none; }}
body > .card {{ flex: 1 1 auto; }}
#side {{ flex: 0 0 {side}%; height: 100%; overflow-y: auto; min-width: 0;
  box-sizing: border-box; padding: 0.1rem 6px 0 14px;
  border-left: 1px solid rgba(255,255,255,0.08);
  display: flex; flex-direction: column; gap: 1.1rem; }}
"""

# 살펴보기 칸. 위가 후보 recipe 목록, 아래가 누른 노드의 설명이다.
#
# ★ **번호는 후보 하나에 하나다.** 노드마다 붙이면 「몇 번째 노드인가」가 되는데
#   사람이 읽고 싶은 것은 「몇 번째 후보인가」다. 후보 안의 차례는 화살표가 말한다.
#   **그래프 위에는 여전히 숫자를 안 올린다** — 번호는 이 칸 안에서만 산다.
# ★ 좁혀도 줄을 빼지 않는다. 고르지 않은 후보는 흐려질 뿐이다 —
#   후보가 몇이었는지는 좁힌 뒤에도 보여야 한다.
SIDE_CSS = """
.head {{ display: flex; align-items: baseline; gap: 0.5rem;
  font-size: 0.78rem; letter-spacing: 0.04em; color: {plain};
  text-transform: uppercase; margin-bottom: 0.45rem; }}
.head .state {{ text-transform: none; letter-spacing: 0; color: #E6E8EB;
  font-size: 0.85rem; }}
.blank {{ color: {plain}; font-size: 0.9rem; }}
#recipes .list:not(:empty) + .blank {{ display: none; }}
#recipes .list {{ counter-reset: candidate; }}
.recipe {{ padding: 0.45rem 0.55rem; border-radius: 8px; cursor: pointer;
  border: 1px solid transparent; transition: opacity 0.18s ease-out; }}
.recipe:hover {{ border-color: rgba(255,255,255,0.10); }}
.recipe + .recipe {{ margin-top: 0.35rem; }}
.recipe.off {{ opacity: 0.38; }}
.rhead {{ display: flex; align-items: center; gap: 0.45rem; margin-bottom: 0.3rem; }}
.rhead::before {{
  counter-increment: candidate; content: "[" counter(candidate) "]";
  color: {plain}; font-variant-numeric: tabular-nums;
}}
.rid {{ font-family: ui-monospace, "SFMono-Regular", Menlo, monospace;
  font-size: 0.86rem; color: #E6E8EB; }}
.rfn {{ font-size: 0.9rem; line-height: 1.45; color: #E6E8EB;
  margin: 0 0 0.35rem 0; word-break: keep-all; overflow-wrap: break-word; }}
.tag {{ font-size: 0.72rem; padding: 0.05rem 0.45rem; border-radius: 999px;
  border: 1px solid {plain}; color: {plain}; }}
.tag.chosen {{ border-color: {lit}; color: {lit}; }}
.chain {{ display: flex; align-items: center; flex-wrap: wrap; gap: 0.1rem; }}
.chip {{
  display: inline-block; padding: 0.16rem 0.55rem;
  border: 1px solid {plain}; border-radius: 999px;
  background: rgba(255,255,255,0.04); color: #E6E8EB;
  font-size: 0.84rem; white-space: nowrap;
  opacity: 0; animation: chip-in 0.22s ease-out forwards;
  animation-delay: calc(var(--i) * 55ms);
}}
.link {{
  display: inline-flex; align-items: center;
  min-width: 1.6rem; padding: 0 0.12rem;
  opacity: 0; animation: chip-in 0.22s ease-out forwards;
  animation-delay: calc(var(--i) * 55ms + 28ms);
}}
.link .arrow-line {{
  display: block; width: 100%; height: 1px; background: {plain};
  position: relative; transform-origin: left center;
  animation: line-grow 0.2s ease-out forwards;
  animation-delay: calc(var(--i) * 55ms + 28ms);
}}
.link .arrow-line::after {{
  content: ""; position: absolute; right: -1px; top: -2.5px;
  border-left: 5px solid {plain};
  border-top: 3px solid transparent; border-bottom: 3px solid transparent;
}}
#node .body {{ display: none; }}
#node.filled .body {{ display: block; }}
#node.filled .blank {{ display: none; }}
.nname {{ font-size: 1.05rem; font-weight: 600; color: #E6E8EB; }}
.nkind {{ display: inline-block; margin-top: 0.3rem; font-size: 0.72rem;
  padding: 0.05rem 0.45rem; border-radius: 999px; border: 1px solid {plain};
  color: {plain}; }}
.nkind.group {{ border-color: {group}; color: {group}; }}
.ntext {{ margin: 0.55rem 0 0 0; font-size: 0.9rem; line-height: 1.5; color: #C9CED6; }}
.nown {{ margin-top: 0.55rem; font-size: 0.8rem; color: {plain}; }}
.nown:empty {{ display: none; }}
@media (prefers-reduced-motion: reduce) {{
  .chip, .link, .link .arrow-line {{ animation: none; opacity: 1; transform: none; }}
}}
@keyframes chip-in {{ from {{ opacity: 0; transform: translateX(-6px); }}
  to {{ opacity: 1; transform: none; }} }}
@keyframes line-grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
"""

# 오른쪽 살펴보기 칸. body 의 자식이라 pyvis 의 .card 와 나란히 선다.
# 후보 목록과 노드 설명은 JS 가 채운다 — 값이 JSON 으로 실려 와야 "</script>" 가
# 섞여도 문서가 안 끊긴다.
SIDE_BOX = (
    '<aside id="side">'
    '<section id="recipes"><div class="head">Recipe <span class="state"></span></div>'
    '<div class="list"></div><div class="blank">—</div></section>'
    '<section id="node"><div class="head">Node</div><div class="blank">—</div>'
    '<div class="body"><div class="nname"></div><span class="nkind"></span>'
    '<p class="ntext"></p><div class="nown"></div></div></section>'
    '</aside>'
)


def embed_json(payload) -> str:
    """<script> 안에 넣어도 안전한 JSON 문자열.

    제약  값 안의 "</" 를 그대로 두지 않는다. "</script>" 가 섞이면 문서가
          거기서 끊김
    """
    return json.dumps(payload, ensure_ascii=False).replace(
        SCRIPT_CLOSE, SCRIPT_CLOSE_SAFE
    )


# ── 브라우저에서 도는 것 ─────────────────────────────────────────────
#
# **vis-network 의 공식 손잡이만 쓴다.**
#
#   흐르는 표시      덮은 캔버스에 흰 대시를 얹고 offset 만 움직임
#   미니맵           또 한 장의 캔버스. 전체 좌표와 지금 보는 자리를 줄여 그림
#   좁혀 들어가기    fit({nodes, animation})
#   고르기 · 살펴보기 click -> DataSet.update · 살펴보기 칸 글자
#
# JS 는 색도 굵기도 모른다. 파이썬이 만든 표에서 고를 뿐이다.

GRAPH_SCRIPT = """
<script>
(function () {
  const CFG = __CFG__;
  const DATA = __DATA__;

  // ══════════════════════════════════════════════════ 0. 진단 (관찰만)
  //
  // ★ **여기 있는 것은 하나도 동작을 바꾸지 않는다.** 값을 읽어 콘솔에 적을
  // 뿐이고 흐름을 가르는 자리가 없다. CFG.trace 가 꺼지면 통째로 조용해진다.
  //
  // 왜 필요한가 : 같은 iframe 안에서 카메라가 되풀이되는 것인지, 아니면
  // Streamlit 이 iframe 을 계속 새로 만들어 새 판마다 처음 한 번을 도는
  // 것인지를 로그 없이는 가를 수 없다. 그래서 판마다 이름을 붙인다.
  // ★ **문지기 하나.** 꺼져 있으면 아래 진단은 한 줄도 안 돈다 —
  // 로그를 막는 것이 아니라 값을 만드는 일 자체를 안 한다. 화면 좌표를 읽고
  // 문자열을 잇는 일이 프레임마다 도는 자리에 있어서, 막기만 하면 공짜가
  // 아니다.
  const TRACE = !!CFG.trace;

  const INSTANCE = TRACE ? (function () {
    try { if (crypto && crypto.randomUUID) return crypto.randomUUID().slice(0, 8); }
    catch (e) {}
    return Math.random().toString(36).slice(2, 10);
  })() : "";

  function stamp() {
    const d = new Date();
    return d.toTimeString().slice(0, 8) + "." +
           String(d.getMilliseconds()).padStart(3, "0");
  }

  function trace(kind, event, extra) {
    if (!CFG.trace) return;
    try {
      let line = "[graph-" + kind + "] time=" + stamp() +
                 " inst=" + INSTANCE + " event=" + event;
      if (extra) line += " " + extra;
      console.log(line);
    } catch (e) {}
  }

  // 지금 화면이 어디를 보고 있나. 읽기뿐이다.
  function where() {
    try {
      const p = network.getViewPosition();
      return "scale=" + network.getScale().toFixed(4) +
             " view=" + p.x.toFixed(1) + "," + p.y.toFixed(1);
    } catch (e) { return "scale=? view=?"; }
  }

  // 잦은 것을 솎아 낸다. 프레임마다 찍으면 콘솔이 죽는다.
  const beats = {};
  function due(name, gap) {
    const now = Date.now();
    if (beats[name] && now - beats[name] < gap) return false;
    beats[name] = now;
    return true;
  }

  if (TRACE) trace("debug", "INSTANCE_CREATE",
        "sig=" + JSON.stringify(CFG.sig || "") + " memkey=" + CFG.memory);

  if (TRACE) {
    try {
      window.addEventListener("pagehide", function () {
        trace("debug", "INSTANCE_DESTROY", "");
      });
    } catch (e) {}
  }

  // ══════════════════════════════════════════════════ 1. 흐르는 표시
  //
  // 고른 경로 위로 흰 대시가 시작 노드에서 끝 노드 쪽으로 흐른다.
  //
  // ★ **제 캔버스에 그린다. 라이브러리의 그리기 루프를 건드리지 않는다.**
  // 예전에는 afterDrawing 에 얹고 프레임마다 network.redraw() 를 불렀는데,
  // 그 redraw 는 카메라 애니메이션을 돌리는 것과 같은 루프다(vis-network 의
  // "_redraw" 는 renderingActive 가 거짓일 때만 듣는다). 그리기와 카메라가
  // 한 루프를 나눠 쓰면 서로를 밀어낸다. 여기서는 위에 덮은 캔버스 한 장에
  // 우리 rAF 로만 그리므로 카메라를 부르는 자리가 아예 없다.
  let flow = [];
  let offset = 0;
  let last = 0;
  let layer = null, pen = null;

  function reduced() {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
    catch (e) { return false; }
  }

  function makeLayer() {
    const box = document.getElementById("mynetwork");
    if (!box) return;
    layer = document.createElement("canvas");
    layer.id = "flowlayer";
    layer.style.cssText =
      "position:absolute;left:0;top:0;pointer-events:none;z-index:2;";
    box.style.position = "relative";
    box.appendChild(layer);
    pen = layer.getContext("2d");
    sizeLayer();
    if (TRACE) trace("flow", "FLOW_CANVAS_CREATE",
          "box=" + box.clientWidth + "x" + box.clientHeight +
          " dpr=" + (window.devicePixelRatio || 1));
    // ★ 크기만 맞춘다. 카메라는 안 건드린다.
    try {
      new ResizeObserver(function () {
        if (TRACE) {
          trace("flow", "FLOW_CANVAS_RESIZE",
                "box=" + box.clientWidth + "x" + box.clientHeight + " " + where());
        }
        sizeLayer();
      }).observe(box);
    } catch (e) {}
  }

  function sizeLayer() {
    const box = document.getElementById("mynetwork");
    if (!box || !layer) return;
    const dpr = window.devicePixelRatio || 1;
    layer.width = Math.max(1, Math.round(box.clientWidth * dpr));
    layer.height = Math.max(1, Math.round(box.clientHeight * dpr));
    layer.style.width = box.clientWidth + "px";
    layer.style.height = box.clientHeight + "px";
    // width 에 값을 넣는 것만으로 캔버스가 비워지고 변형도 풀린다. 그래서
    // 여기서 변형을 다시 건다 — 이 차례가 뒤집히면 그리기 좌표가 어긋난다.
    if (pen) pen.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // 노드 한가운데에서 그 방향 바깥 경계까지의 거리(그래프 단위).
  // vis-network 가 화살촉을 놓을 때 쓰는 것과 같은 함수라 상자든 타원이든
  // 제 모양대로 답한다. 못 재면 상자 절반으로 떨어진다.
  function border(id, angle) {
    const node = (network.body.nodes || {})[id];
    if (!node) return 0;
    try {
      const d = node.distanceToBorder(pen, angle);
      if (isFinite(d) && d > 0) return d;
    } catch (e) {}
    try {
      const shape = node.shape || {};
      return Math.max(shape.width || 0, shape.height || 0) / 2;
    } catch (e) { return 0; }
  }

  // 덮은 캔버스를 통째로 지운다.
  //
  // ★ **지우는 것은 실제 픽셀 좌표에서 해야 한다.** 아래 sizeLayer 가
  // setTransform(dpr, …) 로 변형을 걸어 두므로, 그 상태에서 clearRect 에
  // 백킹 크기(layer.width/height)를 넘기면 그 값에 dpr 이 한 번 더 곱해진다.
  // dpr 이 1 보다 작으면 캔버스의 오른쪽과 아래가 안 지워지고 앞 프레임의
  // 흰 대시가 허공에 남는다.
  //
  // 실측 (2026-09-06 · Chrome) : box=667x523 · layer=534x418 · dpr=0.8 이라
  // 427x334 만 지워졌다 — 오른쪽 107px · 아래 84px 에 잔상이 남았다.
  //
  //   지우기  실제 픽셀 좌표 (identity)
  //   그리기  논리 좌표 (dpr 변형)
  function clearFlowLayer() {
    if (!pen || !layer) return;
    pen.save();
    pen.setTransform(1, 0, 0, 1, 0, 0);
    pen.clearRect(0, 0, layer.width, layer.height);
    pen.restore();
  }

  function paint() {
    if (!pen || !layer) return;
    clearFlowLayer();
    if (!flow.length) return;

    let at, scale;
    try { at = network.getPositions(); scale = network.getScale(); } catch (e) { return; }

    let sample = TRACE && due("flowsample", CFG.sampleMs);

    pen.save();
    pen.strokeStyle = CFG.sheen;
    pen.lineWidth = CFG.width * scale;
    pen.setLineDash([CFG.dash * scale, CFG.gap * scale]);
    // 음수라야 0 을 향해 줄어들며 꼬리에서 머리 쪽으로 흐른다.
    pen.lineDashOffset = -offset * scale;
    pen.beginPath();

    for (const seg of flow) {
      const pa = at[seg.from], pb = at[seg.to];
      if (!pa || !pb) continue;
      const dx = pb.x - pa.x, dy = pb.y - pa.y;
      const span = Math.sqrt(dx * dx + dy * dy);
      if (span < 1) continue;
      const angle = Math.atan2(dy, dx);

      // 시작은 출발 노드의 바깥 경계. 끝은 도착 노드의 바깥 경계이고,
      // 거기 화살촉이 있으면 그 앞에서 멈춘다 — 청록 화살촉을 덮으면 안 된다.
      const head = border(seg.from, angle);
      const tail = border(seg.to, angle + Math.PI);
      const arrow = seg.arrow ? (15 * CFG.arrowScale + 3 * CFG.edgeWidth) : 0;
      const from = head, to = span - tail - arrow;
      if (to - from < CFG.width) continue;   // 그릴 자리가 없으면 건너뛴다

      const cos = dx / span, sin = dy / span;
      let A, B;
      try {
        A = network.canvasToDOM({x: pa.x + cos * from, y: pa.y + sin * from});
        B = network.canvasToDOM({x: pa.x + cos * to, y: pa.y + sin * to});
      } catch (e) { continue; }

      // 표본 한 구간. **그리는 값을 그대로 읽어 적을 뿐이다.**
      // vis-network 좌표와 덮은 캔버스 좌표가 언제 어긋나는지를 보려는 것.
      if (sample) {
        sample = false;
        const box = document.getElementById("mynetwork");
        if (TRACE) trace("flow", "FLOW_PAINT_SAMPLE",
              "edge=" + seg.from + "->" + seg.to + " arrow=" + !!seg.arrow +
              " canvasA=" + pa.x.toFixed(1) + "," + pa.y.toFixed(1) +
              " canvasB=" + pb.x.toFixed(1) + "," + pb.y.toFixed(1) +
              " domA=" + A.x.toFixed(1) + "," + A.y.toFixed(1) +
              " domB=" + B.x.toFixed(1) + "," + B.y.toFixed(1) +
              " trim=" + from.toFixed(1) + "/" + to.toFixed(1) + " span=" + span.toFixed(1) +
              " layer=" + layer.width + "x" + layer.height +
              " box=" + (box ? box.clientWidth + "x" + box.clientHeight : "?") +
              " " + where());
      }

      pen.moveTo(A.x, A.y);
      pen.lineTo(B.x, B.y);
    }
    pen.stroke();
    pen.restore();
  }

  let flowing = false;

  function animate(now) {
    if (TRACE && !!flow.length !== flowing) {
      flowing = !!flow.length;
      if (TRACE) trace("flow", flowing ? "FLOW_START" : "FLOW_STOP",
            "segments=" + flow.length);
    }
    if (flow.length) {
      if (last) {
        offset += (CFG.dash + CFG.gap) * (now - last) / (CFG.period * 1000);
        offset %= (CFG.dash + CFG.gap);
      }
      last = now;
    } else {
      last = 0;
    }
    paint();
    window.requestAnimationFrame(animate);
  }

  // ══════════════════════════════════════════════════ 2. 미니맵
  //
  // 온톨로지 전체를 줄여 그리고, 본 그래프가 지금 보는 자리를 상자로 얹는다.
  // ★ **같은 문서 안의 캔버스 한 장이다.** 그래프를 하나 더 띄우지 않는다 —
  // 좌표는 본 그래프의 getPositions, 보는 자리는 DOMtoCanvas 로 읽는다.
  // ★ **그리기만 한다.** 카메라를 움직이는 것은 사람이 미니맵을 누르거나
  // 끌 때(jump) 하나뿐이다.
  let mini = null, miniPen = null;
  let miniKey = "";          // 지난번에 그린 카메라. 같으면 다시 안 그린다
  let miniSize = "";         // 지난번에 잰 칸 크기
  let miniDirty = true;      // 노드가 옮겨졌다. 전체 범위를 다시 잰다
  let miniFit = null;        // 그래프 좌표 -> 미니맵 좌표 {k, ox, oy, w, h, dpr}
  let lit = {};              // 지금 강조된 노드. repaint 가 채운다

  function makeMini() {
    const box = document.getElementById("mynetwork");
    if (!box) return;
    const M = CFG.mini;
    mini = document.createElement("canvas");
    mini.id = "minimap";
    mini.style.cssText =
      "position:absolute;z-index:3;cursor:crosshair;border-radius:6px;" +
      "right:" + M.margin + "px;bottom:" + M.margin + "px;" +
      "background:" + M.colors.bg + ";border:1px solid " + M.colors.frame + ";";
    box.style.position = "relative";
    box.appendChild(mini);
    miniPen = mini.getContext("2d");

    // 누르거나 끌면 그 자리를 본 그래프 한가운데로. 배율은 그대로 둔다.
    let pressed = false;
    mini.addEventListener("pointerdown", function (ev) {
      pressed = true;
      try { mini.setPointerCapture(ev.pointerId); } catch (e) {}
      ev.preventDefault();
      jump(ev);
    });
    mini.addEventListener("pointermove", function (ev) { if (pressed) jump(ev); });
    function release() {
      if (!pressed) return;
      pressed = false;
      remember();
    }
    mini.addEventListener("pointerup", release);
    mini.addEventListener("pointercancel", release);
  }

  // 전체 범위. 노드 상자 크기까지 넣어야 가장자리 노드가 잘리지 않는다.
  function bounds() {
    let at;
    try { at = network.getPositions(); } catch (e) { return null; }
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const id in at) {
      const p = at[id];
      const node = (network.body.nodes || {})[id];
      const shape = (node && node.shape) || {};
      const hw = (shape.width || 0) / 2, hh = (shape.height || 0) / 2;
      x0 = Math.min(x0, p.x - hw); x1 = Math.max(x1, p.x + hw);
      y0 = Math.min(y0, p.y - hh); y1 = Math.max(y1, p.y + hh);
    }
    if (!isFinite(x0) || x1 - x0 < 1 || y1 - y0 < 1) return null;
    return {x0: x0, y0: y0, x1: x1, y1: y1};
  }

  // 미니맵 크기와 줄이는 비율. 전체 범위의 가로세로 비를 따른다.
  function sizeMini() {
    const box = document.getElementById("mynetwork");
    const B = bounds();
    if (!box || !mini || !B) { miniFit = null; return; }
    const M = CFG.mini;
    const gw = B.x1 - B.x0, gh = B.y1 - B.y0;
    let w = Math.max(M.minWidth, Math.min(M.maxWidth, box.clientWidth * M.share));
    let h = w * gh / gw;
    if (h > M.maxHeight) { h = M.maxHeight; w = Math.max(M.minWidth, h * gw / gh); }
    const k = Math.min((w - 2 * M.pad) / gw, (h - 2 * M.pad) / gh);
    miniFit = {
      k: k, w: w, h: h, dpr: window.devicePixelRatio || 1,
      ox: (w - gw * k) / 2 - B.x0 * k,
      oy: (h - gh * k) / 2 - B.y0 * k,
    };
    mini.style.width = Math.round(w) + "px";
    mini.style.height = Math.round(h) + "px";
  }

  function drawMini() {
    if (!mini || !miniPen) return;
    if (miniDirty) { sizeMini(); miniDirty = false; }
    const f = miniFit;
    if (!f) return;
    // 폭을 다시 넣으면 캔버스가 비워지고 변형도 풀린다. 그 뒤에 변형을 건다.
    mini.width = Math.max(1, Math.round(f.w * f.dpr));
    mini.height = Math.max(1, Math.round(f.h * f.dpr));
    miniPen.setTransform(f.dpr, 0, 0, f.dpr, 0, 0);

    let at;
    try { at = network.getPositions(); } catch (e) { return; }
    const C = CFG.mini.colors;
    const X = (x) => f.ox + x * f.k;
    const Y = (y) => f.oy + y * f.k;

    miniPen.lineWidth = 1;
    miniPen.strokeStyle = C.edge;
    miniPen.beginPath();
    for (const e of DATA.links) {
      const a = at[e[0]], b = at[e[1]];
      if (!a || !b) continue;
      miniPen.moveTo(X(a.x), Y(a.y));
      miniPen.lineTo(X(b.x), Y(b.y));
    }
    miniPen.stroke();

    for (const id in at) {
      const on = !!lit[id];
      const info = DATA.nodes[id] || {};
      const r = on ? CFG.mini.litDot : CFG.mini.dot;
      miniPen.fillStyle = on ? C.lit : (info.group ? C.group : C.node);
      miniPen.fillRect(X(at[id].x) - r, Y(at[id].y) - r, 2 * r, 2 * r);
    }

    // 본 그래프가 지금 보는 자리. 칸의 두 모서리를 그래프 좌표로 옮긴다.
    const box = document.getElementById("mynetwork");
    if (!box) return;
    let a, b;
    try {
      a = network.DOMtoCanvas({x: 0, y: 0});
      b = network.DOMtoCanvas({x: box.clientWidth, y: box.clientHeight});
    } catch (e) { return; }
    miniPen.fillStyle = C.viewFill;
    miniPen.strokeStyle = C.view;
    miniPen.lineWidth = 1.5;
    miniPen.beginPath();
    miniPen.rect(X(a.x), Y(a.y), (b.x - a.x) * f.k, (b.y - a.y) * f.k);
    miniPen.fill();
    miniPen.stroke();
  }

  // 카메라 · 칸 크기 · 좌표가 바뀐 프레임에만 다시 그린다. 읽기뿐이다.
  function watchMini() {
    const box = document.getElementById("mynetwork");
    let key = "", size = "";
    try {
      const p = network.getViewPosition();
      key = network.getScale().toFixed(5) + "," + p.x.toFixed(1) + "," + p.y.toFixed(1);
      size = box ? box.clientWidth + "x" + box.clientHeight : "";
    } catch (e) {}
    if (size !== miniSize) { miniSize = size; miniDirty = true; }
    if (key !== miniKey || miniDirty) {
      miniKey = key;
      drawMini();
    }
    window.requestAnimationFrame(watchMini);
  }

  // 미니맵에서 누른 자리를 본 그래프 한가운데로. 사람이 손으로 하는 일이다.
  function jump(ev) {
    const f = miniFit;
    if (!f || !mini) return;
    const r = mini.getBoundingClientRect();
    const x = (ev.clientX - r.left - f.ox) / f.k;
    const y = (ev.clientY - r.top - f.oy) / f.k;
    halt();
    touched = true;
    if (TRACE && due("jump", CFG.busyMs)) trace("camera", "MINIMAP_JUMP", where());
    try { network.moveTo({position: {x: x, y: y}, animation: false}); } catch (e) {}
  }

  // ══════════════════════════════════════════════════ 3. 카메라
  //
  // ★ **카메라를 움직이는 자리는 여기 모인 것뿐이다.** 화면 다시 그리기 ·
  // 칸 크기 바뀜 · rAF · 흐름 · 미니맵 그리기 · 끌기 · 마우스 올리기는 카메라를
  // 못 부른다.
  //
  //   자리 잡기      전체를 칸에 맞춤. 같은 해석의 iframe 이 새로 만들어졌으면
  //                  마지막 카메라로. 사람이나 좁혀 들어가기가 잡기 전까지만
  //   새 해석       발화 하나에 한 번. 전체를 잠깐 보여준 뒤 고른 자리로
  //   후보 누르기    누를 때마다 한 번
  //   배경 누르기    후보 전부로 되돌아갈 때 한 번
  //   미니맵 누르기  누른 자리로 (jump)
  //
  // 좁혀 들어가기는 도는 동안 다시 들어오면 앞의 것을 버리고 새 것 하나만
  // 돈다(token). 겹쳐 돌면 앞 애니메이션이 제 도착점으로 튀어 화면이 왕복한다.
  const camera = {token: 0, timers: []};

  // 사람이 만졌거나 좁혀 들어가기가 카메라를 잡았다. 그 뒤로는 자리 잡기를 안 한다.
  let touched = false;

  // 되살릴 카메라. 있으면 자리 잡기가 전체 대신 이것으로 간다.
  let pinned = null;

  function halt() {
    if (TRACE && camera.timers.length) {
      if (TRACE) trace("camera", "CAMERA_CANCEL",
            "token=" + camera.token + " pending=" + camera.timers.length);
    }
    camera.token += 1;
    for (const t of camera.timers) window.clearTimeout(t);
    camera.timers = [];
    return camera.token;
  }

  // 전체를 잠깐 보여준 뒤 그 자리로 들어간다. 도착점은 fit 이 정한다.
  //
  // ★ 두 단계를 시각으로 잇는다. 앞 단계가 끝나기 전에 뒤 단계를 걸면
  // vis-network 가 앞 것을 도착점으로 튕기고 새로 시작해서 화면이 튄다.
  // 그래서 여유를 두고, 그 사이 새 명령이 들어오면 token 으로 버린다.
  function glide(ids, why) {
    if (!ids || !ids.length) {
      if (TRACE) trace("camera", "GLIDE_SKIP", "why=" + why + " nodes=0");
      return;
    }
    if (TRACE) trace("camera", "GLIDE_ENTER",
          "why=" + why + " token=" + camera.token +
          " nodes=" + ids.join(",") + " " + where());
    const mine = halt();
    touched = true;
    if (TRACE) trace("camera", "WHOLE_FIT_START",
          "why=" + why + " token=" + mine + " dur=" + CFG.hold + " " + where());
    try {
      network.fit({animation: {duration: CFG.hold, easingFunction: "easeInOutQuad"}});
    } catch (e) {}
    camera.timers.push(window.setTimeout(function () {
      if (mine !== camera.token) {
        if (TRACE) trace("camera", "TARGET_FIT_DROPPED",
              "why=" + why + " token=" + mine + " now=" + camera.token);
        return;   // 더 새로운 명령이 들어왔다
      }
      if (TRACE) trace("camera", "TARGET_FIT_START",
            "why=" + why + " token=" + mine + " dur=" + CFG.move +
            " nodes=" + ids.join(",") + " " + where());
      try {
        network.fit({
          nodes: ids,
          maxZoomLevel: CFG.maxScale,
          animation: {duration: CFG.move, easingFunction: "easeInOutQuad"},
        });
      } catch (e) {}
      // 도착했을 무렵의 화면. 라이브러리가 끝을 알려주지 않아 시각으로 잰다.
      // ★ 로그를 위해서만 있는 타이머다. 꺼져 있으면 만들지도 않는다.
      if (TRACE) {
        window.setTimeout(function () {
          trace("camera", "TARGET_FIT_SETTLED",
                "why=" + why + " token=" + mine + " " + where());
        }, CFG.move + 60);
      }
    }, CFG.hold + CFG.gapMs));
    if (TRACE) trace("camera", "GLIDE_EXIT", "why=" + why + " token=" + mine);
  }

  // ── iframe 밖에 적어 두는 것 ────────────────────────────────────────
  //
  // 「이미 보여줬다」와 마지막 카메라를 이 문서 안에 두면 안 된다 — Streamlit 은
  // 무엇을 누르든 스크립트를 다시 돌리고, 그때 iframe 이 새로 만들어지면 문서
  // 안의 변수가 사라진다. 창 저장소에 맡기고, 막히면 부모 창으로 떨어진다.
  const remembered = {};

  function recall(key) {
    try {
      const raw = window.sessionStorage.getItem(key);
      if (raw !== null) {
        if (TRACE) trace("debug", "MEMORY_READ",
              "tier=session key=" + key + " value=" + JSON.stringify(raw));
        return raw;
      }
    } catch (e) {
      if (TRACE) trace("debug", "MEMORY_READ", "tier=session key=" + key + " error=1");
    }
    try {
      const bagged = window.parent.__graphFocus;
      if (bagged && bagged[key] !== undefined) {
        if (TRACE) trace("debug", "MEMORY_READ",
              "tier=parent key=" + key + " value=" + JSON.stringify(bagged[key]));
        return bagged[key];
      }
    } catch (e) {
      if (TRACE) trace("debug", "MEMORY_READ", "tier=parent key=" + key + " error=1");
    }
    return remembered[key] === undefined ? null : remembered[key];
  }

  function keep(key, value) {
    remembered[key] = value;
    let ok = "document";
    try { window.sessionStorage.setItem(key, value); ok = "session"; } catch (e) {}
    try {
      const top = window.parent;
      if (!top.__graphFocus) top.__graphFocus = {};
      top.__graphFocus[key] = value;
      if (ok === "document") ok = "parent";
    } catch (e) {}
    if (TRACE) trace("debug", "MEMORY_WRITE",
          "tier=" + ok + " key=" + key + " value=" + JSON.stringify(value));
  }

  // ── 새 해석 : 발화 하나에 한 번 ────────────────────────────────────
  //
  // 출력  좁혀 들어가기를 걸었는가
  function focusOnce(ids) {
    // ★ 조건과 차례를 안 바꾼다. 읽은 값을 적어 두고 그대로 판단한다.
    const seenSig = CFG.sig ? recall(CFG.memory) : null;
    if (TRACE) trace("camera", "FOCUS_ONCE_ENTER",
          "sig=" + JSON.stringify(CFG.sig || "") +
          " seen=" + JSON.stringify(seenSig) +
          " same=" + (CFG.sig === seenSig) + " nodes=" + (ids || []).length);
    if (!CFG.sig || CFG.sig === seenSig) {
      if (TRACE) trace("camera", "FOCUS_ONCE_SKIP", "reason=" + (CFG.sig ? "already-shown" : "no-sig"));
      return false;
    }
    keep(CFG.memory, CFG.sig);
    if (!ids || !ids.length) return false;   // 실행 전 · NO_MATCH 는 전체 맞추기로
    glide(ids, "resolve");
    return true;
  }

  // ── 마지막 카메라 : 같은 해석을 다시 그릴 때 ──────────────────────
  //
  // 사람이 옮긴 화면이나 좁혀 들어간 화면을, iframe 이 새로 만들어져도 그대로
  // 둔다. 이 해석의 서명과 함께 적으므로 다른 해석에는 안 쓰인다.
  function remember() {
    if (!CFG.sig) return;
    try {
      const p = network.getViewPosition();
      keep(CFG.memory + "_view", JSON.stringify(
        {sig: CFG.sig, scale: network.getScale(), x: p.x, y: p.y}));
    } catch (e) {}
  }

  // ★ 한 번 옮기고 끝내지 않는다. 칸 크기가 늦게 정해지면 vis-network 가 폭 비율로
  // 배율을 다시 잡아 되살린 자리가 어긋난다. 자리 잡기가 칸 크기를 따라 다시 건다.
  function restoreView() {
    let saved = null;
    try { saved = JSON.parse(recall(CFG.memory + "_view") || "null"); } catch (e) {}
    if (!saved || saved.sig !== CFG.sig) return false;
    if (TRACE) trace("camera", "VIEW_RESTORE", "scale=" + saved.scale);
    pinned = saved;
    return true;
  }

  // 사람이 카메라를 움직이면 적는다. 좁혀 들어가기가 끝나도 적는다. 읽기뿐이다.
  function track() {
    network.on("dragStart", () => { touched = true; });
    network.on("zoom", () => { touched = true; remember(); });
    network.on("dragEnd", () => { remember(); });
    network.on("animationFinished", () => { remember(); });
    // 노드를 옮기면 미니맵 범위를 다시 잰다
    network.on("dragging", (params) => {
      if ((params.nodes || []).length) miniDirty = true;
      if (TRACE && due("drag", CFG.busyMs)) trace("debug", "NODE_DRAG", where());
    });
  }

  // ── 자리 잡기 : 전체를 칸에, 또는 마지막 카메라로 ──────────────────
  //
  // pyvis 는 fit 을 한 번도 안 부른다. 그래서 카메라가 기본값 그대로이고 칸이
  // 아무리 넓어도 그래프가 그 자리에 머문다. 칸 크기가 늦게 정해지는 경우가
  // 있어 한 번 더 잡은 뒤 칸 크기를 따라간다. 누가 카메라를 잡은 뒤로는 안 한다.
  function settle(why) {
    if (touched) {
      if (TRACE) trace("camera", "SETTLE_SKIP", "why=" + why + " reason=touched");
      return;
    }
    if (TRACE) trace("camera", pinned ? "SETTLE_RESTORE" : "SETTLE_FIT", "why=" + why + " " + where());
    try {
      if (pinned) {
        network.moveTo({position: {x: pinned.x, y: pinned.y}, scale: pinned.scale,
                        animation: false});
      } else {
        network.fit({});
      }
    } catch (e) {}
  }

  function overview() {
    settle("start");
    window.requestAnimationFrame(() => settle("frame"));
    window.setTimeout(() => settle("timeout"), 120);
    try {
      new ResizeObserver(function () {
        if (TRACE) trace("camera", "RESIZE_OBSERVER", "target=main");
        settle("resize");
      }).observe(document.getElementById("mynetwork"));
    } catch (e) {
      window.addEventListener("resize", () => settle("window-resize"));
    }
  }

  // ══════════════════════════════════════════════════ 4. 고르기 · 살펴보기
  let picked = null;

  // 고른 후보만 또렷하게. 목록에서 줄을 빼지 않는다 — 후보가 몇이었는지는
  // 좁힌 뒤에도 보여야 한다.
  function mark(key) {
    const rows = document.querySelectorAll("#recipes .recipe");
    for (let i = 0; i < rows.length; i++) {
      const one = !key || DATA.order[i] === key;
      rows[i].classList.toggle("off", !one);
    }
  }

  // ★ 그림만 바꾼다. 카메라는 부르는 쪽이 따로 정한다.
  function repaint() {
    const key = (picked && DATA.patches[picked]) ? picked : "";
    const patch = DATA.patches[key];
    if (!patch) return null;
    try {
      network.body.data.edges.update(patch.edges);
      network.body.data.nodes.update(patch.nodes);
    } catch (e) {}
    flow = reduced() ? [] : (patch.flow || []);
    lit = {};
    for (const id of patch.focus || []) lit[id] = true;
    miniKey = "";              // 미니맵의 강조도 함께 바뀐다
    mark(key);
    return patch;
  }

  function clicked(next, why) {
    if (TRACE) trace("camera", why === "background" ? "BACKGROUND_CLICK" : "CANDIDATE_CLICK",
          "from=" + JSON.stringify(picked) + " to=" + JSON.stringify(next) +
          " changed=" + (next !== picked) + " " + where());
    if (next === picked) return;
    picked = next;
    const patch = repaint();
    if (patch) glide(patch.focus, why);
  }

  // 누른 노드를 살펴보기 칸에. 이름 · 종류 · 설명 · 그 노드를 지나는 후보.
  // 글자는 textContent 로만 넣는다 — 설명에 꺾쇠가 섞여도 마크업이 안 된다.
  function inspect(id) {
    const panel = document.getElementById("node");
    if (!panel) return;
    const info = id ? DATA.nodes[id] : null;
    panel.classList.toggle("filled", !!info);
    if (!info) return;
    panel.querySelector(".nname").textContent = info.name;
    const kind = panel.querySelector(".nkind");
    kind.textContent = info.kind;
    kind.classList.toggle("group", !!info.group);
    panel.querySelector(".ntext").textContent = info.text;
    const owners = [];
    DATA.order.forEach(function (rid, i) {
      const patch = DATA.patches[rid];
      if (patch && (patch.focus || []).indexOf(id) >= 0) owners.push("[" + (i + 1) + "] " + rid);
    });
    panel.querySelector(".nown").textContent =
      owners.length ? CFG.ownerLabel + "  " + owners.join("   ") : "";
  }

  // 살펴보기 칸을 채운다. 후보 줄을 누르면 그 후보로 좁히고, 다시 누르면 전부로.
  function fillSide() {
    const list = document.querySelector("#recipes .list");
    if (list && !list.childElementCount) list.innerHTML = DATA.recipes || "";
    const state = document.querySelector("#recipes .state");
    if (state) state.textContent = DATA.status || "";
    const rows = document.querySelectorAll("#recipes .recipe");
    for (let i = 0; i < rows.length; i++) {
      rows[i].addEventListener("click", function () {
        const key = DATA.order[i];
        clicked(picked === key ? null : key, "candidate");
      });
    }
  }

  // ══════════════════════════════════════════════════ 5. 시작
  function start() {
    if (typeof network === "undefined") { window.setTimeout(start, 60); return; }
    if (TRACE) trace("debug", "NETWORK_READY", where());

    makeLayer();
    window.requestAnimationFrame(animate);
    makeMini();
    window.requestAnimationFrame(watchMini);
    track();
    fillSide();

    network.on("click", function (params) {
      const id = (params.nodes || [])[0];
      if (!id) {
        // 배경을 누르면 후보 전부로 돌아가고 살펴보기 칸을 비운다.
        inspect(null);
        clicked(null, "background");
        return;
      }
      inspect(id);
      // 그 노드를 가진 후보가 하나뿐일 때만 좁힌다. 여럿이 함께 쓰는
      // 노드는 어느 후보인지 가릴 근거가 없어 설명만 보여준다.
      const only = DATA.picks[id];
      if (!only) {
        if (TRACE) trace("camera", "NODE_CLICK_AMBIGUOUS", "node=" + id);
        return;
      }
      clicked(picked === only ? null : only, "candidate");
    });

    // 첫 그림. 새 해석이면 좁혀 들어가고, 같은 해석을 다시 그린 것이면
    // 마지막 카메라로 돌아가고(restoreView 가 자리를 정하고 overview 가 건다),
    // 둘 다 아니면 전체를 칸에 맞춘다.
    if (TRACE) trace("camera", "RESOLVE_RECEIVED",
          "sig=" + JSON.stringify(CFG.sig || "") +
          " variants=" + Object.keys(DATA.patches || {}).length +
          " picks=" + Object.keys(DATA.picks || {}).length);
    const patch = repaint();
    if (!(patch && focusOnce(patch.focus))) restoreView();
    overview();
  }
  start();
})();
</script>
"""


def graph_script(*, signature, data) -> str:
    """브라우저에서 도는 한 벌.

    입력  signature 이 해석의 서명. 같으면 다시 안 좁힘
          data      변형별 스타일 표 · 후보 목록 · 줄 차례 · 노드→후보 표 ·
                    노드 설명 · 미니맵 엣지
    출력  <script> 태그까지 포함한 문자열
    제약  색과 굵기를 여기서 정하지 않는다. 파이썬이 만든 표를 고를 뿐이다
    """
    config = {
        "sig": signature,
        "memory": FOCUS_MEMORY,
        "dash": FLOW_DASH,
        "gap": FLOW_GAP,
        "period": FLOW_PERIOD_SECONDS,
        "width": FLOW_WIDTH,
        "sheen": FLOW_SHEEN,
        # 흰 표시가 어디서 멈출지를 재는 데 쓴다. vis-network 가 화살촉을
        # 놓는 식(15 * scaleFactor + 3 * 선굵기)과 같은 값이어야 한다.
        "arrowScale": ARROW_SCALE,
        "edgeWidth": EDGE_WIDTH_HIGHLIGHT,
        "gapMs": FOCUS_GAP_MS,
        "trace": CAMERA_TRACE,
        "sampleMs": FLOW_SAMPLE_MS,
        "busyMs": BUSY_SAMPLE_MS,
        "hold": FOCUS_HOLD_MS,
        "move": FOCUS_MOVE_MS,
        "maxScale": FOCUS_MAX_SCALE,
        "pad": FOCUS_PAD,
        "ownerLabel": "지나는 후보",
        "mini": {
            "margin": MINIMAP_MARGIN,
            "share": MINIMAP_SHARE,
            "minWidth": MINIMAP_MIN_WIDTH,
            "maxWidth": MINIMAP_MAX_WIDTH,
            "maxHeight": MINIMAP_MAX_HEIGHT,
            "pad": MINIMAP_PAD,
            "dot": MINIMAP_DOT,
            "litDot": MINIMAP_LIT_DOT,
            "colors": data.pop("miniColors", {}),
        },
    }
    return (GRAPH_SCRIPT
            .replace("__CFG__", embed_json(config))
            .replace("__DATA__", embed_json(data)))


def main_html(model, colors, recipes="", *, status="", order=(), height,
              signature="", side_ratio=0.28) -> str:
    """서비스 화면의 그래프 문서 한 벌. 본 그래프 · 미니맵 · 살펴보기 칸.

    입력  model       render 응답의 "network"
          colors      /screen 의 colors
          recipes     후보 recipe 목록 마크업 (path_panel.recipe_rows_markup)
          status      후보 목록 머리에 적을 판정 한 마디. 없으면 빈 문자열
          order       마크업 줄 차례에 맞춘 recipe id
          height      픽셀 높이
          signature   이 해석의 서명
          side_ratio  살펴보기 칸이 차지하는 폭 비율
    출력  iframe 에 넣을 HTML 문서
    규칙  실행 전에는 온톨로지 전체를 칸에 맞춰 보여줌. 강조 없음
          해석이 오면 처음 한 번 전체를 잠깐 보여준 뒤 후보 전부로 좁혀 들어감.
          서명이 같으면 안 돎 — 같은 해석을 다시 그릴 때는 마지막 카메라로 돌아감
          노드를 누르면 살펴보기 칸에 그 노드의 이름 · 종류 · 설명을 적음.
          그 노드를 가진 후보가 하나일 때만 그 후보로 좁힘
          후보 줄을 누르면 그 후보로 좁힘. 다시 누르거나 배경을 누르면 전부로
          변형 스타일은 파이썬이 미리 만들어 넘김. JS 는 고르기만 함
    제약  라이브러리 캔버스를 우리가 다시 그리지 않는다.
          흐르는 표시와 미니맵은 제 캔버스에 그림
          좁힌다고 목록에서 줄을 빼지 않는다. 흐려질 뿐임
          pyvis 마크업 안에 끼워 넣지 않는다. 살펴보기 칸은 .card 옆에 나란히 섬 —
          그 안을 헤집으면 pyvis 판이 바뀔 때 조용히 깨짐
          CDN 을 부르지 않는다. cdn_resources="in_line" 이라 인터넷 없이 뜸
    """
    script = graph_script(
        signature=signature,
        data={
            "patches": variant_patches(model, colors),
            "recipes": recipes,
            "status": status,
            "order": list(order),
            "picks": model.get("picks") or {},
            "nodes": node_details(model),
            "links": minimap_links(model),
            "miniColors": minimap_colors(colors),
        },
    )
    css = (SPLIT_CSS.format(side=round(side_ratio * 100, 2))
           + SIDE_CSS.format(plain=colors.get("plain", "#8C93A1"),
                             lit=colors.get("highlight", "#14B8A6"),
                             group=colors.get("group", "#D9A441")))

    net = build_network(model, colors, height=height)
    html = _without_cdn(net.generate_html(notebook=False))
    # 바꿀 글자를 함수로 넘긴다. 문자열로 넘기면 JSON 안의 역슬래시를 re 가 풀어 버린다.
    style = "<style>" + BASE_CSS + css + "</style></head>"
    html = re.sub(r"</head>", lambda _: style, html, count=1)
    return re.sub(r"</body>", lambda _: SIDE_BOX + script + "</body>", html, count=1)
