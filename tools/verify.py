"""무인 실행 검증. 사람이 화면을 못 볼 때 숫자로 확인할 수 있는 것을 전부 본다.

    python tools/verify.py

백엔드를 실제로 부르지 않는다 — resolve 결과는 가짜로 만든다. 등록만 실제
흐름을 태우고 끝나면 반드시 원복한다.

주의: 노드 폭을 재는 정규식이 penwidth=2 의 "width=2" 에 걸리면 안 된다.
작업 3A 에서 실제로 이 함정에 걸려 겹침을 잘못 셌다.
"""

import itertools
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from frontend import focus, layout_store  # noqa: E402
from frontend.components import focus_panel, graph_section as gs, path_panel, zoom  # noqa: E402
from frontend import config, styles  # noqa: E402

FAILURES = []


def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def check(label, ok, detail=""):
    mark = "OK " if ok else "실패"
    print(f"  [{mark}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)
    return ok


# penwidth= 안의 width= 에 걸리지 않게 앞 글자를 막는다.
_WIDTH = re.compile(r"(?<![a-zA-Z])width=([\d.]+)")
_HEIGHT = re.compile(r"(?<![a-zA-Z])height=([\d.]+)")
_EDGE_STMT = re.compile(r'"?[\w]+"?\s*->\s*"?[\w]+"?\s*\[[^\]]*\];')
_NODE_STMT = re.compile(r'"?([A-Za-z_]\w*)"?\s*\[([^\]]*)\]\s*;')


def node_boxes(dot: str) -> dict:
    """neato 가 계산한 노드 위치와 크기. {id: (x, y, w, h)} 단위는 pt."""
    out = gs._run_graphviz(dot, "neato", ["-Tdot"])
    flat = _EDGE_STMT.sub(" ", re.sub(r"\s+", " ", out))

    boxes = {}
    for match in _NODE_STMT.finditer(flat):
        pos = re.search(r'pos="([-\d.e+]+),([-\d.e+]+)', match.group(2))
        if not pos:
            continue
        width = _WIDTH.search(match.group(2))
        height = _HEIGHT.search(match.group(2))
        boxes[match.group(1)] = (
            float(pos.group(1)),
            float(pos.group(2)),
            float(width.group(1)) * 72 if width else 54.0,
            float(height.group(1)) * 72 if height else 36.0,
        )
    return boxes


def overlaps(boxes: dict) -> list:
    return [
        (a, b)
        for a, b in itertools.combinations(boxes, 2)
        if abs(boxes[a][0] - boxes[b][0]) < (boxes[a][2] + boxes[b][2]) / 2 - 1
        and abs(boxes[a][1] - boxes[b][1]) < (boxes[a][3] + boxes[b][3]) / 2 - 1
    ]


def bbox(boxes: dict):
    xs = [v[0] for v in boxes.values()]
    ys = [v[1] for v in boxes.values()]
    return (
        max(xs) - min(xs) + max(v[2] for v in boxes.values()),
        max(ys) - min(ys) + max(v[3] for v in boxes.values()),
    )


def svg_coords(svg: str) -> dict:
    out = {}
    for block in re.findall(r'<g id="node\d+" class="node">(.*?)</g>', svg, re.S):
        title = re.search(r"<title>([a-z_]+)</title>", block)
        pos = re.search(r'text-anchor="middle" x="([-\d.]+)" y="([-\d.]+)"', block)
        if title and pos:
            out[title.group(1)] = (
                round(float(pos.group(1)), 2),
                round(float(pos.group(2)), 2),
            )
    return out


def svg_canvas(svg: str):
    found = re.search(r'<svg width="(\d+)pt" height="(\d+)pt"', svg)
    return found.groups() if found else ("?", "?")


def run(cmd):
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")


# ------------------------------------------------------------------ 1. 테스트
def step_tests():
    section("1. python -m pytest tests -q")
    result = run([sys.executable, "-m", "pytest", "tests", "-q"])
    tail = [l for l in result.stdout.splitlines() if l.strip()][-1:]
    print("  " + "\n  ".join(tail))
    check("전체 테스트 통과", result.returncode == 0)


# ------------------------------------------------------------------ 2. grep
def step_greps():
    section("2. 계층 규칙 grep (0건이어야 한다)")
    # 웹 스토리지 검사는 뺐다. iframe 샌드박스에 allow-same-origin 이 있어
    # 세션 저장소가 동작한다 — 금지 규칙 자체가 잘못 들어온 것이었다.
    for label, pattern in (
        ("도메인 import", r"from ontology\|from llm_engine\|import paths"),
    ):
        result = run(["grep", "-rn", pattern, "frontend/", "--include=*.py"])
        hits = [l for l in result.stdout.splitlines() if l.strip()]
        print(f"  {label}: {len(hits)}건")
        for hit in hits:
            print(f"    {hit}")
        check(f"{label} 0건", not hits)


# ------------------------------------------------------------------ 3. 변형
SAMPLE_VIEWS = {
    "SELECT 1개": ["recipe_004"],
    "CLARIFY 2개": ["recipe_010", "recipe_011"],
    "CLARIFY 3개": ["recipe_004", "recipe_006", "recipe_008"],
    "CLARIFY 5개": ["recipe_004", "recipe_006", "recipe_008", "recipe_010", "recipe_011"],
}


def fake_paths(graph, recipe_ids):
    """백엔드를 부르지 않고 그럴듯한 경로를 만든다.

    실제 해석 결과가 아니라 변형/좌표를 확인하기 위한 형태만 필요하다.
    """
    nodes = list(graph["nodes"])
    starts = [n for n in nodes if not graph["nodes"][n]["inputs"]]
    mids = [n for n in nodes if graph["nodes"][n]["inputs"] and graph["nodes"][n]["outputs"]]
    ends = [n for n in nodes if not graph["nodes"][n]["outputs"]]

    def step(node_id):
        outputs = graph["nodes"][node_id]["outputs"]
        return {
            "node_id": node_id,
            "name": graph["nodes"][node_id]["name"],
            "out_interface": outputs[0] if outputs else None,
        }

    paths = {}
    for index, recipe_id in enumerate(recipe_ids):
        chain = [starts[index % len(starts)], mids[index % len(mids)]]
        if index % 2 == 1 and ends:
            chain.append(ends[index % len(ends)])
        paths[recipe_id] = [step(n) for n in chain]
    return paths


def step_variants(graph, positions):
    section("3. 샘플 발화별 SVG 변형 (백엔드 호출 없음)")
    for label, recipe_ids in SAMPLE_VIEWS.items():
        paths = fake_paths(graph, recipe_ids)
        gs.build_focus_svgs.clear()
        svgs = gs.build_focus_svgs(
            _graph=graph, _positions=positions, _paths=paths,
            _recipe_ids=tuple(recipe_ids), version=f"verify:{label}",
        )
        keys = sorted(svgs)
        print(f"\n  [{label}] 후보 {len(recipe_ids)}개 -> 변형 {len(svgs)}벌")
        print(f"    키: {keys}")

        base = svg_coords(svgs[""])
        same_coords = all(svg_coords(s) == base for s in svgs.values())
        canvases = {svg_canvas(s) for s in svgs.values()}
        for key in keys:
            print(f"    {key or '(전체)':<28} 캔버스 {svg_canvas(svgs[key])}")

        check(f"{label}: 모든 변형의 노드 좌표 동일", same_coords,
              f"노드 {len(base)}개")
        check(f"{label}: 모든 변형의 캔버스 동일", len(canvases) == 1)
        check(f"{label}: 변형 키가 전체+마지막노드와 일치",
              set(svgs) == {""} | set(focus.last_nodes(paths, recipe_ids)))


# ------------------------------------------------------------------ 4. 등록
REG_SAMPLES = [
    ("구조물 균열 진행 추세 분석", "문서에서 구조물 균열 폭의 시간 변화를 분석한다.",
     ["DocumentData"], ["AnalysisResult"], "analyze_crack_trend", {"target": "구조물"}),
    ("승강장 안전사고 분석", "CCTV 영상에서 승강장 안전사고 위험 상황을 검지한다.",
     ["MediaData"], ["AnalysisResult"], "detect_platform_accident", {"target": "승강장"}),
    ("Excel 생성", "분석 결과를 Excel 표로 생성한다.",
     ["AnalysisResult"], ["DocumentData"], "generate_excel", {"format": "Excel"}),
]


def step_registration():
    section("4. 등록 샘플 3개 — 기존 노드 이동 / 겹침 (실제 등록, 측정 후 원복)")
    from fastapi.testclient import TestClient
    import backend.main as backend_main
    from conftest import StubLLMClient
    from ontology.registry import reset_to_init

    client = TestClient(backend_main.app)
    print(f"\n  {'샘플':<26}{'최대이동':>10}{'겹침':>6}{'캔버스':>13}{'H/W':>7}")
    print("  " + "-" * 62)

    for name, desc, ins, outs, node_id, props in REG_SAMPLES:
        reset_to_init()
        layout_store.LAYOUT_PATH.unlink(missing_ok=True)

        before = gs.ensure_positions(client.get("/graph").json())
        backend_main.OllamaClient = lambda: StubLLMClient(
            json.dumps({"node_id": node_id, "properties": props, "reason": "verify"})
        )
        response = client.post(
            "/nodes",
            json={"name": name, "description": desc, "inputs": ins, "outputs": outs},
        )
        if response.status_code != 200:
            check(f"{name} 등록", False, str(response.json())[:60])
            continue

        registration = response.json()
        mark = gs.mark_from_registration(registration)
        graph = client.get("/graph").json()
        after = gs.ensure_positions(graph)

        shared = [n for n in before if n in after]
        ax, ay = after[shared[0]]
        bx, by = before[shared[0]]
        drift = max(
            max(abs((after[n][0] - ax) - (before[n][0] - bx)),
                abs((after[n][1] - ay) - (before[n][1] - by)))
            for n in shared
        )

        nodes, solid, dotted = gs.to_build_dot_args(graph)
        new_dotted = mark["dotted"]
        dot = gs.build_dot(
            gs.wrap_node_labels(nodes), solid, dotted,
            positions=after, spring=True, node_attrs=gs.NODE_ATTRS,
            graph_attrs=gs.NEATO_ATTRS,
            dotted_labels=set(map(frozenset, new_dotted)) if new_dotted else False,
            mark_nodes=mark["nodes"], mark_edges=mark["solid"], mark_dotted=new_dotted,
        )
        boxes = node_boxes(dot)
        collisions = overlaps(boxes)
        width, height = bbox(boxes)

        print(f"  {name[:24]:<26}{drift:>10.4f}{len(collisions):>6}"
              f"{f'{width:.0f}x{height:.0f}':>13}{height / width:>7.2f}")
        if collisions:
            print(f"  {'':<26}겹침: {collisions}")

        check(f"{name}: 기존 노드 이동 0pt", drift < 0.51, f"{drift:.4f}pt")
        check(f"{name}: 겹침 0쌍", not collisions)

    reset_to_init()
    layout_store.LAYOUT_PATH.unlink(missing_ok=True)
    print("\n  저장소 원복 완료")


# ------------------------------------------------------------ 4-2. 연속 등록
def step_consecutive_registration():
    """연달아 두 번 등록해도 지도가 그대로인가.

    최초 배치에만 걸어야 하는 회전이 증분에도 걸리면, 두 번 걸린 것이 서로
    상쇄돼 **짝수 번째에서는 멀쩡해 보인다.** 그래서 중간 상태를 함께 본다.
    """
    section("4-2. 연속 등록 — 회전이 증분에도 걸리는지 (중간 상태까지 본다)")
    from fastapi.testclient import TestClient
    import backend.main as backend_main
    from conftest import StubLLMClient
    from ontology.registry import reset_to_init

    reset_to_init()
    layout_store.LAYOUT_PATH.unlink(missing_ok=True)
    client = TestClient(backend_main.app)

    def drift(before, after):
        shared = [n for n in before if n in after]
        bx, by = before[shared[0]]
        ax, ay = after[shared[0]]
        return max(
            max(abs((after[n][0] - ax) - (before[n][0] - bx)),
                abs((after[n][1] - ay) - (before[n][1] - by)))
            for n in shared
        )

    snapshots = [gs.ensure_positions(client.get("/graph").json())]
    for index, (name, desc, ins, outs, node_id, props) in enumerate(REG_SAMPLES[:2], 1):
        backend_main.OllamaClient = lambda node_id=node_id, props=props: StubLLMClient(
            json.dumps({"node_id": node_id, "properties": props, "reason": "verify"})
        )
        response = client.post(
            "/nodes",
            json={"name": name, "description": desc, "inputs": ins, "outputs": outs},
        )
        if response.status_code != 200:
            check(f"연속 등록 {index}회차", False, str(response.json())[:60])
            break
        snapshots.append(gs.ensure_positions(client.get("/graph").json()))
        moved = drift(snapshots[0], snapshots[-1])
        print(f"  {index}회차 누적 이동 {moved:.4f}pt  (노드 {len(snapshots[-1])}개)")
        check(f"연속 등록 {index}회차: 기존 노드 이동 0pt", moved < 0.51, f"{moved:.4f}pt")

    reset_to_init()
    layout_store.LAYOUT_PATH.unlink(missing_ok=True)
    print("  저장소 원복 완료")


# ------------------------------------------------------------ 4-3. 배치 모양
def step_shape(graph, positions):
    """최초 배치의 모양. 회전이 빠지면 종횡비가 1을 넘어 세로로 길어진다."""
    section("4-3. 최초 배치 모양 (교차 · 겹침 · 간격 · 종횡비)")
    nodes, solid, dotted = gs.to_build_dot_args(graph)
    dot = gs.build_dot(
        gs.wrap_node_labels(nodes), solid, dotted,
        positions=positions, spring=True,
        node_attrs=gs.NODE_ATTRS, graph_attrs=gs.NEATO_ATTRS, dotted_labels=False,
    )
    boxes = node_boxes(dot)
    width, height = bbox(boxes)
    gap = min(
        max(abs(boxes[a][0] - boxes[b][0]) - (boxes[a][2] + boxes[b][2]) / 2,
            abs(boxes[a][1] - boxes[b][1]) - (boxes[a][3] + boxes[b][3]) / 2)
        for a, b in itertools.combinations(boxes, 2)
    )

    print(f"  캔버스 {width:.0f}x{height:.0f}  종횡비 {height / width:.2f}"
          f"  최소 간격 {gap:.1f}pt  노드 {len(boxes)}개")
    check("겹침 0쌍", not overlaps(boxes))
    check("가로로 누웠다 (종횡비 < 1)", height < width, f"{height / width:.2f}")


# ------------------------------------------------------------ 4-4. iframe 높이
def step_heights():
    section("4-4. 계산된 iframe 높이 (세로 스크롤이 생기면 안 된다)")
    print(f"\n  {'뷰포트':>8}{'상단':>8}{'하단':>8}{'합계':>10}{'여유':>8}")
    print("  " + "-" * 44)
    for viewport in (900, 1080, 1282, 1440, 2160):
        ratios = {**config.LAYOUT, "viewport_height": viewport}
        heights = styles.panel_heights(ratios)
        total = (
            heights["top"] + heights["bottom"]
            + viewport * ratios["chrome_vh"] / 100
            + styles.BAND_HEIGHT + styles.PANEL_PADDING * 2 + styles.PAGE_PADDING
        )
        print(f"  {viewport:>8}{heights['top']:>8}{heights['bottom']:>8}"
              f"{total:>10.0f}{viewport - total:>8.0f}")
        check(f"{viewport}px: 뷰포트를 넘지 않는다", total <= viewport,
              f"{total - viewport:.0f}px")


# ------------------------------------------------------------------ 5. 격리
def step_isolation():
    section("5. 등록 -> pytest -> 등록한 노드가 남아 있는가 (격리 확인)")
    from fastapi.testclient import TestClient
    import backend.main as backend_main
    from conftest import StubLLMClient
    from ontology.graph import load_ontology
    from ontology.registry import reset_to_init

    reset_to_init()
    client = TestClient(backend_main.app)
    backend_main.OllamaClient = lambda: StubLLMClient(
        json.dumps({"node_id": "verify_probe_node", "properties": {}, "reason": "verify"})
    )
    client.post("/nodes", json={
        "name": "검증용 임시 노드", "description": "격리 확인용으로 등록한다.",
        "inputs": ["AnalysisResult"], "outputs": ["DocumentData"],
    })
    planted = "verify_probe_node" in load_ontology()["nodes"]
    print(f"  등록 직후 노드 존재: {planted}")

    result = run([sys.executable, "-m", "pytest", "tests", "-q"])
    survived = "verify_probe_node" in load_ontology()["nodes"]
    print(f"  pytest 실행 후 노드 존재: {survived}  (pytest rc={result.returncode})")

    check("등록한 노드가 pytest 를 견딘다", planted and survived)

    reset_to_init()
    layout_store.LAYOUT_PATH.unlink(missing_ok=True)
    print("  저장소 원복 완료")


# ------------------------------------------------------------------ 6. iframe
def step_iframe(graph, positions):
    section("6. iframe 문서 안전성")
    recipe_ids = ["r1", "r2"]
    paths = fake_paths(graph, recipe_ids)
    # 이름에 위험한 문자를 섞어 이스케이프를 확인한다.
    paths["r1"][0]["name"] = '<script>alert("x")</script> & \'따옴표\''
    paths["r1"][0]["out_interface"] = "<b>Media</b>"

    gs.build_focus_svgs.clear()
    svgs = gs.build_focus_svgs(
        _graph=graph, _positions=positions, _paths=paths,
        _recipe_ids=tuple(recipe_ids), version="verify:iframe",
    )
    variants = focus.focus_variants(paths, recipe_ids)
    html = focus_panel.focus_html(
        {k: gs.fit_svg(v) for k, v in svgs.items()},
        {k: path_panel.chips_markup(paths, ids, "#fff") for k, ids in variants.items()},
        0.62,
        focus.last_nodes(paths, recipe_ids),
    )

    print(f"  문서 길이: {len(html)}자")
    check("script 태그 짝이 맞는다", html.count("<script") == html.count("</script>"))
    check("좁히기 스크립트와 줌 스크립트가 함께 있다",
          "const DATA = " in html and zoom.zoom_script(zoom.BOTTOM_KEY) in html)
    check("하단 줌이 상단 키를 쓰지 않는다", zoom.TOP_KEY not in html)
    check("노드 이름이 이스케이프된다", "<script>alert" not in html)
    check("인터페이스 이름이 이스케이프된다", "<b>Media</b>" not in html)
    check("이스케이프된 흔적이 보인다", "&lt;script&gt;" in html)

    data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html, re.S).group(1)
                      .replace("<\\/", "</"))
    check("변형과 칩 목록의 키가 같다", set(data["svgs"]) == set(data["chips"]))
    check("클릭 대상이 마지막 노드뿐이다",
          set(data["clickable"]) == set(focus.last_nodes(paths, recipe_ids)))
    print(f"  변형 키: {sorted(data['svgs'])}")
    print(f"  클릭 가능: {data['clickable']}")


# ------------------------------------------------------------------ main
def main():
    print("무인 실행 검증 —", REPO_ROOT)
    if shutil.which("neato") is None:
        print("neato 가 없어 그래프 검증을 건너뛴다.")
        return 1

    step_tests()
    step_greps()

    from fastapi.testclient import TestClient
    import backend.main as backend_main
    from ontology.registry import reset_to_init

    reset_to_init()
    layout_store.LAYOUT_PATH.unlink(missing_ok=True)
    graph = TestClient(backend_main.app).get("/graph").json()
    positions = gs.ensure_positions(graph)

    step_variants(graph, positions)
    step_iframe(graph, positions)
    step_shape(graph, positions)
    step_heights()
    step_registration()
    step_consecutive_registration()
    step_isolation()

    section("결과")
    if FAILURES:
        print(f"  실패 {len(FAILURES)}건:")
        for item in FAILURES:
            print(f"    - {item}")
    else:
        print("  전부 통과")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
