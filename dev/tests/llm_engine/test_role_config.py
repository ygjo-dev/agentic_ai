"""대상 : llm_engine/model_config.py 의 역할 설정 — 왜 부르는가와 무엇으로 부르는가

**역할은 모델 이름이 아니다.** 역할은 애플리케이션이 LLM 을 부르는 목적이고
(resolve · node_registration), 모델은 그 목적을 무엇으로 이루는가다. 둘을 한
이름으로 쓰면 모델을 바꿀 때 부르는 쪽의 뜻까지 바뀐 것처럼 읽힌다.

진짜 models.yaml 의 값을 단언하지 않는다. 값이 바뀌면 함께 바뀌는 파일이라
그 내용을 못 박으면 요구사항이 바뀔 때마다 빨간불이 뜬다. 임시 파일로 규칙만
보고, 실물 파일에서는 **지금 살아 있는 역할이 실제로 풀리는지**만 본다.
"""

import pytest

import paths
from llm_engine.model_config import (
    NODE_REGISTRATION,
    RESOLVE,
    InvalidRoleConfig,
    UnknownRole,
    get_role_config,
)

DOCUMENT = """
roles:
  역할하나:
    prompt: {하나}
  역할둘:
    model: "vllm모델"
    prompt: {둘}

default: "기본모델"

defaults:
  provider: ollama
  num_ctx: 8192
  timeout: 180
  reason_max_length: 200

models:
  "vllm모델":
    provider: vllm
    timeout: 300
"""


@pytest.fixture
def models_file(monkeypatch, tmp_path):
    """역할 둘이 적힌 임시 models.yaml. 프롬프트 파일도 실제로 만들어 둔다."""
    하나 = tmp_path / "하나.md"
    둘 = tmp_path / "둘.md"
    하나.write_text("프롬프트 하나", encoding="utf-8", newline="\n")
    둘.write_text("프롬프트 둘", encoding="utf-8", newline="\n")

    path = tmp_path / "models.yaml"
    path.write_text(
        DOCUMENT.format(하나=하나.name, 둘=둘.name), encoding="utf-8", newline="\n"
    )
    monkeypatch.setattr(paths, "MODELS_PATH", path)
    monkeypatch.setattr(paths, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    return path


def test_a_role_carries_its_model_and_its_prompt(models_file):
    """역할 하나를 물으면 모델과 프롬프트가 함께 옴.

    부르는 쪽이 물리 모델 이름을 적지 않고 「이 역할로 부른다」만 말하게 하는
    자리임. 둘을 따로 물으면 그 사이에 파일이 바뀔 수 있음.
    """
    role = get_role_config("역할하나")

    assert role.role == "역할하나"
    assert role.model.model == "기본모델", "model 을 안 적으면 default"
    assert role.prompt == "프롬프트 하나"


def test_a_role_may_pin_its_own_model(models_file):
    """역할마다 다른 모델을 쓸 수 있음.

    오늘 둘이 같은 모델을 쓰는 것은 사실이지 규칙이 아님. 한 역할만 옮길 수
    있어야 「역할과 모델이 갈렸다」가 참이 됨.
    """
    role = get_role_config("역할둘")

    assert role.model.model == "vllm모델"
    assert role.model.provider == "vllm", "모델이 provider 를 정한다"
    assert role.model.timeout == 300, "모델 항목이 defaults 를 덮는다"
    assert role.prompt == "프롬프트 둘"


def test_the_argument_and_the_environment_still_win(models_file, monkeypatch):
    """모델을 갈아 재는 길이 역할 때문에 막히지 않음.

    차례는 인자 > LLM_MODEL > 역할의 model > default. 같은 발화를 모델만 바꿔
    재는 것이 이 저장소 측정의 전부라 그 길이 살아 있어야 함.
    """
    assert get_role_config("역할둘", "인자모델").model.model == "인자모델"

    monkeypatch.setenv("LLM_MODEL", "환경모델")
    assert get_role_config("역할둘").model.model == "환경모델"
    assert get_role_config("역할둘", "인자모델").model.model == "인자모델"


def test_an_unknown_role_says_what_is_written(models_file):
    """없는 역할은 오류. 무엇이 적혀 있는지 문장에 있어야 함.

    역할 이름을 잘못 적었을 때 조용히 기본 모델로 돌면 어느 목적으로 불렀는지
    표에서 사라짐.
    """
    with pytest.raises(UnknownRole) as 터짐:
        get_role_config("없는역할")

    assert "없는역할" in str(터짐.value)
    assert "역할하나" in str(터짐.value), "무엇이 적혀 있는지 알려줘야 한다"


def test_a_role_model_that_is_not_listed_is_an_error(models_file, tmp_path):
    """역할이 적어 둔 모델은 models 목록에 있어야 함.

    오타가 조용히 defaults(ollama)로 떨어지면 어느 모델로 쟀는지 모르게 됨.
    목록에 없는 모델을 한 번 재보는 길은 --model 로 열려 있음.
    """
    (tmp_path / "models.yaml").write_text(
        DOCUMENT.format(하나="하나.md", 둘="둘.md").replace(
            'model: "vllm모델"', 'model: "오타모델"'
        ),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(InvalidRoleConfig) as 터짐:
        get_role_config("역할둘")

    assert "오타모델" in str(터짐.value)


def test_a_missing_prompt_file_is_an_error(models_file, tmp_path):
    """프롬프트가 가리키는 파일이 없으면 부르기 전에 멈춤.

    빈 프롬프트로 LLM 을 부르면 답이 이상한 것이 프롬프트 탓인지 모델 탓인지
    안 갈림.
    """
    (tmp_path / "models.yaml").write_text(
        DOCUMENT.format(하나="없는파일.md", 둘="둘.md"), encoding="utf-8", newline="\n"
    )

    with pytest.raises(InvalidRoleConfig) as 터짐:
        get_role_config("역할하나")

    assert "없는파일.md" in str(터짐.value)


def test_a_broken_role_does_not_break_the_others(models_file, tmp_path):
    """부르지 않은 역할은 검사하지 않음.

    roles 하나가 잘못됐다고 상관없는 자리가 통째로 죽으면, 쓰지도 않는 설정
    한 줄 때문에 애플리케이션이 안 뜨는 구조가 됨.
    """
    (tmp_path / "models.yaml").write_text(
        DOCUMENT.format(하나="없는파일.md", 둘="둘.md"), encoding="utf-8", newline="\n"
    )

    assert get_role_config("역할둘").prompt == "프롬프트 둘"


def test_the_file_is_read_once_per_call(models_file, monkeypatch):
    """역할 하나를 푸는 데 models.yaml 을 한 번만 읽음.

    두 번 읽으면 재는 중에 파일을 고쳤을 때 한 호출 안에서 모델과 프롬프트가
    서로 다른 판의 값이 되는 자리가 생김.
    """
    from llm_engine import model_config

    reads = []
    real = model_config._document
    monkeypatch.setattr(
        model_config, "_document", lambda: (reads.append(1), real())[1]
    )

    get_role_config("역할하나")
    assert len(reads) == 1, f"models.yaml 을 {len(reads)}번 읽었다"


def test_the_live_roles_resolve():
    """실물 models.yaml 의 역할 둘이 실제로 풀림.

    임시 파일 시험은 규칙만 봄. 저장소에 적힌 역할이 실제 프롬프트 파일과
    실제 provider 로 이어지는지는 여기서만 걸림 — 프롬프트를 옮기고 roles 를
    안 고치면 이 줄이 먼저 빨개짐.

    **모델 이름을 단언하지 않는다.** 측정으로 바뀌는 값이라 못 박으면 모델을
    옮길 때마다 상관없는 빨간불이 뜸.
    """
    for role in (RESOLVE, NODE_REGISTRATION):
        config = get_role_config(role)
        assert config.prompt_path.is_file(), f"{role} 의 프롬프트가 없다"
        assert config.prompt.strip(), f"{role} 의 프롬프트가 비었다"
        assert config.model.provider, f"{role} 의 provider 가 비었다"

    assert (
        get_role_config(RESOLVE).prompt_path
        != get_role_config(NODE_REGISTRATION).prompt_path
    ), "목적이 다른 두 역할이 같은 프롬프트를 쓰면 한 역할로 합친 것과 같다"
