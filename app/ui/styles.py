"""화면 CSS.

Streamlit 기본 크롬(햄버거 · Deploy · 푸터 · 넓은 상단 여백)을 걷어낸다.

서비스 화면은 위에서 아래로 셋이다.
  입력 줄     발화 · Run · KRRI_ASAP 연동. 한 줄
  발화 띠     해석한 발화 · 오류 · 기다리는 표시. 한 줄
  그래프      남은 높이 전부. 따라 보기 회차가 있으면 오른쪽에 실행 기록 칸

그래프 iframe 만은 CSS 로 높이를 못 준다. 안쪽 문서의 뷰포트가 height 속성으로
정해지므로 graph_height() 가 픽셀로 계산해 넘긴다.

st.container(key="x") 는 DOM 에 .st-key-x 클래스를 남긴다. 그것을 잡는다.
"""

import html

from app.ui import theme


def note_markup(message: str) -> str:
    """구석에 작게 남기는 한 줄. 오류 전용.

    출력  .note div 마크업
    제약  큰 박스로 띄우지 않는다.
          정상일 때는 아예 안 나와 화면을 안 어지럽히고, 나왔을 때는 "서버가
          죽은 화면" 과 "NO_MATCH 화면" 을 구분해줌. 그 둘이 똑같이 보이는
          것이 시연에서 가장 나쁜 사고임
    """
    return f'<div class="note">{html.escape(str(message))}</div>'


# 화면을 재서 정한 값들. 그래프 iframe 높이를 픽셀로 계산할 때 빼야 하는 것들이다.
INPUT_BAR_HEIGHT = 58   # 입력 줄 (입력칸 한 줄 + 블록 사이 간격)
BAND_HEIGHT = 50        # 발화 띠 (1.2rem 한 줄 + 블록 사이 간격)
PAGE_PADDING = 30       # block-container 위아래 패딩과 여유
MIN_GRAPH_HEIGHT = 320


def graph_height(ratios: dict) -> int:
    """그래프 iframe 에 넘길 픽셀 높이.

    입력  config.layout_ratios() 결과
    출력  창 높이에서 크롬 · 입력 줄 · 발화 띠 · 여백을 뺀 값. 최소 MIN_GRAPH_HEIGHT
    규칙  합이 뷰포트를 넘으면 페이지에 세로 스크롤이 생김. 그것을 막는 것이
          이 계산의 목적
    제약  높이를 CSS 로 늘리지 않는다.
          st.components.v1.html 은 iframe 을 height 속성으로 고정해 만듦.
          바깥 컨테이너에 height:100% 를 줘도 iframe 자신의 높이는 안 바뀜
    """
    viewport = ratios["viewport_height"]
    chrome = viewport * ratios["chrome_vh"] / 100
    height = viewport - chrome - INPUT_BAR_HEIGHT - BAND_HEIGHT - PAGE_PADDING
    return max(int(height), MIN_GRAPH_HEIGHT)


# 한글 폰트 폴백. Malgun Gothic 단독이면 맥·리눅스에서 깨진다.
FONT_STACK = (
    '"Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", '
    '"Nanum Gothic", sans-serif'
)


def page_css() -> str:
    """화면 전체 CSS.

    출력  <style> 블록
    """
    return f"""<style>
/* ---------------------------------------------- Streamlit 크롬 제거 */
#MainMenu, header, footer {{ visibility: hidden; height: 0; }}
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"] {{ display: none !important; }}

.block-container {{
  padding: 0.5rem 1.6rem 0.5rem 1.6rem;
  max-width: 100%;
}}
html, body, [class*="css"] {{ font-family: {FONT_STACK}; }}

/* ---------------------------------------------- 탭 */
/* 서비스 화면 · 테스트 탭 줄. 그래프 높이는 픽셀로 박혀 있어 탭 줄이 먹는 만큼
   위 여백(block-container 위 0.5rem · 탭 높이 · 탭 패널 위)을 줄여 돌려준다.
   안 줄이면 서비스 화면에 페이지 스크롤이 생긴다. */
.st-key-main_tabs [role="tab"] {{ height: 2rem; }}
.st-key-main_tabs [data-testid="stTabPanel"] {{ padding-top: 0.25rem; }}

/* ---------------------------------------------- 입력 줄 */
.st-key-input_bar [data-testid="stHorizontalBlock"] {{ align-items: center; }}
.st-key-input_bar [data-testid="stTextInput"] input {{ font-size: 1rem; }}
/* 연동 스위치와 상태 한 줄을 가로로 나란히. 주기 조각이 상태를 그 옆에 다시 찍는다. */
.st-key-follow_slot [data-testid="stVerticalBlock"] {{
  flex-direction: row; align-items: center; gap: 0.9rem; flex-wrap: wrap;
}}
.st-key-follow_slot [data-testid="stVerticalBlock"] > div {{ width: auto !important; }}
.st-key-follow_slot [data-testid="stCaptionContainer"] p {{ margin: 0; }}

/* ---------------------------------------------- 발화 띠 */
.st-key-band {{ min-height: 1.9rem; }}
.utterance {{
  font-size: 1.2rem;
  font-weight: 600;
  color: #E6E8EB;
  margin: 0;
  line-height: 1.5;
}}
/* 오류 한 줄. 정상일 때는 아예 안 나온다. */
.note {{
  color: {theme.plain()};
  font-size: 0.8rem;
  opacity: 0.85;
  padding: 0.15rem 0;
}}

/* ---------------------------------------------- 그래프 */
/* 높이는 graph_height() 가 픽셀로 정한다. 여기서는 폭만 채운다. */
.st-key-main_panel iframe {{ width: 100% !important; border: 0; }}
.st-key-main_panel {{
  border-top: 1px solid rgba(255,255,255,0.08);
  padding-top: 0.4rem;
}}

/* ---------------------------------------------- 따라 보기 실행 기록 */
/* 실행 답과 단계 줄은 등폭이라야 읽힌다. 도구 이름 칸을 ljust 로 맞춰 왔고
   비례폭으로 내면 그 정렬이 통째로 무너진다. */
.st-key-follow_panel [data-testid="stCode"] {{ margin-bottom: 0.3rem; }}
.st-key-follow_panel pre {{ padding: 0.45rem 0.55rem; }}
.st-key-follow_panel code {{ font-size: 0.75rem; line-height: 1.45; white-space: pre-wrap; }}

/* ---------------------------------------------- 대기 스켈레톤 */
.skeleton {{ padding: 0.35rem 0; }}
.skel-row {{
  height: 1.2rem;
  border-radius: 8px;
  width: calc(42% - var(--i) * 10%);
  background: linear-gradient(90deg,
    rgba(255,255,255,0.05) 25%,
    rgba(255,255,255,0.11) 37%,
    rgba(255,255,255,0.05) 63%);
  background-size: 400% 100%;
  animation: shimmer 1.2s ease-in-out infinite;
  animation-delay: calc(var(--i) * 120ms);
}}
@keyframes shimmer {{
  from {{ background-position: 100% 0; }}
  to   {{ background-position: 0 0; }}
}}
</style>"""
