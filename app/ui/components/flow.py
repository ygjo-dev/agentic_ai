"""고른 실행 경로 위로 흐르는 표시. **원본 선을 안 건드린다.**

굵은 teal 실선(penwidth 8)은 정지 그림이라 어느 쪽으로 흐르는지 한눈에 안
들어온다. 「쉰셋째」에서 순번(xlabel)을 뺀 뒤로 방향 단서가 화살촉뿐이다.
그 자리를 메우는 것이 여기다.

**같은 자리에 사본을 하나 더 얹는다.** 원본 <path> 는 손대지 않고, 그 옆에
점선 사본을 붙여 그것만 움직인다. 그래서 :

    캡처(정지)      JS 가 안 도는 곳에서는 사본이 아예 안 생긴다.
                    서버가 낸 SVG 그대로다 — 보도자료 이미지가 지금과 같다
    애니메이션 정지  prefers-reduced-motion 이면 얹지 않는다.
                    화면이 지금과 똑같아진다

**색으로 고르지 않는다.** build_dot 이 해석 경로에만 class="flow" 를 붙이고
(dot.FLOW_CLASS) 여기서는 그것만 고른다. 색은 상수라 바뀔 수 있고, 굵기로
고르면 등록 경로 · 물러난 경로까지 함께 걸린다.

zoom.py 와 같은 규칙을 따른다 — 상단 · 하단이 한 벌을 쓰고, 어느 단계에서도
예외를 올리지 않는다. 상단은 실선을 아예 안 그리므로(draw_solid=False) 걸리는
엣지가 없고, 아무 일도 일어나지 않는다.
"""

# build_dot 이 붙이는 class 이름. **app/ui/graph_svg/dot.FLOW_CLASS 와 같아야 한다.**
# 여기서 import 하지 않는 이유 : app/ui 는 그리는 규칙을 서버에서 받아 쓰는
# 쪽이고 graph_svg 를 직접 부르지 않는다. 두 값이 어긋나면
# dev/tests/app/ui/test_path_flow_document.py 가 운다.
FLOW_CLASS = "flow"
# 얹은 사본에 붙는 이름. 두 번 얹지 않으려고 표시해 둔다.
OVERLAY_CLASS = "flowline"

# ------------------------------------------------------------ 눈에 보이는 값
# **시연장에서 조절할 값이다. 여기 넷만 고치면 된다.**
#
# 단위는 SVG 사용자 단위(= DOT 포인트)다. 화면 픽셀이 아니다.
# 하단 그래프는 viewBox 2383x811 을 523px 높이 패널에 xMidYMid meet 로 넣는다.
# 그래서 배율은 아무리 커도 523/811 = 0.645 이고, 폭에 걸리면 그보다 작다
# (실측 범위 0.45~0.65). 아래 값은 그 범위에서 고른 것이다.
#
#   DASH 50   화면에서 22~32px. 이보다 짧으면 점처럼 보이고 방향이 안 읽힌다
#   GAP  50   화면에서 22~32px. **대시와 같아 주기의 절반씩이다.** 칸이 있어야
#             아래 teal 실선이 계속 보인다 — 주인공은 여전히 원본 선이고
#             이것은 그 위를 지나가는 표시다
#   PERIOD 1.1초에 한 칸(100단위 = 화면 45~65px)이라 초속 41~59px 이다.
#             걷는 속도로 읽히고 시선을 뺏지 않는다. 0.5초대면 깜빡임처럼 보인다
#   WIDTH 4   PATH_PENWIDTH(8)의 절반. 양옆에 teal 이 2 단위씩 남아 원본 선이
#             테두리처럼 계속 보인다
FLOW_DASH = 50
FLOW_GAP = 50
FLOW_PERIOD_SECONDS = 1.1
FLOW_WIDTH = 4

# 흐르는 표시의 색. **순백이다** — 반투명 합성이 아니라 흰색 그대로다.
# 배경(#0E1117) 대비 18.90, teal(#14B8A6) 위 대비 2.49.
#
# **팔레트에 색을 새로 더한 것이 아니다.** 흰색은 색상(hue)이 없어 새 뜻을
# 만들지 않는다 — teal 선 위에서 "다른 색이 지나간다" 가 아니라 "그 선이
# 밝아진다" 로 읽힌다. 팔레트의 다른 색은 전부 뜻이 있어 못 쓴다 :
# 금색은 「대상」, 분홍은 「새로 생긴 것」, 보라는 「관련」이다.
#
# teal 계통을 밝히는 안(#99F6E4 · teal-200, 배경 14.99 · teal 위 1.97)도
# 검토했다. **사람이 화면을 보고 순백을 골랐다** (2026-08-30, NOTES.md 「쉰넷째」).
#
# 노드 테두리(8.76)보다 밝지만 위계가 뒤집힌 것은 아니다 — 면이 아니라 4단위
# 줄이고, 주기의 절반만 그 자리에 있고, 고른 경로 위에만 있다.
FLOW_SHEEN = "#FFFFFF"
FLOW_OPACITY = 1.0

_TEMPLATE = """
(function () {
  var SEL = "__SEL__", CLS = "__CLS__", MARK = "__MARK__";
  var DASH = __DASH__, GAP = __GAP__, PERIOD = __PERIOD__;
  var WIDTH = __WIDTH__, SHEEN = "__SHEEN__", ALPHA = __ALPHA__;

  // 움직임을 원하지 않는다고 밝힌 사람에게는 아무것도 얹지 않는다.
  // 그러면 화면이 지금과 한 픽셀도 다르지 않다.
  try {
    var mq = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq && mq.matches) return;
  } catch (e) {}

  var box = document.querySelector(SEL);
  if (!box) return;

  // 규칙은 한 번만 넣는다. 사본은 나중에 몇 번을 다시 만들어도 이것을 받는다.
  try {
    var style = document.createElement("style");
    style.textContent =
      "@keyframes recipeflow {" +
      " from { stroke-dashoffset: " + (DASH + GAP) + "; }" +
      " to { stroke-dashoffset: 0; } }" +
      " path." + MARK + " { animation: recipeflow " + PERIOD + "s linear infinite; }";
    (document.head || document.documentElement).appendChild(style);
  } catch (e) {}

  function overlay() {
    try {
      var edges = box.querySelectorAll("g." + CLS);
      for (var i = 0; i < edges.length; i++) {
        var group = edges[i];
        if (group.querySelector("path." + MARK)) continue;  // 두 번 얹지 않는다
        var line = group.querySelector("path");
        if (!line) continue;

        // 사본이라 d 가 원본과 정확히 같다. 좌표를 다시 계산하지 않는다.
        // Graphviz 는 "꼬리 -> 머리" 순서로 d 를 내므로(실측) 대시가 0 을
        // 향해 줄어들면 실행 순서 방향으로 흐른다.
        var copy = line.cloneNode(false);
        copy.setAttribute("class", MARK);
        copy.setAttribute("fill", "none");
        copy.setAttribute("stroke", SHEEN);
        copy.setAttribute("stroke-opacity", ALPHA);
        copy.setAttribute("stroke-width", WIDTH);
        copy.setAttribute("stroke-dasharray", DASH + " " + GAP);
        group.appendChild(copy);
      }
    } catch (e) {}
  }

  // 하단은 노드를 누를 때마다 SVG 를 통째로 갈아끼운다. zoom.py 와 같은 자리다.
  try {
    new MutationObserver(overlay).observe(box, {childList: true, subtree: false});
  } catch (e) {}
  overlay();
})();
"""


def flow_script(selector: str = "#graph") -> str:
    """흐르는 표시 한 벌.

    입력  selector  그래프 컨테이너. 그 안의 class="flow" 엣지에만 얹음
    출력  <script> 태그까지 포함한 문자열
    제약  원본 <path> 를 안 건드린다. 사본을 더할 뿐이다
          예외를 안 올린다. 시연 중에 그래프가 죽는 것이 가장 나쁘다
    """
    body = (
        _TEMPLATE.replace("__SEL__", selector)
        .replace("__CLS__", FLOW_CLASS)
        .replace("__MARK__", OVERLAY_CLASS)
        .replace("__DASH__", str(FLOW_DASH))
        .replace("__GAP__", str(FLOW_GAP))
        .replace("__PERIOD__", str(FLOW_PERIOD_SECONDS))
        .replace("__WIDTH__", str(FLOW_WIDTH))
        .replace("__SHEEN__", FLOW_SHEEN)
        .replace("__ALPHA__", str(FLOW_OPACITY))
    )
    return f"<script>{body}</script>"
