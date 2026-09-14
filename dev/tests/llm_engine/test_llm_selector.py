"""대상 : llm_engine/llm_selector.py — 역할 설정을 LLM 객체로 바꾸는 유일한 자리

해석 엔진은 어떤 LLM 을 쓰는지 모른다. `generate(prompt, schema)` 하나만 아는
객체로 이야기하고, 그것이 Ollama 인지 vLLM 인지는 역할 설정의 provider 가 가른다.

역할 설정은 손으로 만든 한 벌(conftest.fake_role)을 쓴다. 역할 파일을 안 읽는다.
"""

import inspect

import pytest

import paths
from conftest import TEST_ENDPOINTS, fake_role
from llm_engine import llm_selector
from llm_engine.llm_selector import UnknownProvider, get_llm_for
from llm_engine.providers.ollama import OllamaProvider
from llm_engine.providers.vllm import VllmProvider

OLLAMA_ROLE = fake_role(
    provider="ollama", model="느린모델", inference={"num_ctx": 8192, "timeout": 900}
)
VLLM_ROLE = fake_role(provider="vllm", model="vllm모델", inference={"timeout": 300})


def test_the_provider_in_the_role_decides_which_client_comes_back():
    """역할 설정의 provider 가 구현을 고름.

    부르는 쪽은 provider 이름을 안 적음. 역할만 넘기면 됨. 그래야 역할이 backend 를
    옮겨도 부르는 코드가 안 바뀜.
    """
    assert isinstance(get_llm_for(OLLAMA_ROLE), OllamaProvider)
    assert isinstance(get_llm_for(VLLM_ROLE), VllmProvider)


def test_the_role_values_reach_the_client():
    """역할에 적힌 모델과 inference 값이 객체까지 그대로 감. host 만 환경변수에서 옴.

    vLLM 쪽에는 num_ctx 가 없음. 컨텍스트는 서버가 --max-model-len 으로 정함.
    """
    ollama_쪽 = get_llm_for(OLLAMA_ROLE).config
    assert (ollama_쪽.model, ollama_쪽.num_ctx, ollama_쪽.timeout, ollama_쪽.host) == (
        "느린모델", 8192, 900, TEST_ENDPOINTS["OLLAMA_URL"]
    )

    vllm_쪽 = get_llm_for(VLLM_ROLE).config
    assert (vllm_쪽.model, vllm_쪽.timeout, vllm_쪽.host) == (
        "vllm모델", 300, TEST_ENDPOINTS["VLLM_URL"]
    )
    assert not hasattr(vllm_쪽, "num_ctx"), "vLLM 요청에 안 실리는 값을 들고 있으면 먹는다고 읽힌다"


def test_an_unknown_provider_is_an_error_not_a_silent_fallback():
    """모르는 provider 를 Ollama 로 떨어뜨리지 않음.

    오타 하나가 조용히 딴 서버를 부르면 측정이 어느 길로 갔는지 모르게 됨.
    측정 결과가 거짓말을 하느니 부르다 죽는 것이 나음.
    """
    with pytest.raises(UnknownProvider) as 터짐:
        get_llm_for(fake_role(provider="없는프로바이더"))

    assert "없는프로바이더" in str(터짐.value), "무엇이 틀렸는지 메시지가 말해야 한다"


def test_both_providers_answer_to_the_same_call():
    """둘이 같은 이름 같은 인자를 받음.

    orchestrator 가 어느 쪽인지 모르고 부를 수 있는 근거임. 한쪽 signature 가
    갈리면 역할이 backend 를 옮길 때 부르는 코드가 함께 갈려야 함.
    """

    def signature(instance):
        return inspect.signature(instance.generate)

    assert signature(get_llm_for(OLLAMA_ROLE)) == signature(get_llm_for(VLLM_ROLE))


def test_the_selector_does_not_read_the_role_files_again(monkeypatch, tmp_path):
    """넘겨받은 한 벌로만 만듦. 역할 폴더가 없어도 됨.

    여기서 다시 읽으면 한 요청 안에서 LLM 클라이언트와 prompt · schema 가 서로
    다른 판이 되는 자리가 생김.
    """
    monkeypatch.setattr(paths, "ROLES_DIR", tmp_path / "없는폴더")

    assert isinstance(get_llm_for(VLLM_ROLE), VllmProvider)


def test_there_is_no_way_to_pick_a_model_by_name():
    """이름으로 모델을 고르는 길이 없음. 역할 manifest 가 정한 판으로만 부름.

    요청이나 도구가 이름 하나로 모델을 갈아 끼우면 무엇을 쟀는지 파일로 못 읽음.
    """
    for gone in ("get_llm", "get_model_config"):
        assert not hasattr(llm_selector, gone), f"{gone} 이 되살아났다"
