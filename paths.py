from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

ONTOLOGY_PATH = REPO_ROOT / "ontology" / "ontology.yaml"

STATIC_DIR = REPO_ROOT / "orchestrators" / "static"

MENU_PATH = STATIC_DIR / "menu" / "menu.md"
PROMPTS_DIR = STATIC_DIR / "prompts"
RECIPES_DIR = STATIC_DIR / "recipes"
SCHEMAS_DIR = STATIC_DIR / "schemas"

RECIPE_SELECTION_PROMPT_PATH = PROMPTS_DIR / "recipe_selection.md"
