"""/render 응답을 만드는 곳. vis-network 가 받을 노드 · 엣지 모형을 조립한다.

**그림을 만들지 않는다.** 화면 그래프는 `app/ui/components/network.py` 가
라이브러리로 그리고, 여기가 하는 일은 어느 엣지를 강조하고 어느 것을 물리고
무엇이 새로 생겼는지를 후보 조합마다 미리 계산해 넘기는 것이다.

**파이썬이 변형을 다 만들고 JS 는 고르기만 한다.** 규칙이 서버와 JS 두 곳으로
갈라지면 화면이 서버와 다른 말을 하게 된다.

★ **2026-09-06 에 SVG 를 통째로 걷었다.** 그 전에는 변형마다 Graphviz 로 SVG 를
한 장씩 만들어 함께 실어 보냈다(top_svg · variant_svgs). 화면이 vis-network 로
바뀐 뒤로 그것을 읽는 데가 정지 그림 내보내기 하나뿐이었고, 그 내보내기
(dev/tools/export_graph.py)도 쓰지 않기로 정해 함께 갔다.
**Graphviz 는 좌표 계산에만 남는다** — layout_store 가 그 유일한 자리다.

그래서 캐시도 함께 갔다. 캐시는 변형마다 Graphviz 를 돌리는 값을 아끼려던
것이고, 지금 여기는 파이썬 사전 몇 벌을 만들 뿐이다.
"""

from app.ui.graph import focus
from app.ui.graph.dot import wrap_node_labels


def mark_from_registration(result: dict | None) -> dict | None:
    """POST /nodes 응답에서 강조할 것만 뽑음.

    입력  /nodes 응답, 또는 이미 줄어든 {nodes, solid, dotted}
    출력  {nodes, solid, dotted}. 등록에 실패했거나 초기화면 None
    규칙  new_solid_edges / new_dotted_edges 는 등록 전후의 차집합
          이미 줄어든 형태면 그대로 돌려줌. UI 가 응답을 통째로 넘겨도,
          서버가 두 번 줄여도 같은 값이 나옴
    제약  「등록 장면인가」를 여기서 판정하지 않는다.
          2026-09-06 까지는 accepted 키의 유무가 그 표시였음 — 값이 비어도
          키는 남겨야 한다는 규칙이 딸려 있었고, 그 규칙을 모르는 사람이
          빈 값을 지우면 등록 장면이 조용히 해석 장면이 됐음.
          지금은 부르는 쪽이 mode == "register" 를 그대로 넘김
    """
    if not result or "error" in result or result.get("reset"):
        return None

    if "new_solid_edges" not in result and "solid" in result:
        return {
            "nodes": list(result.get("nodes") or []),
            "solid": [tuple(edge) for edge in result.get("solid") or []],
            "dotted": [tuple(pair) for pair in result.get("dotted") or []],
        }

    node_id = result.get("node_id")
    return {
        "nodes": [node_id] if node_id else [],
        "solid": [(e["from"], e["to"]) for e in result.get("new_solid_edges") or []],
        "dotted": [(e["a"], e["b"]) for e in result.get("new_dotted_edges") or []],
    }


def network_payload(
    *,
    nodes: dict,
    solid: list,
    dotted: dict,
    positions: dict,
    paths: dict,
    recipe_ids: list[str],
    mark: dict,
    registering: bool,
) -> dict:
    """interactive graph library 가 받는 노드 · 엣지 모형.

    입력  노드 · 실선 · 점선 · 좌표 · 경로 · recipe id 목록 · 강조 원본 ·
          등록 장면인가
    출력  positions · nodes · dotted · solid · variants · picks · registering
    규칙  등록 장면과 해석 장면이 색을 나눠 씀. 등록은 주황(고른 것 · 빠진 것),
          해석은 teal 임. **한 화면에 섞이면 안 됨** — 그래서 변형마다
          한쪽만 채우고 나머지는 빈 목록으로 나감
          ★ 변형 키가 recipe id 임. 옛 판은 「마지막 노드」로 갈랐는데
          후보가 마지막 노드를 함께 쓰면(인구 둘이 그렇다) 좁힌 것이 전체와
          똑같아져 고를 뜻이 없어짐. 후보 하나하나를 키로 두면 그 일이 없음
          picks 가 「이 노드는 어느 후보에만 있나」를 말함. 여럿에 걸친
          노드는 안 담음 — 눌러도 후보를 좁힐 수 없는 자리임
          final 이 후보마다의 마지막 엣지임. 화살촉이 거기에만 붙음
          순번을 안 냄. 「쉰셋째」에 이미 xlabel 을 뺐고 그 자리를 흐르는
          표시가 맡음. 그래프 위에 숫자를 다시 올리지 않음
    제약  색을 여기서 정하지 않는다.
          팔레트의 주인은 dot.COLORS 이고 화면은 그것을 /screen 으로 이미 받음.
          여기서 색을 실으면 출처가 둘이 됨
          좌표에 배율을 곱하지 않는다.
          for_drawing 은 Graphviz 로 상자를 잴 때의 일이고, library 는 제
          화면 좌표계로 다시 맞춤
    """
    wrapped = wrap_node_labels(nodes)
    all_ids = list(recipe_ids)
    새_노드 = set(mark.get("nodes") or ())
    새_점선 = {tuple(edge) for edge in (mark.get("dotted") or ())}

    def path_edges(ids):
        """recipe 들이 지나는 엣지를 한 줄로. 중복은 접음."""
        return list(dict.fromkeys(
            edge for path in focus.edges_of(paths, ids) for edge in path
        ))

    def final_edges(ids):
        """후보마다의 마지막 엣지. 화살촉이 거기에만 붙는다.

        중간 방향은 흐르는 표시가 말하므로 엣지마다 화살촉을 되풀이하면
        복잡하기만 하다. 후보들이 마지막 엣지를 함께 쓰면 한 번만 담긴다.
        """
        return list(dict.fromkeys(
            path[-1] for path in focus.edges_of(paths, ids) if path
        ))

    def variant(ids):
        나머지 = [recipe_id for recipe_id in all_ids if recipe_id not in set(ids)]
        return {
            "highlight": [] if registering else [list(e) for e in path_edges(ids)],
            "nodes": [] if registering else sorted(focus.nodes_of(paths, ids)),
            "final": [] if registering else [list(e) for e in final_edges(ids)],
            "mark": [list(e) for e in path_edges(ids)] if registering else [],
            "dim": [list(e) for e in path_edges(나머지)] if registering else [],
        }

    def picks():
        """노드 -> 그 노드를 가진 유일한 후보. 여럿에 걸친 노드는 안 담는다.

        누르면 후보가 하나로 좁혀지는 자리만 담긴다. 여럿이 함께 쓰는 노드는
        어느 후보인지 가릴 근거가 없어 눌러도 아무 일이 없어야 한다.
        """
        가진_후보 = {}
        for recipe_id in all_ids:
            for node_id in focus.nodes_of(paths, [recipe_id]):
                가진_후보.setdefault(node_id, []).append(recipe_id)
        return {
            node_id: ids[0]
            for node_id, ids in 가진_후보.items()
            if len(ids) == 1
        }

    return {
        "positions": {node_id: list(xy) for node_id, xy in positions.items()},
        "nodes": {
            node_id: {
                "label": node["name"],
                "title": nodes[node_id]["description"],
                # 대상(group) 노드를 화면이 가르는 유일한 근거다. 노드에 종류가
                # 적혀 있지 않고 about 의 대상으로 등장하는지가 그것을 말하는데,
                # 그 판정은 온톨로지가 이미 했고 여기서 다시 하지 않는다.
                "kind": node.get("kind", ""),
                "new": node_id in 새_노드,
            }
            for node_id, node in wrapped.items()
        },
        "dotted": [
            {"edge": [a, b], "new": (a, b) in 새_점선}
            for (a, b) in dotted
        ],
        "solid": [list(edge) for edge in solid],
        # 빈 키가 후보 전부(union)이고, 그 밖은 후보 하나씩이다.
        "variants": dict(
            [("", variant(all_ids))]
            + [(recipe_id, variant([recipe_id])) for recipe_id in all_ids]
        ),
        "picks": {} if registering else picks(),
        "registering": registering,
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
    registering: bool,
) -> dict:
    """/render 응답 한 벌.

    출력  version  온톨로지 내용 해시. 화면이 「같은 해석인가」를 세는 재료
          chips    후보마다의 이름 사슬. 목록에 그대로 실림
          network  vis-network 가 받는 노드 · 엣지 모형
    규칙  chips 차례가 network["variants"] 의 빈 키를 뺀 차례와 같음.
          어긋나면 목록에서 고른 줄과 그래프가 다른 후보를 가리킴
    이력  예전에는 top · variants(SVG 문자열) · focus 세 칸이 더 있었음.
          2026-09-06 에 SVG 를 걷으면서 함께 지웠음 — focus 가 말하던
          「어느 후보가 어느 노드로 끝나나」는 network 의 variants · picks 가
          이미 갖고 있고, 화면은 그쪽을 읽음
    """
    marks = mark or {}
    return {
        "version": version,
        # 목록은 늘 후보 전부다. 좁혀도 줄이 사라지지 않고 흐려질 뿐이라
        # 변형마다 따로 만들지 않는다.
        "chips": focus.chips_of(paths, recipe_ids),
        "network": network_payload(
            nodes=nodes,
            solid=solid,
            dotted=dotted,
            positions=positions,
            paths=paths,
            recipe_ids=recipe_ids,
            mark=marks,
            registering=registering,
        ),
    }
