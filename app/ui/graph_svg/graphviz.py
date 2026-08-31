"""Graphviz 를 실제로 돌리고, 나온 SVG 를 다듬는다.

SVG 는 서버에서 네이티브 dot 으로 만든다. st.graphviz_chart 는 DOT 을 브라우저로
보내 WASM Graphviz 가 그리는데, 그쪽은 네이티브 dot 이 즉시 끝내는 그래프에서도
레이아웃을 끝내지 못하고 조용히 멈추는 경우가 있다. 완성해서 보내면 브라우저는
표시만 하므로 그 문제가 생기지 않는다.

subprocess 를 부르는 유일한 곳이다. 그래서 이 모듈은 서버에 있어야 한다 —
브라우저 앞단이 프로세스를 띄우고 있을 이유가 없다.
"""

import re
import shutil
import subprocess

from app.ui.graph_svg.dot import FONT  # noqa: F401 — 폰트 규칙을 한곳에서 본다


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


def render_svg(dot: str, engine: str = "dot", *, no_layout: bool = False) -> str:
    """DOT 을 SVG 문자열로 변환.

    입력  dot        DOT 문자열
          engine     기본값 dot. 기존 호출부가 전부 인자 하나로 부름
          no_layout  -n 을 붙임. 모든 노드에 pos 가 있을 때 배치를 다시
                     계산하지 않고 준 좌표를 그대로 씀. 하이라이트가 어떻게
                     바뀌어도 좌표가 같다는 것이 이것으로 구조적으로 보장됨
    출력  SVG 문자열
    규칙  GraphvizNotFound  실행 파일이 없음
          GraphvizFailed    DOT 을 거부했음(문법 오류 등)
    """
    args = ["-Tsvg"] + (["-n"] if no_layout else [])
    return _run_graphviz(dot, engine, args)


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


# <svg ...> 여는 태그 하나. 속성 순서는 Graphviz 가 정한다.
_SVG_OPEN_TAG = re.compile(r"<svg\b[^>]*>", re.S)
_SVG_SIZE_ATTR = re.compile(r'\s(?:width|height)="[^"]*"')
_SVG_PRESERVE_ATTR = re.compile(r'\spreserveAspectRatio="[^"]*"')


def fit_svg(svg: str) -> str:
    """SVG 가 담긴 상자를 꽉 채우도록 크기 속성을 정리.

    입력  SVG 문자열
    출력  width / height 를 뺀 SVG. viewBox 가 없으면 그대로
    규칙  Graphviz 는 <svg width="591pt" height="336pt" viewBox="..."> 를 냄
          두 속성을 빼고 viewBox 만 남기면 CSS 가 크기를 온전히 정함
          preserveAspectRatio 로 비율은 유지. 찌그러지면 안 읽힘
    제약  width / height 를 남기지 않는다.
          박혀 있으면 고정 높이 패널 안에서 위아래 여백이 뜨거나 잘림
          viewBox 를 지우지 않는다.
          크기 정보가 그것뿐이라 지우면 아무것도 안 보이게 됨
    """
    match = _SVG_OPEN_TAG.search(svg)
    if not match or "viewBox" not in match.group(0):
        return svg

    tag = _SVG_SIZE_ATTR.sub("", match.group(0))
    tag = _SVG_PRESERVE_ATTR.sub("", tag)
    tag = tag[:-1].rstrip() + ' preserveAspectRatio="xMidYMid meet">'

    return svg[: match.start()] + tag + svg[match.end() :]


# 노드 하나의 <g> 블록. 안에 중첩 <g> 가 없음을 실측으로 확인했으므로
# 비탐욕 매칭이 안전하다.
_SVG_NODE_GROUP = re.compile(r'<g id="node\d+" class="node">.*?</g>\n?', re.S)
_SVG_GRAPH_CLOSE = re.compile(r"</g>\s*</svg>\s*$", re.S)


def stack_nodes_on_top(svg: str) -> str:
    """노드를 엣지 뒤로 옮겨 선이 노드를 가리지 않게 함.

    입력  SVG 문자열
    출력  노드 <g> 블록이 전부 맨 뒤로 간 SVG
    규칙  SVG 는 문서에 나온 순서대로 그리므로 뒤에 오는 것이 위에 얹힘
          Graphviz 는 노드와 엣지를 섞어서 냄(실측 : 마지막 노드 뒤에 엣지 9개)
          build_dot 을 건드리지 않는 후처리라 기존 테스트가 안전함
          좌표는 손대지 않으므로 배치도 그대로임
    """
    groups = _SVG_NODE_GROUP.findall(svg)
    if not groups:
        return svg

    body = _SVG_NODE_GROUP.sub("", svg)

    # 그래프 그룹을 닫기 직전에 다시 붙인다.
    match = _SVG_GRAPH_CLOSE.search(body)
    if not match:
        return svg

    return body[: match.start()] + "".join(groups) + body[match.start() :]
