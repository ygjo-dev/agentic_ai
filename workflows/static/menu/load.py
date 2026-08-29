"""static workflow의 context인 Menu 로딩.

LLM 에는 menu.yaml 을 전달한다.
menu.md 는 같은 내용을 사람이 읽으라고 둔 문서이고, 코드가 읽지 않는다.

## 걸러서 싣는다 — ★ 임시방편이다 (2026-08-29 「마흔여덟째」)

`load_menu()` 는 원문을 그대로 낸다. **인자를 주면 그중 몇 줄만 낸다.**
무엇을 남길지는 여기가 정하지 않는다 — 부르는 쪽(resolve_service)이 id 로 말한다.

**menu.yaml 을 안 고친다.** 파일은 온톨로지가 만드는 것이고 요청마다 다를 수
없다. 여기서 하는 것은 읽은 문자열에서 블록을 빼는 일뿐이라, 남은 줄은 파일에
적힌 것과 한 글자도 다르지 않다 (마흔 줄만 남기면 「마흔여섯째」 이전 파일과
id 번호만 빼고 본문이 같다 — 3322자로 자수까지 같다).

왜 이런 것이 필요한지는 resolve_service 의 `SCREEN_WORDS` 옆에 적었다.
"""

import re

from paths import MENU_YAML_PATH

# menu.yaml 의 recipe 한 벌이 시작하는 줄. 파일이 "  recipe_001:" 로 적는다.
#
# yaml 로 읽고 다시 쓰지 않는 것은 그러면 따옴표와 줄바꿈이 파일과 달라지기
# 때문이다. **남은 줄이 파일과 한 글자도 달라지면 안 된다** — 자수를 재고
# 표에 적는 값이고, 프롬프트에 실리는 것도 그 문자열이다.
_RECIPE_HEAD = re.compile(r"^  (recipe_\d+):")


def load_menu(recipe_ids=None) -> str:
    """menu.yaml 원문. id 를 주면 그 recipe 만 남긴 것.

    입력  남길 recipe id (없으면 전부)
    출력  menu.yaml 문자열. 머리말(version · recipes:)은 언제나 남음
    규칙  안 주면 파일 원문을 그대로 냄. 인자를 만들기 전과 한 글자도 다르지
          않아야 함 — `_candidate_lines` 와 옛 부름이 그것을 씀
          목록에 없는 id 는 그냥 없는 것으로 봄. 여기서 오류를 올리지 않음 —
          온톨로지가 바뀌는 중에 프롬프트가 죽는 것보다 낫다
    """
    text = MENU_YAML_PATH.read_text(encoding="utf-8")
    if recipe_ids is None:
        return text
    return _only(text, set(recipe_ids))


def _only(text: str, keep: set) -> str:
    """recipe 블록 중 keep 에 든 것만 남긴 문자열.

    규칙  블록은 "  recipe_NNN:" 줄에서 시작해 다음 그런 줄 앞까지임.
          블록 뒤의 빈 줄도 그 블록의 것으로 봄
          첫 블록 앞(머리말)은 조건 없이 남김
    """
    out, block, current = [], [], None
    for line in text.splitlines(keepends=True):
        head = _RECIPE_HEAD.match(line)
        if head:
            if current is None or current in keep:
                out.extend(block)
            block, current = [line], head.group(1)
        else:
            block.append(line)
    if current is None or current in keep:
        out.extend(block)
    return "".join(out)
