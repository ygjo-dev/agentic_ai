"""게시된 온톨로지 한 벌. **읽기만 한다.**

예전에는 둘로 나뉘어 있었다 — `store.py` 가 yaml 을 알고 `graph.py` 가 관계를
계산했다. 저장소 경계를 한 파일에 모으려던 것인데, 그 경계가 실제로 지킨 것은
`yaml.safe_load` 한 줄뿐이었고 대신 같은 것을 두 이름으로 읽는 자리가 생겼다
(`store.read` · `graph.load_ontology`). 캐시도 둘로 갈렸다 — 관계 계산은 파일
내용을 키로 캐시하고 노드 조회는 매번 다시 파싱했다.

**여기가 아는 것은 관계와 도메인 계산뿐이다.** 그리는 방법(Streamlit · DOT)은
모른다 — 그리기는 `app/ui/graph/` 가 안다.

**쓰는 API 가 없다.** append · save · publish 가 없고 되살리지 않는다. 노드 등록 ·
recipe 게시 · Recipe.execution compile 은 agentic_ai 밖의 등록 저장소 일이다.
`AGENTIC_ARTIFACT_ROOT` 가 공유 Registry 를 가리킬 때 이 저장소의 코드가 그
파일을 고칠 수 있는 길이 남아 있으면 안 된다 — 그 길이 없다는 것이 여기서 지키는
불변식이다.

**노드에는 종류가 적혀 있지 않다.** 성격은 관계가 말한다.
  hasOutput 이 있다        -> 실행할 수 있다
  about 의 대상으로 나온다  -> 대상(그룹) 노드다
  둘 다 아니다             -> 오가는 데이터(타입) 노드다

노드 자신이 말하는 사실은 둘이다. 여기서는 꺼내 주기만 한다.
  source  밖(발화 · 화면)에서 곧장 들어오는 자리. 경로의 시작점을 정한다
  tool    무엇으로 실행하는가. 요청 중의 실행은 이것이 아니라 게시된 Recipe.execution 을 읽는다
"""

from pathlib import Path

import yaml

import paths

IS_A = "is-a"
ABOUT = "about"
HAS_INPUT = "hasInput"
HAS_OUTPUT = "hasOutput"

# 지금 지원하는 관계. **여기 없는 predicate 가 온톨로지에 있으면 아무도 안 읽는다.**
#
# 새 관계를 더하려면 여기에 이름을 더하고 그것을 실제로 읽는 로직을 함께 만든다.
# 넷이라는 수 자체가 불변식인 것은 아니다 — 읽는 곳이 있는 관계만 둔다는 것이
# 규칙이고, 읽는 곳이 없어진 관계는 뺀다.
#
# ★ is-a 는 지금 온톨로지에 한 줄도 없다. 읽는 곳(ancestors)은 남아 있어 뺄
#   자리가 아니다 — 형식 계층으로서의 하위 타입이 생기면 그대로 쓴다.
SUPPORTED_PREDICATES = (IS_A, ABOUT, HAS_INPUT, HAS_OUTPUT)


class Ontology:
    """게시된 온톨로지 · recipe 를 읽어 관계를 답한다.

    입력  path         ontology.yaml. 안 주면 부를 때마다 paths.ONTOLOGY_PATH 를 봄
          recipes_dir  recipe 폴더. 안 주면 부를 때마다 paths.RECIPES_DIR 를 봄
    규칙  경로를 __init__ 에서 굳히지 않음. paths 전역이 배포 · 시험에서 갈리는데
          굳히면 그 갈림이 이 객체를 만든 시점에 박혀 버림
    제약  쓰는 메서드를 만들지 않는다.
          게시 자산을 고치는 것은 등록 저장소 일임. 여기 한 줄이라도 있으면
          바깥 Registry 를 가리킨 배포가 남의 파일을 고칠 수 있음
    """

    def __init__(self, path: Path | None = None, recipes_dir: Path | None = None):
        self._path = path
        self._recipes_dir = recipes_dir
        # (파일 원문, 파싱한 document). 내용이 그대로면 다시 파싱하지 않는다.
        self._parsed: tuple[bytes, dict] | None = None

    @property
    def path(self) -> Path:
        """지금 읽는 ontology.yaml."""
        return self._path or paths.ONTOLOGY_PATH

    @property
    def recipes_dir(self) -> Path:
        """지금 읽는 recipe 폴더."""
        return self._recipes_dir or paths.RECIPES_DIR

    # ------------------------------------------------------------ 파일
    def raw_bytes(self) -> bytes:
        """파일 원문 그대로.

        출력  파일 바이트. 내용 해시를 만드는 쪽이 씀
        제약  dict 로 읽어 다시 직렬화해 돌려주지 않는다.
              같은 내용이 다른 바이트가 될 수 있음(키 순서 · 따옴표 · 들여쓰기).
              캐시 키가 헛돌아 화면이 깜빡임
        """
        return self.path.read_bytes()

    def document(self) -> dict:
        """ontology.yaml 원문. dict 로 돌려줌.

        규칙  캐시 키는 파일 원문 바이트. 내용이 그대로면 다시 파싱하지 않음
              경로 계산이 can_connect() 를 수천 번 부름. 매번 파싱하면 몇 분씩
              걸림(실측)
        제약  키를 mtime 으로 바꾸지 않는다.
              파일을 복사하거나 같은 초 안에 여러 번 쓰면 mtime 이 내용을 못 가름
              돌려준 dict 를 고치지 않는다.
              캐시에 든 그 dict 임. 읽기 전용으로 쓴다
        """
        raw = self.raw_bytes()
        if self._parsed is None or self._parsed[0] != raw:
            self._parsed = (raw, yaml.safe_load(self.path.read_text(encoding="utf-8")))
        return self._parsed[1]

    def nodes(self) -> dict:
        """노드 dict.

        출력  {node_id: {name, description, source?, tool?}}
        규칙  종류를 나누는 필드가 없음. 성격은 관계가 말하고 판정은 여기가 함
              source · tool 은 그 노드 자신의 사실이라 노드에 붙음. 실행은 게시된
              Recipe.execution 을 읽음
        """
        return self.document().get("nodes") or {}

    def edges(self) -> list[dict]:
        """노드 사이의 관계. RDF 의 삼항 구조(주어 · 술어 · 목적어)를 그대로 씀.

        출력  [{"from": ..., "to": ..., "predicate": ...}, ...] 파일 순서 그대로.
              블록이 없으면 빈 목록 — 여기서 예외를 올리면 화면이 죽음
        제약  읽는 곳 없는 predicate 를 늘리지 않는다.
              지금 지원하는 것은 SUPPORTED_PREDICATES 넷임. 새 관계는 그것을
              실제로 읽는 로직과 함께 더함
              실행 순서(실선)를 여기 적지 않는다.
              그건 recipe 가 정함. 두 곳에 적으면 어긋났을 때 어느 쪽이 맞는지
              알 수 없음
        """
        return self.document().get("edges") or []

    def _by_predicate(self, predicate: str) -> list[tuple[str, str]]:
        """그 관계의 (from, to) 쌍만. 파일 순서 그대로."""
        return [
            (edge["from"], edge["to"])
            for edge in self.edges()
            if edge.get("predicate") == predicate
        ]

    # ------------------------------------------------------------ 노드가 말하는 것
    def node_ids(self) -> list[str]:
        """온톨로지의 노드 id 전부. 파일에 적힌 차례."""
        return list(self.nodes())

    def source_of(self, node_id: str) -> dict | None:
        """그 노드가 밖에서 곧장 들어오는 자리.

        출력  온톨로지에 적힌 source 그대로({from, description, fields?}). 없으면 None
        규칙  유일한 생성원이 아님. 지점 좌표는 화면에서도 오고 장소 좌표 변환도 내놓음
        """
        source = (self.nodes().get(node_id) or {}).get("source")
        return source if isinstance(source, dict) else None

    def tool_of(self, node_id: str) -> dict | None:
        """그 노드를 무엇으로 실행하는가.

        출력  온톨로지에 적힌 tool 그대로({id, parameters, outputs?}). 없으면 None
        제약  여기서 뜻을 풀지 않는다.
              도구 id 의 namespace · parameters · outputs 문법은 Recipe.execution 을
              compile 하는 쪽(agentic_ai 밖의 등록 저장소)이 읽음
        """
        tool = (self.nodes().get(node_id) or {}).get("tool")
        return tool if isinstance(tool, dict) else None

    # ------------------------------------------------------------ 관계 조회
    def ancestors(self, type_id: str) -> list[str]:
        """is-a 를 타고 올라간 상위 타입들.

        출력  상위 타입 id 목록. 자기 자신은 안 들어감
        규칙  범용 노드가 상위 타입 한 줄만 적어도 하위 타입을 받게 하는 장치.
              프레임 추출은 "영상" 만 적고도 승강장 CCTV 영상을 받음
        제약  순환이 적혀 있어도 멈춘다.
              온톨로지가 잘못 적히는 것보다 화면이 안 도는 것이 더 나쁨
        """
        parents: dict[str, list[str]] = {}
        for child, parent in self._by_predicate(IS_A):
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

    def inputs_of(self, node_id: str) -> list[str]:
        """그 노드가 받는 타입들."""
        return [to for frm, to in self._by_predicate(HAS_INPUT) if frm == node_id]

    def outputs_of(self, node_id: str) -> list[str]:
        """그 노드가 내놓는 타입들."""
        return [to for frm, to in self._by_predicate(HAS_OUTPUT) if frm == node_id]

    def about_of(self, node_id: str) -> set[str]:
        """그 노드가 관한 대상들.

        출력  대상 노드 id 집합. 여럿일 수 있음. 승강장 CCTV 영상은 승강장에도
              CCTV 에도 관한 것임
        """
        return {to for frm, to in self._by_predicate(ABOUT) if frm == node_id}

    def group_ids(self) -> list[str]:
        """대상(그룹) 노드.

        규칙  about 의 대상으로 등장하는 노드가 그룹임
        제약  노드에 kind 를 적지 않는다.
              관계가 이미 말하고 있는 것을 노드에 또 적으면 둘이 조용히 어긋남
        """
        return list(dict.fromkeys(to for _, to in self._by_predicate(ABOUT)))

    def is_executable(self, node_id: str) -> bool:
        """실행해서 무언가를 내놓는 노드인가. hasOutput 이 있으면 참."""
        return bool(self.outputs_of(node_id))

    def type_ids(self) -> list[str]:
        """오가는 형식.

        규칙  누군가 "이걸 받는다 / 내놓는다" 고 선언한 노드
        """
        pairs = self._by_predicate(HAS_INPUT) + self._by_predicate(HAS_OUTPUT)
        return list(dict.fromkeys(to for _, to in pairs))

    def start_ids(self) -> list[str]:
        """경로의 시작점. 밖에서 곧장 들어오는 값이 있는 노드.

        출력  source 가 적힌 노드 id 목록. 온톨로지에 적힌 차례
        규칙  시작점을 정하는 것은 source 하나임. 타입 노드여도 source 가 있으면
              시작점이 됨. 장소 이름은 발화에서, 지점 좌표는 화면에서 곧장 옴
              source 가 없는 타입(행정구역 코드 · 충전소 번호 · 목록)은 앞 단계가
              내놓을 때만 경로에 들어옴
        제약  source 없는 형식을 시작점으로 삼지 않는다.
              "목록으로 …" recipe 가 생기는데 사람이 골라도 어느 목록인지 아무 데도
              안 적혀 실행하려는 순간 막힘
        """
        return [node_id for node_id in self.nodes() if self.source_of(node_id) is not None]

    def _handed_over(self, node_id: str) -> list[str]:
        """다음 단계에 건네는 타입들.

        규칙  실행 노드   hasOutput 이 말함
              데이터 노드 자기 자신. 내놓는 게 아니라 그 자체가 건네짐.
                          그래서 불러오기 노드가 따로 없음
        제약  데이터 노드에 hasOutput 을 적지 않는다.
              데이터 노드가 실행 노드로 읽혀 경로의 시작점에서 빠짐
        """
        return self.outputs_of(node_id) or [node_id]

    def can_connect(self, producer: str, consumer: str) -> bool:
        """producer 가 건네는 것을 consumer 가 받을 수 있나.

        규칙  같은 타입이거나 consumer 가 받는 타입이 그것의 조상이면 받음.
              프레임 추출은 "영상" 만 받는다고 적혀 있어도 승강장 CCTV 영상을 받음
        제약  반대 방향으로 잇지 않는다.
              "영상" 을 내놓는 노드를 "승강장 CCTV 영상" 만 받는 노드에 이을 수
              없음. 그 영상이 승강장 것이라는 보장이 없음
        """
        accepted = set(self.inputs_of(consumer))
        if not accepted:
            # 받는 것이 없는 노드(데이터 · 그룹)는 누구의 뒤에도 설 수 없다.
            return False

        for handed in self._handed_over(producer):
            if accepted & {handed, *self.ancestors(handed)}:
                return True
        return False

    def crosses_groups(self, node_ids) -> bool:
        """경로가 대상을 넘나드는가.

        출력  참이면 넘나듦. about 이 말하는 group 호환성을 계산할 뿐이고 무엇을
              버릴지는 여기서 안 정함
        규칙  about 붙은 노드가 2개 이상인데 공통 대상이 0개면 참
              1개 이하면 거짓. 어긋날 상대가 없음. 대상이 안 붙은 범용 노드만으로
              된 경로가 그 자리임
              예 : 승강장 CCTV → 프레임 추출 → 궤도 균열 검출.
                   타입은 이어지나 화각이 안 맞아 실행 불가
              ★ 이 값을 recipe 생성 정책에서 최종적으로 어떻게 쓸지는 아직
                확정되지 않았음. recipe 생성은 agentic_ai 밖의 등록 저장소 일임
        제약  계산을 다른 데로 옮기지 않는다.
              about 을 읽는 곳이 여기뿐임. 정책이 바뀌어도 이 계산은 그대로 씀
        """
        marked = [self.about_of(node_id) for node_id in node_ids if self.about_of(node_id)]
        return len(marked) > 1 and not set.intersection(*marked)

    # ------------------------------------------------------------ recipe
    def recipe_nodes(self, recipe_id: str) -> list[str]:
        """recipe 의 노드 id 목록.

        출력  노드 id 목록. step 순서 그대로. 파일이 없으면 예외 대신 빈 목록
        """
        recipe_path = self.recipes_dir / f"{recipe_id}.yaml"
        if not recipe_path.exists():
            return []
        data = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
        return [step["node"] for step in data.get("steps", [])]

    def recipe_ids(self) -> list[str]:
        """지금 있는 recipe id 전부. 번호 순."""
        return sorted(path.stem for path in self.recipes_dir.glob("recipe_*.yaml"))

    def executable_in(self, recipe_id: str) -> list[str]:
        """recipe 안에서 실제로 부를 노드.

        출력  실행 노드 id 목록. 경로 순서 그대로
        규칙  시작 데이터 노드(장소 이름)는 값을 준비할 뿐 부를 것이 없어 빠짐
        """
        return [node_id for node_id in self.recipe_nodes(recipe_id) if self.is_executable(node_id)]

    def path_of(self, recipe_id: str, nodes: dict | None = None) -> list[dict]:
        """recipe 한 벌의 실행 경로.

        출력  [{node_id, name, out_type}, ...] 순서 그대로. 없는 recipe 는 빈 목록
        규칙  out_type 은 다음 노드로 흘러가는 것. 실행 노드는 hasOutput 이 말하고
              데이터 노드는 자기 자신을 건넴
        제약  이름을 여기서만 붙인다.
              순서를 아는 곳이 여기뿐이다. 두 곳에서 붙이면 조용히 어긋남
        """
        nodes = self.nodes() if nodes is None else nodes

        chain = []
        for node_id in self.recipe_nodes(recipe_id):
            node = nodes.get(node_id) or {}
            handed = self._handed_over(node_id)
            chain.append(
                {
                    "node_id": node_id,
                    "name": node.get("name", node_id),
                    "out_type": nodes.get(handed[0], {}).get("name", handed[0]),
                }
            )
        return chain

    def paths_for(self, ids, nodes: dict | None = None) -> dict[str, list[dict]]:
        """recipe id 여럿의 경로를 한 번에. 중복은 접고 순서는 유지함."""
        nodes = self.nodes() if nodes is None else nodes
        return {recipe_id: self.path_of(recipe_id, nodes) for recipe_id in dict.fromkeys(ids)}

    def solid_edges(self) -> list[tuple[str, str]]:
        """recipe 에 실제로 이어져 있는 노드 쌍.

        출력  (from, to) 목록. 파일 순서 그대로, 중복 없음
        제약  인터페이스 라벨을 되살리지 않는다.
              무엇을 주고받는지는 이미 경로 안에 노드로 들어 있음
              (승강장 CCTV 영상 -> 프레임 추출 -> 혼잡도 분석)
              같은 쌍을 두 번 담지 않는다.
              선이 겹쳐 두꺼워 보이고 조합마다 엣지 수가 달라져 레이아웃이 흔들림
        """
        pairs = []
        for recipe_path in sorted(self.recipes_dir.glob("*.yaml")):
            chain = self.recipe_nodes(recipe_path.stem)
            pairs += list(zip(chain, chain[1:]))
        return list(dict.fromkeys(pairs))

    def dotted_edges(self) -> dict[tuple[str, str], list[str]]:
        """about 관계.

        출력  {(a, b): ["about"]}
        규칙  방향이 없음. 쌍을 정렬해 한 번만 담음.
              한 노드가 여러 대상에 붙어 점선을 여러 개 가질 수 있음
        제약  (a, b) 와 (b, a) 를 둘 다 담지 않는다. 선이 겹쳐 그려짐
        """
        edges: dict[tuple[str, str], list[str]] = {}
        for frm, to in self._by_predicate(ABOUT):
            labels = edges.setdefault(tuple(sorted((frm, to))), [])
            if ABOUT not in labels:
                labels.append(ABOUT)
        return edges


# 이 프로세스가 읽는 게시 온톨로지 한 벌.
#
# 새 전역을 만든 것이 아니라 있던 것을 옮긴 것이다 — 예전 `graph._SNAPSHOT` 이
# 같은 자리에 같은 방식(파일 원문이 캐시 키)으로 있었다. 요청마다 새로 만들면
# 한 요청 안에서 can_connect 가 수천 번 파일을 다시 파싱한다.
#
# **고칠 수 있는 상태가 아니다.** 쓰는 메서드가 없고 캐시 키가 파일 내용이라
# 파일이 바뀌면 다음 호출이 새 내용을 본다.
ONTOLOGY = Ontology()
