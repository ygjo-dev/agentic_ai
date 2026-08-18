"""`_init` 의 recipe 와 menu 를 온톨로지에서 다시 만든다.

    python tools/rebuild_init.py            무엇이 바뀌는지 보여주고 멈춘다
    python tools/rebuild_init.py --write    실제로 쓴다

**기본이 미리보기다.** 실수로 돌렸을 때 `_init` 이 날아가면 되돌릴 곳이 없다.

경로 생성 · 파일 형식 · menu 문장은 전부 `ontology.registry` 의 함수를 쓴다.
여기서 새로 짜지 않는다 — 등록으로 생기는 recipe 와 규칙이 갈리면
"초기 recipe 는 되는데 등록한 건 안 되는" 상황이 나오고,
menu 문장이 발화 매칭의 유일한 근거라 원인을 찾기도 어렵다.

이 파일이 직접 정하는 것은 "무엇을 거를 것인가"(crosses_groups · MIN_STEPS)뿐이다.

**`_init` 만 만든다. 작업본은 안 건드린다.** 작업본은 화면의 초기화 버튼
(`registry.reset_to_init`)이 `_init` 에서 복사한다. 도구가 작업본을 직접 쓰면
리허설 중에 돌렸을 때 화면과 어긋난다.

`_init` 의 recipe 는 원래 손으로 골라 만든 것이었다. 그래서 온톨로지가 만들 수
있는 경로 여덟 중 둘(데이터 → 프레임 추출)이 빠져 있었다. 그 둘을 넣어 봤다가
발화 해석이 무너져 되돌렸다 — 아래 `MIN_STEPS` 를 본다.
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paths  # noqa: E402
from ontology import store  # noqa: E402
from ontology.graph import crosses_groups  # noqa: E402
from ontology.registry import (  # noqa: E402
    MENU_BUDGET,
    all_recipes,
    append_menu,
    append_recipes,
    function_for,
)

# menu.yaml 에서 항목 앞까지 남길 부분. 이 뒤를 잘라내고 append_menu 로 다시 채운다.
MENU_YAML_HEAD_MARKER = "recipes:"

# 2단 경로(데이터 → 프레임 추출)는 recipe 로 삼지 않는다.
#
# 실행할 수는 있다. 다만 image 는 중간 산출물이라 사용자가 그것을 달라고 하지
# 않고, 무엇보다 **다른 모든 recipe 의 앞토막**이라 menu 에 있으면 발화 해석이
# "어디서 끝나는가" 를 못 가른다 — 실측으로 35/35 가 5/35 가 됐다(e8fcdc2).
# 프롬프트를 절차형으로 바꿔 25/45 까지 올렸으나 나머지를 못 채웠고, 고칠수록
# 시연에 안 쓰는 발화가 대신 무너졌다.
#
# **지금은 길이로 자르지만 진짜 기준은 끝점이다.** analysis · output_report 는
# 사용자가 원하는 것이고 image 는 재료다. 온톨로지가 그것을 말하게 하려면
# deliverable 같은 타입이 필요하고, 그때 이 조건이 사라진다.
MIN_STEPS = 3

# menu.md 에서 목차 표 머리까지 남길 부분. append_menu 는 이 표 끝에 행을 넣고
# 본문 섹션은 "\n\n---\n\n# Recipe " 마커 앞을 갈라 붙인다 — 마커가 없으면 끝에
# 붙으므로 표 머리까지만 남기면 된다.
MENU_MD_HEAD_MARKER = "| --- | --- |"


def _load_init_nodes() -> dict:
    """_init/ontology.yaml 의 노드.

    출력  {node_id: {name, description}}
    규칙  _init 과 작업본이 다르면 SystemExit. 화면에서 초기화를 누르고 다시
          돌리면 됨
    제약  작업본과 다른 채로 진행하지 않는다.
          경로 생성(all_recipes)은 graph 를 거쳐 작업본 ontology.yaml 을 읽음.
          경로를 인자로 받지 않으므로 둘이 다르면 _init 이 아닌 것으로 recipe 를
          만들게 됨
    """
    if store.raw_bytes(paths.INIT_ONTOLOGY_PATH) != store.raw_bytes():
        raise SystemExit(
            "★ ontology/ontology.yaml 이 _init 과 다르다.\n"
            "  경로 생성은 작업본을 읽으므로 이대로는 _init 이 아닌 것으로 만들게 된다.\n"
            "  화면에서 초기화를 누르거나 POST /nodes/reset 을 한 뒤 다시 돌린다."
        )
    return store.nodes(paths.INIT_ONTOLOGY_PATH)


def _head(text: str, marker: str) -> str:
    """마커까지 남기고 그 뒤를 자름.

    출력  머리말 문자열. 마커가 없으면 SystemExit
    제약  손으로 쓴 머리말을 새로 짓지 않는다
    """
    head, found, _tail = text.partition(marker)
    if not found:
        raise SystemExit(f"★ 머리말 마커를 못 찾았다: {marker!r}")
    return head + found


def _current_chains(directory: Path) -> dict[str, tuple[str, ...]]:
    """지금 _init 에 있는 recipe.

    입력  recipe 디렉터리
    출력  {recipe_id: 노드 사슬}
    """
    from ontology.graph import recipe_nodes

    original = paths.RECIPES_DIR
    paths.RECIPES_DIR = directory
    try:
        return {
            path.stem: tuple(recipe_nodes(path.stem))
            for path in sorted(directory.glob("recipe_*.yaml"))
        }
    finally:
        paths.RECIPES_DIR = original


def _table(before: dict[str, tuple[str, ...]], after: list[list[str]], nodes: dict) -> None:
    """번호 대응표. GT(check_resolve · sample_picker)를 갈아끼우는 근거."""
    was = {tuple(chain): recipe_id for recipe_id, chain in before.items()}

    print()
    print("  새 번호      현재         경로")
    for index, chain in enumerate(after, start=1):
        old = was.get(tuple(chain), "(새것)")
        names = " → ".join(nodes[nid]["name"] for nid in chain)
        print(f"  recipe_{index:03d}   {old:<12} {names}")

    gone = [recipe_id for chain, recipe_id in was.items() if list(chain) not in after]
    if gone:
        print()
        print("  ★ 사라진 recipe : " + " · ".join(sorted(gone)))


def rebuild(write: bool) -> int:
    nodes = _load_init_nodes()

    every = all_recipes(nodes)
    chains = [
        chain for chain in every
        if not crosses_groups(chain) and len(chain) >= MIN_STEPS
    ]

    before = _current_chains(paths.INIT_RECIPES_DIR)
    _table(before, chains, nodes)

    # ---------------------------------------------------------- 검증
    crossing = [chain for chain in chains if crosses_groups(chain)]
    print()
    if crossing:
        print(f"  ★★★ 대상이 어긋나는 경로가 {len(crossing)}개 남았다 — 필터가 안 걸렸다")
        for chain in crossing:
            print(f"        {chain}")
    else:
        short = sum(1 for chain in every if len(chain) < MIN_STEPS)
        print(
            f"  대상이 어긋나는 것 0개 "
            f"(전체 {len(every)}개 중 {len(every) - len(chains)}개 버림"
            f" — 그중 {short}개는 {MIN_STEPS}단 미만)"
        )

    sentences = [function_for(chain, nodes) for chain in chains]
    # menu.yaml 은 "  recipe_00N:\n    function: <문장>\n" 한 덩어리씩이다.
    body = sum(len(f"  recipe_{i:03d}:\n    function: {s}\n") for i, s in enumerate(sentences, 1))
    head = len(_head(paths.INIT_MENU_YAML_PATH.read_text(encoding="utf-8"), MENU_YAML_HEAD_MARKER))
    size = head + body + len(sentences)  # 덩어리 사이 빈 줄
    print(f"  menu.yaml 약 {size}자 / MENU_BUDGET {MENU_BUDGET} — 여유 {MENU_BUDGET - size}자")

    if not write:
        print()
        print("  미리보기다. 실제로 쓰려면 --write 를 붙인다.")
        return 0

    # ---------------------------------------------------------- 쓰기
    shutil.rmtree(paths.INIT_RECIPES_DIR)
    paths.INIT_RECIPES_DIR.mkdir(parents=True)
    recipe_ids = append_recipes(chains, nodes, directory=paths.INIT_RECIPES_DIR)

    for path, marker in (
        (paths.INIT_MENU_YAML_PATH, MENU_YAML_HEAD_MARKER),
        (paths.INIT_MENU_MD_PATH, MENU_MD_HEAD_MARKER),
    ):
        # append_menu 는 이어 붙이는 함수라 빈 파일에 못 쓴다. 머리말만 남긴다.
        path.write_text(
            _head(path.read_text(encoding="utf-8"), marker) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    append_menu(
        recipe_ids,
        chains,
        nodes,
        yaml_path=paths.INIT_MENU_YAML_PATH,
        md_path=paths.INIT_MENU_MD_PATH,
    )

    written = len(paths.INIT_MENU_YAML_PATH.read_text(encoding="utf-8"))
    print()
    print(f"  menu.yaml 실측 {written}자 — 여유 {MENU_BUDGET - written}자")
    print(f"  썼다 : recipe {len(recipe_ids)}개 · menu.yaml · menu.md  (모두 _init)")
    print("  화면에서 초기화를 눌러야 작업본에 반영된다.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="_init 의 recipe 와 menu 를 온톨로지에서 다시 만든다."
    )
    parser.add_argument("--write", action="store_true", help="실제로 쓴다 (기본은 미리보기)")
    args = parser.parse_args()
    return rebuild(args.write)


if __name__ == "__main__":
    sys.exit(main())
