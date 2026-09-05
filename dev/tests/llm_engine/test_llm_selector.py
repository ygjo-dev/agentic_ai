"""대상 : llm_engine/llm_selector.py — 어느 LLM 을 쓸지 고르는 유일한 자리

해석 엔진은 어떤 LLM 을 쓰는지 모른다. `generate(prompt, schema)` 하나만 아는
객체로 이야기하고, 그것이 Ollama 인지 vLLM 인지는 여기서 갈린다.

진짜 models.yaml 을 읽지 않는다. 값이 바뀌면 함께 바뀌는 파일이라 그 내용을
단언하면 요구사항이 바뀔 때마다 빨간불이 뜬다. 임시 파일로 규칙만 본다.
"""

import pytest

import paths
from llm_engine.llm_selector import UnknownProvider, get_llm
from llm_engine.providers.ollama import OllamaProvider
from llm_engine.providers.vllm import VllmProvider

DOCUMENT = """
default: "기본모델"

defaults:
  provider: ollama
  num_ctx: 8192
  timeout: 180
  reason_max_length: 200

models:
  "저쪽서버모델":
    provider: vllm
    timeout: 300

  "엉뚱한모델":
    provider: 없는프로바이더
"""


@pytest.fixture
def models_file(monkeypatch, tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(DOCUMENT, encoding="utf-8", newline="\n")
    monkeypatch.setattr(paths, "MODELS_PATH", path)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    return path


def test_the_provider_in_the_file_decides_which_client_comes_back(models_file):
    """models.yaml 의 provider 가 구현을 고름.

    부르는 쪽은 provider 이름을 안 적음. 모델 이름만 대면 됨 — 그래야
    같은 발화를 모델만 바꿔 재는 데 부르는 코드가 안 바뀜.
    """
    assert isinstance(get_llm("저쪽서버모델"), VllmProvider)
    assert isinstance(get_llm("기본모델"), OllamaProvider)


def test_an_unlisted_model_still_goes_to_ollama(models_file):
    """목록에 없는 모델은 defaults 를 따름.

    --model qwen2.5:7b 처럼 새 Ollama 모델을 한 번 재보는 데 파일을 안 고쳐도
    되는 동작임. provider 를 더하면서 이것이 깨지면 안 됨.
    """
    assert isinstance(get_llm("처음보는모델"), OllamaProvider)
    assert isinstance(get_llm(), OllamaProvider), "인자가 없으면 파일의 default"


def test_the_chosen_model_reaches_the_client(models_file):
    """고른 모델과 그 모델의 값이 객체까지 그대로 감.

    모델이 다른 객체가 한 프로세스에 여럿 살아야 함. 전역 상수를 읽으면
    그게 안 됨.
    """
    저쪽 = get_llm("저쪽서버모델")
    assert 저쪽.config.model == "저쪽서버모델"
    assert 저쪽.config.timeout == 300, "모델 항목이 defaults 를 덮음"

    이쪽 = get_llm("처음보는모델")
    assert (이쪽.config.model, 이쪽.config.num_ctx) == ("처음보는모델", 8192)


def test_an_unknown_provider_is_an_error_not_a_silent_fallback(models_file):
    """모르는 provider 를 Ollama 로 떨어뜨리지 않음.

    오타 하나가 조용히 딴 서버를 부르면 측정이 어느 길로 갔는지 모르게 됨.
    성적표가 거짓말을 하느니 부르다 죽는 것이 나음.
    """
    with pytest.raises(UnknownProvider) as 터짐:
        get_llm("엉뚱한모델")

    assert "없는프로바이더" in str(터짐.value), "무엇이 틀렸는지 메시지가 말해야 한다"


def test_both_providers_answer_to_the_same_call(models_file):
    """둘이 같은 이름 같은 인자를 받음.

    orchestrator 가 어느 쪽인지 모르고 부를 수 있는 근거임. 한쪽 signature 가
    갈리면 모델을 바꿀 때 부르는 코드가 함께 갈려야 함.
    """
    import inspect

    def signature(instance):
        return inspect.signature(instance.generate)

    assert signature(get_llm("기본모델")) == signature(get_llm("저쪽서버모델"))
