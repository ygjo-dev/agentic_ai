"""축 셋으로 recipe 후보를 좁힌다. **LLM 을 부르지 않는다.**

발화 해석 LLM 은 무엇을 찾는지(reason)는 맞게 쓰면서 48문장 사이에서 하나를
못 고른다. menu 문장의 앞 30자가 23개나 같기 때문이다. 그래서 LLM 에게는
축 셋을 닫힌 목록의 객관식으로 받고, 그 값으로 후보를 뽑는 일은 여기가 한다.

  given  경로가 무엇에서 시작하는가   graph.start_ids()
  want   무엇을 돌려받는가            hasOutput 의 대상
  about  무엇에 관한 것인가           graph.group_ids()

선택지를 코드에 박지 않는다. 노드를 등록하면 선택지도 함께 늘어야 한다.

recipe 파일을 부를 때마다 다시 읽는다. 온톨로지를 요청마다 다시 읽는 것이
지금 동작이고 시연의 등록 장면이 그것에 기댄다.
"""

import paths
from ontology import graph, store


def axis_choices() -> dict:
    """LLM 이 고를 수 있는 축 값.

    출력  given · want · about  축마다 노드 id 목록
          described             축마다 id 와 이름, 설명을 붙인 여러 줄 문자열
    규칙  given  경로가 시작할 수 있는 데이터 노드
          want   hasOutput 의 대상으로 등장하는 타입 노드
          about  about 의 대상으로 등장하는 그룹 노드
          id 만 보여주면 LLM 이 뜻을 모르고, 이름만 보여주면 무엇을 적어야
          할지 모름. 적어야 하는 것은 id. registry._describe_groups 와 같은 형태임
    제약  선택지를 코드에 박지 않는다.
          노드를 등록하면 선택지도 함께 늘어야 함
    """
    nodes = store.nodes()

    given = graph.start_ids()
    want = list(
        dict.fromkeys(
            type_id for node_id in nodes for type_id in graph.outputs_of(node_id)
        )
    )
    about = graph.group_ids()

    return {
        "given": given,
        "want": want,
        "about": about,
        "described": {
            "given": _describe(nodes, given),
            "want": _describe(nodes, want),
            "about": _describe(nodes, about),
        },
    }


def candidates(
    given: str | None = None,
    want: str | None = None,
    about: str | None = None,
) -> list[str]:
    """축 셋으로 뽑은 recipe 후보.

    입력  축 셋. 각각 None 이면 그 축으로 안 거름
    출력  recipe id 목록. 파일 이름 순. 셋 다 None 이면 전체
    규칙  given  recipe 의 첫 노드가 그것인 것만
          want   마지막 노드가 내놓는 것에 그것이 있는 것만
          about  그 대상이 걸린 recipe 가 하나라도 있으면 그것들만.
                 하나도 없으면 about 이 비어 있는 범용 recipe 만
          온톨로지에 없는 given · want 를 주면 빈 목록. 없는 about 은
          두 단째로 내려가 범용 recipe 가 남음
    제약  is-a 를 타고 올라가지 않는다.
          want 는 마지막 노드가 실제로 내놓는 타입과 정확히 맞는 것만 봄.
          조상까지 올리면 상위 타입 하나가 하위 전부를 끌어와 좁히는 뜻이 없어짐
    """
    facets = {
        recipe_path.stem: graph.recipe_facets(recipe_path.stem)
        for recipe_path in sorted(paths.RECIPES_DIR.glob("recipe_*.yaml"))
    }

    kept = [
        recipe_id
        for recipe_id, facet in facets.items()
        if (given is None or facet["given"] == given)
        and (want is None or want in facet["want"])
    ]

    if about is None:
        return kept

    # 두 단으로 거른다. 늘 범용 recipe 를 통과시키면 "국회의원 선거구" 에
    # 웹 검색과 VWorld 경계가 계속 따라오고, 늘 빼면 대상 없는 발화에서
    # 후보가 0개가 된다.
    matched = [recipe_id for recipe_id in kept if about in facets[recipe_id]["about"]]
    if matched:
        return matched
    return [recipe_id for recipe_id in kept if not facets[recipe_id]["about"]]


def _describe(nodes: dict, choices: list[str]) -> str:
    """고를 수 있는 값 목록. id 와 이름, 설명을 함께 담음."""
    return "\n".join(
        f"- {node_id}  ({nodes[node_id]['name']} — {nodes[node_id]['description']})"
        for node_id in choices
    )
