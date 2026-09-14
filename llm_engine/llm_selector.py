"""역할 설정을 LLM 객체로 바꾸는 유일한 자리.

프로덕션은 여기만 부른다. 부르는 쪽은 provider 를 모르고
`generate(prompt, response_schema)` 하나만 안다.

    get_role_config(역할)            manifest · prompt · schema 한 벌 (role_config)
      → get_llm_for(role)
      → role.provider                ollama | vllm
      → OllamaProvider | VllmProvider

역할 설정은 부르는 쪽이 이미 읽어 두었다. 여기서 다시 읽으면 한 요청 안에서
모델과 prompt 가 서로 다른 판의 값으로 도는 자리가 생긴다.

registry 나 factory 틀을 만들지 않았다. provider 가 둘뿐이라 명시적인 분기가
더 읽힌다.
"""

from llm_engine.providers import ollama, vllm
from llm_engine.role_config import OLLAMA, VLLM


class UnknownProvider(ValueError):
    """역할 설정에 아는 provider 가 아닌 것이 적혔다."""


def get_llm_for(role):
    """이미 읽어 둔 역할 설정으로 LLM 객체 가져옴.

    입력  RoleConfig. get_role_config 가 돌려준 그것
    출력  generate(prompt, response_schema) 를 가진 객체
    규칙  물리 모델 이름과 inference 값은 role 에 적힌 그대로 provider 에 감
    제약  모르는 provider 를 Ollama 로 떨어뜨리지 않는다.
          오타 하나가 조용히 딴 모델을 불러 측정이 어느 길로 갔는지 모르게 됨
          역할 설정을 여기서 다시 읽지 않는다.
          부르는 쪽이 넘긴 한 벌과 다른 판의 값이 섞임
    """
    if role.provider == OLLAMA:
        return ollama.OllamaProvider(ollama.config_for(role))
    if role.provider == VLLM:
        return vllm.VllmProvider(vllm.config_for(role))

    raise UnknownProvider(
        f"역할 {role.role!r} 의 provider 를 모른다: {role.provider!r} "
        f"(모델 {role.model!r}). 아는 것은 {OLLAMA!r} · {VLLM!r} 뿐이다."
    )
