"""역할과 모델 설정. models.yaml 을 읽는 유일한 파일.

**역할과 모델은 다른 것이다.** 역할은 애플리케이션이 LLM 을 부르는 목적이고
(resolve · node_registration), 모델은 그 목적을 무엇으로 이루는가다. 둘을 한
이름으로 쓰면 모델을 바꿀 때 부르는 쪽의 뜻까지 바뀐 것처럼 읽힌다.

    역할 → (model) → 물리 모델 → provider → provider client
    역할 → prompt


같은 발화를 모델만 바꿔 재는 것이 측정의 전부인데, 모델이 바뀌면 함께 바뀌는
값이 있다. num_ctx 는 컨텍스트 크기에, timeout 은 응답 시간에, reason 길이
상한은 반복을 끊는 데 걸린다. 셋을 소스 상수로 두면 모델 하나만 표현할 수 있다.

provider 도 여기서 갈린다. qwen 은 Ollama 에, Solar 는 vLLM 에 붙는다 —
지금 배포에서 그 모델을 어느 backend 로 부르는가이므로 모델마다 적는 설정이고
models.yaml 이 갖는다. **어디에 붙는가**(host)는 기계마다 다르므로 환경변수이고
provider 안에 있다.

값의 근거는 NOTES.md 에 있다. 여기서는 읽어서 넘기기만 한다.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

import paths

OLLAMA = "ollama"
VLLM = "vllm"

# 애플리케이션이 LLM 을 부르는 목적. models.yaml 의 roles 키와 같은 글자다.
#
# **둘뿐이다.** 계기판과 시험이 LLM 을 부르는 것은 이 둘 중 하나를 재는 것이지
# 새 역할이 아니다. 역할을 더하려면 그 목적으로 LLM 을 부르는 애플리케이션
# 코드가 먼저 있어야 한다.
RESOLVE = "resolve"
NODE_REGISTRATION = "node_registration"


@dataclass(frozen=True)
class ModelConfig:
    """모델 하나를 부를 때 쓰는 값들."""

    model: str
    provider: str
    num_ctx: int
    timeout: float
    reason_max_length: int


@dataclass(frozen=True)
class RoleConfig:
    """역할 하나가 LLM 을 부를 때 쓰는 것.

    prompt_path 를 들고 원문은 부를 때 읽음. 프롬프트를 고치고 서버를 띄운 채
    다시 재는 것이 models.yaml 값과 같은 쓰임임.
    """

    role: str
    model: ModelConfig
    prompt_path: Path

    @property
    def prompt(self) -> str:
        """그 역할이 쓰는 프롬프트 원문."""
        return self.prompt_path.read_text(encoding="utf-8")


class UnknownRole(ValueError):
    """models.yaml 의 roles 에 없는 역할을 불렀다."""


class InvalidRoleConfig(ValueError):
    """roles 항목이 쓸 수 없는 값을 담고 있다."""


def _document() -> dict:
    return yaml.safe_load(paths.MODELS_PATH.read_text(encoding="utf-8"))


def _model_config(document: dict, model: str | None, fallback: str | None) -> ModelConfig:
    """읽어 둔 문서에서 모델 하나의 설정. 파일을 다시 안 읽음."""
    name = model or os.environ.get("LLM_MODEL") or fallback or document["default"]
    overrides = (document.get("models") or {}).get(name) or {}
    return ModelConfig(model=name, **{**document["defaults"], **overrides})


def get_model_config(model: str | None = None) -> ModelConfig:
    """모델 하나의 설정.

    출력  ModelConfig
    규칙  고르는 차례는 인자 > LLM_MODEL > models.yaml 의 default
          defaults 위에 그 모델 항목을 덮어씀. provider 도 그렇게 갈림
          목록에 없는 모델은 defaults 를 그대로 씀. 새 모델을 한 번 재보는 데
          파일을 안 고쳐도 됨
    제약  값을 캐시하지 않는다.
          측정 중에 값을 고치고 서버를 띄운 채 다시 재는 것이 이 파일의 용도임
          provider 별 환경변수를 여기서 보지 않는다.
          어느 모델을 쓸지는 provider 와 상관없는 값이라 이름 하나로 받음
    """
    return _model_config(_document(), model, fallback=None)


def get_role_config(role: str, model: str | None = None) -> RoleConfig:
    """역할 하나의 설정. 모델과 프롬프트가 함께 옴.

    입력  역할 이름(RESOLVE · NODE_REGISTRATION) · 재보려는 모델(없으면 설정대로)
    출력  RoleConfig
    규칙  고르는 차례는 인자 > LLM_MODEL > 역할의 model > models.yaml 의 default.
          역할이 model 을 안 적으면 default 라 오늘 두 역할이 같은 모델로 감
          역할이 model 을 적었으면 그 이름은 models 목록에 있어야 함. 오타가
          조용히 defaults 로 떨어지면 어느 모델로 쟀는지 모르게 됨
          prompt 는 저장소 뿌리에서 본 경로임. 파일이 없으면 여기서 멈춤
          문서를 한 번만 읽음. 한 호출 안에서 앞뒤가 다른 값으로 돌면 안 됨
    제약  부르지 않은 역할을 검사하지 않는다.
          roles 하나가 잘못됐다고 상관없는 import 가 통째로 죽으면 안 됨
    """
    document = _document()
    roles = document.get("roles") or {}
    entry = roles.get(role)
    if entry is None:
        raise UnknownRole(
            f"models.yaml 의 roles 에 {role!r} 이 없다. "
            f"적힌 것은 {sorted(roles) or '없음'} 뿐이다."
        )
    if not isinstance(entry, dict):
        raise InvalidRoleConfig(f"roles.{role} 이 맵이 아니다: {entry!r}")

    written = entry.get("model")
    if written is not None and written not in (document.get("models") or {}):
        raise InvalidRoleConfig(
            f"roles.{role}.model 이 models 목록에 없다: {written!r}. "
            "적어 둔 역할의 모델은 목록에 있어야 한다 — 오타가 조용히 "
            "defaults 로 떨어지면 어느 모델로 쟀는지 모르게 된다."
        )

    written_prompt = entry.get("prompt")
    if not written_prompt:
        raise InvalidRoleConfig(f"roles.{role} 에 prompt 가 없다")
    prompt_path = paths.REPO_ROOT / written_prompt
    if not prompt_path.is_file():
        raise InvalidRoleConfig(
            f"roles.{role}.prompt 가 가리키는 파일이 없다: {prompt_path}"
        )

    return RoleConfig(
        role=role,
        model=_model_config(document, model, fallback=written),
        prompt_path=prompt_path,
    )
