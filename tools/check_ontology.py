"""온톨로지 내용 점검. 데이터를 고친 뒤 사람이 돌려본다.

    python tools/check_ontology.py

테스트가 아니다. **값을 찍을 뿐 판정하지 않는다.** 노드 수나 점선 개수는
요구사항이 바뀌면 함께 바뀌는 값이라, 테스트로 박아두면 데이터를 손볼 때마다
빨간불이 뜨고 그 빨간불은 아무것도 알려주지 않는다.

다만 **명백한 이상은 표시한다** — 어느 recipe 에도 안 들어간 노드, menu 크기
초과처럼 그냥 두면 시연에서 터지는 것들이다.
"""

import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import paths  # noqa: E402
from ontology.graph import dotted_edges, recipe_nodes, solid_edges  # noqa: E402
from ontology.registry import MENU_BUDGET  # noqa: E402
from ontology.store import interfaces, nodes  # noqa: E402


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def main() -> int:
    node_map = nodes()
    interface_names = interfaces()
    recipe_ids = sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))
    solid = solid_edges()
    dotted = dotted_edges()

    print(f"온톨로지 점검 — {paths.ONTOLOGY_PATH}")

    # ------------------------------------------------------------ 규모
    section("규모")
    print(f"  노드        {len(node_map)}")
    print(f"  인터페이스   {len(interface_names)}   {', '.join(interface_names)}")
    print(f"  recipe      {len(recipe_ids)}")
    print(f"  실선        {len(solid)}")
    print(f"  점선        {len(dotted)}")

    # ------------------------------------------------------------ subject
    section("subject 별 점선")
    by_subject = Counter()
    for labels in dotted.values():
        for label in labels:
            by_subject[label] += 1

    members = {}
    for node_id, node in node_map.items():
        subject = (node.get("properties") or {}).get("subject")
        if subject:
            members.setdefault(subject, []).append(node_id)

    for subject, node_ids in sorted(members.items()):
        count = by_subject.get(f"subject: {subject}", 0)
        # n 개 노드가 서로 다 이어지면 nC2 개다. 다르면 값이 갈렸다는 뜻이다.
        expected = len(node_ids) * (len(node_ids) - 1) // 2
        mark = "" if count == expected else f"   ← 기대 {expected}"
        print(f"  {subject:<8} 노드 {len(node_ids)}개 · 점선 {count}{mark}")
        print(f"           {', '.join(sorted(node_ids))}")

    bare = sorted(
        node_id for node_id, node in node_map.items()
        if not (node.get("properties") or {}).get("subject")
    )
    print(f"\n  subject 없음 {len(bare)}개 : {', '.join(bare) or '없음'}")
    print("           (어느 대상에도 매이지 않는 범용 노드. 점선이 안 생기는 것이 정상)")

    # ------------------------------------------------------------ 끊긴 노드
    section("실선이 하나도 없는 노드")
    touched = {node_id for edge in solid for node_id in edge}
    orphans = sorted(set(node_map) - touched)
    if orphans:
        for node_id in orphans:
            print(f"  ⚠ {node_id}  ({node_map[node_id]['name']})")
        print("    어느 recipe 에도 안 들어간 노드다. 등록 시연용으로 일부러 비워둔")
        print("    것이면 정상이고, 아니면 recipe 를 빠뜨린 것이다.")
    else:
        print("  없음")

    # ------------------------------------------------------------ menu
    section("menu.yaml 크기")
    size = len(paths.MENU_YAML_PATH.read_text(encoding="utf-8"))
    over = size >= MENU_BUDGET
    print(f"  {size} / {MENU_BUDGET}자{'   ⚠ 상한 초과' if over else ''}")
    if over:
        print("    num_ctx(8192)를 넘겨 LLM 이 타임아웃한다.")
        print("    recipe 를 줄이거나 menu 형식을 더 줄여야 한다.")

    # ------------------------------------------------------------ recipe 길이
    section("recipe 단계 수 분포")
    lengths = Counter(len(recipe_nodes(recipe_id)) for recipe_id in recipe_ids)
    for steps in sorted(lengths):
        print(f"  {steps}단  {lengths[steps]:>3}개  {'█' * lengths[steps]}")

    # ------------------------------------------------------------ 요약
    warnings = len(orphans) + int(over)
    section("요약")
    print(f"  표시할 것 {warnings}건")
    if orphans:
        print(f"    - 실선 없는 노드 {len(orphans)}개")
    if over:
        print("    - menu.yaml 상한 초과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
