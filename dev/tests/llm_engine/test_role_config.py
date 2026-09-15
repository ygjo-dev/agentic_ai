"""대상 : llm_engine/role_config.py — 역할 하나가 logical model 한 판이다

역할(지금은 resolve)마다 물리 모델 · provider · inference 값 · prompt ·
응답 schema 가 한 벌로 묶이고, manifest 의 판 번호가 prompt 와 schema 파일을 고른다.
경로는 manifest 에 없다. 역할 이름과 판 번호가 위치를 정한다.

임시 역할 폴더로 규칙을 본다. 실물 역할에서는 **지금 살아 있는 역할이 실제로
풀리는지와 코드가 채우는 치환자가 있는지**만 본다. 모델 이름 같은 값은 못 박지
않는다. 측정으로 바뀌는 값이라 못 박으면 모델을 옮길 때마다 빨간불이 뜬다.
"""

import inspect
from pathlib import Path

import pytest
import yaml

import paths
from llm_engine import role_config
from llm_engine.role_config import (
    RESOLVE,
    InvalidRoleConfig,
    UnknownRole,
    get_role_config,
)

# type 의 "null" 은 문자열이고 enum 의 None 은 JSON null 이다. 둘이 파일을 거쳐도
# 갈리지 않는지 함께 본다.
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": ["string", "null"], "enum": ["네", None]}},
    "required": ["answer"],
}

OLLAMA_ROLE = {
    "role": "역할하나",
    "version": 1,
    "model": {"provider": "ollama", "name": "느린모델"},
    "inference": {"num_ctx": 8192, "timeout": 900},
    "prompt_version": 1,
    "response_schema_version": 1,
}

VLLM_ROLE = {
    "role": "역할둘",
    "version": 3,
    "model": {"provider": "vllm", "name": "vllm모델"},
    "inference": {"timeout": 300},
    "prompt_version": 2,
    "response_schema_version": 1,
}


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def dump(path: Path, document) -> None:
    write(path, yaml.safe_dump(document, allow_unicode=True, sort_keys=False))


def put(root: Path, manifest: dict, folder: str | None = None) -> None:
    folder = folder or manifest["role"]
    dump(root / folder / f"{folder}.yaml", manifest)


def drop(document: dict, key: str) -> dict:
    return {k: v for k, v in document.items() if k != key}


@pytest.fixture
def roles(monkeypatch, tmp_path):
    """역할 둘이 든 임시 roles 폴더. 하나는 Ollama, 하나는 vLLM 이고 prompt 판이 둘이다."""
    root = tmp_path / "roles"
    put(root, OLLAMA_ROLE)
    dump(root / "역할하나" / "prompts" / "v1.yaml", {"template": "프롬프트 하나 {utterance}\n"})
    dump(root / "역할하나" / "response_schemas" / "v1.yaml", SCHEMA)

    put(root, VLLM_ROLE)
    dump(root / "역할둘" / "prompts" / "v1.yaml", {"template": "옛 프롬프트\n"})
    dump(root / "역할둘" / "prompts" / "v2.yaml", {"template": "새 프롬프트\n"})
    dump(root / "역할둘" / "response_schemas" / "v1.yaml", SCHEMA)

    monkeypatch.setattr(paths, "ROLES_DIR", root)
    return root


def test_a_role_is_one_logical_model_read_from_its_own_folder(roles):
    """역할 하나를 물으면 모델 · provider · inference · prompt · schema 가 한 벌로 옴.

    manifest 하나를 보면 그 역할이 무엇으로 어떻게 도는지 다 읽혀야 함. 둘을 따로
    물으면 그 사이에 파일이 바뀔 수 있음.
    """
    role = get_role_config("역할하나")

    assert (role.role, role.version, role.model, role.provider) == (
        "역할하나", 1, "느린모델", "ollama"
    )
    assert role.inference == {"num_ctx": 8192, "timeout": 900}
    assert (role.prompt_version, role.response_schema_version) == (1, 1)
    assert role.prompt == "프롬프트 하나 {utterance}\n", "template 을 한 글자도 안 바꿔야 한다"
    assert role.response_schema == SCHEMA
    assert role.response_schema["properties"]["answer"]["enum"][-1] is None, (
        "YAML null 이 문자열이 되면 schema 의 뜻이 바뀐다"
    )


def test_the_version_numbers_pick_the_prompt_and_schema_files(roles):
    """prompt_version 2 가 prompts/v2.yaml 을 고름. 경로를 manifest 에 적지 않음.

    판 번호만 올리면 옛 판 파일은 그대로 남고 새 판이 실림. 경로 문자열을 적게
    하면 이름과 판 번호가 갈리는 자리가 하나 더 생김.
    """
    role = get_role_config("역할둘")

    assert role.prompt == "새 프롬프트\n"
    assert (role.version, role.provider, role.inference) == (3, "vllm", {"timeout": 300})


def test_an_unknown_role_says_what_is_there(roles):
    """없는 역할은 오류. 무엇이 있는지 문장에 있어야 함.

    역할 이름을 잘못 적었을 때 조용히 다른 역할로 돌면 어느 목적으로 불렀는지
    표에서 사라짐.
    """
    with pytest.raises(UnknownRole) as 터짐:
        get_role_config("없는역할")

    assert "없는역할" in str(터짐.value)
    assert "역할하나" in str(터짐.value), "무엇이 있는지 알려줘야 한다"


def _vllm_with_num_ctx(root):
    put(root, {**VLLM_ROLE, "inference": {"timeout": 300, "num_ctx": 8192}})


BROKEN = {
    "role 이 폴더 이름과 다름": ("역할하나", lambda r: put(r, {**OLLAMA_ROLE, "role": "딴이름"}, "역할하나"), "role"),
    "manifest 파일 없음": ("역할하나", lambda r: (r / "역할하나" / "역할하나.yaml").unlink(), "파일이 없다"),
    "manifest 가 맵이 아님": ("역할하나", lambda r: write(r / "역할하나" / "역할하나.yaml", "- 목록\n"), "맵이 아니다"),
    "version 없음": ("역할하나", lambda r: put(r, drop(OLLAMA_ROLE, "version")), "version"),
    "version 이 문자열": ("역할하나", lambda r: put(r, {**OLLAMA_ROLE, "version": "1"}), "version"),
    "version 이 0": ("역할하나", lambda r: put(r, {**OLLAMA_ROLE, "version": 0}), "version"),
    "model.name 없음": ("역할하나", lambda r: put(r, {**OLLAMA_ROLE, "model": {"provider": "ollama"}}), "model.name"),
    "model.provider 없음": ("역할하나", lambda r: put(r, {**OLLAMA_ROLE, "model": {"name": "느린모델"}}), "model.provider"),
    "모르는 provider": ("역할하나", lambda r: put(r, {**OLLAMA_ROLE, "model": {"provider": "없는프로바이더", "name": "느린모델"}}), "없는프로바이더"),
    "inference 없음": ("역할하나", lambda r: put(r, drop(OLLAMA_ROLE, "inference")), "inference"),
    "Ollama 에 num_ctx 없음": ("역할하나", lambda r: put(r, {**OLLAMA_ROLE, "inference": {"timeout": 900}}), "num_ctx"),
    "vLLM 에 num_ctx 있음": ("역할둘", _vllm_with_num_ctx, "num_ctx"),
    "timeout 이 0": ("역할하나", lambda r: put(r, {**OLLAMA_ROLE, "inference": {"num_ctx": 8192, "timeout": 0}}), "timeout"),
    "prompt_version 없음": ("역할하나", lambda r: put(r, drop(OLLAMA_ROLE, "prompt_version")), "prompt_version"),
    "response_schema_version 없음": ("역할하나", lambda r: put(r, drop(OLLAMA_ROLE, "response_schema_version")), "response_schema_version"),
    "prompt 판 파일 없음": ("역할하나", lambda r: put(r, {**OLLAMA_ROLE, "prompt_version": 9}), "v9.yaml"),
    "schema 판 파일 없음": ("역할하나", lambda r: put(r, {**OLLAMA_ROLE, "response_schema_version": 9}), "v9.yaml"),
    "template 없음": ("역할하나", lambda r: dump(r / "역할하나" / "prompts" / "v1.yaml", {"text": "딴 칸"}), "template"),
    "schema 가 맵이 아님": ("역할하나", lambda r: write(r / "역할하나" / "response_schemas" / "v1.yaml", "- type\n"), "맵이 아니다"),
}


@pytest.mark.parametrize("role, breaks, fragment", BROKEN.values(), ids=BROKEN.keys())
def test_a_broken_role_stops_before_the_llm_is_called(roles, role, breaks, fragment):
    """잘못된 역할 설정은 부르기 전에 멈춤. 무엇이 틀렸는지 문장에 있어야 함.

    빈 prompt · 모르는 provider · 안 실리는 num_ctx 로 LLM 을 부르면 답이 이상한 것이
    설정 탓인지 모델 탓인지 안 갈림. 모르는 provider 를 Ollama 로 떨어뜨리면 어느
    서버로 쟀는지도 모르게 됨.
    """
    breaks(roles)

    with pytest.raises(InvalidRoleConfig) as 터짐:
        get_role_config(role)

    assert fragment in str(터짐.value)


def test_a_broken_role_does_not_break_the_others(roles):
    """부르지 않은 역할은 검사하지 않음.

    역할 하나가 잘못됐다고 상관없는 자리가 통째로 죽으면, 쓰지도 않는 설정 한 줄
    때문에 애플리케이션이 안 뜨는 구조가 됨.
    """
    (roles / "역할하나" / "prompts" / "v1.yaml").unlink()

    assert get_role_config("역할둘").prompt == "새 프롬프트\n"


def test_nothing_is_cached_between_calls(roles):
    """manifest · prompt · schema 를 고치면 다음 호출에 보임. 먼저 받은 한 벌은 그대로임.

    서버를 띄운 채 설정을 고치고 다시 재는 것이 용도임. 캐시하면 재시작 전까지
    옛 판으로 돌면서 새 판으로 쟀다고 읽힘.
    """
    first = get_role_config("역할하나")

    put(roles, {**OLLAMA_ROLE, "model": {"provider": "ollama", "name": "바꾼모델"}})
    dump(roles / "역할하나" / "prompts" / "v1.yaml", {"template": "고친 프롬프트\n"})
    dump(roles / "역할하나" / "response_schemas" / "v1.yaml", {**SCHEMA, "required": []})

    second = get_role_config("역할하나")

    assert (second.model, second.prompt, second.response_schema["required"]) == (
        "바꾼모델", "고친 프롬프트\n", []
    )
    assert (first.model, first.prompt) == ("느린모델", "프롬프트 하나 {utterance}\n"), (
        "먼저 받은 한 벌이 뒤의 수정에 따라 움직이면 한 요청 안에서 판이 섞인다"
    )


def test_one_call_reads_the_three_files_once_each(roles, read_file_paths):
    """한 호출이 manifest · prompt · schema 를 한 번씩 읽어 한 벌로 묶음.

    같은 파일을 두 번 읽으면 그 사이의 수정이 한 벌 안에 섞일 자리가 생김. 역할
    이름과 판 번호가 가리키는 세 파일 말고 다른 것도 안 읽음.
    """
    read_file_paths.clear()

    get_role_config("역할하나")

    read = sorted(
        str(Path(entry).relative_to(roles))
        for entry in read_file_paths
        if isinstance(entry, Path) and roles in entry.parents
    )
    assert read == [
        "역할하나/prompts/v1.yaml",
        "역할하나/response_schemas/v1.yaml",
        "역할하나/역할하나.yaml",
    ]


def test_the_physical_model_cannot_be_swapped_at_run_time(roles, monkeypatch):
    """인자도 환경변수도 manifest 의 모델을 못 바꿈.

    요청 하나가 manifest 와 다른 물리 모델로 돌면 무엇을 쟀는지 파일로 못 읽음.
    다른 모델을 재려면 manifest 를 고치고 판을 올림.
    """
    monkeypatch.setenv("LLM_MODEL", "환경모델")

    assert get_role_config("역할하나").model == "느린모델"
    assert list(inspect.signature(get_role_config).parameters) == ["role"]
    assert not hasattr(role_config, "get_model_config"), "이름으로 모델을 고르는 길이 되살아났다"


# 코드가 prompt 에 채워 넣는 치환자. 이름이 갈리면 format 이 KeyError 로 죽거나
# 값이 통째로 안 실린다.
PLACEHOLDERS = {
    RESOLVE: ("{menu}", "{utterance}"),
}


def test_the_live_roles_resolve_with_the_placeholders_the_code_fills():
    """실물 역할이 실제로 풀리고, 코드가 채우는 치환자를 prompt 가 가짐.

    임시 폴더 시험은 규칙만 봄. 저장소에 적힌 역할이 실제 판 파일로 이어지는지는
    여기서만 걸림. 판 번호를 올리고 파일을 안 만들면 이 줄이 먼저 빨개짐.

    모델 이름을 단언하지 않는다. 측정으로 바뀌는 값이라 못 박으면 모델을 옮길 때마다
    상관없는 빨간불이 뜸.
    """
    for role, placeholders in PLACEHOLDERS.items():
        config = get_role_config(role)
        assert config.role == role
        for placeholder in placeholders:
            assert placeholder in config.prompt, f"{role} prompt 에 {placeholder} 가 없다"
        schema = config.response_schema
        assert set(schema["required"]) == set(schema["properties"]), (
            f"{role} schema 의 required 와 properties 가 갈렸다"
        )

    assert not (paths.REPO_ROOT / "models.yaml").exists(), (
        "역할 밖에 모델 목록을 되살리지 않는다. 역할 manifest 한 곳이 모델을 정한다"
    )
