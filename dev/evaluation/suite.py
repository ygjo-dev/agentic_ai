"""발화 해석 정답표(evaluation suite)를 읽는 유일한 곳.

정답표는 같은 폴더의 `resolve_regression.yaml` 이다. 계기판 `dev/tools/check_resolve.py` 와
공통 runner `dev/evaluation/runner.py` 가 같은 파일을 이 모듈로 읽는다.

기대값을 여기서 고치거나 채우지 않는다. 무엇이 정답인지는 파일에 사람이 적는다.
"""

from pathlib import Path

import yaml

SUITE_PATH = Path(__file__).resolve().parent / "resolve_regression.yaml"

# 이 모듈이 읽을 줄 아는 파일 판.
SUITE_VERSION = 1

# 묶음 id 와 그 차례. 표를 찍는 차례이기도 하다.
GROUP_IDS = ("spoken", "picked_point", "view_extent")


class SuiteError(ValueError):
    """정답표 파일을 알아볼 수 없다."""


def load(path: Path | None = None) -> dict:
    """정답표 한 벌.

    입력  YAML 경로. 없으면 SUITE_PATH
    출력  읽은 dict. 아래 검사를 통과한 것만
    규칙  version 이 SUITE_VERSION
          groups 가 GROUP_IDS 차례 그대로
          case id 가 정수이고 겹치지 않음. group 이 아는 묶음임
          묶음이 id 순으로 이어짐. BASELINE_LAST 같은 「묶음의 마지막 번호」가 뜻을 가지려면 필요함
          expected.recipe_ids 가 비지 않음. expected.spoken 칸이 spoken_value_names 안에 있음
          enabled 인 case 는 expected.semantic_inputs 가 있음. 있으면 dict. 안 말한 발화는 {}
          semantic_inputs 의 이름이 semantic_catalog 에 있는지는 안 봄
          marks 가 있는 case id 를 가리킴
    제약  기대값을 고치거나 채우지 않는다.
          틀린 파일을 부분만 읽지 않는다. 표가 조용히 줄어듦
          정답 semantic 이름을 지금 구현이 내는 이름으로 거르지 않는다.
          정답표를 구현에 맞춰 낮추면 구현이 못 내는 이름이 안 보임
    """
    path = path or SUITE_PATH
    document = yaml.safe_load(path.read_text(encoding="utf-8"))

    def fail(message):
        return SuiteError(f"{path.name}: {message}")

    if not isinstance(document, dict) or document.get("version") != SUITE_VERSION:
        raise fail(f"version 이 {SUITE_VERSION} 이 아니다")
    if tuple(group.get("id") for group in document.get("groups") or []) != GROUP_IDS:
        raise fail(f"groups 는 {list(GROUP_IDS)} 차례다")

    names = set(document.get("spoken_value_names") or [])
    cases = document.get("cases") or []
    if not cases:
        raise fail("cases 가 비었다")

    seen = set()
    order = []
    for case in cases:
        number = case.get("id")
        if not isinstance(number, int) or number in seen:
            raise fail(f"case id 가 정수가 아니거나 겹친다: {number!r}")
        seen.add(number)
        if case.get("group") not in GROUP_IDS:
            raise fail(f"{number}: 모르는 group {case.get('group')!r}")
        if not isinstance(case.get("utterance"), str) or not isinstance(case.get("enabled"), bool):
            raise fail(f"{number}: utterance 는 문자열 · enabled 는 참/거짓이다")
        expected = case.get("expected") or {}
        if not expected.get("recipe_ids"):
            raise fail(f"{number}: expected.recipe_ids 가 비었다")
        unknown = sorted(set(expected.get("spoken") or {}) - names)
        if unknown:
            raise fail(f"{number}: spoken_value_names 에 없는 칸 {unknown}")
        if case["enabled"] and "semantic_inputs" not in expected:
            raise fail(f"{number}: expected.semantic_inputs 가 없다. 안 말한 발화도 {{}} 로 적는다")
        if "semantic_inputs" in expected and not isinstance(expected["semantic_inputs"], dict):
            raise fail(f"{number}: expected.semantic_inputs 는 dict 다")
        order.append((number, GROUP_IDS.index(case["group"])))

    ranks = [rank for _number, rank in sorted(order)]
    if ranks != sorted(ranks):
        raise fail("묶음이 id 순으로 이어지지 않는다")

    stray = sorted(set(document.get("marks") or {}) - seen)
    if stray:
        raise fail(f"marks 가 없는 case 를 가리킨다: {stray}")

    return document


def utterances(suite: dict) -> list[tuple]:
    """(번호, 발화, 기대 recipe 집합, 기본 실행 여부) 목록. 파일 차례 그대로."""
    return [
        (case["id"], case["utterance"], set(case["expected"]["recipe_ids"]), case["enabled"])
        for case in suite["cases"]
    ]


def spoken_values(suite: dict) -> dict[int, dict]:
    """이름 있는 값의 정답표. {번호: {이름: 기대값}}. 적은 case 만 들어감."""
    return {
        case["id"]: dict(case["expected"]["spoken"])
        for case in suite["cases"]
        if "spoken" in case["expected"]
    }


def marks(suite: dict) -> dict[int, str]:
    """{번호: 표시}. 적지 않은 번호는 없음."""
    return dict(suite.get("marks") or {})


def group_labels(suite: dict) -> tuple[str, ...]:
    """묶음 이름들. GROUP_IDS 차례."""
    labels = {group["id"]: group["label"] for group in suite["groups"]}
    return tuple(labels[group_id] for group_id in GROUP_IDS)


def group_of(suite: dict) -> dict[int, str]:
    """{번호: 묶음 이름}."""
    labels = dict(zip(GROUP_IDS, group_labels(suite)))
    return {case["id"]: labels[case["group"]] for case in suite["cases"]}


def last_id(suite: dict, group_id: str) -> int:
    """그 묶음의 마지막 번호. 묶음이 비면 SuiteError."""
    numbers = [case["id"] for case in suite["cases"] if case["group"] == group_id]
    if not numbers:
        raise SuiteError(f"{group_id} 묶음이 비었다")
    return max(numbers)
