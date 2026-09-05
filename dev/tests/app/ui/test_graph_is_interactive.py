"""대상 : app/ui/components/zoom.py — 그래프를 손으로 움직일 수 있어야 한다

**정지 그림이면 안 된다.** 온톨로지 그래프는 노드가 예순 남짓이라 칸에 다
넣으면 글씨가 안 읽힌다. 확대와 끌기가 없으면 화면이 「그림 한 장」이 되고
시연에서 무엇을 골랐는지 짚어 줄 수가 없다.

★ 2026-09-06 에 이 시험을 더했다. 그때까지 zoom.py 에 시험이 하나도 없었고,
「지금 그래프가 정지 이미지인가」를 코드를 읽지 않고는 답할 수 없었다.
실제로 그 물음이 한 번 올라왔고, 이미 되는 것을 다시 만들 뻔했다.

여기서 브라우저를 띄우지 않는다. 만들어진 문서에 손잡이가 실렸는지만 본다 —
실제 손맛은 사람이 화면에서 본다. 이 시험이 지키는 것은 「손잡이가 조용히
사라지지 않는다」 하나다.
"""

from app.ui.components import zoom
from app.ui.components.graph_section import graph_fill_html

SVG = '<svg><g class="node"><title>n0</title></g></svg>'


def test_the_top_graph_ships_zoom_and_drag():
    """상단 그래프 문서에 확대·끌기 손잡이가 함께 실림.

    셋이 다 있어야 손으로 다룰 수 있음.
      wheel      확대·축소
      mousedown  끌기 시작. mousemove 로 따라오고 mouseup 에 멎음
      dblclick   길을 잃었을 때 되돌아오는 길
    """
    document = graph_fill_html(SVG)

    assert "wheel" in document, "휠 확대가 없다"
    assert "mousedown" in document and "mousemove" in document, "끌기가 없다"
    assert "dblclick" in document, "되돌아올 길이 없다"
    assert "cursor: grab" in document, "끌 수 있다는 표시가 없다"


def test_zoom_has_room_to_move_and_a_ceiling():
    """확대에 바닥과 천장이 있음.

    천장이 없으면 한 번 굴리다 그래프가 사라지고, 바닥이 없으면 점이 된다.
    천장 3.5 의 근거는 NOTES 「예순다섯째」 실측임.
    """
    assert zoom.MIN_SCALE < 1 < zoom.MAX_SCALE
    assert zoom.ZOOM_STEP > 1


def test_the_two_graphs_remember_their_zoom_apart():
    """상단과 하단이 배율을 따로 기억함.

    서로 다른 그래프라 한 키를 나눠 쓰면 한쪽을 굴렸을 때 다른 쪽이 함께 튐.
    """
    assert zoom.TOP_KEY != zoom.BOTTOM_KEY

    top = zoom.zoom_script(zoom.TOP_KEY)
    bottom = zoom.zoom_script(zoom.BOTTOM_KEY)
    assert zoom.TOP_KEY in top and zoom.BOTTOM_KEY not in top
    assert zoom.BOTTOM_KEY in bottom and zoom.TOP_KEY not in bottom


def test_dragging_does_not_count_as_a_click():
    """끌고 나서 손을 떼는 것은 클릭이 아님.

    없으면 그래프를 옮길 때마다 후보가 좁혀지고 배경 클릭으로 전체 복귀됨.
    문턱이 0 이면 손떨림도 끌기로 읽힘.
    """
    assert zoom.DRAG_THRESHOLD > 0
    assert "stopPropagation" in zoom.zoom_script(zoom.TOP_KEY)
