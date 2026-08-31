"""노드 좌표 보관과 배치 계산.

배치를 매번 다시 계산하면 노드가 하나 늘 때마다 지도 전체가 재배치된다.
시연에서 보여줘야 하는 건 "새 노드가 어디에 들어가는지" 인데, 그러면
"화면이 리셋됐다" 로 보인다. 그래서 한 번 정한 좌표를 파일에 남겨 고정한다.

**좌표 파일은 둘이다.** 온톨로지 · recipe · menu 와 같은 꼴이다.

    _init/layout.json   사람이 눈으로 골라 확정한 배치. git 이 추적한다
    layout.json         작업본. 등록할 때마다 바뀐다. .gitignore 다

예전에는 "좌표는 캐시일 뿐이다 — 없으면 다시 계산하면 된다" 였고 그때는
맞았다. 지금은 아니다. 배치 파라미터를 여러 벌 만들어 사람이 화면을 보고
하나를 고르므로, **어느 후보를 골랐는지가 좌표 파일에만 남는다.** 지우면
그 선택이 사라진다.

없으면 계산하는 것은 그대로다. 작업본이 없으면 _init 에서 복사하고, 둘 다
없을 때만 neato 를 돌린다. 그래서 이 모듈은 어떤 경우에도 예외를 올리지
않는다 — 시연 중에 좌표 파일 때문에 화면이 죽는 것이 가장 나쁘다.
"""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from app.ui.graph_svg.dot import (
    GROUP_ATTRS,
    NODE_ATTRS,
    build_dot,
    wrap_node_labels,
)
from app.ui.graph_svg.graphviz import layout_positions

# 이 패키지 안에 둔다. 좌표는 그리기의 소유다 — 만드는 것도 쓰는 것도 여기뿐이고,
# 나중에 JS 렌더러로 갈아끼우면 좌표 파일도 함께 사라진다.
# 파일을 옮기면 이미 잡아둔 좌표를 잃지만, 최초 배치는 결정적이라 같은
# 온톨로지에서는 같은 지도가 다시 나온다(좌표 해시로 확인).
LAYOUT_PATH = Path(__file__).resolve().parent / "layout.json"
# 사람이 고른 배치. 온톨로지 · recipe · menu 의 _init 사본과 같은 자리다.
INIT_LAYOUT_PATH = Path(__file__).resolve().parent / "_init" / "layout.json"


def restore_from_init(path: Path | None = None, init_path: Path | None = None) -> None:
    """_init 사본을 작업본으로 되돌림.

    입력  작업본 경로 · _init 사본 경로(없으면 기본값)
    규칙  ontology.registry.reset_to_init 이 부름. 온톨로지 · recipe · menu 와
          함께 좌표도 첫 배치로 돌아감
          못 되돌려도 예외를 안 올림. 작업본이 그대로 남거나 다시 계산됨
    제약  _init 사본 자체를 건드리지 않는다. 망가지면 되돌릴 곳이 없음
    """
    path = path or LAYOUT_PATH
    init_path = init_path or INIT_LAYOUT_PATH

    try:
        shutil.copy2(init_path, path)
    except OSError:  # 없음 · 권한 등
        pass


def load(path: Path | None = None) -> dict[str, tuple[float, float]]:
    """저장된 좌표.

    출력  {node_id: (x, y)}. 파일이 없거나 깨졌으면 빈 dict
    규칙  한 항목이 이상해도 나머지는 살림
    """
    path = path or LAYOUT_PATH

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # 없음 · 깨진 JSON · 권한 등
        if path != LAYOUT_PATH:
            return {}
        # 작업본이 없거나 깨졌으면 사람이 고른 배치를 읽는다. 복사는
        # ensure_positions 가 한다 — 읽기만 하는 함수가 파일을 만들지 않는다.
        try:
            raw = json.loads(INIT_LAYOUT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
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


# 그릴 때만 곱하는 좌표 배율. 저장된 좌표는 안 고친다 (아래 for_drawing).
# **1.0 이다** — 배치가 처음부터 촘촘하게 놓이므로 줄일 것이 없다. 0.64 였던
# 때의 근거와 왜 없어졌는지는 NOTES.md 「쉰두째」·「쉰셋째」.
DRAW_SCALE = 1.1


def for_drawing(
    positions: dict[str, tuple[float, float]], scale: float | None = None
) -> dict[str, tuple[float, float]]:
    """그릴 좌표. 저장된 좌표에 DRAW_SCALE 을 곱한 사본.

    입력  {node_id: (x, y)} · 배율(생략하면 DRAW_SCALE)
    출력  {node_id: (x*배율, y*배율)}
    규칙  원본을 안 건드림. 저장된 좌표는 배치의 단일 출처로 남음
    제약  배치 계산(ensure_positions)에 이 값을 넣지 않는다.
          거기 들어가는 핀은 저장된 좌표계의 값이어야 함
    """
    factor = DRAW_SCALE if scale is None else scale
    return {node_id: (x * factor, y * factor) for node_id, (x, y) in positions.items()}


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
# 거리 모델은 기본값(model=shortpath)을 쓴다. 예전에는 model=subset 이었고
# 근거는 "교차가 적고 노드 사이가 넓다" 였는데, 노드가 48개가 된 지금 다시
# 재보니 교차는 둘 다 101 로 같고 캔버스만 5357x5348 대 2054x1726 으로
# subset 이 2.6배 컸다. 근거가 사라졌다 (NOTES.md 「쉰셋째」).
# 최초와 증분에 같은 모델을 쓴다. 다르면 새 노드가 다른 규칙으로 놓여 어색해진다.
NEATO_ATTRS = ("inputscale=72",)
# 최초 배치에만 겹침을 제거한다. overlap 은 고정(!)을 무시하고 재배치하므로
# 기존 노드를 핀으로 잡아둔 실행에는 절대 쓸 수 없다(실측: 388~710pt 이동).
NEATO_FRESH_ATTRS = ("inputscale=72", "overlap=voronoi")

# 늘리는 배수. 힘 기반 배치는 등방이라 늘 동그랗게 나오는데(H/W 0.84) 화면
# 칸은 가로로 길다(0.35). 가로로 늘린 뒤 겹침만 다시 없애면 칸 모양에 맞는다.
# 5.0 이었다. 뭉치기(CLUSTER_PULL)가 노드를 무리 안으로 당겨 캔버스가 좁아지므로
# 늘리기를 조금 올려 폭 100% 를 지킨다 (NOTES.md 「예순넷째」의 표).
SPREAD_X = 5.25
# 늘린 자리에서 겹침만 다시 없앤다. maxiter=0 이 배치 반복을 건너뛰므로
# 늘려둔 모양이 그대로 남고, prism 은 겹친 노드만 국소적으로 밀어낸다.
# sep 은 노드 둘레에 두는 여유(pt). +12 였다. 뭉치기가 무리 안을 촘촘하게
# 만들어 +12 로는 캔버스가 커져 글씨가 15.11pt 아래로 떨어진다. +11 에서
# 가장 가까운 쌍이 8.6pt 떨어지고 화면 글씨가 15.21pt 다.
NEATO_SPREAD_ATTRS = ("inputscale=72", "overlap=prism", "maxiter=0", 'sep="+11"')

# 무리로 당기는 정도. 0 이면 안 당기고 1 이면 무리의 무게중심에 겹쳐 쌓는다.
#
# **사람이 화면을 보고 "난잡하다 · 같은 대상끼리 동그랗게 모이면 좋겠다" 고 했다.**
# 엣지 길이(dot.py SOLID_LEN · DOTTED_LEN)로 먼저 해봤는데 안 됐다 — 점선을
# 0.7 에서 0.15 까지 줄여도 뭉침은 2.52 -> 2.6 으로 거의 그대로였고 교차만
# 116 -> 183 으로 늘었다. 점선을 짧게 두면 별이 자기 안으로 무너지고, 그 뒤에
# 오는 겹침 제거가 무너진 것을 다시 흩어놓기 때문이다 (NOTES.md 「예순넷째」).
#
# 그래서 배치가 끝난 자리에서 좌표를 직접 당긴다. 힘으로 부탁하는 것이 아니라
# 결과를 옮기는 것이라 확실하다. 당긴 뒤에 prism 이 겹친 쌍만 밀어내므로
# 겹침 0 은 그대로 지켜진다.
# 0.7 에서 뭉침 2.52 -> 2.84, 교차 116 -> 123 이다.
CLUSTER_PULL = 0.7


def clusters(nodes: dict, dotted: dict) -> dict[str, str]:
    """노드가 어느 무리에 드는가. {node_id: 무리 노드 id}

    입력  노드 전체 · 점선(특성 관계)
    출력  대상 노드와 그 구성원만. 어느 무리에도 안 드는 노드는 안 담김
    규칙  대상 노드(kind=group)에 점선으로 붙은 것이 그 무리의 구성원.
          대상 노드 자신도 자기 무리에 넣음 — 당길 때 무게중심에 함께 들어가야
          별의 한가운데가 딴 데로 밀리지 않음
    제약  한 노드를 두 무리에 넣지 않는다.
          평균 거리를 두 번 세게 되고 당기는 방향도 갈림. 먼저 만난 무리로 둠
    """
    groups = {nid for nid, node in (nodes or {}).items()
              if node.get("kind") == "group"}
    found = {gid: gid for gid in groups}

    for a, b in dotted or ():
        if (a in groups) == (b in groups):
            continue  # 무리끼리 · 무리 아닌 것끼리는 소속을 안 만든다
        group, member = (a, b) if a in groups else (b, a)
        found.setdefault(member, group)

    return found


def pull_to_clusters(
    positions: dict[str, tuple[float, float]],
    nodes: dict,
    dotted: dict,
    strength: float | None = None,
) -> dict[str, tuple[float, float]]:
    """같은 무리 노드를 무게중심 쪽으로 당긴 좌표.

    입력  좌표 · 노드 · 점선 · 당기는 정도(생략하면 CLUSTER_PULL)
    출력  {node_id: (x, y)}
    규칙  무리마다 그 안 노드의 평균 자리를 구하고 그쪽으로 strength 만큼 옮김.
          어느 무리에도 안 드는 노드(지오코딩 · 문서 같은 공용 도구 열일곱)는
          안 건드림 — 무리가 아니므로 모을 중심이 없음
    제약  원본을 안 건드림. 새 dict 를 돌려줌
    제약  이 결과를 그대로 저장하지 않는다.
          당기면 노드가 겹치므로 prism 겹침 제거를 반드시 뒤에 붙인다(spread)
    """
    factor = CLUSTER_PULL if strength is None else strength
    if not factor:
        return dict(positions)

    belongs = clusters(nodes, dotted)

    middle: dict[str, tuple[float, float]] = {}
    for group in set(belongs.values()):
        members = [nid for nid, gid in belongs.items()
                   if gid == group and nid in positions]
        if not members:
            continue
        middle[group] = (
            sum(positions[nid][0] for nid in members) / len(members),
            sum(positions[nid][1] for nid in members) / len(members),
        )

    pulled = {}
    for node_id, (x, y) in positions.items():
        centre = middle.get(belongs.get(node_id, ""))
        if centre is None:
            pulled[node_id] = (x, y)
            continue
        pulled[node_id] = (
            (1 - factor) * x + factor * centre[0],
            (1 - factor) * y + factor * centre[1],
        )
    return pulled


def spread(
    nodes: dict, solid: dict, dotted: dict,
    positions: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """가로로 늘리고 겹침만 다시 없앤 좌표.

    입력  노드 · 실선 · 점선 · 최초 배치 좌표
    출력  {node_id: (x, y)}
    규칙  가로만 SPREAD_X 배 늘리고, 같은 무리를 무게중심으로 당긴 뒤,
          prism 으로 겹친 쌍만 밀어냄
          당기기는 늘리기 **뒤**에 옴. 앞에 두면 늘리기가 동그란 무리를
          가로로 5배 늘려 다시 납작하게 폄
          늘린 좌표는 핀이 아니라 시작 위치로 넘김(pin=False) — 못박으면
          겹침 제거가 할 일이 없음
          노드 크기를 함께 넘김. 겹침 제거가 상자 크기를 알아야 뜻이 있음
          점선 라벨은 끔. 화면이 안 그리는 것을 배치가 세면 자리가 어긋남
          이름은 화면과 같이 두 줄로 접어 넘김
    제약  증분 배치에 쓰지 않는다.
          핀이 있는 실행에 겹침 제거를 걸면 기존 노드가 밀려남
    """
    stretched = {node_id: (x * SPREAD_X, y) for node_id, (x, y) in positions.items()}
    stretched = pull_to_clusters(stretched, nodes, dotted)

    return layout_positions(
        build_dot(
            wrap_node_labels(nodes), solid, dotted,
            positions=stretched,
            pin=False,
            spring=True,
            graph_attrs=NEATO_SPREAD_ATTRS,
            dotted_labels=False,
            node_attrs=NODE_ATTRS,
            group_attrs=GROUP_ATTRS,
        )
    )


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
    # 작업본이 없으면 사람이 고른 배치에서 복사한다. 둘 다 없으면 아래에서
    # neato 가 처음부터 놓는다.
    try:
        fresh_install = not LAYOUT_PATH.exists() and INIT_LAYOUT_PATH.exists()
    except OSError:
        fresh_install = False
    if fresh_install:
        restore_from_init()

    positions, missing = resolve(nodes)
    if not missing:
        return positions

    fresh = not positions  # 처음이면 핀이 없으니 겹침 제거를 쓸 수 있다
    dot = build_dot(
        # 그리는 것과 같은 조건으로 놓는다. 두 줄 접기 · 노드 크기 · 점선
        # 라벨 셋이 다 노드 상자 크기를 바꾸므로, 하나라도 빠지면 배치가
        # 계산한 상자와 화면에 뜨는 상자가 달라져 겹침 제거가 헛돈다.
        wrap_node_labels(nodes),
        solid,
        dotted,
        positions=positions,
        spring=True,
        graph_attrs=NEATO_FRESH_ATTRS if fresh else NEATO_ATTRS,
        dotted_labels=False,
        node_attrs=NODE_ATTRS,
        group_attrs=GROUP_ATTRS,
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

    # 최초 배치에만 늘린다. 증분에 걸면 핀이 통째로 밀린다.
    if fresh:
        positions = spread(nodes, solid, dotted, positions)

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
