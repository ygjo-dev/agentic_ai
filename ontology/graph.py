"""온톨로지 그래프 계산.

순수 함수만 둔다. Streamlit 도 DOT 문법도 모른다 — 그리는 방법은
app/ui/graph_svg/ 가 안다.

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

    출력  edge dict 목록
    규칙  캐시 키는 파일 원문 바이트. 내용이 그대로면 다시 파싱하지 않음
    제약  키를 mtime 으로 바꾸지 않는다.
          reset_to_init() 은 파일을 복사하고 등록은 같은 초 안에 여러 번 씀.
          내용이 키면 바뀔 때 키도 바뀌므로 캐시가 낡은 채로 남을 수 없음
          store 에 캐시를 두지 않는다.
          저장소는 쓰는 쪽이라 "방금 쓴 것이 다음 읽기에 보인다" 를 어기면
          안 됨. 여기는 읽기 전용 계산임
    이력  경로 생성이 can_connect() 를 수천 번 부르고 그것이 다시 inputs_of ·
          outputs_of · ancestors 를 부름. 매번 yaml 을 다시 파싱해 등록 한 번이
          몇 분씩 걸렸음. 실제로 걸려서 이 캐시를 넣었음
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

    입력  타입 id
    출력  상위 타입 id 목록. 자기 자신은 안 들어감
    규칙  범용 노드가 상위 타입 한 줄만 적어도 하위 타입을 받게 하는 장치
          예 : Word 생성은 "분석결과" 만, 프레임 추출은 "영상" 만 적음
          순환이 적혀 있어도 멈춤. 온톨로지가 잘못 적히는 것보다 화면이
          안 도는 것이 더 나쁨
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

    출력  대상 노드 id 집합. 여러 개일 수 있음
    규칙  예 : 승강장 CCTV 영상은 승강장에 관한 것이자 CCTV 에 관한 것임
    """
    return {to for frm, to in _by_predicate(ABOUT) if frm == node_id}


def group_ids() -> list[str]:
    """대상(그룹) 노드.

    출력  노드 id 목록
    규칙  about 의 대상으로 등장하는 노드가 그룹임
    제약  노드에 kind 를 적지 않는다.
          관계가 이미 말하고 있는 것을 노드에 또 적으면 둘이 조용히 어긋남
    """
    return list(dict.fromkeys(to for _, to in _by_predicate(ABOUT)))


def is_executable(node_id: str) -> bool:
    """실행해서 무언가를 내놓는 노드인가.

    출력  참이면 실행 노드
    규칙  hasOutput 이 있으면 참
    """
    return bool(outputs_of(node_id))


def type_ids() -> list[str]:
    """오가는 형식.

    출력  노드 id 목록
    규칙  누군가 "이걸 받는다 / 내놓는다" 고 선언한 노드
          영상 · 이미지 · 문서 · 분석결과가 해당
          형식은 그 자체로 손에 잡히는 데이터가 아님.
          "영상" 이라고만 하면 어느 영상인지 알 수 없음
    """
    return list(
        dict.fromkeys(to for _, to in _by_predicate(HAS_INPUT) + _by_predicate(HAS_OUTPUT))
    )


def start_ids() -> list[str]:
    """경로의 시작점. 손에 잡히는 구체적인 데이터.

    입력  없음. 온톨로지 전체를 봄
    출력  노드 id 목록
    규칙  전체에서 아래를 뺌
            group_ids()   about 의 대상
            type_ids()    hasInput/hasOutput 의 대상
            실행 노드     hasOutput 이 있는 것
          남는 것 : 승강장 CCTV 영상 · 궤도 검측차 영상 · 궤도 점검 보고서
    제약  형식을 시작점으로 삼지 않는다.
          "영상으로 프레임을 추출하고…" recipe 가 생기는데 사람이 골라도
          어느 영상인지 아무 데도 안 적혀 시연에서 실행하려는 순간 막힘
    """
    excluded = set(group_ids()) | set(type_ids())
    return [
        node_id
        for node_id in store.nodes()
        if node_id not in excluded and not is_executable(node_id)
    ]


def handed_over(node_id: str) -> list[str]:
    """다음 단계에 건네는 타입들.

    입력  노드 id
    출력  타입 id 목록
    규칙  실행 노드   hasOutput 이 말함
          데이터 노드 자기 자신. 내놓는 게 아니라 그 자체가 건네짐
    제약  데이터 노드에 hasOutput video 를 적지 않는다.
          건네는 것이 "영상" 이 되어 구체 타입을 잃음. is-a 가 그 위를 말함
    이력  데이터 노드가 자기 자신을 건네게 되어 불러오기 노드를 없앨 수 있었음
    """
    return outputs_of(node_id) or [node_id]


def can_connect(producer: str, consumer: str) -> bool:
    """producer 가 건네는 것을 consumer 가 받을 수 있나.

    입력  producer · consumer 노드 id
    출력  참이면 이을 수 있음
    규칙  같은 타입이거나 consumer 가 받는 타입이 그것의 조상이면 받음
          예 : 프레임 추출은 "영상" 만 받는다고 적혀 있어도
               승강장 CCTV 영상을 받음
    제약  반대 방향으로 잇지 않는다.
          "영상" 을 내놓는 노드를 "승강장 CCTV 영상" 만 받는 노드에
          이을 수 없음. 그 영상이 승강장 것이라는 보장이 없음
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

    입력  노드 id 목록. 경로 순서
    출력  참이면 넘나듦. registry.register_node 가 여기서 버림.
          recipe 가 되지 않고 화면에도 안 나옴
    규칙  노드들의 about 을 모음
          about 붙은 노드 2개 이상 + 공통 대상 0개  → 참
          about 붙은 노드 1개 이하                  → 거짓. 어긋날 상대 없음
          예 : 승강장 CCTV → 프레임 추출 → 궤도 균열 검출
               타입은 이어지나 화각이 안 맞아 실행 불가
          어느 대상에도 안 매인 범용 노드(형식만 바꾸는 생성 노드)만으로 된
          경로가 1개 이하에 해당
    이력  f9bbda1 이전 분류자였음. 표시만 하고 사람이 화면에서 승인
          f9bbda1 에서 차단자로 전환. 관문이 시연 화면의 절반을 먹었고
          걸러진 것이 전부 쓰레기였음. 사람이 건질 조합 0개
          검토 절차가 Streamlit 밖에 제대로 들어오면 여기가 분류로 돌아갈
          지점. 무엇이 말이 안 되는지 아는 곳은 여기뿐임
    """
    marked = [about_of(node_id) for node_id in node_ids if about_of(node_id)]
    return len(marked) > 1 and not set.intersection(*marked)


# ------------------------------------------------------------ recipe
def recipe_nodes(recipe_id: str) -> list[str]:
    """recipe 의 노드 id 목록.

    입력  recipe id
    출력  노드 id 목록. step 순서 그대로.
          recipes/<recipe_id>.yaml 이 없으면 빈 목록
    """
    recipe_path = paths.RECIPES_DIR / f"{recipe_id}.yaml"
    if not recipe_path.exists():
        return []
    data = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    return [step["node"] for step in data.get("steps", [])]


def recipe_facets(recipe_id: str) -> dict:
    """recipe 한 벌을 축 셋으로 요약.

    입력  recipe id
    출력  given  경로의 첫 노드 id. 없는 recipe 면 None
          want   마지막 노드가 다음에 건네는 타입 id 목록
          about  경로 노드들의 about 합집합
    규칙  want 는 handed_over 가 말함. 실행 노드는 hasOutput 이고
          데이터 노드는 자기 자신임
          about 은 crosses_groups 가 보는 것과 같은 재료임
          없는 recipe 는 recipe_nodes 가 빈 목록을 내므로 빈 축을 냄
    제약  is-a 를 타고 올라가지 않는다.
          상위 타입 하나가 하위 전부를 끌어와 좁히는 뜻이 없어짐
    """
    chain = recipe_nodes(recipe_id)
    if not chain:
        return {"given": None, "want": [], "about": set()}

    about: set[str] = set()
    for node_id in chain:
        about |= about_of(node_id)

    return {"given": chain[0], "want": handed_over(chain[-1]), "about": about}


def solid_edges() -> list[tuple[str, str]]:
    """recipe 에 실제로 이어져 있는 노드 쌍.

    출력  (from, to) 목록. 파일 순서 그대로, 중복 없음
    규칙  같은 쌍이 여러 recipe 에 나와도 한 번만 담음
    제약  인터페이스 라벨을 되살리지 않는다.
          두 노드가 무엇을 주고받는지는 이미 경로 안에 노드로 들어 있음
          (승강장 CCTV 영상 -> 프레임 추출 -> 혼잡도 분석).
          라벨로 또 적으면 같은 것을 두 번 말하는 셈
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
    규칙  방향이 없음. 쌍을 정렬해 한 번만 담음
          한 노드가 여러 대상에 붙어 점선을 여러 개 가짐
          예 : 승강장 CCTV 영상은 승강장에도 CCTV 에도 붙음
    제약  (a, b) 와 (b, a) 를 둘 다 담지 않는다. 선이 겹쳐 그려짐
    이력  반환 형태가 예전과 같음.
          이 형태만 지키면 그리는 쪽은 구조가 바뀐 것을 모름
    """
    edges: dict[tuple[str, str], list[str]] = {}
    for frm, to in _by_predicate(ABOUT):
        labels = edges.setdefault(tuple(sorted((frm, to))), [])
        if ABOUT not in labels:
            labels.append(ABOUT)
    return edges


def highlight_edges(recipe_id: str) -> list[tuple[str, str]]:
    """선택된 recipe 의 실행 경로.

    입력  recipe id
    출력  (from, to) 목록. 순서 그대로
    제약  집합으로 만들지 않는다.
          순번 라벨을 붙여야 하고, recipe 에 루프가 생겨 같은 엣지를
          두 번 지날 때 뭉개면 안 됨
    """
    chain = recipe_nodes(recipe_id)
    return list(zip(chain, chain[1:]))
