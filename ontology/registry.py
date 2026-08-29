"""노드 등록. 온톨로지 · recipe · menu 를 갱신.

온톨로지 읽기와 쓰기는 store 에게 맡긴다. 이 파일은 ontology.yaml 을 직접
열지 않는다 — 저장소가 그래프DB 로 바뀌어도 등록 규칙은 그대로여야 한다.
recipe 와 menu 는 아직 store 가 맡는 자산이 아니라 여기서 직접 쓴다.
"""

import re
import shutil

import paths
from ontology import graph, store
from ontology.graph import ABOUT, HAS_INPUT, HAS_OUTPUT
from orchestrator.route_resolver import resolve_route


def group_ids() -> list[str]:
    """지금 있는 대상(그룹) 노드 id.

    출력  노드 id 목록. LLM 이 고를 수 있는 선택지 전부
    규칙  파일에 종류가 안 적혀 있으므로 관계로 판정.
          about 의 대상으로 등장하는 노드가 그룹임
    """
    return graph.group_ids()


def functions(nodes: dict) -> dict:
    """실행할 수 있는 노드만.

    입력  {노드 id: 노드} 전체
    출력  같은 형태. 실행 노드만 남음
    규칙  hasOutput 이 있으면 실행할 수 있음
          데이터 노드와 그룹 노드는 안 들어옴
    """
    return {nid: node for nid, node in nodes.items() if graph.is_executable(nid)}


class DuplicateNode(ValueError):
    """이미 있는 노드 id 다."""


class UnknownType(ValueError):
    """온톨로지에 없는 타입 노드다."""


class UnknownGroup(ValueError):
    """온톨로지에 없는 대상(그룹) 노드 id 다."""


def add_node(node_id: str, node: dict, path=None) -> None:
    """온톨로지에 노드를 추가.

    입력  노드 id · 노드 dict · 온톨로지 경로(없으면 기본)
    규칙  여기서 보는 것은 중복뿐. 이미 있으면 DuplicateNode
          관계는 붙이지 않음. 무엇을 받고 내놓는지는 노드가 아니라 관계라
          register_node() 가 edge 로 따로 붙임
    """
    ontology = store.read(path)

    if node_id in ontology["nodes"]:
        raise DuplicateNode(f"이미 있는 노드다: {node_id}")

    store.append_node(node_id, node, path)


def check_types(type_ids, path=None) -> None:
    """받고 내놓는 타입이 실재하는지.

    입력  타입 id 목록 · 온톨로지 경로(없으면 기본)
    규칙  온톨로지에 없는 id 가 있으면 UnknownType. 파일을 건드리기 전에 막음
    제약  없는 타입을 가리키는 노드를 만들지 않는다.
          아무와도 이어지지 않아 화면에는 떠 있는데 경로가 하나도 안 생김
    """
    known = set(store.nodes(path))
    for type_id in type_ids:
        if type_id not in known:
            raise UnknownType(
                f"온톨로지에 없는 타입이다: {type_id}\n"
                f"  쓸 수 있는 것 : {sorted(known)}"
            )


# LLM 응답 구조(json). node_id 형식은 코드에서 다시 검증한다.
NODE_REGISTRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "node_id": {"type": "string"},
        # 관한 대상(그룹) 노드 id 들. **여러 개 고를 수 있다** — 승강장 CCTV
        # 영상이 승강장에도 CCTV 에도 관한 것처럼. 어느 대상에도 매이지
        # 않으면 빈 목록.
        "groups": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["node_id", "groups", "reason"],
}

NODE_ID_PATTERN = re.compile(r"^[a-z]+(_[a-z]+)*$")


class InvalidInference(ValueError):
    """LLM 이 쓸 수 없는 값을 돌려줬다."""


def infer_node(form: dict, llm_client, path=None) -> dict:
    """사람이 쓴 노드 정보를 보고 LLM 이 node_id 와 관한 대상들을 정함.

    입력  노드 폼 · LLM 클라이언트 · 온톨로지 경로(없으면 기본)
    출력  node_id · groups · reason. groups 는 중복 제거됨.
          같은 대상을 두 번 적으면 점선이 두 줄 생김
    규칙  대상은 닫힌 목록에서 고름. 존재하는 그룹 노드 id 들
          여럿 고를 수 있음. 한 노드가 여러 대상에 관한 것일 수 있음
          예 : 승강장 CCTV 영상은 승강장에 관한 것이자 CCTV 에 관한 것임
          빈 목록 허용. 어느 대상에도 안 매인 범용 노드(형식만 바꾸는 생성
          노드 등)가 그렇고, 억지로 고르는 것보다 나음
          InvalidInference      형식에 맞지 않거나 쓸 수 없는 값을 돌려줌
          RouteResolutionError  응답이 JSON 이 아니거나 필수 key 가 없음
    제약  대상을 자유 문자열로 받지 않는다.
          예전 subject 값이 그랬는데 "궤도" 대신 "선로" 라고 쓰면 아무와도
          안 이어졌음
    """
    nodes = store.nodes(path)
    choices = group_ids()

    result = resolve_route(
        prompt=paths.NODE_REGISTRATION_PROMPT_PATH.read_text(encoding="utf-8"),
        variables={
            "existing_nodes": _describe(nodes, _group_of(store.edges(path))),
            "new_node": _describe_form(form),
            "groups": _describe_groups(nodes, choices),
        },
        response_schema=NODE_REGISTRATION_SCHEMA,
        llm_client=llm_client,
    )

    node_id = result["node_id"]
    if not isinstance(node_id, str) or not NODE_ID_PATTERN.match(node_id):
        raise InvalidInference(
            f"노드 id 형식이 맞지 않다: {node_id!r}\n"
            "  소문자 영문과 언더스코어만 쓴다."
        )
    if node_id in nodes:
        raise InvalidInference(f"이미 있는 노드 id 다: {node_id}")

    groups = result["groups"]
    if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
        raise InvalidInference(f"groups 는 문자열 목록이어야 한다: {groups!r}")

    # 빈 목록은 "어느 대상에도 관한 것이 아니다" 는 뜻이라 허용한다.
    unknown = [g for g in groups if g not in choices]
    if unknown:
        raise InvalidInference(
            f"온톨로지에 없는 대상이다: {unknown}\n"
            f"  고를 수 있는 것 : {choices}"
        )

    # 같은 대상을 두 번 적으면 점선이 두 줄 생긴다.
    result["groups"] = list(dict.fromkeys(groups))
    return result


def _group_of(edges: list[dict]) -> dict[str, list[str]]:
    """노드 -> 관한 대상 id 들. 프롬프트에 보여줄 용도. 여럿일 수 있음."""
    found: dict[str, list[str]] = {}
    for edge in edges:
        if edge.get("predicate") == ABOUT:
            found.setdefault(edge["from"], []).append(edge["to"])
    return found


def _describe(nodes: dict, belongs: dict[str, list[str]]) -> str:
    """기존 기능 노드를 프롬프트에 넣을 형태로.

    입력  노드 전체 · {노드: 관한 대상 목록}
    출력  여러 줄 문자열
    규칙  무엇에 관한 것인지가 핵심이라 반드시 넣음. LLM 이 비슷한 노드를
          보고 고름
    제약  그룹 노드 자체를 여기 넣지 않는다.
          선택지는 _describe_groups 가 따로 보여줌
    """
    lines = []
    for node_id, node in functions(nodes).items():
        lines.append(
            f"- {node_id}\n"
            f"    이름 : {node['name']}\n"
            f"    설명 : {node['description']}\n"
            f"    입력 : {graph.inputs_of(node_id) or '없음'}"
            f" -> 출력 : {graph.outputs_of(node_id)}\n"
            f"    관한 대상 : {', '.join(belongs.get(node_id, [])) or '(없음)'}"
        )
    return "\n".join(lines)


def _describe_groups(nodes: dict, choices: list[str]) -> str:
    """고를 수 있는 group 목록.

    입력  노드 전체 · 고를 수 있는 그룹 id 목록
    출력  여러 줄 문자열. id 와 이름을 함께 담음
    규칙  id 만 보여주면 LLM 이 뜻을 모르고, 이름만 보여주면 무엇을 적어야
          할지 모름. 적어야 하는 것은 id
    """
    return "\n".join(
        f"- {group_id}  ({nodes[group_id]['name']} — {nodes[group_id]['description']})"
        for group_id in choices
    )


def _describe_form(form: dict) -> str:
    return (
        f"    이름 : {form['name']}\n"
        f"    설명 : {form['description']}\n"
        f"    입력 : {form['inputs'] or '없음'} -> 출력 : {form['outputs']}"
    )


# 경로 한 개의 최대 노드 수. **데이터 노드가 한 칸을 차지한다** — 예전에는
# 불러오기 · 분석 · 생성 세 기능이 3칸이었는데, 이제 데이터 · 추출 · 분석 · 생성
# 이 4칸이다. 그래서 3 -> 4 다.
#
# 5 로 올리면 안 된다. 등록 한 번에 경로가 44~52개 생기고 menu 가 5764~6923자가
# 되어 MENU_BUDGET(6000자)을 **한 번의 등록으로 넘긴다**. 4 에서는 14~20개 ·
# 2299~2772자다. menu 가 커지면 LLM context 를 넘겨 타임아웃한다.
#
#   MAX_STEPS   경로 수      등록 후 menu
#         3      4~ 8        1193~1514자
#         4     14~20        2299~2772자   <- 여기
#         5     44~52        5764~6923자   <- 예산 초과
#
# **임시방편이다.** 경로 길이가 문제인 것이 아니라 말이 안 되는 조합이 섞이는
# 것이 문제이고, 그것은 about 차단(crosses_groups)이 푼다. 온톨로지가 촘촘해지고
# 범용 노드가 줄면 이 상수는 의미가 없어진다.
MAX_STEPS = 4


def all_recipes(nodes: dict) -> list[list[str]]:
    """온톨로지 전체의 경로 후보.

    입력  노드 전체
    출력  노드 id 목록의 목록. 길이 2 이상 MAX_STEPS 이하. 파일은 안 씀
    규칙  데이터 노드에서 출발해 can_connect 로 이어 붙임.
          규칙은 ontology/graph.py 의 solid_edges 와 같음. 앞 노드가 건네는
          것을 뒤 노드가 받을 수 있으면 이어짐
          순서가 결정적. 짧은 것부터(BFS), 같은 길이 안에서는 start_ids 와
          nodes 의 순서를 따르고 그것은 ontology.yaml 에 적힌 순서임.
          같은 온톨로지로 두 번 돌리면 같은 번호가 나오고
          tools/rebuild_init.py 가 그것에 기댐
    제약  대상(about)이 어긋나는 것을 여기서 거르지 않는다.
          거르는 것은 부르는 쪽의 일임(register_node · tools/rebuild_init.py).
          그래야 "무엇이 만들어질 수 있는가" 와 "무엇을 남길 것인가" 가 갈림.
          여기서 함께 걸러 버리면 등록이 무엇을 버렸는지 셀 수 없어짐
          길이 1 을 만들지 않는다.
          "승강장 CCTV 영상" 하나도 그 자체로 건넬 수 있는 것은 맞지만,
          recipe 로 삼으려면 start_ids 와 function_for 의 "데이터만 있는 경로"
          분기를 건드려야 함. 지금은 안 함
    """
    # 그룹을 여기서 따로 거르지 않는다. **거를 필요가 없다** — 그룹은
    # hasInput 이 없어 `can_connect` 가 누구 뒤에도 세우지 않고, `start_ids` 도
    # 그룹을 빼므로 첫 칸에도 못 온다. 관계가 이미 막고 있는 것을 여기서 또
    # 막으면 진짜로 막는 곳이 어디인지 흐려진다.
    #
    # (예전에는 노드에 kind 가 적혀 있어서 그것을 보고 걸렀다. 지금은 성격이
    #  관계에서 나오므로 관계가 그대로 규칙이 된다.)
    usable = list(nodes)

    # 시작점은 **손에 잡히는 구체적인 데이터**다. 승강장 CCTV 영상처럼 그
    # 자체로 존재하는 것이 경로의 첫 단계가 된다. "영상" 같은 형식은 시작점이
    # 될 수 없다 — 어느 영상인지 아무 데도 안 적혀 실행할 수 없다.
    starts = [nid for nid in graph.start_ids() if nid in usable]

    chains = [[start] for start in starts]
    found = []
    for _ in range(MAX_STEPS):
        found += [chain for chain in chains if len(chain) >= 2]
        chains = [
            [*chain, nxt]
            for chain in chains
            if len(chain) < MAX_STEPS
            for nxt in usable
            # can_connect 가 is-a 를 타고 올라가 매칭한다 — 프레임 추출이
            # "영상" 만 받아도 승강장 CCTV 영상을 받는다.
            if nxt not in chain and graph.can_connect(chain[-1], nxt)
        ]

    return found


def new_recipes_for(node_id: str, nodes: dict) -> list[list[str]]:
    """새 노드를 지나는 경로만.

    입력  새 노드 id · 노드 전체
    출력  노드 id 목록의 목록. 파일은 안 씀
    규칙  기존 노드끼리의 조합은 이미 recipe 로 있어 다시 만들면 중복
          경로 자체는 all_recipes 가 만듦
    제약  등록용 경로 생성을 따로 만들지 않는다.
          등록으로 생기는 recipe 와 _init 의 recipe 가 같은 함수에서 나와야 함.
          규칙이 두 벌이 되면 menu 문장이 미묘하게 갈리고, 그 문장이 발화
          매칭의 유일한 근거라 "초기 recipe 는 되는데 등록한 건 안 되는"
          상황이 나옴
    """
    if node_id not in nodes or node_id in set(group_ids()):
        return []

    return [chain for chain in all_recipes(nodes) if node_id in chain]


def append_recipes(chains: list[list[str]], nodes: dict, directory=None) -> list[str]:
    """경로를 recipe 파일로 씀.

    입력  경로 목록 · 노드 전체 · 쓸 디렉터리(없으면 기본)
    출력  만들어진 recipe id 목록
    규칙  가장 큰 번호 다음부터 이어 붙임
    제약  기존 번호를 건드리지 않는다.
          menu 와 frontend 의 SAMPLES 가 그 번호를 가리키고 있음
    """
    directory = directory or paths.RECIPES_DIR

    last = max(
        (int(path.stem.split("_")[1]) for path in directory.glob("recipe_*.yaml")),
        default=0,
    )

    created = []
    for offset, chain in enumerate(chains, start=1):
        recipe_id = f"recipe_{last + offset:03d}"
        body = "steps:\n\n" + "\n\n".join(_step_block(nodes[n], n) for n in chain) + "\n"
        (directory / f"{recipe_id}.yaml").write_text(body, encoding="utf-8", newline="\n")
        created.append(recipe_id)

    return created


def _step_block(node: dict, node_id: str) -> str:
    """recipe 파일의 step 한 덩어리.

    출력  "  - node: <id>" 한 줄
    제약  무엇을 주고받는지 여기 적지 않는다.
          온톨로지의 hasInput / hasOutput 이 말하므로 또 적으면 진실의 원천이
          둘이 됨. 노드를 고쳤을 때 recipe 파일이 옛 값을 들고 있으면 어느
          쪽이 맞는지 알 수 없음
    """
    return f"  - node: {node_id}"


# menu.yaml 크기 상한. 넘으면 models.yaml 의 num_ctx 를 넘겨 LLM 이 타임아웃한다.
# tests/context_loading 의 상한과 같은 값이다.
# 프로덕션에서 부르는 곳은 없다. 등록 뒤 menu 가 이 선을 넘지 않는지
# tests/node_registration/test_append_menu.py 가 보는 기준값이라 남긴다.
MENU_BUDGET = 6000


def _to_connective(sentence: str) -> str:
    """종결형을 연결형으로.

    입력  description 한 문장
    출력  이어 붙일 수 있는 형태. "분석한다" -> "분석하고", "찾는다" -> "찾고"
    규칙  어미 둘만 다룸. 지금 description 이 그 둘로 끝남
            ~는다  자음 어간. "는" 을 통째로 떼고 "고" 를 붙임 (찾는다 -> 찾고)
            ~ㄴ다  하다 계열. 종성 ㄴ 을 떼고 "고" 를 붙임 (분석한다 -> 분석하고)
    제약  한국어 활용을 다 다루지 않는다.
          ㄹ 불규칙("만든다" 는 "만들고" 인데 이 규칙으로는 "만드고" 가 된다)은
          처리 못 함. 그래서 description 을 쓸 때 "생성한다" 처럼 하다 계열이나
          "찾는다" 처럼 는다 계열로 끝맺음. 이 제약은 tests 가 지킴
    """
    if not sentence.endswith("다") or len(sentence) < 2:
        return sentence + "하고"

    if sentence.endswith("는다"):
        return sentence[:-2] + "고"

    stem_end = sentence[-2]
    code = ord(stem_end) - 0xAC00
    if 0 <= code < 11172 and code % 28:  # 종성이 있는 한글 음절
        stem_end = chr(ord(stem_end) - code % 28)  # 종성 제거 : 한 -> 하

    return sentence[:-2] + stem_end + "고"


def _with_particle(name: str) -> str:
    """"~으로" 인가 "~로" 인가.

    입력  노드 이름
    출력  조사가 붙은 이름
    규칙  받침 있음        으로
          받침 없음 · ㄹ   로
          한글이 아니면(영문 · 숫자) 안전하게 "으로"
          "궤도 점검 보고서으로" 처럼 어긋나면 시연 중에 사람이 먼저 알아챔
    """
    last = name.strip()[-1]
    code = ord(last) - 0xAC00
    if not 0 <= code < 11172:  # 한글이 아니면(영문·숫자) 안전하게 "으로"
        return name + "으로"

    final = code % 28
    return name + ("로" if final in (0, 8) else "으로")  # 0 = 받침 없음, 8 = ㄹ


def function_for(chain: list[str], nodes: dict) -> str:
    """recipe 가 하는 일 한 문장.

    입력  경로(노드 id 목록) · 노드 전체
    출력  마침표로 끝나는 한 문장. LLM 이 recipe 를 고르는 유일한 근거
    규칙  경로는 데이터 노드에서 시작함
          데이터는 이름에 조사를 붙여 앞에 두고, 기능들의 description 만
          이어 붙임. 마지막만 종결형이고 앞은 모두 연결형
          예 : 승강장 CCTV 영상으로 영상에서 분석용 이미지 프레임을 추출하고
               이미지에서 승강장의 혼잡한 정도를 분석한다.
    제약  데이터의 description 을 연결형으로 바꾸지 않는다.
          명사구라("승강장에 설치된 CCTV 가 촬영한 영상") 붙이면 "영상하고"
          가 됨
          데이터 이름을 빼지 않는다.
          같은 기능을 쓰는 recipe 가 무엇으로 시작하는지 구분할 근거가 사라져
          LLM 이 고를 수 없음. 승강장 CCTV 로 시작하는 것과 검측차 영상으로
          시작하는 것이 같은 문장이 됨
    """
    steps = [nid for nid in chain if graph.is_executable(nid)]
    sources = [nid for nid in chain if nid not in steps]

    prefix = " ".join(_with_particle(nodes[nid]["name"]) for nid in sources)
    descriptions = [nodes[nid]["description"].rstrip(".") for nid in steps]

    if not descriptions:
        # 데이터만 있는 경로. 실행할 것이 없으니 이름만 남긴다.
        return " ".join(nodes[nid]["name"] for nid in sources) + "."

    # 마지막만 종결형으로 두고 앞은 모두 연결형으로 잇는다.
    clauses = [_to_connective(text) for text in descriptions[:-1]]
    body = " ".join([*clauses, descriptions[-1]])

    return (f"{prefix} {body}" if prefix else body) + "."


def append_menu(
    recipe_ids: list[str],
    chains: list[list[str]],
    nodes: dict,
    yaml_path=None,
    md_path=None,
) -> None:
    """menu.yaml 과 menu.md 에 새 recipe 를 추가.

    입력  recipe id 목록 · 경로 목록 · 노드 전체 · 두 파일 경로(없으면 기본)
    규칙  yaml 은 끝에 블록을 이어 붙임
          md 는 목차 표 끝에 행을 넣고 본문 섹션은 문서 끝에 붙임
    제약  기존 항목을 다시 쓰지 않는다. 텍스트째로 두고 뒤에 이어 붙임.
          function 문장이 한 글자라도 바뀌면 이미 검증한 발화들이 다른
          recipe 로 갈 수 있음
    """
    yaml_path = yaml_path or paths.MENU_YAML_PATH
    md_path = md_path or paths.MENU_MD_PATH

    functions = {
        recipe_id: function_for(chain, nodes)
        for recipe_id, chain in zip(recipe_ids, chains)
    }

    # ---------------------------------------------------------- menu.yaml
    blocks = [
        f"  {recipe_id}:\n    function: {sentence}\n"
        for recipe_id, sentence in functions.items()
    ]
    yaml_path.write_text(
        yaml_path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + "\n".join(blocks),
        encoding="utf-8",
        newline="\n",
    )

    # ---------------------------------------------------------- menu.md
    # 목차 표 끝에 행을 넣고, 본문 섹션은 문서 끝에 붙인다.
    md = md_path.read_text(encoding="utf-8")
    rows = "".join(
        f"| {recipe_id} | {sentence} |\n" for recipe_id, sentence in functions.items()
    )
    marker = "\n\n---\n\n# Recipe "
    head, sep, tail = md.partition(marker)
    md = head.rstrip("\n") + "\n" + rows.rstrip("\n") + sep + tail

    sections = "".join(
        f"\n\n---\n\n# Recipe {recipe_id.split('_')[1]}\n\n## 기능\n\n{sentence}"
        for recipe_id, sentence in functions.items()
    )
    md_path.write_text(md.rstrip("\n") + sections + "\n", encoding="utf-8", newline="\n")


def register_node(form: dict, llm_client) -> dict:
    """노드 등록 전체. 한 번에 끝남.

    입력  노드 폼 · LLM 클라이언트
    출력  inferred(node_id · groups · reason) + node · recipe_ids · chains
    규칙  LLM 판단 -> 온톨로지 -> 경로 생성 -> recipe · menu
          앞 단계가 실패하면 뒤는 실행되지 않음. 온톨로지에 못 넣은 노드로
          recipe 를 만들면 존재하지 않는 노드를 가리킴
          관계는 노드를 쓴 뒤에 이음. 순서가 바뀌면 아직 없는 노드를 가리키는
          edge 가 파일에 남음
          crosses_groups 가 참인 경로는 파일이 되지 않고 응답에도 안 담김.
          예 : 궤도 검측차 영상으로 승강장 승객의 위험 행동을 찾는 경로.
               화각이 안 맞아 실행할 수 없음
    제약  버린 경로를 돌려주지 않는다. 화면이 안 쓰는 키를 만들지 않음
    이력  f9bbda1 이전 그런 경로를 화면에 올려 사람이 승인하게 했음
          (propose/approve). 관문이 시연 화면의 절반을 먹었고, 걸러지는 것이
          전부 진짜 쓰레기라 사람이 건질 조합이 하나도 없었음
          사람이 검토하는 절차는 이 화면이 아닌 곳에 제대로 들어감.
          그때 crosses_groups 가 차단에서 분류로 돌아감
    """
    inferred = infer_node(form, llm_client=llm_client)
    node_id = inferred["node_id"]

    check_types([*form["inputs"], *form["outputs"]])

    node = {"name": form["name"], "description": form["description"]}
    add_node(node_id, node)

    for type_id in form["inputs"]:
        store.append_edge(node_id, type_id, HAS_INPUT)
    for type_id in form["outputs"]:
        store.append_edge(node_id, type_id, HAS_OUTPUT)
    for group in inferred["groups"]:
        store.append_edge(node_id, group, ABOUT)

    nodes = store.nodes()
    chains = [
        chain
        for chain in new_recipes_for(node_id, nodes)
        if not graph.crosses_groups(chain)
    ]

    recipe_ids = append_recipes(chains, nodes)
    if recipe_ids:
        append_menu(recipe_ids, chains, nodes)

    return {
        **inferred,
        "node": node,
        "recipe_ids": recipe_ids,
        "chains": chains,
    }


def reset_to_init() -> None:
    """_init 사본을 작업 파일로 되돌림.

    규칙  등록으로 늘어난 recipe 도 사라져야 하므로 디렉터리를 통째로 갈아끼움
          노드 좌표도 함께 되돌림. 안 되돌리면 등록한 노드가 사라진 뒤에도
          그 좌표가 남아, 시연을 두 번 하면 두 번째가 첫 배치가 아님
    제약  _init 사본 자체를 건드리지 않는다. 망가지면 되돌릴 곳이 없음
          좌표를 위에서 import 하지 않는다.
          좌표는 그리기(demo/)의 자산이고 핵심이 시연 계층을 의존하면 안 됨.
          여기서 함수 안에 두면 demo/ 가 사라질 때 이 줄만 조용히 건너뜀
    """
    store.restore_from_init()
    shutil.copy2(paths.INIT_MENU_YAML_PATH, paths.MENU_YAML_PATH)
    shutil.copy2(paths.INIT_MENU_MD_PATH, paths.MENU_MD_PATH)

    if paths.RECIPES_DIR.exists():
        shutil.rmtree(paths.RECIPES_DIR)
    shutil.copytree(paths.INIT_RECIPES_DIR, paths.RECIPES_DIR)

    try:
        from demo.graph_svg import layout_store
    except ImportError:  # 시연 계층이 없는 설치
        return
    layout_store.restore_from_init()
