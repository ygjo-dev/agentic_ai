"""직전 되묻기를 세션마다 하나 기억하고, 다음 발화가 그것을 고른 것인지 가른다.

**되묻기는 한 번 주고받는 일이다.** 화면에 번호 붙은 후보를 내놓고, 사람이
그중 하나를 말하면 끝난다. 그래서 여기 있는 것은 대화 기록이 아니라 **직전
되묻기 하나**다 — 세션마다 한 건만 두고, 쓰면 지운다.

메모리에만 둔다. 파일도 DB 도 만들지 않는다. 서버를 다시 띄우면 사라지는데,
그때 사람은 발화를 다시 말하면 된다 — 되묻기 하나를 잃는 값이 저장소 하나를
더 두는 값보다 싸다.

**고르기인지 가르는 일도 여기 있다.** LLM 을 부르지 않고 문자열로만 가른다.
부르면 느려지고, 무엇보다 같은 문구에 다른 답이 나온다 — 고르기는 사람이
방금 화면에서 읽은 것을 되뇌는 일이라 흔들릴 자리가 아니다.

규칙을 좁게 잡는다. 넓게 잡으면 멀쩡한 새 발화를 고르기로 오해해 엉뚱한
도구를 부른다. **애매하면 고르기가 아닌 쪽이다** — "무슨 말인지 모르겠다" 가
잘못 실행하는 것보다 낫다.
"""

import re
import time
from collections import OrderedDict

# 되묻기를 기억해 두는 시간(초).
#
# 사람이 후보 넷을 읽고 번호를 누르는 데 걸리는 시간은 길어야 한두 분이다.
# 5분을 넘겨 온 발화는 고르기라기보다 새 발화로 보는 것이 맞다 — 화면을 띄워
# 두고 자리를 비웠다가 돌아와 다른 것을 묻는 자리가 그것이다.
#
# 짧게 잡으면 시연 중에 설명하다가 시간이 지나 못 고르게 되고, 길게 잡으면
# 두 발화 전의 후보 목록이 살아 있어 엉뚱한 것이 실행된다. 그 사이다.
TTL_SECONDS = 300

# 동시에 기억할 세션 수의 상한.
#
# 세션 id 는 저쪽 화면이 만든다. 우리는 언제 그 세션이 끝나는지 모르므로
# 놔두면 무한히 는다. 상한을 두고 넘치면 **가장 오래 안 쓴 것부터** 버린다.
# 시연은 한두 사람이 쓰므로 64 면 넉넉하다.
MAX_SESSIONS = 64

# 세션 id -> 기억해 둔 되묻기. 최근에 쓴 것이 뒤로 간다(LRU).
_PENDING: "OrderedDict[str, dict]" = OrderedDict()

# ── 고르기로 볼 꼴 ────────────────────────────────────────────────
#
# 넷뿐이다. 화면에 보인 것("  1  전기차 충전소 검색")을 사람이 되뇌는 방식이
# 그 넷이다.
#
#   번호만          "1"  "2번"  "1번요"
#   번호 + 이름     "1 전기차 충전소 검색"     ← 화면 줄 그대로다
#   이름만          "전기차 충전소 검색"
#   차례말          "첫 번째"  "두번째"
#
# **번호가 앞에 있어도 이름이 안 맞으면 고르기가 아니다.** "1호선 지하철역
# 알려줘" 가 그것이다 — 숫자로 시작하지만 뒤가 후보 이름이 아니다.
# **이름을 담고 있어도 통째로 같지 않으면 고르기가 아니다.** "인구 통계 조회
# 방법 알려줘" 가 그것이다.

# 번호만. "1번째" · "1째" 도 같은 자리로 본다.
_NUMBER_ONLY = re.compile(r"^(\d{1,2})\s*(?:번째|번|째)?\s*(?:이요|요)?$")

# 번호 뒤에 무언가 더 붙은 것. 뒤가 후보 이름과 통째로 같을 때만 고르기다.
_NUMBER_NAME = re.compile(r"^(\d{1,2})\s*(?:번째|번|째)?\s*[.)]?\s*(\S.*)$")

# 차례말. **전체가 이것일 때만 받는다.**
#
# 넣을지 재봤다. 화면에 번호가 보이므로 대개는 번호로 답하지만 "첫 번째" 는
# 사람이 자연히 쓰는 말이고, 전체 일치만 받으므로 "첫 번째 역이 어디야" 같은
# 새 발화는 걸리지 않는다. 위험이 없어 넣었다.
_ORDINAL_ONLY = re.compile(r"^(첫|두|세|네|다섯|여섯|일곱|여덟|아홉)\s*(?:번째|째)\s*(?:이요|요)?$")

_ORDINAL_NUMBER = {
    "첫": 1, "두": 2, "세": 3, "네": 4, "다섯": 5,
    "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9,
}

# 문장 끝에 붙어도 뜻이 안 바뀌는 것. 가르기 전에 떼어낸다.
_TRAILING = ".!?~ \t　"


def remember(session_id: str, *, recipe_ids, labels, names, argument, given, text) -> None:
    """직전 되묻기를 이 세션에 남김. 이미 있으면 덮어씀.

    입력  session_id   저쪽 화면이 보낸 것. 빈 문자열이면 아무것도 안 함
          recipe_ids   화면에 보인 번호 순서 그대로의 recipe id 목록
          labels       그 줄에 적힌 이름. recipe_ids 와 같은 순서
          names        그 줄의 끝 이름(사슬이면 마지막 칸). 같은 순서
          argument     그 발화에서 뽑아둔 인자. 없으면 빈 문자열
          given        발화 해석이 쓴 축. 인자가 없을 때 안내 문구를 고름
          text         원래 발화
    규칙  세션이 없거나 빈 문자열이면 기억하지 않음. 그 화면은 이 기능을 안 씀
          후보가 비면 기억하지 않음. 고를 것이 없음
          상한을 넘으면 가장 오래 안 쓴 세션부터 버림
    제약  대화 기록을 쌓지 않는다.
          세션마다 직전 되묻기 하나다. 두 발화 전의 후보를 나중에 고르는
          일이 없어야 한다
    """
    if not session_id or not recipe_ids:
        return

    _PENDING.pop(session_id, None)
    _PENDING[session_id] = {
        "recipe_ids": list(recipe_ids),
        "labels": list(labels),
        "names": list(names),
        "argument": argument or "",
        "given": given,
        "text": text,
        "at": time.monotonic(),
    }

    while len(_PENDING) > MAX_SESSIONS:
        _PENDING.popitem(last=False)


def take(session_id: str) -> dict | None:
    """이 세션의 직전 되묻기를 꺼내면서 지움.

    입력  session_id. 없거나 빈 문자열이면 None
    출력  기억해 둔 dict. 없거나 오래됐으면 None
    규칙  꺼내면 지운다. 고른 뒤에도, 고르기가 아니라고 판정한 뒤에도
          남지 않음. 두 발화 전의 되묻기를 나중에 고르는 일이 없어야 함
          TTL_SECONDS 를 넘긴 것은 없는 것으로 봄
          부르는 김에 오래된 세션을 함께 치움
    """
    _sweep()
    if not session_id:
        return None
    return _PENDING.pop(session_id, None)


def forget(session_id: str) -> None:
    """이 세션의 되묻기를 지움. 없으면 아무 일도 안 함."""
    _PENDING.pop(session_id, None)


def clear() -> None:
    """전부 지움. 시험이 서로 안 섞이게 하는 자리다."""
    _PENDING.clear()


def pick(text: str, pending: dict) -> int | None:
    """이 발화가 기억해 둔 후보 중 하나를 고른 것인가.

    입력  발화 · take 가 꺼낸 되묻기
    출력  고른 후보의 자리(0부터). 고르기가 아니면 None
    규칙  번호만 · 번호 + 이름 · 이름만 · 차례말 넷만 받음
          번호는 후보 수 안에 있어야 함. 벗어나면 고르기가 아님
          이름은 화면 줄과 통째로 같거나 그 줄의 끝 이름과 같아야 함.
          담고 있는 것으로는 안 됨
          이름이 여러 후보에 걸리면 고르기가 아님. 무엇을 고른 것인지 모름
    제약  LLM 을 부르지 않는다.
          느려지고, 같은 문구에 다른 답이 나온다
    """
    total = len(pending.get("recipe_ids") or [])
    if not total:
        return None

    spoken = re.sub(r"\s+", " ", text.strip(_TRAILING).strip())
    if not spoken:
        return None

    number_only = _NUMBER_ONLY.match(spoken)
    if number_only:
        return _in_range(int(number_only.group(1)), total)

    ordinal = _ORDINAL_ONLY.match(spoken)
    if ordinal:
        return _in_range(_ORDINAL_NUMBER[ordinal.group(1)], total)

    number_name = _NUMBER_NAME.match(spoken)
    if number_name:
        index = _in_range(int(number_name.group(1)), total)
        if index is None:
            return None
        # 번호가 맞아도 뒤가 그 줄의 이름이 아니면 고르기가 아니다.
        # "1호선 지하철역 알려줘" 가 여기서 걸러진다.
        return index if number_name.group(2) in _names_of(pending, index) else None

    matched = [
        index for index in range(total) if spoken in _names_of(pending, index)
    ]
    return matched[0] if len(matched) == 1 else None


def _names_of(pending: dict, index: int) -> set:
    """그 자리의 후보를 부를 수 있는 이름.

    출력  화면 줄 그대로와 그 줄의 끝 이름. 둘이 같으면 하나
    규칙  줄이 사슬이면("장소 좌표 변환 -> 인구 통계 조회") 사람은 끝 이름만
          말하기도 함. 둘 다 받음
    """
    labels = pending.get("labels") or []
    names = pending.get("names") or []
    found = {labels[index] if index < len(labels) else "",
             names[index] if index < len(names) else ""}
    found.discard("")
    return found


def _in_range(number: int, total: int) -> int | None:
    """1부터 세는 번호를 0부터 세는 자리로. 벗어나면 None."""
    return number - 1 if 1 <= number <= total else None


def _sweep() -> None:
    """TTL 을 넘긴 세션을 치움. take 가 부를 때마다 돈다."""
    now = time.monotonic()
    for session_id in [
        key for key, entry in _PENDING.items() if now - entry["at"] > TTL_SECONDS
    ]:
        del _PENDING[session_id]
