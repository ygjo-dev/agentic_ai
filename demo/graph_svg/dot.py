"""온톨로지 → DOT 문자열. 색 · 굵기 · 길이의 단일 출처.

여기서 정한 색을 /graph 응답의 colors 로 UI 에 내려보낸다. UI 가 자기 팔레트를
따로 들면 두 곳이 조용히 어긋나고, 그때 사람은 화면을 보고 코드를 의심한다.

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
#   분홍  새 노드 테두리  (NEW_COLOR, 위)
#   보라  새로 생긴 관계(점선)
#   주황  새로 생긴 실행 경로. 고른 것은 짙게 · 빠진 것은 옅게
#
# 새 점선은 보라 계열을 유지한다(249° — 하단 점선 244° · 상단 점선 245°).
# 관계는 점선이 말하는 것이라 같은 계열이어야 "같은 종류의 선" 으로 읽히고,
# 새 것과 헌 것은 밝기와 굵기로만 가른다. 대비 8.51 로 하단 점선(5.91)의
# 1.44배다. 강조 teal(7.59)보다 위인데 위계가 뒤집힌 것은 아니다 —
# **등록 장면에는 teal 이 아예 없다**(해석 결과와 한 화면에 뜨지 않는다).
NEW_DOTTED_COLOR = "#B0A2FF"
# 새 실행 경로. 대비 7.09 로 강조 teal(7.59)과 거의 같은 무게다 — 둘 다
# 하단의 실행 경로이고 장면이 달라 한 화면에서 경쟁하지 않는다.
# 대상(group) 노드의 금색(39°)과 색상이 가깝지만(29°) 그쪽은 타원 노드이고
# 이쪽은 선이라 도형부터 갈린다.
PATH_NEW = "#E8862A"
# 선택에서 빠진 경로. 같은 색상(32°)이라 "같은 종류인데 꺼진 것" 으로 읽힌다.
# 대비 3.49 — 짙은 주황(7.09)의 절반이라 확실히 물러나면서도 배경 실선(2.41)
# 보다는 위라 사라지지는 않는다. 옅어도 실행 경로다.
PATH_NEW_DIM = "#8A6234"

# /graph 응답에 실어 보낸다. UI 는 이것만 보고 칩 테두리 · 배지 · 안내 문구를 칠한다.
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
}

# ------------------------------------------------------------ 크기
# 노드 글씨 크기. model=subset 이 노드를 넓게 벌려서 겹침은 더 이상 제약이 아니다 —
# fontsize 18 · 한 줄까지 올려도 겹침 0쌍이었다. 실제 제약은 종횡비다.
# 화면에 보이는 글씨(= fontsize × 축소배율)로 재보면 11 → 7.3pt, 16 → 10.1pt 이고
# 종횡비는 0.72 → 0.75, 폭 사용은 55% → 53% 로 2%p 만 손해다. 그래서 16 을 쓴다.
# 두 줄 접기는 유지한다. 풀면 노드가 150~245pt 로 넓어지고 그 폭이 회전 후 높이가
# 되어 종횡비가 0.78 로 나빠진다 — 화면 글씨도 오히려 작아진다(실측).
# 채우기를 넣어 선이 노드를 통과해 비치지 않게 한다 — 크기에는 영향이 없다(실측).
# style 과 color 가 앞 기본값과 두 번 나오지만 Graphviz 는 나중 것을 쓴다(실측).
NODE_ATTRS = (
    "fontsize=16",
    'margin="0.14,0.07"',
    'style="rounded,filled"',
    f'fillcolor="{NODE_FILL}"',
    f'color="{NODE_BORDER}"',
)
# 상단은 배경 지도라 노드도 한 단계 낮춘다.
NODE_ATTRS_TOP = NODE_ATTRS[:-1] + (f'color="{NODE_BORDER_TOP}"',)

# 점선 굵기. 예전에는 없어서 기본값 1 이었고 실선도 1 이라 굵기로 안 갈렸다.
# 밝기 · 굵기 둘을 함께 올려야 다크 배경에서 확실히 구분된다.
# 파선 간격은 못 바꾼다 — Graphviz 는 style=dashed 에 stroke-dasharray="5,2" 를
# 고정으로 내보내고 penwidth 를 올려도 그대로다(실측). 그래서 밝기와 굵기로만 간다.
DOTTED_PENWIDTH = 1.6
# 상단은 실선이 아예 없다. 점선이 유일한 선이므로 배경 지도가 아니라 주인공이고,
# 다른 선과 경쟁할 일도 없어 마음껏 굵게 둘 수 있다. 하단(1.6)과 따로 두는 이유 :
# 하단에는 강조 실행 경로(penwidth=3)가 있어 점선이 그보다 굵으면 위계가 뒤집힌다.
# **화면을 보고 조절할 값이다. 여기 하나만 고치면 상단 점선 굵기가 전부 바뀐다.**
DOTTED_PENWIDTH_TOP = 4.5

# 대상(group) 노드에 얹는 속성. 도형과 굵기로 기능 노드와 갈린다.
# ellipse 는 Graphviz 기본 도형이라 안전하고, 사각형과 확실히 구분된다.
GROUP_ATTRS = (
    "shape=ellipse",
    "penwidth=2",
    f'color="{GROUP_COLOR}"',
    f'fontcolor="{GROUP_COLOR}"',
)
GROUP_ATTRS_TOP = (
    "shape=ellipse",
    "penwidth=2",
    f'color="{GROUP_COLOR_TOP}"',
    f'fontcolor="{GROUP_COLOR_TOP}"',
)

# 실행 경로 굵기. 배경 실선(속성 없음 = 1)보다 확실히 굵어야 "이 길이 켜졌다"
# 가 읽힌다. 강조와 등록이 **같은 굵기**인 이유 : 하단에서는 둘 다 실행 경로다.
# 무엇이 다른지는 색이 말한다(teal 해석 결과 · 분홍 새로 등록된 경로).
PATH_PENWIDTH = 3

# 실행 경로 화살표. 배경 실선은 방향이 없고(dir=none) 강조된 것만 방향을 보여준다 —
# 하단은 "무엇 다음에 무엇이 오는가" 를 말하는 자리다. **평행 엣지를 추가하지
# 않는다** — 이미 있는 엣지의 속성만 바꾼다(검증된 제약: 엣지 수가 조합마다
# 달라지면 레이아웃이 흔들린다).
# 기본 화살표는 1639pt 캔버스를 화면 폭에 맞춰 줄이면 점처럼 보인다.
# **화면을 보고 조절할 값이다 — 여기 하나만 고치면 된다.**
PATH_ARROWSIZE = 1.6

# 순번 글씨 크기. 엣지 기본(fontsize=10)은 축소 후 안 읽힌다.
# xlabel 은 레이아웃에 관여하지 않으므로(label 과 달리) 키워도 노드가 안 밀린다.
# 다만 캔버스는 커질 수 있다 — 글자가 그림 밖으로 나가면 bbox 가 따라 넓어진다.
# **화면을 보고 조절할 값이다 — 여기 하나만 고치면 된다.**
ORDER_FONTSIZE = 26

# 등록 강조 굵기. 주인공은 "노드가 어디에 붙었나" 이고 recipe 개수는 스탯이 말한다.
MARK_NODE_PENWIDTH = 2
# 새 관계(점선) 굵기. 2.5 에서 올렸다 — 새 점선(#B0A2FF, 대비 8.51)과 하단의
# 평범한 점선(#8B84E8, 5.91)은 같은 보라 계열이라 색상만으로는 잘 안 갈린다.
# 밝기 1.44배에 굵기 2.5배를 더해 갈리게 한다 (기본 점선 1.6 기준).
MARK_DOTTED_PENWIDTH = 4.0
# 예전에는 둘 다 1.5 였다 — 상단 지도 위의 조연이라 얇게 둔 값이다. 상단이
# 실선을 안 그리게 되면서 이 둘은 하단 전용이 됐고, 하단에서는 조연이 아니라
# 실행 경로 자체다. 배경 실선(1)과 갈리지 않으면 등록해도 화면이 안 변한다.
MARK_SOLID_PENWIDTH = PATH_PENWIDTH
# 표시된 점선은 평소 굵기의 이 배수다. 절댓값 하나로 박아두면 상단(4.5)에서
# **새로 생긴 점선이 평범한 점선보다 가늘어진다** — 등록 장면의 주인공이
# 배경보다 옅어지는 셈이라 배수로 둔다. 기본 점선에서는 예전 값과 같다.
MARK_DOTTED_RATIO = MARK_DOTTED_PENWIDTH / DOTTED_PENWIDTH

# 엣지 길이(spring). 실선을 길게 둬 가로로 펴고, 점선을 짧게 둬 같은 특성끼리 모은다.
# 두 줄 접기로 노드가 작아지면 그래프가 정방형이 되는데, 실선을 늘리면 다시 펴진다
# (실측: len 2.2 에서 H/W 0.97, len 4.0 에서 0.65).
SOLID_LEN = 4.0
DOTTED_LEN = 0.7


def build_dot(
    nodes: dict,
    solid: dict,
    dotted: dict,
    highlight=None,
    highlight_nodes=None,
    highlight_paths=None,
    *,
    positions=None,
    spring=False,
    graph_attrs=(),
    dotted_labels=True,
    draw_solid=True,
    dotted_penwidth=None,
    node_attrs=(),
    group_attrs=(),
    mark_nodes=(),
    mark_edges=(),
    mark_dotted=(),
    dim_edges=(),
    mark_color=None,
    edge_color=None,
    dotted_color=None,
) -> str:
    """계산 결과를 Graphviz DOT 문자열로 옮긴다.

    Args:
        nodes: {node_id: {"name": 표시명, ...}}
        solid: {(from, to): 인터페이스} — 레시피 연결. 화살표 없음.
            인터페이스 값은 받되 그리지 않는다. 열 위치만 봐도 무엇이
            흐르는지 읽히고, 같은 이름이 16번 반복되면 노이즈다.
        dotted: {(a, b): ["key: value", ...]} — 특성 관련. 점선, 화살표 없음.
        highlight: [(from, to), ...] — 경로 하나. 굵은 실선, 화살표, 순번.
            리스트 순서가 곧 실행 순서다.
        highlight_nodes: 테두리를 강조할 노드. 생략하면 강조 엣지의 양 끝에서
            유도한다. 1단 recipe 는 엣지가 없어 유도가 불가능하므로 그때는
            호출하는 쪽이 넘겨야 한다.
        highlight_paths: [[(from, to), ...], ...] — 경로 여러 개(CLARIFY 후보).
            엣지 합집합을 강조하고 순번은 붙이지 않는다. 여러 경로가 같은
            엣지를 공유하면 순번이 겹쳐 읽을 수 없기 때문이다.
            경로가 정확히 하나면 highlight 와 똑같이 순번을 붙인다.
        positions: {node_id: (x, y)} — neato 용 고정 좌표. pos="x,y!" 로 붙인다.
            label 뒤에 놓는다 — 테스트가 노드 줄을 '"id" [label=' 로 찾는다.
        spring: neato 용 엣지 길이. 실선보다 점선을 짧게 둬 같은 특성을 공유하는
            노드끼리 서로 끌어당겨 모이게 한다. len 은 dot 엔진에서는 무시된다.
        graph_attrs: graph [...] 에 더할 속성들. neato 는 inputscale=72 가
            있어야 좌표 왕복이 항등이고(없으면 72배로 어긋난다), 최초 배치에는
            overlap 제거가 필요하다.
        dotted_labels: 점선 라벨을 붙일 범위. True 면 전부, False 면 없음,
            쌍의 집합이면 그것만. 끄면 화면이 깨끗해지고 노드 사이 공간이
            넓어진다. 레이아웃 자체는 바뀌지 않는다(실측).
        draw_solid: 실선(recipe 파생)을 그릴지. False 면 실선 문장을 아예 넣지
            않는다 — 상단이 "무엇이 무엇과 관련되는가"(점선)만 말하는 관계
            지도가 되고, "무엇 다음에 무엇이 오는가"(실선)는 하단이 맡는다.
            **좌표는 안 바뀐다** — 전 노드가 핀이고 neato -n 이라 선을 빼도
            배치를 다시 계산하지 않는다(테스트로 고정).
        dotted_penwidth: 점선 굵기. 생략하면 DOTTED_PENWIDTH. 상단은 실선이
            없어 점선이 유일한 선이므로 더 굵게 둔다(DOTTED_PENWIDTH_TOP).
        node_attrs: node [...] 기본 줄에 더할 속성들. 폰트·여백을 줄여 박스를
            작게 만드는 데 쓴다.
        group_attrs: kind == "group" 인 노드에만 더할 속성들. 도형과 색을 바꿔
            기능 노드와 갈리게 한다. 비워두면 group 도 기능과 똑같이 그려진다 —
            기본 출력을 바꾸지 않으려는 것이다.
            강조·마크 색은 이 뒤에 붙으므로 걸리면 그쪽이 이긴다(Graphviz 는
            같은 속성이 두 번 나오면 나중 것을 쓴다 — 실측).
        mark_nodes / mark_edges / mark_dotted: 새로 생긴 것을 표시한다.
            highlight(실행 경로) 와는 직교하는 별개의 레이어다 — 등록 강조는
            "무엇을 고른 경로인지" 가 아니라 "무엇이 새로 생겼는지" 라서
            같은 색 조합 규칙에 넣으면 읽는 사람이 헷갈린다.
            둘 다 걸린 대상은 mark 가 이긴다.
            **셋이 서로 다른 색이다.** 하나가 뜻 하나이기 때문이다.
                mark_nodes   NEW_COLOR         (mark_color 로 덮을 수 있다)
                mark_dotted  NEW_DOTTED_COLOR  (상수)
                mark_edges   PATH_NEW          (상수)
            뒤의 둘을 상수로 고정하는 이유 : 이 인자들은 등록 장면에서만 쓰인다.
            해석 장면은 highlight_paths 를 쓴다.
        dim_edges: [(from, to), ...] — 선택에서 빠진 실행 경로. PATH_NEW_DIM 으로
            칠하고 굵기와 화살표는 짙은 경로와 같다(옅어도 실행 경로다).
            순번은 안 붙인다.
            **색 우선순위는 mark > highlight > dim 이다.** dim 이 가장 낮은
            이유 : 경로들이 앞 구간을 공유하므로, 같은 엣지가 짙은 경로에도
            걸려 있으면 짙은 쪽이 이겨야 앞 구간이 끊겨 보이지 않는다.
            실선이 없는 쌍은 조용히 건너뛴다 — 여기서 선을 새로 긋지 않는다.
        mark_color: mark_nodes 에 쓸 색. 생략하면 NEW_COLOR.
        edge_color: 실선 색. 생략하면 PLAIN_COLOR — 노드 테두리와 같은 값이라
            엣지만 옅게 할 수가 없었다. 분리해두면 선을 뒤로 물릴 수 있다.
        dotted_color: 점선 색. 생략하면 DOTTED_COLOR. 실선만 어둡게 하면
            밝은 점선이 화면에서 가장 튀어 위계가 뒤집히므로 함께 조절한다.

    mark_edges 와 dim_edges 에는 순번(xlabel)을 붙이지 않는다. 등록 장면은
    highlight_paths 를 쓰지 않으므로 순번 규칙(경로가 정확히 하나일 때)에
    아예 걸리지 않는다.

    새 인자는 모두 키워드 전용이고 기본값에서는 출력이 한 글자도 달라지지 않는다.
    tests/graph_rendering 의 40여 개가 기존 출력 문자열에 의존한다.

    레이아웃은 어떤 조합에서도 같다. 강조는 엣지를 새로 추가하지 않고 이미
    있는 실선의 색·굵기만 바꾸며, 순번은 label 이 아니라 xlabel 로 붙인다.
    (label 은 Graphviz 가 공간을 확보해 노드가 밀린다 — 실측으로 확인했다.)
    """
    if highlight_paths is None:
        paths = [highlight] if highlight else []
    else:
        paths = [path for path in highlight_paths if path]

    highlighted = {edge for path in paths for edge in path}

    # 경로가 하나로 확정됐을 때만 순번. 같은 엣지를 두 번 지나면 번호를 이어 붙인다.
    orders: dict[tuple[str, str], str] = {}
    if len(paths) == 1:
        seen: dict[tuple[str, str], list[int]] = {}
        for order, edge in enumerate(paths[0], start=1):
            seen.setdefault(edge, []).append(order)
        orders = {edge: ", ".join(str(n) for n in nums) for edge, nums in seen.items()}

    if highlight_nodes is None:
        highlight_nodes = {node_id for path in paths for edge in path for node_id in edge}
    highlight_nodes = set(highlight_nodes)

    marked_nodes = set(mark_nodes)
    marked_edges = {tuple(edge) for edge in mark_edges}
    # 점선은 방향이 없다. 어느 순서로 받아도 같은 쌍으로 본다.
    marked_dotted = {frozenset(pair) for pair in mark_dotted}
    dimmed_edges = {tuple(edge) for edge in dim_edges}
    marked_color = mark_color or NEW_COLOR
    line_color = edge_color or PLAIN_COLOR
    dash_color = dotted_color or DOTTED_COLOR
    dash_width = DOTTED_PENWIDTH if dotted_penwidth is None else dotted_penwidth

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
        f'  edge [fontname="{FONT}", fontsize=10, color="{line_color}"];',
        "",
    ]

    # 노드는 모두 같은 중립색이다. 종류별로 색을 나누면 하이라이트가 묻힌다.
    # 색만 바꾸고 굵기는 건드리지 않는다 — 굵기는 레이아웃에 영향을 줄 수 있다.
    for node_id, node in nodes.items():
        label = node.get("name", node_id)
        attrs = [f'label="{label}"']
        # pos 는 label 뒤에. 테스트가 노드 줄을 '"id" [label=' 로 찾는다.
        if positions and node_id in positions:
            x, y = positions[node_id]
            attrs.append(f'pos="{x},{y}!"')
        # mark 가 걸리면 그것이 이긴다 — 새로 생긴 것이 가장 먼저 눈에 띄어야 한다.
        # 대상 노드는 도형부터 다르다. 실행할 수 있는 것과 개념은 다른 것이다.
        if group_attrs and node.get("kind") == "group":
            attrs.extend(group_attrs)

        marked = node_id in marked_nodes
        color = marked_color if marked else (
            HIGHLIGHT_COLOR if node_id in highlight_nodes else ""
        )
        if color:
            width = MARK_NODE_PENWIDTH if marked else 2
            attrs.append(f'penwidth={width}, color="{color}"')
        lines.append(f'  "{node_id}" [{", ".join(attrs)}];')

    lines.append("")

    # 레시피 연결 — 기본은 방향 없는 가는 실선.
    # 강조는 이 엣지의 색·굵기만 바꾼다. 평행 엣지를 따로 추가하면 엣지 수가
    # 조합마다 달라져 레이아웃이 흔들린다 (실측: height 256 -> 289 -> 293).
    solid_len = f", len={SOLID_LEN}" if spring else ""
    for frm, to in solid if draw_solid else ():
        edge = (frm, to)
        is_marked = edge in marked_edges
        # mark > highlight > dim. 새로 생긴 것이 고른 경로보다 먼저 보이고,
        # 물러난 경로가 가장 낮다 — 경로들이 앞 구간을 공유하므로 그 구간은
        # 짙은 쪽이 이겨야 길이 끊겨 보이지 않는다.
        if is_marked:
            color = PATH_NEW
        elif edge in highlighted:
            color = HIGHLIGHT_COLOR
        elif edge in dimmed_edges:
            color = PATH_NEW_DIM
        else:
            color = ""
        if not color:
            lines.append(f'  "{frm}" -> "{to}" [dir=none{solid_len}];')
            continue

        width = MARK_SOLID_PENWIDTH if is_marked else PATH_PENWIDTH
        # 켜진 길에만 화살표. 배경 실선은 dir=none 그대로다 — 방향이 보이는 것이
        # 곧 "이것이 실행 경로다" 라는 표시이므로 아무 데나 붙이면 뜻이 없어진다.
        attrs = (
            f'dir=forward, arrowsize={PATH_ARROWSIZE}, '
            f'penwidth={width}, color="{color}"'
        )
        # 표시된 엣지에는 순번을 붙이지 않는다 — 실행 순서가 아니라 새로 생긴 것이다.
        if edge in orders and not is_marked:
            # xlabel 은 레이아웃에 관여하지 않는다. label 을 쓰면 노드가 밀린다.
            attrs += (
                f', xlabel="{orders[edge]}", fontcolor="{HIGHLIGHT_COLOR}"'
                f", fontsize={ORDER_FONTSIZE}"
            )
        lines.append(f'  "{frm}" -> "{to}" [{attrs}{solid_len}];')

    # 특성 관련 — 방향 없는 점선.
    # constraint=false 는 쓰지 않는다. 랭크 제약이 없는 엣지가 늘면
    # 브라우저 WASM Graphviz(st.graphviz_chart 가 쓰는 렌더러)는 레이아웃을
    # 끝내지 못해 화면이 계속 비어있는다. 네이티브 dot 은 즉시 끝내므로
    # 로컬 `dot -Tsvg` 검증만으로는 이 문제가 잡히지 않는다.
    # 점선을 실선보다 짧게 둔다(len). 같은 특성을 공유하는 노드끼리 서로
    # 끌어당겨 자연스럽게 모인다 — 열로 강제 정렬하는 것보다 잘 읽힌다.
    dotted_len = f", len={DOTTED_LEN}" if spring else ""
    for (a, b), labels in dotted.items():
        pair = frozenset((a, b))
        is_marked = pair in marked_dotted
        # dir=none 과 style=dashed 는 표시해도 그대로 둔다 — 테스트가 실선과
        # 점선을 이 두 속성으로 가른다.
        color = NEW_DOTTED_COLOR if is_marked else dash_color
        width = round(dash_width * MARK_DOTTED_RATIO, 2) if is_marked else dash_width
        attrs = f'dir=none, style=dashed, color="{color}", penwidth={width}'

        if labelled_dotted is True:
            show_label = True
        elif labelled_dotted is False:
            show_label = False
        else:
            show_label = pair in labelled_dotted

        if show_label:
            # 라벨을 끄면 fontcolor 도 뺀다 — 칠할 글자가 없다.
            attrs += f', fontcolor="{color}", label="{chr(10).join(labels)}"'
        lines.append(f'  "{a}" -> "{b}" [{attrs}{dotted_len}];')

    lines.append("}")
    return "\n".join(lines)
