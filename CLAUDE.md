# 이 저장소에서 작업하는 방식

온톨로지 기반 발화 해석 시스템.

지금의 Streamlit 화면은 **중간 구현을 보고하기 위한 시연용**이다. 실제 서비스는
KRRI_ASAP 화면이 `/chat/stream` 을 부르는 길이다.

측정값 · 실패한 시도 · 날짜별 경과는 이 파일이 아니라 `NOTES.md` 에 있다.
여기는 **지금 지켜야 하는 규칙**만 둔다.

---

## 발화 하나가 지나는 길

```
발화
→ LLM 이 static recipe 를 고른다 (만들지 않는다)
→ recipe = 사람이 받아들인 온톨로지 노드 목록 + 게시된 execution
→ 온톨로지 관계가 이을 수 있는지 말한다
→ 노드의 tool(온톨로지)이 노드를 MCP 서버 · 도구 · 인자에 잇는다
  (agentic_ai 밖의 등록 저장소가 compile 해 게시한다 = Recipe.execution)
→ 요청 중에는 Recipe.execution 에 이번 요청의 값을 채워 KRRI native call_mcp_workflow 로 만든다
  (지금은 legacy 다리가 vendoring 한 KRRI 실행기로 Gateway 실행)
→ 답 · API · 화면
```

이 길의 이음매가 계약이다. **깨면 안 된다.**

```
1  LLM 은 MCP 도구 순서를 만들지 않는다. recipe 를 고른다
2  recipe 의 steps 는 노드만 적는다 (사람이 적은 example 은 둔다). 서버 · 도구 · 인자는
   사람이 안 적는다 — 온톨로지로 compile 해 execution 칸에 게시한다
   (compile · 게시는 등록 저장소가 한다). 요청 중에는 그 칸만 읽고, 없으면 오류다.
   온톨로지로 계획을 다시 만들지 않는다
3  도구 식별과 입력 배선은 온톨로지 노드의 tool 에 둔다. 관계(hasInput)를 대신하지 않는다.
   도구 이름은 tool 칸에만 있다 — name · description · source.description 은 menu
   재료라 거기 적으면 프롬프트로 샌다. 주소 · 포트는 온톨로지에 두지 않는다
4  resolve 는 고르기만 한다. 실행 문맥으로 후보를 다시 거르지 않는다
5  실행 전제(배선이 있나 · 인자가 있나 · 화면 문맥이 왔나)는 실행이 본다
6  문맥이 없다고 다른 recipe 로 갈아타지 않는다. 안 부르고 그렇다고 말한다
7  화면이 가짜 선택 문맥을 지어내지 않는다
```

`dev/tests/test_architecture_contract.py` 가 1 · 2 와 계층 규칙 · 저장소 책임 경계를 지킨다.
나머지는 각 subsystem 의 시험이 본다 (`dev/tests/orchestrator/` ·
`dev/tests/execution/`).

### 실행 계약 — agentic_ai 가 오케스트레이터다

실행의 뜻은 전부 agentic_ai 가 정한다. 어느 recipe · 차례 · step id · 서버 · 도구 ·
칸 이름 · 값의 출처(발화 · 화면 · 부르는 순간 · 앞 단계 · 상수 · 조건) · 앞 단계 응답의
어느 경로를 읽나 · 어느 transform 인가.

```
Recipe.execution    게시된 정적 기호 계획. agentic_ai 안의 semantic IR 이고 요청과 무관하다
                    (등록 저장소가 compile 해 recipe 파일에 게시한다)
materialize         Recipe.execution + spoken · context · runtime -> 완성된 KRRI native
                    call_mcp_workflow (execution/workflow_materializer.materialize)
```

- **Recipe.execution 은 기호로 남긴다.** 받는 쪽은 `s1.point.lon`, raw 경로 `location.0` 은
  내놓는 단계의 `outputs` 에만 있다. transform 은 id 로, 조건 · `runtime.now.*` 는 기호로 남는다.
  execution 과 native workflow 사이에 따로 요청 봉투 계약을 두지 않는다
- **native 표현은 workflow_materializer 만 적는다.** exact server_id · tool, `$s1.location.0` ·
  `$context.…`, 명시한 inputAdapter, 채운 조건 · 시각. KRRI 실행기의 편의 추론(짧은 도구 이름
  정규화 · 자동 bbox · 참조 이름 특례 · web.search 보수)에 기대는 workflow 를 만들지 않는다.
  부를 수 없으면 문장이 아니라 status · missing 을 돌려준다
- **KRRI_ASAP 에 agentic_ai 의 기호 해석기를 넣지 않는다.** 지금은 `execution/legacy_vendor.py`
  가 완성된 workflow 를 vendoring 한 실행기에 그대로 넘긴다. vendor_to_be_deleted 를 import 하는
  제품 코드는 그 파일 하나고, KRRI_ASAP generic_mcp_executor 에 직접 넘기게 되면 사라진다
- **사람에게 보일 문장은 workflow_answer 가 만든다.** 창구(`app/api/main.py`) · materializer ·
  다리는 문장을 만들지 않는다. 답 첫 줄은 판정(성공 · 빈 결과 · 오류)마다 하나다. 노드 ·
  recipe 마다 문장을 두지 않는다 — 실행 계획에 화면 문구를 섞지 않는다

---

## 저장소 책임 경계 — agentic_ai 는 runtime 이다

```
agentic_ai 가 갖는 것        온톨로지 · runtime 자산 읽기 · resolve · workflow materialize ·
                             실행 다리 · 답 · 화면(runtime 관찰)
agentic_ai 가 안 갖는 것     노드 등록 · 후보 recipe 생성 · 받아들인 recipe 게시 ·
                             Recipe.execution compile
```

- 등록 capability 는 agentic_ai 밖의 별도 저장소가 갖는다. **두 저장소 사이의 계약은
  게시된 파일이다.** 게시 자산은 `KRRI_Ontology_Registry/` 짜임새 하나다

  ```
  KRRI_Ontology_Registry/
    ontology/ontology.yaml
    menu/menu.yaml
    recipes/recipe_NNN.yaml      (각 recipe 의 execution 칸 포함)
  ```

  이 폴더에는 게시 자산만 둔다. loader · prompt · schema · 시험 · 도구는 넣지 않는다.
  agentic_ai 코드는 이것을 읽기만 한다
- 그 저장소의 Python 모듈을 import 하지 않는다. 호환 wrapper 도 두지 않는다
- 게시 파일을 어디서 읽을지는 `AGENTIC_ARTIFACT_ROOT` 하나가 정한다(`paths.py`). 비우면 이 저장소의
  `KRRI_Ontology_Registry/` 를 읽고, 적으면 같은 짜임새의 바깥 폴더를 읽는다. 적은 폴더가 없으면
  저장소 안으로 돌아가지 않고 멈춘다. 폴더를 저장소 밖으로 옮겨도 코드는 안 바뀐다
- 게시된 자산을 요청 중에 다시 계획하지 않는다. 블록이 없거나 틀리면 오류다

---

## 폴더가 말하는 다섯 갈래

```
도메인      오래 남는다
  ontology/          온톨로지 도메인. Ontology class 가 게시 자산을 읽는 유일한 자리다.
                     읽기만 한다 — 등록 · 게시는 밖의 저장소 일이라 쓰는 API 가 없다
  orchestrator/      발화 해석
  execution/         요청 중의 실행. workflow_materializer 가 게시된 execution 을 KRRI native
                     workflow 로 만들고, legacy_vendor 는 그것을 vendoring 한 실행기로 부르는
                     임시 다리다
  llm_engine/        LLM 역할(logical model 판 · prompt · response schema) · provider
  workflows/static/  menu 를 프롬프트로 읽는 자리(menu/load.py). 자산은 없다

게시 자산    agentic_ai 는 읽기만 한다
  KRRI_Ontology_Registry/  ontology · menu · recipes. 게시 자산만 있다

서비스      안 사라진다
  app/api/           창구 — 라우팅 + services
  app/ui/            화면 — Streamlit

그리기
  app/ui/graph/      온톨로지 → 좌표. UI 를 위해 있는 것이라 ui 밑이다.
                     그래프DB 로 가면 갈릴 자리다
  app/ui/components/network.py
                     화면 그래프. interactive graph library
                     (pyvis · vis-network)가 그린다. 좌표는 위에서 온다

빌려온 것
  vendor_to_be_deleted/  아래 「저장소 경계」를 본다

재는 것     배포에 안 들어간다
  dev/tools/         계기판
  dev/tests/         시험
```

**서비스를 위해 도메인을 굽히지 않는다.** 화면이 편해지자고 도메인 모양을 바꾸는
제안이 나오면, 그것이 화면 문제인지 도메인 문제인지 먼저 가른다.

---

## 저장소 경계

### KRRI_ASAP

옆 저장소(`KRRI_ASAP`)는 조대표님 것이다. **이 저장소에서 작업할 때 건드리지
않는다.** 고쳐야 하면 그쪽에서 새 브랜치를 판다.

### vendor_to_be_deleted/

`vendor_to_be_deleted/asap/` 은 **한 폴더에 두 주인이 있다.**

```
KRRI_ASAP 원본 다섯   generic_mcp_executor · command_renderer ·
                      mcp_result_inspector · mcp_client · isochrone_geometry
agentic_ai 것 넷      config · schemas_chat · workflow_answer · __init__
```

- 원본 다섯을 **리팩터링하지 않는다.** 원본이 갱신될 때 무엇을 다시 가져와야
  하는지 알 수 있어야 한다. 고친 곳은 `asap/README.md` 에 전부 적혀 있다
- 우리 넷이 여기 있는 까닭은 vendor 가 그것을 import 하기 때문이다.
  `workflow_answer.py` 를 밖으로 옮기는 것은 아직 정해지지 않았다
- 어느 것이 누구 것인지 헷갈리면 `asap/README.md` 의 두 표를 본다

### git push

**`git push` 는 사람이 직접 한다.** 지시받기 전에는 하지 않고, 설정을 고쳐
우회하지 않는다. 로컬 커밋은 괜찮다.

---

## 온톨로지 설계

노드에는 `name` 과 `description` 이 있고, 필요한 노드에만 `source` · `tool` 이 붙는다.
노드 자체에 `kind` · `inputs` · `outputs` 같은 필드가 없다 — **성격은 관계가 말한다.**
(`tool.outputs` 는 타입 선언이 아니라 도구 응답을 읽는 경로다. 무엇을 내놓는지는 `hasOutput` 이 말한다)

```
source   밖(발화 · 화면)에서 곧장 들어오는 자리. from 이 spoken.argument ·
         context.selectedLocation · context.view.bbox 중 하나다.
         source 가 있는 노드가 경로의 시작점이다. 유일한 생성원은 아니다
         (지점 좌표는 화면에서도 오고 장소 좌표 변환도 내놓는다)
         fields 는 화면 값 안에서 semantic 칸을 읽는 경로다 (minLon: "0.0")
tool     id          "<server_id>/<도구>" 논리 식별. 예약 namespace builtin/ · frontend/
         parameters  도구 칸 -> 값. semantic 참조 · {from: spoken.<이름>, default, map} ·
                     {from: context.<경로>} · runtime.now.<date|time> · 조건 · 상수
         outputs     hasOutput 타입 -> raw 응답 안의 경로. value | fields,
                     목록에서 고르면 list + pick: first. MCP 도구에만 둔다
```

**값의 출처를 노드로 만들지 않는다.** 「말한 장소」 · 「찍은 지점」 같은 노드는 타입이
아니라 출처라서 source 가 대신한다. 그런 노드를 is-a 로 매달면 is-a 가 형식 계층이
아니라 출처를 말하게 된다.

**semantic 칸이 raw 값의 어디 있는지는 값을 내놓는 쪽이 적는다.** 앞 도구의 응답은
그 노드의 `tool.outputs`, 화면 값은 semantic 노드의 `source.fields` 다. 받는 노드의
`tool.parameters` 는 semantic 칸(`point.lon`)만 안다. 게시된 Recipe.execution 은 둘을 그대로
담고, `$s1.location.0` 같은 native 참조는 요청 중에 workflow_materializer 가 둘을 이어 적는다.

- **가운데 공통 모양을 만들지 않는다.** 지점 좌표를 늘 `{lon, lat}` 로 바꿔 건네지 않는다
- **적힌 경로가 없는 칸을 이름으로 짐작하지 않는다.** 그 자리는 unwired 다.
  `point.lon` 을 응답의 `lon` 으로 읽으면 vendor 의 이름 특례가 풀어 줄 때만 맞는다
- 뒤 노드가 읽는 타입만 적는다. 아무도 안 받는 hasOutput 까지 적지 않는다

관계는 넷뿐이다. edge 필드는 `from` · `to` · `predicate` (RDF 삼항).

| 관계 | 뜻 | 읽는 곳 |
|---|---|---|
| `is-a` | A는 B의 한 종류다 | 경로 생성의 타입 매칭 (지금 0줄. 읽는 곳은 둔다) |
| `about` | A는 B에 관한 것이다 | 대상 판정 · 말이 안 되는 경로 차단 · 화면 점선 |
| `hasInput` | A는 B를 받는다 | 경로 생성 |
| `hasOutput` | A는 B를 내놓는다 | 경로 생성 · 실행 가능 판정 |

**새 관계를 만들려면 "그것을 읽어서 무엇을 하는가" 에 답할 수 있어야 한다.**
답할 수 없으면 만들지 않는다. 읽는 곳이 없어진 관계는 지운다.

**`is-a` 에 대상 구분을 시키지 않는다.** 그건 `about` 의 일이다.

```
is-a    형식 계층. 여러 구체 타입을 상위로 묶어 범용 노드가 한 줄만 적게 한다
about   대상 판정. 경로가 대상을 넘나드는지 본다
```

`description` 이 발화 매칭의 유일한 근거다 — `menu.yaml` 문장의 재료다.
`name` 은 화면 표시용이다.

---

## recipe 번호

`KRRI_Ontology_Registry/recipes/` 의 번호는 **다시 안 매긴다.** 밀리면 정답표
기대값과 시험이 함께 움직이고, 다른 가지에서 recipe 를 다시 붙일 때 어긋난다.

**recipe 파일이 사람의 판정 결과다.** 온톨로지는 후보를 만들 뿐이고(후보 생성은
등록 저장소의 일이다), 그중 무엇을 서비스에 올릴지는 사람이 정한다. 따로 목록
파일(catalog · whitelist)을 두지 않는다 — 원천이 둘이 된다.
**후보를 한꺼번에 recipe 파일로 쓰지 않는다.** 사람이 지운 경로가 되살아나고 번호가
흔들리고 사람이 쓴 example 이 사라진다.
example 은 온톨로지가 아니라 recipe 파일에 사람이 적는다.

★ **비어 있는 번호를 새 기능이 차지하지 않는다.** 그 자리는 지운 recipe 를
되살릴 곳이라, 새 기능이 들어가면 되살릴 때 어긋난다.
**새 기능은 지금 있는 가장 큰 번호 다음에 이어 붙인다.**

무엇을 언제 왜 지웠는지와 되살리는 법은 `NOTES.md` 에 있다.

★ **recipe 하나를 되살리면 둘이 함께 움직인다** — `KRRI_Ontology_Registry/recipes/` 의
파일(example 까지)과 `KRRI_Ontology_Registry/menu/menu.yaml` 의 해당 줄.
execution 칸은 등록 저장소가 게시한 것을 그대로 받는다. 온톨로지의 tool · source 를
고쳤을 때도 거기서 다시 게시한다. 후보를 받아들이는 것도 거기 일이다.
**그리고 menu 문장과 정답표 발화를 함께 만들어야 한다.** recipe 만 되살리면
menu 에는 실리는데 자에는 없는 상태가 된다. 정답표는
`dev/evaluation/resolve_regression.yaml` 이고, 발화를 더하면 그 발화의 묶음(`group`)도
함께 적는다.

---

## 게시 자산은 한 벌이다

온톨로지 · recipe · menu 는 `KRRI_Ontology_Registry/` 에 한 벌만 있다. **되돌릴 원본(`_init`)
사본을 두지 않는다.** 되돌리기는 git 이 한다. menu 는 `menu.yaml` 하나고 사람이 읽을
사본(`menu.md`)도 두지 않는다 — 두 벌은 어긋난다.

화면 좌표는 게시 자산과 다른 책임이라 짝을 그대로 둔다.

```
app/ui/graph/layout.json        app/ui/graph/_init/layout.json   (작업본은 .gitignore)
```

- `app/ui/graph/_init/layout.json` 은 좌표 작업본이 없는 기계의 첫 배치다
  (`layout_store.ensure_positions` 가 복사한다). 추적한다. 사람이 눈으로 골라 확정한 배치라 지우면 그
  선택이 사라진다. `.gitignore` 패턴에서 앞의 `/app/ui/graph/` 를 빼면 `_init`
  사본까지 함께 무시된다

---

## 절대 깨면 안 되는 것 — 실측으로 얻은 제약

### 배치

- 모든 노드 좌표를 `layout.json` 에 고정하고 `neato -n` 으로 렌더한다.
- **`app/ui/graph/layout.json` 을 지우지 않는다.** 좌표 회전 조건이 임계
  근처라 다시 배치하면 지도가 눕는다.
- 핀이 있는 실행에 `overlap` 금지 — 고정을 무시하고 388~710pt 밀어낸다.
- `inputscale=72` 없으면 좌표 왕복이 깨진다 (delta 14657).
- 좌표 회전은 **최초 배치에만**. 두 번 걸리면 지도가 뒤집힌다.
- **노드가 늘어도 기존 노드가 0.0000pt 움직여야 한다** ← 시연의 핵심 장면.

### 렌더

- **Graphviz 는 이제 좌표 계산에만 쓴다.** SVG 를 만들어 화면에 보내던 길은
  없앴다. 화면 그래프는 `app/ui/components/network.py` 가 라이브러리로 그린다.
  아래 DOT 규칙은 여전히 유효하다 — 좌표를 재는 DOT 을 만드는 자리이기 때문이다.
- `st.graphviz_chart` 금지. 브라우저 WASM Graphviz 가 멈춘다.
- **라이브러리에서 물리 시뮬레이션을 켜지 않는다.** 켜면 노드가 늘 때마다
  지도가 통째로 흔들려 위의 「0.0000pt」가 없어진다. 좌표는 서버의
  `layout.json` 을 그대로 박는다. y 는 뒤집는다 — Graphviz 는 위로,
  vis-network 는 아래로 y 가 커진다.
- 하이라이트는 **평행 엣지 추가가 아니라 기존 엣지의 색·굵기 변경**.
- 순번은 `label` 이 아니라 `xlabel` (label 은 노드를 밀어낸다).
- `constraint=false` 금지.
- **파이썬이 변형을 만들고 JS 는 고르기만 한다.** 변형마다의 엣지 · 노드
  스타일을 파이썬이 미리 만들어 넘기고 JS 는 표 하나를 골라 `DataSet.update` 에
  넘긴다. **스크립트 안에 색 문자열이 없어야 한다.**
- 색의 단일 출처는 `app/ui/graph/dot.py` 의 `COLORS` 다.
- `build_dot` 기본 출력 불변. 새 인자는 키워드 전용 + 기본값이고 키워드 인자
  목록 검사 테스트에 추가한다.
- iframe 높이는 파이썬이 픽셀로 계산해 넘긴다. CSS 로 늘리지 않는다.

### 계층

- 화면(`app/ui/`)에서 `ontology` · `llm_engine` · `paths` import 0건.
- 그리기(`app/ui/graph/`)가 `ontology` 를 직접 읽지 않는다 — 도메인 데이터는
  창구의 `screen_service` 에서만 온다. **`app/` 안에서 온톨로지를 읽는 유일한
  지점이 거기다.**
- `ontology/ontology.py` 는 `paths` 외의 프로젝트 모듈을 import 하지 않는다.
- **온톨로지 도메인에 쓰는 API 를 두지 않는다** (append · save · publish). `AGENTIC_ARTIFACT_ROOT`
  가 공유 Registry 를 가리킨 배포에서 이쪽 코드가 남의 게시 파일을 고칠 수 있으면 안 된다.
- **`yaml.dump` 로 다시 쓰지 않는다** (상단 주석과 들여쓰기가 날아간다).
  텍스트를 이어 붙이거나 마커 앞에 삽입한다.
- 데이터 파일(ontology.yaml · menu · recipe)을 스크립트로 고칠 때는
  `write_text(..., newline="\n")` 을 붙인다. 안 붙이면 Windows 에서 파일
  전체가 CRLF 가 되어 내용 4줄 변경이 900줄 diff 가 된다.

### 화면

- 설명글을 넣지 않는다. 범례 · 힌트 · 인터페이스 이름 · recipe id 전부 없앴다.
  발화 인용문과 오류 메시지만 남긴다.

---

## LLM 배포 계약

```
llm_engine/roles/<역할>/
  <역할>.yaml                 logical model 한 판
                              version · model(provider · name) · inference ·
                              prompt_version · response_schema_version
  prompts/v<N>.yaml           template
  response_schemas/v<N>.yaml  JSON Schema 그대로 (감싸는 칸 없음)
host                          기계마다 다르므로 환경변수다 (OLLAMA_URL · VLLM_URL)
```

**역할 하나가 logical model 하나다.** 물리 모델 · provider · inference · prompt 판 ·
schema 판 중 하나라도 뜻을 갖고 바꾸면 그 역할의 `version` 을 올린다. 새 prompt ·
schema 는 판 번호를 올린 새 파일로 더한다. 경로는 manifest 에 적지 않는다 — 역할
이름과 판 번호가 위치를 정한다. 읽는 곳은 `llm_engine/role_config.py` 하나다.

- **요청이 물리 모델을 갈아 끼우지 않는다.** `/resolve` 에 model 인자가
  없고 환경변수로도 못 바꾼다. 계기판에도 `--model` 이 없다. 다른 모델을 재려면
  manifest 를 고치고 판을 올린다
- **전역 defaults · 모델 목록을 따로 두지 않는다.** 역할마다 필요한 값을 적는다.
  Ollama 역할은 `num_ctx` · `timeout`, vLLM 역할은 `timeout` 만 적는다 (컨텍스트는
  vLLM 서버의 `--max-model-len`)
- **요청마다 역할 설정을 한 번 읽고 그 한 벌을 끝까지 넘긴다.** 캐시하지 않으므로
  서버를 띄운 채 고치면 다음 요청부터 반영된다. 뒤에서 다시 읽으면 한 요청 안에서
  모델과 prompt 가 서로 다른 판이 된다
- 역할끼리 나눠 쓰는 prompt · schema 층은 공유할 요구가 생기기 전까지 만들지 않는다
- provider 의 고정 요청 계약(think · keep_alive · temperature · seed ·
  reasoning_effort · max_tokens · strict)은 역할 설정이 아니라 provider 코드에 있다

**역할마다 다른 값은 `llm_engine/roles/`, 기계마다 다른 값은 `.env` 다.** 측정으로
얻은 값(모델 · provider · num_ctx · timeout · schema 의 길이 상한)은 저장소에 남아야
하고, 어디에 붙는지는 저장소가 알 일이 아니다. `.env.example` 이 후자의 목록이다.

---

## 서비스 주소

주소를 읽는 유일한 곳이 `endpoints.py` 다. 이름에 **누가 누구를 부르는가**가
적혀 있다.

```
OLLAMA_URL         agentic_ai  ->  Ollama
VLLM_URL           agentic_ai  ->  vLLM
ASAP_GATEWAY_URL   agentic_ai  ->  KRRI_ASAP Gateway
AGENTIC_API_URL    화면 · 계기판  ->  agentic_ai API
```

- **기본값을 두지 않는다.** 안 적으면 localhost 로 돌아가지 않고 멈춘다.
  조용히 loopback 을 부르면 서비스를 다른 기계로 나눴을 때 무엇이 안 보이는지
  아무도 못 찾는다. `localhost` · `127.0.0.0/8` · `::1` 은 값으로도 안 받는다
- **부를 때 읽는다.** import 시점에 넷을 다 읽지 않는다 — Ollama 를 안 쓰는
  배포가 `OLLAMA_URL` 이 없다고 통째로 못 뜨면 안 된다
- **주소와 bind 를 섞지 않는다.** 서버가 어느 인터페이스에 귀를 여는가는
  띄우는 명령이 정한다 (`uvicorn … --host 0.0.0.0 --port 8000`). 그래서
  `0.0.0.0` 은 서비스 주소로 안 받고, 앱은 제 bind 주소를 읽지 않는다
- **계기판도 같은 계약을 쓴다.** dev/tools 라고 localhost 대비책을 두지 않는다 —
  배포와 다른 주소를 재면 표를 믿을 수 없다
- 주소를 역할 manifest(`llm_engine/roles/`)에 적지 않는다. 저쪽은 역할마다 다른
  값이고 이쪽은 배포마다 다른 값이다

지금 무엇에 붙는지와 그 서버가 떠 있는지는 재기 전에 이것으로 본다.

```
python dev/tools/check_llm.py --dry-run
```

---

## 서버 · 계기판

```
python -m uvicorn app.api.main:app --reload    창구 (8000)
streamlit run app/ui/main.py                   화면 (8501)
```

계기판이 무엇을 요구하는지는 갈린다. **서버가 필요한 것과 아닌 것을 섞지 않는다.**

```
아무것도 안 띄우고        check_wiring · pytest
Gateway 만               probe_tools · probe_shapes
LLM 만                   check_llm  (창구를 안 지나고 resolve_service 를 직접 부른다)
창구(8000) + LLM         check_resolve · check_demo · dev/evaluation/runner.py
창구 + LLM + Gateway     check_argument  (도구를 실제로 불러 본다)
```

`dev/tools/probe_out/` 과 `dev/tools/sweep_out/` 은 `.gitignore` 다. 기계마다
다른 실측 산출물이라 저장소에 담지 않는다 — **새로 clone 하면 없다.**

---

## 테스트

```
python -m pytest
```

- **제품 명세인 테스트**(`dev/tests/test_architecture_contract.py` ·
  `dev/tests/ontology/` · `dev/tests/orchestrator/` · `dev/tests/execution/` ·
  `dev/tests/llm_engine/`)는 요구사항 문서다. 함수 이름이 요구사항 한 문장이고
  docstring 에 왜 그런지가 있다. 함부로 늘리지 않는다.
- **배치 불변식**은 눈으로 못 보는 것을 본다. 좌표가 3pt 움직인 것은 화면을
  봐도 모른다. 실측으로 얻은 것이라 지우면 다시 못 찾는다.
- **그 밖의 서비스 · 그리기 테스트는 늘리지 않는다.** 계층이 사라져서가 아니라
  구조가 계속 바뀌는 중이라, 회귀를 잡는 게 아니라 변경을 따라다니게 된다.
- 전체 테스트는 **작업을 마칠 때 한 번만** 돌린다. 중간에는 바꾼 부분만.
- **테스트를 일부러 망가뜨려 확인하지 않는다.**
- **서버를 띄워 확인하지 않는다.** 화면 깨짐은 엔드포인트 테스트가 잡는다.

`build_dot` 에 새 인자를 넣을 때만 예외다 — 단위 테스트만 두면 조립부가 인자를
안 넘겨도 통과한다. 두 번 당했다(`group_attrs` · `review_edges`). 그때는
완성된 SVG 를 보는 엔드포인트 테스트를 함께 둔다.

`dev/tools/` 에는 테스트를 두지 않는다. 대신 계기판마다 `_selfcheck()` 를
자기 안에 두고 `dev/tests/tools/test_dashboard_selfchecks.py` 가 그것을 부른다 —
계기판은 어쩌다 한 번 돌지만 온톨로지와 발화 목록은 커밋마다 바뀐다.

---

## 데이터 확인

노드 개수 · menu 크기 · recipe 개수 · 테스트 개수 같은 **실제 데이터 값은
테스트에도 문서에도 박지 않는다.** 요구사항이 바뀌면 함께 바뀌는 값이라 빨간불이
아무것도 알려주지 않고, 문서에 적으면 조용히 낡는다. 확인이 필요하면 그 작업에서
한 번 재서 커밋 메시지에 적는다.

---

## 함수 docstring

**모든 함수가 같은 틀을 쓴다.** 사람이 쓴 명세이므로 틀이 제각각이면 안 된다.

```
"""한 줄 요약. 의문형이나 명사로 끝냄.

입력  시그니처가 다 말하면 생략
출력  판정 함수면 참/거짓의 뜻
규칙  개조식. 조건을 한 줄씩
제약  하면 안 되는 것. 없으면 생략
이력  왜 이렇게 됐는가. 커밋 해시. 없으면 생략
"""
```

- 절 이름을 바꾸거나 새 절을 만들지 않는다. 필요 없으면 생략한다
- 개조식 · 음슴체. "…한다" 대신 "…함"
- 볼드(`**`)와 줄표(`—`)를 쓰지 않는다
- **제약 절만 명령형** — "…하지 않는다".
  음슴체로 쓰면 관찰인지 금지인지 흐려진다
- 이력은 커밋 해시로 가리킨다. "작업 21" 같은 대화 번호는 저장소에 없다

반드시 남길 것
- 실측 숫자 (543x256 · 대비 2.41 · 388~710pt). 다시 못 잰다
- "왜 안 했나" (yaml.dump · overlap · 1노드 recipe).
  없으면 다음에 또 시도한다. 실제로 두 번 당했다
- 되돌린 이력. 코드에 안 남는다

## 테스트 함수는 예외

함수 이름이 요구사항 한 문장이고 docstring 은 "왜 그런지" 다. 입력도 출력도
없으므로 위 틀을 적용하지 않는다. 문체(개조식 · 음슴체 · 볼드/줄표 금지)만 맞춘다.

## 그 밖의 주석

모듈 docstring · 상수 옆 메모 · 코드 사이 주석은 위 틀을 안 따른다.
지금 문체 그대로 둔다. 실측값과 근거를 남기는 것만 지킨다.

---

## 주석

**소스 주석은 그 파일의 로직을 설명한다.** 코드 리뷰에서 읽는 곳이므로 실험
경과를 늘어놓지 않는다.

```
.py         그 값이 무엇인지          "reason 의 길이 상한"
NOTES.md    왜 그 값인지 · 무엇이 안 됐나   측정 · 모델 비교 · 실패한 시도
```

- 상수는 **이름으로 설명한다.** 이름으로 안 되면 한 줄까지. 근거를 옆에 붙이지
  않는다
- "하지 마라" 도 `NOTES.md` 의 「건드리기 전에 읽을 것」 표에 적는다.
  값을 고치려는 사람은 그 표를 먼저 본다
- 변경으로 사실과 어긋나게 된 주석은 반드시 고친다. 낡은 주석을 남기지 않는다
- **없는 파일 · 없는 함수 · 옛 경로를 가리키는 주석을 만들지 않는다.**
  폴더 이름이 갈리면 그것을 가리키던 주석을 함께 고친다
- 소스 주석에 **날짜별 경과 · 옛 benchmark 숫자 · 지운 파일 이름 · "예전에는 …"**
  을 적지 않는다. 그것은 `NOTES.md` 것이다
- **아직 정해지지 않은 정책을 영구 규칙처럼 적지 않는다.** 미정이면 미정이라고
  적는다 (`graph.crosses_groups` 의 ★ 가 그 예다)
- 실측으로 얻은 숫자를 지우지 않는다. `NOTES.md` 는 덧붙이기만 하고, 틀린 것이
  밝혀져도 지우지 말고 아래에 정정을 덧붙인다

---

## 고치기 전에 멈춘다

- 무엇을 왜 고칠지 먼저 말하고 승인을 기다린다. 승인 없이 파일을 고치지 않는다.
- "왜 이런지" 를 물으면 **조사해서 답만 한다.** 고칠 계획을 같이 내밀지 않는다.
- 고칠 것을 제안할 때는 선택지 2~3개와 각각의 대가를 적고, 무엇을 권하는지와 그
  이유를 밝힌다. 완성된 계획 하나를 승인받으려 하지 않는다.
- 갈림길이 아닌 것은 묻지 않는다 — 어느 파일을 읽을지, 어떻게 조사할지 같은 것.

무인 실행 프롬프트를 받았을 때는 이 절이 적용되지 않는다. 그때는 프롬프트의
「무인 실행 규칙」을 따른다.

---

## 커밋

- **먼저 커밋하지 않는다.** 결과를 보고하고 멈춘 뒤, **커밋 메시지 초안을
  채팅에 낸다.** 파일로 만들지 않는다.
- 사람이 화면을 보고 만족하면 "커밋해줘" 라고 말한다. 그때 커밋한다.
- 측정값과 실패한 시도는 **`NOTES.md`** 에 남긴다. 커밋 메시지에는 이번 변경을
  왜 했는지만 적는다 — 파일을 고치는 사람이 `git log` 를 뒤지지는 않는다.
- 메시지에 담을 것 :
  - 제목 한 줄 (50자 안팎, 마침표 없이)
  - 왜 그렇게 했는지. 다른 선택지가 있었으면 왜 그것을 안 골랐는지
  - **범위 밖으로 나간 변경과 그 근거.** 없으면 "범위 밖 변경 없음"
  - 실패한 시도와 거기서 알아낸 사실. 되돌린 코드는 안 남아도 사실은 남아야 한다
  - 측정한 숫자가 있으면 표 그대로. 환경(모델 · 온톨로지 상태)도 함께
  - 테스트 결과 한 줄
- 마칠 때 보고할 것 : `pytest` 결과 · `git status --short`.
