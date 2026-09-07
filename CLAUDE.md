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
→ recipe = 순서 있는 온톨로지 노드 목록
→ 온톨로지 관계가 이을 수 있는지 말한다
→ 배선(execution/wiring.yaml)이 노드를 MCP 서버 · 도구 · 인자에 잇는다
→ vendor / Gateway 실행
→ 답 · API · 화면
```

이 길의 이음매가 계약이다. **깨면 안 된다.**

```
1  LLM 은 MCP 도구 순서를 만들지 않는다. recipe 를 고른다
2  recipe 는 노드만 적는다. 서버 · 도구 · 인자를 안 가진다
3  온톨로지 관계와 실행 배선을 가른다.
   온톨로지에 도구 이름을 적으면 노드가 특정 MCP 서버에 묶이고,
   menu 가 온톨로지에서 만들어지므로 도구 이름이 프롬프트로 샌다
4  resolve 는 고르기만 한다. 실행 문맥으로 후보를 다시 거르지 않는다
5  실행 전제(배선이 있나 · 인자가 있나 · 화면 문맥이 왔나)는 실행이 본다
6  문맥이 없다고 다른 recipe 로 갈아타지 않는다. 안 부르고 그렇다고 말한다
7  화면이 가짜 선택 문맥을 지어내지 않는다
```

`dev/tests/test_architecture_contract.py` 가 1 · 2 와 계층 규칙을 지킨다.
나머지는 각 subsystem 의 시험이 본다 (`dev/tests/orchestrator/` ·
`dev/tests/execution/`).

---

## 폴더가 말하는 여섯 갈래

```
도메인      오래 남는다
  ontology/          온톨로지 도메인. store.py 가 yaml 을 아는 유일한 파일
  orchestrator/      발화 해석
  execution/         실행 배선. wiring.yaml 이 여기 있다
  llm_engine/        LLM provider (ollama · vllm)
  workflows/static/  recipe · menu · prompt

서비스      안 사라진다
  app/api/           창구 — 라우팅 + services
  app/ui/            화면 — Streamlit

그리기
  app/ui/graph/      온톨로지 → 좌표. UI 를 위해 있는 것이라 ui 밑이다.
                     그래프DB 로 가면 갈릴 자리다
  app/ui/components/network.py
                     화면 그래프. interactive graph library
                     (pyvis · vis-network)가 그린다. 좌표는 위에서 온다

등록
  registration/      한 폴더로 모았다. 나중에 다른 저장소로 나간다.
                     도메인과 같은 규칙을 진다 — app/ 을 모듈 수준에서 부르지
                     않는다. 창구(/nodes)와 화면(node_form)은 app/ 에 남는다

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

노드에는 `name` 과 `description` 만 있다. `kind` · `inputs` · `outputs` 같은
필드가 없다 — **노드는 그저 존재하고, 성격은 관계가 말한다.**

관계는 넷뿐이다. edge 필드는 `from` · `to` · `predicate` (RDF 삼항).

| 관계 | 뜻 | 읽는 곳 |
|---|---|---|
| `is-a` | A는 B의 한 종류다 | 경로 생성의 타입 매칭 |
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

`workflows/static/recipes/` 의 번호는 **다시 안 매긴다.** 밀리면 정답표
기대값과 시험이 함께 움직이고, 다른 가지에서 recipe 를 다시 붙일 때 어긋난다.

★ **비어 있는 번호를 새 기능이 차지하지 않는다.** 그 자리는 지운 recipe 를
되살릴 곳이라, 새 기능이 들어가면 되살릴 때 어긋난다.
**새 기능은 지금 있는 가장 큰 번호 다음에 이어 붙인다.**

무엇을 언제 왜 지웠는지와 되살리는 법은 `NOTES.md` 에 있다.

★ **recipe 하나를 되살리면 넷이 함께 움직인다** — `recipes/` 와
`_init/recipes/` 의 파일, 그리고 두 `menu.yaml` · 두 `menu.md` 의 해당 줄.
**그리고 menu 문장과 정답표 발화를 함께 만들어야 한다.** recipe 만 되살리면
menu 에는 실리는데 자에는 없는 상태가 된다. 정답표는
`dev/tools/check_resolve.py` 의 `UTTERANCES` 이고, 발화를 더하면 묶음
경계(`BASELINE_LAST` · `EXTENSION_LAST`)도 함께 센다.

---

## active 와 `_init`

작업본과 초기화 원본이 짝으로 있다. **뜻이 다르다.**

```
작업본                          _init 사본
ontology/ontology.yaml          ontology/_init/ontology.yaml
workflows/static/recipes/       workflows/static/_init/recipes/
workflows/static/menu/          workflows/static/_init/menu/
app/ui/graph/layout.json        app/ui/graph/_init/layout.json   (작업본은 .gitignore)
```

- 노드를 등록하면 **작업본만** 바뀐다. `_init` 은 되돌릴 곳이라 안 건드린다
- 화면의 초기화(`registration.registry.reset_to_init`)가 `_init` 을 작업본으로
  복사한다. 좌표까지 함께 되돌린다 — 안 되돌리면 시연을 두 번 할 때 두 번째가
  첫 배치가 아니다
- `_init` 을 코드가 자동으로 다시 만들지 않는다. 재생성하면 등록된 노드가 섞인
  상태가 원본이 되어 되돌릴 수 없다. 다시 만드는 것은
  `dev/tools/rebuild_init.py` 뿐이고 **기본이 미리보기다**
- `_init/layout.json` 은 추적한다. 사람이 눈으로 골라 확정한 배치라 지우면 그
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
- **노드를 등록해도 기존 노드가 0.0000pt 움직여야 한다** ← 시연의 핵심 장면.

### 렌더

- **Graphviz 는 이제 좌표 계산에만 쓴다.** SVG 를 만들어 화면에 보내던 길은
  없앴다. 화면 그래프는 `app/ui/components/network.py` 가 라이브러리로 그린다.
  아래 DOT 규칙은 여전히 유효하다 — 좌표를 재는 DOT 을 만드는 자리이기 때문이다.
- `st.graphviz_chart` 금지. 브라우저 WASM Graphviz 가 멈춘다.
- **라이브러리에서 물리 시뮬레이션을 켜지 않는다.** 켜면 노드를 등록할 때마다
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
- `ontology/store.py` 는 `paths` 외의 프로젝트 모듈을 import 하지 않는다.
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
모델 고르는 차례   명시한 이름 > 환경변수 LLM_MODEL > models.yaml 의 default
provider          models.yaml 이 모델마다 적는다 (ollama · vllm)
host              기계마다 다르므로 환경변수다 (OLLAMA_HOST · VLLM_HOST)
```

**모델마다 다른 값은 `models.yaml`, 기계마다 다른 값은 `.env` 다.** 측정으로
얻은 값(provider · num_ctx · timeout · reason 길이 상한)은 저장소에 남아야
하고, 어디에 붙는지는 저장소가 알 일이 아니다. `.env.example` 이 후자의 목록이다.

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
아무것도 안 띄우고        check_wiring · rebuild_init(미리보기) · pytest
Gateway 만               check_inputs(캐시 없을 때) · probe_tools · probe_shapes
LLM 만                   check_llm  (창구를 안 지나고 resolve_service 를 직접 부른다)
창구(8000) + LLM         check_resolve · check_demo
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
계기판은 어쩌다 한 번 돌지만 배선표와 발화 목록은 커밋마다 바뀐다.

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
