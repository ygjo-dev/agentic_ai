"""recipe 의 경로와 온톨로지 tool 의 입력 배선이 서로 맞는지 세는 도구.

개편에서 배선을 노드별에서 간선별로 다시 적을 때 선언과 배선이 맞는지를 계속
세야 했는데 그 눈이 없어서 13개를 놓쳤다. NOTES.md 2026-08-23 참고. 입력 배선이
온톨로지의 tool 로 옮겨간 뒤에도 같은 세 가지를 센다.

    python dev/tools/check_wiring.py
    python dev/tools/check_wiring.py --quiet

**서버도 LLM 도 쓰지 않는다.** 파일만 읽는 순수 계산이라 언제든 돌려도 된다.
dev/tools/check_resolve.py · dev/tools/probe_tools.py 와 같은 성격이라 그 파일들의
짜임새를 따른다 — 파일 하나에 담고 저장소의 다른 곳을 건드리지 않는다.

**규칙을 복사하지 않는다.** 실행 계획과 tool 해석은 execution/step_service 에서
그대로 가져온다. 여기에 옮겨 적으면 온톨로지를 고칠 때 두 곳이 조용히 어긋나고,
그러면 이 도구가 세는 숫자를 믿을 수 없게 된다.

세는 규칙은 셋이다.

    A  첫 도구 단계인데 input 이 앞 단계 참조만 쓴다        발화 · 화면 값을 버린다
    B  앞 도구 단계가 있는데 input 이 발화 인자만 쓴다       앞 단계 결과를 안 쓴다
    C  hasInput 에는 있는데 tool.parameters 가 안 가리킨다   그 자리는 부를 수 없다

A 와 B 는 실행 수단이 다 있는 recipe 만 본다(unwired 가 빈 것). 없는 recipe 는
execute_service.run 이 도구를 하나도 안 부르므로 맞고 틀리고를 따질 것이 없다.

C 는 recipe 를 안 본다. 온톨로지의 hasInput 선언과 tool.parameters 를 맞대는 것뿐이다.
**C 가 0 이어야 하는 것은 아니다.** 응답 모양을 못 본 자리는 지어내지 않고 비워
두는 것이 규칙이라(온톨로지의 web_fetch 곁 주석) 비어 있는 이유가 적혀 있으면 그것이
맞다. A 와 B 는 0 이어야 한다.

tool 과 배선표 잔여분(headline · legacy result 경로)이 서로 맞는지도 맨 위에 찍는다
(step_service.check_bindings).

**테스트를 두지 않는다.** tools/ 는 재는 도구이고 제품 경로가 아니다. 이 파일이
틀리면 NOTES.md 에 적힌 숫자가 안 나와 바로 드러난다.
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.api.services.streamlit import screen_service  # noqa: E402
from execution.step_service import (  # noqa: E402
    binding_of,
    bound_inputs,
    check_bindings,
    plan,
    unwired,
)
from ontology.graph import inputs_of, is_executable  # noqa: E402
from ontology.store import nodes as all_nodes  # noqa: E402

# 표에 찍는 부류 셋. NOTES.md 「배선이 온톨로지의 선언을 반만 따른다」의 이름과
# 같아야 한다 — 표를 옮겨 적을 때 사람이 짝을 못 찾는다.
DISCARDS_SPOKEN = "A"
IGNORES_PREVIOUS = "B"
UNDECLARED_WIRING = "C"

# 계획에 심어 보는 발화 인자. 사람이 말할 수 없는 글자로 짓는다.
PROBE = "\x00check-wiring\x00"

# vendor 가 앞 단계 결과로 푸는 참조. "$s1.location" 같은 꼴이다.
PREVIOUS_REFERENCE = re.compile(r"^\$s\d+(\.|$)")


# ── 한글 폭 ──────────────────────────────────────────────────────────
# 한글은 폭이 2 라 ljust 로는 표가 어긋난다. 표 라이브러리를 쓰지 않으므로
# 여기서 직접 센다. dev/tools/check_resolve.py 와 같은 방식이다.


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


# ── 세기 ────────────────────────────────────────────────────────────


SPOKEN = "spoken"
PREVIOUS = "previous"


def marks_in(value) -> set:
    """input 한 벌이 쓰는 값의 출처.

    입력  실행 계획이 만든 step 의 input. dict · list · 스칼라가 섞여 있음
    출력  {SPOKEN, PREVIOUS} 의 부분집합
    규칙  중첩된 dict · list 안까지 봄
          발화 인자는 PROBE 가 그대로 들어간 칸임
          앞 단계 참조는 "$s<번호>" 로 시작하는 문자열임
    제약  값이 무엇인지 판정하지 않는다. 어느 출처를 썼는지만 셈
    """
    if isinstance(value, dict):
        return set().union(*(marks_in(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(marks_in(item) for item in value)) if value else set()
    if value == PROBE:
        return {SPOKEN}
    if isinstance(value, str) and PREVIOUS_REFERENCE.match(value):
        return {PREVIOUS}
    return set()


def undeclared() -> list:
    """hasInput 에는 있는데 tool.parameters 가 안 가리키는 (노드 × 받는 타입).

    출력  [{kind, node_id, name, type_id, type_name, tool}, ...]
    규칙  실행 노드만 봄. 받는 것이 없는 노드는 셀 것이 없음
          tool 이 아예 없는 노드는 모든 hasInput 이 여기 들어옴
    """
    nodes = all_nodes()
    found = []
    for node_id in nodes:
        if not is_executable(node_id):
            continue
        bound = bound_inputs(node_id)
        binding = binding_of(node_id)
        for type_id in inputs_of(node_id):
            if type_id in bound:
                continue
            found.append(
                {
                    "kind": UNDECLARED_WIRING,
                    "node_id": node_id,
                    "name": nodes[node_id]["name"],
                    "type_id": type_id,
                    "type_name": nodes[type_id]["name"],
                    "tool": binding["id"] if binding else "",
                }
            )
    return found


def findings() -> tuple:
    """입력 배선이 선언과 어긋난 자리 전부.

    출력  (recipe 총수, 실행 수단이 다 있는 recipe 수, [어긋난 자리, ...])
          어긋난 자리는 {kind, recipe_id, previous, node_id, tool}
          kind 는 DISCARDS_SPOKEN 또는 IGNORES_PREVIOUS. previous 는 앞 도구
          노드 id 이고 첫 단계면 None
    규칙  unwired 가 빈 recipe 만 봄
          실행 계획(step_service.plan)을 PROBE 인자로 만들어 step 마다 봄.
          builtin 은 뒤 단계에 얹혀 step 이 없고 지도 명령은 step 이 아님
          첫 단계가 앞 단계 참조만 쓰면 A. 발화 · 화면 값이 갈 곳이 없음
          앞 단계가 있는데 발화 인자만 쓰면 B. 앞 단계 결과가 버려짐
          둘 다 쓰거나 둘 다 안 쓰는 것은 세지 않음
    제약  무엇이 맞는 배선인지 정하지 않는다. 어긋난 자리를 셀 뿐이고 어느
          쪽으로 고칠지는 사람이 정한다
    """
    recipe_ids = screen_service.recipe_ids()
    found, wired = [], 0

    for recipe_id in recipe_ids:
        if unwired(recipe_id):
            continue
        wired += 1

        result = plan(recipe_id, PROBE)
        previous = None
        for node_id, step in zip(result["nodes"], result["steps"]):
            marks = marks_in(step["input"])

            kind = None
            if previous is None:
                if PREVIOUS in marks and SPOKEN not in marks:
                    kind = DISCARDS_SPOKEN
            elif SPOKEN in marks and PREVIOUS not in marks:
                kind = IGNORES_PREVIOUS

            if kind:
                found.append(
                    {
                        "kind": kind,
                        "recipe_id": recipe_id,
                        "previous": previous,
                        "node_id": node_id,
                        "tool": f"{step['server_id']}/{step['tool']}",
                    }
                )
            previous = node_id

    return len(recipe_ids), wired, found


# ── 표 ──────────────────────────────────────────────────────────────

RECIPE_WIDTH = 14
NODE_WIDTH = 52


def _short(recipe_id: str) -> str:
    """recipe_012 -> 012. 합계 줄에 번호만 늘어놓을 때 씀."""
    return recipe_id[len("recipe_"):] if recipe_id.startswith("recipe_") else recipe_id


def _print_discards(rows: list) -> None:
    """A 표. 첫 도구 단계가 앞 단계 참조만 쓰는 자리."""
    print()
    print(f"  A  발화 · 화면 값을 버린다 ({len(rows)}개)")
    print("  " + _pad("recipe", RECIPE_WIDTH) + _pad("첫 도구 노드", NODE_WIDTH) + "도구")
    for row in rows:
        print("  " + _pad(row["recipe_id"], RECIPE_WIDTH) + _pad(row["node_id"], NODE_WIDTH) + row["tool"])


def _print_ignores(rows: list) -> None:
    """B 표. 앞 도구 단계가 있는데 발화 인자만 쓰는 자리."""
    print()
    print(f"  B  앞 단계 결과를 안 쓴다 ({len(rows)}개)")
    print("  " + _pad("recipe", RECIPE_WIDTH) + _pad("앞 노드 -> 노드", NODE_WIDTH) + "도구")
    for row in rows:
        print(
            "  "
            + _pad(row["recipe_id"], RECIPE_WIDTH)
            + _pad(f"{row['previous']} -> {row['node_id']}", NODE_WIDTH)
            + row["tool"]
        )


def _print_undeclared(rows: list) -> None:
    """C 표. hasInput 에는 있는데 tool.parameters 가 안 가리키는 자리."""
    print()
    print(f"  C  선언에는 있는데 입력 배선이 없다 ({len(rows)}개)")
    print("  " + _pad("노드 × 받는 타입", NODE_WIDTH) + "도구")
    for row in rows:
        print("  " + _pad(f"{row['node_id']} × {row['type_name']}", NODE_WIDTH) + (row["tool"] or "(tool 없음)"))


def _print_total(total: int, wired: int, found: list, missing: list, problems: list) -> None:
    """합계 한 줄. recipe 총수 · 실행 수단이 다 있는 것 · tool 수 · A · B · C."""
    discards = [row for row in found if row["kind"] == DISCARDS_SPOKEN]
    ignores = [row for row in found if row["kind"] == IGNORES_PREVIOUS]
    tools = sum(1 for node_id in all_nodes() if binding_of(node_id) is not None)
    print()
    print(
        f"  recipe {total}개 · 실행 수단이 다 있는 것 {wired}개"
        f" · tool 이 있는 노드 {tools}개"
        f" · A {len(discards)}개 · B {len(ignores)}개 · C {len(missing)}개"
        f" · tool/배선표 어긋남 {len(problems)}개"
    )
    for label, rows in ((DISCARDS_SPOKEN, discards), (IGNORES_PREVIOUS, ignores)):
        if rows:
            print(f"  {label}  " + " ".join(_short(row["recipe_id"]) for row in rows))
    if missing:
        print("  C  " + " ".join(f"{row['node_id']}×{row['type_id']}" for row in missing))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="recipe 의 경로와 온톨로지 tool 의 입력 배선이 맞는지 센다."
    )
    parser.add_argument("--quiet", action="store_true", help="표 없이 합계만")
    args = parser.parse_args()

    problems = check_bindings()
    total, wired, found = findings()
    missing = undeclared()

    if not args.quiet:
        if problems:
            print()
            print(f"  tool 과 배선표 잔여분이 어긋났다 ({len(problems)}개)")
            for problem in problems:
                print(f"    {problem}")
        discards = [row for row in found if row["kind"] == DISCARDS_SPOKEN]
        ignores = [row for row in found if row["kind"] == IGNORES_PREVIOUS]
        if discards:
            _print_discards(discards)
        if ignores:
            _print_ignores(ignores)
        if missing:
            _print_undeclared(missing)

    _print_total(total, wired, found, missing, problems)
    return 0


if __name__ == "__main__":
    sys.exit(main())
