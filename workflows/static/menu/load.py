"""static workflow의 context인 Menu 로딩.

LLM 에는 menu.yaml 을 전달한다.
menu.md 는 같은 내용을 사람이 읽으라고 둔 문서이고, 코드가 읽지 않는다.
"""

from paths import MENU_YAML_PATH


def load_menu() -> str:
    """menu.yaml 원문을 그대로 돌려준다."""
    return MENU_YAML_PATH.read_text(encoding="utf-8")
