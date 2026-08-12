"""변형 SVG 조립과 캐시. /render 응답을 만드는 곳.

**모든 변형의 노드 좌표가 같아야 한다.** 좌표를 전부 고정하고 `neato -n` 으로
그리므로 배치를 아예 계산하지 않는다 — 어느 조합을 강조하든 좌표가 같다는 것이
구조적으로 보장된다. 그래서 몇 벌을 만들어도 화면이 안 흔들린다.

SVG 는 크기 속성을 뺀 채로 나간다(fit_svg). 폭·높이가 박혀 있으면 고정 높이
패널 안에서 여백이 뜨거나 잘린다 — viewBox 만 남기면 CSS 가 크기를 온전히 정한다.

JS 가 SVG 를 다시 칠하지 않는다. 그러면 엣지 굵기 · 색 · 순번 규칙이 build_dot 과
JS 두 곳으로 갈라진다. 파이썬이 변형을 다 만들고 JS 는 고르기만 한다.

캐시는 여기 있다. 예전에는 프론트엔드가 st.cache_data 로 들고 있었는데,
그리기가 서버로 왔으니 캐시도 따라온다. 브라우저가 몇이든 한 번만 그린다.
"""

import hashlib
import json
from collections import OrderedDict

from demo.graph_svg import focus
from demo.graph_svg.dot import (
    DOTTED_COLOR_BOTTOM,
    DOTTED_COLOR_TOP,
    DOTTED_PENWIDTH_TOP,
    EDGE_COLOR,
    EDGE_COLOR_TOP,
    GROUP_ATTRS,
    GROUP_ATTRS_TOP,
    NODE_ATTRS,
    NODE_ATTRS_TOP,
    build_dot,
)
from demo.graph_svg.graphviz import fit_svg, render_svg, stack_nodes_on_top

# 서버 캐시. 키가 version 을 포함하므로 온톨로지가 바뀌면 저절로 빗나간다.
# 그래도 상한을 둔다 — 시연이 길어지면 등록 · 발화 조합이 계속 쌓인다.
CACHE_LIMIT = 32
_CACHE: OrderedDict[str, dict] = OrderedDict()


def wrap_label(name: str) -> str:
    """긴 이름을 두 줄로 접는다. 가운데에 가장 가까운 공백에서 자른다.

    가로 폭이 줄면 겹칠 확률이 가장 크게 준다 — 노드 폭이 194 에서 87 로 준다.
    공백에서만 자른다. 공백이 없는 이름은 그대로 둔다.
    한글이 계속 읽혀야 하므로 글자 중간에서 자르지 않는다.
    """
    if " " not in name:
        return name

    middle = len(name) / 2
    cut = min(
        (i for i, char in enumerate(name) if char == " "),
        key=lambda i: abs(i - middle),
    )
    # DOT 문자열 안에서 \n 은 줄바꿈이다. 파이썬 개행이 아니라 두 글자로 넣는다.
    return name[:cut] + "\\n" + name[cut + 1 :]


def wrap_node_labels(nodes: dict) -> dict:
    """노드 이름만 두 줄로 접은 사본. build_dot 은 건드리지 않는다."""
    return {
        node_id: {**node, "name": wrap_label(node.get("name", node_id))}
        for node_id, node in nodes.items()
    }


def chain_edges(chains) -> list[tuple[str, str]]:
    """노드 id 사슬들을 인접 쌍으로. 중복은 접는다.

    /nodes 응답의 accepted.chains · pending[*].chain 이 이 모양이다. 경로 전체를
    칠하려면 "새로 생긴 연결"(new_solid_edges)만으로는 부족하다 — 이미 있던
    연결을 지나는 경로가 대부분이라 그것만 칠하면 길이 끊겨 보인다.
    """
    return list(dict.fromkeys(
        edge for chain in chains or () for edge in zip(chain, chain[1:])
    ))


def mark_from_registration(result: dict | None) -> dict | None:
    """POST /nodes 응답에서 강조할 것만 뽑는다.

    new_solid_edges / new_dotted_edges 는 등록 전후의 차집합이다.
    이미 줄어든 형태({nodes, solid, dotted, accepted, review})가 들어오면 그대로
    돌려준다 — UI 가 응답을 통째로 넘겨도, 서버가 두 번 줄여도 같은 값이 나온다.

    accepted 는 자동 승격된 경로(분홍), review 는 검토 대상(pending) 경로
    (amber)다. 둘 다 하단에 실행 경로로 그린다 — 등록이 무엇을 만들었고 무엇을
    묻고 있는지가 경로로 보여야 한다. pending 은 아직 recipe 가 아니라
    new_solid_edges 에 없고, 승인되면 accepted 로 옮겨가며 색이 바뀐다.
    """
    if not result or "error" in result or result.get("reset"):
        return None

    if "new_solid_edges" not in result and "solid" in result:
        return {
            "nodes": list(result.get("nodes") or []),
            "solid": [tuple(edge) for edge in result.get("solid") or []],
            "dotted": [tuple(pair) for pair in result.get("dotted") or []],
            "accepted": [tuple(edge) for edge in result.get("accepted") or []],
            "review": [tuple(edge) for edge in result.get("review") or []],
        }

    node_id = result.get("node_id")
    return {
        "nodes": [node_id] if node_id else [],
        "solid": [(e["from"], e["to"]) for e in result.get("new_solid_edges") or []],
        "dotted": [(e["a"], e["b"]) for e in result.get("new_dotted_edges") or []],
        "accepted": chain_edges((result.get("accepted") or {}).get("chains")),
        "review": chain_edges(
            entry.get("chain") or [] for entry in result.get("pending") or []
        ),
    }


def mark_key(mark: dict | None) -> str:
    """강조 상태를 캐시 키에 넣을 짧은 문자열.

    강조 여부가 SVG 를 다르게 만든다. 키에 반영하지 않으면 등록 직후 강조가
    안 뜨거나(이전 SVG 재사용) 강조가 계속 남는다.
    """
    if not mark:
        return "plain"

    payload = json.dumps(
        {kind: sorted(map(list, values)) for kind, values in sorted(mark.items())},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def focus_key(recipe_ids, mark: dict | None) -> str:
    """하단 그래프 캐시 키. 후보 집합과 모드를 반영한다.

    후보 순서가 달라도 같은 키가 나오게 정렬해서 넣는다 — 순서만 다른데
    캐시가 헛돌면 같은 그림을 매번 다시 만든다.
    """
    payload = json.dumps(
        {"recipes": sorted(recipe_ids or []), "mark": mark_key(mark)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def cache_key(version: str, layout: str, mode: str, recipe_ids, mark) -> str:
    """캐시 한 칸의 이름. 같은 화면이면 같아야 하고 다르면 달라야 한다."""
    return f"{version}:{layout}:{mode}:{focus_key(recipe_ids, mark)}"


def top_svg(nodes: dict, solid: dict, dotted: dict, positions: dict, mark: dict) -> str:
    """상단 그래프. 온톨로지의 **관계 지도**다 — 점선만 그린다.

    상단은 "무엇이 무엇과 관련되는가", 하단은 "무엇 다음에 무엇이 오는가".
    둘 다 실선과 점선을 그리면 같은 그림이 두 번 뜨고, 그러면 두 패널이 각각
    무엇을 말하는지 구분되지 않는다. 실선(실행 순서)은 하단에 넘긴다.

    solid 는 계속 받는다 — 값은 그리지 않지만 노드 목록과 캔버스 계산에
    쓰이던 인자이고, 인자를 지우면 부르는 쪽이 두 갈래로 갈린다.

    발화 해석은 상단을 강조하지 않는다 — 결과는 하단이 보여준다. 노드를
    등록했을 때만 **새 노드 테두리와 새 점선**을 표시한다. 새 실선(mark_edges)과
    검토 표시(review_edges)는 실선 위에 얹는 것이라 여기서는 갈 곳이 없다 —
    둘 다 하단이 맡는다.
    """
    return fit_svg(stack_nodes_on_top(
        render_svg(
            build_dot(
                wrap_node_labels(nodes),
                solid,
                dotted,
                positions=positions,
                spring=True,
                # 라벨은 어느 경우에도 안 그린다. 발표자가 말로 설명한다.
                dotted_labels=False,
                draw_solid=False,
                dotted_penwidth=DOTTED_PENWIDTH_TOP,
                node_attrs=NODE_ATTRS_TOP,
                group_attrs=GROUP_ATTRS_TOP,
                edge_color=EDGE_COLOR_TOP,
                dotted_color=DOTTED_COLOR_TOP,
                mark_nodes=mark.get("nodes") or (),
                mark_dotted=mark.get("dotted") or (),
            ),
            "neato",
            no_layout=True,
        )
    ))


def variant_svgs(
    nodes: dict,
    solid: dict,
    dotted: dict,
    positions: dict,
    paths: dict,
    recipe_ids: list[str],
    mark: dict,
) -> dict[str, str]:
    """하단 실행 경로 그래프. 조합별로 미리 만들어 둔다.

    {"": 후보 전부 강조, "<마지막노드 id>": 그것으로 끝나는 recipe 만}

    배경 실선은 그대로 둔다 — 강조 안 된 경로도 보여야 지도 역할을 한다.
    그 위에 세 가지가 화살표로 얹힌다.

        발화 해석 결과   HIGHLIGHT (teal)   순번 있음
        등록 자동 승격   NEW      (분홍)
        등록 승인 대기   REVIEW   (amber)

    자동 승격은 mark_edges 로 넘긴다 — 색 우선순위가 mark > highlight > review 라
    등록 장면에서 teal 을 덮는다. 등록 결과는 "고른 경로" 가 아니라 "새로 생긴
    것" 이므로 그 편이 맞다.
    """
    wrapped = wrap_node_labels(nodes)

    def svg_for(ids):
        return fit_svg(stack_nodes_on_top(
            render_svg(
                build_dot(
                    wrapped,
                    solid,
                    dotted,
                    # 경로가 정확히 하나면 build_dot 이 순번을 붙인다. 규칙은 한곳뿐이다.
                    highlight_paths=focus.edges_of(paths, ids),
                    highlight_nodes=focus.nodes_of(paths, ids),
                    positions=positions,
                    spring=True,
                    dotted_labels=False,
                    node_attrs=NODE_ATTRS,
                    group_attrs=GROUP_ATTRS,
                    edge_color=EDGE_COLOR,
                    dotted_color=DOTTED_COLOR_BOTTOM,
                    mark_nodes=mark.get("nodes") or (),
                    mark_edges=[
                        *(mark.get("solid") or ()),
                        *(mark.get("accepted") or ()),
                    ],
                    mark_dotted=mark.get("dotted") or (),
                    review_edges=mark.get("review") or (),
                ),
                "neato",
                no_layout=True,
            )
        ))

    return {
        key: svg_for(ids)
        for key, ids in focus.focus_variants(paths, recipe_ids).items()
    }


def render_payload(
    *,
    nodes: dict,
    solid: dict,
    dotted: dict,
    positions: dict,
    paths: dict,
    recipe_ids: list[str],
    mark: dict | None,
    version: str,
    layout: str,
    mode: str,
) -> dict:
    """/render 응답 한 벌. 같은 화면을 두 번 그리지 않는다.

    캐시 적중이면 Graphviz 를 한 번도 부르지 않는다 — 시연에서 같은 발화를
    다시 눌렀을 때 눈에 띄게 빠른 이유다.
    """
    key = cache_key(version, layout, mode, recipe_ids, mark)
    hit = _CACHE.get(key)
    if hit is not None:
        _CACHE.move_to_end(key)
        return hit

    marks = mark or {}
    payload = {
        "version": version,
        "top": top_svg(nodes, solid, dotted, positions, marks),
        "variants": variant_svgs(
            nodes, solid, dotted, positions, paths, recipe_ids, marks
        ),
        "focus": {
            "last_nodes": focus.last_nodes(paths, recipe_ids),
            "recipes_by_last_node": focus.recipes_by_last_node(paths, recipe_ids),
        },
        "chips": focus.chips_by_variant(paths, recipe_ids),
    }

    _CACHE[key] = payload
    while len(_CACHE) > CACHE_LIMIT:
        _CACHE.popitem(last=False)
    return payload


def clear_cache() -> None:
    """테스트와 온톨로지 초기화용. 평소에는 키가 version 을 물고 있어 필요 없다."""
    _CACHE.clear()
