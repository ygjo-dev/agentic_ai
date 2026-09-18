"""recipe 선택 LLM 에 실을 menu context.

**menu.yaml 원문 전부를 프롬프트에 넣는다.** 파일은 게시 자산 뿌리의
menu/menu.yaml 이다(paths.MENU_YAML_PATH).
"""

from paths import MENU_YAML_PATH


def load_menu() -> str:
    """menu.yaml 원문.

    출력  파일에 적힌 그대로의 문자열. 프롬프트에 실리는 것도 이것임
    제약  한 글자도 바꾸지 않는다. 자수를 재서 표에 적는 값이기도 함
    """
    return MENU_YAML_PATH.read_text(encoding="utf-8")
