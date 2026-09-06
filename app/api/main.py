"""Backend FastAPI 진입점.

**라우팅만 둔다.** 도메인 로직은 app/api/services/ 가, 오류 매핑은 아래
미들웨어가 맡는다. 엔드포인트마다 같은 try/except 를 반복하면 한 곳을 고칠 때
나머지를 빠뜨리게 된다.
"""

import json
import logging
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
from llm_engine.llm_selector import get_llm
from llm_engine.model_config import get_model_config
from registration.registry import (
    DuplicateNode,
    InvalidInference,
    UnknownGroup,
    UnknownType,
)
from execution import execute_service
from orchestrator import resolve_service
from orchestrator.resolve_service import RouteResolutionError

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Recipe Resolver API",
    description="사용자 발화로부터 Recipe 선택",
    version="1.0.0",
)

# 지나간 회차를 기억하려고 두 자리를 감싼다. **값을 안 바꾸는 껍데기다.**
#
# 후보와 인자는 resolve 안에만 있고 실제로 부른 recipe 는 run 안에만 있다.
# 둘 다 이벤트로는 안 나온다. 씌우는 자리를 여기 한 곳에 두고, --reload 로
# 모듈을 다시 읽어도 두 번 씌우지 않는다.
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

# 예상 못 한 오류에서 client 로 나가는 문구. 원인은 서버 로그에만 남는다.
#
# **원문을 실어 보내지 않는다.** vendor 예외에는 Gateway 응답 본문 · 내부 URL
# (http://localhost:3000/api/tools/execute) · 저장소 경로가 그대로 들어 있고,
# 이 응답은 KRRI_ASAP 시스템까지 나간다.
INTERNAL_ERROR_DETAIL = "서버 내부 오류입니다. 서버 로그를 확인하세요."


@app.middleware("http")
async def errors_to_json(request: Request, call_next):
    """오류 매핑을 한 곳에 모음. 엔드포인트는 라우팅만 함.

    출력  DOMAIN_ERRORS 는 422, 나머지는 500
    규칙  NAMED_ERROR_PATHS 만 detail 에 예외 이름을 남김
          500 의 detail 은 고정 문구임. 실제 예외와 traceback 은 서버 로그로 감
    제약  예상 못 한 예외의 원문을 응답에 담지 않는다.
          내부 URL · vendor HTTP 원문 · 저장소 경로가 그대로 실려 나감
          @app.exception_handler 로 옮기지 않는다.
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
    except Exception:  # noqa: BLE001 — 예상 못 한 것은 전부 500 이다.
        logger.exception("처리하지 못한 오류: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content={"detail": INTERNAL_ERROR_DETAIL}
        )


@app.get("/screen")
async def screen_endpoint() -> dict:
    """화면이 그리기 전에 받아 두는 것. 고를 수 있는 타입과 색.

    출력  colors  칩 · 배지 · 안내 문구 · 그래프에 쓸 색. 출처는
                  app/ui/graph/dot.py 한 곳뿐임
          types   등록 폼의 입출력 선택지
    """
    return screen_service.screen_payload()


@app.post("/render")
async def render_endpoint(form: RenderRequest) -> dict:
    """화면 한 장에 필요한 그래프 모형과 칩 데이터.

    출력  version  온톨로지 내용 해시
          chips    칩에 적을 이름 사슬. 후보 차례 그대로
          network  vis-network 가 받는 노드 · 엣지 · 좌표 · 변형별 스타일
    규칙  모든 변형이 같은 좌표를 씀. 좌표는 layout.json 에 고정돼 있어
          어느 후보를 강조하든 안 흔들림
          그림을 만들지 않음. 그리는 것은 화면의 라이브러리임
    """
    return screen_service.render(form.mode, form.recipe_ids, form.mark)


@app.post("/resolve")
async def resolve_endpoint(utterance: str, model: str | None = None) -> dict:
    """사용자 발화로부터 Recipe 선택.

    출력  status(SELECT / CLARIFY / NO_MATCH) · recipe_id ·
          candidate_recipe_ids · reason · paths · argument
          paths 는 후보별 실행 경로. NO_MATCH 면 비어 있음
    규칙  고르는 것은 LLM 뿐임. 지도 문맥을 안 받음 — 문맥이 필요한지는 실행
          직전에 보고, 실행은 /chat/stream 이 함
          model 은 측정용임. 같은 발화를 모델만 바꿔 재는 데 서버를 다시
          띄우지 않으려는 것. 화면은 이 인자를 쓰지 않음
    """
    return resolve_service.resolve(
        utterance,
        llm_client=get_llm(model),
        reason_max_length=get_model_config(model).reason_max_length,
    )


@app.post("/nodes")
async def register_node_endpoint(
    form: NodeRegisterRequest, model: str | None = None
) -> dict:
    """노드 등록. 온톨로지 · recipe · menu 가 함께 갱신됨.

    출력  새로 생긴 것. node_id · node · groups · reason · recipe_ids ·
          new_solid_edges · new_dotted_edges
    제약  대상이 어긋나는 경로를 등록하지 않는다.
          화각이 안 맞는 것(궤도 검측차 영상으로 승강장 승객을 보는 식)은
          recipe 가 되지 않고 응답에도 안 담김
          버린 경로를 응답에 담지 않는다.
          화면이 쓰지 않는 키를 만들지 않음
    """
    return node_service.register(form.model_dump(), llm_client=get_llm(model))


def _chat_events(form: ChatRequest, model: str | None = None):
    """발화 한 건의 이벤트 흐름. /chat/stream 이 이것을 씀.

    출력  비동기 이벤트 흐름. 마지막은 반드시 type=result
    규칙  흐름이 끝나면 그 회차를 recent_service 가 기억함. GET /recent 로
          Streamlit 이 물어가 따라 그림
    제약  동기 for 로 돌지 않는다.
          vendor 실행기가 코루틴이라 흐름 전체가 async generator 임
          기록 때문에 이벤트를 바꾸지 않는다.
          watched 는 받은 것을 그대로 다시 내는 껍데기임. KRRI_ASAP 시스템이
          읽는 흐름이라 한 건이라도 모양이 달라지면 시연이 깨짐
    """
    return recent_service.watched(
        form.text,
        execute_service.chat(
            form.text,
            llm_client=get_llm(model),
            reason_max_length=get_model_config(model).reason_max_length,
            context=form.context,
        ),
    )


@app.post("/chat/stream")
async def chat_stream_endpoint(form: ChatRequest) -> StreamingResponse:
    """발화 한 건의 답을 SSE 로 흘려보냄. **KRRI_ASAP 시스템이 부르는 유일한 창구다.**

    출력  text/event-stream. step_start · step_end · result · [DONE] 순서
    규칙  step_start 와 step_end 가 recipe 의 실행 단계마다 한 쌍씩 나감.
          해석(resolve)도 한 단계로 나감. 부르는 화면이 진행 상황을 그림
          이벤트마다 빈 줄을 하나 붙임. SSE 는 빈 줄이 있어야 한 건이 끝남
    제약  ensure_ascii 를 켜지 않는다. 켜면 한글이 유니코드 이스케이프로
          나가 받는 화면에서 읽히지 않는다
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
    출력  seq(지금 번호) · turns(그 번호보다 큰 회차들). 회차 한 건에 언제 ·
          발화 · status · 인자 · 고른 recipe 와 후보들 · 단계 줄 · 답 문구
    규칙  번호가 그대로면 turns 가 빈 목록임. 화면은 그때 아무것도 다시 안 그림
    제약  아무것도 바꾸지 않는다. 읽기 전용임
          raw JSON 을 담지 않는다.
          commands 를 아예 안 읽음. geojson 과 좌표 배열이 거기 있음
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
