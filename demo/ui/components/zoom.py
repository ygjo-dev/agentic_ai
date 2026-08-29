"""그래프 줌·팬. 상단과 하단이 같은 스크립트를 쓴다.

두 벌로 나누어 쓰지 않는다 — 한쪽만 고치는 일이 반드시 생기고, 그러면 시연 중에
위아래가 다르게 반응한다. 여기서 한 벌을 만들고 양쪽이 키만 다르게 부른다.

SVG 를 다시 그리지 않고 CSS transform 만 건다. 색·굵기·순번을 정하는 규칙은
여전히 build_dot 한 곳에만 남는다 — "파이썬이 변형을 만들고 JS 는 고르기만
한다" 는 원칙과 부딪히지 않는다.

저장소는 세 단계로 내려간다. Streamlit 1.60 의 컴포넌트 iframe 샌드박스는
`allow-same-origin allow-scripts allow-downloads` 라 웹 스토리지가 동작하지만,
그건 정적으로 확인한 것이지 실행 시 보장이 아니다. 막히면 부모 창 전역으로,
그것도 막히면 이 문서 안 변수로 떨어진다. 어느 단계에서도 예외를 올리지 않는다.
"""

# 확대 폭. 근거와 전후 값은 NOTES.md 「쉰두째」.
# 축소는 두 칸이면 바닥이라 그대로 둔다. 확대는 노드 하나가 화면을 채울 때까지
# 가고, 한 칸이 30% 라 바닥에서 끝까지 아홉 번 남짓이다.
MIN_SCALE = 0.9
MAX_SCALE = 2.5
ZOOM_STEP = 1.03
# 이만큼 안 움직였으면 클릭으로 본다. 없으면 그래프를 옮길 때마다 후보가
# 좁혀지고 배경 클릭으로 전체 복귀돼 버린다.
DRAG_THRESHOLD = 5

# 상단과 하단은 서로 다른 그래프이므로 배율도 따로 기억한다.
TOP_KEY = "recipe_zoom_top"
BOTTOM_KEY = "recipe_zoom_bottom"

_TEMPLATE = """
(function () {
  var KEY = "__KEY__", SEL = "__SEL__";
  var MIN = __MIN__, MAX = __MAX__, STEP = __STEP__, THRESHOLD = __THRESHOLD__;

  // ---------------------------------------------------------- 저장소
  var memory = null;

  function load() {
    try {
      var raw = window.sessionStorage.getItem(KEY);
      if (raw) return JSON.parse(raw);
    } catch (e) {}
    try {
      var bag = window.parent.__recipeZoom;
      if (bag && bag[KEY]) return bag[KEY];
    } catch (e) {}
    return memory;
  }

  function save(state) {
    memory = state;
    try { window.sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
    try {
      var top = window.parent;
      if (!top.__recipeZoom) top.__recipeZoom = {};
      top.__recipeZoom[KEY] = state;
    } catch (e) {}
  }

  // ---------------------------------------------------------- 상태
  var box = document.querySelector(SEL);
  if (!box) return;

  var saved = load() || {};
  var scale = saved.scale || 1, tx = saved.tx || 0, ty = saved.ty || 0;

  function apply() {
    var svg = box.querySelector("svg");
    if (!svg) return;
    svg.style.transformOrigin = "0 0";
    svg.style.transform =
      "translate(" + tx + "px," + ty + "px) scale(" + scale + ")";
  }

  function commit() { apply(); save({scale: scale, tx: tx, ty: ty}); }

  // ---------------------------------------------------------- 휠
  box.addEventListener("wheel", function (ev) {
    ev.preventDefault();   // 그래프 위에서만 가로챈다. 바깥 스크롤은 그대로다.
    var rect = box.getBoundingClientRect();
    var px = ev.clientX - rect.left, py = ev.clientY - rect.top;
    var next = Math.min(MAX, Math.max(MIN, scale * (ev.deltaY < 0 ? STEP : 1 / STEP)));
    // 커서가 가리키던 지점이 제자리에 남게 평행이동을 함께 옮긴다.
    tx = px - (px - tx) * (next / scale);
    ty = py - (py - ty) * (next / scale);
    scale = next;
    commit();
  }, {passive: false});

  // ---------------------------------------------------------- 드래그
  var dragging = false, moved = false;
  var startX = 0, startY = 0, baseX = 0, baseY = 0;

  box.addEventListener("mousedown", function (ev) {
    if (ev.button !== 0) return;
    dragging = true; moved = false;
    startX = ev.clientX; startY = ev.clientY;
    baseX = tx; baseY = ty;
  });

  window.addEventListener("mousemove", function (ev) {
    if (!dragging) return;
    var dx = ev.clientX - startX, dy = ev.clientY - startY;
    if (!moved && Math.abs(dx) < THRESHOLD && Math.abs(dy) < THRESHOLD) return;
    moved = true;
    tx = baseX + dx; ty = baseY + dy;
    apply();
  });

  window.addEventListener("mouseup", function () {
    if (!dragging) return;
    dragging = false;
    if (moved) commit();
  });

  // 드래그로 끝난 손짓은 클릭이 아니다. 잡기(capture) 단계에서 삼켜야
  // 노드 좁히기와 배경 복귀 핸들러에 닿기 전에 멈춘다.
  window.addEventListener("click", function (ev) {
    if (!moved) return;
    moved = false;
    ev.stopPropagation();
    ev.preventDefault();
  }, true);

  // ---------------------------------------------------------- 복귀
  // 시연 중에 길을 잃었을 때 빠져나올 길. 안내 문구 없이도 짐작되는 몸짓이다.
  box.addEventListener("dblclick", function (ev) {
    ev.preventDefault();
    scale = 1; tx = 0; ty = 0;
    commit();
  });

  // 하단은 노드를 누를 때마다 SVG 를 통째로 갈아끼운다. 그때 transform 이
  // 날아가므로 새 SVG 에 다시 얹는다.
  new MutationObserver(apply).observe(box, {childList: true, subtree: false});
  apply();
})();
"""


def zoom_script(storage_key: str, selector: str = "#graph") -> str:
    """줌 · 팬 스크립트 한 벌.

    입력  storage_key  배율을 기억할 키. 상단 · 하단이 서로 달라야 함
          selector     줌을 걸 컨테이너. 그 안의 첫 <svg> 에 transform 이 붙음
    출력  <script> 태그까지 포함한 문자열
    """
    body = (
        _TEMPLATE.replace("__KEY__", storage_key)
        .replace("__SEL__", selector)
        .replace("__MIN__", str(MIN_SCALE))
        .replace("__MAX__", str(MAX_SCALE))
        .replace("__STEP__", str(ZOOM_STEP))
        .replace("__THRESHOLD__", str(DRAG_THRESHOLD))
    )
    return f"<script>{body}</script>"


# 드래그 중에 글자가 잡히면 파란 선택 블록이 생겨 지저분하다.
ZOOM_CSS = """
#graph { cursor: grab; user-select: none; }
#graph:active { cursor: grabbing; }
"""
