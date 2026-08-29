"""하단 본문. 해석 그래프와 recipe 칩 목록을 한 문서에 담는다.

둘을 한 iframe 에 넣는 이유 : 나누면 클릭마다 Streamlit 재실행이라 반응이 굼뜨다.
문서 안에서 처리하면 파이썬 왕복이 없어 즉각 반응하고 LLM 도 다시 불리지 않는다.

그래프 변형과 칩 데이터는 백엔드가 미리 만들어 보낸다(POST /render). 여기서는
고르고 그리기만 한다 — 엣지 굵기 · 색 · 순번 규칙이 서버와 JS 두 곳으로
갈라지지 않게 하려는 것이다.

고른 노드(picked)는 이 문서 안 변수로만 둔다 — 다시 그릴 때마다 전체로
돌아가는 것이 맞다. 반면 줌 배율은 Run·등록을 건너도 남아야 하므로
zoom.py 가 세션 저장소에 맡긴다.
"""

import json

import streamlit as st

from demo.ui import config, styles, theme
from demo.ui.components import flow, path_panel, zoom

# JSON 을 <script> 안에 넣을 때 "</script>" 가 섞이면 문서가 거기서 끊긴다.
# 값 안의 "</" 를 이스케이프해 그런 일이 없게 한다.
_SCRIPT_CLOSE = "</"
_SCRIPT_CLOSE_SAFE = "<\\/"


def embed_json(payload) -> str:
    """<script> 안에 넣어도 안전한 JSON 문자열.

    제약  값 안의 "</" 를 그대로 두지 않는다. "</script>" 가 섞이면 문서가
          거기서 끊김
    """
    return json.dumps(payload, ensure_ascii=False).replace(
        _SCRIPT_CLOSE, _SCRIPT_CLOSE_SAFE
    )


def focus_css(left_ratio: float) -> str:
    """iframe 안 스타일. 바깥 styles.py 와 별개. 문서가 분리돼 있음."""
    left = round(left_ratio * 100, 2)
    return f"""
html, body {{
  background: transparent; margin: 0; padding: 0; height: 100%;
  overflow: hidden;
  font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
  color: #E6E8EB;
}}
#wrap {{ display: flex; height: 100%; gap: 10px; }}
#graph {{ flex: 0 0 {left}%; height: 100%; overflow: hidden; }}
#graph svg {{ width: 100%; height: 100%; display: block; }}
/* 칩이 넘치면 세로 스크롤. 잘리게 두지 않는다. */
#list {{ flex: 1 1 auto; height: 100%; overflow-y: auto; padding-right: 4px; min-width: 0; }}

.chain {{ display: flex; align-items: center; flex-wrap: wrap; gap: 0.1rem; padding: 0.22rem 0; }}
.chain + .chain {{ margin-top: 0.8rem; }}
.chip {{
  display: inline-block; padding: 0.2rem 0.6rem;
  border: 1px solid {theme.plain()}; border-radius: 999px;
  background: rgba(255,255,255,0.04); color: #E6E8EB;
  font-size: 0.9rem; white-space: nowrap;
  opacity: 0; animation: chip-in 0.22s ease-out forwards;
  animation-delay: calc(var(--i) * 55ms);
}}
.link {{
  display: inline-flex; align-items: center;
  min-width: 2.6rem; padding: 0 0.12rem;
  opacity: 0; animation: chip-in 0.22s ease-out forwards;
  animation-delay: calc(var(--i) * 55ms + 28ms);
}}
.link .arrow-line {{
  display: block; width: 100%; height: 1px; background: {theme.plain()};
  position: relative; transform-origin: left center;
  animation: line-grow 0.2s ease-out forwards;
  animation-delay: calc(var(--i) * 55ms + 28ms);
}}
.link .arrow-line::after {{
  content: ""; position: absolute; right: -1px; top: -2.5px;
  border-left: 5px solid {theme.plain()};
  border-top: 3px solid transparent; border-bottom: 3px solid transparent;
}}
.empty-note {{ color: {theme.plain()}; font-size: 0.92rem; }}

/* 클릭할 수 있는 노드에만 신호를 준다. 나머지는 눌러도 아무 일이 없으므로
   손 모양을 보여주면 거짓말이 된다. */
#graph g.node.pick {{ cursor: pointer; }}
#graph g.node.pick:hover ellipse, #graph g.node.pick:hover path,
#graph g.node.pick:hover polygon {{ stroke-width: 3; }}
#graph g.node.dim {{ opacity: 0.28; }}

@keyframes chip-in {{ from {{ opacity: 0; transform: translateX(-6px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes line-grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
"""


def focus_html(
    svgs: dict,
    chips: dict,
    left_ratio: float | None = None,
    clickable: list[str] | None = None,
) -> str:
    """그래프와 칩 목록을 나란히 둔 문서. 마지막 노드를 누르면 함께 좁혀짐.

    입력  svgs       {"": 전체, "<마지막노드 id>": 좁힌 것}.
                     파이썬이 미리 만든 변형
          chips      같은 키의 칩 목록 마크업
          left_ratio 그래프가 차지할 폭 비율
          clickable  클릭할 수 있는 노드 id. 후보들의 마지막 노드뿐
    출력  iframe 에 넣을 HTML 문서
    제약  JS 가 다시 칠하지 않는다. 고르기만 함.
          그리는 규칙이 build_dot 한 곳에만 남아야 엣지 굵기 · 색 · 순번이
          두 곳으로 갈라지지 않음
    """
    if left_ratio is None:
        left_ratio = config.LAYOUT["bottom_left_ratio"]

    data = embed_json(
        {"svgs": svgs, "chips": chips, "clickable": list(clickable or [])}
    )

    return f"""<style>{focus_css(left_ratio)}{zoom.ZOOM_CSS}</style>
<div id="wrap">
  <div id="graph"></div>
  <div id="list"></div>
</div>
<script>
const DATA = {data};
let picked = null;

function draw() {{
  const key = (picked && DATA.svgs[picked]) ? picked : "";
  document.getElementById("graph").innerHTML = DATA.svgs[key] || "";
  document.getElementById("list").innerHTML = DATA.chips[key] || "";

  const pickable = new Set(DATA.clickable);

  // 좁힌 뒤에도 클릭 대상은 그대로 둔다. 다른 끝점으로 바로 옮겨갈 수 있어야 한다.
  document.querySelectorAll("#graph g.node").forEach(g => {{
    const title = g.querySelector("title");
    if (!title) return;
    const id = title.textContent.trim();
    if (!pickable.has(id)) return;

    g.classList.add("pick");
    g.addEventListener("click", ev => {{
      ev.stopPropagation();                 // 배경 복귀와 겹치지 않게.
      picked = (picked === id) ? null : id; // 같은 노드 재클릭 = 해제.
      draw();
    }});
  }});
}}

document.body.addEventListener("click", () => {{ picked = null; draw(); }});
draw();
</script>
{zoom.zoom_script(zoom.BOTTOM_KEY)}
{flow.flow_script()}"""


def chip_color(view: dict | None) -> str:
    """칩 색.

    출력  등록 장면이면 theme.new(), 그 밖에는 theme.highlight()
    규칙  등록 장면만 다른 색을 씀. 무엇이 새로 생겼는지가 주인공
    """
    if isinstance(view, dict) and view.get("kind") == "register":
        return theme.new()
    return theme.highlight()


def render_focus_section(
    rendered: dict | None = None,
    view: dict | None = None,
    ratios: dict | None = None,
):
    """하단 본문. 해석 그래프와 recipe 칩 목록을 한 iframe 에 담음.

    입력  rendered  POST /render 응답. variants · chips · focus 가 들어 있음
          view      지금 장면. 칩 색을 고르는 데만 씀
          ratios    config.layout_ratios() 결과
    규칙  후보가 없어도 그림. 실행 전에는 위아래가 같은 지도로 채워진 채
          시작하고, NO_MATCH 에서는 지도는 떠 있는데 켜지는 길이 하나도 없음.
          문구 없이 그림으로 읽힘
    제약  iframe 을 없애지 않는다. 항상 있어야 결과가 생길 때 화면이 안 튐
    """
    if not rendered or not rendered.get("variants"):
        return

    color = chip_color(view)
    chips = rendered.get("chips") or {}
    ratios = ratios or config.LAYOUT

    st.components.v1.html(
        focus_html(
            rendered["variants"],
            {key: path_panel.chips_markup(chains, color) for key, chains in chips.items()},
            ratios["bottom_left_ratio"],
            (rendered.get("focus") or {}).get("last_nodes") or [],
        ),
        height=styles.panel_heights(ratios)["bottom"],
    )
