"""역할 설정. llm_engine/roles/ 를 읽는 유일한 파일.

**역할 하나가 logical model 하나다.** 애플리케이션이 LLM 을 부르는 목적
(resolve · node_registration)마다 무엇으로 · 어떻게 · 무엇을 묻고 · 어떤 모양으로
받는지가 한 판으로 묶인다.

    roles/<역할>/<역할>.yaml                       manifest. 아래를 이름과 판으로 가리킴
      version                                     logical model 판
      model.provider · model.name                 어느 backend 의 어느 물리 모델
      inference                                   provider 가 요청에 싣는 값
      prompt_version           -> prompts/v<N>.yaml           template
      response_schema_version  -> response_schemas/v<N>.yaml  JSON Schema 그대로

경로를 manifest 에 적지 않는다. 역할 이름과 판 번호가 위치를 정한다.
manifest 의 값 중 하나라도 뜻을 갖고 바꾸면 version 을 올린다.

**어디에 붙는가**(OLLAMA_URL · VLLM_URL)는 기계마다 다르므로 여기 없다.
provider 가 부를 설정을 만들 때 endpoints 에서 읽는다.

**캐시하지 않는다.** 서버를 띄운 채 manifest · prompt · schema 를 고치면 다음
요청부터 반영된다. 대신 get_role_config 한 번이 셋을 함께 읽어 한 벌로 돌려주고,
부르는 쪽은 한 요청 안에서 그 한 벌을 끝까지 넘긴다.
"""

from dataclasses import dataclass

import yaml

import paths

OLLAMA = "ollama"
VLLM = "vllm"

# 애플리케이션이 LLM 을 부르는 목적. roles/ 아래 폴더 이름과 같은 글자다.
#
# **둘뿐이다.** 계기판과 시험이 LLM 을 부르는 것은 이 둘 중 하나를 재는 것이지
# 새 역할이 아니다. 역할을 더하려면 그 목적으로 LLM 을 부르는 애플리케이션
# 코드가 먼저 있어야 한다.
RESOLVE = "resolve"
NODE_REGISTRATION = "node_registration"

# provider 마다 inference 에 적는 값. 더 적거나 덜 적으면 오류다.
# vLLM 에 num_ctx 가 없는 것은 컨텍스트를 서버가 --max-model-len 으로 정해서다.
INFERENCE_KEYS = {
    OLLAMA: ("num_ctx", "timeout"),
    VLLM: ("timeout",),
}


@dataclass(frozen=True)
class RoleConfig:
    """역할 하나의 logical model 한 벌. 한 번 읽은 그대로임."""

    role: str
    version: int
    model: str
    provider: str
    inference: dict
    prompt_version: int
    response_schema_version: int
    prompt: str
    response_schema: dict


class UnknownRole(ValueError):
    """roles/ 에 없는 역할을 불렀다."""


class InvalidRoleConfig(ValueError):
    """역할 설정이 쓸 수 없는 값을 담고 있다."""


def _read_mapping(path, what: str) -> dict:
    """YAML 파일 하나를 맵으로 읽음.

    규칙  파일이 없거나 맵이 아니면 InvalidRoleConfig. 무엇이 어디서 틀렸는지 적음
    """
    if not path.is_file():
        raise InvalidRoleConfig(f"{what} 파일이 없다: {path}")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise InvalidRoleConfig(f"{what} 이 맵이 아니다: {path}")
    return document


def _version(manifest: dict, key: str, role: str) -> int:
    """판 번호 하나. 1 이상의 정수만 받음."""
    value = manifest.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidRoleConfig(
            f"{role}.yaml 의 {key} 는 1 이상의 정수여야 한다: {value!r}"
        )
    return value


def _inference(manifest: dict, provider: str, role: str) -> dict:
    """provider 에 맞는 inference 값.

    규칙  provider 가 아는 것(ollama · vllm)이 아니면 InvalidRoleConfig
          INFERENCE_KEYS 의 값을 빠짐없이, 그것만 적어야 함
          값은 0 보다 큰 숫자. num_ctx 는 정수
    제약  모르는 provider 를 Ollama 로 떨어뜨리지 않는다.
          오타 하나가 조용히 딴 서버를 불러 어느 길로 갔는지 모르게 됨
          vLLM 역할에 num_ctx 를 받아 두지 않는다.
          요청에 안 실리는 값이 적혀 있으면 그것이 먹는다고 읽힘
    """
    if provider not in INFERENCE_KEYS:
        raise InvalidRoleConfig(
            f"{role}.yaml 의 model.provider 를 모른다: {provider!r}. "
            f"아는 것은 {' · '.join(INFERENCE_KEYS)} 뿐이다."
        )
    inference = manifest.get("inference")
    if not isinstance(inference, dict):
        raise InvalidRoleConfig(f"{role}.yaml 에 inference 맵이 없다")

    expected = INFERENCE_KEYS[provider]
    missing = [key for key in expected if key not in inference]
    extra = [key for key in inference if key not in expected]
    if missing or extra:
        raise InvalidRoleConfig(
            f"{role}.yaml 의 inference 가 {provider} 와 안 맞는다. "
            f"적을 것 {list(expected)} · 빠진 것 {missing} · 더 적은 것 {extra}"
        )
    for key, value in inference.items():
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not number or value <= 0 or (key == "num_ctx" and not isinstance(value, int)):
            raise InvalidRoleConfig(
                f"{role}.yaml 의 inference.{key} 가 쓸 수 없는 값이다: {value!r}"
            )
    return dict(inference)


def get_role_config(role: str) -> RoleConfig:
    """역할 하나의 설정. manifest · prompt · response schema 가 함께 옴.

    입력  역할 이름(RESOLVE · NODE_REGISTRATION)
    출력  RoleConfig
    규칙  roles/<역할>/<역할>.yaml 을 읽음. 폴더가 없으면 UnknownRole
          manifest 의 role 은 폴더 이름과 같아야 함
          prompt 는 prompts/v<prompt_version>.yaml 의 template,
          schema 는 response_schemas/v<response_schema_version>.yaml 전체임
          잘못된 값은 전부 InvalidRoleConfig. 무엇이 틀렸는지 문장에 적음
          부를 때마다 파일을 새로 읽음. 한 번 부르면 셋을 한 벌로 묶어 돌려줌
    제약  값을 캐시하지 않는다.
          서버를 띄운 채 설정을 고치고 다음 요청에서 다시 재는 것이 용도임
          물리 모델을 인자나 환경변수로 갈아 끼우지 않는다.
          요청 하나가 manifest 와 다른 모델로 돌면 무엇을 쟀는지 파일로 못 읽음
          부르지 않은 역할을 검사하지 않는다.
          역할 하나가 잘못됐다고 상관없는 자리가 통째로 죽으면 안 됨
    """
    role_dir = paths.ROLES_DIR / role
    if not role or not role_dir.is_dir():
        known = sorted(p.name for p in paths.ROLES_DIR.iterdir() if p.is_dir())
        raise UnknownRole(
            f"llm_engine/roles 에 {role!r} 이 없다. 있는 것은 {known or '없음'} 뿐이다."
        )

    manifest = _read_mapping(role_dir / f"{role}.yaml", f"{role} manifest")
    if manifest.get("role") != role:
        raise InvalidRoleConfig(
            f"{role}.yaml 의 role 이 폴더 이름과 다르다: {manifest.get('role')!r}"
        )
    version = _version(manifest, "version", role)

    model = manifest.get("model")
    if not isinstance(model, dict):
        raise InvalidRoleConfig(f"{role}.yaml 에 model 맵이 없다")
    name, provider = model.get("name"), model.get("provider")
    if not isinstance(name, str) or not name:
        raise InvalidRoleConfig(f"{role}.yaml 에 model.name 이 없다")
    if not isinstance(provider, str) or not provider:
        raise InvalidRoleConfig(f"{role}.yaml 에 model.provider 가 없다")
    inference = _inference(manifest, provider, role)

    prompt_version = _version(manifest, "prompt_version", role)
    schema_version = _version(manifest, "response_schema_version", role)

    prompt_file = _read_mapping(
        role_dir / "prompts" / f"v{prompt_version}.yaml", f"{role} prompt"
    )
    template = prompt_file.get("template")
    if not isinstance(template, str) or not template.strip():
        raise InvalidRoleConfig(
            f"{role} 의 prompts/v{prompt_version}.yaml 에 template 이 없다"
        )

    response_schema = _read_mapping(
        role_dir / "response_schemas" / f"v{schema_version}.yaml", f"{role} response schema"
    )
    if not isinstance(response_schema.get("required"), list):
        raise InvalidRoleConfig(
            f"{role} 의 response_schemas/v{schema_version}.yaml 에 required 목록이 없다. "
            "응답에서 남길 key 를 거기서 읽는다."
        )

    return RoleConfig(
        role=role,
        version=version,
        model=name,
        provider=provider,
        inference=inference,
        prompt_version=prompt_version,
        response_schema_version=schema_version,
        prompt=template,
        response_schema=response_schema,
    )
