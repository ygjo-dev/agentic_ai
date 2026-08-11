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
from ontology.store import edges as ontology_edges  # noqa: E402
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
    groups = {nid: n for nid, n in node_map.items() if n.get("kind") == "group"}
    funcs = {nid: n for nid, n in node_map.items() if n.get("kind") != "group"}

    section("규모")
    print(f"  노드        {len(node_map)}   (function {len(funcs)} · group {len(groups)})")
    print(f"  인터페이스   {len(interface_names)}   {', '.join(interface_names)}")
    print(f"  recipe      {len(recipe_ids)}")
    print(f"  실선        {len(solid)}   (recipe 파생)")
    print(f"  점선        {len(dotted)}   (edges 블록 {len(ontology_edges())}줄)")

    # ------------------------------------------------------------ subject
    section("대상(group) 별 소속")
    members = {}
    for edge in ontology_edges():
        members.setdefault(edge["to"], []).append(edge["from"])

    for group_id, node in sorted(groups.items()):
        attached = sorted(members.get(group_id, []))
        mark = "   ⚠ 아무도 안 붙었다" if not attached else ""
        print(f"  {group_id:<16} {node['name']}   기능 {len(attached)}개{mark}")
        print(f"                   {', '.join(attached) or '없음'}")

    bare = sorted(set(funcs) - {edge["from"] for edge in ontology_edges()})
    print(f"\n  대상 없는 기능 {len(bare)}개 : {', '.join(bare) or '없음'}")
    print("           (어느 대상에도 매이지 않는 범용 노드. 안 붙는 것이 정상)")

    unknown = [
        edge for edge in ontology_edges()
        if edge["from"] not in node_map or edge["to"] not in node_map
    ]
    if unknown:
        print(f"\n  ⚠ 없는 노드를 가리키는 edge {len(unknown)}개 : {unknown}")

    # ------------------------------------------------------------ 끊긴 노드
    section("실선이 하나도 없는 노드")
    touched = {node_id for edge in solid for node_id in edge}
    orphans = sorted(set(funcs) - touched)
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
    # group 이 recipe 에 섞이면 실행할 수 없는 경로가 된다.
    in_recipes = {n for rid in recipe_ids for n in recipe_nodes(rid)}
    strays = sorted(in_recipes & set(groups))
    if strays:
        print(f"  ⚠ recipe 에 group 이 섞였다 : {strays}")
    for steps in sorted(lengths):
        print(f"  {steps}단  {lengths[steps]:>3}개  {'█' * lengths[steps]}")

    # ------------------------------------------------------------ 요약
    warnings = len(orphans) + int(over) + len(unknown) + len(strays)
    section("요약")
    print(f"  표시할 것 {warnings}건")
    if orphans:
        print(f"    - 실선 없는 노드 {len(orphans)}개")
    if over:
        print("    - menu.yaml 상한 초과")
    if unknown:
        print(f"    - 없는 노드를 가리키는 edge {len(unknown)}개")
    if strays:
        print(f"    - recipe 에 섞인 group {len(strays)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
