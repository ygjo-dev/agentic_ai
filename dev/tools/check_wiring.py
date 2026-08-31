"""recipe 의 경로와 STEP_OF 의 배선이 서로 맞는지 세는 도구.

개편에서 배선을 노드별에서 간선별로 다시 적는다. 그때 선언과 배선이 맞는지를
계속 세야 하는데 그 눈이 없어서 13개를 놓쳤다. NOTES.md 2026-08-23 참고.

    python dev/tools/check_wiring.py
    python dev/tools/check_wiring.py --quiet

**서버도 LLM 도 쓰지 않는다.** 파일만 읽는 순수 계산이라 언제든 돌려도 된다.
dev/tools/check_resolve.py · dev/tools/probe_tools.py 와 같은 성격이라 그 파일들의
짜임새를 따른다 — 파일 하나에 담고 저장소의 다른 곳을 건드리지 않는다.

**표를 복사하지 않는다.** STEP_OF 와 unwired 를 app/api/services/step_service
에서 그대로 import 한다. 여기에 옮겨 적으면 배선을 고칠 때 두 곳이 조용히
어긋나고, 그러면 이 도구가 세는 숫자를 믿을 수 없게 된다. @arg · $prev 도
문자열로 박지 않고 SPOKEN_VALUE · PREVIOUS_STEP 을 쓴다.

세는 규칙은 셋이다.

    A  첫 실행 노드인데 input 이 $prev 만 쓴다      발화 인자를 버린다
    B  앞 실행 노드가 있는데 input 이 @arg 만 쓴다  앞 단계 결과를 안 쓴다
    C  hasInput 에는 있는데 STEP_OF 에 줄이 없다    그 자리는 부를 수 없다

A 와 B 는 배선이 다 있는 recipe 만 본다(unwired 가 빈 것). 배선이 없는 recipe 는
execute_service.run 이 도구를 하나도 안 부르므로 맞고 틀리고를 따질 것이 없다.

C 는 recipe 를 안 본다. 온톨로지의 hasInput 선언과 STEP_OF 의 키를 맞대는 것뿐이다.
**C 가 0 이어야 하는 것은 아니다.** 응답 모양을 못 본 자리는 지어내지 않고 비워
두는 것이 규칙이라(STEP_OF 아래 주석) 비어 있는 이유가 적혀 있으면 그것이 맞다.
A 와 B 는 0 이어야 한다.

**테스트를 두지 않는다.** tools/ 는 재는 도구이고 제품 경로가 아니다. 이 파일이
틀리면 NOTES.md 에 적힌 숫자가 안 나와 바로 드러난다.
"""

import argparse
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.api.services import ontology_service  # noqa: E402
from app.api.services.step_service import (  # noqa: E402
    PREVIOUS_STEP,
    SPOKEN_VALUE,
    STEP_OF,
    TOOL_OF,
    input_of,
    unwired,
    wiring_at,
)
from ontology.graph import inputs_of, is_executable  # noqa: E402
from ontology.store import nodes as all_nodes  # noqa: E402

# 표에 찍는 부류 셋. NOTES.md 「배선이 온톨로지의 선언을 반만 따른다」의 이름과
# 같아야 한다 — 표를 옮겨 적을 때 사람이 짝을 못 찾는다.
DISCARDS_SPOKEN = "A"
IGNORES_PREVIOUS = "B"
UNDECLARED_WIRING = "C"


# ── 한글 폭 ──────────────────────────────────────────────────────────
# 한글은 폭이 2 라 ljust 로는 표가 어긋난다. 표 라이브러리를 쓰지 않으므로
# 여기서 직접 센다. dev/tools/check_resolve.py 와 같은 방식이다.


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


# ── 세기 ────────────────────────────────────────────────────────────


def marks_in(value) -> set:
    """input 한 벌이 쓰는 표시.

    입력  STEP_OF 한 줄의 input. dict · list · 스칼라가 섞여 있음
    출력  {SPOKEN_VALUE, PREVIOUS_STEP} 의 부분집합
    규칙  중첩된 dict · list 안까지 봄. step_service._filled 이 값을 채우는
          범위와 같아야 함
          "$prev.location" 처럼 뒤에 경로가 붙은 것도 $prev 로 셈
          "@arg" 는 어절 전체가 표시일 때만 셈. _filled 이 그렇게 바꿈
    제약  값이 무엇인지 판정하지 않는다. 어느 표시를 썼는지만 셈
    """
    if isinstance(value, dict):
        return set().union(*(marks_in(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(marks_in(item) for item in value)) if value else set()
    if value == SPOKEN_VALUE:
        return {SPOKEN_VALUE}
    if isinstance(value, str) and value.startswith(PREVIOUS_STEP):
        return {PREVIOUS_STEP}
    return set()


def wired_chain(recipe_id: str) -> list:
    """recipe 한 벌에서 실제로 도구를 부르는 노드만. 그 자리에서 고른 배선까지.

    입력  recipe id
    출력  [{node_id, name, wiring}, ...] 경로 순서
    규칙  step_service.plan 이 step 을 만드는 조건과 같음. 앞 노드가 건네는
          타입으로 배선 줄을 고르고 맞는 줄이 없으면 빠짐
          데이터 노드(말한 장소)는 부를 것이 없어 빠짐
    제약  배선을 고르는 규칙을 여기 옮겨 적지 않는다.
          step_service.wiring_at 을 부른다. 옮겨 적으면 두 곳이 어긋남
    """
    chain, source_id = [], None
    for entry in ontology_service.path_of(recipe_id):
        node_id = entry["node_id"]
        wiring = wiring_at(node_id, source_id) if source_id is not None else None
        source_id = node_id
        if wiring is not None:
            chain.append({**entry, "wiring": wiring})
    return chain


def undeclared() -> list:
    """hasInput 에는 있는데 STEP_OF 에 줄이 없는 (노드 × 받는 타입).

    출력  [{kind, node_id, name, type_id, type_name, tool}, ...]
    규칙  실행 노드만 봄. 받는 것이 없는 노드는 셀 것이 없음
          도구 이름은 TOOL_OF 가 앎. 그것조차 없으면 빈 문자열
    """
    nodes = all_nodes()
    found = []
    for node_id in nodes:
        if not is_executable(node_id):
            continue
        for type_id in inputs_of(node_id):
            if (node_id, type_id) in STEP_OF:
                continue
            found.append(
                {
                    "kind": UNDECLARED_WIRING,
                    "node_id": node_id,
                    "name": nodes[node_id]["name"],
                    "type_id": type_id,
                    "type_name": nodes[type_id]["name"],
                    "tool": (TOOL_OF.get(node_id) or {}).get("tool", ""),
                }
            )
    return found


def findings() -> tuple:
    """배선이 선언과 어긋난 자리 전부.

    출력  (recipe 총수, 배선이 다 있는 recipe 수, [어긋난 자리, ...])
          어긋난 자리는 {kind, recipe_id, previous, node_id, name, tool}
          kind 는 DISCARDS_SPOKEN 또는 IGNORES_PREVIOUS. previous 는 앞 실행
          노드 id 이고 첫 노드면 None
    규칙  unwired 가 빈 recipe 만 봄. 배선이 없는 recipe 는 execute_service 가
          도구를 하나도 안 부름
          첫 실행 노드가 $prev 만 쓰면 A. 발화에서 온 값이 갈 곳이 없음
          앞 실행 노드가 있는데 @arg 만 쓰면 B. 앞 단계 결과가 버려짐
          둘 다 쓰거나 둘 다 안 쓰는 것은 세지 않음
          첫 자리인지에 따라 input 이 갈리는 줄이 있으므로 input_of 로 고름
    제약  무엇이 맞는 배선인지 정하지 않는다. 어긋난 자리를 셀 뿐이고 어느
          쪽으로 고칠지는 사람이 정한다
    """
    recipe_ids = ontology_service.recipe_ids()
    found, wired = [], 0

    for recipe_id in recipe_ids:
        if unwired(recipe_id):
            continue
        wired += 1

        previous = None
        for entry in wired_chain(recipe_id):
            node_id = entry["node_id"]
            wiring = entry["wiring"]
            marks = marks_in(input_of(wiring, first=previous is None))

            kind = None
            if previous is None:
                if PREVIOUS_STEP in marks and SPOKEN_VALUE not in marks:
                    kind = DISCARDS_SPOKEN
            elif SPOKEN_VALUE in marks and PREVIOUS_STEP not in marks:
                kind = IGNORES_PREVIOUS

            if kind:
                found.append(
                    {
                        "kind": kind,
                        "recipe_id": recipe_id,
                        "previous": previous,
                        "node_id": node_id,
                        "name": entry["name"],
                        "tool": TOOL_OF[node_id]["tool"],
                    }
                )
            previous = node_id

    return len(recipe_ids), wired, found


# ── 표 ──────────────────────────────────────────────────────────────

RECIPE_WIDTH = 14
NODE_WIDTH = 52
TOOL_WIDTH = 40


def _short(recipe_id: str) -> str:
    """recipe_012 -> 012. 합계 줄에 번호만 늘어놓을 때 씀."""
    return recipe_id[len("recipe_"):] if recipe_id.startswith("recipe_") else recipe_id


def _print_discards(rows: list) -> None:
    """A 표. 첫 실행 노드가 $prev 만 쓰는 자리."""
    print()
    print(f"  A  발화 인자를 버린다 ({len(rows)}개)")
    print(
        "  "
        + _pad("recipe", RECIPE_WIDTH)
        + _pad("첫 실행 노드", NODE_WIDTH)
        + "도구"
    )
    for row in rows:
        print(
            "  "
            + _pad(row["recipe_id"], RECIPE_WIDTH)
            + _pad(row["node_id"], NODE_WIDTH)
            + row["tool"]
        )


def _print_ignores(rows: list) -> None:
    """B 표. 앞 실행 노드가 있는데 @arg 만 쓰는 자리."""
    print()
    print(f"  B  앞 단계 결과를 안 쓴다 ({len(rows)}개)")
    print(
        "  "
        + _pad("recipe", RECIPE_WIDTH)
        + _pad("앞 노드 -> 노드", NODE_WIDTH)
        + "도구"
    )
    for row in rows:
        print(
            "  "
            + _pad(row["recipe_id"], RECIPE_WIDTH)
            + _pad(f"{row['previous']} -> {row['node_id']}", NODE_WIDTH)
            + row["tool"]
        )


def _print_undeclared(rows: list) -> None:
    """C 표. hasInput 에는 있는데 STEP_OF 에 줄이 없는 자리."""
    print()
    print(f"  C  선언에는 있는데 배선이 없다 ({len(rows)}개)")
    print("  " + _pad("노드 × 받는 타입", NODE_WIDTH) + "도구")
    for row in rows:
        print(
            "  "
            + _pad(f"{row['node_id']} × {row['type_name']}", NODE_WIDTH)
            + row["tool"]
        )


def _print_total(total: int, wired: int, found: list, missing: list) -> None:
    """합계 한 줄. recipe 총수 · 배선이 다 있는 것 · 배선 줄 수 · A · B · C."""
    discards = [row for row in found if row["kind"] == DISCARDS_SPOKEN]
    ignores = [row for row in found if row["kind"] == IGNORES_PREVIOUS]
    print()
    print(
        f"  recipe {total}개 · 배선이 다 있는 것 {wired}개"
        f" · STEP_OF {len(STEP_OF)}줄"
        f" · A {len(discards)}개 · B {len(ignores)}개 · C {len(missing)}개"
    )
    for label, rows in ((DISCARDS_SPOKEN, discards), (IGNORES_PREVIOUS, ignores)):
        if rows:
            print(f"  {label}  " + " ".join(_short(row["recipe_id"]) for row in rows))
    if missing:
        print("  C  " + " ".join(f"{row['node_id']}×{row['type_id']}" for row in missing))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="recipe 의 경로와 STEP_OF 의 배선이 맞는지 센다."
    )
    parser.add_argument("--quiet", action="store_true", help="표 없이 합계만")
    args = parser.parse_args()

    total, wired, found = findings()
    missing = undeclared()

    if not args.quiet:
        discards = [row for row in found if row["kind"] == DISCARDS_SPOKEN]
        ignores = [row for row in found if row["kind"] == IGNORES_PREVIOUS]
        if discards:
            _print_discards(discards)
        if ignores:
            _print_ignores(ignores)
        if missing:
            _print_undeclared(missing)

    _print_total(total, wired, found, missing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
