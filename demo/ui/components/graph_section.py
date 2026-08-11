"""온톨로지 그래프 표시 컴포넌트.

그리는 방법만 안다. 무엇을 그릴지(엣지 계산)는 백엔드가 하고, 여기는
GET /graph 응답을 받아 build_dot 이 받는 형태로 되돌려 그린다.

SVG 는 서버에서 네이티브 dot 으로 미리 만들어 보낸다. st.graphviz_chart 는
DOT 을 브라우저로 보내 WASM Graphviz 가 그리는데, 그쪽은 네이티브 dot 이
즉시 끝내는 그래프에서도 레이아웃을 끝내지 못하고 조용히 멈추는 경우가 있다.
서버에서 완성해 보내면 브라우저는 표시만 하므로 그 문제가 생기지 않는다.
"""

import hashlib
import json
import re
import shutil
import subprocess

import streamlit as st

from demo.ui import config, focus, layout_store, styles
from demo.ui.components import zoom


class GraphvizNotFound(RuntimeError):
    """dot 실행 파일을 찾지 못했다."""


class GraphvizFailed(RuntimeError):
    """dot 이 DOT 을 거부했다. 대개 문법 오류다."""

# 한글 노드 라벨이 깨지지 않도록 지정. Windows 기본 한글 폰트.
FONT = "Malgun Gothic"

# 색은 demo/ui/config.py 가 정한다. 여기서 다시 내보내는 것은
# tests/graph_rendering 이 이 모듈에서 import 하고 있어서다.
HIGHLIGHT_COLOR = config.HIGHLIGHT_COLOR
DOTTED_COLOR = config.DOTTED_COLOR
PLAIN_COLOR = config.PLAIN_COLOR
NEW_COLOR = config.NEW_COLOR

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
    f'fillcolor="{config.NODE_FILL}"',
    f'color="{config.NODE_BORDER}"',
)
# 상단은 배경 지도라 노드도 한 단계 낮춘다.
NODE_ATTRS_TOP = NODE_ATTRS[:-1] + (f'color="{config.NODE_BORDER_TOP}"',)

# 등록 강조 굵기. 주인공은 "노드가 어디에 붙었나" 이고 recipe 개수는 스탯이 말한다.
MARK_NODE_PENWIDTH = 2
MARK_DOTTED_PENWIDTH = 2.5  # 관계를 더 또렷하게
MARK_SOLID_PENWIDTH = 1.5  # 새 recipe 는 조연으로

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
    node_attrs=(),
    mark_nodes=(),
    mark_edges=(),
    mark_dotted=(),
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
        node_attrs: node [...] 기본 줄에 더할 속성들. 폰트·여백을 줄여 박스를
            작게 만드는 데 쓴다.
        mark_nodes / mark_edges / mark_dotted: 새로 생긴 것을 표시한다.
            highlight(실행 경로) 와는 직교하는 별개의 레이어다 — 등록 강조는
            "무엇을 고른 경로인지" 가 아니라 "무엇이 새로 생겼는지" 라서
            같은 색 조합 규칙에 넣으면 읽는 사람이 헷갈린다.
            둘 다 걸린 대상은 mark 가 이긴다.
        mark_color: mark 에 쓸 색. 생략하면 NEW_COLOR.
        edge_color: 실선 색. 생략하면 PLAIN_COLOR — 노드 테두리와 같은 값이라
            엣지만 옅게 할 수가 없었다. 분리해두면 선을 뒤로 물릴 수 있다.
        dotted_color: 점선 색. 생략하면 DOTTED_COLOR. 실선만 어둡게 하면
            밝은 점선이 화면에서 가장 튀어 위계가 뒤집히므로 함께 조절한다.

    mark_edges 에는 순번(xlabel)을 붙이지 않는다. 실행 순서가 아니라
    새로 생겼다는 표시일 뿐이다.

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
    marked_color = mark_color or NEW_COLOR
    line_color = edge_color or PLAIN_COLOR
    dash_color = dotted_color or DOTTED_COLOR

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
    for frm, to in solid:
        edge = (frm, to)
        is_marked = edge in marked_edges
        color = marked_color if is_marked else (
            HIGHLIGHT_COLOR if edge in highlighted else ""
        )
        if not color:
            lines.append(f'  "{frm}" -> "{to}" [dir=none{solid_len}];')
            continue

        # 등록으로 생긴 실선은 얇게 — 등록 장면의 주인공은 노드가 어디에 붙었냐다.
        width = MARK_SOLID_PENWIDTH if is_marked else 3
        attrs = f'penwidth={width}, color="{color}"'
        # 표시된 엣지에는 순번을 붙이지 않는다 — 실행 순서가 아니라 새로 생긴 것이다.
        if edge in orders and not is_marked:
            # xlabel 은 레이아웃에 관여하지 않는다. label 을 쓰면 노드가 밀린다.
            attrs += f', xlabel="{orders[edge]}", fontcolor="{HIGHLIGHT_COLOR}"'
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
        color = marked_color if is_marked else dash_color
        attrs = f'dir=none, style=dashed, color="{color}"'
        if is_marked:
            attrs += f", penwidth={MARK_DOTTED_PENWIDTH}"

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


def _run_graphviz(dot: str, engine: str, args: list[str]) -> str:
    """Graphviz 를 한 번 돌린다. 실행 파일 확인과 오류 변환을 한곳에 모은다.

    Raises:
        GraphvizNotFound: 실행 파일이 없다.
        GraphvizFailed: DOT 을 거부했거나 시간 안에 끝내지 못했다.
    """
    if shutil.which(engine) is None:
        raise GraphvizNotFound(
            f"Graphviz 의 {engine} 실행 파일을 찾을 수 없다.\n"
            "  설치 : https://graphviz.org/download/\n"
            f"  설치 후 {engine} 이 PATH 에 있어야 한다 ({engine} -V 로 확인)."
        )

    try:
        result = subprocess.run(
            [engine, *args],
            input=dot,
            capture_output=True,
            text=True,
            encoding="utf-8",  # 한글 노드 라벨이 있다.
            timeout=30,
        )
    except OSError as exc:  # 실행 자체가 실패
        raise GraphvizNotFound(f"{engine} 을 실행할 수 없다: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GraphvizFailed(f"{engine} 이 30초 안에 끝나지 않았다.") from exc

    if result.returncode != 0:
        raise GraphvizFailed(
            f"{engine} 이 DOT 을 거부했다 (exit {result.returncode}).\n{result.stderr.strip()}"
        )

    return result.stdout


def render_svg(dot: str, engine: str = "dot", *, no_layout: bool = False) -> str:
    """DOT 을 SVG 문자열로 변환한다.

    Args:
        engine: 기본값 dot 을 유지한다 — 기존 호출부가 전부 인자 하나로 부른다.
        no_layout: -n 을 붙인다. 모든 노드에 pos 가 있을 때 배치를 다시 계산하지
            않고 준 좌표를 그대로 쓴다. 하이라이트가 어떻게 바뀌어도 좌표가
            같다는 것이 이것으로 구조적으로 보장된다.

    Raises:
        GraphvizNotFound: 실행 파일이 없다.
        GraphvizFailed: DOT 을 거부했다 (문법 오류 등).
    """
    args = ["-Tsvg"] + (["-n"] if no_layout else [])
    return _run_graphviz(dot, engine, args)


# 엣지에도 pos(스플라인)가 붙는다. 노드만 골라내려면 엣지 문장을 먼저 지운다.
_EDGE_STATEMENT = re.compile(r'"?[\w]+"?\s*->\s*"?[\w]+"?\s*\[[^\]]*\];')
_NODE_STATEMENT = re.compile(r'"?([A-Za-z_]\w*)"?\s*\[([^\]]*)\]\s*;')
_POS_ATTR = re.compile(r'pos="([-\d.e+]+),([-\d.e+]+)')


def layout_positions(dot: str) -> dict[str, tuple[float, float]]:
    """neato 로 배치를 계산해 노드 좌표를 뽑는다. {node_id: (x, y)}.

    -Tdot 을 쓴다. -Tplain 도 좌표를 주지만 단위가 인치라 포인트인 pos 와
    72배 어긋난다 — 그대로 되돌려 넣으면 배치가 폭발한다.
    """
    out = _run_graphviz(dot, "neato", ["-Tdot"])

    flat = _EDGE_STATEMENT.sub(" ", re.sub(r"\s+", " ", out))

    positions = {}
    for match in _NODE_STATEMENT.finditer(flat):
        pos = _POS_ATTR.search(match.group(2))
        if pos:
            positions[match.group(1)] = (float(pos.group(1)), float(pos.group(2)))
    return positions


# <svg ...> 여는 태그 하나. 속성 순서는 Graphviz 가 정한다.
_SVG_OPEN_TAG = re.compile(r"<svg\b[^>]*>", re.S)
_SVG_SIZE_ATTR = re.compile(r'\s(?:width|height)="[^"]*"')
_SVG_PRESERVE_ATTR = re.compile(r'\spreserveAspectRatio="[^"]*"')


def fit_svg(svg: str) -> str:
    """SVG 가 담긴 상자를 꽉 채우도록 크기 속성을 정리한다.

    Graphviz 는 <svg width="591pt" height="336pt" viewBox="..."> 를 낸다.
    width/height 가 박혀 있으면 고정 높이 패널 안에서 위아래 여백이 뜨거나
    잘린다. 두 속성을 빼고 viewBox 만 남기면 CSS 가 크기를 온전히 정한다.

    preserveAspectRatio 로 비율은 유지한다 — 찌그러지면 안 읽힌다.
    viewBox 가 없으면(있을 리 없지만) 손대지 않는다. 크기 정보가 그것뿐이라
    지우면 아무것도 안 보이게 된다.
    """
    match = _SVG_OPEN_TAG.search(svg)
    if not match or "viewBox" not in match.group(0):
        return svg

    tag = _SVG_SIZE_ATTR.sub("", match.group(0))
    tag = _SVG_PRESERVE_ATTR.sub("", tag)
    tag = tag[:-1].rstrip() + ' preserveAspectRatio="xMidYMid meet">'

    return svg[: match.start()] + tag + svg[match.end() :]


# 노드 하나의 <g> 블록. 안에 중첩 <g> 가 없음을 실측으로 확인했으므로
# 비탐욕 매칭이 안전하다.
_SVG_NODE_GROUP = re.compile(r'<g id="node\d+" class="node">.*?</g>\n?', re.S)
_SVG_GRAPH_CLOSE = re.compile(r"</g>\s*</svg>\s*$", re.S)


def stack_nodes_on_top(svg: str) -> str:
    """노드를 엣지 뒤로 옮겨 선이 노드를 가리지 않게 한다.

    SVG 는 문서에 나온 순서대로 그리므로 뒤에 오는 것이 위에 얹힌다.
    Graphviz 는 노드와 엣지를 섞어서 내는데(실측: 마지막 노드 뒤에 엣지 9개),
    그 엣지들이 노드 위를 지나간다. 노드를 전부 맨 뒤로 보내면 정리된다.

    build_dot 을 건드리지 않는 후처리라 기존 테스트가 안전하다.
    좌표는 손대지 않으므로 배치도 그대로다.
    """
    groups = _SVG_NODE_GROUP.findall(svg)
    if not groups:
        return svg

    body = _SVG_NODE_GROUP.sub("", svg)

    # 그래프 그룹을 닫기 직전에 다시 붙인다.
    match = _SVG_GRAPH_CLOSE.search(body)
    if not match:
        return svg

    return body[: match.start()] + "".join(groups) + body[match.start() :]


# 새로 생긴 것이 잠깐 두근거린다. 짧게 두 번만 — 계속 깜빡이면 시선을 뺏는다.
_PULSE_CSS = """
@keyframes markpulse {
  0%   { opacity: 1; }
  50%  { opacity: 0.35; }
  100% { opacity: 1; }
}
g.node [stroke="MARK"], g.edge [stroke="MARK"] {
  animation: markpulse 0.6s ease-in-out 2;
}
"""


def graph_fill_html(svg: str, pulse: bool = False) -> str:
    """고정 높이 패널을 꽉 채우는 iframe 문서.

    iframe 배경은 기본 흰색이라 다크 테마에서 흰 카드로 뜬다. DOT 의
    bgcolor="transparent" 는 SVG 안쪽만 투명하게 하므로 여기서 한 번 더 덮는다.
    SVG 는 비율을 유지한 채 상자에 맞춘다(크기 속성은 fit_svg 가 뺀다).

    pulse 는 방금 등록된 것에만 준다. CSS 애니메이션이라 JS 가 없다.
    """
    extra = _PULSE_CSS.replace("MARK", NEW_COLOR.lower()) if pulse else ""

    return (
        "<style>"
        "html, body { background: transparent; margin: 0; padding: 0;"
        " height: 100%; overflow: hidden; }"
        "#graph { width: 100%; height: 100%; overflow: hidden; }"
        "svg { width: 100%; height: 100%; display: block; }"
        f"{zoom.ZOOM_CSS}"
        f"{extra}"
        "</style>"
        f'<div id="graph">{fit_svg(svg)}</div>'
        f"{zoom.zoom_script(zoom.TOP_KEY)}"
    )


def to_build_dot_args(payload: dict) -> tuple[dict, dict, dict]:
    """API 응답을 build_dot 이 받는 형태로 되돌린다.

    build_dot 의 기존 인자는 바꾸지 않는다 — tests/graph_rendering 이 의존한다.
    JSON 은 튜플 키를 못 담으므로 변환은 경계인 여기서 한다.

    리스트를 순서 그대로 dict 로 되돌리므로 노드·엣지 순서가 보존된다.
    순서가 흔들리면 Graphviz 레이아웃이 바뀌어 화면이 깜빡인다.
    """
    nodes = payload["nodes"]
    solid = {(e["from"], e["to"]): e["interface"] for e in payload["solid_edges"]}
    dotted = {(e["a"], e["b"]): e["labels"] for e in payload["dotted_edges"]}
    return nodes, solid, dotted


# neato graph 속성. inputscale=72 가 없으면 좌표 왕복이 72배로 어긋난다(실측).
#
# model=subset 은 거리를 이웃 부분집합으로 계산한다. 기본값(mode=major)보다
# 엣지 교차가 훨씬 적고 노드 사이가 넓다 — 21벌을 뽑아 재보니 교차 12 -> 3,
# 최소 간격 8.1 -> 50.3pt 였다. 화면이 난잡해 보이던 원인이 기본 모델이었다.
# 최초와 증분에 같은 모델을 쓴다. 다르면 새 노드가 다른 규칙으로 놓여 어색해진다.
_NEATO_MODEL = "model=subset"

NEATO_ATTRS = ("inputscale=72", _NEATO_MODEL)
# 최초 배치에만 겹침을 제거한다. overlap 은 고정(!)을 무시하고 재배치하므로
# 기존 노드를 핀으로 잡아둔 실행에는 절대 쓸 수 없다(실측: 388~710pt 이동).
NEATO_FRESH_ATTRS = ("inputscale=72", _NEATO_MODEL, "overlap=voronoi")


def ensure_positions(graph: dict) -> dict[str, tuple[float, float]]:
    """모든 노드에 좌표가 있게 만든다. 없는 것만 새로 계산해 저장한다.

    좌표가 이미 다 있으면 neato 를 부르지 않는다. 등록으로 노드가 늘었을 때만
    한 번 돌리고, 그때도 기존 노드는 pos="x,y!" 로 고정하므로 움직이지 않는다.
    """
    positions, missing = layout_store.resolve(graph)
    if not missing:
        return positions

    nodes, solid, dotted = to_build_dot_args(graph)
    fresh = not positions  # 처음이면 핀이 없으니 겹침 제거를 쓸 수 있다
    dot = build_dot(
        nodes,
        solid,
        dotted,
        positions=positions,
        spring=True,
        graph_attrs=NEATO_FRESH_ATTRS if fresh else NEATO_ATTRS,
    )

    positions = layout_positions(dot)

    # 최초 배치에서만 눕힌다. model=subset 은 세로로 길게(H/W 1.38) 놓으므로
    # 축을 바꿔 가로로 만든다.
    #
    # 증분 배치에서는 절대 하면 안 된다. 거기 들어간 핀 좌표는 이미 눕혀둔
    # 값이라, 또 바꾸면 지도가 통째로 뒤집히고 기존 노드가 전부 움직인다.
    # 한 번은 통과하고 두 번째 등록에서 터지는 자리라 fresh 분기에만 건다.
    if fresh:
        positions = layout_store.transpose(positions)

    layout_store.save(positions)
    return positions


def wrap_label(name: str) -> str:
    """긴 이름을 두 줄로 접는다. 가운데에 가장 가까운 공백에서 자른다.

    가로 폭이 줄면 겹칠 확률이 가장 크게 준다 — 노드 폭이 194 에서 87 로 준다.
    공백에서만 자른다. 공백이 없는 이름은 그대로 둔다.
    한글이 계속 읽혀야 하므로 글자 중간에서 자르지 않는다.
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
    """노드 이름만 두 줄로 접은 사본. build_dot 은 건드리지 않는다."""
    return {
        node_id: {**node, "name": wrap_label(node.get("name", node_id))}
        for node_id, node in nodes.items()
    }


def to_node_ids(path: list[dict]) -> list[str]:
    """경로에서 노드 id 만. ontology.graph 의 recipe_nodes() 가 주던 것과 같다."""
    return [step["node_id"] for step in path]


def to_edges(node_ids: list[str]) -> list[tuple[str, str]]:
    """사슬을 인접 쌍으로. highlight_edges() 와 같은 계산이다.

    집합이 아니라 리스트다 — 순번 라벨을 붙여야 하고, 같은 엣지를 두 번
    지날 때 그것을 뭉개면 안 된다.
    """
    return list(zip(node_ids, node_ids[1:]))


def mark_from_registration(result: dict | None) -> dict | None:
    """POST /nodes 응답에서 강조할 것만 뽑는다.

    new_solid_edges / new_dotted_edges 는 등록 전후의 차집합이다(작업 1에서
    계약을 확정해두고 여태 쓰지 않았다). 여기서 처음 쓰인다.
    """
    if not result or "error" in result or result.get("reset"):
        return None

    node_id = result.get("node_id")
    return {
        "nodes": [node_id] if node_id else [],
        "solid": [(e["from"], e["to"]) for e in result.get("new_solid_edges") or []],
        "dotted": [(e["a"], e["b"]) for e in result.get("new_dotted_edges") or []],
    }


def mark_key(mark: dict | None) -> str:
    """강조 상태를 캐시 키에 넣을 짧은 문자열.

    강조 여부가 SVG 를 다르게 만든다. 키에 반영하지 않으면 등록 직후 강조가
    안 뜨거나(이전 SVG 재사용) 강조가 계속 남는다.
    """
    if not mark:
        return "plain"

    payload = json.dumps(
        {kind: sorted(map(list, values)) for kind, values in sorted(mark.items())},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


@st.cache_data(show_spinner=False)
def build_graph_svg(
    *,
    _graph: dict | None = None,
    _positions: dict | None = None,
    _mark: dict | None = None,
    version: str = "",
) -> str:
    """온톨로지 그래프 SVG 한 벌.

    발화 해석은 상단 그래프를 강조하지 않는다 — 결과는 하단 경로 패널이
    보여준다. 그래서 후보 조합별로 여러 벌을 만들 이유가 없다.

    모든 노드가 고정된 상태에서 -n 은 배치를 아예 계산하지 않으므로
    좌표가 항상 같다는 것이 구조적으로 보장된다.

    Args:
        _graph: GET /graph 응답. 밑줄로 시작하면 st.cache_data 가 해싱을
            건너뛴다 — 캐시 키는 사실상 version 하나다.
        _positions: {node_id: (x, y)} 고정 좌표.
        _mark: {"nodes": [...], "solid": [...], "dotted": [...]} — 방금 등록된 것.
            없으면 기본 그래프다.
        version: 온톨로지 내용 해시 + 좌표 해시 + 강조 해시. 노드를 등록하면
            값이 바뀌어 캐시가 저절로 무효화된다.
    """
    nodes, solid, dotted = to_build_dot_args(_graph or {})
    mark = _mark or {}

    return stack_nodes_on_top(
        render_svg(
            build_dot(
                wrap_node_labels(nodes),
                solid,
                dotted,
                positions=_positions,
                spring=True,
                # 라벨은 어느 경우에도 안 그린다. 발표자가 말로 설명한다.
                dotted_labels=False,
                node_attrs=NODE_ATTRS_TOP,
                edge_color=config.EDGE_COLOR_TOP,
                dotted_color=config.DOTTED_COLOR_TOP,
                mark_nodes=mark.get("nodes") or (),
                mark_edges=mark.get("solid") or (),
                mark_dotted=mark.get("dotted") or (),
            ),
            "neato",
            no_layout=True,
        )
    )


def show_graph(svg: str, height: int, pulse: bool = False):
    """SVG 를 iframe 으로 띄운다.

    높이를 픽셀로 받는다. iframe 은 height 속성으로 고정되므로 CSS 로 덮을 수
    없다 — 그게 예전에 그래프가 420px 에 갇혀 폭까지 눌렸던 원인이다.
    """
    st.components.v1.html(graph_fill_html(svg, pulse), height=height)


def recipe_ids_of(result: dict | None) -> list[str]:
    """결과에서 강조할 recipe 목록. SELECT 는 하나, CLARIFY 는 후보 전부."""
    if not result:
        return []
    if result["status"] == "SELECT" and result["recipe_id"]:
        return [result["recipe_id"]]
    if result["status"] == "CLARIFY":
        return list(result["candidate_recipe_ids"])
    return []  # NO_MATCH — 강조할 것이 없다.


def focus_key(recipe_ids, mark: dict | None) -> str:
    """하단 그래프 캐시 키. 후보 집합과 모드를 반영한다.

    후보 순서가 달라도 같은 키가 나오게 정렬해서 넣는다 — 순서만 다른데
    캐시가 헛돌면 같은 그림을 매번 다시 만든다.
    """
    payload = json.dumps(
        {"recipes": sorted(recipe_ids or []), "mark": mark_key(mark)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


@st.cache_data(show_spinner=False)
def build_focus_svgs(
    *,
    _graph: dict | None = None,
    _positions: dict | None = None,
    _paths: dict | None = None,
    _recipe_ids: tuple[str, ...] = (),
    _mark: dict | None = None,
    version: str = "",
) -> dict[str, str]:
    """하단 해석 그래프. 조합별로 미리 만들어 둔다.

    {"": 후보 전부 강조, "<마지막노드 id>": 그것으로 끝나는 recipe 만}

    JS 가 SVG 를 다시 칠하지 않는다. 그러면 엣지 굵기·색·순번 규칙이 build_dot 과
    JS 두 곳으로 갈라진다. 파이썬이 변형을 다 만들고 JS 는 고르기만 한다.

    모든 노드가 좌표 고정 + neato -n 이라 어느 변형이든 좌표가 같다는 것이
    구조적으로 보장된다(작업 2). 그래서 몇 벌을 만들어도 화면이 안 흔들린다.
    """
    nodes, solid, dotted = to_build_dot_args(_graph or {})
    wrapped = wrap_node_labels(nodes)
    paths = _paths or {}
    mark = _mark or {}

    def svg_for(recipe_ids):
        return stack_nodes_on_top(
            render_svg(
                build_dot(
                    wrapped,
                    solid,
                    dotted,
                    # 경로가 정확히 하나면 build_dot 이 순번을 붙인다. 기존 규칙 그대로다.
                    highlight_paths=focus.edges_of(paths, recipe_ids),
                    highlight_nodes=focus.nodes_of(paths, recipe_ids),
                    positions=_positions,
                    spring=True,
                    dotted_labels=False,
                    node_attrs=NODE_ATTRS,
                    edge_color=config.EDGE_COLOR,
                    dotted_color=config.DOTTED_COLOR_BOTTOM,
                    mark_nodes=mark.get("nodes") or (),
                    mark_edges=mark.get("solid") or (),
                    mark_dotted=mark.get("dotted") or (),
                ),
                "neato",
                no_layout=True,
            )
        )

    return {
        key: svg_for(recipe_ids)
        for key, recipe_ids in focus.focus_variants(paths, list(_recipe_ids)).items()
    }


def layout_hash(positions: dict) -> str:
    """좌표 해시. 캐시 키에 넣는다."""
    return hashlib.sha1(
        json.dumps(positions, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]


def render_graph_section(
    graph: dict | None = None, mark: dict | None = None, ratios: dict | None = None
):
    """온톨로지 그래프. 무엇을 골랐는지는 하단 경로 패널이 보여준다.

    발화 해석으로는 이 그래프를 강조하지 않는다. 노드를 등록했을 때만
    새로 생긴 것을 강조한다 — 그때가 "어디에 들어갔는지" 를 보여줄 장면이다.

    Args:
        graph: Backend 의 /graph 응답. 무엇을 그릴지는 전부 여기서 온다.
        mark: 방금 등록된 것. 없으면 기본 그래프.
    """
    if graph is None:
        st.markdown(styles.note_markup("그래프를 불러올 수 없습니다. Backend 가 실행 중인지 확인하세요."),
                    unsafe_allow_html=True)
        return

    try:
        positions = ensure_positions(graph)
        # 좌표도 캐시 키에 넣는다. layout.json 을 지우고 다시 켜면 온톨로지가
        # 그대로라 version 은 같지만 좌표는 새로 계산될 수 있다.
        svg = build_graph_svg(
            _graph=graph,
            _positions=positions,
            _mark=mark,
            version=f"{graph['version']}:{layout_hash(positions)}:{mark_key(mark)}",
        )
        height = styles.panel_heights(ratios or config.LAYOUT)["top"]
        show_graph(svg, height, pulse=bool(mark))
    except (GraphvizNotFound, GraphvizFailed) as exc:
        st.markdown(
            styles.note_markup(f"그래프를 그릴 수 없습니다 — {exc}"),
            unsafe_allow_html=True,
        )
