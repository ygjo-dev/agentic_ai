"""Graphviz 를 실제로 돌리고 나온 DOT 에서 배치를 읽는다. **좌표만 낸다.**

★ **2026-09-06 에 그림 만들기를 걷었다.** 그 전에는 여기서 `-Tsvg` 로 SVG 를
완성해 화면에 보냈다(render_svg · fit_svg · stack_nodes_on_top). 화면 그래프가
vis-network 로 바뀐 뒤 그 SVG 를 읽는 데가 없어졌고, 남은 일은 **좌표 계산**
하나다 — `-Tdot` 으로 돌려 pos · width · height 를 뽑는다.

subprocess 를 부르는 유일한 곳이다. 그래서 이 모듈은 서버에 있어야 한다 —
브라우저 앞단이 프로세스를 띄우고 있을 이유가 없다.
"""

import re
import shutil
import subprocess


class GraphvizNotFound(RuntimeError):
    """dot 실행 파일을 찾지 못했다."""


class GraphvizFailed(RuntimeError):
    """dot 이 DOT 을 거부했다. 대개 문법 오류다."""


def _run_graphviz(dot: str, engine: str, args: list[str]) -> str:
    """Graphviz 를 한 번 돌림. 실행 파일 확인과 오류 변환을 한곳에 모음.

    입력  DOT 문자열 · 엔진 이름 · 명령행 인자
    출력  표준 출력
    규칙  GraphvizNotFound  실행 파일이 없음
          GraphvizFailed    DOT 을 거부했거나 30초 안에 못 끝냄
    """
    if shutil.which(engine) is None:
        raise GraphvizNotFound(
            f"Graphviz 의 {engine} 실행 파일을 찾을 수 없다.\n"
            "  설치 : https://graphviz.org/download/\n"
            f"  설치 후 {engine} 이 PATH 에 있어야 한다 ({engine} -V 로 확인)."
        )

    try:
        result = subprocess.run(
            [engine, *args],
            input=dot,
            capture_output=True,
            text=True,
            encoding="utf-8",  # 한글 노드 라벨이 있다.
            timeout=30,
        )
    except OSError as exc:  # 실행 자체가 실패
        raise GraphvizNotFound(f"{engine} 을 실행할 수 없다: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GraphvizFailed(f"{engine} 이 30초 안에 끝나지 않았다.") from exc

    if result.returncode != 0:
        raise GraphvizFailed(
            f"{engine} 이 DOT 을 거부했다 (exit {result.returncode}).\n{result.stderr.strip()}"
        )

    return result.stdout


# 엣지에도 pos(스플라인)가 붙는다. 노드만 골라내려면 엣지 문장을 먼저 지운다.
_EDGE_STATEMENT = re.compile(r'"?[\w]+"?\s*->\s*"?[\w]+"?\s*\[[^\]]*\];')
_NODE_STATEMENT = re.compile(r'"?([A-Za-z_]\w*)"?\s*\[([^\]]*)\]\s*;')
_POS_ATTR = re.compile(r'pos="([-\d.e+]+),([-\d.e+]+)')


def layout_positions(dot: str) -> dict[str, tuple[float, float]]:
    """neato 로 배치를 계산해 노드 좌표를 뽑음.

    입력  DOT 문자열
    출력  {node_id: (x, y)}
    제약  -Tplain 을 쓰지 않는다.
          좌표를 주긴 하지만 단위가 인치라 포인트인 pos 와 72배 어긋남.
          그대로 되돌려 넣으면 배치가 폭발함. -Tdot 을 씀
    """
    out = _run_graphviz(dot, "neato", ["-Tdot"])

    flat = _EDGE_STATEMENT.sub(" ", re.sub(r"\s+", " ", out))

    positions = {}
    for match in _NODE_STATEMENT.finditer(flat):
        pos = _POS_ATTR.search(match.group(2))
        if pos:
            positions[match.group(1)] = (float(pos.group(1)), float(pos.group(2)))
    return positions


_WIDTH_ATTR = re.compile(r'width="?([\d.]+)')
_HEIGHT_ATTR = re.compile(r'height="?([\d.]+)')

# 인치로 나오는 width · height 를 pt 로.
POINTS_PER_INCH = 72


def node_boxes(dot: str) -> dict[str, tuple[float, float, float, float]]:
    """그려질 노드 사각형. {node_id: (중심x, 중심y, 폭, 높이)} 단위 pt.

    입력  좌표가 이미 박힌 DOT. -n 으로 돌리므로 배치를 다시 계산하지 않음
    출력  상자 넷. pos · width · height 가 다 있는 노드만 담음
    규칙  엣지에도 pos(스플라인)가 붙으므로 엣지 문장을 먼저 지움.
          layout_positions 와 같은 자와 같은 정규식임
    제약  그려진 그림에서 재지 않는다.
          style="rounded,filled" 라 노드가 도형 하나로 나오고 거기서 사각형을
          되찾으려면 경로 문자열을 파싱해야 함. DOT 은 수를 그대로 적어 준다
    """
    out = _run_graphviz(dot, "neato", ["-n", "-Tdot"])
    flat = _EDGE_STATEMENT.sub(" ", re.sub(r"\s+", " ", out))

    boxes = {}
    for match in _NODE_STATEMENT.finditer(flat):
        body = match.group(2)
        pos = _POS_ATTR.search(body)
        width = _WIDTH_ATTR.search(body)
        height = _HEIGHT_ATTR.search(body)
        if pos and width and height:
            boxes[match.group(1)] = (
                float(pos.group(1)),
                float(pos.group(2)),
                float(width.group(1)) * POINTS_PER_INCH,
                float(height.group(1)) * POINTS_PER_INCH,
            )
    return boxes
