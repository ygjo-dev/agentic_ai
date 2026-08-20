from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

ONTOLOGY_PATH = REPO_ROOT / "ontology" / "ontology.yaml"

# 모델별 값(num_ctx · timeout · reason 길이 상한). 측정 결과라 커밋한다.
MODELS_PATH = REPO_ROOT / "models.yaml"

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
NODE_REGISTRATION_PROMPT_PATH = PROMPTS_DIR / "node_registration.md"

# 초기화 원본. 웹UI 에서 노드를 등록하면 위 자산이 바뀌므로 되돌릴 곳이 필요하다.
# 코드가 자동으로 다시 만들지 않는다 — 사람이 명시적으로 다시 뜨기 전까지 고정이다.
# 자동 재생성하면 등록된 노드가 섞인 상태가 원본이 되어 되돌릴 수 없다.
INIT_ONTOLOGY_PATH = REPO_ROOT / "ontology" / "_init" / "ontology.yaml"

INIT_STATIC_DIR = STATIC_DIR / "_init"
INIT_MENU_DIR = INIT_STATIC_DIR / "menu"
INIT_MENU_MD_PATH = INIT_MENU_DIR / "menu.md"
INIT_MENU_YAML_PATH = INIT_MENU_DIR / "menu.yaml"
INIT_RECIPES_DIR = INIT_STATIC_DIR / "recipes"
