"""온톨로지 전체 그래프를 SVG 파일 하나로 뽑는다.

    python3 dev/tools/export_graph.py
    python3 dev/tools/export_graph.py --out /tmp/ontology.svg
    python3 dev/tools/export_graph.py --quiet

발표에서 지도를 확대 · 축소하며 보여주려면 화면 밖에서도 열리는 파일 한 장이
있어야 한다. 화면은 Streamlit 이 iframe 으로 감싸 띄우므로 그 안의 것을 그대로
꺼낼 수 없다.

**화면과 같은 함수를 부른다.** app/ui/graph_svg/build.top_svg 다. 여기서 DOT 을
다시 짜면 색 · 굵기 · 접기 규칙이 두 곳으로 갈리고, 그러면 발표 자료와 화면이
조용히 어긋난다. 이 파일이 정하는 것은 "어디에 쓸 것인가" 뿐이다.

**좌표를 새로 잡지 않는다.** layout_store.resolve 로 layout.json 을 읽기만 한다.
화면이 부르는 ensure_positions 는 좌표가 없는 노드가 있으면 neato 를 돌려 저장까지
하는데, 그러면 이 도구가 작업본 좌표를 바꿔 화면 배치를 움직이게 된다. 좌표가
빠진 노드가 있으면 그리지 않고 멈춘다 — 다른 그림을 내는 것보다 안 내는 것이 낫다.

**강조를 넣지 않는다.** mark 는 빈 dict 다. 등록 · 발화 장면은 화면에서 보여준다.

**iframe 이 얹는 것(app/ui/components/zoom.py 의 줌 스크립트)은 안 넣는다.**
그것은 Streamlit 패널 안에서만 뜻이 있는 것이고, 파일로 열 때는 브라우저의
확대가 그 일을 한다. 크기 속성이 빠진 SVG(fit_svg)라 창을 꽉 채우고, 글씨는
SVG 텍스트로 남아 확대해도 안 깨진다.

**자체 검사를 함께 둔다.** 「계기판이 조용히 죽는다」를 네 번 겪었다. 파일이
생겼다는 것만으로는 아무것도 확인되지 않는다 — 크기 0 인 파일도, 글씨가 이미지로
바뀐 파일도, 노드가 절반만 담긴 파일도 다 "만들어진" 것이다. 그래서 낸 파일을
다시 읽어 일곱 가지를 세고, 하나라도 어긋나면 1 로 끝낸다. 서버도 LLM 도 안 쓴다.

**테스트를 두지 않는다.** dev/tools 는 재는 도구이고 배포에 안 들어간다.
check_wiring.py · check_inputs.py 와 같은 성격이라 그 파일들의 짜임새를 따른다 —
파일 하나에 담고 저장소의 다른 곳을 건드리지 않는다. app/ui 도 온톨로지도
읽기만 한다.
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.api.services.streamlit import screen_service  # noqa: E402
from app.ui.graph_svg import build, layout_store  # noqa: E402

DEFAULT_OUT = Path("/tmp/ontology.svg")

# ── 검사가 세는 것 ───────────────────────────────────────────────────
# 눈으로 확인해야 하는 네 가지("파일이 있다 · 화면과 같다 · 확대해도 안 깨진다 ·
# 노드 수가 맞다")를 파일만 읽고 셀 수 있는 것으로 바꿔 적은 것이다.
_SVG_OPEN_TAG = re.compile(r"<svg\b[^>]*>", re.S)
_SIZE_ATTR = re.compile(r'\s(?:width|height)="')
_NODE_GROUP = re.compile(r'<g id="node\d+" class="node">')
_EDGE_GROUP = re.compile(r'<g id="edge\d+" class="edge">')
_TEXT_TAG = re.compile(r"<text\b")
_RASTER = re.compile(r"<image\b|xlink:href=\"data:image", re.I)
_SCRIPT = re.compile(r"<script\b|<iframe\b|\son(?:load|click|wheel)=", re.I)


def render() -> tuple[str, dict, dict]:
    """전체 그래프 SVG 와 그것을 잰 도메인 값.

    출력  (svg, nodes, dotted)
    규칙  좌표가 빠진 노드가 있으면 SystemExit. 새로 배치하지 않음
    """
    nodes, solid, dotted = screen_service.domain_graph()
    positions, missing = layout_store.resolve(nodes)

    if missing:
        raise SystemExit(
            "좌표가 없는 노드가 있어 멈춘다 (새로 배치하지 않는다):\n"
            f"  {' '.join(missing)}\n"
            f"  {layout_store.LAYOUT_PATH} 를 먼저 화면에서 만든다."
        )

    # 강조 없는 전체 그림 한 장. 화면 상단 패널이 부르는 것과 같은 함수다.
    return build.top_svg(nodes, solid, dotted, positions, {}), nodes, dotted


def checks(out: Path, svg: str, nodes: dict, dotted: dict) -> list[tuple[bool, str]]:
    """낸 파일을 다시 읽어 센다.

    입력  낸 경로 · 만든 SVG 문자열 · 노드 · 점선
    출력  (통과 여부, 무엇을 봤는가) 목록
    규칙  만든 문자열이 아니라 **파일에서 읽은 것**을 센다. 인코딩이나 쓰기가
          중간에 깨지는 자리가 검사 밖에 남으면 안 된다
    """
    try:
        size = out.stat().st_size
        body = out.read_text(encoding="utf-8")
    except OSError as exc:
        return [(False, f"파일을 다시 못 읽었다: {exc}")]

    tag = _SVG_OPEN_TAG.search(body)
    open_tag = tag.group(0) if tag else ""

    drawn_nodes = len(_NODE_GROUP.findall(body))
    drawn_edges = len(_EDGE_GROUP.findall(body))
    texts = len(_TEXT_TAG.findall(body))

    return [
        (size > 0, f"파일이 있고 크기가 0 이 아니다 ({size:,} bytes)"),
        (len(body) == len(svg), "쓴 것과 읽은 것이 같다"),
        (bool(open_tag) and "viewBox" in open_tag, "루트가 <svg> 이고 viewBox 가 있다"),
        (
            not _SIZE_ATTR.search(open_tag),
            "width / height 가 없다 — 화면과 같은 fit_svg 결과이고 창을 꽉 채운다",
        ),
        (
            texts > 0 and not _RASTER.search(body),
            f"글씨가 SVG 텍스트다 (<text> {texts}개 · 래스터 이미지 0개)",
        ),
        (
            not _SCRIPT.search(body),
            "스크립트 · iframe 이 안 섞였다 — 파일 하나로 열어도 그대로 보인다",
        ),
        (
            drawn_nodes == len(nodes),
            f"노드 수가 온톨로지와 같다 (SVG {drawn_nodes} · 온톨로지 {len(nodes)})",
        ),
        (
            drawn_edges == len(dotted),
            f"엣지 수가 점선과 같다 (SVG {drawn_edges} · 점선 {len(dotted)})"
            "  — 상단은 점선만 그린다",
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="온톨로지 전체 그래프를 SVG 파일 하나로 뽑는다."
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help=f"낼 자리 (기본 {DEFAULT_OUT})"
    )
    parser.add_argument("--quiet", action="store_true", help="검사 목록 없이 합계만")
    args = parser.parse_args()

    svg, nodes, dotted = render()

    out = args.out.expanduser().resolve()
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(svg, encoding="utf-8")
    except OSError as exc:
        print(f"못 썼다: {exc}", file=sys.stderr)
        return 1

    found = checks(out, svg, nodes, dotted)
    failed = [note for ok, note in found if not ok]

    if not args.quiet:
        print()
        for ok, note in found:
            print(f"  {'통과' if ok else '실패'}  {note}")

    print()
    print(f"  {out}")
    print(
        f"  노드 {len(nodes)}개 · 점선 {len(dotted)}개 · 실선은 상단에 안 그린다"
        f" · 검사 {len(found) - len(failed)}/{len(found)}"
    )

    if failed:
        print()
        print("  검사가 걸렸다. 파일을 발표에 쓰지 않는다:", file=sys.stderr)
        for note in failed:
            print(f"    {note}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
