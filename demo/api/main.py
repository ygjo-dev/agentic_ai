"""
Backend FastAPI 진입점.

**라우팅만 둔다.** 도메인 로직은 demo/api/services/ 가, 오류 매핑은 아래
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

# demo/api/main.py -> demo/api -> demo -> 저장소 뿌리.
REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

# 프로젝트 모듈보다 먼저 읽는다. llm_engine 이 import 시점에 OLLAMA_HOST 를
# 읽으므로, 뒤에 읽으면 .env 가 안 먹는다.
load_dotenv(Path(REPO_ROOT) / ".env")

from demo.api.schemas.requests import (
    ChatRequest,
    NodeRegisterRequest,
    RenderRequest,
)
from demo.api.services import (
    execute_service,
    node_service,
    ontology_service,
    render_service,
    resolve_service,
)
from demo.api.services.render_service import UnknownRenderMode
from llm_engine.ollama import make_client
from llm_engine.profiles import profile
from ontology.registry import (
    DuplicateNode,
    InvalidInference,
    UnknownGroup,
    UnknownType,
)
from orchestrator.route_resolver import RouteResolutionError

app = FastAPI(
    title="Recipe Resolver API",
    description="사용자 발화로부터 Recipe 선택",
    version="1.0.0",
)

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


@app.get("/graph")
async def graph_endpoint() -> dict:
    """온톨로지 그래프 한 벌. 프론트엔드가 그리는 데 필요한 것 전부.

    출력  version · colors · types · nodes · solid_edges · dotted_edges
    규칙  version 은 내용 해시라 프론트엔드 캐시 키가 됨
          colors 는 화면이 칩 · 배지 · 안내 문구에 쓸 색.
          색의 출처는 graph_svg 한 곳뿐임
    """
    return ontology_service.graph_payload()


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
    return render_service.render(form.mode, form.recipe_ids, form.mark)


@app.post("/resolve")
async def resolve_endpoint(utterance: str, model: str | None = None) -> dict:
    """사용자 발화로부터 Recipe 선택.

    입력  utterance  사용자 자연어 입력
          model      쓸 LLM 모델 이름. 없으면 기본 모델
    출력  status(SELECT / CLARIFY / NO_MATCH) · recipe_id ·
          candidate_recipe_ids · reason · paths
          LLM 이 쓴 축 셋(given · want · about)과 발화에서 뽑은 argument,
          그 축으로 뽑은 shortlist_recipe_ids 도 함께 담김. 화면은 안 그림.
          브라우저에서 응답을 열었을 때 왜 그 후보가 남았는지 보이면 됨
          paths 는 후보별 실행 경로. NO_MATCH 면 비어 있음
    규칙  model 은 측정용임. 같은 발화를 모델만 바꿔 재는 데 서버를 다시
          띄우지 않으려는 것. 화면은 이 인자를 쓰지 않음
    """
    return resolve_service.resolve(
        utterance,
        llm_client=make_client(model),
        reason_max_length=profile(model).reason_max_length,
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
    제약  동기 for 로 돌지 않는다.
          vendor 실행기가 코루틴이라 흐름 전체가 async generator 임
    """
    return execute_service.chat(
        form.text,
        llm_client=make_client(model),
        reason_max_length=profile(model).reason_max_length,
        context=form.context,
    )


@app.post("/chat")
async def chat_endpoint(form: ChatRequest) -> dict:
    """KRRI_ASAP 이 부르는 ASAP-orchestrator 자리를 대신 받음.

    입력  form  text · sessionId · context · target_documents
    출력  answer 와 commands. commands 는 vendor 가 결과에서 만든 지도 명령임
    규칙  발화를 해석해 recipe 를 고르고 그 노드 순서를 steps 로 바꿔
          vendor 실행기에 넘김. 부른 순서가 answer 에 그대로 적힘
          /chat/stream 과 같은 흐름을 씀. 중간 이벤트를 버리고 마지막
          result 만 돌려줄 뿐임
    제약  form 의 target_documents 를 해석하지 않는다. 아직 쓰는 곳이 없다.
          context 는 읽지 않고 vendor 참조 범위($context.…)로 넘기기만 함
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


@app.post("/nodes/reset")
async def reset_nodes_endpoint() -> dict:
    """_init 사본으로 되돌림. 등록한 노드와 recipe 가 모두 사라짐."""
    return node_service.reset()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "demo.api.main:app",
        host=os.environ.get("API_HOST", "0.0.0.0"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload=True,
    )
