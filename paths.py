from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

ONTOLOGY_PATH = REPO_ROOT / "ontology" / "ontology.yaml"

# 실행 경로(Route) 결정 엔진.
ORCHESTRATOR_DIR = REPO_ROOT / "orchestrator"
SCHEMAS_DIR = ORCHESTRATOR_DIR / "schemas"

# static workflow 자산.
STATIC_DIR = REPO_ROOT / "workflows" / "static"

MENU_DIR = STATIC_DIR / "menu"
MENU_MD_PATH = MENU_DIR / "menu.md"      # 사람이 읽는 문서.
MENU_YAML_PATH = MENU_DIR / "menu.yaml"  # LLM 에 Context 로 전달하는 원문.
PROMPTS_DIR = STATIC_DIR / "prompts"
RECIPES_DIR = STATIC_DIR / "recipes"

RECIPE_SELECTION_PROMPT_PATH = PROMPTS_DIR / "recipe_selection.md"
