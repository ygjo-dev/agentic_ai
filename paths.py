from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

ONTOLOGY_PATH = REPO_ROOT / "ontology" / "ontology.yaml"

# LLM 역할. 역할마다 manifest · prompt · response schema 를 판 번호로 갖는다.
# 읽는 곳은 llm_engine/role_config.py 의 get_role_config 하나다.
ROLES_DIR = REPO_ROOT / "llm_engine" / "roles"

# static workflow 자산.
STATIC_DIR = REPO_ROOT / "workflows" / "static"

MENU_DIR = STATIC_DIR / "menu"
MENU_MD_PATH = MENU_DIR / "menu.md"      # 사람이 읽는 문서.
MENU_YAML_PATH = MENU_DIR / "menu.yaml"  # LLM 에 Context 로 전달하는 원문.
RECIPES_DIR = STATIC_DIR / "recipes"

# ★ 프롬프트 경로는 여기 없다. **어느 역할이 어느 프롬프트를 쓰는가**는 역할
#   폴더(ROLES_DIR/<역할>/prompts)가 갖고 판 번호는 그 역할의 manifest 가 정한다 —
#   여기에 두면 역할과 프롬프트의 연결이 두 파일에 나뉜다.
