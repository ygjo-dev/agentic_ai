"""되묻기 뒤에 고르는 것.

LLM 도 온톨로지도 안 부른다. 기억해 둘 후보를 손으로 만들어 넣고
「고르기인가」만 본다.

**고르기로 봐서는 안 되는 꼴이 더 중요하다.** 멀쩡한 새 발화를 고르기로
오해하면 사람이 묻지도 않은 도구가 돌고, 그것이 지금 화면에서 일어나는 일보다
나쁘다. 그래서 아래 부정 시험이 긍정 시험보다 많다.
"""

import pytest

from app.api.services import clarify_service

# 화면에 실제로 나온 되묻기 하나. 「청주시 인구 알려줘」의 후보 넷이다.
#
#   여러 가지로 해석됩니다. 어느 것을 보시겠습니까?
#     1  인구 통계 조회
#     2  장소 좌표 변환 -> 인구 통계 조회
#     3  연령별 인구 구성 조회
#     4  인구 변화 추이 조회
RECIPE_IDS = ["recipe_011", "recipe_041", "recipe_045", "recipe_046"]
LABELS = [
    "인구 통계 조회",
    "장소 좌표 변환 -> 인구 통계 조회",
    "연령별 인구 구성 조회",
    "인구 변화 추이 조회",
]
NAMES = [
    "인구 통계 조회",
    "인구 통계 조회",
    "연령별 인구 구성 조회",
    "인구 변화 추이 조회",
]


@pytest.fixture(autouse=True)
def empty_memory():
    """시험끼리 세션을 안 물려받게 함."""
    clarify_service.clear()
    yield
    clarify_service.clear()


def pending(**overrides):
    """기억해 둔 되묻기 하나."""
    return {
        "recipe_ids": list(RECIPE_IDS),
        "labels": list(LABELS),
        "names": list(NAMES),
        "argument": "청주시",
        "given": "spoken_place",
        "text": "청주시 인구 알려줘",
        "at": 0.0,
        **overrides,
    }


# ── 고르기로 봐야 하는 것 ──────────────────────────────────────────
@pytest.mark.parametrize(
    "spoken, index",
    [
        ("1", 0),
        ("2번", 1),
        ("1번요", 0),
        ("3번이요", 2),
        ("4.", 3),
        (" 2 ", 1),
    ],
    ids=["번호만", "번호와_번", "번호와_요", "번호와_이요", "마침표", "앞뒤_공백"],
)
def test_saying_only_the_number_picks_that_position(spoken, index):
    """화면에 번호가 보이므로 사람은 번호로 답한다. 이것이 기본 꼴임."""
    assert clarify_service.pick(spoken, pending()) == index


@pytest.mark.parametrize(
    "spoken, index",
    [
        ("1 인구 통계 조회", 0),
        ("2 장소 좌표 변환 -> 인구 통계 조회", 1),
        ("3 연령별 인구 구성 조회", 2),
        ("2번 인구 통계 조회", 1),
    ],
    ids=["화면_줄_그대로", "사슬_줄_그대로", "셋째_줄", "번호에_번이_붙은_것"],
)
def test_saying_the_number_together_with_the_name_picks_that_position(spoken, index):
    """화면 줄을 그대로 되뇌는 사람이 있음. 지금은 그것이 새 발화로 처리됐음."""
    assert clarify_service.pick(spoken, pending()) == index


def test_a_chain_line_matches_from_its_number_with_only_the_tail_name():
    """"장소 좌표 변환 -> 인구 통계 조회" 를 통째로 옮겨 적는 사람은 없음."""
    assert clarify_service.pick("2 인구 통계 조회", pending()) == 1


def test_the_name_alone_picks_when_it_matches_only_one_candidate():
    """번호를 안 보고 이름을 말하는 사람도 있음. 하나로 좁혀질 때만 받음."""
    assert clarify_service.pick("연령별 인구 구성 조회", pending()) == 2


@pytest.mark.parametrize(
    "spoken, index",
    [("첫 번째", 0), ("두번째", 1), ("세 번째", 2), ("네번째요", 3)],
    ids=["첫", "두", "세", "네"],
)
def test_ordinal_words_are_accepted_too(spoken, index):
    """전체가 차례말일 때만 받음. "첫 번째 역이 어디야" 는 아래에서 안 걸림."""
    assert clarify_service.pick(spoken, pending()) == index


# ── 고르기로 봐서는 안 되는 것 ★ ──────────────────────────────────
@pytest.mark.parametrize(
    "spoken",
    [
        "1호선 지하철역 알려줘",
        "2호선 CCTV 보여줘",
        "1번 출구 근처 충전소",
    ],
    ids=["1호선", "2호선", "1번_출구"],
)
def test_starting_with_a_digit_is_a_new_utterance_when_the_rest_is_not_a_candidate_name(spoken):
    """숫자로 시작하는 멀쩡한 발화가 많음. 번호만으로 고르기로 보면 안 됨."""
    assert clarify_service.pick(spoken, pending()) is None


@pytest.mark.parametrize(
    "spoken",
    [
        "인구 통계 조회 방법 알려줘",
        "연령별 인구 구성 조회해줘",
        "청주시 인구 통계 조회",
    ],
    ids=["방법_알려줘", "조회해줘", "장소가_앞에"],
)
def test_containing_a_name_is_a_new_utterance_unless_it_matches_entirely(spoken):
    """담고 있는 것으로 보면 이름이 든 어떤 발화도 삼켜짐."""
    assert clarify_service.pick(spoken, pending()) is None


def test_a_number_outside_the_candidate_count_is_not_a_choice():
    """후보가 넷인데 "9번" 이면 무엇을 고른 것인지 알 수 없음."""
    assert clarify_service.pick("9번", pending()) is None
    assert clarify_service.pick("0", pending()) is None


def test_a_name_matching_several_candidates_is_not_a_choice():
    """"인구 통계 조회" 는 1번과 2번의 끝 이름임. 무엇을 고른 것인지 모름."""
    assert clarify_service.pick("인구 통계 조회", pending()) is None


def test_an_ordinal_word_at_the_front_of_an_utterance_is_a_new_utterance():
    """전체 일치만 받는 근거. 이것이 걸리면 차례말을 넣을 수 없음."""
    assert clarify_service.pick("첫 번째 역이 어디야", pending()) is None
    assert clarify_service.pick("두번째 CCTV 보여줘", pending()) is None


def test_an_empty_utterance_is_not_a_choice():
    assert clarify_service.pick("", pending()) is None
    assert clarify_service.pick("   ", pending()) is None


def test_no_phrase_is_a_choice_when_the_candidates_are_empty():
    """고를 것이 없는데 번호를 받으면 IndexError 로 죽음."""
    assert clarify_service.pick("1", pending(recipe_ids=[], labels=[], names=[])) is None


# ── 기억해 두는 자리 ───────────────────────────────────────────────
def test_taking_what_was_stored_clears_it():
    """되묻기는 한 번 주고받는 일임. 고른 뒤에 남으면 두 번 실행됨."""
    clarify_service.remember(
        "s1", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given="spoken_place", text="청주시 인구 알려줘",
    )

    assert clarify_service.take("s1") is not None
    assert clarify_service.take("s1") is None


def test_an_empty_session_string_neither_remembers_nor_takes():
    """저쪽 화면이 세션을 안 보내면 지금까지와 똑같이 동작해야 함."""
    clarify_service.remember(
        "", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given=None, text="청주시 인구 알려줘",
    )

    assert clarify_service.take("") is None


def test_a_different_session_cannot_take_another_ones_clarify():
    clarify_service.remember(
        "s1", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given=None, text="청주시 인구 알려줘",
    )

    assert clarify_service.take("s2") is None
    assert clarify_service.take("s1") is not None


def test_there_is_nothing_to_take_when_there_was_no_clarify():
    """직전에 되묻기가 없으면 "1번" 도 새 발화임."""
    assert clarify_service.take("s1") is None


def test_an_old_clarify_counts_as_absent(monkeypatch):
    """화면을 띄워두고 자리를 비웠다가 돌아와 다른 것을 묻는 자리임."""
    clock = [1000.0]
    monkeypatch.setattr(clarify_service.time, "monotonic", lambda: clock[0])

    clarify_service.remember(
        "s1", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given=None, text="청주시 인구 알려줘",
    )
    clock[0] += clarify_service.TTL_SECONDS + 1

    assert clarify_service.take("s1") is None


def test_within_the_TTL_it_is_taken_unchanged(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(clarify_service.time, "monotonic", lambda: clock[0])

    clarify_service.remember(
        "s1", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given=None, text="청주시 인구 알려줘",
    )
    clock[0] += clarify_service.TTL_SECONDS - 1

    assert clarify_service.take("s1") is not None


def test_exceeding_the_session_cap_evicts_the_oldest_first():
    """세션이 언제 끝나는지 우리는 모름. 상한이 없으면 무한히 늚."""
    for index in range(clarify_service.MAX_SESSIONS + 3):
        clarify_service.remember(
            f"s{index}", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
            argument="청주시", given=None, text="청주시 인구 알려줘",
        )

    assert clarify_service.take("s0") is None
    assert clarify_service.take("s2") is None
    assert clarify_service.take(f"s{clarify_service.MAX_SESSIONS + 2}") is not None


def test_storing_again_in_the_same_session_overwrites():
    """직전 되묻기 하나임. 두 발화 전의 후보가 살아 있으면 안 됨."""
    clarify_service.remember(
        "s1", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given=None, text="청주시 인구 알려줘",
    )
    clarify_service.remember(
        "s1", recipe_ids=["recipe_012"], labels=["전기차 충전소 검색"],
        names=["전기차 충전소 검색"], argument="전기차 충전소",
        given="spoken_keyword", text="전기차 충전소 데이터 검색해줘",
    )

    assert clarify_service.take("s1")["recipe_ids"] == ["recipe_012"]


def test_empty_candidates_are_not_stored():
    """NO_MATCH 는 화면에 번호를 안 보임. 고를 것이 없음."""
    clarify_service.remember(
        "s1", recipe_ids=[], labels=[], names=[],
        argument="", given=None, text="오늘 날씨",
    )

    assert clarify_service.take("s1") is None


# ── 스위치 ──────────────────────────────────────────────────────────


def test_no_env_var_means_on(monkeypatch):
    """기본이 켬임. 지금 동작을 지킴."""
    monkeypatch.delenv(clarify_service.CHOICE_ENV, raising=False)

    assert clarify_service.enabled() is True


def test_the_env_var_being_0_means_off(monkeypatch):
    monkeypatch.setenv(clarify_service.CHOICE_ENV, "0")

    assert clarify_service.enabled() is False


def test_any_value_other_than_0_means_on(monkeypatch):
    """끄는 값은 "0" 하나임. 오타로 꺼지지 않아야 함."""
    for value in ["1", "true", "off", ""]:
        monkeypatch.setenv(clarify_service.CHOICE_ENV, value)
        assert clarify_service.enabled() is True
