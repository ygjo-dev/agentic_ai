"""화면 CSS.

Streamlit 기본 크롬(햄버거 · Deploy · 푸터 · 넓은 상단 여백)을 걷어내고,
패널에 고정 높이를 준다. 패널 자체는 vh 로 준다 — 시연 화면 해상도가
무엇일지 모르므로 픽셀로 박으면 노트북에서 잘린다.

다만 iframe 만은 예외다. 안쪽 문서의 뷰포트가 height 속성으로 정해지므로
CSS 로는 못 덮는다. 그쪽은 panel_heights() 가 픽셀로 계산해 넘긴다.

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


# 화면을 재서 정한 값들. iframe 높이를 픽셀로 계산할 때 빼야 하는 것들이다.
BAND_HEIGHT = 62      # 하단 위쪽 발화 띠 (1.45rem 한 줄 + 아래 여백)
PANEL_PADDING = 26    # 패널 테두리 + 안쪽 여백 (위아래 합)
PAGE_PADDING = 30     # block-container 위아래 패딩


def panel_heights(ratios: dict) -> dict:
    """iframe 에 넘길 픽셀 높이.

    입력  config.layout_ratios() 결과
    출력  {"top": px, "bottom": px}. 화면이 아주 작아도 최소 200
    규칙  상단 + 하단 + 크롬 + 여백의 합이 뷰포트를 넘으면 페이지에 세로
          스크롤이 생김. 그것을 막는 것이 이 계산의 목적
    제약  높이를 CSS 로 늘리지 않는다.
          st.components.v1.html 은 iframe 을 height 속성으로 고정해 만듦.
          바깥 컨테이너에 height:100% 를 줘도 iframe 자신의 높이는 안 바뀜.
          예전에는 그래프가 420px 에 갇혔고 종횡비가 걸려 폭까지 눌렸음.
          높이 하나가 폭까지 죽이고 있었음
    """
    viewport = ratios["viewport_height"]
    chrome = viewport * ratios["chrome_vh"] / 100

    top = viewport * ratios["top_ratio"] - chrome - PANEL_PADDING
    bottom = viewport * (1 - ratios["top_ratio"]) - BAND_HEIGHT - PANEL_PADDING - PAGE_PADDING

    # 화면이 아주 작아도 최소한은 보이게 둔다.
    return {"top": max(int(top), 200), "bottom": max(int(bottom), 200)}


# 한글 폰트 폴백. Malgun Gothic 단독이면 맥·리눅스에서 깨진다.
FONT_STACK = (
    '"Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", '
    '"Nanum Gothic", sans-serif'
)


def page_css(ratios: dict) -> str:
    """화면 전체 CSS.

    입력  config.layout_ratios() 결과
    출력  <style> 블록
    """
    top_vh = round(ratios["top_ratio"] * 100 - ratios["chrome_vh"], 2)
    bottom_vh = round((1 - ratios["top_ratio"]) * 100 - 2, 2)

    return f"""<style>
/* ---------------------------------------------- Streamlit 크롬 제거 */
#MainMenu, header, footer {{ visibility: hidden; height: 0; }}
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"] {{ display: none !important; }}

.block-container {{
  padding: 1.2rem 1.6rem 0.5rem 1.6rem;
  max-width: 100%;
}}
html, body, [class*="css"] {{ font-family: {FONT_STACK}; }}

/* ---------------------------------------------- 패널 */
.st-key-top_panel {{ height: {top_vh}vh; min-height: 300px; }}
.st-key-bottom_panel {{
  height: {bottom_vh}vh;
  min-height: 260px;
  border-top: 1px solid rgba(255,255,255,0.10);
  padding-top: 0.5rem;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}}
/* 위쪽 얇은 띠는 내용만큼, 아래 본문이 남은 높이를 전부 가져간다. */
.st-key-bottom_band {{ flex: 0 0 auto; }}
.st-key-bottom_body {{ flex: 1 1 auto; min-height: 0; overflow: hidden; }}
/* 높이는 건드리지 않는다. iframe 은 height 속성으로 만들어지고, 그 속성이
   곧 안쪽 문서의 뷰포트다 — CSS 로 늘리면 파이썬이 계산한 값과 둘로 갈린다.
   폭만 채운다. */
.st-key-bottom_body iframe {{ width: 100% !important; border: 0; }}
.st-key-bottom_body [data-testid="stIFrame"],
.st-key-bottom_body [data-testid="stCustomComponentV1"],
.st-key-bottom_body > div,
.st-key-bottom_body [data-testid="stVerticalBlock"] {{ height: 100%; }}

/* 카드처럼 보이게. 테두리는 아주 옅게 — 선이 도드라지면 내용이 묻힌다. */
.st-key-graph_panel, .st-key-side_panel {{
  height: 100%;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px;
  background: rgba(255,255,255,0.02);
  padding: 0.6rem 0.8rem;
  overflow: hidden;
}}
.st-key-side_panel {{ overflow-y: auto; }}

/* 높이는 panel_heights() 가 픽셀로 정한다. 여기서는 폭만 채운다. */
.st-key-graph_panel iframe {{
  width: 100% !important;
  border: 0;
}}
.st-key-graph_panel [data-testid="stIFrame"],
.st-key-graph_panel [data-testid="stCustomComponentV1"] {{ height: 100%; }}
.st-key-graph_panel > div, .st-key-graph_panel [data-testid="stVerticalBlock"] {{
  height: 100%;
}}

/* ---------------------------------------------- 하단 패널 */
.utterance {{
  font-size: 1.45rem;
  font-weight: 600;
  color: #E6E8EB;
  margin: 0.1rem 0 0.5rem 0;
  line-height: 1.35;
}}
.new-badge {{
  display: inline-block;
  background: {theme.new()};
  color: #12141A;
  font-size: 0.72rem;
  font-weight: 700;
  padding: 0.1rem 0.45rem;
  border-radius: 6px;
  vertical-align: 0.18em;
  margin-right: 0.4rem;
}}
/* 오류 한 줄. 정상일 때는 아예 안 나온다. */
.note {{
  color: {theme.plain()};
  font-size: 0.8rem;
  opacity: 0.85;
  padding: 0.15rem 0;
}}

/* ---------------------------------------------- 따라 보기 */
/* 저쪽 답과 단계 줄은 등폭이라야 읽힌다. 도구 이름 칸을 ljust 로 맞춰 왔고
   비례폭으로 내면 그 정렬이 통째로 무너진다. */
.st-key-follow_slot [data-testid="stCode"] {{ margin-bottom: 0.3rem; }}
.st-key-follow_slot pre {{ padding: 0.45rem 0.55rem; }}
.st-key-follow_slot code {{ font-size: 0.75rem; line-height: 1.45; white-space: pre; }}

/* ---------------------------------------------- 경로 사슬 */
/* recipe 하나가 한 줄. 여러 줄일 때 rid 폭을 고정해 세로가 맞는다. */
.chain {{
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.1rem;
  padding: 0.22rem 0;
}}
.chip {{
  display: inline-block;
  padding: 0.24rem 0.7rem;
  border: 1px solid {theme.plain()};
  border-radius: 999px;
  background: rgba(255,255,255,0.04);
  color: #E6E8EB;
  font-size: 0.97rem;
  white-space: nowrap;          /* 사슬의 흐름이 끊기면 안 된다 */
  opacity: 0;
  animation: chip-in 0.22s ease-out forwards;
  animation-delay: calc(var(--i) * 55ms);
}}
.link {{
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 4.2rem;
  padding: 0 0.15rem;
  opacity: 0;
  animation: chip-in 0.22s ease-out forwards;
  animation-delay: calc(var(--i) * 55ms + 28ms);
}}
/* 화살표는 선 + 촉. 선이 왼쪽에서 오른쪽으로 자라난다. */
.link .arrow-line {{
  display: block;
  width: 100%;
  height: 1px;
  background: {theme.plain()};
  position: relative;
  transform-origin: left center;
  animation: line-grow 0.2s ease-out forwards;
  animation-delay: calc(var(--i) * 55ms + 28ms);
}}
.link .arrow-line::after {{
  content: "";
  position: absolute;
  right: -1px; top: -2.5px;
  border-left: 5px solid {theme.plain()};
  border-top: 3px solid transparent;
  border-bottom: 3px solid transparent;
}}

@keyframes chip-in {{
  from {{ opacity: 0; transform: translateX(-6px); }}
  to   {{ opacity: 1; transform: none; }}
}}
@keyframes line-grow {{
  from {{ transform: scaleX(0); }}
  to   {{ transform: scaleX(1); }}
}}

/* ---------------------------------------------- 대기 스켈레톤 */
.skeleton {{ padding: 0.4rem 0; }}
.skel-row {{
  height: 1.5rem;
  margin: 0.42rem 0;
  border-radius: 8px;
  width: calc(62% - var(--i) * 10%);
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

/* 입력 영역은 3B 에서 손본다. 지금은 여백만 줄인다. */
.st-key-side_panel [data-testid="stVerticalBlock"] {{ gap: 0.55rem; }}
</style>"""
