"""어느 LLM 을 쓸지 고르는 유일한 자리.

프로덕션은 여기만 부른다. 부르는 쪽은 provider 를 모르고
`generate(prompt, response_schema)` 하나만 안다.

    get_llm(model)
      → get_model_config(model)      그 모델의 설정 (models.yaml)
      → config.provider              ollama | vllm
      → OllamaProvider | VllmProvider

registry 나 factory 틀을 만들지 않았다. provider 가 둘뿐이라 명시적인 분기가
더 읽힌다.
"""

from llm_engine.model_config import OLLAMA, VLLM, get_model_config
from llm_engine.providers import ollama, vllm


class UnknownProvider(ValueError):
    """models.yaml 에 아는 provider 가 아닌 것이 적혔다."""


def get_llm(model: str | None = None):
    """모델 이름으로 LLM 객체 가져옴.

    출력  generate(prompt, response_schema) 를 가진 객체
    규칙  provider 는 models.yaml 이 정함. 목록에 없는 모델은 defaults 를 따라
          Ollama 로 감
          모델이 다른 객체가 한 프로세스에 여럿 살 수 있음. 같은 발화를 모델만
          바꿔 재는 데 프로세스를 다시 안 띄우려는 것
          models.yaml 을 한 번만 읽어 그 ModelConfig 를 provider 에 넘김
    제약  모르는 provider 를 Ollama 로 떨어뜨리지 않는다.
          오타 하나가 조용히 딴 모델을 불러 측정이 어느 길로 갔는지 모르게 됨
    """
    config = get_model_config(model)

    if config.provider == OLLAMA:
        return ollama.OllamaProvider(ollama.config_for(found=config))
    if config.provider == VLLM:
        return vllm.VllmProvider(vllm.config_for(found=config))

    raise UnknownProvider(
        f"models.yaml 의 provider 를 모른다: {config.provider!r} "
        f"(모델 {config.model!r}). 아는 것은 {OLLAMA!r} · {VLLM!r} 뿐이다."
    )
