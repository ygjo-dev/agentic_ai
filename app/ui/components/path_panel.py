"""후보 recipe 목록과 발화 띠.

그래프 문서 오른쪽 살펴보기 칸의 후보 목록 마크업을 만들고(그래프 문서가 싣는다),
그래프 위 얇은 띠에 발화 · 오류 · 기다리는 표시를 그린다.

경로를 무엇으로 채울지는 백엔드가 정한다(그리기 패키지의 focus.py). 여기는 이름
사슬을 받아 칩으로 그리기만 한다 — 순서 계산이 두 곳에 있으면 그래프와 목록이
서로 다른 순서를 말하게 된다.

후보 한 줄은 recipe id · 사람이 읽는 기능 메뉴(menu.md)의 제목과 설명(무엇을 할 수
있는가) · 실제 노드 이름 사슬(어떻게 하는가)이다. 화면이 만든 설명 문장은 없다.
발화 해석용 menu.yaml 의 문장은 여기 실리지 않는다.

마크업 생성은 Streamlit 없이 부를 수 있는 순수 함수다(테스트 때문).
"""

import html

import streamlit as st

from app.ui import config, styles

# 안내 문구를 두지 않는다. 실행 전에는 지도가 그대로 떠 있고, NO_MATCH 면
# 지도는 있는데 켜지는 길이 없다 — 문구 없이 그림으로 읽힌다.
# 발표자가 말로 설명하므로 화면에 글이 필요 없고, 글이 없으면 오류가 났을 때 티가 난다.

# 후보 줄의 꼬리표. 해석이 고른 것과 되묻는 후보를 가른다.
CHOSEN_TAG = "선택"
CANDIDATE_TAG = "후보"


def chip(name: str, index: int, color: str) -> str:
    """노드 이름 하나.

    입력  이름 · 순서(등장 애니메이션용) · 테두리 색
    출력  .chip span 마크업
    제약  여기서는 이름을 두 줄로 접지 않는다.
          그래프의 노드는 접혀 있지만 접으면 사슬의 흐름이 끊겨 읽힘
    """
    return (
        f'<span class="chip" style="--i:{index}; border-color:{color}">'
        f"{html.escape(name)}</span>"
    )


def link(index: int) -> str:
    """칩 사이의 화살표.

    입력  순서(등장 애니메이션용)
    출력  .link span 마크업
    제약  인터페이스 이름을 적지 않는다.
          무엇이 흘러가는지는 노드 이름만으로 읽히고, 같은 이름이 여러 줄에
          반복되면 화면이 글자로 덮임
    """
    return (
        f'<span class="link" style="--i:{index}">'
        f'<span class="arrow-line"></span>'
        f"</span>"
    )


def path_chain(names: list[str], color: str) -> str:
    """이름 사슬 하나를 칩 한 줄로.

    입력  이름 목록 · 칩 테두리 색
    출력  .chain div 마크업. 비면 빈 .chain
    """
    if not names:
        return '<div class="chain"></div>'

    parts = []
    for position, name in enumerate(names):
        parts.append(chip(name, position, color))
        if position < len(names) - 1:
            parts.append(link(position))

    return f'<div class="chain">{"".join(parts)}</div>'


def recipe_row(recipe_id: str, names: list[str], chosen: bool, color: str,
               entry: dict | None = None) -> str:
    """후보 recipe 한 줄. id · 꼬리표 · 기능 이름 · 기능 설명 · 노드 이름 사슬.

    입력  entry  사람이 읽는 기능 메뉴 한 항목 {"title", "description"}. 없으면 None
    출력  .recipe div 마크업
    규칙  해석이 고른 recipe 면 「선택」, 그 밖은 「후보」
          id 는 정답표 · 평가 화면 · KRRI 되묻기 목록과 맞춰 볼 수 있게 적음
          기능 이름 · 설명은 사슬보다 먼저 둠. 무엇을 하는지가 어떻게 하는지보다 먼저 읽혀야 함
          설명의 문단 나눔은 CSS(pre-line)로 살림
          메뉴 항목이 없으면 그 칸만 빠지고 id · 사슬은 그대로임
    제약  설명 문장을 줄이거나 다시 쓰지 않는다. 줄 수를 자르지 않고 살펴보기 칸 세로 스크롤에 맡김
    """
    tag = (f'<span class="tag chosen">{CHOSEN_TAG}</span>' if chosen
           else f'<span class="tag">{CANDIDATE_TAG}</span>')
    entry = entry or {}
    title = entry.get("title") or ""
    description = entry.get("description") or ""
    text = (f'<div class="rtitle">{html.escape(title)}</div>' if title else "") + (
        f'<div class="rfn">{html.escape(description)}</div>' if description else "")
    return (
        f'<div class="recipe"><div class="rhead">'
        f'<span class="rid">{html.escape(recipe_id)}</span>{tag}</div>'
        f"{text}{path_chain(names, color)}</div>"
    )


def recipe_rows_markup(chains: list[list[str]], order: list[str],
                       chosen: str | None, color: str,
                       recipes: dict | None = None) -> str:
    """후보 recipe 목록 전체. 그래프 문서의 살펴보기 칸에 들어감.

    입력  이름 사슬 목록 · 줄 차례에 맞춘 recipe id · 해석이 고른 recipe · 칩 색 ·
          render 응답의 recipes ({recipe id: {"title", "description"}})
    출력  .recipe div 여러 개. 후보가 없으면 빈 문자열
    제약  줄 차례를 다시 매기지 않는다.
          서버가 낸 chips 차례가 곧 그래프 변형 차례임
    """
    recipes = recipes or {}
    return "".join(
        recipe_row(recipe_id, names, recipe_id == chosen, color, recipes.get(recipe_id))
        for recipe_id, names in zip(order, chains or [])
    )


def chosen_recipe(view) -> str | None:
    """해석이 고른 recipe. 되묻기라 고른 것이 없으면 None."""
    if not isinstance(view, dict) or "error" in view:
        return None
    return (view.get("result") or {}).get("recipe_id") or None


def recipe_status(view, count: int) -> str:
    """후보 목록 머리에 적을 판정 한 마디.

    입력  지금 장면 · 후보 수
    출력  실행 전 · 오류면 빈 문자열
    규칙  resolve 의 status 를 그대로 옮김. SELECT 「선택」 · CLARIFY 「후보 N개 · 되묻기」 ·
          NO_MATCH 「맞는 Recipe 없음」
          status 가 없는 옛 회차는 고른 recipe 가 있으면 「선택」, 없으면 「후보 N개」
    """
    if not isinstance(view, dict) or "error" in view or view.get("kind") != "resolve":
        return ""
    result = view.get("result") or {}
    status = result.get("status")
    if status == "NO_MATCH" or not count:
        return "맞는 Recipe 없음"
    if status == "CLARIFY":
        return f"후보 {count}개 · 되묻기"
    if status == "SELECT" or result.get("recipe_id"):
        return "선택"
    return f"후보 {count}개"


def utterance_markup(utterance: str | None) -> str:
    """입력 발화. 화면에서 가장 눈에 띄어야 하는 문장."""
    if not utterance:
        return ""
    return f'<div class="utterance">“{html.escape(utterance)}”</div>'





def skeleton_markup() -> str:
    """응답을 기다리는 동안 띠에 한 줄. LLM 지연이 길어 스피너만으로는 멈춘 것처럼 보임.

    제약  그래프를 가리지 않는다. 기다리는 동안에도 지도는 그대로 보임
    """
    return '<div class="skeleton"><div class="skel-row" style="--i:0"></div></div>'


def band_markup(view: dict | None) -> str:
    """그래프 위 얇은 띠. 발화뿐.

    입력  지금 장면
    출력  마크업. 장면이 없으면 빈 문자열
    제약  범례를 두지 않는다. 색이 무엇인지는 발표자가 말함
          경로 사슬을 여기 두지 않는다. 그래프 문서의 살펴보기 칸이 그림
    """
    if not isinstance(view, dict):
        return ""

    return utterance_markup(view.get("utterance"))


def render_band(view: dict | None):
    """띠를 그림.

    규칙  오류도 여기서 작게 처리. 실패는 DEBUG 와 무관하게 언제나 보여줌
    """
    if isinstance(view, dict) and "error" in view:
        # 실패는 DEBUG 와 무관하게 언제나 보여준다. 화면이 조용하면 더 나쁘다.
        st.markdown(styles.note_markup(view["error"]), unsafe_allow_html=True)
        return

    st.markdown(band_markup(view), unsafe_allow_html=True)

    if config.DEBUG and isinstance(view, dict) and view.get("result"):
        st.caption(f"reason : {view['result'].get('reason', '')}")
