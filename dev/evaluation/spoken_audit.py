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
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dev.evaluation import suite as suite_module  # noqa: E402
from execution import workflow_materializer  # noqa: E402

# 조건 칸. 있으면 그 참조는 인자 모양에 따라 빠질 수 있다.
CONDITION_KEYS = ("if_endswith", "unless_endswith")


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

    출력  [{id, group, utterance, recipe_ids, refs, consumed, gt, missing, extra}]
          consumed 는 기대 recipe 모두가 읽는 이름. 기대 recipe 가 여럿이면 교집합
          missing = consumed - gt 칸 · extra = gt 칸 - consumed. 이름 차례
    규칙  recipe 파일이 없으면 refs 가 비고 consumed 도 빔
    제약  정답표 · recipe 를 고치지 않는다
    """
    rows = []
    for case in suite["cases"]:
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


def _selfcheck() -> None:
    """진짜 정답표의 채점 칸이 전부 기대 recipe 가 읽는 칸인가. 틀리면 죽는다.

    규칙  extra 가 있는 발화가 없어야 함. 안 읽는 칸을 채점하면 맞혀도 틀려도 실행이 안 바뀜
          missing 은 안 봄. 채점할지는 사람이 정정표에 적는 일임
          spoken_refs 가 조건 · 기본값 · 필수를 가르는지 가짜 execution 으로 봄
    """
    rows = audit(suite_module.load())
    extra = {row["id"]: row["extra"] for row in rows if row["extra"]}
    assert not extra, f"기대 recipe 가 안 읽는 칸을 채점한다: {extra}"

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
    parser.add_argument("--suite", default=str(suite_module.SUITE_PATH), help="정답표 YAML")
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
