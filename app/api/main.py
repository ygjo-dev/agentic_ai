"""
Backend FastAPI 진입점.

**라우팅만 둔다.** 도메인 로직은 app/api/services/ 가, 오류 매핑은 아래
예외 핸들러가 맡는다. 엔드포인트마다 같은 try/except 를 반복하면 한 곳을
고칠 때 나머지를 빠뜨리게 된다.

(향후 타 샌드박스와의 소켓/HTTP 통신을 추가 예정).
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# app/api/main.py -> app/api -> app -> 저장소 뿌리.
REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

# 프로젝트 모듈보다 먼저 읽는다. llm_engine 이 import 시점에 OLLAMA_HOST 를
# 읽으므로, 뒤에 읽으면 .env 가 안 먹는다.
load_dotenv(Path(REPO_ROOT) / ".env")

from app.api.schemas.requests import (
    ChatRequest,
    NodeRegisterRequest,
    RenderRequest,
)
from app.api.services.bridge import recent_service
from app.api.services.streamlit import node_service, screen_service
from app.api.services.streamlit.screen_service import UnknownRenderMode
from llm_engine.ollama import make_client
from llm_engine.profiles import profile
from registration.registry import (
    DuplicateNode,
    InvalidInference,
    UnknownGroup,
    UnknownType,
)
from execution import execute_service
from orchestrator import resolve_service
from orchestrator.route_resolver import RouteResolutionError

app = FastAPI(
    title="Recipe Resolver API",
    description="사용자 발화로부터 Recipe 선택",
    version="1.0.0",
)

# 지나간 회차를 기억하려고 두 자리를 감싼다. **값을 안 바꾸는 껍데기다.**
#
# 저쪽 화면이 넣은 발화의 축 셋과 후보는 resolve 안에만 있고, 되묻기 뒤에
# 고른 회차의 recipe 는 run 안에만 있다. 둘 다 이벤트로는 안 나온다.
# 씌우는 자리를 여기 한 곳에 둔다 — 감싸는 쪽이 여럿이면 두 번 씌워진다.
#
# --reload 로 모듈을 다시 읽어도 두 번 씌우지 않는다.
if not hasattr(resolve_service.resolve, "__wrapped__"):
    resolve_service.resolve = recent_service.watch_resolve(resolve_service.resolve)
if not hasattr(execute_service.run, "__wrapped__"):
    execute_service.run = recent_service.watch_run(execute_service.run)

# 422 로 내보낼 예외. "요청이 잘못됐거나 LLM 이 계약을 어겼다" 는 뜻이고,
# 서버가 고장난 것이 아니다.
#
# 맨 ValueError 로 뭉뚱그리지 않는다. 그러면 코드 어딘가의 진짜 버그
# (int("x") 같은 것)까지 422 로 나가 "요청이 잘못됐다" 로 읽힌다.
DOMAIN_ERRORS = (
    RouteResolutionError,
    DuplicateNode,
    UnknownType,
    UnknownGroup,
    InvalidInference,
    UnknownRenderMode,
)

# 이 경로만 예외 이름을 detail 에 남긴다.
NAMED_ERROR_PATHS = ("/nodes",)


@app.middleware("http")
async def errors_to_json(request: Request, call_next):
    """오류 매핑을 한 곳에 모음. 엔드포인트는 라우팅만 함.

    출력  DOMAIN_ERRORS 는 422, 나머지는 500
    규칙  NAMED_ERROR_PATHS 만 detail 에 예외 이름을 남김
    제약  @app.exception_handler 로 옮기지 않는다.
          잡히지 않은 예외를 핸들러로 다루면 Starlette 의
          ServerErrorMiddleware 가 응답을 낸 뒤 예외를 다시 올림.
          라우트 안에서 잡아 500 을 만들던 것과 동작이 갈림.
          여기서 잡으면 응답 하나로 끝남
    """
    try:
        return await call_next(request)
    except DOMAIN_ERRORS as exc:
        # 등록 경로만 예외 이름을 남긴다. 화면이 원인을 그대로 보여주는데
        # "이미 있는 노드다" 만으로는 무엇이 잘못됐는지 안 읽힌다.
        named = request.url.path in NAMED_ERROR_PATHS
        detail = f"{type(exc).__name__}: {exc}" if named else str(exc)
        return JSONResponse(status_code=422, content={"detail": detail})
    except Exception as exc:  # noqa: BLE001 — 예상 못 한 것은 전부 500 이다.
        # 원문을 그대로 남긴다. 시연 중에 원인을 못 찾으면 끝이다.
        return JSONResponse(
            status_code=500, content={"detail": f"Internal error: {str(exc)}"}
        )


@app.get("/screen")
async def screen_endpoint() -> dict:
    """화면이 그리기 전에 받아 두는 것. 고를 수 있는 타입과 색.

    출력  version · colors · types · nodes · solid_edges · dotted_edges
    규칙  version 은 내용 해시라 프론트엔드 캐시 키가 됨
          colors 는 화면이 칩 · 배지 · 안내 문구에 쓸 색.
          색의 출처는 graph_svg 한 곳뿐임
          지금 화면이 실제로 읽는 것은 types 와 colors 둘뿐임.
          나머지 셋은 서버가 그리게 된 뒤로 아무도 안 읽음
    """
    return screen_service.screen_payload()


@app.post("/render")
async def render_endpoint(form: RenderRequest) -> dict:
    """화면 한 장에 필요한 SVG 와 칩 데이터.

    출력  top      상단 그래프
          variants 하단 변형들
          focus    클릭 가능한 끝노드
          chips    칩에 적을 이름 사슬
    규칙  variants 의 모든 SVG 는 노드 좌표와 캔버스 크기가 같음.
          좌표를 전부 고정하고 neato -n 으로 그리기 때문. 그래야 노드를 눌러
          좁혀도 화면이 안 흔들림
          같은 요청은 서버가 캐시함. 키에 온톨로지 version 과 좌표 해시가
          들어가 노드를 등록하면 저절로 빗나감
    """
    return screen_service.render(form.mode, form.recipe_ids, form.mark)


@app.post("/resolve")
async def resolve_endpoint(
    utterance: str,
    model: str | None = None,
    context: dict | None = None,
) -> dict:
    """사용자 발화로부터 Recipe 선택.

    입력  utterance  사용자 자연어 입력
          model      쓸 LLM 모델 이름. 없으면 기본 모델
          context    화면의 지도 문맥. **요청 본문이다** (나머지 둘은 query).
                     /chat 의 ChatRequest.context 와 같은 모양이고 같은 자리로
                     흐름 — view.bbox · selectedLocation. **없으면 없는 것으로.**
                     안 보내면 이 인자를 만들기 전과 한 글자도 다르지 않음
    출력  status(SELECT / CLARIFY / NO_MATCH) · recipe_id ·
          candidate_recipe_ids · reason · paths
          발화에서 뽑은 argument 도 함께 담김. 화면은 안 그림.
          문맥 거르개 전에 LLM 이 쓴 날것은 llm_recipe_id ·
          llm_candidate_recipe_ids 에 따로 담김. candidate_recipe_ids 쪽은
          값이 안 온 시작 데이터를 뺀 값이라 둘이 다를 수 있음.
          브라우저에서 응답을 열었을 때 왜 그 후보가 남았는지 보이면 됨
          paths 는 후보별 실행 경로. NO_MATCH 면 비어 있음
    규칙  model 은 측정용임. 같은 발화를 모델만 바꿔 재는 데 서버를 다시
          띄우지 않으려는 것. 화면은 이 인자를 쓰지 않음
    """
    return resolve_service.resolve(
        utterance,
        llm_client=make_client(model),
        reason_max_length=profile(model).reason_max_length,
        context=context,
    )


@app.post("/nodes")
async def register_node_endpoint(
    form: NodeRegisterRequest, model: str | None = None
) -> dict:
    """노드 등록. 온톨로지 · recipe · menu 가 함께 갱신됨.

    입력  form   노드 폼
          model  쓸 LLM 모델 이름. 없으면 기본 모델. /resolve 와 같은 뜻
    출력  새로 생긴 것(node_id · node · recipe_ids · paths · accepted ·
          new_solid_edges · new_dotted_edges) · 등록 전후 개수(counts) ·
          갱신된 version
    제약  대상이 어긋나는 경로를 등록하지 않는다.
          화각이 안 맞는 것(궤도 검측차 영상으로 승강장 승객을 보는 식)은
          recipe 가 되지 않고 응답에도 안 담김
          버린 경로를 응답에 담지 않는다.
          화면이 쓰지 않는 키를 만들지 않음
    """
    return node_service.register(form.model_dump(), llm_client=make_client(model))


def _chat_events(form: ChatRequest, model: str | None = None):
    """발화 한 건의 이벤트 흐름. /chat 과 /chat/stream 이 같은 것을 씀.

    입력  요청 본문 · 쓸 LLM 모델 이름(없으면 기본 모델)
    출력  비동기 이벤트 흐름. 마지막은 반드시 type=result
    규칙  두 경로가 다른 답을 하면 화면과 curl 중 무엇을 믿을지가 갈림
          흐름이 끝나면 그 회차를 recent_service 가 기억함. GET /recent 로
          Streamlit 이 물어가 따라 그림
    제약  동기 for 로 돌지 않는다.
          vendor 실행기가 코루틴이라 흐름 전체가 async generator 임
          기록 때문에 이벤트를 바꾸지 않는다.
          watched 는 받은 것을 그대로 다시 내는 껍데기임. 저쪽 화면이 읽는
          흐름이라 한 건이라도 모양이 달라지면 시연이 깨짐
    """
    return recent_service.watched(
        form.text,
        execute_service.chat(
            form.text,
            llm_client=make_client(model),
            reason_max_length=profile(model).reason_max_length,
            context=form.context,
        ),
    )


@app.post("/chat")
async def chat_endpoint(form: ChatRequest) -> dict:
    """KRRI_ASAP 이 부르는 ASAP-orchestrator 자리를 대신 받음.

    입력  form  text · context (sessionId · target_documents 는 안 읽음)
    출력  answer 와 commands. commands 는 vendor 가 결과에서 만든 지도 명령임
    규칙  발화를 해석해 recipe 를 고르고 그 노드 순서를 steps 로 바꿔
          vendor 실행기에 넘김. 부른 순서가 answer 에 그대로 적힘
          /chat/stream 과 같은 흐름을 씀. 중간 이벤트를 버리고 마지막
          result 만 돌려줄 뿐임
    제약  form 의 target_documents 를 해석하지 않는다. 아직 쓰는 곳이 없다.
          context 는 읽지 않고 vendor 참조 범위($context.…)로 넘기기만 함
          sessionId 는 받기만 하고 안 읽는다. 2026-09-01 에 세션을 걷었다
    """
    last = {"answer": "", "commands": []}
    async for payload in _chat_events(form):
        if payload["type"] == "result":
            last = {"answer": payload["answer"], "commands": payload["commands"]}
    return last


@app.post("/chat/stream")
async def chat_stream_endpoint(form: ChatRequest) -> StreamingResponse:
    """/chat 과 같은 답을 SSE 로 흘려보냄. 저쪽 화면이 부르는 것은 이쪽임.

    입력  form  /chat 과 같은 ChatRequest
    출력  text/event-stream. step_start · step_end · result · [DONE] 순서
    규칙  step_start 와 step_end 가 recipe 의 실행 단계마다 한 쌍씩 나감.
          해석(resolve)도 한 단계로 나감. 저쪽 화면이 진행 상황을 그림
          answer 는 /chat 과 같음. 두 경로가 다른 답을 하면 화면과 curl 중
          무엇을 믿을지가 갈림
          이벤트마다 빈 줄을 하나 붙임. SSE 는 빈 줄이 있어야 한 건이 끝남
    제약  ensure_ascii 를 켜지 않는다. 켜면 한글이 유니코드 이스케이프로
          나가 저쪽 화면에서 읽히지 않는다
    """

    def event(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def stream():
        async for payload in _chat_events(form):
            yield event(payload)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/recent")
async def recent_endpoint(since: int | None = None) -> dict:
    """지나간 회차. Streamlit 이 주기적으로 물어가 따라 그림.

    입력  since  마지막으로 본 회차 번호. 없으면 마지막 몇 회차
    출력  seq(지금 번호) · turns(그 번호보다 큰 회차들)
          회차 한 건에 언제 · 발화 · status · 축 셋 · 인자 · 고른 recipe 와
          후보들 · 단계 줄 · 답 문구가 담김
    규칙  번호가 그대로면 turns 가 빈 목록임. 화면은 그때 아무것도 다시 안 그림
          저쪽 화면이 `POST /chat/stream` 으로 넣은 회차가 여기 그대로 나옴.
          저쪽은 아무것도 안 바꿈
    제약  아무것도 바꾸지 않는다. 읽기 전용임
          raw JSON 을 담지 않는다.
          commands 를 아예 안 읽는다. geojson 과 좌표 배열이 거기 있음
    """
    return recent_service.since(since)


@app.post("/nodes/reset")
async def reset_nodes_endpoint() -> dict:
    """_init 사본으로 되돌림. 등록한 노드와 recipe 가 모두 사라짐."""
    return node_service.reset()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.api.main:app",
        host=os.environ.get("API_HOST", "0.0.0.0"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload=True,
    )
