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
from ontology.graph import (  # noqa: E402
    ABOUT,
    dotted_edges,
    group_ids,
    inputs_of,
    is_executable,
    outputs_of,
    recipe_nodes,
    solid_edges,
    start_ids,
    type_ids,
)
from ontology.registry import MENU_BUDGET  # noqa: E402
from ontology.store import edges as ontology_edges  # noqa: E402
from ontology.store import nodes  # noqa: E402


def about_edges() -> list[dict]:
    """대상 관계만. 다른 관계(is-a · hasInput · hasOutput)는 여기 안 센다."""
    return [e for e in ontology_edges() if e["predicate"] == ABOUT]


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def main() -> int:
    node_map = nodes()
    type_names = type_ids()
    recipe_ids = sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))
    solid = solid_edges()
    dotted = dotted_edges()

    print(f"온톨로지 점검 — {paths.ONTOLOGY_PATH}")

    # ------------------------------------------------------------ 규모
    #
    # 노드에는 종류가 안 적혀 있다. 전부 관계로 가른다 — 이 스크립트가 파일에서
    # kind 를 읽으면 프로덕션과 다른 근거로 세는 것이 된다.
    groups = {nid: n for nid, n in node_map.items() if nid in set(group_ids())}
    funcs = {nid: n for nid, n in node_map.items() if is_executable(nid)}
    data = {nid: n for nid, n in node_map.items()
            if nid not in groups and nid not in funcs}

    section("규모")
    print(f"  노드        {len(node_map)}   (기능 {len(funcs)} · 대상 {len(groups)} · "
          f"데이터/형식 {len(data)})")
    print(f"  형식        {len(type_names)}   {', '.join(type_names)}")
    print(f"  경로 시작점  {len(start_ids())}   {', '.join(start_ids())}")
    print(f"  recipe      {len(recipe_ids)}")
    print(f"  실선        {len(solid)}   (recipe 파생)")
    print(f"  점선        {len(dotted)}   (about {len(about_edges())}줄 / "
          f"edges 전체 {len(ontology_edges())}줄)")

    # ------------------------------------------------------------ subject
    section("대상별 소속")
    members = {}
    for edge in about_edges():
        members.setdefault(edge["to"], []).append(edge["from"])

    for group_id, node in sorted(groups.items()):
        attached = sorted(members.get(group_id, []))
        mark = "   ⚠ 아무도 안 붙었다" if not attached else ""
        print(f"  {group_id:<16} {node['name']}   노드 {len(attached)}개{mark}")
        print(f"                   {', '.join(attached) or '없음'}")

    # 한 노드가 여러 대상에 관한 것일 수 있다. 그런 노드를 따로 보여준다 —
    # 승강장 CCTV 영상은 승강장에도 CCTV 에도 관한 것이다.
    multi = {}
    for edge in about_edges():
        multi.setdefault(edge["from"], []).append(edge["to"])
    several = {nid: gs for nid, gs in multi.items() if len(gs) > 1}
    print(f"\n  대상이 둘 이상인 노드 {len(several)}개")
    for node_id, gs in sorted(several.items()):
        print(f"    {node_id:<22} {', '.join(gs)}")

    bare = sorted(set(funcs) - set(multi))
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
    # 형식 노드는 recipe 에 안 나오는 것이 정상이다. 세면 늘 5개가 뜬다.
    orphans = sorted((set(funcs) | set(start_ids())) - touched)
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
    print("       (데이터 노드가 한 칸을 차지한다 — 2단은 데이터 + 기능 하나다)")

    # ------------------------------------------------------------ 대상 넘나듦
    from ontology.graph import crosses_groups  # noqa: E402

    section("대상을 넘나드는 recipe")
    crossing = [rid for rid in recipe_ids if crosses_groups(recipe_nodes(rid))]
    if crossing:
        for recipe_id in crossing:
            print(f"  ⚠ {recipe_id}  {' -> '.join(recipe_nodes(recipe_id))}")
        print("    타입은 맞지만 대상이 안 겹친다. 승강장 CCTV 로 궤도 균열을 찾는")
        print("    것처럼 화각이 안 맞을 수 있다. **막지 않는다** — 판단은 사람이 한다.")
    else:
        print("  없음")

    # ------------------------------------------------------------ 요약
    warnings = len(orphans) + int(over) + len(unknown) + len(strays) + len(crossing)
    section("요약")
    print(f"  표시할 것 {warnings}건")
    if orphans:
        print(f"    - 실선 없는 노드 {len(orphans)}개")
    if over:
        print("    - menu.yaml 상한 초과")
    if unknown:
        print(f"    - 없는 노드를 가리키는 edge {len(unknown)}개")
    if strays:
        print(f"    - recipe 에 섞인 대상 {len(strays)}개")
    if crossing:
        print(f"    - 대상을 넘나드는 recipe {len(crossing)}개 (막지 않는다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
