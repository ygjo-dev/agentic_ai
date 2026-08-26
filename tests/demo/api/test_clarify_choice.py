"""되묻기 뒤에 고르는 것.

LLM 도 온톨로지도 안 부른다. 기억해 둘 후보를 손으로 만들어 넣고
「고르기인가」만 본다.

**고르기로 봐서는 안 되는 꼴이 더 중요하다.** 멀쩡한 새 발화를 고르기로
오해하면 사람이 묻지도 않은 도구가 돌고, 그것이 지금 화면에서 일어나는 일보다
나쁘다. 그래서 아래 부정 시험이 긍정 시험보다 많다.
"""

import pytest

from demo.api.services import clarify_service

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
def test_번호만_말하면_그_자리를_고른다(spoken, index):
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
def test_번호와_이름을_함께_말하면_그_자리를_고른다(spoken, index):
    """화면 줄을 그대로 되뇌는 사람이 있음. 지금은 그것이 새 발화로 처리됐음."""
    assert clarify_service.pick(spoken, pending()) == index


def test_사슬_줄은_끝_이름만_말해도_그_자리다():
    """"장소 좌표 변환 -> 인구 통계 조회" 를 통째로 옮겨 적는 사람은 없음."""
    assert clarify_service.pick("2 인구 통계 조회", pending()) == 1


def test_이름만_말해도_후보_하나에만_걸리면_고른다():
    """번호를 안 보고 이름을 말하는 사람도 있음. 하나로 좁혀질 때만 받음."""
    assert clarify_service.pick("연령별 인구 구성 조회", pending()) == 2


@pytest.mark.parametrize(
    "spoken, index",
    [("첫 번째", 0), ("두번째", 1), ("세 번째", 2), ("네번째요", 3)],
    ids=["첫", "두", "세", "네"],
)
def test_차례말도_받는다(spoken, index):
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
def test_숫자로_시작해도_뒤가_후보_이름이_아니면_새_발화다(spoken):
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
def test_이름을_담고_있어도_통째로_같지_않으면_새_발화다(spoken):
    """담고 있는 것으로 보면 이름이 든 어떤 발화도 삼켜짐."""
    assert clarify_service.pick(spoken, pending()) is None


def test_후보_수를_벗어난_번호는_고르기가_아니다():
    """후보가 넷인데 "9번" 이면 무엇을 고른 것인지 알 수 없음."""
    assert clarify_service.pick("9번", pending()) is None
    assert clarify_service.pick("0", pending()) is None


def test_이름이_여러_후보에_걸리면_고르기가_아니다():
    """"인구 통계 조회" 는 1번과 2번의 끝 이름임. 무엇을 고른 것인지 모름."""
    assert clarify_service.pick("인구 통계 조회", pending()) is None


def test_차례말이_발화_앞에_있으면_새_발화다():
    """전체 일치만 받는 근거. 이것이 걸리면 차례말을 넣을 수 없음."""
    assert clarify_service.pick("첫 번째 역이 어디야", pending()) is None
    assert clarify_service.pick("두번째 CCTV 보여줘", pending()) is None


def test_빈_발화는_고르기가_아니다():
    assert clarify_service.pick("", pending()) is None
    assert clarify_service.pick("   ", pending()) is None


def test_후보가_비면_어떤_문구도_고르기가_아니다():
    """고를 것이 없는데 번호를 받으면 IndexError 로 죽음."""
    assert clarify_service.pick("1", pending(recipe_ids=[], labels=[], names=[])) is None


# ── 기억해 두는 자리 ───────────────────────────────────────────────
def test_남긴_것을_꺼내면_지워진다():
    """되묻기는 한 번 주고받는 일임. 고른 뒤에 남으면 두 번 실행됨."""
    clarify_service.remember(
        "s1", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given="spoken_place", text="청주시 인구 알려줘",
    )

    assert clarify_service.take("s1") is not None
    assert clarify_service.take("s1") is None


def test_세션이_빈_문자열이면_기억하지도_꺼내지도_않는다():
    """저쪽 화면이 세션을 안 보내면 지금까지와 똑같이 동작해야 함."""
    clarify_service.remember(
        "", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given=None, text="청주시 인구 알려줘",
    )

    assert clarify_service.take("") is None


def test_세션이_다르면_남의_되묻기를_못_꺼낸다():
    clarify_service.remember(
        "s1", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given=None, text="청주시 인구 알려줘",
    )

    assert clarify_service.take("s2") is None
    assert clarify_service.take("s1") is not None


def test_되묻기가_없었으면_꺼낼_것이_없다():
    """직전에 되묻기가 없으면 "1번" 도 새 발화임."""
    assert clarify_service.take("s1") is None


def test_오래된_되묻기는_없는_것으로_본다(monkeypatch):
    """화면을 띄워두고 자리를 비웠다가 돌아와 다른 것을 묻는 자리임."""
    clock = [1000.0]
    monkeypatch.setattr(clarify_service.time, "monotonic", lambda: clock[0])

    clarify_service.remember(
        "s1", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given=None, text="청주시 인구 알려줘",
    )
    clock[0] += clarify_service.TTL_SECONDS + 1

    assert clarify_service.take("s1") is None


def test_TTL_안에서는_그대로_꺼내진다(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(clarify_service.time, "monotonic", lambda: clock[0])

    clarify_service.remember(
        "s1", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
        argument="청주시", given=None, text="청주시 인구 알려줘",
    )
    clock[0] += clarify_service.TTL_SECONDS - 1

    assert clarify_service.take("s1") is not None


def test_세션_수가_상한을_넘으면_오래된_것부터_버린다():
    """세션이 언제 끝나는지 우리는 모름. 상한이 없으면 무한히 늚."""
    for index in range(clarify_service.MAX_SESSIONS + 3):
        clarify_service.remember(
            f"s{index}", recipe_ids=RECIPE_IDS, labels=LABELS, names=NAMES,
            argument="청주시", given=None, text="청주시 인구 알려줘",
        )

    assert clarify_service.take("s0") is None
    assert clarify_service.take("s2") is None
    assert clarify_service.take(f"s{clarify_service.MAX_SESSIONS + 2}") is not None


def test_같은_세션에_다시_남기면_덮어쓴다():
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


def test_후보가_비면_남기지_않는다():
    """NO_MATCH 는 화면에 번호를 안 보임. 고를 것이 없음."""
    clarify_service.remember(
        "s1", recipe_ids=[], labels=[], names=[],
        argument="", given=None, text="오늘 날씨",
    )

    assert clarify_service.take("s1") is None
