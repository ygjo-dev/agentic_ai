"""노드 좌표 보관.

배치를 매번 다시 계산하면 노드가 하나 늘 때마다 지도 전체가 재배치된다.
시연에서 보여줘야 하는 건 "새 노드가 어디에 들어가는지" 인데, 그러면
"화면이 리셋됐다" 로 보인다. 그래서 한 번 정한 좌표를 파일에 남겨 고정한다.

좌표는 캐시일 뿐이다 — 없으면 다시 계산하면 된다. 그래서 이 모듈은
어떤 경우에도 예외를 올리지 않는다. 시연 중에 좌표 파일 때문에 화면이
죽는 것이 가장 나쁘다.
"""

import json
import os
import tempfile
from pathlib import Path

# 저장소 루트. frontend 는 paths 를 import 하지 않는다(계층 규칙).
LAYOUT_PATH = Path(__file__).resolve().parent.parent / "layout.json"


def load(path: Path | None = None) -> dict[str, tuple[float, float]]:
    """저장된 좌표. 파일이 없거나 깨졌으면 빈 dict."""
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
    """좌표를 파일에 쓴다.

    임시 파일에 쓰고 os.replace 로 갈아끼운다 — 중간에 끊겨 깨진 JSON 이
    남으면 다음 실행에서 배치를 통째로 다시 계산하게 된다.
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
    """x 와 y 를 바꾼다. 세로로 긴 배치를 가로로 눕히는 데 쓴다.

    model=subset 은 교차가 압도적으로 적은 대신 세로로 길다(H/W 1.38).
    좌표를 파일로 들고 있으므로 축만 바꿔치면 가로로 눕는다.

    교차 · 간격 · 겹침은 좌표 교환으로 그대로 보존되고, 노드 글씨는 SVG 텍스트라
    가로로 유지된다. 회전이 아니라 축 교환이라 거울상이 되지만, 방향이 없는
    그래프라 읽는 데 차이가 없다.
    """
    return {node_id: (y, x) for node_id, (x, y) in positions.items()}


def resolve(
    graph: dict, path: Path | None = None
) -> tuple[dict[str, tuple[float, float]], list[str]]:
    """저장된 좌표와, 좌표가 없는 노드 id 목록을 함께 돌려준다.

    지금 그래프에 없는 노드의 좌표는 버린다 — 초기화하거나 노드가 사라지면
    남은 좌표가 새 노드의 자리를 잘못 잡게 한다.
    """
    stored = load(path)
    node_ids = list(graph.get("nodes") or {})

    positions = {nid: stored[nid] for nid in node_ids if nid in stored}
    missing = [nid for nid in node_ids if nid not in stored]

    return positions, missing
