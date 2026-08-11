"""화면 설정 검증.

비율은 리허설 중에 주소창으로 바꾼다. 잘못 친 값 때문에 화면이 죽으면 안 된다.
"""

import pytest

from frontend import config


class FakeQueryParams(dict):
    """st.query_params 대역. dict 처럼 get 이 되면 된다."""


@pytest.fixture
def query(monkeypatch):
    def _set(params):
        monkeypatch.setattr(config.st, "query_params", FakeQueryParams(params))

    return _set


# ------------------------------------------------------------ 기본값
def test_defaults_when_no_query(query):
    query({})

    assert config.layout_ratios() == config.LAYOUT


def test_result_is_a_copy_not_the_module_constant(query):
    """돌려준 dict 를 고쳐도 LAYOUT 이 바뀌면 안 된다."""
    query({})
    original = config.LAYOUT["top_ratio"]

    config.layout_ratios()["top_ratio"] = 0.99

    assert config.LAYOUT["top_ratio"] == original


# ------------------------------------------------------------ 정상 오버라이드
def test_query_overrides_ratios(query):
    query({"top": "0.7", "left": "0.28"})

    ratios = config.layout_ratios()

    assert ratios["top_ratio"] == 0.7
    assert ratios["left_ratio"] == 0.28


def test_one_key_overrides_only_itself(query):
    query({"top": "0.7"})

    ratios = config.layout_ratios()

    assert ratios["top_ratio"] == 0.7
    assert ratios["left_ratio"] == config.LAYOUT["left_ratio"]


# ------------------------------------------------------------ 잘못된 값
@pytest.mark.parametrize(
    "bad",
    ["문자열", "", "0", "1", "-0.3", "1.5", "nan", "0.7abc", None, "None"],
    ids=["문자열", "빈값", "0", "1", "음수", "범위밖", "nan", "섞임", "None", "None문자열"],
)
def test_bad_values_fall_back_without_raising(query, bad):
    """주소창을 잘못 건드려도 예외 없이 기본값으로 떨어져야 한다."""
    query({"top": bad})

    assert config.layout_ratios()["top_ratio"] == config.LAYOUT["top_ratio"]


def test_missing_streamlit_runtime_still_returns_defaults(monkeypatch):
    """Streamlit 런타임 밖에서 불러도 죽지 않아야 한다."""

    class FakeSt:
        @property
        def query_params(self):
            raise RuntimeError("런타임 없음")

    monkeypatch.setattr(config, "st", FakeSt())

    assert config.layout_ratios() == config.LAYOUT


# ------------------------------------------------------------ 색
def test_new_color_is_distinct_from_the_others():
    """노드 등록 강조가 기존 색과 헷갈리면 안 된다."""
    colors = [
        config.HIGHLIGHT_COLOR,
        config.DOTTED_COLOR,
        config.PLAIN_COLOR,
        config.EXPECTED_COLOR,
        config.NEW_COLOR,
    ]

    assert len(set(colors)) == len(colors)


@pytest.fixture
def reloaded_config(monkeypatch):
    """DEMO_DEBUG 를 바꿔 config 를 다시 읽는다. 끝나면 원래대로 되돌린다.

    되돌리지 않으면 DEBUG=True 인 채로 남아 뒤따르는 테스트에 샌다.
    """
    import importlib

    def _load(env):
        if env is None:
            monkeypatch.delenv("DEMO_DEBUG", raising=False)
        else:
            monkeypatch.setenv("DEMO_DEBUG", env)
        return importlib.reload(config)

    yield _load

    monkeypatch.undo()
    importlib.reload(config)


@pytest.mark.parametrize(
    "env, expected",
    [(None, False), ("0", False), ("", False), ("true", False), ("1", True)],
    ids=["미설정", "0", "빈값", "true문자열", "1"],
)
def test_debug_only_turns_on_with_exactly_1(reloaded_config, env, expected):
    """시연에서는 꺼져 있어야 한다. 켜는 것은 DEMO_DEBUG=1 뿐이다."""
    assert reloaded_config(env).DEBUG is expected
