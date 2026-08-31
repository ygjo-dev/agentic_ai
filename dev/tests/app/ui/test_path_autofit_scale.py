"""대상 : app/ui/components/zoom.py 의 MAX_SCALE · FIT_PAD — 값이 칸에 드는가

문서 검사(test_path_autofit_document.py)는 규칙이 들어 있는지만 본다. 여기서는
**완성된 SVG 를 재서** 시연 발화 넷이 지금 천장 안에서 화면을 채우는지 본다.
브라우저 없이 할 수 있는 것이 여기까지다 — 실제로 맞춰지는지는 사람이 본다.

JS 는 getBoundingClientRect 로 재고 여기서는 경로 좌표로 잰다. 두 값은 정확히
같지 않다.

    JS 가 크게 나온다   선 굵기를 포함해서 잰다 (강조 실선 8pt · 노드 6pt)
    여기가 크게 나온다   베지에 조절점까지 세므로 굽은 엣지가 조금 부푼다

둘 다 몇 pt 짜리라 배율 판정(2.07 대 3.5)을 뒤집지 못한다. 그래서 같은 값을
요구하지 않고 **천장 안에 드는가** 만 본다.
"""

import re

import pytest

from app.api.services import ontology_service, render_service
from app.ui.graph_svg.dot import FLOW_CLASS
from app.ui.components import zoom

# 하단 그래프 칸(px). 2560x1440 화면 · viewport 1282 · bottom_left_ratio 0.60
# 에서 실측한 값이다. NOTES.md 「쉰두째」부터 이 숫자로 계산해 왔다.
BOX_W, BOX_H = 1500.0, 523.0

# 화면으로 볼 목록. NOTES.md 「예순다섯째」 5번과 같은 넷이다.
DEMO_PATHS = [
    ("오송역 좌표 보여줘", "recipe_001"),
    ("오송역 CCTV 보여줘", "recipe_036"),
    ("오송역 근처 충전소 자세히 알려줘", "recipe_060"),
    ("문서에서 철도안전법 관련 내용 찾아줘", "recipe_014"),
]

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:e[-+]?\d+)?", re.I)
_GROUP = re.compile(r'<g id="(node|edge)\d+" class="([^"]*)">(.*?)</g>', re.S)
_GEOMETRY = re.compile(r'\s(?:d|points)="([^"]*)"')
_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
_VIEWBOX = re.compile(r'viewBox="([^"]*)"')


def points(blob: str) -> list[tuple[float, float]]:
    """경로 문자열에서 좌표 쌍만 뽑음. 명령 문자는 숫자가 아니라 걸리지 않음."""
    flat = [float(v) for v in _NUMBER.findall(blob)]
    return list(zip(flat[0::2], flat[1::2]))


def groups(svg: str) -> list[dict]:
    """<g> 하나를 {kind, classes, title, points} 로."""
    out = []
    for match in _GROUP.finditer(svg):
        kind, classes, body = match.group(1), match.group(2), match.group(3)
        title = _TITLE.search(body)
        coords = []
        for blob in _GEOMETRY.findall(body):
            coords += points(blob)
        out.append(
            {
                "kind": kind,
                "classes": classes.split(),
                # Graphviz 는 "-" 와 ">" 를 실체참조로 낸다. 브라우저의
                # textContent 가 돌려주는 모양으로 되돌린다.
                "title": (
                    title.group(1).replace("&#45;", "-").replace("&gt;", ">").strip()
                    if title
                    else ""
                ),
                "points": coords,
            }
        )
    return out


def highlighted(svg: str, with_nodes: bool) -> list[dict]:
    """zoom.py 의 JS 와 같은 규칙으로 고름 — 강조 엣지, 그리고 그 양 끝 노드."""
    every = groups(svg)
    flow = [g for g in every if FLOW_CLASS in g["classes"]]
    if not with_nodes:
        return flow

    ends = set()
    for edge in flow:
        if "->" in edge["title"]:
            ends.update(part.strip() for part in edge["title"].split("->"))
    return flow + [g for g in every if g["kind"] == "node" and g["title"] in ends]


def needed_scale(svg: str, with_nodes: bool = True) -> float:
    """강조 상자를 칸에 채우는 데 필요한 배율. 자르기 전 값."""
    fit = _VIEWBOX.search(svg).group(1).split()
    view_w, view_h = float(fit[2]), float(fit[3])
    # xMidYMid meet — 배율 1 일 때 SVG 가 칸에 들어가는 비율.
    base = min(BOX_W / view_w, BOX_H / view_h)

    picked = highlighted(svg, with_nodes)
    assert picked, "강조가 하나도 없다"
    xs = [p[0] for g in picked for p in g["points"]]
    ys = [p[1] for g in picked for p in g["points"]]
    width = (max(xs) - min(xs)) * base
    height = (max(ys) - min(ys)) * base

    return min(
        (BOX_W - 2 * zoom.FIT_PAD) / width,
        (BOX_H - 2 * zoom.FIT_PAD) / height,
    )


def bottom_svg(recipe_id: str) -> str:
    """그 recipe 를 강조한 하단 SVG(좁히기 전 전체)."""
    if recipe_id not in ontology_service.recipe_ids():
        pytest.skip(f"{recipe_id} 이 지금 온톨로지에 없다")
    return render_service.render("resolve", [recipe_id])["variants"][""]


# ------------------------------------------------------------ 천장이 넉넉한가
@pytest.mark.parametrize("utterance,recipe_id", DEMO_PATHS)
def test_every_demo_path_fits_inside_the_ceiling(utterance, recipe_id):
    """시연 발화 넷이 전부 지금 천장 안에서 화면을 채워야 함.

    천장에 걸리면 경로가 칸을 다 못 채운다 — 죽지는 않지만 "이 경로가
    골라졌다" 가 덜 보인다. 2.5 에서 3.5 로 올린 것이 이 검사 때문이다.
    """
    needed = needed_scale(bottom_svg(recipe_id))

    assert zoom.MIN_SCALE <= needed <= zoom.MAX_SCALE, (
        f"{utterance} 은 배율 {needed:.2f} 가 필요한데 "
        f"천장이 {zoom.MAX_SCALE} 다"
    )


def test_the_ceiling_is_not_wastefully_high():
    """천장이 필요한 것보다 지나치게 높으면 손으로 굴릴 때 헛도는 칸이 는다.

    필요한 최대치의 두 배를 넘지 않는다.
    """
    worst = max(needed_scale(bottom_svg(rid)) for _, rid in DEMO_PATHS)

    assert zoom.MAX_SCALE <= worst * 2


# ------------------------------------------------------------ 노드를 왜 함께 재나
def test_measuring_only_the_edges_would_push_a_demo_path_past_the_ceiling():
    """엣지만 재면 노드 이름이 칸 밖으로 나감.

    「문서에서 철도안전법」은 두 노드가 세로로 가까워 엣지 상자가 작다.
    그것만 재면 천장을 넘을 만큼 확대되고, 노드 상자는 화면에 안 남는다.
    """
    svg = bottom_svg("recipe_014")

    assert needed_scale(svg, with_nodes=False) > zoom.MAX_SCALE
    assert needed_scale(svg, with_nodes=True) <= zoom.MAX_SCALE


# ------------------------------------------------------------ 제일 짧은 경로
def test_the_shortest_path_is_two_nodes_and_one_edge():
    """엣지가 하나뿐인 경로에서도 상자를 잴 수 있어야 함.

    「오송역 좌표 보여줘」가 그 자리다. 특별한 갈래 없이 같은 계산으로 돈다.
    """
    svg = bottom_svg("recipe_001")
    flow = highlighted(svg, with_nodes=False)
    both = highlighted(svg, with_nodes=True)

    assert len(flow) == 1
    assert len(both) == 3          # 엣지 하나 + 양 끝 노드 둘
    assert zoom.MIN_SCALE <= needed_scale(svg) <= zoom.MAX_SCALE
