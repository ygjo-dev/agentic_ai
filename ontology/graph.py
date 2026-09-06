"""온톨로지의 관계 · 경로 계산.

**여기가 아는 것은 관계와 도메인 계산뿐이다.** 그리는 방법(Streamlit · DOT)도,
파일 형식도 모른다 — 온톨로지는 store 에게 묻고 그리기는 app/ui/graph/ 가 안다.
저장소를 바꿀 때 고칠 곳을 store 경계에 모으려는 것이다.
recipe 는 아직 store 가 맡는 자산이 아니라 여기서 직접 읽는다.

부수효과가 아주 없지는 않다 — _edges() 가 파싱 결과를 스냅샷으로 들고 있고
recipe 는 파일에서 읽는다. 계산은 그 위에 순수하게 얹혀 있다.

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

# 지금 지원하는 관계. **여기 없는 predicate 가 온톨로지에 있으면 아무도 안 읽는다.**
#
# 새 관계를 더하려면 여기에 이름을 더하고 그것을 실제로 읽는 로직을 함께 만든다.
# 넷이라는 수 자체가 불변식인 것은 아니다 — 읽는 곳이 있는 관계만 둔다는 것이
# 규칙이고, 읽는 곳이 없어진 관계는 뺀다.
SUPPORTED_PREDICATES = (IS_A, ABOUT, HAS_INPUT, HAS_OUTPUT)


# (파일 원문, 파싱한 edges). 내용이 그대로면 다시 파싱하지 않는다.
_EDGE_SNAPSHOT: tuple[bytes, list[dict]] | None = None


def _edges() -> list[dict]:
    """edges 스냅샷.

    규칙  캐시 키는 파일 원문 바이트. 내용이 그대로면 다시 파싱하지 않음
          경로 생성이 can_connect() 를 수천 번 부름. 매번 파싱하면 등록 한 번이
          몇 분씩 걸림(실측)
    제약  키를 mtime 으로 바꾸지 않는다.
          reset_to_init() 은 파일을 복사하고 등록은 같은 초 안에 여러 번 씀
          store 에 캐시를 두지 않는다.
          저장소는 쓰는 쪽이라 "방금 쓴 것이 다음 읽기에 보인다" 를 어기면 안 됨
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
    """ontology.yaml 원문. dict 로 돌려줌."""
    return store.read()


# ------------------------------------------------------------ 관계 조회
def ancestors(type_id: str) -> list[str]:
    """is-a 를 타고 올라간 상위 타입들.

    출력  상위 타입 id 목록. 자기 자신은 안 들어감
    규칙  범용 노드가 상위 타입 한 줄만 적어도 하위 타입을 받게 하는 장치.
          프레임 추출은 "영상" 만 적고도 승강장 CCTV 영상을 받음
    제약  순환이 적혀 있어도 멈춘다.
          온톨로지가 잘못 적히는 것보다 화면이 안 도는 것이 더 나쁨
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
    """그 노드가 관한 대상들.

    출력  대상 노드 id 집합. 여럿일 수 있음. 승강장 CCTV 영상은 승강장에도
          CCTV 에도 관한 것임
    """
    return {to for frm, to in _by_predicate(ABOUT) if frm == node_id}


def group_ids() -> list[str]:
    """대상(그룹) 노드.

    규칙  about 의 대상으로 등장하는 노드가 그룹임
    제약  노드에 kind 를 적지 않는다.
          관계가 이미 말하고 있는 것을 노드에 또 적으면 둘이 조용히 어긋남
    """
    return list(dict.fromkeys(to for _, to in _by_predicate(ABOUT)))


def is_executable(node_id: str) -> bool:
    """실행해서 무언가를 내놓는 노드인가. hasOutput 이 있으면 참."""
    return bool(outputs_of(node_id))


def type_ids() -> list[str]:
    """오가는 형식.

    규칙  누군가 "이걸 받는다 / 내놓는다" 고 선언한 노드
          형식은 손에 잡히는 데이터가 아님. "영상" 이라고만 하면 어느 영상인지
          알 수 없어 start_ids 가 이것을 시작점에서 뺌
    """
    return list(
        dict.fromkeys(to for _, to in _by_predicate(HAS_INPUT) + _by_predicate(HAS_OUTPUT))
    )


def start_ids() -> list[str]:
    """경로의 시작점. 손에 잡히는 구체적인 데이터.

    규칙  온톨로지 전체에서 그룹 · 형식 · 실행 노드를 뺀 나머지
    제약  형식을 시작점으로 삼지 않는다.
          "영상으로 프레임을 추출하고…" recipe 가 생기는데 사람이 골라도
          어느 영상인지 아무 데도 안 적혀 실행하려는 순간 막힘
    """
    excluded = set(group_ids()) | set(type_ids())
    return [
        node_id
        for node_id in store.nodes()
        if node_id not in excluded and not is_executable(node_id)
    ]


def handed_over(node_id: str) -> list[str]:
    """다음 단계에 건네는 타입들.

    규칙  실행 노드   hasOutput 이 말함
          데이터 노드 자기 자신. 내놓는 게 아니라 그 자체가 건네짐.
                      그래서 불러오기 노드가 따로 없음
    제약  데이터 노드에 hasOutput video 를 적지 않는다.
          건네는 것이 "영상" 이 되어 구체 타입을 잃음. is-a 가 그 위를 말함
    """
    return outputs_of(node_id) or [node_id]


def handed_types(node_id: str) -> list[str]:
    """그 노드가 다음 자리에 건네는 타입. 상위 타입까지 편 것.

    출력  타입 id 목록. 앞에 오는 것이 먼저 건네는 것
    규칙  차례는 hasOutput 에 적힌 순서 그대로임. 장소 좌표 변환은 지점 좌표를
          지도 범위보다 먼저 내놓고, wiring_at 이 그 차례로 줄을 고름
          데이터 노드는 자기 자신을 건네므로 is-a 로 가리키는 상위 타입을 폄
    제약  받는 쪽이 무엇을 받는지 보지 않는다. 고르는 것은 부르는 쪽 일임
    """
    seen, handed = set(), []
    for out_id in handed_over(node_id):
        for type_id in (out_id, *ancestors(out_id)):
            if type_id not in seen:
                seen.add(type_id)
                handed.append(type_id)
    return handed


def can_connect(producer: str, consumer: str) -> bool:
    """producer 가 건네는 것을 consumer 가 받을 수 있나.

    규칙  같은 타입이거나 consumer 가 받는 타입이 그것의 조상이면 받음.
          프레임 추출은 "영상" 만 받는다고 적혀 있어도 승강장 CCTV 영상을 받음
    제약  반대 방향으로 잇지 않는다.
          "영상" 을 내놓는 노드를 "승강장 CCTV 영상" 만 받는 노드에 이을 수
          없음. 그 영상이 승강장 것이라는 보장이 없음
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
    """경로가 대상을 넘나드는가.

    출력  참이면 넘나듦. about 이 말하는 group 호환성을 계산할 뿐이고 무엇을
          버릴지는 여기서 안 정함
    규칙  about 붙은 노드가 2개 이상인데 공통 대상이 0개면 참
          1개 이하면 거짓. 어긋날 상대가 없음. 대상이 안 붙은 범용 노드만으로
          된 경로가 그 자리임
          예 : 승강장 CCTV → 프레임 추출 → 궤도 균열 검출.
               타입은 이어지나 화각이 안 맞아 실행 불가
          ★ 이 값을 recipe 생성 정책에서 최종적으로 어떻게 쓸지는 아직
            확정되지 않았음. 지금 registration 구현은 참인 경로를 recipe 로
            만들지 않음(registry.register_node)
    제약  계산을 다른 데로 옮기지 않는다.
          about 을 읽는 곳이 여기뿐임. 정책이 바뀌어도 이 계산은 그대로 씀
    """
    marked = [about_of(node_id) for node_id in node_ids if about_of(node_id)]
    return len(marked) > 1 and not set.intersection(*marked)


# ------------------------------------------------------------ recipe
def recipe_nodes(recipe_id: str) -> list[str]:
    """recipe 의 노드 id 목록.

    출력  노드 id 목록. step 순서 그대로. 파일이 없으면 예외 대신 빈 목록
    """
    recipe_path = paths.RECIPES_DIR / f"{recipe_id}.yaml"
    if not recipe_path.exists():
        return []
    data = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    return [step["node"] for step in data.get("steps", [])]


def recipe_ids() -> list[str]:
    """지금 있는 recipe id 전부. 번호 순."""
    return sorted(path.stem for path in paths.RECIPES_DIR.glob("recipe_*.yaml"))


def executable_in(recipe_id: str) -> list[str]:
    """recipe 안에서 실제로 부를 노드.

    출력  실행 노드 id 목록. 경로 순서 그대로
    규칙  데이터 노드(말한 장소)는 값을 준비할 뿐 부를 것이 없어 빠짐
    """
    return [node_id for node_id in recipe_nodes(recipe_id) if is_executable(node_id)]


def path_of(recipe_id: str, nodes: dict | None = None) -> list[dict]:
    """recipe 한 벌의 실행 경로.

    출력  [{node_id, name, out_type}, ...] 순서 그대로. 없는 recipe 는 빈 목록
    규칙  out_type 은 다음 노드로 흘러가는 것. 실행 노드는 hasOutput 이 말하고
          데이터 노드는 자기 자신을 건넴
    제약  이름을 여기서만 붙인다.
          순서를 아는 곳이 여기뿐이다. 두 곳에서 붙이면 조용히 어긋남
    """
    nodes = load_ontology()["nodes"] if nodes is None else nodes

    chain = []
    for node_id in recipe_nodes(recipe_id):
        node = nodes.get(node_id) or {}
        handed = outputs_of(node_id) or [node_id]
        chain.append(
            {
                "node_id": node_id,
                "name": node.get("name", node_id),
                "out_type": nodes.get(handed[0], {}).get("name", handed[0]),
            }
        )
    return chain


def paths_for(ids, nodes: dict | None = None) -> dict[str, list[dict]]:
    """recipe id 여럿의 경로를 한 번에. 중복은 접고 순서는 유지함."""
    nodes = load_ontology()["nodes"] if nodes is None else nodes
    return {recipe_id: path_of(recipe_id, nodes) for recipe_id in dict.fromkeys(ids)}


def solid_edges() -> list[tuple[str, str]]:
    """recipe 에 실제로 이어져 있는 노드 쌍.

    출력  (from, to) 목록. 파일 순서 그대로, 중복 없음
    제약  인터페이스 라벨을 되살리지 않는다.
          무엇을 주고받는지는 이미 경로 안에 노드로 들어 있음
          (승강장 CCTV 영상 -> 프레임 추출 -> 혼잡도 분석)
          같은 쌍을 두 번 담지 않는다.
          선이 겹쳐 두꺼워 보이고 조합마다 엣지 수가 달라져 레이아웃이 흔들림
    """
    pairs = []
    for recipe_path in sorted(paths.RECIPES_DIR.glob("*.yaml")):
        chain = recipe_nodes(recipe_path.stem)
        pairs += list(zip(chain, chain[1:]))
    return list(dict.fromkeys(pairs))


def dotted_edges() -> dict[tuple[str, str], list[str]]:
    """about 관계.

    출력  {(a, b): ["about"]}
    규칙  방향이 없음. 쌍을 정렬해 한 번만 담음.
          한 노드가 여러 대상에 붙어 점선을 여러 개 가질 수 있음
    제약  (a, b) 와 (b, a) 를 둘 다 담지 않는다. 선이 겹쳐 그려짐
    """
    edges: dict[tuple[str, str], list[str]] = {}
    for frm, to in _by_predicate(ABOUT):
        labels = edges.setdefault(tuple(sorted((frm, to))), [])
        if ABOUT not in labels:
            labels.append(ABOUT)
    return edges
