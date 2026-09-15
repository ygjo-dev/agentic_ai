import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# 게시 자산(온톨로지 · menu · recipe)을 저장소 밖에서 읽을 때 그 뿌리를 적는 환경변수.
# 값이 있으면 그 폴더의 ontology/ontology.yaml · menu/ · recipes/ 를 읽는다
# (KRRI_Ontology_Registry 의 짜임새). 값이 없으면 이 저장소 안의 작업본을 읽는다.
ARTIFACT_ROOT_ENV = "AGENTIC_ARTIFACT_ROOT"


class ArtifactRootError(RuntimeError):
    """게시 자산 뿌리 설정이 잘못됐다. 적힌 폴더가 없다."""


def artifact_root() -> Path | None:
    """게시 자산을 읽을 바깥 뿌리. 적지 않았으면 None.

    출력  폴더 경로. None 이면 이 저장소 안의 작업본을 읽음
    규칙  AGENTIC_ARTIFACT_ROOT 한 값만 봄. 앞뒤 공백은 뗌
          값이 있는데 폴더가 아니면 ArtifactRootError
          값이 없을 때 작업본을 읽는 것은 옮기는 동안의 호환임
    제약  값이 틀렸을 때 작업본으로 돌아가지 않는다.
          조용히 돌아가면 어느 자산으로 해석했는지 아무도 모름
    """
    raw = (os.environ.get(ARTIFACT_ROOT_ENV) or "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ArtifactRootError(f"{ARTIFACT_ROOT_ENV} 가 가리키는 폴더가 없다: {raw}")
    return root


# 한 프로세스 안에서 한 번 정한다. 요청마다 다시 읽으면 한 요청 안에서 온톨로지와
# recipe 가 서로 다른 뿌리에서 올 수 있다.
ARTIFACT_ROOT = artifact_root()

# LLM 역할. 역할마다 manifest · prompt · response schema 를 판 번호로 갖는다.
# 읽는 곳은 llm_engine/role_config.py 의 get_role_config 하나다.
ROLES_DIR = REPO_ROOT / "llm_engine" / "roles"

# static workflow 자산.
STATIC_DIR = REPO_ROOT / "workflows" / "static"

if ARTIFACT_ROOT is None:
    ONTOLOGY_PATH = REPO_ROOT / "ontology" / "ontology.yaml"
    MENU_DIR = STATIC_DIR / "menu"
    RECIPES_DIR = STATIC_DIR / "recipes"
else:
    ONTOLOGY_PATH = ARTIFACT_ROOT / "ontology" / "ontology.yaml"
    MENU_DIR = ARTIFACT_ROOT / "menu"
    RECIPES_DIR = ARTIFACT_ROOT / "recipes"

MENU_MD_PATH = MENU_DIR / "menu.md"      # 사람이 읽는 문서.
MENU_YAML_PATH = MENU_DIR / "menu.yaml"  # LLM 에 Context 로 전달하는 원문.

# ★ 프롬프트 경로는 여기 없다. **어느 역할이 어느 프롬프트를 쓰는가**는 역할
#   폴더(ROLES_DIR/<역할>/prompts)가 갖고 판 번호는 그 역할의 manifest 가 정한다 —
#   여기에 두면 역할과 프롬프트의 연결이 두 파일에 나뉜다.
