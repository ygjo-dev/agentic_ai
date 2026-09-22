"""실행 칸이 「KRRI 까지 실행됐는가」를 제대로 가르는가.

서버도 KRRI 도 안 부른다. KRRI 를 안 부른 자리의 답은 **local_presentation 이 만든
문구 그대로** `check_resolve._execution_of` 에 먹인다 — 문구를 시험에 베껴 적으면
문구가 바뀌었을 때 이 시험만 혼자 통과하고 표는 조용히 거짓말을 한다.

실제로 실행한 답은 KRRI 가 만들고 그 판정도 KRRI 것이다. 실행 칸은 그것을 다시 가르지
않는다. 실행 칸이 무엇이고 왜 관문이 아닌지는 `tools/check_resolve.py` 의 「실행」 절에
있다.
"""

from dev.tools import check_resolve
from execution.local_presentation import EXECUTOR_UNREACHABLE, NO_ARGUMENT_ANSWER, UNWIRED_ANSWER

# KRRI 가 만든 답이라는 표시. 우리 문구에 없는 문장이다.
KRRI_ANSWER = "오송역 주변에서 CCTV 3대를 찾았습니다.\n\n첫째는 오송역 앞입니다."


def test_a_krri_answer_counts_as_executed_and_is_shown_verbatim():
    """KRRI 가 돌았다. 결과가 무엇이었는지는 KRRI 답의 첫 줄을 사람이 읽는다."""
    mark, why = check_resolve._execution_of({"answer": KRRI_ANSWER, "steps": []})

    assert mark == check_resolve.RAN
    assert why == "오송역 주변에서 CCTV 3대를 찾았습니다."


def test_a_krri_failure_answer_is_not_rejudged_here():
    """KRRI 의 실패 답도 KRRI 가 돈 결과다. 이 도구가 문장을 읽어 성공 · 실패를 다시 가르지 않는다."""
    mark, why = check_resolve._execution_of({"answer": "조회하지 못했습니다.", "steps": []})

    assert (mark, why) == (check_resolve.RAN, "조회하지 못했습니다.")


def test_failing_to_extract_an_argument_means_no_tool_was_called():
    """단계가 하나도 없다. Gateway 쪽 데이터 탓이 아니라 우리 해석 탓이다."""
    turn = {"answer": NO_ARGUMENT_ANSWER["place_name"], "steps": []}

    mark, why = check_resolve._execution_of(turn)

    assert mark == check_resolve.EMPTY
    assert why.startswith(check_resolve.WHY_ARGUMENT)


def test_an_unwired_node_means_no_tool_was_called():
    turn = {"answer": UNWIRED_ANSWER.format(names="CCTV 조회"), "steps": []}

    mark, why = check_resolve._execution_of(turn)

    assert mark == check_resolve.EMPTY
    assert why == f"{check_resolve.WHY_UNWIRED} · CCTV 조회"


def test_an_unreachable_executor_is_recorded_apart_from_a_krri_answer():
    """KRRI 창구를 못 불렀으면 실행이 된 것이 아니다."""
    mark, why = check_resolve._execution_of({"answer": EXECUTOR_UNREACHABLE, "steps": []})

    assert mark == check_resolve.EMPTY
    assert why.startswith(check_resolve.WHY_UNREACHABLE)


# ── 정답표가 온톨로지와 안 어긋났는가 ───────────────────────────────


def test_every_expected_recipe_really_exists():
    """recipe 번호가 다섯 번 밀렸다. 밀릴 때마다 손으로 맞춰 왔다.

    없는 번호를 가리키면 그 발화는 영영 빗나감으로 찍히는데, 표만 봐서는
    발화가 나쁜 것인지 번호가 밀린 것인지가 안 갈린다.
    """
    from app.api.services.streamlit import screen_service

    있는_것 = set(screen_service.recipe_ids())
    기대한_것 = {rid for _, _, expected, _ in check_resolve.UTTERANCES for rid in expected}

    assert 기대한_것 <= 있는_것


def test_the_expected_recipes_of_the_five_screen_utterances_start_from_the_screen():
    """화면 발화라고 넣었는데 「장소 이름」 으로 시작하는 recipe 를 가리키면 뜻이 없다.

    번호가 밀리면 조용히 옆 recipe 를 가리키게 된다. 경로 첫 칸으로 지킨다.
    """
    from app.api.services.streamlit import screen_service
    from execution import workflow_materializer

    for number, _u, expected, _d in check_resolve.UTTERANCES:
        if number <= check_resolve.EXTENSION_LAST:
            continue
        for recipe_id in expected:
            path = screen_service.path_of(recipe_id)
            assert path[0]["node_id"] in workflow_materializer.load(recipe_id)["context_needs"]


def test_each_utterance_falls_into_exactly_one_group():
    """묶음이 셋이 되면서 겹치거나 빠지면 합계가 시행 횟수와 안 맞는다."""
    갈라진_것 = [n for _label, group in check_resolve._groups(check_resolve.UTTERANCES)
                for n, _u, _e, _d in group]

    assert sorted(갈라진_것) == sorted(n for n, _u, _e, _d in check_resolve.UTTERANCES)
    assert len(갈라진_것) == len(set(갈라진_것))
