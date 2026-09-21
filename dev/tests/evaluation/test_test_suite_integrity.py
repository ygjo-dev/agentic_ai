"""대상 : dev/evaluation/inputs/test_suites/ — 정답표가 게시 자산(recipe · menu · prompt)과 맞물리나

정답표의 구조(묶음 · id · 범위 밖 모양)는 load_test_suite.load 가 읽을 때 본다. 여기는 그 밖,
정답표와 게시 자산 사이의 불변식이다. recipe 배선 · menu · prompt 는 커밋마다 바뀌므로 커밋마다 본다.

    채점 칸      기대 recipe 의 Recipe.execution 이 {from: spoken.<이름>} 으로 읽는 칸과 같다
    묶음         범위 안 case 의 묶음이 기대 recipe 의 화면 문맥(context_needs)과 맞다
    누설         발화에 recipe id · 도구 이름이 없다. 판 2 면 menu example · prompt 예시 문장도 없다
    범위 밖      결과 이름이 resolve 응답 schema 의 status 에 있고, 전부 [NO_MATCH] 다
    두께         판 2 는 받아들인 recipe 마다 발화 MIN_UTTERANCES_PER_RECIPE 이상, 범위 밖 갈래마다 하나 이상
    분리         판 2 발화가 FULL48 발화와 글자까지 같지 않다

정답표 · recipe 를 고치지 않는다. 읽기만 한다.
"""

import re
from collections import Counter

import pytest

import paths
from dev.evaluation.engine import load_test_suite, score
from execution import workflow_materializer
from llm_engine.role_config import RESOLVE, get_role_config

# 판 2 정답표가 받아들인 recipe 마다 가져야 하는 범위 안 발화 수.
MIN_UTTERANCES_PER_RECIPE = 5

# 화면 문맥 이름 -> 그 문맥에서 시작하는 묶음. 둘 다 없으면 말한 것.
CONTEXT_GROUPS = (("point", "picked_point"), ("map_extent", "view_extent"))

# prompt 에서 따옴표로 인용한 예시 중 발화에 들어가면 안 되는 것의 최소 길이.
# 짧은 것(「보여줘」 · 「여기」)은 어느 발화에나 있는 말이라 새는 것이 아니다.
LEAK_MIN_LENGTH = 6

SUITES = [entry["id"] for entry in load_test_suite.datasets()]


def _suite(dataset_id: str) -> dict:
    return load_test_suite.load(load_test_suite.dataset(dataset_id)["path"])


def _expected_group(execution: dict) -> str:
    """recipe 가 속할 묶음 id. execution 이 읽는 화면 문맥이 정함."""
    needs = execution.get("context_needs") or {}
    return next((group for name, group in CONTEXT_GROUPS if name in needs), load_test_suite.GROUP_IDS[0])


def _leak_phrases() -> set[str]:
    """발화에 옮기면 안 되는 prompt 속 글. menu example · prompt 의 따옴표 예시(띄어쓰기 있고 LEAK_MIN_LENGTH 이상)."""
    import yaml

    phrases = set()
    menu = yaml.safe_load(paths.MENU_YAML_PATH.read_text(encoding="utf-8")) or {}
    for entry in (menu.get("recipes") or {}).values():
        if isinstance(entry, dict) and entry.get("example"):
            phrases.add(entry["example"])
    for quoted in re.findall(r'"([^"\n]+)"', get_role_config(RESOLVE).prompt):
        if " " in quoted and len(quoted) >= LEAK_MIN_LENGTH:
            phrases.add(quoted)
    return phrases


def _accepted() -> list[str]:
    return sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))


@pytest.mark.parametrize("dataset_id", SUITES)
def test_every_graded_spoken_field_is_one_the_expected_recipe_reads_and_none_is_left_out(dataset_id):
    """안 읽는 칸은 맞혀도 틀려도 실행이 안 바뀌어 점수가 실행의 뜻과 어긋난다. 읽는 칸을 빼면 틀려도 모른다."""
    problems = []
    for case in _suite(dataset_id)["cases"]:
        if not load_test_suite.in_scope(case):
            continue
        reads = set(score.recipe_reads(case["expected"]["recipe_ids"]))
        graded = set(case["expected"].get("spoken") or {})
        if graded - reads:
            problems.append((case["id"], "안 읽는 칸을 채점함", sorted(graded - reads)))
        if reads - graded:
            problems.append((case["id"], "읽는 칸을 안 채점함", sorted(reads - graded)))
    assert problems == []


@pytest.mark.parametrize("dataset_id", SUITES)
def test_every_expected_recipe_exists_and_sits_in_the_group_its_screen_context_implies(dataset_id):
    problems = []
    for case in _suite(dataset_id)["cases"]:
        if not load_test_suite.in_scope(case):
            continue
        for recipe_id in case["expected"]["recipe_ids"]:
            execution = workflow_materializer.load(recipe_id)
            if execution is None:
                problems.append((case["id"], "없는 recipe", recipe_id))
            elif _expected_group(execution) != case["group"]:
                problems.append((case["id"], recipe_id, _expected_group(execution), case["group"]))
    assert problems == []


@pytest.mark.parametrize("dataset_id", SUITES)
def test_no_utterance_leaks_a_recipe_id_a_tool_name_or_for_v2_a_prompt_example(dataset_id):
    """FULL48(판 1)은 얼린 자라 prompt 예시 검사보다 먼저 지은 발화가 그대로 있다. 그래서 그 검사는 판 2 에만 건다."""
    suite = _suite(dataset_id)
    tools = set()
    for recipe_id in _accepted():
        for step in (workflow_materializer.load(recipe_id) or {}).get("workflow") or []:
            tools.update(value for value in (step.get("tool"), step.get("command")) if value)
    leaks = _leak_phrases()

    problems = []
    for case in suite["cases"]:
        text = case["utterance"]
        if "recipe" in text.lower() or any(tool in text for tool in tools):
            problems.append((case["id"], "recipe id · 도구 이름"))
        if suite["version"] >= 2 and any(phrase in text for phrase in leaks):
            problems.append((case["id"], "prompt 예시 문장"))
    assert problems == []


@pytest.mark.parametrize("dataset_id", SUITES)
def test_out_of_scope_accepts_only_no_match_and_it_is_a_real_resolve_status(dataset_id):
    """되묻기 · 값 부족이 정답인 발화는 범위 밖이 아니다. 섞이면 「기능이 없다」와 「더 물어야 한다」가 한 점수가 된다."""
    known = set(get_role_config(RESOLVE).response_schema["properties"]["status"]["enum"])
    assert set(load_test_suite.OOS_OUTCOMES) <= known
    for case in _suite(dataset_id)["cases"]:
        if not load_test_suite.in_scope(case):
            assert case["expected"]["outcomes"] == ["NO_MATCH"], case["id"]


def test_test_suite_v2_gives_every_accepted_recipe_enough_distinct_utterances_and_out_of_scope_means_no_match():
    """v2 는 recipe 마다 다섯 이상이어야 일반화를 잰다고 말할 수 있고, 범위 밖은 NO_MATCH 만 정답이다."""
    v2 = load_test_suite.load(load_test_suite.SUITE_V2_PATH)
    accepted = set(_accepted())
    inside = [case for case in v2["cases"] if load_test_suite.in_scope(case)]
    outside = [case for case in v2["cases"] if not load_test_suite.in_scope(case)]
    per_recipe = Counter(case["expected"]["recipe_ids"][0] for case in inside)

    assert set(per_recipe) == accepted
    assert min(per_recipe.values()) >= MIN_UTTERANCES_PER_RECIPE
    assert len({case["id"] for case in v2["cases"]}) == len(v2["cases"])
    assert len({case["utterance"] for case in v2["cases"]}) == len(v2["cases"])
    assert outside, "범위 밖 발화가 없다"
    assert {case["expected"]["category"] for case in outside} == set(load_test_suite.OOS_CATEGORIES)
    assert not any("CLARIFY" in (case["expected"].get("outcomes") or []) for case in v2["cases"])
    assert not any("MISSING_ARGUMENT" in (case["expected"].get("outcomes") or []) for case in v2["cases"])


def test_v2_shares_no_utterance_with_the_full48_anchor():
    """같은 발화가 두 자에 있으면 v2 가 일반화를 잰다는 말이 흐려진다."""
    full = load_test_suite.load()
    v2 = load_test_suite.load(load_test_suite.SUITE_V2_PATH)
    assert {case["utterance"] for case in v2["cases"]} & {case["utterance"] for case in full["cases"]} == set()


def test_full48_stays_the_frozen_version_1_anchor_next_to_v2():
    """v2 를 붙여도 FULL48 은 판 1 · 범위 안만 · 같은 묶음으로 읽혀야 한다. 옛 기록과 이어 읽는 자다."""
    full = load_test_suite.load()
    assert full["version"] == 1
    assert load_test_suite.datasets()[0]["path"] == load_test_suite.SUITE_PATH
    assert all(load_test_suite.in_scope(case) for case in full["cases"])
    assert tuple(group["id"] for group in full["groups"]) == load_test_suite.GROUP_IDS
    assert len(load_test_suite.utterances(full)) == len(full["cases"])


def test_spoken_refs_tells_required_default_and_conditional_reads_apart():
    """조건 · 기본값 · 필수를 가르지 못하면 「사용 안 함」과 「없음」을 가르는 reads 가 틀린다."""
    fake = {"workflow": [{"input": {
        "a": {"from": "spoken.argument"},
        "b": {"from": "spoken.argument", "unless_endswith": "선"},
        "c": [{"from": "spoken.future_name", "default": [30]}],
        "d": {"from": "context.point.lon"},
    }}]}
    assert [(ref["name"], ref["use"]) for ref in score.spoken_refs(fake)] == [
        ("argument", "required"),
        ("argument", "unless_endswith=선"),
        ("future_name", "default=[30]"),
    ]
