"""정답표의 이름 있는 값(expected.spoken)을 기대 recipe 의 Recipe.execution 과 맞대는 감사표.

    python dev/evaluation/spoken_audit.py            발화마다 한 줄 (markdown 표)
    python dev/evaluation/spoken_audit.py --json     같은 내용을 JSON 으로

발화마다 기대 recipe 의 게시된 execution 이 `{from: spoken.<이름>}` 으로 **실제로 읽는 칸**을
뽑고, 정답표가 채점하는 칸과 맞댄다.

    missing   execution 이 읽는데 정답표가 안 채점하는 칸. 채점할지는 사람이 정한다
              (말하지 않은 것이 정상인 자리 · 뜻이 애매한 자리가 있다)
    extra     정답표가 채점하는데 기대 recipe 가 안 읽는 칸. 맞혀도 틀려도 실행이 안 바뀐다

이름 목록을 두지 않는다. 꼴이 `spoken.<이름>` 이면 다 같은 길로 뽑는다.
정답표도 recipe 도 고치지 않는다. 읽기만 한다.

integrity 는 정답표 한 벌이 서 있을 조건을 본다 (묶음 · 기대 recipe · 채점 칸 · 발화가 prompt 로
새지 않았나 · 범위 밖은 NO_MATCH 뿐인가). 판 2 정답표에는 recipe 마다 발화 수 하한이 더 걸린다.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dev.evaluation import suite as suite_module  # noqa: E402
from execution import workflow_materializer  # noqa: E402

# 조건 칸. 있으면 그 참조는 인자 모양에 따라 빠질 수 있다.
CONDITION_KEYS = ("if_endswith", "unless_endswith")

# 판 2 정답표가 받아들인 recipe 마다 가져야 하는 범위 안 발화 수.
MIN_UTTERANCES_PER_RECIPE = 5

# 화면 문맥 이름 -> 그 문맥에서 시작하는 묶음. 둘 다 없으면 말한 것.
CONTEXT_GROUPS = (("point", "picked_point"), ("map_extent", "view_extent"))

# prompt 에서 따옴표로 인용한 예시 중 발화에 들어가면 안 되는 것의 최소 길이.
# 짧은 것(「보여줘」 · 「여기」)은 어느 발화에나 있는 말이라 새는 것이 아니다.
LEAK_MIN_LENGTH = 6


def spoken_refs(execution: dict) -> list[dict]:
    """execution 이 읽는 spoken 참조. [{name, at, use}] execution 안 차례.

    출력  use 는 required · default=<값> · <조건>=<어미> 중 하나
    규칙  {from: spoken.<이름>} 꼴인 dict 만 참조로 셈. 중첩 dict · list 를 끝까지 훑음
          default 가 있으면 안 말해도 실행이 기본값으로 감. 없으면 값이 있어야 부름
          조건(if_endswith · unless_endswith)이 있으면 그 참조는 인자 모양에 따라 빠짐
    """
    found = []

    def walk(node, at):
        if isinstance(node, dict):
            origin = node.get("from")
            if isinstance(origin, str) and origin.startswith(workflow_materializer.SPOKEN_SOURCE):
                name = origin[len(workflow_materializer.SPOKEN_SOURCE):]
                condition = next((key for key in CONDITION_KEYS if key in node), None)
                if condition:
                    use = f"{condition}={node[condition]}"
                elif "default" in node:
                    use = f"default={json.dumps(node['default'], ensure_ascii=False)}"
                else:
                    use = "required"
                found.append({"name": name, "at": at, "use": use})
            for key, value in node.items():
                walk(value, f"{at}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{at}[{index}]")

    walk(execution.get("workflow") or [], "workflow")
    return found


def audit(suite: dict) -> list[dict]:
    """발화마다 한 줄. 정답표 차례.

    출력  [{id, group, utterance, recipe_ids, refs, consumed, gt, missing, extra}]. 범위 안 case 만
          consumed 는 기대 recipe 모두가 읽는 이름. 기대 recipe 가 여럿이면 교집합
          missing = consumed - gt 칸 · extra = gt 칸 - consumed. 이름 차례
    규칙  recipe 파일이 없으면 refs 가 비고 consumed 도 빔
    제약  정답표 · recipe 를 고치지 않는다
    """
    rows = []
    for case in suite["cases"]:
        if not suite_module.in_scope(case):
            continue
        expected = case["expected"]
        refs, consumed = {}, None
        for recipe_id in expected["recipe_ids"]:
            execution = workflow_materializer.load(recipe_id)
            found = spoken_refs(execution) if execution else []
            refs[recipe_id] = found
            names = {ref["name"] for ref in found}
            consumed = names if consumed is None else consumed & names
        consumed = consumed or set()
        gt = dict(expected.get("spoken") or {})
        rows.append({
            "id": case["id"],
            "group": case["group"],
            "utterance": case["utterance"],
            "recipe_ids": list(expected["recipe_ids"]),
            "refs": refs,
            "consumed": sorted(consumed),
            "gt": gt,
            "missing": sorted(consumed - set(gt)),
            "extra": sorted(set(gt) - consumed),
        })
    return rows


def _mark(value) -> str:
    return "null" if value is None else json.dumps(value, ensure_ascii=False)


def markdown(rows: list[dict]) -> str:
    """사람이 읽는 표 한 벌."""
    lines = [
        "| case | utterance | recipe | execution spoken refs | GT spoken | missing | extra |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        refs = "; ".join(
            f"{ref['name']}({ref['use']})" for found in row["refs"].values() for ref in found
        ) or "-"
        gt = ", ".join(f"{name}={_mark(value)}" for name, value in row["gt"].items()) or "-"
        lines.append(
            f"| {row['id']} | {row['utterance']} | {','.join(row['recipe_ids'])} | {refs} | {gt} | "
            f"{','.join(row['missing']) or '-'} | {','.join(row['extra']) or '-'} |"
        )
    return "\n".join(lines)


def expected_group(execution: dict) -> str:
    """recipe 가 속할 묶음 id. execution 이 읽는 화면 문맥이 정함."""
    needs = execution.get("context_needs") or {}
    return next((group for name, group in CONTEXT_GROUPS if name in needs), suite_module.GROUP_IDS[0])


def _leak_phrases() -> set[str]:
    """발화에 옮기면 안 되는 prompt 속 글. menu example · prompt 의 따옴표 예시(띄어쓰기 있고 LEAK_MIN_LENGTH 이상)."""
    import yaml

    import paths
    from llm_engine.role_config import RESOLVE, get_role_config

    phrases = set()
    menu = yaml.safe_load(paths.MENU_YAML_PATH.read_text(encoding="utf-8")) or {}
    for entry in (menu.get("recipes") or {}).values():
        if isinstance(entry, dict) and entry.get("example"):
            phrases.add(entry["example"])
    prompt = get_role_config(RESOLVE).prompt
    for quoted in re.findall(r'"([^"\n]+)"', prompt):
        if " " in quoted and len(quoted) >= LEAK_MIN_LENGTH:
            phrases.add(quoted)
    return phrases


def integrity(suite: dict, *, anchor: dict | None = None) -> list[str]:
    """정답표 한 벌이 서 있을 조건 중 깨진 것. 비면 통과.

    입력  anchor 는 발화가 겹치면 안 되는 다른 정답표(FULL48). 없으면 안 봄
    규칙  기대 recipe 파일이 있음. 범위 안 case 의 묶음이 그 recipe 의 화면 문맥과 맞음
          채점 칸이 기대 recipe 가 읽는 칸과 같음 (extra · missing 둘 다 없음)
          발화에 recipe id · 도구 이름이 없음. 판 2 면 menu example · prompt 예시 문장도 없음
          (판 1 인 FULL48 은 얼린 자라 이 검사보다 먼저 지은 발화가 그대로 있음)
          범위 밖 결과 이름이 resolve 응답 schema 의 status enum 에 있음. 범위 밖은 전부 [NO_MATCH]
          (되묻기 · 값 부족이 정답인 발화는 범위 밖이 아님)
          판 2 면 받아들인 recipe 전부가 MIN_UTTERANCES_PER_RECIPE 이상. 범위 밖 갈래마다 하나 이상
          anchor 가 있으면 그 발화와 글자까지 같은 발화가 없음
    제약  정답표 · recipe 를 고치지 않는다
    """
    import paths
    from llm_engine.role_config import RESOLVE, get_role_config

    problems = []
    accepted = sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))
    tools = set()
    for recipe_id in accepted:
        for step in (workflow_materializer.load(recipe_id) or {}).get("workflow") or []:
            tools.update(value for value in (step.get("tool"), step.get("command")) if value)
    leaks = _leak_phrases()

    for case in suite["cases"]:
        text = case["utterance"]
        if "recipe" in text.lower() or any(tool in text for tool in tools):
            problems.append(f"{case['id']}: 발화에 recipe id · 도구 이름이 있음")
        if suite.get("version", 1) >= 2 and any(phrase in text for phrase in leaks):
            problems.append(f"{case['id']}: 발화가 prompt 예시 문장을 옮김")
        if not suite_module.in_scope(case):
            continue
        for recipe_id in case["expected"]["recipe_ids"]:
            execution = workflow_materializer.load(recipe_id)
            if execution is None:
                problems.append(f"{case['id']}: 없는 recipe {recipe_id}")
            elif expected_group(execution) != case["group"]:
                problems.append(f"{case['id']}: {recipe_id} 는 {expected_group(execution)} 묶음인데 {case['group']}")
    if problems:
        return problems

    for row in audit(suite):
        if row["extra"]:
            problems.append(f"{row['id']}: 기대 recipe 가 안 읽는 칸을 채점함 {row['extra']}")
        if row["missing"]:
            problems.append(f"{row['id']}: 기대 recipe 가 읽는 칸을 안 채점함 {row['missing']}")

    known = set(get_role_config(RESOLVE).response_schema["properties"]["status"]["enum"])
    unknown = set(suite_module.OOS_OUTCOMES) - known
    if unknown:
        problems.append(f"범위 밖 결과 이름이 resolve status 에 없음 {sorted(unknown)}")
    for case in suite["cases"]:
        if not suite_module.in_scope(case) and case["expected"]["outcomes"] != ["NO_MATCH"]:
            problems.append(f"{case['id']}: 범위 밖인데 NO_MATCH 말고 {case['expected']['outcomes']} 를 받아들임")

    if suite.get("version", 1) >= 2:
        per_recipe = Counter(
            case["expected"]["recipe_ids"][0] for case in suite["cases"] if suite_module.in_scope(case)
        )
        thin = {recipe_id: per_recipe.get(recipe_id, 0) for recipe_id in accepted
                if per_recipe.get(recipe_id, 0) < MIN_UTTERANCES_PER_RECIPE}
        if thin:
            problems.append(f"발화가 {MIN_UTTERANCES_PER_RECIPE} 개 미만인 recipe {thin}")
        categories = {case["expected"]["category"] for case in suite["cases"] if not suite_module.in_scope(case)}
        if categories != set(suite_module.OOS_CATEGORIES):
            problems.append(f"범위 밖 갈래가 빠짐 {sorted(set(suite_module.OOS_CATEGORIES) - categories)}")

    if anchor is not None:
        same = {case["utterance"] for case in suite["cases"]} & {case["utterance"] for case in anchor["cases"]}
        if same:
            problems.append(f"기준 정답표와 같은 발화 {sorted(same)}")
    return problems


def _selfcheck() -> None:
    """고를 수 있는 정답표 전부가 integrity 를 통과하나. 틀리면 죽는다.

    규칙  suite.DATASETS 의 정답표를 다 읽음. FULL48 이 아닌 것은 FULL48 과 발화가 안 겹쳐야 함
          채점 칸이 기대 recipe 가 읽는 칸과 같아야 함. 안 읽는 칸을 채점하면 맞혀도 틀려도 실행이 안 바뀜
          spoken_refs 가 조건 · 기본값 · 필수를 가르는지 가짜 execution 으로 봄
    """
    anchor = suite_module.load()
    for entry in suite_module.datasets():
        loaded = suite_module.load(entry["path"])
        problems = integrity(loaded, anchor=None if entry["path"] == suite_module.SUITE_PATH else anchor)
        assert not problems, (entry["id"], problems)

    fake = {"workflow": [{"input": {
        "a": {"from": "spoken.argument"},
        "b": {"from": "spoken.argument", "unless_endswith": "선"},
        "c": [{"from": "spoken.future_name", "default": [30]}],
        "d": {"from": "context.point.lon"},
    }}]}
    assert [(ref["name"], ref["use"]) for ref in spoken_refs(fake)] == [
        ("argument", "required"),
        ("argument", "unless_endswith=선"),
        ("future_name", "default=[30]"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="정답표의 채점 칸을 Recipe.execution 이 읽는 칸과 맞댄다.")
    parser.add_argument("--suite", default=str(suite_module.SUITE_PATH), help="정답표 YAML (판 2: dev/evaluation/test_suite_v2.yaml)")
    parser.add_argument("--json", action="store_true", help="JSON 으로 찍는다")
    args = parser.parse_args()

    rows = audit(suite_module.load(Path(args.suite)))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        print(markdown(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
