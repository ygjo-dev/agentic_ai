"""대상 : ontology/shortlist.py — 축 셋으로 recipe 후보를 좁힌다

**LLM 을 부르지 않는다.** 발화 해석 LLM 은 무엇을 찾는지(reason)는 맞게 쓰면서
48문장 사이에서 하나를 못 고른다 — menu 문장의 앞 30자가 23개나 같기 때문이다.
그래서 축 셋은 LLM 에게 닫힌 목록의 객관식으로 받고, 그 값으로 후보를 뽑는
일은 코드가 한다. 여기 있는 것은 그 뽑는 일이고 전부 순수 함수다.

  given  경로가 무엇에서 시작하는가
  want   무엇을 돌려받는가
  about  무엇에 관한 것인가

축은 저마다 null 일 수 있다. 발화에 근거가 없으면 그 축으로는 안 거른다.
"""

import paths
from ontology import store
from ontology.graph import (
    group_ids,
    outputs_of,
    recipe_facets,
    recipe_nodes,
    start_ids,
)
from ontology.shortlist import axis_choices, candidates


def recipe_ids() -> list[str]:
    return sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))


def test_the_choices_come_from_the_ontology_not_from_code():
    """선택지를 코드에 박지 않음. 노드를 등록하면 함께 늘어야 함.

    박아두면 등록한 노드로 만들어진 recipe 를 LLM 이 영영 못 고름.
    menu 는 늘어나는데 축은 그대로라 그 recipe 가 조회에서 계속 빠짐.

    id 와 이름과 설명을 함께 보여줌. id 만 보여주면 LLM 이 뜻을 모르고,
    이름만 보여주면 무엇을 적어야 할지 모름. 적어야 하는 것은 id 다.
    """
    choices = axis_choices()
    nodes = store.nodes()

    assert choices["given"] == start_ids()
    assert choices["about"] == group_ids()

    # want 는 누군가 "이것을 내놓는다" 고 선언한 타입들이다.
    declared = {out for node_id in nodes for out in outputs_of(node_id)}
    assert set(choices["want"]) == declared

    for axis in ("given", "want", "about"):
        assert choices[axis], axis
        for node_id in choices[axis]:
            assert node_id in nodes, node_id
            assert node_id in choices["described"][axis]
            assert nodes[node_id]["name"] in choices["described"][axis]
            assert nodes[node_id]["description"] in choices["described"][axis]


def test_no_axis_keeps_everything():
    """셋 다 null 이면 아무것도 안 거름.

    발화에 근거가 없을 때 LLM 이 추측해서 채우는 것보다 낫다. 근거 없는 축으로
    거르면 맞는 recipe 가 조용히 사라지고, 사라진 뒤에는 왜 없는지 알 수 없다.
    """
    assert candidates() == recipe_ids()
    assert candidates(None, None, None) == recipe_ids()


def test_one_axis_alone_narrows_the_list():
    """축 하나만 있어도 걸러짐. 셋을 다 채워야 하는 것이 아님.

    "국회의원 선거구 찾아줘" 에는 무엇을 돌려받을지가 없다. 그래도 given 과
    about 둘만으로 20개가 4개로 줄어든다.
    """
    everything = recipe_ids()

    by_given = candidates(given="spoken_keyword")
    by_want = candidates(want="statistics")
    by_about = candidates(about="group_ev")

    for narrowed in (by_given, by_want, by_about):
        assert narrowed
        assert len(narrowed) < len(everything)
        assert set(narrowed) <= set(everything)
        assert narrowed == sorted(narrowed), "파일 이름 순이 아니다"

    # given 은 경로의 첫 노드다.
    assert all(recipe_nodes(rid)[0] == "spoken_keyword" for rid in by_given)
    # want 는 마지막 노드가 내놓는 것이다.
    assert all("statistics" in outputs_of(recipe_nodes(rid)[-1]) for rid in by_want)


def test_three_axes_together_narrow_to_what_the_utterance_asked():
    """셋을 다 주면 발화 하나가 가리키는 자리까지 좁혀짐.

    "오송역 근처 충전소 찾아줘" 는 말한 장소에서 시작해 목록을 돌려받는
    전기차 충전 이야기다. 전체가 그 하나로 준다.

    **둘로 줄던 자리였다.** 충전소 검색과 충전기 조회가 축 셋이 똑같아
    조회로는 못 갈렸고, "옛 호출 호환용으로 보여줘" 라고 말하는 사람이 없어
    발화로도 못 갈렸다. 2026-08-26 에 충전기 조회 노드를 뺐다 — 저쪽이
    폐기 예정이라 도구 설명에 적어 둔 `ev.searchChargers` 다. 축이 좁히지
    못한 것이 아니라 온톨로지가 같은 것을 둘 두고 있었다.

    "오송역 위치 보여줘" 도 하나로 정해진다. 좌표를 돌려받는 recipe 는
    하나뿐이라 앞토막이 같은 나머지가 전부 빠진다.

    번호를 2026-08-28 에 옮겼다 — recipe_030 -> recipe_045. 같은 사슬이고,
    화면 문맥 시작 노드 둘이 붙으면서 그 뒤 번호가 밀렸다.
    """
    assert candidates("spoken_place", "item_list", "group_ev") == ["recipe_045"]
    assert candidates("spoken_place", "point", None) == ["recipe_001"]


def test_a_general_recipe_survives_only_when_nothing_matches_the_subject():
    """about 은 두 단으로 거름. 대상이 걸린 것이 있으면 범용은 빠짐.

    범용 recipe(about 이 하나도 안 붙은 것)를 늘 통과시키면 "국회의원 선거구"
    에 웹 검색과 VWorld 경계가 계속 따라온다. 그렇다고 늘 빼면 대상 없는
    발화에서 후보가 0개가 된다.
    """
    # 선거에 걸린 recipe 가 있다. 범용(web_search · VWorld 경계)은 빠진다.
    election = candidates("spoken_keyword", None, "group_election")
    assert election == ["recipe_007", "recipe_008", "recipe_009", "recipe_010"]
    assert "recipe_006" not in election, "웹 검색은 선거에 관한 것이 아니다"

    # 좌표를 돌려받는 recipe 는 범용 하나뿐이다. 선거에 걸린 것이 하나도
    # 없으므로 그 범용이 남는다. 여기서 빼면 후보가 0개가 된다.
    assert candidates("spoken_place", "point", "group_election") == ["recipe_001"]


def test_an_axis_does_not_climb_the_is_a_chain():
    """상위 타입으로 물으면 안 걸림. 실제로 적힌 것과 정확히 맞는 것만 봄.

    말한 식별자는 식별자의 한 종류(is-a)지만, given 을 조상까지 올리면
    상위 타입 하나가 하위 전부를 끌어와 좁히는 뜻이 없어진다.
    """
    assert candidates(given="spoken_identifier")
    assert candidates(given="record_key") == []
    assert candidates(want="place_name") == []


def test_an_unknown_axis_value_is_empty_not_an_error():
    """없는 값을 물어도 예외가 아님. 화면이 죽는 것보다 나음.

    given 과 want 는 빈 목록이 된다. 빈 목록이면 부르는 쪽이 LLM 이 쓴 것을
    그대로 쓴다. 축이 틀렸다는 뜻이라 조회 결과를 믿지 않는 자리다.

    about 만 다르다. 두 단째로 내려가 범용 recipe 가 남는다. 대상이 걸린 것이
    하나도 없는 경우와 같은 자리이고, 실제로는 닫힌 목록이라 없는 대상이
    들어올 수 없다.
    """
    assert candidates(given="없는노드") == []
    assert candidates(want="없는타입") == []

    generic = candidates(about="없는대상")
    assert generic == [rid for rid in recipe_ids() if not recipe_facets(rid)["about"]]
    assert "recipe_001" in generic and "recipe_007" not in generic
