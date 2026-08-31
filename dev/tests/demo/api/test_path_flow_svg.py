"""대상 : demo/api/main.py — POST /render 가 낸 SVG 에 흐름 표시가 실려 나오는지

**★ 완성된 SVG 를 본다.** build_dot 만 고치고 단위 테스트만 두면 조립부가
그 인자를 안 넘겨도 전부 통과한다 — group_attrs · review_edges 에서 두 번
당했다.

여기서 보는 것은 표시가 붙는 자리뿐이다. 실제로 흐르는지는 브라우저가 하는
일이고, 문서에 규칙이 실렸는지는 tests/demo/ui/test_path_flow.py 가 본다.
"""

import re
import shutil

import pytest
from fastapi.testclient import TestClient

import demo.api.main as backend_main
from demo.api.services.ontology_service import recipe_ids
from demo.graph_svg import build
from demo.graph_svg.dot import FLOW_CLASS, HIGHLIGHT_COLOR, PATH_PENWIDTH

pytestmark = pytest.mark.skipif(
    shutil.which("neato") is None, reason="graphviz 가 설치되어 있지 않다"
)

CHOSEN = recipe_ids()[:2]


@pytest.fixture
def client():
    build.clear_cache()
    return TestClient(backend_main.app)


def rendered(client, mode, mark=None):
    response = client.post(
        "/render",
        json={"mode": mode, "recipe_ids": CHOSEN, "mark": mark},
    )
    assert response.status_code == 200
    return response.json()


def flowing_edges(svg: str) -> set[str]:
    """흐름 표시가 붙은 엣지 이름들."""
    return set(
        re.findall(
            r'<g id="edge\d+" class="edge ' + FLOW_CLASS + r'">\s*<title>(.*?)</title>',
            svg,
        )
    )


def highlighted_edges(svg: str) -> set[str]:
    """굵은 teal 실선인 엣지 이름들. 표시와 상관없이 색·굵기로만 셈."""
    found = set()
    for block in re.findall(r'<g id="edge\d+" class="edge[^"]*">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>(.*?)</title>", block, re.S)
        teal = f'stroke="{HIGHLIGHT_COLOR}" stroke-width="{PATH_PENWIDTH}"'
        if title and teal.lower() in block.lower():
            found.add(title.group(1))
    return found


def test_the_chosen_path_carries_the_flow_mark(client):
    """해석 장면에서 굵은 teal 실선과 표시가 붙은 엣지가 정확히 같아야 함."""
    whole = rendered(client, "resolve")["variants"][""]

    assert highlighted_edges(whole), "teal 실선이 하나도 없다 — 검사가 무력하다"
    assert flowing_edges(whole) == highlighted_edges(whole)


def test_the_bottom_graph_is_the_only_place_it_appears(client):
    """상단은 실선을 안 그리므로 표시가 하나도 없어야 함."""
    payload = rendered(client, "resolve")

    assert flowing_edges(payload["top"]) == set()


def test_narrowing_keeps_the_mark_on_what_stays_lit(client):
    """좁힌 변형에서도 짙은 경로와 표시가 같이 감."""
    variants = rendered(client, "resolve")["variants"]

    for svg in variants.values():
        assert flowing_edges(svg) == highlighted_edges(svg)


def test_the_registration_scene_has_no_flow(client):
    """등록 장면에는 teal 이 없고 표시도 없음. 주황 경로는 안 흐름."""
    mark = {"nodes": [], "solid": [], "dotted": [], "accepted": []}
    payload = rendered(client, "register", mark)

    for svg in payload["variants"].values():
        assert flowing_edges(svg) == set()
