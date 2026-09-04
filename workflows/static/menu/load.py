"""static workflow의 context인 Menu 로딩.

LLM 에는 menu.yaml 을 전달한다.
menu.md 는 같은 내용을 사람이 읽으라고 둔 문서이고, 코드가 읽지 않는다.

## 걸러 싣던 길을 걷었다 (2026-09-04)

2026-08-29 「마흔여덟째」에 인자를 주면 recipe 몇 줄만 내는 길을 냈다. 발화가
화면을 가리키느냐로 menu 를 가르던 임시방편(resolve_service 의 SCREEN_WORDS)이
그것을 쓰던 유일한 자리였고, 그 임시방편을 걷으면서 함께 걷었다.
**지금은 언제나 원문 전부를 낸다.**

되살리려면 `git show before-buttress-removed:workflows/static/menu/load.py`.
왜 걷었는지는 NOTES.md 「아흔여섯째」에 있다.
"""

from paths import MENU_YAML_PATH


def load_menu() -> str:
    """menu.yaml 원문.

    출력  파일에 적힌 그대로의 문자열
    규칙  자수를 재고 표에 적는 값이고 프롬프트에 실리는 것도 이 문자열임.
          한 글자도 안 바꿈
    """
    return MENU_YAML_PATH.read_text(encoding="utf-8")
