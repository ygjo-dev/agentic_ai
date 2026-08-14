"""온톨로지 그래프 계산.

순수 함수만 둔다. Streamlit 도 DOT 문법도 모른다 — 그리는 방법은
demo/graph_svg/ 가 안다.

온톨로지는 store 에게 묻는다. 이 파일은 ontology.yaml 을 직접 열지 않는다 —
저장소가 그래프DB 로 바뀌어도 여기는 그대로여야 하기 때문이다.
recipe 는 아직 store 가 맡는 자산이 아니라 여기서 직접 읽는다.

**노드에는 종류가 적혀 있지 않다.** 성격은 관계가 말한다.
  hasOutput 이 있다        -> 실행할 수 있다
  about 의 대상으로 나온다  -> 대상(그룹) 노드다
  둘 다 아니다             -> 오가는 데이터(타입) 노드다
"""

import yaml

import paths
from ontology import store

IS_A = "is-a"
ABOUT = "about"
HAS_INPUT = "hasInput"
HAS_OUTPUT = "hasOutput"


# (파일 원문, 파싱한 edges). 내용이 그대로면 다시 파싱하지 않는다.
_EDGE_SNAPSHOT: tuple[bytes, list[dict]] | None = None


def _edges() -> list[dict]:
    """edges 스냅샷.

    경로 생성이 `can_connect()` 를 수천 번 부르고, 그것이 다시 `inputs_of` ·
    `outputs_of` · `ancestors` 를 부른다. 매번 yaml 을 다시 파싱하면 등록 한
    번이 몇 분씩 걸린다 — 실제로 걸려서 이 캐시를 넣었다.

    **키는 파일 내용이다.** mtime 이 아니다 — `reset_to_init()` 은 파일을
    복사하고 등록은 같은 초 안에 여러 번 쓴다. 내용이 바뀌면 키가 바뀌므로
    캐시가 낡은 채로 남을 수 없다.

    store 에 캐시를 두지 않는 이유도 같다. 저장소는 쓰는 쪽이라 "방금 쓴 것이
    다음 읽기에 보인다" 를 어기면 안 된다. 여기는 읽기 전용 계산이다.
    """
    global _EDGE_SNAPSHOT
    raw = store.raw_bytes()
    if _EDGE_SNAPSHOT is None or _EDGE_SNAPSHOT[0] != raw:
        _EDGE_SNAPSHOT = (raw, store.edges())
    return _EDGE_SNAPSHOT[1]


def _by_predicate(predicate: str) -> list[tuple[str, str]]:
    """그 관계의 (from, to) 쌍만. 파일 순서 그대로."""
    return [
        (edge["from"], edge["to"])
        for edge in _edges()
        if edge.get("predicate") == predicate
    ]


def load_ontology() -> dict:
    """ontology.yaml 원문을 dict 로 돌려준다."""
    return store.read()


# ------------------------------------------------------------ 관계 조회
def ancestors(type_id: str) -> list[str]:
    """is-a 를 타고 올라간 상위 타입들. 자기 자신은 넣지 않는다.

    범용 노드가 상위 타입 한 줄만 적어도 하위 타입을 받게 하는 장치다 —
    Word 생성은 "분석결과" 만 적고, 프레임 추출은 "영상" 만 적는다.

    순환이 적혀 있어도 멈춘다. 온톨로지가 잘못 적히는 것보다 화면이 안 도는 것이
    더 나쁘다.
    """
    parents: dict[str, list[str]] = {}
    for child, parent in _by_predicate(IS_A):
        parents.setdefault(child, []).append(parent)

    found, queue, seen = [], list(parents.get(type_id, [])), {type_id}
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        found.append(current)
        queue += parents.get(current, [])
    return found


def inputs_of(node_id: str) -> list[str]:
    """그 노드가 받는 타입들."""
    return [to for frm, to in _by_predicate(HAS_INPUT) if frm == node_id]


def outputs_of(node_id: str) -> list[str]:
    """그 노드가 내놓는 타입들."""
    return [to for frm, to in _by_predicate(HAS_OUTPUT) if frm == node_id]


def about_of(node_id: str) -> set[str]:
    """그 노드가 관한 대상들. 여러 개일 수 있다.

    승강장 CCTV 영상은 승강장에 관한 것이자 CCTV 에 관한 것이다.
    """
    return {to for frm, to in _by_predicate(ABOUT) if frm == node_id}


def group_ids() -> list[str]:
    """대상(그룹) 노드. about 의 대상으로 등장하는 노드가 그룹이다.

    파일에 kind 를 적지 않는 이유가 이것이다 — 관계가 이미 말하고 있는 것을
    노드에 또 적으면 둘이 조용히 어긋날 수 있다.
    """
    return list(dict.fromkeys(to for _, to in _by_predicate(ABOUT)))


def is_executable(node_id: str) -> bool:
    """실행해서 무언가를 내놓는 노드인가. hasOutput 이 있으면 그렇다."""
    return bool(outputs_of(node_id))


def type_ids() -> list[str]:
    """오가는 형식. 누군가 "이걸 받는다 / 내놓는다" 고 선언한 노드다.

    영상 · 이미지 · 문서 · 분석결과가 여기 해당한다. 형식은 그 자체로 손에
    잡히는 데이터가 아니다 — "영상" 이라고만 하면 어느 영상인지 알 수 없다.
    """
    return list(
        dict.fromkeys(to for _, to in _by_predicate(HAS_INPUT) + _by_predicate(HAS_OUTPUT))
    )


def start_ids() -> list[str]:
    """경로가 시작할 수 있는 노드. **손에 잡히는 구체적인 데이터**다.

    실행 노드도 그룹도 형식도 아닌 것이 남는다 — 승강장 CCTV 영상, 궤도 검측차
    영상, 궤도 점검 보고서.

    형식을 시작점으로 삼으면 안 된다. "영상으로 프레임을 추출하고..." 라는
    recipe 가 만들어지는데, 사람이 그걸 골라도 **어느 영상인지 아무 데도 안
    적혀 있다.** 시연에서 실행하려는 순간 막힌다.
    """
    excluded = set(group_ids()) | set(type_ids())
    return [
        node_id
        for node_id in store.nodes()
        if node_id not in excluded and not is_executable(node_id)
    ]


def handed_over(node_id: str) -> list[str]:
    """그 노드가 다음 단계에 건네는 타입들.

    실행 노드는 hasOutput 이 말한다. **데이터 노드는 자기 자신이다** —
    승강장 CCTV 영상은 무언가를 내놓는 것이 아니라 그 자체가 건네지는 것이다.
    이것이 불러오기 노드를 없앨 수 있었던 이유다.
    """
    return outputs_of(node_id) or [node_id]


def can_connect(producer: str, consumer: str) -> bool:
    """producer 가 건네는 것을 consumer 가 받을 수 있나.

    같은 타입이거나, **consumer 가 받는 타입이 그것의 조상**이면 받는다.
    프레임 추출은 "영상" 만 받는다고 적혀 있어도 승강장 CCTV 영상을 받는다.

    반대 방향은 안 된다 — "영상" 을 내놓는 노드를 "승강장 CCTV 영상" 만 받는
    노드에 이을 수는 없다. 그 영상이 승강장 것이라는 보장이 없기 때문이다.
    """
    accepted = set(inputs_of(consumer))
    if not accepted:
        # 받는 것이 없는 노드(데이터 · 그룹)는 누구의 뒤에도 설 수 없다.
        return False

    for handed in handed_over(producer):
        if accepted & {handed, *ancestors(handed)}:
            return True
    return False


def crosses_groups(node_ids) -> bool:
    """그 경로가 대상을 넘나드는가.

    경로에 나온 노드들의 about 을 모아 본다. 대상이 붙은 노드가 둘 이상인데
    **공통 대상이 하나도 없으면** 넘나드는 것이다 — 승강장 CCTV 로 궤도 균열을
    찾는 경로가 그렇다. 화각이 안 맞아 실제로는 실행할 수 없다.

    대상이 붙은 노드가 하나 이하면 거짓이다. 어긋날 상대가 없다 — 어느 대상에도
    안 매인 범용 노드(형식만 바꾸는 생성 노드)만으로 된 경로가 그렇다.

    **차단자다.** 등록(`registry.register_node`)이 이것으로 경로를 거른다. 참인
    경로는 recipe 가 되지 않고 화면에도 안 나온다.

    예전에는 표시만 하고 사람이 화면에서 승인했다. 관문이 시연 화면의 절반을
    먹고, 걸러지는 것이 전부 진짜 쓰레기라(사람이 건질 조합이 하나도 없었다)
    차단으로 바꿨다. **검토 절차가 이 Streamlit 화면 밖에 제대로 들어오면 여기가
    분류로 돌아갈 지점이다** — 무엇이 말이 안 되는지 아는 곳은 여기뿐이다.
    """
    marked = [about_of(node_id) for node_id in node_ids if about_of(node_id)]
    return len(marked) > 1 and not set.intersection(*marked)


# ------------------------------------------------------------ recipe
def recipe_nodes(recipe_id: str) -> list[str]:
    """recipes/<recipe_id>.yaml 에서 노드 id 를 step 순서 그대로 읽는다."""
    recipe_path = paths.RECIPES_DIR / f"{recipe_id}.yaml"
    if not recipe_path.exists():
        return []
    data = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    return [step["node"] for step in data.get("steps", [])]


def solid_edges() -> list[tuple[str, str]]:
    """recipe 에 실제로 이어져 있는 노드 쌍. 파일 순서 그대로, 중복 없이.

    **인터페이스 라벨이 없어졌다.** 예전에는 두 노드가 무엇을 주고받는지 값으로
    담았는데, 이제 그 데이터가 경로 안에 노드로 들어 있다 —
    `승강장 CCTV 영상 -> 프레임 추출 -> 혼잡도 분석` 처럼. 라벨로 또 적으면
    같은 것을 두 번 말하는 셈이다.

    같은 쌍이 여러 recipe 에 나와도 한 번만 담는다. 두 번 그리면 선이 겹쳐
    두꺼워 보이고, 조합마다 엣지 수가 달라져 레이아웃이 흔들린다.
    """
    pairs = []
    for recipe_path in sorted(paths.RECIPES_DIR.glob("*.yaml")):
        chain = recipe_nodes(recipe_path.stem)
        pairs += list(zip(chain, chain[1:]))
    return list(dict.fromkeys(pairs))


def dotted_edges() -> dict[tuple[str, str], list[str]]:
    """about 관계. {(a, b): ["about"]}.

    **방향이 없다.** (a, b) 와 (b, a) 를 둘 다 담으면 선이 겹쳐 그려지므로
    쌍을 정렬해 한 번만 담는다.

    한 노드가 여러 대상에 붙을 수 있어 점선을 여러 개 갖는다 —
    승강장 CCTV 영상은 승강장에도, CCTV 에도 붙는다.

    반환 형태는 예전과 같다. 이 형태만 지키면 그리는 쪽은 구조가 바뀐 것을 모른다.
    """
    edges: dict[tuple[str, str], list[str]] = {}
    for frm, to in _by_predicate(ABOUT):
        labels = edges.setdefault(tuple(sorted((frm, to))), [])
        if ABOUT not in labels:
            labels.append(ABOUT)
    return edges


def highlight_edges(recipe_id: str) -> list[tuple[str, str]]:
    """선택된 recipe 의 실행 경로. [(from, to), ...] 순서 그대로.

    집합이 아니라 리스트다 — 순번 라벨을 붙여야 하고, recipe 에 루프가
    생겨 같은 엣지를 두 번 지날 때 그것을 뭉개면 안 된다.
    """
    chain = recipe_nodes(recipe_id)
    return list(zip(chain, chain[1:]))
