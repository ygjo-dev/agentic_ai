"""대상 : llm_engine/profiles.py — 모델마다 다른 값을 파일에서 읽는다

num_ctx · timeout · reason 길이 상한은 모델이 바뀌면 함께 바뀐다. 소스 상수로
두면 한 모델만 표현할 수 있어 같은 발화를 모델별로 재지 못한다.

진짜 models.yaml 을 읽지 않는다. 값이 바뀌면 함께 바뀌는 파일이라 그 내용을
단언하면 요구사항이 바뀔 때마다 빨간불이 뜬다. 임시 파일로 규칙만 본다.
"""

import pytest

import paths
from llm_engine.profiles import profile

DOCUMENT = """
default: "기본모델"

defaults:
  num_ctx: 8192
  timeout: 180
  reason_max_length: 200

models:
  "느린모델":
    timeout: 300
"""


@pytest.fixture
def models_file(monkeypatch, tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(DOCUMENT, encoding="utf-8", newline="\n")
    monkeypatch.setattr(paths, "MODELS_PATH", path)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    return path


def test_a_model_only_overrides_what_differs(models_file):
    """모델 항목에 적은 것만 덮고 나머지는 defaults 를 그대로 씀.

    모델마다 값 전부를 적게 하면 "timeout 만 올려보자" 가 여러 줄 수정이 되고,
    한 줄을 빠뜨리면 조용히 다른 조건으로 재게 됨.
    """
    slow = profile("느린모델")

    assert slow.timeout == 300
    assert slow.num_ctx == 8192
    assert slow.reason_max_length == 200


def test_an_unlisted_model_still_runs_on_the_defaults(models_file):
    """목록에 없는 모델도 부를 수 있음. 새 모델을 한 번 재보는 데 파일을 안 고침."""
    unknown = profile("처음보는모델")

    assert unknown.model == "처음보는모델"
    assert (unknown.num_ctx, unknown.timeout) == (8192, 180)


def test_the_default_model_comes_from_the_file_and_the_environment_wins(
    models_file, monkeypatch
):
    """인자가 없으면 파일의 default. 환경변수가 있으면 그것이 이김.

    기계마다 다른 것(어느 모델이 받아져 있나)은 환경변수로, 저장소가 아는 것은
    파일로 갈림.
    """
    assert profile().model == "기본모델"

    monkeypatch.setenv("OLLAMA_MODEL", "환경모델")
    assert profile().model == "환경모델"
    assert profile("인자모델").model == "인자모델", "인자가 환경변수보다 앞선다"
