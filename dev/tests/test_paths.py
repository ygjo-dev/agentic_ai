"""대상 : paths.py — 게시 자산을 어디서 읽나 · 서비스를 어느 주소로 부르나

게시 자산(온톨로지 · menu · recipe)은 KRRI_Ontology_Registry 짜임새의 한 뿌리에서 온다.
기본 뿌리는 이 저장소 안의 KRRI_Ontology_Registry 이고, AGENTIC_ARTIFACT_ROOT 에 적으면
같은 짜임새의 바깥 폴더다.

paths 는 import 할 때 한 번 정하므로 따로 띄운 python 으로 본다. 이 프로세스의 paths 를
다시 읽으면 뒤의 시험이 다른 자산을 읽게 된다.

서비스 주소는 **같은 기계에 있다는 사실을 코드의 전제로 만들지 않는다** 를 지킨다. 주소를
안 적었을 때 조용히 loopback 을 부르면, 서비스를 다른 기계로 나눠 놓았을 때 무엇이
어디를 부르는지 아무도 못 읽는다. 부르는 쪽 주소와 서버가 귀를 여는 주소를 갈라 두는
것도 여기서 본다. 0.0.0.0 은 띄우는 명령이 쓰는 값이지 찾아갈 주소가 아니다.
"""

import json
import os
import subprocess
import sys

import pytest

import paths

NAMES = ("ARTIFACT_ROOT", "ONTOLOGY_PATH", "MENU_YAML_PATH", "MENU_MD_PATH", "RECIPES_DIR")


def paths_in_child(root):
    """root 를 AGENTIC_ARTIFACT_ROOT 로 두고 띄운 python 이 본 경로. root 가 None 이면 값을 지움."""
    env = dict(os.environ)
    env.pop(paths.ARTIFACT_ROOT_ENV, None)
    if root is not None:
        env[paths.ARTIFACT_ROOT_ENV] = root
    code = f"import json, paths; print(json.dumps({{n: str(getattr(paths, n)) for n in {NAMES!r}}}))"
    return subprocess.run(
        [sys.executable, "-c", code], cwd=paths.REPO_ROOT, env=env, capture_output=True, text=True
    )


def test_without_an_artifact_root_the_registry_in_this_repository_is_read():
    """값을 안 적은 배포는 저장소 안의 KRRI_Ontology_Registry 를 읽는다."""
    done = paths_in_child(None)
    registry = paths.REPO_ROOT / "KRRI_Ontology_Registry"

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {
        "ARTIFACT_ROOT": str(registry),
        "ONTOLOGY_PATH": str(registry / "ontology" / "ontology.yaml"),
        "MENU_YAML_PATH": str(registry / "menu" / "menu.yaml"),
        "MENU_MD_PATH": str(registry / "menu" / "menu.md"),
        "RECIPES_DIR": str(registry / "recipes"),
    }


def test_an_artifact_root_moves_the_ontology_the_menu_and_the_recipes_together(tmp_path):
    """셋이 한 뿌리에서 와야 함. 하나만 옮겨지면 menu 에 없는 recipe 를 고르거나 온톨로지에 없는 노드를 실행함."""
    root = tmp_path.resolve()

    done = paths_in_child(str(root))

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {
        "ARTIFACT_ROOT": str(root),
        "ONTOLOGY_PATH": str(root / "ontology" / "ontology.yaml"),
        "MENU_YAML_PATH": str(root / "menu" / "menu.yaml"),
        "MENU_MD_PATH": str(root / "menu" / "menu.md"),
        "RECIPES_DIR": str(root / "recipes"),
    }


def test_an_artifact_root_that_is_not_a_folder_stops_instead_of_falling_back(tmp_path):
    """틀린 값에 저장소 안 Registry 로 돌아가면 어느 자산으로 해석했는지 아무도 모름."""
    done = paths_in_child(str(tmp_path / "없는_폴더"))

    assert done.returncode != 0
    assert "ArtifactRootError" in done.stderr


def test_the_two_menus_have_different_readers():
    """menu.yaml 은 발화 해석 프롬프트, menu.md 는 사람이 읽는 기능 메뉴. 같은 menu 폴더에 나란히 있음."""
    assert paths.MENU_YAML_PATH.parent == paths.MENU_MD_PATH.parent == paths.MENU_DIR
    assert paths.MENU_YAML_PATH.is_file() and paths.MENU_MD_PATH.is_file()


# ── 서비스 주소 ─────────────────────────────────────────────────────

VARIABLE = "TEST_SERVICE_URL"


def read(monkeypatch, value):
    """환경변수를 그 값으로 두고 한 번 읽음. None 이면 아예 안 둠."""
    if value is None:
        monkeypatch.delenv(VARIABLE, raising=False)
    else:
        monkeypatch.setenv(VARIABLE, value)
    return paths.service_url(VARIABLE, "부르는 쪽", "불리는 쪽")


def test_a_reachable_address_passes(monkeypatch):
    """이름이든 주소든 닿을 수 있으면 그대로 통과함."""
    assert read(monkeypatch, "http://192.168.68.231:18000") == "http://192.168.68.231:18000"
    assert read(monkeypatch, "https://llm.example.org") == "https://llm.example.org"
    assert read(monkeypatch, "http://[2001:db8::1]:8000") == "http://[2001:db8::1]:8000"


def test_the_trailing_slash_is_dropped(monkeypatch):
    """부르는 쪽이 경로를 이어 붙이므로 빗금이 겹치면 안 됨.

    이어 붙이는 자리가 여럿(provider · vendor · 계기판)이라 그 자리마다
    rstrip 을 적으면 한 곳을 빠뜨림.
    """
    assert read(monkeypatch, "http://gateway.example:3000/") == "http://gateway.example:3000"


def test_a_missing_address_says_which_call_it_broke(monkeypatch):
    """값이 없으면 멈추되, 무엇이 무엇을 못 부르게 됐는지 문장에 있어야 함.

    변수 이름만 적으면 넷 중 어느 길이 끊겼는지 로그만 보고 못 가름.
    """
    for missing in (None, "", "   "):
        with pytest.raises(paths.EndpointError) as raised:
            read(monkeypatch, missing)
        assert VARIABLE in str(raised.value)
        assert "부르는 쪽" in str(raised.value)
        assert "불리는 쪽" in str(raised.value)


def test_loopback_is_refused(monkeypatch):
    """제 기계를 가리키는 주소는 서비스 endpoint 가 아님.

    127.0.0.1 한 줄만 막으면 127.0.0.2 가 그대로 통과하므로 127.0.0.0/8 전체를
    봄. ::1 과 localhost 하위 이름도 같은 자리.
    """
    for address in (
        "http://localhost:8000",
        "http://LOCALHOST:8000",
        "http://api.localhost:8000",
        "http://127.0.0.1:18000",
        "http://127.0.0.2:18000",
        "http://127.1.2.3:18000",
        "http://[::1]:18000",
    ):
        with pytest.raises(paths.EndpointError):
            read(monkeypatch, address)


def test_a_bind_address_is_refused(monkeypatch):
    """0.0.0.0 은 서버가 귀를 여는 값이지 찾아갈 주소가 아님.

    이것을 목적지로 적으면 무엇을 부르는지 아무도 모르고, 클라이언트에 따라
    조용히 loopback 으로 돌기도 함.
    """
    for address in ("http://0.0.0.0:8000", "http://[::]:8000"):
        with pytest.raises(paths.EndpointError):
            read(monkeypatch, address)


def test_the_scheme_must_be_http(monkeypatch):
    """host:port 만 적은 값은 부를 수 없음. 주소 전체를 받는다는 계약임."""
    for address in ("192.168.68.231:18000", "ftp://gateway.example", "//gateway.example"):
        with pytest.raises(paths.EndpointError):
            read(monkeypatch, address)


def test_each_service_reads_its_own_variable(monkeypatch):
    """넷이 서로 다른 변수를 봄. 이름만 읽어도 누가 누구를 부르는지 알아야 함."""
    for read_url, variable in (
        (paths.ollama_url, "OLLAMA_URL"),
        (paths.vllm_url, "VLLM_URL"),
        (paths.asap_gateway_url, "ASAP_GATEWAY_URL"),
        (paths.agentic_api_url, "AGENTIC_API_URL"),
    ):
        monkeypatch.setenv(variable, f"http://{variable.lower()}.example:9")
        assert read_url() == f"http://{variable.lower()}.example:9"

        monkeypatch.delenv(variable)
        with pytest.raises(paths.EndpointError) as raised:
            read_url()
        assert variable in str(raised.value)


def test_the_address_is_read_when_it_is_needed(monkeypatch):
    """import 시점에 넷을 다 읽지 않음.

    Ollama 를 안 쓰는 배포가 OLLAMA_URL 이 없다고 통째로 못 뜨면 안 됨.
    provider 모듈을 읽는 것만으로는 아무 변수도 안 봄.
    """
    import importlib

    for variable in ("OLLAMA_URL", "VLLM_URL"):
        monkeypatch.delenv(variable, raising=False)

    from llm_engine.providers import ollama, vllm

    importlib.reload(ollama)
    importlib.reload(vllm)
