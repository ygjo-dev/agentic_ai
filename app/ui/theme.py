"""화면이 쓰는 색. 값은 백엔드가 정하고 여기는 받아 둔다.

색의 출처는 `app/ui/graph_svg/dot.py` 한 곳이다. 그래프 SVG 를 그리는 것도
그 색이고, 칩 테두리 · 새 노드 배지 · 안내 문구도 같은 색이어야 한다. 화면이
자기 팔레트를 따로 들면 두 곳이 조용히 어긋나고, 그때 사람은 화면을 보고
코드를 의심하게 된다.

`/screen` 응답의 colors 를 main.py 가 한 번 넣어주고, 그 뒤로는 어느 컴포넌트든
`theme.get()` 으로 읽는다. Streamlit 은 매 실행마다 스크립트를 처음부터 돌리므로
넣는 시점이 항상 그리기보다 앞선다.
"""

# 백엔드가 죽어 색을 못 받았을 때. 팔레트를 복제하지 않는다 — 복제하면
# 단일 출처가 깨진다. 무채색 하나로 떨어뜨려 "색이 안 왔다" 가 눈에 보이게 둔다.
FALLBACK = "#8C93A1"

_COLORS: dict[str, str] = {}


def set_colors(colors: dict | None) -> None:
    """/screen 응답의 colors 를 받아 둠.

    입력  colors dict. 없으면 이전 값을 유지
    제약  못 받았다고 색을 비우지 않는다.
          백엔드가 잠깐 끊겼을 때 색까지 사라지면 화면이 통째로 회색이 됨.
          마지막으로 받은 값을 그대로 쓰는 편이 나음
    """
    if colors:
        _COLORS.update(colors)


def get(name: str) -> str:
    """색 하나. 못 받았으면 무채색."""
    return _COLORS.get(name, FALLBACK)


def highlight() -> str:
    """선택된 경로."""
    return get("highlight")


def new() -> str:
    """새로 등록된 것."""
    return get("new")


def plain() -> str:
    """그 밖의 모든 것."""
    return get("plain")
