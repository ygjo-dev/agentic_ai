from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

ONTOLOGY_PATH = REPO_ROOT / "ontology" / "ontology.yaml"

# 모델별 값(num_ctx · timeout · reason 길이 상한). 측정 결과라 커밋한다.
MODELS_PATH = REPO_ROOT / "models.yaml"

# 배선표. 노드를 무엇으로 실행하고 input 을 어떻게 채우는지.
#
# **온톨로지 밖이다.** 노드가 MCP 서버에 묶이면 도구를 갈아 끼울 때 도메인을
# 고쳐야 하고, menu 가 온톨로지에서 만들어지므로 도구 이름이 프롬프트로 샌다.
WIRING_PATH = REPO_ROOT / "execution" / "wiring.yaml"

# 노드 등록. 온톨로지와 배선을 자동으로 만든다.
REGISTRATION_DIR = REPO_ROOT / "registration"

# static workflow 자산.
STATIC_DIR = REPO_ROOT / "workflows" / "static"

MENU_DIR = STATIC_DIR / "menu"
MENU_MD_PATH = MENU_DIR / "menu.md"      # 사람이 읽는 문서.
MENU_YAML_PATH = MENU_DIR / "menu.yaml"  # LLM 에 Context 로 전달하는 원문.
PROMPTS_DIR = STATIC_DIR / "prompts"
RECIPES_DIR = STATIC_DIR / "recipes"

RECIPE_SELECTION_PROMPT_PATH = PROMPTS_DIR / "recipe_selection.md"
NODE_REGISTRATION_PROMPT_PATH = REGISTRATION_DIR / "node_registration.md"

# 초기화 원본. 등록으로 위 자산이 바뀌므로 되돌릴 곳이 필요하다.
# 코드가 자동으로 다시 만들지 않는다 — 재생성하면 등록된 노드가 섞인 상태가
# 원본이 되어 되돌릴 수 없다.
INIT_ONTOLOGY_PATH = REPO_ROOT / "ontology" / "_init" / "ontology.yaml"

INIT_STATIC_DIR = STATIC_DIR / "_init"
INIT_MENU_DIR = INIT_STATIC_DIR / "menu"
INIT_MENU_MD_PATH = INIT_MENU_DIR / "menu.md"
INIT_MENU_YAML_PATH = INIT_MENU_DIR / "menu.yaml"
INIT_RECIPES_DIR = INIT_STATIC_DIR / "recipes"
