"""모델별 프로파일. models.yaml 을 읽는 유일한 파일.

같은 발화를 모델만 바꿔 재는 것이 측정의 전부인데, 모델이 바뀌면 함께 바뀌는
값이 있다. num_ctx 는 컨텍스트 크기에, timeout 은 응답 시간에, reason 길이
상한은 반복을 끊는 데 걸린다. 셋을 소스 상수로 두면 모델 하나만 표현할 수 있다.

값의 근거는 NOTES.md 에 있다. 여기서는 읽어서 넘기기만 한다.
"""

import os
from dataclasses import dataclass

import yaml

import paths


@dataclass(frozen=True)
class ModelProfile:
    """모델 하나를 부를 때 쓰는 값들."""

    model: str
    num_ctx: int
    timeout: float
    reason_max_length: int


def _document() -> dict:
    return yaml.safe_load(paths.MODELS_PATH.read_text(encoding="utf-8"))


def profile(model: str | None = None) -> ModelProfile:
    """모델 하나의 프로파일.

    입력  모델 이름. None 이면 기본 모델
    출력  ModelProfile
    규칙  기본 모델은 환경변수 OLLAMA_MODEL 이 있으면 그것, 없으면
          models.yaml 의 default
          defaults 위에 그 모델 항목을 덮어씀
          목록에 없는 모델은 defaults 를 그대로 씀. 새 모델을 한 번 재보는 데
          파일을 안 고쳐도 됨
          호출할 때마다 파일을 읽음. 서버를 띄운 채 값을 고쳐 다시 잴 수 있음
    제약  값을 캐시하지 않는다.
          측정 중에 값을 고치고 다시 재는 것이 이 파일의 용도임
    """
    document = _document()
    name = model or os.environ.get("OLLAMA_MODEL") or document["default"]
    overrides = (document.get("models") or {}).get(name) or {}
    return ModelProfile(model=name, **{**document["defaults"], **overrides})
