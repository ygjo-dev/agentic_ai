"""그래프 줌·팬, 그리고 고른 경로에 화면을 맞추는 것. 상단과 하단이 같은 스크립트를 쓴다.

두 벌로 나누어 쓰지 않는다 — 한쪽만 고치는 일이 반드시 생기고, 그러면 시연 중에
위아래가 다르게 반응한다. 여기서 한 벌을 만들고 양쪽이 키만 다르게 부른다.

SVG 를 다시 그리지 않고 CSS transform 만 건다. 색·굵기·순번을 정하는 규칙은
여전히 build_dot 한 곳에만 남는다 — "파이썬이 변형을 만들고 JS 는 고르기만
한다" 는 원칙과 부딪히지 않는다.

저장소는 세 단계로 내려간다. Streamlit 1.60 의 컴포넌트 iframe 샌드박스는
`allow-same-origin allow-scripts allow-downloads` 라 웹 스토리지가 동작하지만,
그건 정적으로 확인한 것이지 실행 시 보장이 아니다. 막히면 부모 창 전역으로,
그것도 막히면 이 문서 안 변수로 떨어진다. 어느 단계에서도 예외를 올리지 않는다.

**자동 맞춤도 여기 있다.** 배율·평행이동을 이미 이 한 곳이 쥐고 있어서다 —
따로 스크립트를 두면 scale 사본이 둘이 되어 손으로 굴린 값과 어긋난다.
고르는 손잡이(강조 엣지 class)는 밖에서 받는다. 이 모듈은 무엇이 강조인지
정하지 않는다.

맞출 때는 곧장 확대하지 않고 전체 그림을 잠깐 보여준 뒤 그 자리로 좁혀
들어간다(INTRO_*). 도착점은 그대로라 좁혀진 뒤 화면은 예전과 같다.
"""

# 확대 폭. 근거와 전후 값은 NOTES.md 「쉰두째」 · 「예순다섯째」.
# 축소는 두 칸이면 바닥이라 그대로 둔다. 확대는 노드 하나가 화면을 채울 때까지
# 가고, 한 칸이 3% 라 바닥에서 끝까지 마흔여섯 번 남짓이다.
#
# **2.5 에서 3.5 로 올렸다** (「예순다섯째」). 자동 맞춤에 따로 상한을 두지 않고
# 손으로 굴릴 때와 천장을 하나로 뒀다 — 따로 두면 자동으로 3.0 까지 간 화면에서
# 휠을 한 칸 올리는 순간 2.5 로 뚝 떨어진다. 시연 중에 그 튐이 가장 나쁘다.
# 3.5 인 이유는 시연 발화 넷을 실제로 재보니 필요한 배율이 2.07 ~ 3.00 이고
# (NOTES.md 「예순다섯째」 3번 표) 그보다 조금 남겨둔 값이기 때문이다.
# 한 칸의 크기(ZOOM_STEP)는 안 바꿨다 — 손맛은 그대로이고 천장만 올라간다.
MIN_SCALE = 0.9
MAX_SCALE = 3.5
ZOOM_STEP = 1.03
# 이만큼 안 움직였으면 클릭으로 본다. 없으면 그래프를 옮길 때마다 후보가
# 좁혀지고 배경 클릭으로 전체 복귀돼 버린다.
DRAG_THRESHOLD = 5

# 자동으로 맞출 때 강조 상자 둘레에 남기는 여백(화면 px, 한 변). 하단 칸이
# 1500x523px 이라 좌우 24px 은 폭의 3.2%, 위아래는 높이의 9.2% 다.
# 배율에는 거의 영향이 없다 — 시연 발화 넷에서 24 를 40 으로 늘려도 필요한
# 배율이 2.07 -> 2.02 로만 움직인다(「예순다섯째」 3번). 즉 이 값은 "맞추기
# 위해" 가 아니라 "선이 칸 테두리에 닿아 보이지 않게" 두는 값이다.
# getBoundingClientRect 는 선 굵기를 포함해서 재므로 굵은 teal 선(8pt) 몫을
# 여기서 따로 더할 필요가 없다.
FIT_PAD = 24

# ------------------------------------------------------------ 전체를 먼저 보여주기
# **여기 셋만 고치면 된다. INTRO 를 False 로 두면 예전처럼 곧장 확대된다.**
#
# 확대된 그림이 곧장 나타나면 그것이 전체의 어디쯤인지 사람 눈이 못 잡는다.
# 그래서 자동 맞춤을 할 때 전체 그림(배율 1)을 한 번 보여주고, 잠깐 머문 뒤
# 그 자리로 좁혀 들어간다. 좁혀진 뒤 화면은 예전과 완전히 같다 —
# 도착점은 fit() 이 재던 그 값 그대로이고 여기서는 가는 길만 만든다.
#
#   HOLD 0.35초  전체 그림에 머무는 시간. 눈이 한 번 훑기에 이만큼은 필요하다.
#                더 짧으면 깜빡임으로 보이고, 0.5초를 넘기면 멈춘 것처럼 보인다
#   MOVE 1.0초   좁혀 들어가는 시간. 합쳐서 1.35초라 영상이 안 늘어진다.
#                0.6초대는 눈이 못 따라가고 2초를 넘기면 기다리게 된다
#
# 움직임을 끈 사람에게는 안 보여준다(prefers-reduced-motion). flow.py 와 같은
# 규칙이다 — 그 화면은 예전처럼 곧장 확대된 그림이 뜬다.
INTRO_ENABLED = True
INTRO_HOLD_MS = 350
INTRO_MOVE_MS = 1000

# 상단과 하단은 서로 다른 그래프이므로 배율도 따로 기억한다.
TOP_KEY = "recipe_zoom_top"
BOTTOM_KEY = "recipe_zoom_bottom"

_TEMPLATE = """
(function () {
  var KEY = "__KEY__", SEL = "__SEL__", HL = "__HL__";
  var MIN = __MIN__, MAX = __MAX__, STEP = __STEP__, THRESHOLD = __THRESHOLD__;
  var PAD = __PAD__;
  var INTRO = __INTRO__, HOLD = __HOLD__, MOVE = __MOVE__;

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
  // 마지막으로 맞춰준 경로의 서명. 이것이 그대로면 다시 안 맞춘다 —
  // 손으로 굴려둔 배율을 다시 그릴 때마다 덮으면 안 되기 때문이다.
  var fitted = saved.sig || "";

  function apply() {
    var svg = box.querySelector("svg");
    if (!svg) return;
    svg.style.transformOrigin = "0 0";
    svg.style.transform =
      "translate(" + tx + "px," + ty + "px) scale(" + scale + ")";
  }

  function commit() {
    apply();
    save({scale: scale, tx: tx, ty: ty, sig: fitted});
  }

  // ---------------------------------------------------------- 강조 고르기
  // **색이나 굵기로 고르지 않는다.** flow.py 와 같은 손잡이(class)를 쓴다 —
  // 색은 상수라 바뀌고, 굵기로 고르면 등록 경로 · 물러난 경로가 함께 걸린다.
  function flowEdges() {
    try { return box.querySelectorAll("g." + HL); } catch (e) { return []; }
  }

  // 강조된 엣지의 <title> 은 "꼬리->머리" 다(Graphviz 실측). 이것을 모아
  // 정렬한 것이 경로의 서명이고, 양 끝에서 강조 노드 id 도 함께 얻는다.
  // **노드에는 class 가 없다.** 붙이려면 dot.py 를 고쳐야 하는데 그건 이번
  // 범위 밖이라, 엣지 제목에서 끌어낸다.
  function endpoints(edges, into) {
    var names = [];
    for (var i = 0; i < edges.length; i++) {
      var title = edges[i].querySelector("title");
      if (!title) continue;
      var text = title.textContent.replace(/\\s+/g, "");
      names.push(text);
      if (!into) continue;
      var ends = text.split("->");
      for (var k = 0; k < ends.length; k++) if (ends[k]) into[ends[k]] = true;
    }
    names.sort();
    return names.join("|");
  }

  // 강조 엣지와 그 양 끝 노드. **엣지만 재면 노드 이름이 화면 밖으로 나간다** —
  // 「문서에서 철도안전법」은 엣지만 재면 5.10배가 필요해 두 노드 상자(195.6px)가
  // 칸을 넘는다. 노드까지 재면 3.00배다 (NOTES.md 「예순다섯째」 3번).
  function pieces() {
    var picked = [], wanted = {};
    try {
      var edges = flowEdges();
      for (var i = 0; i < edges.length; i++) picked.push(edges[i]);
      endpoints(edges, wanted);

      var nodes = box.querySelectorAll("g.node");
      for (var j = 0; j < nodes.length; j++) {
        var title = nodes[j].querySelector("title");
        if (title && wanted[title.textContent.replace(/\\s+/g, "")]) picked.push(nodes[j]);
      }
    } catch (e) {}
    return picked;
  }

  // ---------------------------------------------------------- 전체 -> 그 자리
  // 도착점은 fit() 이 정한다. 여기는 가는 길만 만든다 — 끝나면 예전과 같은
  // 화면이다. 어느 줄에서 걸려도 도착점으로 그냥 건너뛴다.
  var wait = null, anim = null;

  function halt() {
    if (wait) { clearTimeout(wait); wait = null; }
    if (anim) { try { window.cancelAnimationFrame(anim); } catch (e) {} anim = null; }
  }

  // 움직임을 끈 사람에게는 안 보여준다. flow.py 와 같은 규칙이다.
  function calm() {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
    catch (e) { return false; }
  }

  // 양 끝이 느리고 가운데가 빠르다. 등속이면 출발과 도착이 툭 끊겨 보인다.
  function ease(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  function land(to) {
    scale = to.s; tx = to.x; ty = to.y;
    commit();
  }

  function glide(to) {
    halt();
    // 전체 그림. SVG 는 칸에 비율대로 맞춰 들어가 있으므로 배율 1 이 전체다.
    scale = 1; tx = 0; ty = 0;
    apply();
    wait = setTimeout(function () {
      wait = null;
      var t0 = 0;
      function step(now) {
        if (!t0) t0 = now;
        var k = MOVE > 0 ? Math.min(1, (now - t0) / MOVE) : 1, e = ease(k);
        scale = 1 + (to.s - 1) * e;
        tx = to.x * e;
        ty = to.y * e;
        apply();
        if (k < 1) { anim = window.requestAnimationFrame(step); return; }
        anim = null;
        commit();   // 저장은 도착해서 한 번만. 중간 값을 남기면 안 된다
      }
      try { anim = window.requestAnimationFrame(step); } catch (e) { land(to); }
    }, HOLD);
  }

  // ---------------------------------------------------------- 자동 맞춤
  // 어느 줄에서 걸려도 아무 일도 안 하고 지금 화면을 그대로 둔다.
  function fit() {
    try {
      if (!HL) return;
      var sig = endpoints(flowEdges(), null);
      if (!sig || sig === fitted) return;   // 강조가 없거나 경로가 그대로다

      var parts = pieces();
      if (!parts.length) return;

      var frame = box.getBoundingClientRect();
      if (!(frame.width > 0) || !(frame.height > 0)) return;

      var left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
      for (var i = 0; i < parts.length; i++) {
        var r = parts[i].getBoundingClientRect();
        if (!(r.width > 0) && !(r.height > 0)) continue;
        if (r.left < left) left = r.left;
        if (r.top < top) top = r.top;
        if (r.right > right) right = r.right;
        if (r.bottom > bottom) bottom = r.bottom;
      }
      // 화면 좌표를 변형 전 좌표로 되돌린다. 지금 걸린 배율 · 평행이동을
      // 빼는 것이라 손으로 굴려둔 상태에서 눌러도 같은 답이 나온다.
      var w = (right - left) / scale, h = (bottom - top) / scale;
      if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return;
      var x = (left - frame.left - tx) / scale, y = (top - frame.top - ty) / scale;

      var next = Math.min((frame.width - 2 * PAD) / w, (frame.height - 2 * PAD) / h);
      if (!isFinite(next) || next <= 0) return;
      next = Math.min(MAX, Math.max(MIN, next));

      var to = {
        s: next,
        x: (frame.width - next * w) / 2 - next * x,
        y: (frame.height - next * h) / 2 - next * y
      };
      // 서명을 먼저 남긴다. 미끄러지는 동안 다시 그려도 처음부터 되돌아가지
      // 않게 하려는 것이다.
      fitted = sig;
      if (INTRO && !calm()) { glide(to); return; }
      land(to);
    } catch (e) {}
  }

  // 다시 그린 뒤에는 얹고 나서 맞춘다. 순서가 뒤바뀌면 아직 안 걸린 배율로
  // 상자를 재게 된다.
  function refresh() { apply(); fit(); }

  // ---------------------------------------------------------- 휠
  box.addEventListener("wheel", function (ev) {
    ev.preventDefault();   // 그래프 위에서만 가로챈다. 바깥 스크롤은 그대로다.
    halt();                // 사람이 손을 대면 미끄러짐은 그 자리에서 끝난다
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
    halt();
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
  // 서명은 그대로 둔다 — 여기서 지우면 다시 그리는 순간 자동 맞춤이 되살아나
  // 복귀가 한 순간만 살아 있게 된다. 복귀는 사람이 부른 것이므로 이긴다.
  box.addEventListener("dblclick", function (ev) {
    ev.preventDefault();
    halt();
    scale = 1; tx = 0; ty = 0;
    commit();
  });

  // 하단은 노드를 누를 때마다 SVG 를 통째로 갈아끼운다. 그때 transform 이
  // 날아가므로 새 SVG 에 다시 얹는다.
  new MutationObserver(refresh).observe(box, {childList: true, subtree: false});
  refresh();
  // 첫 그림에서 칸 크기가 아직 0 이면 위에서 아무 일도 안 일어났다. 그때는
  // 더 부를 사람이 없으므로(엣지가 안 바뀌니 MutationObserver 도 안 운다)
  // 한 프레임 뒤에 한 번만 더 본다. 이미 맞췄으면 서명이 같아 그냥 돌아온다.
  try { window.requestAnimationFrame(fit); } catch (e) {}
})();
"""


def zoom_script(
    storage_key: str, selector: str = "#graph", highlight_class: str = ""
) -> str:
    """줌 · 팬 · 자동 맞춤 한 벌.

    입력  storage_key      배율을 기억할 키. 상단 · 하단이 서로 달라야 함
          selector         줌을 걸 컨테이너. 그 안의 첫 <svg> 에 transform 이 붙음
          highlight_class  강조 엣지에 붙은 SVG class. 이것으로 고른 경로를
                           찾아 화면을 맞춤. 비우면 자동 맞춤을 아예 안 함
    출력  <script> 태그까지 포함한 문자열
    규칙  맞출 때 전체 그림을 먼저 보여주고 좁혀 들어감(INTRO_ENABLED).
          꺼도 · 움직임을 끈 화면에서도 도착점은 같음
    제약  예외를 안 올린다. 강조가 없거나 상자를 못 재면 아무 일도 안 하고
          지금 화면을 그대로 둔다
    """
    body = (
        _TEMPLATE.replace("__KEY__", storage_key)
        .replace("__SEL__", selector)
        .replace("__HL__", highlight_class)
        .replace("__MIN__", str(MIN_SCALE))
        .replace("__MAX__", str(MAX_SCALE))
        .replace("__STEP__", str(ZOOM_STEP))
        .replace("__THRESHOLD__", str(DRAG_THRESHOLD))
        .replace("__PAD__", str(FIT_PAD))
        .replace("__INTRO__", "true" if INTRO_ENABLED else "false")
        .replace("__HOLD__", str(INTRO_HOLD_MS))
        .replace("__MOVE__", str(INTRO_MOVE_MS))
    )
    return f"<script>{body}</script>"


# 드래그 중에 글자가 잡히면 파란 선택 블록이 생겨 지저분하다.
ZOOM_CSS = """
#graph { cursor: grab; user-select: none; }
#graph:active { cursor: grabbing; }
"""
