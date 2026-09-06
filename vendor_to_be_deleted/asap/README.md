# vendor_to_be_deleted/asap

KRRI_ASAP 의 ASAP-orchestrator 에서 가져온 MCP 실행기다.

**이 폴더 전체가 KRRI_ASAP 원본인 것은 아니다.** 아래 「가져온 파일」 다섯만
원본이고, 「우리가 새로 만든 파일」 넷은 agentic_ai 코드다. 그중
`workflow_answer.py` 는 원본에 대응하는 파일이 없는 우리 것이고, 지금 답 문구를
만드는 자리다 — 옮길 자리가 정해지면 vendor 밖으로 나간다.

원본 다섯은 리팩터링하지 않는다. 원본이 갱신되면 무엇을 다시 가져와야 하는지
알 수 있어야 한다.

## 출처

```
저장소   https://github.com/jscho-esnt/KRRI_ASAP
커밋     311187ea2ba041f748f7c5a6ed7233942f55315f
         "Update architecture and orchestrator integration docs" (2026-08-20)
경로     ASAP-orchestrator/app/
가져온 날 2026-08-20
```

## 가져온 파일

| 여기 | 원본 | 줄 |
|---|---|---|
| `generic_mcp_executor.py` | `app/core/generic_mcp_executor.py` | 1241 |
| `command_renderer.py` | `app/core/command_renderer.py` | 470 |
| `mcp_result_inspector.py` | `app/core/mcp_result_inspector.py` | 529 |
| `mcp_client.py` | `app/core/mcp_client.py` | 141 |
| `isochrone_geometry.py` | `app/core/isochrone_geometry.py` | 692 |

`isochrone_geometry.py` 는 목록에 없었지만 `mcp_result_inspector` 가
`validate_and_repair_isochrone_polygons` 를 부른다. 프로젝트 모듈을 하나도
import 하지 않는 잎이라 그대로 가져왔다.

`app/core/__init__.py` 는 가져오지 않았다. `app.config` 를 다시 export 할 뿐이라
여기서는 의미가 없다.

원본은 CRLF 였다. 저장소가 `* text=auto eol=lf` 라 LF 로 바꿔 두었다.
내용 비교는 `git diff --ignore-cr-at-eol` 이 아니라 줄바꿈을 맞춘 뒤에 한다.

## 우리가 새로 만든 파일 — 원본에 없다

| 파일 | 무엇 |
|---|---|
| `config.py` | 원본 `app/config.py` 자리. vendor 가 읽는 다섯 값만 둠 |
| `schemas_chat.py` | 원본 `app/schemas/chat.py` 의 `Command` 만 옮김 |
| `workflow_answer.py` | **agentic_ai 코드다.** Gemini 로 답을 다듬던 자리를 대신함. 성공·빈 결과·오류 판정도 여기서 함 |
| `__init__.py` | 패키지 표시 |

## 고친 곳 — 이것 말고는 한 줄도 안 고쳤다

### 1. import 경로

```
from app.config import settings              → from vendor_to_be_deleted.asap.config import settings
from app.core.command_renderer import …      → from vendor_to_be_deleted.asap.command_renderer import …
from app.core.mcp_result_inspector import …  → from vendor_to_be_deleted.asap.mcp_result_inspector import …
from app.core.mcp_client import …            → from vendor_to_be_deleted.asap.mcp_client import …
from app.core.isochrone_geometry import …    → from vendor_to_be_deleted.asap.isochrone_geometry import …
from app.schemas.chat import Command         → from vendor_to_be_deleted.asap.schemas_chat import Command
from app.core.logging import get_logger      → from logging import getLogger as get_logger
```

`app.core.logging` 은 `logging.basicConfig` 를 부르고 `getLogger` 를 그대로
돌려주는 11줄짜리다. 우리 진입점이 로깅을 따로 잡으므로 표준 것을 바로 쓴다.

### 2. `from google import genai` 삭제 — `generic_mcp_executor.py`

우리는 Gemini 키를 쓰지 않기로 했다. genai 를 부르는 곳은 둘이었다.

```
_compose_answer           도구를 하나만 부르는 경로(execute_generic_mcp)의 것
_compose_workflow_answer  아래 3번으로 통째로 대체됨
```

앞엣것은 통째로 지웠다. 직접 도구 호출 길(`execute_generic_mcp`)을 안 쓰기로
정하면서 그 길의 함수 열다섯을 함께 걷었고 `_compose_answer` 가 그중 하나다.
`config.py` 의 `GEMINI_API_KEY` · `GEMINI_MODEL` 두 칸도 읽는 데가 없어져
함께 사라졌다.

**원본이 갱신되면 그 열다섯이 병합 충돌로 돌아온다.** 그때 다시 지운다 —
무엇을 왜 지웠는지가 이 절이다.

### 3. `_compose_workflow_answer` 대체 — `generic_mcp_executor.py`

원본은 Gemini 로 trace 를 한국어 문장으로 다듬고, 키가 없으면 trace JSON 을
통째로 덤프했다. 우리는 **호출 순서가 그대로 보여야 한다** — 지금 증명하려는
것이 "온톨로지가 실행 순서를 정한다" 이기 때문이다. LLM 이 다시 쓰면 순서가
문장에 녹아 사라지고, JSON 덤프는 사람이 읽을 것이 못 된다.

본문은 `workflow_answer.compose_workflow_answer(intent, trace)` 한 줄이 되었다.
성공한 실행의 첫 줄은 `intent["answer_instruction"]` 을 그대로 쓴다 — 우리 쪽
`execution/wiring.yaml` 의 `tool_of` 가 노드마다 적어 넣는다.

원본 `_fallback_workflow_answer` 는 지우지 않았다. 다른 곳에서 쓰이지 않지만
지우면 병합할 것이 늘어난다.

**`compose_workflow_answer` 를 부르는 자리는 둘이다.** 여기가 하나이고, 우리 쪽
`execution/execute_service.run` 이 또 하나다. vendor 는 실패하면
`_failed_workflow_result` 로 **여기까지 오지 않고** 자기 문구를 `answer_draft` 에
담아 돌아간다. 그 문구가 사용자 화면에 나가면 안 되는 것을 담고 있어(실측 :
HTTP 오류 문장 · `http://localhost:3000/api/tools/execute` · Gateway 응답 본문
원문) `execute_service` 가 `executed["errors"]` 를 보고 같은 함수를 trace 로 다시
부른다. 문구를 두 벌 쓰지 않으려는 것이다.

`compose_workflow_answer` 가 성공/실패를 스스로 가르는 이유도 여기 있다.
Gateway 는 실패를 `200` + `{"error": {...}}` 로도 돌려주고(실물 :
`asap_probe_out/geo.geocode.english_notfound.json`), `mcp_client` 가 예외를 안
올리므로 vendor 는 그것을 성공한 호출로 보고 `answer_draft` 에 성공 문구를 적는다.
`errors` 만 보고서는 못 가른다.

### 4. `config.py` 의 두 값이 원본 기본값과 다르다

| 값 | 원본 | 여기 | 왜 |
|---|---|---|---|
| `MCP_TIMEOUT` | 60.0 | 120.0 | `/api/tools` 42개에 21.1초(실측). 20초로는 모자랐다 |
| `MCP_TOOLS_CACHE_TTL` | 30.0 | 600.0 | 목록 한 번에 21초라 30초 캐시는 발화마다 다시 받는다 |

## 이 코드가 무엇을 해주는가

```
steps 배열                     우리가 만든다 (step_service)
  ↓
_resolve_reference             $s1.location · $s1.minLon 을 이름으로 찾아냄.
                               lon/lng/longitude 동의어, bbox 네 귀퉁이,
                               [lon, lat] 배열 인덱싱까지 도구별이 아니라
                               필드 이름별이라 도구가 늘어도 그대로다
_apply_input_adapter           중심 좌표 + radiusMeters 를 bbox 로. 위도
                               보정(cos)까지 한다. 대상 도구의 required 에
                               bbox 넷이 있으면 저절로 걸린다
mcp_client.execute_tool        Gateway 호출
inspect_mcp_trace              결과에서 지도에 그릴 것을 골라냄
build_commands_from_artifacts  → commands
```

## 다시 가져올 때

1. 위 다섯 파일을 원본에서 다시 복사한다
2. CRLF → LF
3. 「고친 곳」의 1~3 을 다시 적용한다
4. `config.py` · `schemas_chat.py` · `workflow_answer.py` 는 우리 것이니 두고,
   원본의 `app/config.py` 에서 vendor 가 읽는 이름이 늘지 않았는지만 본다
