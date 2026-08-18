"""노드 좌표 보관과 배치 계산.

배치를 매번 다시 계산하면 노드가 하나 늘 때마다 지도 전체가 재배치된다.
시연에서 보여줘야 하는 건 "새 노드가 어디에 들어가는지" 인데, 그러면
"화면이 리셋됐다" 로 보인다. 그래서 한 번 정한 좌표를 파일에 남겨 고정한다.

좌표는 캐시일 뿐이다 — 없으면 다시 계산하면 된다. 그래서 이 모듈은
어떤 경우에도 예외를 올리지 않는다. 시연 중에 좌표 파일 때문에 화면이
죽는 것이 가장 나쁘다.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from demo.graph_svg.dot import build_dot
from demo.graph_svg.graphviz import layout_positions

# 이 패키지 안에 둔다. 좌표는 그리기의 소유다 — 만드는 것도 쓰는 것도 여기뿐이고,
# 나중에 JS 렌더러로 갈아끼우면 좌표 파일도 함께 사라진다.
# 파일을 옮기면 이미 잡아둔 좌표를 잃지만, 최초 배치는 결정적이라 같은
# 온톨로지에서는 같은 지도가 다시 나온다(좌표 해시로 확인).
LAYOUT_PATH = Path(__file__).resolve().parent / "layout.json"


def load(path: Path | None = None) -> dict[str, tuple[float, float]]:
    """저장된 좌표.

    출력  {node_id: (x, y)}. 파일이 없거나 깨졌으면 빈 dict
    규칙  한 항목이 이상해도 나머지는 살림
    """
    path = path or LAYOUT_PATH

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # 없음 · 깨진 JSON · 권한 등
        return {}

    if not isinstance(raw, dict):
        return {}

    positions = {}
    for node_id, value in raw.items():
        try:
            x, y = value
            positions[node_id] = (float(x), float(y))
        except (TypeError, ValueError):
            continue  # 한 항목이 이상해도 나머지는 살린다
    return positions


def save(positions: dict[str, tuple[float, float]], path: Path | None = None) -> None:
    """좌표를 파일에 씀.

    입력  {node_id: (x, y)} · 쓸 경로(없으면 LAYOUT_PATH)
    규칙  못 써도 예외를 올리지 않음. 다음 실행에서 다시 계산할 뿐
    제약  대상 파일에 직접 쓰지 않는다.
          임시 파일에 쓰고 os.replace 로 갈아끼움. 중간에 끊겨 깨진 JSON 이
          남으면 다음 실행에서 배치를 통째로 다시 계산하게 됨
    """
    path = path or LAYOUT_PATH
    body = json.dumps(
        {node_id: [x, y] for node_id, (x, y) in positions.items()},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            tmp = Path(handle.name)
            handle.write(body + "\n")
        os.replace(tmp, path)
    except OSError:
        # 못 써도 화면은 그려져야 한다. 다음 실행에서 다시 계산할 뿐이다.
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass


def transpose(
    positions: dict[str, tuple[float, float]]
) -> dict[str, tuple[float, float]]:
    """x 와 y 를 바꿈. 세로로 긴 배치를 가로로 눕히는 데 씀.

    입력  {node_id: (x, y)}
    출력  {node_id: (y, x)}
    규칙  model=subset 은 교차가 압도적으로 적은 대신 세로로 김(H/W 1.38).
          좌표를 파일로 들고 있으므로 축만 바꿔치면 가로로 누움
          교차 · 간격 · 겹침은 좌표 교환으로 그대로 보존되고, 노드 글씨는
          SVG 텍스트라 가로로 유지됨
          회전이 아니라 축 교환이라 거울상이 되지만 방향이 없는 그래프라
          읽는 데 차이가 없음
    """
    return {node_id: (y, x) for node_id, (x, y) in positions.items()}


def is_tall(positions: dict[str, tuple[float, float]]) -> bool:
    """세로가 가로보다 긴 배치인가.

    출력  참이면 눕힐 것. 노드가 하나 이하면 거짓
    규칙  좌표의 퍼진 범위로 잼. 렌더링한 SVG 크기가 아니라 좌표라서 노드
          크기와 여백은 안 들어가지만 눕힐지 말지를 가르는 데는 충분함
          노드가 하나거나 없으면 눕힐 것이 없어 거짓. 0 으로 나누지도 않음
    """
    if len(positions) < 2:
        return False

    xs = [x for x, _ in positions.values()]
    ys = [y for _, y in positions.values()]

    return (max(ys) - min(ys)) > (max(xs) - min(xs))


def resolve(
    nodes: dict, path: Path | None = None
) -> tuple[dict[str, tuple[float, float]], list[str]]:
    """저장된 좌표와 좌표가 없는 노드 id 목록.

    입력  노드 전체 · 좌표 파일 경로(없으면 LAYOUT_PATH)
    출력  (positions, missing)
    제약  지금 그래프에 없는 노드의 좌표를 남기지 않는다.
          초기화하거나 노드가 사라지면 남은 좌표가 새 노드의 자리를 잘못 잡음
    """
    stored = load(path)
    node_ids = list(nodes or {})

    positions = {nid: stored[nid] for nid in node_ids if nid in stored}
    missing = [nid for nid in node_ids if nid not in stored]

    return positions, missing


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


def ensure_positions(
    nodes: dict, solid: dict, dotted: dict
) -> dict[str, tuple[float, float]]:
    """모든 노드에 좌표가 있게 만듦. 없는 것만 새로 계산해 저장.

    입력  노드 · 실선 · 점선. 도메인 dict 를 그대로 받음
    출력  {node_id: (x, y)}
    규칙  좌표가 이미 다 있으면 neato 를 안 부름
          등록으로 노드가 늘었을 때만 한 번 돌리고, 그때도 기존 노드는
          pos="x,y!" 로 고정하므로 안 움직임
    제약  증분 배치에서 눕히지 않는다.
          거기 들어간 핀 좌표는 이미 눕혀둔 값이라 또 바꾸면 지도가 통째로
          뒤집히고 기존 노드가 전부 움직임. 한 번은 통과하고 두 번째 등록에서
          터지는 자리라 fresh 분기에만 걺
    이력  예전에는 조건 없이 눕혔음. 그때 배치가 늘 세로로 길었기 때문인데
          (H/W 1.38), 온톨로지를 바꾸자 배치가 이미 가로로 길어졌고(0.83)
          거기에 또 회전을 걸어 1.09 로 되돌려놓고 있었음. 패널 폭 사용이
          49% 에서 37% 로 떨어졌음
          예전에는 프론트엔드가 JSON 응답을 튜플 키 dict 로 되돌려 넘겼음.
          그리기가 서버로 들어온 지금은 왕복할 이유가 없음
    """
    positions, missing = resolve(nodes)
    if not missing:
        return positions

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

    # 최초 배치에서만, 그리고 **세로로 길 때만** 눕힌다. 화면 패널이 가로로
    # 넓어서(H/W 0.40) 세로로 긴 배치는 높이에 걸려 폭을 못 쓴다.
    #
    # 예전에는 조건 없이 눕혔다. 그때 배치가 늘 세로로 길었기 때문인데(H/W 1.38),
    # 온톨로지를 바꾸자 배치가 이미 가로로 길어졌고(0.83) 거기에 또 회전을 걸어
    # 1.09 로 되돌려놓고 있었다 — 패널 폭 사용이 49% 에서 37% 로 떨어졌다.
    # 목적은 "회전한다" 가 아니라 "가로로 눕힌다" 이므로 조건을 붙인다.
    #
    # 증분 배치에서는 절대 하면 안 된다. 거기 들어간 핀 좌표는 이미 눕혀둔
    # 값이라, 또 바꾸면 지도가 통째로 뒤집히고 기존 노드가 전부 움직인다.
    # 한 번은 통과하고 두 번째 등록에서 터지는 자리라 fresh 분기에만 건다.
    if fresh and is_tall(positions):
        positions = transpose(positions)

    save(positions)
    return positions


def layout_hash(positions: dict) -> str:
    """좌표 해시. 캐시 키에 넣음.

    출력  12자 해시
    제약  캐시 키를 온톨로지 version 만으로 만들지 않는다.
          좌표는 version 과 따로 놂. layout.json 을 지우고 다시 켜면 version 은
          그대로인데 좌표만 새로 잡힐 수 있고, 그때 캐시가 안 비면 옛 그림이
          그대로 나옴
    """
    return hashlib.sha1(
        json.dumps(positions, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
