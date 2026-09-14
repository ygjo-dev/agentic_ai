"""받아들인 recipe 파일에 execution 블록을 게시한다.

    python -m registration.publish            작업본   ontology/ontology.yaml -> workflows/static/recipes/
    python -m registration.publish --init     _init    ontology/_init/ontology.yaml -> workflows/static/_init/recipes/
    python -m registration.publish --check    쓰지 않는다. 다시 적어야 할 recipe 만 찍고 있으면 1

**recipe 파일의 steps 와 example 은 사람의 판정이다.** 여기는 그것을 안 고친다.
steps 의 노드 사슬을 execution/step_service.compile_execution 에 넘겨 나온 블록을
파일 끝의 execution 칸에 적을 뿐이다. 같은 온톨로지 · 같은 사슬이면 같은 글자가 나온다.

**yaml.dump 로 파일을 통째로 다시 쓰지 않는다.** 사람이 쓴 칸의 모양과 주석이
사라진다. execution 칸만 떼어 내고 새로 붙인다.

**후보는 게시하지 않는다.** 후보(registry.candidate_recipes)는 파일이 아니고, 사람이
받아들여 recipe 파일이 된 것만 여기를 지난다.

**_init 은 --init 을 줄 때만 적는다.** 코드가 저절로 _init 을 고치지 않는다. 온톨로지나
사슬을 바꿔 execution 이 낡으면 dev/tests/execution/test_published_execution.py 가 짝마다
빨개진다.

서버도 LLM 도 쓰지 않는다. 파일만 읽고 쓴다.
"""

import argparse
import contextlib
import re
import sys

import yaml

import paths
from execution import step_service

EXECUTION_KEY = "execution"

# 최상위 칸이 시작하는 줄. 들여쓰기 · 주석 · 빈 줄이 아니다.
_TOP_LEVEL = re.compile(r"^[^\s#]")


def published_text(text: str) -> str:
    """recipe 파일 원문에 지금 온톨로지로 compile 한 execution 칸을 붙인 원문.

    입력  recipe 파일 원문. execution 칸이 이미 있어도 됨
    출력  execution 칸을 떼고 파일 끝에 새로 붙인 원문
    규칙  steps 의 노드 사슬만 compile 에 넘김
          다시 읽은 execution 이 compile 한 것과 같아야 하고, execution 밖의 칸은
          원문과 같아야 함. 아니면 터짐
    제약  사람이 쓴 칸을 다시 쓰지 않는다
    """
    document = yaml.safe_load(text) or {}
    chain = [step["node"] for step in document.get("steps") or []]
    execution = step_service.compile_execution(chain)

    body = _without_execution(text).rstrip("\n") + "\n\n" + render(execution) + "\n"

    reread = yaml.safe_load(body)
    if reread.get(EXECUTION_KEY) != execution:
        raise ValueError("다시 읽은 execution 이 compile 한 것과 다르다")
    if _human_part(reread) != _human_part(document):
        raise ValueError("execution 밖의 칸이 달라졌다")
    return body


def _human_part(document: dict) -> dict:
    """execution 을 뺀 칸. 사람이 쓴 것."""
    return {key: value for key, value in document.items() if key != EXECUTION_KEY}


def _without_execution(text: str) -> str:
    """원문에서 execution 칸 한 덩어리를 뗌. 다음 최상위 칸이나 파일 끝까지."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith(EXECUTION_KEY + ":")), None)
    if start is None:
        return text
    end = next((i for i in range(start + 1, len(lines)) if _TOP_LEVEL.match(lines[i])), len(lines))
    return "\n".join(lines[:start] + lines[end:])


def _flow(value) -> str:
    """값 하나를 한 줄 YAML 로."""
    dumped = yaml.safe_dump(
        value, default_flow_style=True, allow_unicode=True, sort_keys=False, width=float("inf")
    ).rstrip("\n")
    return dumped[: -len("\n...")] if dumped.endswith("\n...") else dumped


def render(execution: dict) -> str:
    """execution 한 벌을 recipe 파일에 붙일 글로.

    규칙  칸 차례는 dict 차례 그대로. 기호 하나는 한 줄(flow)로 적음
          steps 와 같게 머리와 항목 사이에 빈 줄을 둠
    """
    lines = [f"{EXECUTION_KEY}:", "", f"  spoken_needed: {_flow(execution['spoken_needed'])}"]
    if execution.get("unwired"):
        lines += ["", f"  unwired: {_flow(execution['unwired'])}"]

    needs = execution["context_needs"]
    lines.append("")
    if needs:
        lines.append("  context_needs:")
        lines += [f"    {start}: {_flow(declaration)}" for start, declaration in needs.items()]
    else:
        lines.append("  context_needs: {}")

    lines.append("")
    if not execution["workflow"]:
        lines.append("  workflow: []")
        return "\n".join(lines)

    lines.append("  workflow:")
    for entry in execution["workflow"]:
        lines.append("")
        for index, (key, value) in enumerate(entry.items()):
            head = "    - " if index == 0 else "      "
            if key == "transform":
                lines.append(f"{head}transform:")
                lines.append(f"        id: {_flow(value['id'])}")
                lines.append(f"        node: {_flow(value['node'])}")
                lines += _block("        input", value["input"], "          ")
            elif key in ("input", "outputs"):
                lines += _block(f"{head}{key}", value, "        ")
            else:
                lines.append(f"{head}{key}: {_flow(value)}")
    return "\n".join(lines)


def _block(head: str, fields: dict, indent: str) -> list[str]:
    """칸 -> 기호 한 벌. 비었으면 {} 한 줄."""
    if not fields:
        return [f"{head}: {{}}"]
    return [f"{head}:"] + [f"{indent}{name}: {_flow(value)}" for name, value in fields.items()]


def publish(check: bool = False) -> list[str]:
    """paths.RECIPES_DIR 의 recipe 마다 execution 칸을 지금 온톨로지(paths.ONTOLOGY_PATH)로 맞춤.

    출력  다시 적은(check 면 다시 적어야 할) recipe id 목록. 번호 순
    규칙  원문이 이미 같으면 안 씀. 파일은 LF 로 씀
    """
    changed = []
    for path in sorted(paths.RECIPES_DIR.glob("recipe_*.yaml")):
        text = path.read_text(encoding="utf-8")
        wanted = published_text(text)
        if wanted == text:
            continue
        changed.append(path.stem)
        if not check:
            path.write_text(wanted, encoding="utf-8", newline="\n")
    return changed


@contextlib.contextmanager
def init_pair():
    """paths 를 잠시 _init 짝(온톨로지 · recipe)으로 돌림."""
    saved = paths.ONTOLOGY_PATH, paths.RECIPES_DIR
    paths.ONTOLOGY_PATH, paths.RECIPES_DIR = paths.INIT_ONTOLOGY_PATH, paths.INIT_RECIPES_DIR
    try:
        yield
    finally:
        paths.ONTOLOGY_PATH, paths.RECIPES_DIR = saved


def main() -> int:
    parser = argparse.ArgumentParser(description="받아들인 recipe 에 execution 블록을 게시한다.")
    parser.add_argument("--init", action="store_true", help="_init 짝을 게시한다")
    parser.add_argument("--check", action="store_true", help="쓰지 않고 낡은 recipe 만 찍는다")
    args = parser.parse_args()

    with init_pair() if args.init else contextlib.nullcontext():
        changed = publish(check=args.check)
        where = paths.RECIPES_DIR

    verb = "낡음" if args.check else "게시"
    print(f"{where}: {verb} {len(changed)}" + (f" — {' · '.join(changed)}" if changed else ""))
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
