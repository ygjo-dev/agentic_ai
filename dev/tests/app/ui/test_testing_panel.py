"""테스트 탭 화면 시안. 가짜 결과 200건과 그것을 화면 글자로 바꾸는 순수 함수만 본다.

Streamlit 을 안 띄운다. 그리는 것은 화면을 보면 알고, **화면을 봐도 모르는 것은
숫자가 어긋났는지와 개발 용어가 샜는지다.** 그것을 여기서 막는다.
"""

import re

from app.ui.components import testing_panel as panel
from app.ui.testing_mock import mock_test_results

# 사람이 보는 화면에 나오면 안 되는 개발 용어
BANNED = ("Recipe", "recipe", "Resolve", "resolve", "Semantic", "semantic", "Menu",
          "Workflow", "Materializ", "기대", "실제", "None", "null")


def visible_text(markup: str) -> str:
    """마크업에서 태그를 걷어낸 글자."""
    return re.sub(r"<[^>]+>", " ", markup)


def test_the_mock_has_200_fixed_results_with_unique_ids():
    """다시 띄워도 같은 화면이어야 시안을 두고 이야기할 수 있음."""
    first, second = mock_test_results(), mock_test_results()

    assert first == second
    assert [r["id"] for r in first] == list(range(1, 201))
    assert len({r["utterance"] for r in first}) == len(first)


def test_the_mock_splits_into_187_passed_5_function_and_8_input_failures():
    summary = panel.summarize(mock_test_results())

    assert summary == {"total": 200, "passed": 187, "failed": 13, "function": 5, "input": 8}


def test_each_mock_verdict_agrees_with_its_answer_and_model_output():
    """판정과 상세가 어긋나면 화면이 스스로를 반박함.

    기능이 다르면 기능 선택 실패, 기능이 같고 채점하는 인자가 다르면 인자 추출 실패,
    그 밖에는 성공이어야 함
    """
    for r in mock_test_results():
        function_differs = r["answer"]["function_id"] != r["model_output"]["function_id"]
        graded_differs = any(f["differs"] and f["graded"] for f in panel.field_rows(r))
        if function_differs:
            expected = (False, "function")
        elif graded_differs:
            expected = (False, "input")
        else:
            expected = (True, None)
        assert (r["passed"], r["failure_stage"]) == expected, r["id"]


def test_the_mock_covers_multi_field_misses_and_ungraded_differences():
    """화면에서 확인하려던 경우가 데이터에 없으면 시안이 그것을 못 보여줌."""
    results = mock_test_results()
    graded_misses = [
        sum(f["differs"] and f["graded"] for f in panel.field_rows(r)) for r in results
    ]
    ungraded_on_pass = [
        r for r in results
        if r["passed"] and any(f["differs"] and not f["graded"] for f in panel.field_rows(r))
    ]

    assert 1 in graded_misses
    assert max(graded_misses) >= 2
    assert ungraded_on_pass


def test_the_filters_pick_failures_by_stage_and_search_ignores_spaces():
    results = mock_test_results()

    assert len(panel.filter_results(results, "전체")) == 200
    assert len(panel.filter_results(results, "실패만")) == 13
    assert {r["failure_stage"] for r in panel.filter_results(results, "기능 선택")} == {"function"}
    assert len(panel.filter_results(results, "인자 추출")) == 8
    found = panel.filter_results(results, "실패만", "청주 서원")
    assert [r["utterance"] for r in found] == ["청주서원 선거구 알려줘"]


def test_an_input_the_panel_does_not_know_is_still_shown_under_its_own_name():
    """새 인자가 들어와도 화면 코드를 안 고쳐야 함."""
    result = mock_test_results()[0]
    result["model_output"]["inputs"]["new_field"] = "값"

    rows = panel.field_rows(result)

    assert [r["name"] for r in rows][:4] == list(panel.FIELD_ORDER)
    assert rows[-1] == {
        "name": "new_field", "label": "new_field", "answer": None, "model": "값",
        "differs": True, "graded": False,
    }


def test_missing_values_read_as_없음():
    assert panel.display_value(None) == "없음"
    assert panel.display_value([]) == "없음"
    assert panel.display_value([15, 30]) == "15 · 30"


def test_every_detail_compares_정답표_with_ai_model_output_without_developer_words():
    """성공 · 실패가 같은 틀이고, 내부 번호 대신 「기능 NNN」이 보여야 함."""
    for r in mock_test_results():
        text = visible_text(panel.detail_markup(r))
        assert "정답표" in text and "AI 모델 출력" in text, r["id"]
        assert "모델 판단" in text and "후보 기능" in text and "모델 판정 상태" in text, r["id"]
        leaked = [w for w in BANNED if w in text]
        assert not leaked, (r["id"], leaked)
