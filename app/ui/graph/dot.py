"""온톨로지 → DOT 문자열. **배치를 계산시키려고 만든다.** 그리고 색의 단일 출처.

★ **2026-09-06 부터 여기서 나온 DOT 은 화면에 안 나간다.** Graphviz 에 넣어
좌표(pos · width · height)를 받아 오는 것이 전부이고, 화면 그래프는
`app/ui/components/network.py` 가 vis-network 로 그린다. 그래서 강조 · 등록
표시 · 물러난 경로처럼 **그리기에만 쓰던 인자 열둘을 그때 걷었다** — 그것이
어떤 좌표도 안 바꾼다는 것은 이미 시험이 지키고 있었다.

**남긴 것은 상자 크기를 바꾸는 것들이다.** 글꼴 · 글씨 크기 · 여백 · 최소
크기 · 도형 · 두 줄 접기 · 엣지 길이. 하나라도 빼면 여기서 잰 상자와 화면에
뜨는 상자가 달라져 겹침 판정이 헛돈다.

색은 여기 남는다. /screen 응답의 colors 로 UI 에 내려보내는 자리가 여기다 —
UI 가 자기 팔레트를 따로 들면 두 곳이 조용히 어긋나고, 그때 사람은 화면을
보고 코드를 의심한다.

브라우저를 모른다. Streamlit 도, HTML 도 모른다 — 문자열만 만든다.
"""

# 한글 노드 라벨이 깨지지 않도록 지정. Windows 기본 한글 폰트.
FONT = "Malgun Gothic"

# ------------------------------------------------------------ 색
# 배경이 투명이라 어느 테마에도 얹힌다. 색은 중간 톤으로 골라 밝은 배경에서도 읽힌다.
HIGHLIGHT_COLOR = "#14B8A6"  # 선택된 경로. 노드 테두리와 엣지에만 쓴다.
DOTTED_COLOR = "#7F77DD"  # 특성 관련. 실선과 확실히 구분되어야 한다.
PLAIN_COLOR = "#8C93A1"  # 그 밖의 모든 것.
# 새로 등록된 **노드 테두리**. 위 둘과 충분히 떨어진 분홍 계열로 골랐다 —
# teal(180°) · 보라(245°) 사이에서 330° 가 가장 멀다.
# 예전에는 새 점선과 새 실선도 이 색이었다. 지금은 노드 테두리 하나뿐이라
# 분홍이 "이번에 생긴 노드" 를 가리키는 유일한 신호다 (아래 등록 장면의 색).
NEW_COLOR = "#F2589D"

# 선이 뒤로 물러나고 노드가 앞으로 나오게 값을 배경(#0E1117) 대비비로 골랐다.
#   강조 7.6  >  노드 테두리 8.8(가늘다)  >  점선 2.9  >  실선 2.4  >  상단 1.5
# 32인치 모니터라 이 정도 섬세한 대비가 통한다. 프로젝터면 더 벌려야 한다.
NODE_BORDER = "#A9B1C0"  # 노드 테두리. 선보다 밝아야 앞으로 나온다.
NODE_FILL = "#171B26"    # 노드 배경. 배경과 거의 같아(1.10) 카드처럼 뜬다.

# 하단 = 답(주인공), 상단 = 배경 지도(참조용). 상단을 더 흐리게 둔다.
EDGE_COLOR = "#4A5262"           # 하단 실선  (대비 2.41)
EDGE_COLOR_TOP = "#2F3542"       # 상단 실선  (대비 1.54)
# 점선은 실선보다 확실히 밝아야 한다. 예전 값(#5B55A0, 대비 2.93)은 실선(2.41)과
# 거의 같은 밝기라 색상만으로 갈렸고, 다크 배경에서는 그것만으로 부족해 묻혔다.
# 지금은 2.45배 밝다. 다만 강조(teal 7.59)보다는 아래다 — 점선은 배경 정보이고
# 선택된 실행 경로가 주인공이라 이 위계가 뒤집히면 안 된다.
DOTTED_COLOR_BOTTOM = "#8B84E8"  # 하단 점선  (대비 5.91)
DOTTED_COLOR_TOP = "#615BA8"     # 상단 점선  (대비 3.21, 상단 실선의 2.1배)
# 상단 노드도 낮춘다 — 선만 흐리게 하면 상단 노드가 하단과 같은 무게로 경쟁한다.
NODE_BORDER_TOP = "#5A6474"

# 대상(group) 노드. 기능과 한눈에 갈려야 한다 — 실행할 수 있는 것과 개념은
# 다른 것이다. 색상환에서 기존 넷과 가장 가까운 것이 69°(분홍 330° vs 39°)라
# 충분히 떨어져 있다. 밝기는 노드 테두리(8.76)와 비슷한 8.40 — group 도 노드라
# 전경에 있어야 하고, 선(2.4~5.9)보다는 위에 있어야 한다.
GROUP_COLOR = "#D9A441"
GROUP_COLOR_TOP = "#8A6B2E"      # 상단용. 대비 3.80 으로 한 단계 낮춘다.

# ------------------------------------------------------------ 등록 장면의 색
# **색 하나가 뜻 하나다.** 예전에는 새 노드 · 새 점선 · 새 실행 경로 셋을 전부
# NEW_COLOR(분홍) 하나로 칠했다. 그래서 "무엇이 새로 생겼나" 와 "어떤 실행
# 경로가 생겼나" 가 겹쳐 보였고, 경로가 3~6개면 서로 뒤엉켜 읽히지 않았다.
#
#   분홍  새 노드 테두리와 새 관계(점선)  (NEW_COLOR, 위)
#   주황  새로 생긴 실행 경로. 고른 것은 짙게 · 빠진 것은 옅게
#
# 새 실행 경로. 대비 7.09 로 강조 teal(7.59)과 거의 같은 무게다 — 둘 다
# 하단의 실행 경로이고 장면이 달라 한 화면에서 경쟁하지 않는다.
# 대상(group) 노드의 금색(39°)과 색상이 가깝지만(29°) 그쪽은 타원 노드이고
# 이쪽은 선이라 도형부터 갈린다.
PATH_NEW = "#E8862A"
# 선택에서 빠진 경로. 같은 색상(32°)이라 "같은 종류인데 꺼진 것" 으로 읽힌다.
# 대비 3.49 — 짙은 주황(7.09)의 절반이라 확실히 물러나면서도 배경 실선(2.41)
# 보다는 위라 사라지지는 않는다. 옅어도 실행 경로다.
PATH_NEW_DIM = "#8A6234"

# /screen 응답에 실어 보낸다. UI 는 이것만 보고 칩 테두리 · 배지 · 안내 문구를 칠한다.
COLORS = {
    "highlight": HIGHLIGHT_COLOR,
    "dotted": DOTTED_COLOR,
    "plain": PLAIN_COLOR,
    "new": NEW_COLOR,
    "node_border": NODE_BORDER,
    "node_fill": NODE_FILL,
    "edge": EDGE_COLOR,
    "edge_top": EDGE_COLOR_TOP,
    "dotted_bottom": DOTTED_COLOR_BOTTOM,
    "dotted_top": DOTTED_COLOR_TOP,
    "node_border_top": NODE_BORDER_TOP,
    "group": GROUP_COLOR,
    "group_top": GROUP_COLOR_TOP,
    # 등록 장면의 실행 경로 둘. 예전에는 화면이 같은 값을 제 파일에 또 적고
    # 있었다 — 팔레트의 주인이 둘이면 조용히 어긋난다.
    "new_path": PATH_NEW,
    "new_path_dim": PATH_NEW_DIM,
}

# ------------------------------------------------------------ 크기
# 노드 글씨 · 노드 최소 크기(인치). 화면 글씨는 `fontsize x 맞춤배율` 이고
# 맞춤배율은 캔버스가 정하므로, 이 값은 layout_store.DRAW_SCALE 과 짝이다.
# **한쪽만 올리면 겹친다.** 고르는 근거와 21벌의 표는 NOTES.md 「쉰두째」.
# 겹침 0 은 dev/tests/app/ui/graph/test_nodes_do_not_overlap.py 가 지킨다.
# 두 줄 접기는 유지한다. 풀면 노드가 넓어지고 그 폭이 회전 후 높이가 되어
# 종횡비가 나빠진다 — 화면 글씨도 오히려 작아진다(실측).
# 채우기를 넣어 선이 노드를 통과해 비치지 않게 한다 — 크기에는 영향이 없다(실측).
# style 과 color 가 앞 기본값과 두 번 나오지만 Graphviz 는 나중 것을 쓴다(실측).
NODE_ATTRS = (
    "fontsize=21",
    'margin="0.14,0.07"',
    "width=1.3",
    "height=0.6",
    'style="rounded,filled"',
    f'fillcolor="{NODE_FILL}"',
    f'color="{NODE_BORDER}"',
)
# 점선 굵기. 예전에는 없어서 기본값 1 이었고 실선도 1 이라 굵기로 안 갈렸다.
# 밝기 · 굵기 둘을 함께 올려야 다크 배경에서 확실히 구분된다.
# 파선 간격은 못 바꾼다 — Graphviz 는 style=dashed 에 stroke-dasharray="5,2" 를
# 고정으로 내보내고 penwidth 를 올려도 그대로다(실측). 그래서 밝기와 굵기로만 간다.
DOTTED_PENWIDTH = 1.6
# 대상(group) 노드에 얹는 속성. 도형과 굵기로 기능 노드와 갈린다.
# ellipse 는 Graphviz 기본 도형이라 안전하고, 사각형과 확실히 구분된다.
GROUP_ATTRS = (
    "shape=ellipse",
    "penwidth=2",
    f'color="{GROUP_COLOR}"',
    f'fontcolor="{GROUP_COLOR}"',
)
# 엣지 길이(spring). 실선을 길게 둬 가로로 펴고, 점선을 짧게 둬 같은 특성끼리 모은다.
# 두 줄 접기로 노드가 작아지면 그래프가 정방형이 되는데, 실선을 늘리면 다시 펴진다
# (실측: len 2.2 에서 H/W 0.97, len 4.0 에서 0.65).
SOLID_LEN = 4.0
DOTTED_LEN = 0.7


def wrap_label(name: str) -> str:
    """긴 이름을 두 줄로 접음.

    입력  노드 이름
    출력  가운데에 가장 가까운 공백에서 자르고 DOT 개행(\\n)을 넣은 이름.
          공백이 없으면 그대로
    규칙  가로 폭이 줄면 겹칠 확률이 가장 크게 줆. 노드 폭 194 -> 87
    제약  글자 중간에서 자르지 않는다. 한글이 계속 읽혀야 함
    """
    if " " not in name:
        return name

    middle = len(name) / 2
    cut = min(
        (i for i, char in enumerate(name) if char == " "),
        key=lambda i: abs(i - middle),
    )
    # DOT 문자열 안에서 \n 은 줄바꿈이다. 파이썬 개행이 아니라 두 글자로 넣는다.
    return name[:cut] + "\\n" + name[cut + 1 :]


def wrap_node_labels(nodes: dict) -> dict:
    """노드 이름만 두 줄로 접은 사본. build_dot 은 안 건드림."""
    return {
        node_id: {**node, "name": wrap_label(node.get("name", node_id))}
        for node_id, node in nodes.items()
    }


def build_dot(
    nodes: dict,
    solid: dict,
    dotted: dict,
    *,
    positions=None,
    pin=True,
    spring=False,
    graph_attrs=(),
    dotted_labels=True,
    node_attrs=(),
    group_attrs=(),
) -> str:
    """온톨로지를 Graphviz 가 배치를 잴 DOT 문자열로.

    입력  nodes  {node_id: {"name": 표시명, ...}}
          solid  {(from, to): 인터페이스}. recipe 연결. 화살표 없음
                 인터페이스 값은 받되 그리지 않음 — 무엇이 흐르는지는 경로
                 안에 노드로 들어 있고, 라벨은 노드 상자를 밀어냄
          dotted  {(a, b): ["key: value", ...]}. 특성 관련. 점선, 화살표 없음
          positions  {node_id: (x, y)} neato 용 고정 좌표. pos="x,y!" 로 붙임.
                 label 뒤에 놓음. 테스트가 노드 줄을 '"id" [label=' 로 찾음
          pin  좌표에 느낌표를 붙일지. True 면 못박고 False 면 시작 위치로만
                 씀. 배치를 다시 계산하되 지금 자리에서 출발시키고 싶을 때
                 False (layout_store.spread 가 겹침만 다시 없앨 때 씀)
          spring  neato 용 엣지 길이. 실선보다 점선을 짧게 둬 같은 특성을
                 공유하는 노드끼리 서로 끌어당겨 모이게 함.
                 len 은 dot 엔진에서는 무시됨
          graph_attrs  graph [...] 에 더할 속성들. neato 는 inputscale=72 가
                 있어야 좌표 왕복이 항등이고(없으면 72배로 어긋남), 최초 배치에는
                 overlap 제거가 필요함
          dotted_labels  점선 라벨을 붙일 범위. True 면 전부, False 면 없음,
                 쌍의 집합이면 그것만. 끄면 노드 사이 공간이 넓어짐.
                 레이아웃 자체는 안 바뀜(실측)
          node_attrs  node [...] 기본 줄에 더할 속성들. 폰트 · 여백을 줄여
                 박스를 작게 만드는 데 씀
          group_attrs  kind == "group" 인 노드에만 더할 속성들. 도형을 바꿔
                 기능 노드와 갈리게 함. 비워두면 group 도 기능과 똑같이 그려짐
    출력  DOT 문자열
    제약  새 인자를 위치 인자로 만들지 않는다.
          모두 키워드 전용이고 기본값에서는 출력이 한 글자도 달라지지 않음
          강조 · 등록 표시를 여기서 하지 않는다.
          2026-09-06 에 그 인자 열둘(highlight · highlight_nodes ·
          highlight_paths · draw_solid · dotted_penwidth · mark_nodes ·
          mark_edges · mark_dotted · dim_edges · mark_color · edge_color ·
          dotted_color)을 걷었음. 무엇을 짙게 하고 무엇을 물릴지는 화면
          라이브러리의 일이고 그 표는 build.network_payload 가 만듦.
          여기서 나온 DOT 은 좌표를 재는 데만 들어감
    이력  엣지 라벨을 되살릴 때는 label 이 아니라 xlabel 로 붙인다.
          label 은 Graphviz 가 공간을 확보해 노드가 밀림(실측)
    """
    if dotted_labels is True or dotted_labels is False:
        labelled_dotted = dotted_labels
    else:
        labelled_dotted = {frozenset(pair) for pair in dotted_labels}

    # rankdir 은 dot 엔진에서만 의미가 있다. neato 는 무시하므로 그대로 둔다.
    graph_line = f'  graph [fontname="{FONT}", bgcolor="transparent"'
    graph_line += "".join(f", {attr}" for attr in graph_attrs) + "];"

    node_line = (
        f'  node [shape=box, style=rounded, fontname="{FONT}", '
        f'color="{PLAIN_COLOR}", fontcolor="{PLAIN_COLOR}"'
    )
    node_line += "".join(f", {attr}" for attr in node_attrs) + "];"

    lines = [
        "digraph ontology {",
        "  rankdir=LR;",
        graph_line,
        node_line,
        f'  edge [fontname="{FONT}", fontsize=10, color="{PLAIN_COLOR}"];',
        "",
    ]

    # 노드는 모두 같은 중립색이다. 크기를 정하는 것은 라벨 · 글씨 · 여백이고
    # 색은 여기서 아무것도 안 바꾼다.
    for node_id, node in nodes.items():
        label = node.get("name", node_id)
        attrs = [f'label="{label}"']
        # pos 는 label 뒤에. 테스트가 노드 줄을 '"id" [label=' 로 찾는다.
        if positions and node_id in positions:
            x, y = positions[node_id]
            attrs.append(f'pos="{x},{y}{"!" if pin else ""}"')
        # 대상 노드는 도형부터 다르다 — 타원이라 상자 크기가 갈린다.
        if group_attrs and node.get("kind") == "group":
            attrs.extend(group_attrs)
        lines.append(f'  "{node_id}" [{", ".join(attrs)}];')

    lines.append("")

    # 레시피 연결 — 방향 없는 가는 실선. **평행 엣지를 추가하지 않는다** —
    # 엣지 수가 조합마다 달라지면 레이아웃이 흔들린다
    # (실측: height 256 -> 289 -> 293).
    solid_len = f", len={SOLID_LEN}" if spring else ""
    for frm, to in solid:
        lines.append(f'  "{frm}" -> "{to}" [dir=none{solid_len}];')

    # 특성 관련 — 방향 없는 점선.
    # constraint=false 는 쓰지 않는다. 랭크 제약이 없는 엣지가 늘면 배치가
    # 흔들린다.
    # 점선을 실선보다 짧게 둔다(len). 같은 특성을 공유하는 노드끼리 서로
    # 끌어당겨 자연스럽게 모인다 — 열로 강제 정렬하는 것보다 잘 읽힌다.
    dotted_len = f", len={DOTTED_LEN}" if spring else ""
    for (a, b), labels in dotted.items():
        pair = frozenset((a, b))
        attrs = (
            f'dir=none, style=dashed, color="{DOTTED_COLOR}", '
            f"penwidth={DOTTED_PENWIDTH}"
        )

        if labelled_dotted is True:
            show_label = True
        elif labelled_dotted is False:
            show_label = False
        else:
            show_label = pair in labelled_dotted

        if show_label:
            # 라벨을 끄면 fontcolor 도 뺀다 — 칠할 글자가 없다.
            attrs += f', fontcolor="{DOTTED_COLOR}", label="{chr(10).join(labels)}"'
        lines.append(f'  "{a}" -> "{b}" [{attrs}{dotted_len}];')

    lines.append("}")
    return "\n".join(lines)
