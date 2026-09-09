"""대상 : llm_engine/model_config.py — 모델마다 다른 값을 파일에서 읽는다

provider · num_ctx · timeout · reason 길이 상한은 모델이 바뀌면 함께 바뀐다. 소스 상수로
두면 한 모델만 표현할 수 있어 같은 발화를 모델별로 재지 못한다.

진짜 models.yaml 을 읽지 않는다. 값이 바뀌면 함께 바뀌는 파일이라 그 내용을
단언하면 요구사항이 바뀔 때마다 빨간불이 뜬다. 임시 파일로 규칙만 본다.
"""

import pytest

import paths
from llm_engine.model_config import OLLAMA, VLLM, MissingModel, get_model_config

# **전역 기본 모델이 없다.** 어느 모델을 부를지는 역할이 정하거나 부르는 쪽이
# 이름을 댄다. 그래서 이 문서에도 default 가 없다.
DOCUMENT = """
defaults:
  provider: ollama
  num_ctx: 8192
  timeout: 180
  reason_max_length: 200

models:
  "느린모델":
    timeout: 300

  "vllm모델":
    provider: vllm
"""


@pytest.fixture
def models_file(monkeypatch, tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(DOCUMENT, encoding="utf-8", newline="\n")
    monkeypatch.setattr(paths, "MODELS_PATH", path)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    return path


def test_a_model_only_overrides_what_differs(models_file):
    """모델 항목에 적은 것만 덮고 나머지는 defaults 를 그대로 씀.

    모델마다 값 전부를 적게 하면 "timeout 만 올려보자" 가 여러 줄 수정이 되고,
    한 줄을 빠뜨리면 조용히 다른 조건으로 재게 됨.
    """
    slow = get_model_config("느린모델")

    assert slow.timeout == 300
    assert slow.num_ctx == 8192
    assert slow.reason_max_length == 200


def test_an_unlisted_model_still_runs_on_the_defaults(models_file):
    """목록에 없는 모델도 부를 수 있음. 새 모델을 한 번 재보는 데 파일을 안 고침."""
    unknown = get_model_config("처음보는모델")

    assert unknown.model == "처음보는모델"
    assert (unknown.num_ctx, unknown.timeout) == (8192, 180)


def test_nobody_naming_a_model_is_an_error_not_a_hidden_default(
    models_file, monkeypatch
):
    """아무도 모델을 안 대면 멈춤. 전역 기본으로 메우지 않음.

    한 줄짜리 기본 모델이 있으면 그 줄을 고칠 때 모든 목적이 함께 움직이고,
    어느 역할을 무엇으로 재고 있는지 파일만 보고는 알 수 없게 됨.
    """
    with pytest.raises(MissingModel):
        get_model_config()

    monkeypatch.setenv("LLM_MODEL", "환경모델")
    assert get_model_config().model == "환경모델"
    assert get_model_config("인자모델").model == "인자모델", "인자가 환경변수보다 앞선다"


def test_the_model_name_is_chosen_in_one_order_and_llm_model_is_the_only_env_name(
    models_file, monkeypatch
):
    """차례가 인자 > LLM_MODEL. 갈래가 둘뿐이어야 함.

    모델 이름은 provider 와 상관없는 값이라 환경변수 이름도 하나다. provider
    별 이름을 두면 어느 모델로 잰 것인지 응답만 보고는 못 가린다.
    """
    monkeypatch.setenv("LLM_MODEL", "환경모델")
    assert get_model_config().model == "환경모델", "환경변수만 있으면 그것"
    assert get_model_config("인자모델").model == "인자모델", "인자가 제일 앞선다"

    # provider 별 옛 이름은 안 본다. 남겨 두면 그것만 적어 둔 기계가 조용히
    # 다른 모델로 돌아도 아무 신호가 없다.
    monkeypatch.delenv("LLM_MODEL")
    monkeypatch.setenv("OLLAMA_MODEL", "옛이름모델")
    with pytest.raises(MissingModel):
        get_model_config()
    monkeypatch.delenv("OLLAMA_MODEL")


def test_the_provider_says_which_backend_this_deployment_calls(models_file):
    """provider 는 지금 배포에서 그 모델을 어느 backend 로 부르는가다. 파일이 안다.

    적지 않은 모델이 Ollama 로 가야 --model 로 새 Ollama 모델을 바로 재볼 수
    있음. Solar 처럼 다른 서버에 붙는 모델만 제 항목에 적음.

    호스트 주소는 여기가 아님. 그것은 기계마다 다르라고 환경변수임.
    """
    assert get_model_config("느린모델").provider == OLLAMA, "안 적으면 defaults"
    assert get_model_config("처음보는모델").provider == OLLAMA
    assert get_model_config("vllm모델").provider == VLLM

    # provider 를 덮어써도 나머지 defaults 는 그대로다.
    vllm_쪽 = get_model_config("vllm모델")
    assert (vllm_쪽.num_ctx, vllm_쪽.timeout, vllm_쪽.reason_max_length) == (8192, 180, 200)
