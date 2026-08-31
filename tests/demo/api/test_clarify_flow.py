"""되묻기 → 고르기 → 실행이 chat 한 흐름 안에서 이어지는 것.

LLM 을 안 부른다. resolve 결과와 run 을 가짜로 주고 **무엇이 불렸는가**만 본다.
온톨로지도 안 읽는다 — 경로와 배선은 test_clarify_answer 와 같은 방식으로
가짜로 준다.

여기서 보는 것은 다섯이다.
  고르면 resolve 를 다시 안 부르는가
  고른 recipe 와 기억해 둔 인자로 부르는가
  고르기가 아니면 지금까지와 똑같이 도는가
  그때 직전 되묻기가 지워지는가
  스위치를 안 주면 켬이고, 끄면 세션을 아예 안 쓰는가
"""

import asyncio

import pytest

from demo.api.services import clarify_service, execute_service

SESSION = "s-demo"

# 「청주시 인구 알려줘」의 되묻기 하나. 후보 둘로 줄여 표를 짧게 둠.
CANDIDATES = ["recipe_011", "recipe_045"]
PATHS = {
    "recipe_011": [
        {"node_id": "spoken_place", "name": "말한 장소", "out_type": "말한 장소"},
        {"node_id": "n_pop", "name": "인구 통계 조회", "out_type": "인구 통계"},
    ],
    "recipe_045": [
        {"node_id": "spoken_place", "name": "말한 장소", "out_type": "말한 장소"},
        {"node_id": "n_age", "name": "연령별 인구 구성 조회", "out_type": "연령 구성"},
    ],
}


def collect(events):
    """async generator 가 낸 이벤트를 순서대로 모음."""

    async def pump():
        return [event async for event in events]

    return asyncio.run(pump())


@pytest.fixture(autouse=True)
def no_ontology(monkeypatch):
    """온톨로지와 배선 표를 안 읽음."""
    monkeypatch.setattr(
        execute_service.ontology_service,
        "executable_in",
        lambda recipe_id: [
            entry["node_id"]
            for entry in PATHS.get(recipe_id, [])
            if entry["node_id"] != "spoken_place"
        ],
    )
    monkeypatch.setattr(execute_service.step_service, "unwired", lambda recipe_id: [])
    clarify_service.clear()
    yield
    clarify_service.clear()


@pytest.fixture
def calls(monkeypatch):
    """resolve 와 run 이 몇 번 무엇으로 불렸는지 적음."""
    seen = {"resolve": [], "run": []}

    async def fake_run(recipe_id, argument, text="", context=None):
        seen["run"].append({"recipe_id": recipe_id, "argument": argument, "text": text})
        yield {"type": "result", "answer": "인구 통계를 조회했습니다.", "commands": []}

    monkeypatch.setattr(execute_service, "run", fake_run)
    return seen


def answering(monkeypatch, calls, **result):
    """resolve 가 늘 같은 것을 내도록. 부른 발화를 적어 둠."""
    answer = {
        "status": "CLARIFY",
        "recipe_id": None,
        "candidate_recipe_ids": CANDIDATES,
        "paths": PATHS,
        "reason": "",
        "given": "spoken_place",
        "argument": "청주시",
        **result,
    }

    def fake_resolve(text, llm_client, reason_max_length, context=None):
        calls["resolve"].append(text)
        return answer

    monkeypatch.setattr(execute_service.resolve_service, "resolve", fake_resolve)


def chat(text, session_id=SESSION):
    return collect(
        execute_service.chat(text, None, 200, context={}, session_id=session_id)
    )


def test_saying_a_number_after_a_clarify_calls_that_recipe(monkeypatch, calls):
    """이번 작업의 핵심. 지금은 "1번" 이 "요청이 없습니다" 로 끝남."""
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    chat("1번")

    assert calls["run"] == [
        {"recipe_id": "recipe_011", "argument": "청주시", "text": "청주시 인구 알려줘"}
    ]


def test_choosing_does_not_call_resolve_again(monkeypatch, calls):
    """무엇을 부를지는 이미 정해졌음. 다시 부르면 느리고 답이 흔들림."""
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    chat("2번")

    assert calls["resolve"] == ["청주시 인구 알려줘"]


def test_the_number_together_with_the_name_still_counts_as_a_choice(monkeypatch, calls):
    """화면 줄을 그대로 옮겨 적는 꼴임. 지금은 이것이 새 발화로 처리됨."""
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    chat("2 연령별 인구 구성 조회")

    assert calls["run"][0]["recipe_id"] == "recipe_045"
    assert calls["resolve"] == ["청주시 인구 알려줘"]


def test_what_was_chosen_shows_as_one_line_in_the_answer(monkeypatch, calls):
    """사람이 잘못 고른 것을 그 자리에서 알아야 함."""
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    events = chat("1번")

    assert events[-1]["answer"].splitlines()[0] == "고르신 것 — 1 인구 통계 조회"
    assert events[-1]["answer"].endswith("인구 통계를 조회했습니다.")


def test_what_is_not_a_choice_is_resolved_as_a_new_utterance(monkeypatch, calls):
    """멀쩡한 발화를 삼키면 안 됨. 지금까지와 똑같이 돌아야 함."""
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    chat("오송역 CCTV 보여줘")

    assert calls["resolve"] == ["청주시 인구 알려줘", "오송역 CCTV 보여줘"]
    assert calls["run"] == []


def test_what_is_not_a_choice_clears_the_previous_clarify(monkeypatch, calls):
    """두 발화 전의 되묻기를 나중에 고르는 일이 없어야 함.

    화면 실측 6 → 7 이 이 순서다. 되묻기 뒤에 딴 것을 물어 그것이 실행되면,
    그다음 "1번" 은 고를 것이 없는 자리다.
    """
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    # 딴 발화가 하나로 좁혀져 실행된다. 되묻기가 아니므로 남길 것도 없다.
    answering(
        monkeypatch, calls,
        status="SELECT", recipe_id="recipe_002", candidate_recipe_ids=[],
    )
    chat("오송역 CCTV 보여줘")

    answering(monkeypatch, calls)
    chat("1번")

    # 앞의 되묻기가 살아 있었다면 recipe_011 이 불렸을 것이다. 새 발화로 갔다.
    assert calls["resolve"][-1] == "1번"
    assert [call["recipe_id"] for call in calls["run"]] == ["recipe_002"]


def test_a_number_is_a_new_utterance_too_when_there_was_no_clarify(monkeypatch, calls):
    """직전에 되묻기가 없으면 어떤 문구도 고르기가 아님."""
    answering(monkeypatch, calls)

    chat("1번")

    assert calls["resolve"] == ["1번"]


def test_a_number_outside_the_candidate_count_is_a_new_utterance(monkeypatch, calls):
    """후보가 둘인데 "9번" 이면 무엇을 고른 것인지 알 수 없음."""
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    chat("9번")

    assert calls["resolve"][-1] == "9번"
    assert calls["run"] == []


def test_an_empty_session_string_does_not_remember(monkeypatch, calls):
    """저쪽 화면이 세션을 안 보내면 지금까지와 똑같이 동작해야 함."""
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘", session_id="")

    chat("1번", session_id="")

    assert calls["resolve"] == ["청주시 인구 알려줘", "1번"]
    assert calls["run"] == []


def test_without_an_argument_nothing_runs_even_after_choosing(monkeypatch, calls):
    """되묻기 때 인자를 못 뽑았으면 고른 뒤에도 없음. 안내만 함."""
    answering(monkeypatch, calls, argument=None)
    chat("인구 알려줘")

    events = chat("1번")

    assert calls["run"] == []
    assert "장소를 함께" in events[-1]["answer"]
    assert events[-1]["answer"].startswith("고르신 것 — 1 인구 통계 조회")


def test_SELECT_stores_no_clarify(monkeypatch, calls):
    """번호를 화면에 안 보였음. 그 뒤의 "1번" 은 새 발화임."""
    answering(monkeypatch, calls, status="SELECT", recipe_id="recipe_011")
    chat("청주시 인구 통계 알려줘")

    chat("1번")

    assert calls["resolve"][-1] == "1번"


def test_no_clarify_remains_after_choosing(monkeypatch, calls):
    """한 번 쓰면 지움. 남으면 같은 것이 두 번 실행됨."""
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")
    chat("1번")

    chat("2번")

    assert len(calls["run"]) == 1
    assert calls["resolve"][-1] == "2번"


# ── 스위치 ──────────────────────────────────────────────────────────


def test_no_env_var_means_on_so_a_number_runs(monkeypatch, calls):
    """기본이 켬임. 이것이 깨지면 시연 화면이 바뀜."""
    monkeypatch.delenv(clarify_service.CHOICE_ENV, raising=False)
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    chat("1번")

    assert calls["run"] == [
        {"recipe_id": "recipe_011", "argument": "청주시", "text": "청주시 인구 알려줘"}
    ]


def test_turning_it_off_sends_a_number_to_a_new_utterance(monkeypatch, calls):
    """「서른넷째」 이전과 같은 동작임."""
    monkeypatch.setenv(clarify_service.CHOICE_ENV, "0")
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    chat("1번")

    assert calls["resolve"] == ["청주시 인구 알려줘", "1번"]
    assert calls["run"] == []


def test_turning_it_off_does_not_even_remember(monkeypatch, calls):
    """끄는 까닭이 세션을 안 쓰는 것임. 고르기만 막으면 끈 것이 아님."""
    monkeypatch.setenv(clarify_service.CHOICE_ENV, "0")
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    assert clarify_service.take(SESSION) is None


def test_turning_it_off_and_on_again_does_not_revive_the_earlier_clarify(monkeypatch, calls):
    """끈 동안에는 남긴 것이 없음. 켠 뒤 첫 번호는 새 발화임."""
    monkeypatch.setenv(clarify_service.CHOICE_ENV, "0")
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    monkeypatch.delenv(clarify_service.CHOICE_ENV, raising=False)
    chat("1번")

    assert calls["resolve"] == ["청주시 인구 알려줘", "1번"]
    assert calls["run"] == []


def test_being_off_does_not_change_the_clarify_wording(monkeypatch, calls):
    """끄는 것은 고르기뿐임. 화면에 보이는 되묻기는 그대로여야 함."""
    answering(monkeypatch, calls)
    켬 = chat("청주시 인구 알려줘")[-1]["answer"]

    monkeypatch.setenv(clarify_service.CHOICE_ENV, "0")
    끔 = chat("청주시 인구 알려줘")[-1]["answer"]

    assert 켬 == 끔


def test_the_env_var_not_being_0_means_on(monkeypatch, calls):
    """끄는 값은 "0" 하나임. 다른 값은 지금 길로 감."""
    monkeypatch.setenv(clarify_service.CHOICE_ENV, "1")
    answering(monkeypatch, calls)
    chat("청주시 인구 알려줘")

    chat("1번")

    assert calls["run"][0]["recipe_id"] == "recipe_011"
