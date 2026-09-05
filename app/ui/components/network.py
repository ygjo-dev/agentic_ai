"""온톨로지 그래프를 **interactive graph library** 로 그린다.

    pyvis (vis-network 9.1.2) 를 쓴다.

## 왜 갈았나

예전에는 서버가 Graphviz 로 SVG 를 완성해 보내고, `zoom.py` 가 그 위에 CSS
transform 을 얹어 확대 · 끌기를 흉내 냈다. 그림 자체는 정지 이미지라 노드를
집어 옮길 수 없고, 손잡이 한 벌이 전부 우리가 쓴 JS 였다. 여기서는 그리는
일을 라이브러리에 넘긴다 — 노드 끌기 · 화면 끌기 · 휠 확대 · 마우스를 올리면
설명이 뜨는 것이 전부 vis-network 것이다.

**JS 번들을 베껴 오지 않는다.** pyvis 가 제 패키지 안에 vis-network 를 들고
있고 `cdn_resources="in_line"` 이 그것을 문서에 넣는다. 인터넷이 없어도 뜬다.

## 무엇이 그대로인가

    /screen 응답      한 칸도 안 바뀌었다
    온톨로지 · 배선   안 건드렸다
    좌표              서버의 layout.json 그대로다. 물리 시뮬레이션을 끈다
    색                dot.COLORS 한 곳에서만 온다
    Graphviz SVG      안 지웠다. dev/tools/export_graph.py 가 정지 그림을 쓴다

**좌표를 라이브러리가 다시 잡게 두지 않는다.** 물리 시뮬레이션을 켜면 노드를
등록할 때마다 지도가 통째로 다시 흔들려서, 「노드를 등록해도 기존 노드가
0.0000pt 움직인다」는 시연의 핵심 장면이 없어진다. 그래서 physics 를 끄고
좌표는 서버가 준 값을 그대로 박는다. 사람이 손으로 끌어 옮기는 것은 그대로
되고, 그것은 그 사람의 화면에서만 움직인다.

**y 를 뒤집는다.** Graphviz 는 위로 갈수록 y 가 커지고 vis-network 는 아래로
갈수록 커진다. 안 뒤집으면 지도가 상하로 뒤집힌 채 뜬다.
"""

import json
import re

from pyvis.network import Network

# 노드 이름의 줄바꿈. DOT 는 역슬래시와 n 두 글자로 적는데 라이브러리는 진짜
# 줄바꿈을 받는다. 서버가 만든 라벨을 그대로 쓰되 이 한 가지만 바꾼다.
DOT_NEWLINE = "\\n"

# 순번 키의 구분자. build.network_payload 가 같은 글자로 만든다.
ORDER_SEP = ">"

# 노드 상자.
NODE_FONT_SIZE = 15
NODE_SHAPE = "box"
NODE_MARGIN = 8
NODE_BORDER_WIDTH = 1
NODE_BORDER_WIDTH_MARKED = 4

# 엣지 굵기. 배경보다 강조가 굵어야 위에 떠 보인다.
EDGE_WIDTH = 1.6
EDGE_WIDTH_TOP = 4.5
EDGE_WIDTH_HIGHLIGHT = 5
EDGE_WIDTH_MARK = 5

# 배경 실선을 얼마나 물러나게 둘까. 강조가 그 위에 떠 보여야 한다.
DIM_OPACITY = 0.45

# 서버 좌표를 라이브러리 화면 좌표로 옮길 때의 배율. 1.0 이면 그대로다.
COORD_SCALE = 1.0

# 등록 장면의 주황 둘. /screen 의 colors 에는 없어서 여기에 기본값을 둔다 —
# dot.py 의 PATH_NEW · PATH_NEW_DIM 과 같은 값이고, colors 에 그 키가 실리면
# 그쪽이 이긴다.
PATH_NEW = "#E8862A"
PATH_NEW_DIM = "#8A6234"


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
            "smooth": {"enabled": True, "type": "continuous"},
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.6}},
        },
    })


def build_network(model, colors, *, top, variant="", height=480):
    """/render 의 network 모형을 vis-network 그래프로.

    입력  model    render 응답의 "network"
          colors   /screen 의 colors. 팔레트의 주인은 서버임
          top      상단 그래프인가. 상단은 점선만 그림
          variant  하단에서 보여줄 변형 키
          height   픽셀 높이
    출력  pyvis Network
    규칙  상단은 점선(about)만. 하단은 배경 실선 위에 강조를 얹음.
          SVG 때의 규칙 그대로임
          강조 · 짙은 주황 · 옅은 주황을 서버가 이미 갈라 보냄.
          여기서 무엇이 강조인지 다시 판단하지 않음
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

    칸 = (model.get("variants") or {}).get(variant) or {}
    강조_노드 = set(칸.get("nodes") or ())
    테두리 = colors.get("node_border_top" if top else "node_border", "#A9B1C0")
    배경 = colors.get("node_fill", "#171B26")
    글자 = colors.get("plain", "#8C93A1")

    for node_id, node in (model.get("nodes") or {}).items():
        x, y = model["positions"][node_id]
        새것 = bool(node.get("new"))
        짚음 = 새것 or node_id in 강조_노드
        if 새것:
            선색 = colors.get("new", "#F2589D")
        elif node_id in 강조_노드:
            선색 = colors.get("highlight", "#14B8A6")
        else:
            선색 = 테두리
        칠 = {"border": 선색, "background": 배경,
              "highlight": {"border": 선색, "background": 배경},
              "hover": {"border": 선색, "background": 배경}}
        net.add_node(
            node_id,
            label=_label(node["label"]),
            title=node.get("title") or "",
            x=x * COORD_SCALE,
            # Graphviz 는 위로, vis-network 는 아래로 y 가 큼.
            y=-y * COORD_SCALE,
            shape=NODE_SHAPE,
            margin=NODE_MARGIN,
            borderWidth=NODE_BORDER_WIDTH_MARKED if 짚음 else NODE_BORDER_WIDTH,
            color=칠,
            font={"size": NODE_FONT_SIZE, "color": 글자, "face": "sans-serif"},
        )

    점선색 = colors.get("dotted_top" if top else "dotted_bottom", "#8B84E8")
    for entry in model.get("dotted") or ():
        a, b = entry["edge"]
        net.add_edge(
            a, b,
            color=colors.get("new", "#F2589D") if entry.get("new") else 점선색,
            width=EDGE_WIDTH_TOP if top else EDGE_WIDTH,
            dashes=True,
            arrows="",
        )

    if not top:
        for style in solid_styles(model, colors, variant):
            net.add_edge(style.pop("from"), style.pop("to"), **style)

    net.set_options(options())
    return net


def edge_id(a: str, b: str) -> str:
    """실선 엣지 하나의 id. JS 가 이 id 로만 스타일을 갈아끼운다."""
    return f"{a}{ORDER_SEP}{b}"


def solid_styles(model: dict, colors: dict, variant: str) -> list[dict]:
    """한 변형에서 배경 실선이 어떻게 보여야 하는가.

    입력  network 모형 · 색 · 변형 키
    출력  vis-network 엣지 dict 목록. id · from · to · color · width · label
    규칙  짙은 주황(등록한 경로) > 옅은 주황(빠진 경로) > teal(해석 경로) >
          물러난 배경 차례로 걸림. build_dot 의 우선순위와 같음
          순번은 경로가 정확히 하나일 때만 서버가 보내므로 여기서 안 따짐
    제약  무엇이 강조인지 여기서 판단하지 않는다.
          서버(build.network_payload)가 이미 갈라 보냄. 두 곳에서 판단하면
          그림과 칩이 조용히 어긋남
    """
    칸 = (model.get("variants") or {}).get(variant) or {}
    실선색 = colors.get("edge", "#4A5262")
    강조 = {tuple(e) for e in 칸.get("highlight") or ()}
    표시 = {tuple(e) for e in 칸.get("mark") or ()}
    물러남 = {tuple(e) for e in 칸.get("dim") or ()}
    순번 = 칸.get("order") or {}

    out = []
    for a, b in (tuple(e) for e in model.get("solid") or ()):
        if (a, b) in 표시:
            색, 굵기 = colors.get("new_path", PATH_NEW), EDGE_WIDTH_MARK
        elif (a, b) in 물러남:
            색, 굵기 = colors.get("new_path_dim", PATH_NEW_DIM), EDGE_WIDTH
        elif (a, b) in 강조:
            색, 굵기 = colors.get("highlight", "#14B8A6"), EDGE_WIDTH_HIGHLIGHT
        else:
            색, 굵기 = _rgba(실선색, DIM_OPACITY), EDGE_WIDTH
        out.append({
            "id": edge_id(a, b), "from": a, "to": b,
            "color": 색, "width": 굵기,
            "label": str(순번.get(f"{a}{ORDER_SEP}{b}") or ""),
        })
    return out


def node_styles(model: dict, colors: dict, variant: str) -> list[dict]:
    """한 변형에서 노드 테두리가 어떻게 보여야 하는가.

    출력  vis-network 노드 dict 목록. id · color · borderWidth
    규칙  새 노드(분홍)가 강조(teal)를 이김. 「무엇이 새로 생겼는가」는 어느
          후보를 보든 같은 사실이라 좁혀도 안 변함
    """
    칸 = (model.get("variants") or {}).get(variant) or {}
    강조_노드 = set(칸.get("nodes") or ())
    배경 = colors.get("node_fill", "#171B26")
    테두리 = colors.get("node_border", "#A9B1C0")

    out = []
    for node_id, node in (model.get("nodes") or {}).items():
        새것 = bool(node.get("new"))
        짚음 = 새것 or node_id in 강조_노드
        선색 = (colors.get("new", "#F2589D") if 새것
                else colors.get("highlight", "#14B8A6") if node_id in 강조_노드
                else 테두리)
        out.append({
            "id": node_id,
            "color": {"border": 선색, "background": 배경,
                      "highlight": {"border": 선색, "background": 배경},
                      "hover": {"border": 선색, "background": 배경}},
            "borderWidth": NODE_BORDER_WIDTH_MARKED if 짚음 else NODE_BORDER_WIDTH,
        })
    return out


def variant_patches(model: dict, colors: dict) -> dict:
    """변형마다의 스타일 한 벌. **파이썬이 만들고 JS 는 고르기만 한다.**

    출력  {변형 키: {"edges": [...], "nodes": [...]}}
    규칙  JS 가 색 · 굵기 규칙을 하나도 모르게 함. 누르면 이 표에서 골라
          vis-network 의 DataSet.update 에 그대로 넘김
    제약  JS 에서 다시 칠하지 않는다.
          예전 SVG 판의 「파이썬이 변형을 만들고 JS 는 고르기만 한다」와 같은
          규칙임. 규칙이 두 곳으로 갈라지면 한쪽만 고쳤을 때 조용히 어긋남
    """
    return {
        key: {
            "edges": solid_styles(model, colors, key),
            "nodes": node_styles(model, colors, key),
        }
        for key in (model.get("variants") or {})
    }


# pyvis 문서가 CDN 에서 끌어오는 것. **vis-network 는 여기 없다** — 그것은
# cdn_resources="in_line" 로 문서 안에 실려 있고, 이 둘은 pyvis 가 제 버튼과
# 선택 상자를 꾸미는 데 쓰는 Bootstrap 이다. 우리는 그 UI 를 안 쓴다.
#
# 지우는 까닭은 시연 장소의 망을 안 믿기 때문이다. 남겨 두면 인터넷이 없을 때
# 브라우저가 두 번 기다렸다 실패하고, 그 사이 그래프가 늦게 뜬다.
# ★ 라이브러리를 베껴 오는 것이 아니라 안 쓰는 것을 빼는 것이다.
CDN_TAGS = (
    '<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.0.0-beta3/dist/js/'
    'bootstrap.bundle.min.js" integrity="sha384-JEW9xMcG8R+pH31jmWH6WWP0WintQrMb4s7ZOdauHnUtxwoG2vI5DkLtS3qm9Ekf"'
    ' crossorigin="anonymous"></script>',
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.0.0-beta3/'
    'dist/css/bootstrap.min.css" integrity="sha384-eOJMYsd53ii+scO/bJGFsiCZc+5NDVN2yr8+0RDqr0Ql0h+rP48ckxlpbzKgwra6"'
    ' crossorigin="anonymous">',
)


def _without_cdn(html: str) -> str:
    """CDN 태그를 뺌. 정규식으로 통째로 훑음 — pyvis 판이 바뀌면 속성 차례가 달라짐."""
    html = re.sub(
        r"<script[^>]+cdn\.jsdelivr\.net[^>]*>\s*</script>", "", html)
    html = re.sub(r"<link[^>]+cdn\.jsdelivr\.net[^>]*>", "", html)
    return html


# pyvis 기본 문서는 흰 카드로 뜬다. 어두운 화면에 흰 상자가 생기므로 덮는다.
TRANSPARENT_CSS = (
    "<style>html,body{background:transparent!important;margin:0;padding:0;}"
    "#mynetwork{background:transparent!important;border:none!important;}"
    ".card,.container,.container-fluid{background:transparent!important;"
    "border:none!important;padding:0!important;}</style>"
)


def network_html(model, colors, *, top, variant="", height=480):
    """iframe 에 넣을 문서 한 벌.

    출력  pyvis 가 만든 완성 HTML. vis-network 가 문서 안에 실려 있음
    제약  CDN 을 부르지 않는다.
          cdn_resources="in_line" 이라 인터넷 없이도 뜸. 시연 장소의 망을
          믿지 않음
    """
    net = build_network(model, colors, top=top, variant=variant, height=height)
    html = _without_cdn(net.generate_html(notebook=False))
    return re.sub(r"</head>", TRANSPARENT_CSS + "</head>", html, count=1)


# ── 하단 : 그래프와 칩을 한 문서에 ──────────────────────────────────
#
# 둘을 나누면 클릭마다 Streamlit 재실행이라 반응이 굼뜨다. 예전 SVG 판과 같은
# 판단이고, 다른 것은 왼쪽이 SVG 가 아니라 라이브러리 캔버스라는 것뿐이다.

# JSON 을 <script> 안에 넣을 때 "</script>" 가 섞이면 문서가 거기서 끊긴다.
SCRIPT_CLOSE = "</"
SCRIPT_CLOSE_SAFE = "<\\/"

BOTTOM_CSS = """
html, body {{ background: transparent !important; margin: 0; padding: 0;
  height: 100%; overflow: hidden;
  font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
  color: #E6E8EB; }}
#wrap {{ display: flex; height: 100vh; gap: 10px; }}
#netbox {{ flex: 0 0 {left}%; height: 100%; position: relative; }}
#mynetwork {{ width: 100% !important; height: 100% !important;
  background: transparent !important; border: none !important; }}
#list {{ flex: 1 1 auto; height: 100%; overflow-y: auto; padding-right: 4px;
  min-width: 0; }}
.card, .container, .container-fluid {{ background: transparent !important;
  border: none !important; padding: 0 !important; margin: 0 !important; }}
"""

# 누르면 좁히고 다시 누르면 푼다. **JS 가 색을 하나도 모른다** — 파이썬이 만든
# 표에서 골라 vis-network 의 DataSet 에 그대로 넘길 뿐이다.
PICK_SCRIPT = """
<script>
(function () {{
  const DATA = {data};
  let picked = null;

  function apply() {{
    const key = (picked && DATA.patches[picked]) ? picked : "";
    const patch = DATA.patches[key];
    if (!patch || typeof network === "undefined") return;
    try {{
      network.body.data.edges.update(patch.edges);
      network.body.data.nodes.update(patch.nodes);
    }} catch (e) {{ return; }}
    const list = document.getElementById("list");
    if (list) list.innerHTML = DATA.chips[key] || "";
  }}

  function attach() {{
    if (typeof network === "undefined") {{ setTimeout(attach, 60); return; }}
    const pickable = new Set(DATA.clickable);
    network.on("click", function (params) {{
      const id = (params.nodes || [])[0];
      if (!id || !pickable.has(id)) {{ picked = null; }}
      else {{ picked = (picked === id) ? null : id; }}
      apply();
    }});
    apply();
  }}
  attach();
}})();
</script>
"""


def embed_json(payload) -> str:
    """<script> 안에 넣어도 안전한 JSON 문자열.

    제약  값 안의 "</" 를 그대로 두지 않는다. "</script>" 가 섞이면 문서가
          거기서 끊김
    """
    return json.dumps(payload, ensure_ascii=False).replace(
        SCRIPT_CLOSE, SCRIPT_CLOSE_SAFE
    )


def bottom_html(model, colors, chips, *, left_ratio, clickable, height):
    """하단 문서 한 벌. 왼쪽이 라이브러리 그래프, 오른쪽이 칩 목록.

    입력  network 모형 · 색 · {변형 키: 칩 마크업} · 왼쪽 폭 비율 ·
          누를 수 있는 노드 id · 픽셀 높이
    출력  iframe 에 넣을 HTML 문서
    규칙  pyvis 가 만든 문서를 감싸서 씀. 그 안의 #mynetwork 를 왼쪽 칸에
          넣고 오른쪽에 칩 칸을 붙임
          변형 스타일은 파이썬이 미리 만들어 넘김. JS 는 고르기만 함
    제약  라이브러리 캔버스를 우리가 다시 그리지 않는다.
          노드 끌기 · 화면 끌기 · 휠 확대가 전부 vis-network 것이어야 함
    """
    html = network_html(model, colors, top=False, variant="", height=height)
    data = embed_json({
        "patches": variant_patches(model, colors),
        "chips": chips,
        "clickable": list(clickable or []),
    })

    css = "<style>" + BOTTOM_CSS.format(left=round(left_ratio * 100, 2)) + "</style>"
    html = re.sub(r"</head>", css + "</head>", html, count=1)
    # pyvis 의 #mynetwork 를 왼쪽 칸으로 감싸고 오른쪽에 칩 칸을 붙인다.
    html = html.replace(
        '<div id="mynetwork"',
        '<div id="wrap"><div id="netbox"><div id="mynetwork"', 1)
    html = re.sub(
        r"</body>",
        '</div><div id="list"></div></div>' + PICK_SCRIPT.format(data=data) + "</body>",
        html, count=1)
    return html
