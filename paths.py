"""agentic_ai 가 쓰는 위치의 단일 출처. 저장소 · 게시 자산의 파일 경로와 서비스 주소가 여기서 온다.

    파일 경로     REPO_ROOT · ARTIFACT_ROOT · ONTOLOGY_PATH · MENU_* · RECIPES_DIR · ROLES_DIR
                  import 할 때 한 번 정한다
    서비스 주소   ollama_url() · vllm_url() · asap_gateway_url() · asap_orchestrator_url() ·
                  agentic_api_url()
                  부르기 직전에 읽는다. import 시점에 읽지 않는다
"""

import ipaddress
import os
from pathlib import Path
from urllib.parse import urlsplit

# ── 저장소 · 게시 자산 경로 ─────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent

# 게시 자산(온톨로지 · menu · recipe)의 뿌리. 짜임새는 어디 있든 같다.
#
#     <뿌리>/ontology/ontology.yaml
#     <뿌리>/menu/menu.yaml
#     <뿌리>/menu/menu.md
#     <뿌리>/recipes/recipe_NNN.yaml
#
# 기본 뿌리는 이 저장소 안의 KRRI_Ontology_Registry 다. 그 폴더를 저장소 밖으로 옮긴
# 배포는 AGENTIC_ARTIFACT_ROOT 에 그 경로를 적는다 — 코드는 안 바뀐다.
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "KRRI_Ontology_Registry"
ARTIFACT_ROOT_ENV = "AGENTIC_ARTIFACT_ROOT"


class ArtifactRootError(RuntimeError):
    """게시 자산 뿌리가 폴더가 아니다."""


def artifact_root() -> Path:
    """게시 자산을 읽을 뿌리.

    출력  폴더 경로
    규칙  AGENTIC_ARTIFACT_ROOT 한 값만 봄. 앞뒤 공백은 뗌
          값이 비었으면 이 저장소의 KRRI_Ontology_Registry
          고른 뿌리가 폴더가 아니면 ArtifactRootError
    제약  값이 틀렸을 때 기본 뿌리로 돌아가지 않는다.
          조용히 돌아가면 어느 자산으로 해석했는지 아무도 모름
    """
    raw = (os.environ.get(ARTIFACT_ROOT_ENV) or "").strip()
    root = Path(raw).expanduser().resolve() if raw else DEFAULT_ARTIFACT_ROOT
    if not root.is_dir():
        raise ArtifactRootError(f"게시 자산 뿌리가 폴더가 아니다: {root} ({ARTIFACT_ROOT_ENV}={raw!r})")
    return root


# 한 프로세스 안에서 한 번 정한다. 요청마다 다시 읽으면 한 요청 안에서 온톨로지와
# recipe 가 서로 다른 뿌리에서 올 수 있다.
ARTIFACT_ROOT = artifact_root()

# LLM 역할. 역할마다 manifest · prompt · response schema 를 판 번호로 갖는다.
# 읽는 곳은 llm_engine/role_config.py 의 get_role_config 하나다.
ROLES_DIR = REPO_ROOT / "llm_engine" / "roles"

ONTOLOGY_PATH = ARTIFACT_ROOT / "ontology" / "ontology.yaml"
MENU_DIR = ARTIFACT_ROOT / "menu"
# menu 는 두 벌이고 읽는 쪽이 다르다. 서로 대신하지 않는다.
MENU_YAML_PATH = MENU_DIR / "menu.yaml"  # 발화 해석(Resolve) LLM 에 Context 로 전달하는 원문.
MENU_MD_PATH = MENU_DIR / "menu.md"      # 사람이 읽는 기능 메뉴. 화면의 recipe 제목 · 설명. 프롬프트에 안 실음.
RECIPES_DIR = ARTIFACT_ROOT / "recipes"

# ★ 프롬프트 경로는 여기 없다. **어느 역할이 어느 프롬프트를 쓰는가**는 역할
#   폴더(ROLES_DIR/<역할>/prompts)가 갖고 판 번호는 그 역할의 manifest 가 정한다 —
#   여기에 두면 역할과 프롬프트의 연결이 두 파일에 나뉜다.


# ── 서비스 주소 ─────────────────────────────────────────────────────
#
# **누가 누구를 부르는가가 이름에 적혀 있다.**
#
#     OLLAMA_URL         agentic_ai  ->  Ollama
#     VLLM_URL           agentic_ai  ->  vLLM
#     ASAP_GATEWAY_URL   agentic_ai  ->  KRRI_ASAP Gateway
#     ASAP_ORCHESTRATOR_URL  agentic_ai  ->  KRRI_ASAP Orchestrator (workflow 실행)
#     AGENTIC_API_URL    화면 · 계기판  ->  agentic_ai API
#
# 앞 넷은 백엔드가 밖으로 나가는 길이고, 마지막 하나는 백엔드를 찾아오는 길이다.
# 그 경계가 곧 app/ui 가 언제든 다른 저장소로 나갈 수 있는 자리다.
#
# **주소와 bind 를 섞지 않는다.** 여기 있는 것은 「부르는 쪽이 찾아갈 주소」뿐이다.
# 서버가 어느 인터페이스에 귀를 여는가(0.0.0.0:8000)는 띄우는 명령이 정하고
# 이 파일도 .env 도 모른다. 둘을 한 값에 섞으면 서버를 옮길 때 부르는 쪽이 함께
# 망가진다.
#
# **같은 기계에 있다는 사실에 기대지 않는다.** 그래서 기본값이 없다. 값이 없으면
# localhost 로 돌아가지 않고 그 자리에서 멈춘다 — 조용히 loopback 을 부르면
# 서비스를 나눠 놓았을 때 「왜 옆 기계 것이 안 보이나」를 아무도 못 찾는다.
#
# **주소를 역할 manifest(llm_engine/roles/)에 적지 않는다.** 저쪽은 역할마다 다른
# 값(모델 · num_ctx · timeout)을 적는 곳이고 이쪽은 기계마다 다른 값이다. 섞으면
# 역할 설정을 기계마다 갈라 두어야 한다.
#
# 읽는 때는 부르기 직전이다. import 시점에 다섯을 다 읽지 않는다 — Ollama 를 안
# 쓰는 배포가 OLLAMA_URL 이 없다고 통째로 못 뜨면 안 된다.

# 부를 수 있는 scheme. 서비스 endpoint 라 이 둘 말고는 받지 않는다.
ALLOWED_SCHEMES = ("http", "https")


class EndpointError(RuntimeError):
    """서비스 주소 설정이 잘못됐다. 값이 없거나 부를 수 없는 주소다."""


def _address_of(host: str):
    """host 가 IP 면 그 주소 객체. 이름이면 None.

    출력  ipaddress 객체 또는 None. 이름인지 주소인지를 부르는 쪽이 갈라 씀
    """
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_loopback(host: str) -> bool:
    """그 host 가 제 기계를 가리키나.

    입력  URL 에서 떼어 온 host. urlsplit 이 대괄호를 이미 벗겨 줌
    출력  참이면 loopback. 이름이든 주소든 같게 봄
    규칙  127.0.0.0/8 전체와 ::1 을 봄. 127.0.0.1 한 줄만 막으면
          127.0.0.2 가 그대로 통과함
          host 가 IP 가 아니면 이름으로 봄. localhost 와 그 하위 이름
    """
    name = host.lower().rstrip(".")
    if name == "localhost" or name.endswith(".localhost"):
        return True
    address = _address_of(name)
    return address is not None and address.is_loopback


def service_url(variable: str, caller: str, callee: str) -> str:
    """환경변수 하나를 읽어 부를 수 있는 서비스 주소로.

    입력  환경변수 이름 · 부르는 쪽 이름 · 불리는 쪽 이름.
          뒤의 둘은 오류 문장에만 쓰임. 무엇을 못 부르게 됐는지가 먼저 보여야 함
    출력  뒤 빗금을 뗀 주소 문자열
    규칙  값이 없거나 비었으면 EndpointError. 기본값으로 메우지 않음
          scheme 은 http · https 만
          loopback(localhost · 127.0.0.0/8 · ::1)은 거절함
          wildcard(0.0.0.0 · ::)는 서버 bind 주소라 거절함
    제약  특정 서비스 이름이나 특정 주소를 여기 적지 않는다.
          하나를 적으면 나머지 셋이 각자 규칙을 갖게 됨
          못 읽었을 때 loopback 으로 돌아가지 않는다.
          같은 기계에 있다는 사실이 코드의 전제가 됨
    """
    raw = (os.environ.get(variable) or "").strip()
    if not raw:
        raise EndpointError(
            f"{variable} 이 비어 있다. {caller} 가 {callee} 를 부를 주소다. "
            f".env 에 적는다 (예: {variable}=http://<host>:<port>)"
        )

    parts = urlsplit(raw)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise EndpointError(
            f"{variable}={raw} 의 scheme 이 {'·'.join(ALLOWED_SCHEMES)} 가 아니다. "
            f"주소 전체를 적는다 (예: {variable}=http://<host>:<port>)"
        )

    host = parts.hostname
    if not host:
        raise EndpointError(f"{variable}={raw} 에 host 가 없다")

    address = _address_of(host)
    if address is not None and address.is_unspecified:
        raise EndpointError(
            f"{variable}={raw} 은 서버가 귀를 여는 주소다. "
            f"{caller} 가 {callee} 를 찾아갈 주소를 적는다"
        )

    if _is_loopback(host):
        raise EndpointError(
            f"{variable}={raw} 은 제 기계를 가리킨다. "
            f"{callee} 가 다른 기계로 옮겨가면 {caller} 가 못 찾는다. "
            f"닿을 수 있는 host 이름이나 주소를 적는다"
        )

    return raw.rstrip("/")


def ollama_url() -> str:
    """agentic_ai 가 Ollama 를 부를 주소."""
    return service_url("OLLAMA_URL", "agentic_ai", "Ollama")


def vllm_url() -> str:
    """agentic_ai 가 vLLM 을 부를 주소."""
    return service_url("VLLM_URL", "agentic_ai", "vLLM")


def asap_gateway_url() -> str:
    """agentic_ai 가 KRRI_ASAP Gateway 를 부를 주소."""
    return service_url("ASAP_GATEWAY_URL", "agentic_ai", "KRRI_ASAP Gateway")


def asap_orchestrator_url() -> str:
    """agentic_ai 가 완성된 workflow 를 KRRI_ASAP Orchestrator 에 넘겨 실행할 주소."""
    return service_url("ASAP_ORCHESTRATOR_URL", "agentic_ai", "KRRI_ASAP Orchestrator")


def agentic_api_url() -> str:
    """화면 · 계기판이 agentic_ai API 를 부를 주소."""
    return service_url("AGENTIC_API_URL", "화면 · 계기판", "agentic_ai API")
