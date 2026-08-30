"""실행 칸이 「답이 나왔는가」를 제대로 가르는가.

서버도 Gateway 도 안 부른다. 답 문구를 **vendor 가 만들게 해서** 그것을
`check_resolve._execution_of` 에 먹인다 — 문구를 시험에 베껴 적으면
`vendor/asap/workflow_answer.py` 가 문구를 갱신했을 때 이 시험만 혼자 통과하고
표는 조용히 거짓말을 한다. 실제로 「쉰다섯째」에 그 머리말이 한 줄에서 두 줄이
됐다.

실행 칸이 무엇이고 왜 관문이 아닌지는 `tools/check_resolve.py` 의 「실행」 절에
있다.
"""

from tools import check_resolve
from vendor.asap.workflow_answer import compose_workflow_answer, step_line

# recipe 가 아는 성공 문장. 무엇이 오든 vendor 는 그대로 첫 줄에 쓴다.
HEADLINE = "행정구역을 조회했습니다."

INTENT = {"answer_instruction": HEADLINE}


def turn_of(trace, *, failed=False):
    """trace 한 벌을 /recent 회차 모양으로.

    답도 단계 줄도 vendor 가 만든 것을 쓴다. recent_service 가 화면에 내보내는
    것이 바로 그 둘이라 여기서 흉내내면 시험이 실물과 갈린다.
    """
    return {
        "answer": compose_workflow_answer(INTENT, trace, failed=failed),
        "steps": [
            {"node": "n", "line": f"{i}. {step_line(item)}"}
            for i, item in enumerate(trace, start=1)
        ],
    }


def test_결과가_오면_답이_나온_것이다():
    """건수가 있는 마지막 단계가 성공 판정이다."""
    turn = turn_of([{"tool": "adminBoundary.searchBoundaries", "result": {"count": 4}}])

    mark, _why = check_resolve._execution_of(turn)

    assert mark == check_resolve.RAN


def test_0건은_답이_안_나온_것이다():
    """적중 3/3 인데 화면이 "찾지 못했습니다" 이던 자리가 이것이다."""
    turn = turn_of([{"tool": "election.searchDistricts", "result": {"count": 0}}])

    mark, why = check_resolve._execution_of(turn)

    assert mark == check_resolve.EMPTY
    assert why.startswith(check_resolve.WHY_EMPTY)


def test_not_found_는_0건과_갈라_적는다():
    """사람이 할 일이 다르다 — 낱말을 바꿀 일이 아니라 있는 이름을 대야 한다."""
    turn = turn_of([{"tool": "election.getDistrict", "result": {"status": "not_found"}}])

    mark, why = check_resolve._execution_of(turn)

    assert mark == check_resolve.EMPTY
    assert why.startswith("not_found")


def test_권한이_없는_것은_터진_것과_갈라_적는다():
    """저쪽에 도구를 열어 달라고 할 일이지 우리가 고칠 일이 아니다."""
    turn = turn_of(
        [
            {
                "tool": "web-search/web.search",
                "error": "실패",
                "error_detail": "MCP tool 'web-search/web.search' is not applied for this user.",
            }
        ]
    )

    mark, why = check_resolve._execution_of(turn)

    assert mark == check_resolve.EMPTY
    assert why.startswith(check_resolve.WHY_PERMISSION)


def test_인자를_못_뽑으면_도구를_안_부른_것이다():
    """단계가 하나도 없다. 저쪽 데이터 탓이 아니라 우리 해석 탓이다."""
    from demo.api.services.execute_service import NO_ARGUMENT_ANSWER

    turn = {"answer": NO_ARGUMENT_ANSWER["spoken_place"], "steps": []}

    mark, why = check_resolve._execution_of(turn)

    assert mark == check_resolve.EMPTY
    assert why.startswith(check_resolve.WHY_ARGUMENT)


def test_되묻기_뒤에_고른_줄은_판정에서_뗀다():
    """그 줄은 늘 성공한 것처럼 생겨서 붙여 두면 0건도 ✓ 로 읽힌다."""
    from demo.api.services.execute_service import CHOICE_HEAD

    head = CHOICE_HEAD.format(number=1, label="국회의원 전체 선거구 검색")
    zero = turn_of([{"tool": "election.searchAssemblyDistricts", "result": {"count": 0}}])
    turn = {**zero, "answer": f"{head}\n\n{zero['answer']}"}

    mark, why = check_resolve._execution_of(turn)

    assert mark == check_resolve.EMPTY
    assert why.startswith(check_resolve.WHY_EMPTY)


# ── 정답표가 온톨로지와 안 어긋났는가 ───────────────────────────────


def test_기대_recipe_가_다_실재한다():
    """recipe 번호가 다섯 번 밀렸다. 밀릴 때마다 손으로 맞춰 왔다.

    없는 번호를 가리키면 그 발화는 영영 빗나감으로 찍히는데, 표만 봐서는
    발화가 나쁜 것인지 번호가 밀린 것인지가 안 갈린다.
    """
    from demo.api.services import ontology_service

    있는_것 = set(ontology_service.recipe_ids())
    기대한_것 = {rid for _, _, expected, _ in check_resolve.UTTERANCES for rid in expected}

    assert 기대한_것 <= 있는_것


def test_화면_다섯의_기대_recipe_는_화면에서_출발한다():
    """화면 발화라고 넣었는데 「말한 장소」 recipe 를 가리키면 뜻이 없다.

    번호가 밀리면 조용히 옆 recipe 를 가리키게 된다. 경로 첫 칸으로 지킨다.
    """
    from demo.api.services import ontology_service, step_service

    for number, _u, expected, _d in check_resolve.UTTERANCES:
        if number <= check_resolve.EXTENSION_LAST:
            continue
        for recipe_id in expected:
            path = ontology_service.path_of(recipe_id)
            assert path[0]["node_id"] in step_service.CONTEXT_STARTS


def test_발화가_묶음_하나에만_든다():
    """묶음이 셋이 되면서 겹치거나 빠지면 합계가 시행 횟수와 안 맞는다."""
    갈라진_것 = [n for _label, group in check_resolve._groups(check_resolve.UTTERANCES)
                for n, _u, _e, _d in group]

    assert sorted(갈라진_것) == sorted(n for n, _u, _e, _d in check_resolve.UTTERANCES)
    assert len(갈라진_것) == len(set(갈라진_것))
