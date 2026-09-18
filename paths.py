import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# 게시 자산(온톨로지 · menu · recipe)의 뿌리. 짜임새는 어디 있든 같다.
#
#     <뿌리>/ontology/ontology.yaml
#     <뿌리>/menu/menu.yaml
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
MENU_YAML_PATH = MENU_DIR / "menu.yaml"  # LLM 에 Context 로 전달하는 원문.
RECIPES_DIR = ARTIFACT_ROOT / "recipes"

# ★ 프롬프트 경로는 여기 없다. **어느 역할이 어느 프롬프트를 쓰는가**는 역할
#   폴더(ROLES_DIR/<역할>/prompts)가 갖고 판 번호는 그 역할의 manifest 가 정한다 —
#   여기에 두면 역할과 프롬프트의 연결이 두 파일에 나뉜다.
