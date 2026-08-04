"""static workflow의 context인 Menu.md 로딩.
"""

from paths import MENU_PATH


def load_menu() -> str:
    return MENU_PATH.read_text(encoding="utf-8")
