# 프로젝트 규칙

온톨로지 기반으로 사용자 발화를 실행 경로(Recipe)로 해석하는 데모 저장소다.
Backend(FastAPI) + Frontend(Streamlit) + Ollama.

## 절대 깨지 말 것 — 실측으로 검증된 제약

`frontend/components/graph_section.py` 주석에 시행착오가 기록되어 있다. 아래는 그 요약이다.
이 중 하나라도 어기면 과거에 겪은 회귀가 그대로 재발한다.

1. **`st.graphviz_chart` 금지.** DOT을 브라우저로 보내면 WASM Graphviz가 레이아웃을 끝내지 못하고
   조용히 멈춘다. 서버에서 네이티브 `dot`으로 SVG를 완성해 보낸다.
2. **하이라이트는 평행 엣지 추가가 아니라 기존 엣지의 색·굵기 변경.**
   엣지 수가 조합마다 달라지면 레이아웃이 흔들린다 (실측: 543x256 → 543x293).
3. **순번은 `label`이 아니라 `xlabel`.** `label`은 Graphviz가 공간을 확보해 노드를 밀어낸다.
4. **점선에 `constraint=false` 금지.** 랭크 제약 없는 엣지가 늘면 렌더러가 레이아웃을 끝내지 못한다.
5. **`build_dot()`의 시그니처와 인자 타입을 바꾸지 않는다.**
   `solid`는 `{(from, to): interface}`, `dotted`는 `{(a, b): [labels]}` 형태의 dict.
   `tests/graph_rendering/`의 40여 개 테스트가 이 시그니처에 의존한다.
   JSON 직렬화가 필요하면 경계에 어댑터를 두고 시그니처는 건드리지 않는다.

## 계층 규칙

- **`frontend/`는 그리기와 입력 UI만 한다.**
  `ontology` / `registry` / `llm_engine` / `paths` import 금지. 모든 도메인 조회·변경은 백엔드 API 경유.
- **`backend/services/graph_service.py`가 온톨로지 저장소와 맞닿는 유일한 지점이다.**
  지금은 `ontology/graph.py`가 YAML을 읽지만, 나중에 그래프 DB로 바뀌면 여기만 교체한다.
  API 계약과 프론트엔드는 그대로여야 한다.
- `backend/main.py`는 라우팅과 오류 매핑만. 도메인 로직을 두지 않는다.

## 도메인 코드는 옮기지도 고치지도 않는다

다음은 안정화된 코드다. 명시적 지시 없이 수정하지 않는다.

```
ontology/graph.py, ontology/registry.py, ontology/ontology.yaml, ontology/_init/
orchestrator/
llm_engine/
workflows/
paths.py
```

## 작업 방식

- 작업 시작과 종료 시 `python -m pytest tests -q`. **green이 아니면 커밋하지 않는다.**
- 기존 테스트를 통과시키려고 테스트를 고치지 않는다. 계약을 바꿔야 하면 먼저 이유를 보고한다.
- 노드 등록 관련 테스트는 실제 YAML 파일을 쓴다. 반드시 격리하거나 `reset_to_init()`으로 되돌린다.
  저장소가 더러워진 채 남으면 안 된다.
- 커밋 메시지는 한국어 서술형. `feat:` `fix:` 같은 접두사를 쓰지 않는다.
  예) `프론트엔드에서 온톨로지 계산과 LLM 호출 제거, 백엔드 API 로 이관`

## 코드 스타일

- 주석과 docstring은 한국어. 기존 파일의 톤(왜 그렇게 했는지를 적는 방식)을 따른다.
- 노드 라벨에 한글이 있으므로 파일 입출력은 항상 `encoding="utf-8"`, 개행은 `newline="\n"`.