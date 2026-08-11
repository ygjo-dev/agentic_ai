"""배치 후보 비교. 코드를 바꾸지 않고 SVG 만 뽑아 사람이 눈으로 고르게 한다.

    python tools/layout_lab.py

tmp/layouts/<조합이름>.svg 로 남기고 표를 출력한다. 파일명만 봐도 어떤 설정인지 안다.

지금 화면 스타일(색·굵기·채우기·두 줄 접기)을 그대로 써서 뽑는다 — 스타일이
다르면 비교가 의미 없다.

layout.json 을 건드리지 않는다. 조합마다 좌표를 새로 계산하므로 저장된 배치를
읽지도 쓰지도 않는다.
"""

import itertools
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from frontend.components import graph_section as gs  # noqa: E402

OUT_DIR = REPO_ROOT / "tmp" / "layouts"

# penwidth= 안의 width= 에 걸리면 노드 폭을 2인치(144pt)로 잘못 읽는다.
# 작업 3A 에서 실제로 이 함정에 걸려 겹침을 잘못 셌다.
_WIDTH = re.compile(r"(?<![a-zA-Z])width=([\d.]+)")
_HEIGHT = re.compile(r"(?<![a-zA-Z])height=([\d.]+)")
_EDGE_STMT = re.compile(r'"?[\w]+"?\s*->\s*"?[\w]+"?\s*\[[^\]]*\];')
_NODE_STMT = re.compile(r'"?([A-Za-z_]\w*)"?\s*\[([^\]]*)\]\s*;')


def boxes(dot_output: str) -> dict:
    """-Tdot 출력에서 노드 위치와 크기. {id: (x, y, w, h)} 단위 pt."""
    flat = _EDGE_STMT.sub(" ", re.sub(r"\s+", " ", dot_output))

    found = {}
    for match in _NODE_STMT.finditer(flat):
        pos = re.search(r'pos="([-\d.e+]+),([-\d.e+]+)', match.group(2))
        if not pos:
            continue
        width = _WIDTH.search(match.group(2))
        height = _HEIGHT.search(match.group(2))
        found[match.group(1)] = (
            float(pos.group(1)), float(pos.group(2)),
            float(width.group(1)) * 72 if width else 54.0,
            float(height.group(1)) * 72 if height else 36.0,
        )
    return found


def crosses(p, q, r, s) -> bool:
    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2, d3, d4 = side(p, q, r), side(p, q, s), side(r, s, p), side(r, s, q)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def edge_crossings(box: dict, edges) -> int:
    """중심선끼리의 교차 수. 배치의 성질이라 splines 와 무관하다."""
    segments = [
        ((box[a][0], box[a][1]), (box[b][0], box[b][1]))
        for a, b in edges
        if a in box and b in box
    ]
    return sum(
        1
        for s1, s2 in itertools.combinations(segments, 2)
        if not {s1[0], s1[1]} & {s2[0], s2[1]} and crosses(s1[0], s1[1], s2[0], s2[1])
    )


def path_points(svg: str):
    """SVG 엣지 경로를 점 목록으로. 실제 라우팅이라 splines 가 반영된다."""
    for d in re.findall(
        r'<g id="edge\d+" class="edge">.*?<path[^>]*d="([^"]+)"', svg, re.S
    ):
        yield [
            tuple(map(float, p.split(",")))
            for p in re.findall(r"(-?[\d.]+,-?[\d.]+)", d)
        ]


def through_nodes(svg: str, box: dict) -> int:
    """엣지가 노드 박스를 지나는 수. 가려짐의 직접 지표다.

    SVG 는 y 축이 뒤집혀 있어 -Tdot 좌표와 부호가 다르다. 박스도 SVG 쪽에서
    다시 읽는 대신, 여기서는 렌더된 경로만 쓰고 박스는 SVG 노드 도형에서 잰다.
    """
    shapes = {}
    for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>([^<]+)</title>", block)
        coords = [
            tuple(map(float, p.split(",")))
            for p in re.findall(r"(-?[\d.]+,-?[\d.]+)", block)
        ]
        if title and coords:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            shapes[title.group(1)] = (min(xs), min(ys), max(xs), max(ys))

    def hits_box(points, rect) -> bool:
        """경로가 사각형을 지나는가. 점만 보면 직선에서 놓친다 — 선분으로 본다."""
        x0, y0, x1, y1 = rect
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for start, end in zip(points, points[1:]):
            if any(x0 < p[0] < x1 and y0 < p[1] < y1 for p in (start, end)):
                return True
            if any(
                crosses(start, end, corners[i], corners[(i + 1) % 4]) for i in range(4)
            ):
                return True
        return False

    hits = 0
    for points in path_points(svg):
        if len(points) < 2:
            continue
        # 경로의 양 끝은 자기 노드에 닿아 있다. 끝점에서 조금 들어간 구간만 본다.
        inner = points[1:-1] if len(points) > 3 else points
        for rect in shapes.values():
            if hits_box(inner, rect):
                hits += 1
                break
    return hits


def metrics(box: dict, edges, svg: str) -> dict:
    xs = [v[0] for v in box.values()]
    ys = [v[1] for v in box.values()]
    width = max(xs) - min(xs) + max(v[2] for v in box.values())
    height = max(ys) - min(ys) + max(v[3] for v in box.values())

    gaps = []
    overlaps = 0
    for a, b in itertools.combinations(box, 2):
        dx = abs(box[a][0] - box[b][0]) - (box[a][2] + box[b][2]) / 2
        dy = abs(box[a][1] - box[b][1]) - (box[a][3] + box[b][3]) / 2
        gap = max(dx, dy)
        gaps.append(gap)
        if gap < -1:
            overlaps += 1

    return {
        "cross": edge_crossings(box, edges),
        "through": through_nodes(svg, box),
        "w": width,
        "h": height,
        "ratio": height / width,
        "gap": min(gaps),
        "overlap": overlaps,
    }


def run_case(nodes, solid, dotted, *, model=None, mode=None, splines=None,
             slen=None, overlap="voronoi"):
    """한 조합을 배치하고 렌더한다. 지금 화면 스타일 그대로."""
    attrs = ["inputscale=72", f"overlap={overlap}"]
    if mode:
        attrs.append(f"mode={mode}")
    if model:
        attrs.append(f"model={model}")
    if splines:
        attrs.append(f"splines={splines}")

    original = gs.SOLID_LEN
    if slen is not None:
        gs.SOLID_LEN = slen
    try:
        dot = gs.build_dot(
            nodes, solid, dotted, spring=True, graph_attrs=tuple(attrs),
            node_attrs=gs.NODE_ATTRS, dotted_labels=False,
            edge_color=gs.config.EDGE_COLOR, dotted_color=gs.config.DOTTED_COLOR_BOTTOM,
        )
        box = boxes(gs._run_graphviz(dot, "neato", ["-Tdot"]))

        pinned = gs.build_dot(
            nodes, solid, dotted, positions={k: (v[0], v[1]) for k, v in box.items()},
            spring=True, graph_attrs=tuple(a for a in attrs if not a.startswith("overlap")),
            node_attrs=gs.NODE_ATTRS, dotted_labels=False,
            edge_color=gs.config.EDGE_COLOR, dotted_color=gs.config.DOTTED_COLOR_BOTTOM,
        )
        svg = gs.stack_nodes_on_top(gs.render_svg(pinned, "neato", no_layout=True))
    finally:
        gs.SOLID_LEN = original

    return box, svg


def main():
    from fastapi.testclient import TestClient
    import backend.main as backend_main

    graph = TestClient(backend_main.app).get("/graph").json()
    nodes, solid, dotted = gs.to_build_dot_args(graph)
    wrapped = gs.wrap_node_labels(nodes)
    edges = list(solid) + list(dotted)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.svg"):
        stale.unlink()

    # 1차 : 배치 모델 x 엣지 모양
    cases = []
    for label, kw in [
        ("mode-major", {"mode": "major"}),
        ("mode-KK", {"mode": "KK"}),
        ("model-subset", {"model": "subset"}),
        ("model-circuit", {"model": "circuit"}),
    ]:
        for shape in (None, "true", "curved"):
            name = f"{label}_{'straight' if shape is None else 'splines-' + shape}"
            cases.append((name, {**kw, "splines": shape}))

    results = []
    for name, kw in cases:
        try:
            box, svg = run_case(wrapped, solid, dotted, **kw)
        except Exception as exc:  # noqa: BLE001 — 한 조합이 죽어도 나머지는 본다
            print(f"  건너뜀 {name}: {exc}")
            continue
        (OUT_DIR / f"{name}.svg").write_text(svg, encoding="utf-8", newline="\n")
        results.append((name, kw, metrics(box, edges, svg)))

    # 2차 : 1차 상위에 len 과 overlap 을 붙인다.
    # 배치 모델이 겹치지 않게 고른다 — splines 만 다른 것끼리는 배치가 같아서
    # len 을 붙여봐야 같은 그림이 세 벌 나온다.
    ranked = sorted(results, key=lambda r: (r[2]["cross"], r[2]["through"]))
    seeds, seen_models = [], set()
    for name, kw, _ in ranked:
        model = (kw.get("mode"), kw.get("model"))
        if model in seen_models:
            continue
        seen_models.add(model)
        seeds.append((name, kw))
        if len(seeds) == 3:
            break

    for name, kw in seeds:
        for extra_label, extra in [
            ("len3.0", {"slen": 3.0}),
            ("len5.5", {"slen": 5.5}),
            ("prism", {"overlap": "prism"}),
        ]:
            full = f"{name}_{extra_label}"
            try:
                box, svg = run_case(wrapped, solid, dotted, **{**kw, **extra})
            except Exception as exc:  # noqa: BLE001
                print(f"  건너뜀 {full}: {exc}")
                continue
            (OUT_DIR / f"{full}.svg").write_text(svg, encoding="utf-8", newline="\n")
            results.append((full, {**kw, **extra}, metrics(box, edges, svg)))

    print(f"\nSVG {len(results)}벌 -> {OUT_DIR}")
    print(f"\n{'조합':<44}{'교차':>5}{'관통':>5}{'캔버스':>13}{'H/W':>7}{'최소간격':>9}{'겹침':>5}")
    print("-" * 90)

    current = "mode-major_straight"
    for name, _, m in sorted(results, key=lambda r: (r[2]["cross"], abs(r[2]["ratio"] - 0.5))):
        mark = "  <- 현재" if name == current else ""
        canvas = f"{int(m['w'])}x{int(m['h'])}"
        print(
            f"{name:<44}{m['cross']:>5}{m['through']:>5}{canvas:>13}"
            f"{m['ratio']:>7.2f}{m['gap']:>9.1f}{m['overlap']:>5}{mark}"
        )


if __name__ == "__main__":
    main()
