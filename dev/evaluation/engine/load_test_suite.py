"""발화 해석 정답표(Test Suite)를 읽는 유일한 곳. 등록 목록 · 읽기 · 구조 검사 · 신원.

정답표는 `dev/evaluation/inputs/test_suites/` 의 두 파일이다.

    test_suite_v1.yaml   FULL48. 판 1. 얼린 회귀 기준선. 계기판 dev/tools/check_resolve.py 도 이것을 읽는다
    test_suite_v2.yaml   테스트 세트 v2. 판 2. recipe 마다 발화 다섯 이상 + 범위 밖(NO_MATCH) 묶음

`dev/evaluation/run_evaluation.py` 와 화면 테스트 탭이 이 모듈로 읽는다.
정답표가 게시 자산(recipe · menu · prompt)과 맞물리는지는 여기서 안 본다.
그것은 dev/tests/evaluation/test_test_suite_integrity.py 가 커밋마다 본다.

기대값을 여기서 고치거나 채우지 않는다. 무엇이 정답인지는 파일에 사람이 적는다.
"""

from pathlib import Path

import yaml

# 정답표 파일이 사는 폴더. 평가의 입력이다. 결과는 outputs/ 에 따로 둔다.
SUITES_DIR = Path(__file__).resolve().parents[1] / "inputs" / "test_suites"

SUITE_PATH = SUITES_DIR / "test_suite_v1.yaml"
SUITE_V2_PATH = SUITES_DIR / "test_suite_v2.yaml"

# 화면 · 계기판이 이름으로 고를 수 있는 정답표(Test Suite). (id, 사람이 읽는 이름, 경로)
# 정답표 파일을 더하면 여기 한 줄을 더한다. 첫 줄이 화면의 기본값이다.
#   test_suite_v1   FULL48. 얼린 회귀 기준선. 발화 · 기대값을 바꾸지 않는다
#   test_suite_v2   일반화를 재는 넓은 자. recipe 마다 발화 다섯 이상 + 범위 밖
DATASETS = (
    ("test_suite_v1", "FULL48 회귀 테스트", SUITE_PATH),
    ("test_suite_v2", "테스트 세트 v2", SUITE_V2_PATH),
)

# 이 모듈이 읽을 줄 아는 파일 판. 1 은 FULL48, 2 는 범위 밖 묶음을 더 가짐.
SUITE_VERSION = 1
SUITE_VERSIONS = (1, 2)

# 묶음 id 와 그 차례. 표를 찍는 차례이기도 하다. 셋 다 범위 안(기대 recipe 가 있음)이다.
GROUP_IDS = ("spoken", "picked_point", "view_extent")

# 판 2 만 갖는 마지막 묶음. 기대 recipe 가 없고 기대 결과(outcomes)가 있다.
# **범위 밖 = 지원하는 기능 중 어느 것도 고르면 안 되는 발화**다. 되묻기(CLARIFY)가 정답인
# 발화 · 값이 모자라 멈추는 것(MISSING_ARGUMENT)이 정답인 발화는 범위 밖이 아니다 — 그것은
# 되묻기 동작을 재는 일이라 이 묶음에 섞으면 「기능이 없다」와 「더 물어야 한다」가 한 점수가 된다.
OUT_OF_SCOPE = "out_of_scope"

# 범위 밖 발화의 갈래. 지금은 하나다.
#   unsupported   menu 의 어느 기능도 하는 일이 아니다
OOS_CATEGORIES = ("unsupported",)

# 범위 밖 발화가 받아들이는 결과. resolve 응답 schema 의 status 이름이다
# (dev/tests/evaluation/test_test_suite_integrity.py 가 schema 에 실제로 있는지 본다).
OOS_OUTCOMES = ("NO_MATCH",)


class SuiteError(ValueError):
    """정답표 파일을 알아볼 수 없다."""


def load(path: Path | None = None) -> dict:
    """정답표 한 벌.

    입력  YAML 경로. 없으면 SUITE_PATH
    출력  읽은 dict. 아래 검사를 통과한 것만
    규칙  version 이 SUITE_VERSIONS 중 하나
          groups 가 판 1 이면 GROUP_IDS, 판 2 면 GROUP_IDS + OUT_OF_SCOPE 차례 그대로
          case id 가 정수이고 겹치지 않음. group 이 아는 묶음임
          묶음이 id 순으로 이어짐. BASELINE_LAST 같은 「묶음의 마지막 번호」가 뜻을 가지려면 필요함
          범위 안 case 는 expected.recipe_ids 가 비지 않음. expected.spoken 칸이 spoken_value_names 안에 있음
          범위 밖 case 는 recipe_ids · spoken 이 없고 category 가 OOS_CATEGORIES,
          outcomes 가 비지 않은 OOS_OUTCOMES 부분 목록임 (지금은 [NO_MATCH] 뿐)
          marks 가 있는 case id 를 가리킴
    제약  기대값을 고치거나 채우지 않는다.
          틀린 파일을 부분만 읽지 않는다. 표가 조용히 줄어듦
    """
    path = path or SUITE_PATH
    document = yaml.safe_load(path.read_text(encoding="utf-8"))

    def fail(message):
        return SuiteError(f"{path.name}: {message}")

    if not isinstance(document, dict) or document.get("version") not in SUITE_VERSIONS:
        raise fail(f"version 이 {list(SUITE_VERSIONS)} 중 하나가 아니다")
    group_ids = GROUP_IDS if document["version"] == 1 else (*GROUP_IDS, OUT_OF_SCOPE)
    if tuple(group.get("id") for group in document.get("groups") or []) != group_ids:
        raise fail(f"groups 는 {list(group_ids)} 차례다")

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
        if case.get("group") not in group_ids:
            raise fail(f"{number}: 모르는 group {case.get('group')!r}")
        if not isinstance(case.get("utterance"), str) or not isinstance(case.get("enabled"), bool):
            raise fail(f"{number}: utterance 는 문자열 · enabled 는 참/거짓이다")
        expected = case.get("expected") or {}
        if case["group"] == OUT_OF_SCOPE:
            if "recipe_ids" in expected or "spoken" in expected:
                raise fail(f"{number}: 범위 밖 case 에는 recipe_ids · spoken 이 없다")
            if expected.get("category") not in OOS_CATEGORIES:
                raise fail(f"{number}: 모르는 범위 밖 갈래 {expected.get('category')!r}")
            outcomes = expected.get("outcomes")
            if not outcomes or not isinstance(outcomes, list) or set(outcomes) - set(OOS_OUTCOMES):
                raise fail(f"{number}: outcomes 는 {list(OOS_OUTCOMES)} 중 하나 이상이다")
        else:
            if "category" in expected or "outcomes" in expected:
                raise fail(f"{number}: 범위 안 case 에는 category · outcomes 가 없다")
            if not expected.get("recipe_ids"):
                raise fail(f"{number}: expected.recipe_ids 가 비었다")
            unknown = sorted(set(expected.get("spoken") or {}) - names)
            if unknown:
                raise fail(f"{number}: spoken_value_names 에 없는 칸 {unknown}")
        order.append((number, group_ids.index(case["group"])))

    ranks = [rank for _number, rank in sorted(order)]
    if ranks != sorted(ranks):
        raise fail("묶음이 id 순으로 이어지지 않는다")

    stray = sorted(set(document.get("marks") or {}) - seen)
    if stray:
        raise fail(f"marks 가 없는 case 를 가리킨다: {stray}")

    return document


def datasets() -> list[dict]:
    """고를 수 있는 정답표 목록. [{id, label, path}] DATASETS 차례.

    제약  파일을 여기서 읽지 않는다. 읽는 것은 load 임
    """
    return [{"id": dataset_id, "label": label, "path": path} for dataset_id, label, path in DATASETS]


def dataset(dataset_id: str) -> dict:
    """id 로 고른 정답표 한 줄. {id, label, path}. 모르는 id 면 KeyError."""
    chosen = next((entry for entry in datasets() if entry["id"] == dataset_id), None)
    if chosen is None:
        raise KeyError(f"모르는 정답표: {dataset_id!r}")
    return chosen


def dataset_of_path(path: Path) -> dict | None:
    """그 파일이 등록된 정답표면 {id, label}. 아니면 None."""
    return next(
        ({"id": entry["id"], "label": entry["label"]} for entry in datasets()
         if Path(entry["path"]).resolve() == Path(path).resolve()),
        None,
    )


def in_scope(case: dict) -> bool:
    """기대 recipe 가 있는 case 인가. 범위 밖 묶음이면 거짓."""
    return case["group"] != OUT_OF_SCOPE


def utterances(suite: dict) -> list[tuple]:
    """(번호, 발화, 기대 recipe 집합, 기본 실행 여부) 목록. 파일 차례 그대로. 범위 안만."""
    return [
        (case["id"], case["utterance"], set(case["expected"]["recipe_ids"]), case["enabled"])
        for case in suite["cases"]
        if in_scope(case)
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
    """묶음 이름들. 파일의 groups 차례 (GROUP_IDS, 판 2 면 그 뒤에 범위 밖)."""
    return tuple(group["label"] for group in suite["groups"])


def label_of(suite: dict) -> dict[str, str]:
    """{묶음 id: 묶음 이름}."""
    return {group["id"]: group["label"] for group in suite["groups"]}


def group_of(suite: dict) -> dict[int, str]:
    """{번호: 묶음 이름}."""
    labels = label_of(suite)
    return {case["id"]: labels[case["group"]] for case in suite["cases"]}


def identity(suite: dict, path: Path | None = None) -> dict:
    """정답표 한 벌의 신원. {name, version, sha256, case_count}.

    규칙  name 은 파일의 name, 없으면 파일 이름. sha256 은 파일 바이트 그대로
    """
    import hashlib

    path = Path(path or SUITE_PATH)
    return {
        "name": suite.get("name") or path.stem,
        "version": suite.get("version"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        "case_count": len(suite["cases"]),
    }


def last_id(suite: dict, group_id: str) -> int:
    """그 묶음의 마지막 번호. 묶음이 비면 SuiteError."""
    numbers = [case["id"] for case in suite["cases"] if case["group"] == group_id]
    if not numbers:
        raise SuiteError(f"{group_id} 묶음이 비었다")
    return max(numbers)
