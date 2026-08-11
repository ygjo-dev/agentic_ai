"""샘플 콤보박스 검증.

목록에는 발화만 나와야 한다. 상태와 recipe id 를 같이 보여주면 답을
미리 알려주는 셈이라 시연에서 의미가 없다. 기대값 자체는 정답 경로를
그리는 데 계속 쓰므로 데이터에서 지우면 안 된다.
"""

from frontend.components.sample_picker import (
    EXPECTED_BY_UTTERANCE,
    PLACEHOLDER,
    SAMPLES,
)

VALID_STATUSES = {"SELECT", "CLARIFY", "NO_MATCH"}


def options() -> list[str]:
    """render_sample_picker 가 selectbox 에 넘기는 목록."""
    return [PLACEHOLDER, *(utterance for utterance, *_ in SAMPLES)]


# ------------------------------------------------------------ 노출 범위
def test_options_are_utterances_only():
    for option in options():
        assert isinstance(option, str)


def test_status_is_not_exposed():
    """SELECT / CLARIFY / NO_MATCH 가 목록에 보이면 답을 알려주는 셈이다."""
    joined = " ".join(options())

    for status in VALID_STATUSES:
        assert status not in joined


def test_recipe_id_is_not_exposed():
    joined = " ".join(options())

    assert "recipe_" not in joined


def test_placeholder_comes_first():
    """기본값은 직접 입력이어야 한다. 열자마자 샘플이 채워지면 곤란하다."""
    assert options()[0] == PLACEHOLDER


# ------------------------------------------------------------ 기대값 보존
def test_expected_values_are_kept_in_the_data():
    """화면에 감출 뿐, 정답 경로를 그리는 데 계속 쓴다."""
    assert len(SAMPLES) == 7

    for utterance, status, recipe_id, candidates in SAMPLES:
        assert status in VALID_STATUSES
        assert isinstance(candidates, list)
        if status == "SELECT":
            assert recipe_id and recipe_id in candidates
        else:
            assert recipe_id is None


def test_every_utterance_maps_to_its_expected():
    assert set(EXPECTED_BY_UTTERANCE) == {utterance for utterance, *_ in SAMPLES}

    for utterance, status, recipe_id, candidates in SAMPLES:
        expected = EXPECTED_BY_UTTERANCE[utterance]
        assert expected == {
            "status": status,
            "recipe_id": recipe_id,
            "candidate_recipe_ids": candidates,
        }


def test_utterances_are_unique():
    """중복이 있으면 콤보박스에서 어느 쪽이 골렸는지 알 수 없다."""
    utterances = [utterance for utterance, *_ in SAMPLES]

    assert len(utterances) == len(set(utterances))


def test_placeholder_is_not_a_sample():
    assert PLACEHOLDER not in EXPECTED_BY_UTTERANCE


# ------------------------------------------------------------ use_sample() 콜백
# 샘플을 고르면 그 발화가 입력란(session_state["utterance"])에 즉시 채워져야
# Run 을 바로 누를 수 있다. Streamlit 런타임 없이 검증하려고 st 를
# session_state 딕셔너리만 가진 가짜 객체로 바꿔치기한다.
import frontend.components.sample_picker as sample_picker


class FakeStreamlit:
    def __init__(self, session_state):
        self.session_state = session_state


def use_sample_with(monkeypatch, session_state):
    monkeypatch.setattr(sample_picker, "st", FakeStreamlit(session_state))
    sample_picker.use_sample()


def test_selecting_a_sample_fills_the_utterance(monkeypatch):
    utterance = SAMPLES[0][0]
    state = {"sample_choice": utterance, "utterance": ""}

    use_sample_with(monkeypatch, state)

    assert state["utterance"] == utterance


def test_selecting_every_sample_fills_the_utterance(monkeypatch):
    for utterance, *_ in SAMPLES:
        state = {"sample_choice": utterance, "utterance": ""}

        use_sample_with(monkeypatch, state)

        assert state["utterance"] == utterance


def test_selecting_placeholder_leaves_existing_utterance_alone(monkeypatch):
    """직접 입력을 고르면 이미 쓰던 글이 지워지면 안 된다."""
    state = {"sample_choice": PLACEHOLDER, "utterance": "사용자가 쓰던 글"}

    use_sample_with(monkeypatch, state)

    assert state["utterance"] == "사용자가 쓰던 글"
