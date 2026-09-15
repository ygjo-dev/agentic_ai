"""온톨로지가 만드는 recipe 후보를 사람이 받아들인 recipe 와 대조한다. **쓰지 않는다.**

    python dev/tools/rebuild_init.py            후보 표 · menu 문장 대조 · 요약
    python dev/tools/rebuild_init.py --quiet    요약만

## 후보와 받아들인 것은 다르다

    온톨로지   「어떤 경로를 이을 수 있는가」   registry.candidate_recipes
    사람       「그것을 서비스 recipe 로 올리는가」   workflows/static/recipes/ 의 파일

**받아들인 recipe 파일 자체가 사람의 판정 결과다.** 따로 목록 파일을 두지 않는다 —
두면 원천이 둘이 되고 어긋났을 때 어느 쪽이 맞는지 알 수 없다. 사람이 지운 후보는
파일이 없으므로 여기서 「미게시」로 보이고, 다시 올라가지 않는다.

**그래서 이 도구는 후보를 파일로 쓰지 않는다.** 후보를 통째로 recipe 로 다시 쓰면
사람이 지운 경로가 되살아나고, 번호가 흔들리고, recipe 파일에 사람이 적은 example
이 사라진다. 후보 하나를 받아들이는 것은 사람이 한다 — CLAUDE.md 「recipe 번호」의
되살리는 법(recipe 두 벌 · menu 두 벌 · 정답표 발화)이 그 절차다.

## menu 문장은 견주기만 한다

`registry.function_for` 가 온톨로지(시작 노드의 source · 기능의 description ·
경로)로 만든 문장과 지금 menu.yaml 에 실린 문장을 나란히 찍는다. **menu.yaml 을
덮어쓰지 않는다** — 지금 문장은 사람이 다듬어 판정을 잰 것이라 한 글자만 바뀌어도
이미 검증한 발화가 다른 recipe 로 갈 수 있다.

example 은 온톨로지에 없다. 사람이 recipe 파일에 적은 값이고, menu 에 실린 example
과 같은지를 여기서 본다.

## 기준이 되는 두 값

MIN_STEPS — recipe 로 삼을 경로의 최소 노드 수. 아래 주석이 그 역사다.
대상이 어긋나는 경로(crosses_groups)는 후보에서 뺀다 — registry 가 한다.

서버도 LLM 도 쓰지 않는다. 파일만 읽는다.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import yaml  # noqa: E402

import paths  # noqa: E402
from registration import recipe_execution_builder  # noqa: E402
from ontology import store  # noqa: E402
from registration.registry import (  # noqa: E402
    MAX_STEPS,
    MENU_BUDGET,
    accepted_recipes,
    all_recipes,
    candidate_recipes,
    function_for,
)

# recipe 로 삼을 경로의 최소 노드 수.
#
# **기준은 길이가 아니라 끝점이다.** 사용자가 그것을 달라고 할 만한 것에서
# 끝나면 recipe 이고, 재료에서 끝나면 앞토막이다. 길이는 그 대용품일 뿐이다.
#
# 3 이었다. 그때 2단의 끝점은 image(프레임 추출 결과)였고 그것은 재료였다 —
# "프레임만 뽑아줘" 라고 할 사람이 없는데 **다른 모든 recipe 의 앞토막**이라
# menu 에 있으면 발화 해석이 "어디서 끝나는가" 를 못 갈랐다. 실측으로 35/35 가
# 5/35 가 됐고(e8fcdc2), 프롬프트를 절차형으로 바꿔 25/45 까지만 올렸다.
# **그 숫자는 그때의 온톨로지(철도 CCTV 14노드) 기준이다.** 지금 온톨로지에
# 그대로 대입할 수 없다.
#
# 2 로 내렸다. 지금 2단은 장소 이름 → 장소 좌표 변환이고 그 끝점 지점 좌표는
# 재료가 아니라 사용자가 원하는 답이다 — "오송역 좌표 알려줘" 가 그 발화다.
# 답에서 끝나는 경로를 길이 때문에 버리면 그 발화는 갈 곳이 없어진다.
#
# **앞토막 위험이 사라진 것은 아니다.** 2단은 여전히 3단의 앞토막이라
# "오송역 좌표 알려줘" 와 "오송역 CCTV 보여줘" 의 끝점이 실제로 갈리는지는
# 판정 자(dev/tools/check_resolve.py)가 잰다.
#
# 온톨로지가 끝점을 스스로 말하게 하려면(deliverable 같은 타입) 이 조건은
# 사라진다. 그때까지는 길이로 자른다.
MIN_STEPS = 2

# 표에서 경로 칸 앞의 폭.
STATUS_WIDTH = 12


def _recipe_file(recipe_id: str) -> dict:
    """recipe 파일 원문."""
    return yaml.safe_load((paths.RECIPES_DIR / f"{recipe_id}.yaml").read_text(encoding="utf-8")) or {}


def _menu() -> dict:
    """지금 menu.yaml 의 recipes."""
    return (yaml.safe_load(paths.MENU_YAML_PATH.read_text(encoding="utf-8")) or {}).get("recipes") or {}


def _tool_names() -> set[str]:
    """온톨로지 tool 에 적힌 도구 이름 · 명령 이름. 문장에 샜는지 볼 때 씀."""
    names = set()
    for node_id in store.nodes():
        binding = recipe_execution_builder.binding_of(node_id)
        if binding is None:
            continue
        names.add(binding["id"])
        names.add(binding.get("tool") or binding.get("command") or binding["id"].split("/", 1)[1])
    return names


def review(quiet: bool) -> int:
    nodes = store.nodes()
    every = all_recipes(nodes)
    candidates = [chain for chain in candidate_recipes(nodes) if len(chain) >= MIN_STEPS]
    accepted = accepted_recipes()
    by_chain = {tuple(chain): recipe_id for recipe_id, chain in accepted.items()}

    # ---------------------------------------------------------- 후보 표
    if not quiet:
        print()
        print("## 후보 — 온톨로지로 이을 수 있는 경로")
        print()
        for index, chain in enumerate(candidates, start=1):
            status = by_chain.get(tuple(chain), "미게시")
            names = " → ".join(nodes[node_id]["name"] for node_id in chain)
            missing = recipe_execution_builder.unwired_in(chain)
            mark = f"   (실행 수단 없음: {' · '.join(missing)})" if missing else ""
            print(f"  {index:>3}  {status:<{STATUS_WIDTH}} {names}{mark}")

    candidate_set = {tuple(chain) for chain in candidates}
    stranded = [recipe_id for recipe_id, chain in accepted.items() if tuple(chain) not in candidate_set]
    unwired = {recipe_id: recipe_execution_builder.unwired(recipe_id) for recipe_id in accepted}
    unwired = {recipe_id: missing for recipe_id, missing in unwired.items() if missing}

    # ---------------------------------------------------------- menu 문장 대조
    menu = _menu()
    leaks = _tool_names()
    same_function, same_example, rows = 0, 0, []
    leaked = []
    for recipe_id, chain in accepted.items():
        generated = function_for(chain, nodes)
        active = (menu.get(recipe_id) or {}).get("function", "")
        example_file = _recipe_file(recipe_id).get("example")
        example_menu = (menu.get(recipe_id) or {}).get("example")
        same_function += generated == active
        same_example += example_file == example_menu
        leaked += [f"{recipe_id}: {name}" for name in leaks if name in generated]
        rows.append((recipe_id, generated, active, example_file, example_menu))

    if not quiet:
        print()
        print("## menu 문장 — 온톨로지로 만든 것 / 지금 menu.yaml 에 실린 것")
        for recipe_id, generated, active, example_file, example_menu in rows:
            print()
            print(f"  {recipe_id}")
            print(f"    만든 것   {generated}")
            print(f"    지금 것   {active or '(menu 에 없음)'}")
            if example_file or example_menu:
                mark = "" if example_file == example_menu else "   ★ 어긋남"
                print(f"    example   recipe={example_file!r} · menu={example_menu!r}{mark}")

    # ---------------------------------------------------------- 요약
    size = len(paths.MENU_YAML_PATH.read_text(encoding="utf-8"))
    crossing = len(every) - len(candidate_recipes(nodes))
    print()
    print("## 요약")
    print()
    runnable = sum(1 for chain in candidates if not recipe_execution_builder.unwired_in(chain))
    print(f"  경로 {len(every)} · 대상이 어긋나 뺀 것 {crossing} · 후보 {len(candidates)} (MAX_STEPS {MAX_STEPS})"
          f" · 그중 지금 실행 수단이 다 붙는 것 {runnable}")
    print(f"  받아들인 recipe {len(accepted)} · 그중 후보로 만들 수 있는 것 {len(accepted) - len(stranded)}"
          f" · 미게시 후보 {len(candidates) - (len(accepted) - len(stranded))}")
    if stranded:
        print("  ★ 온톨로지가 더는 못 만드는 recipe : " + " · ".join(stranded))
    if unwired:
        print("  ★ 실행 수단이 빈 recipe : " + " · ".join(f"{rid}({'·'.join(m)})" for rid, m in unwired.items()))
    print(f"  menu 문장이 만든 것과 같은 recipe {same_function}/{len(accepted)}"
          f" · example 이 recipe 파일과 menu 에서 같은 recipe {same_example}/{len(accepted)}"
          f" · recipe 파일의 example {sum(1 for row in rows if row[3])}")
    print(f"  menu.yaml {size}자 / MENU_BUDGET {MENU_BUDGET}")
    if leaked:
        print("  ★ 만든 문장에 도구 이름이 샜다 : " + " · ".join(leaked))
    print()
    print("  쓰지 않았다. 후보를 받아들이는 것은 사람이 한다 (CLAUDE.md 「recipe 번호」).")
    return 1 if stranded or leaked else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="온톨로지 후보를 받아들인 recipe · menu 와 대조한다. 쓰지 않는다."
    )
    parser.add_argument("--quiet", action="store_true", help="요약만")
    args = parser.parse_args()
    return review(args.quiet)


if __name__ == "__main__":
    sys.exit(main())
