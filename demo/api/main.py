"""
Backend FastAPI 진입점.

**라우팅만 둔다.** 도메인 로직은 demo/api/services/ 가, 오류 매핑은 아래
예외 핸들러가 맡는다. 엔드포인트마다 같은 try/except 를 반복하면 한 곳을
고칠 때 나머지를 빠뜨리게 된다.

(향후 타 샌드박스와의 소켓/HTTP 통신을 추가 예정).
"""

import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# demo/api/main.py -> demo/api -> demo -> 저장소 뿌리.
REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from demo.api.schemas.requests import NodeRegisterRequest, RenderRequest
from demo.api.services import (
    node_service,
    ontology_service,
    render_service,
    resolve_service,
)
from demo.api.services.render_service import UnknownRenderMode
from llm_engine import ollama
from llm_engine.ollama import OllamaClient
from ontology.registry import (
    DuplicateNode,
    InvalidInference,
    UnknownGroup,
    UnknownInterface,
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
    UnknownInterface,
    UnknownGroup,
    InvalidInference,
    UnknownRenderMode,
)

# 이 경로만 예외 이름을 detail 에 남긴다.
NAMED_ERROR_PATHS = ("/nodes",)


@app.middleware("http")
async def errors_to_json(request: Request, call_next):
    """오류 매핑을 한 곳에 모은다. 엔드포인트는 라우팅만 한다.

    핸들러(@app.exception_handler)가 아니라 미들웨어인 이유 : 잡히지 않은
    예외를 핸들러로 다루면 Starlette 의 ServerErrorMiddleware 가 응답을 낸 뒤
    예외를 다시 올린다. 그러면 예전처럼 라우트 안에서 잡아 500 을 만들던 것과
    동작이 갈린다. 여기서 잡으면 응답 하나로 끝난다.
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

    version · colors · interfaces · nodes · solid_edges · dotted_edges 를 담아
    돌려준다. version 은 내용 해시라 프론트엔드 캐시 키가 되고, colors 는
    화면이 칩 · 배지 · 안내 문구에 쓸 색이다(색의 출처는 graph_svg 한 곳뿐이다).
    """
    return ontology_service.graph_payload()


@app.post("/render")
async def render_endpoint(form: RenderRequest) -> dict:
    """화면 한 장에 필요한 SVG 와 칩 데이터.

    top(상단 그래프) · variants(하단 변형들) · focus(클릭 가능한 끝노드) ·
    chips(칩에 적을 이름 사슬)를 돌려준다.

    variants 의 모든 SVG 는 노드 좌표와 캔버스 크기가 같다 — 좌표를 전부
    고정하고 neato -n 으로 그리기 때문이다. 그래야 노드를 눌러 좁혀도
    화면이 안 흔들린다.

    같은 요청은 서버가 캐시한다. 키에 온톨로지 version 과 좌표 해시가 들어가
    노드를 등록하면 저절로 빗나간다.
    """
    return render_service.render(form.mode, form.recipe_ids, form.mark)


@app.post("/resolve")
async def resolve_endpoint(utterance: str) -> dict:
    """
    사용자 발화로부터 Recipe 선택.

    Args:
        utterance: 사용자 자연어 입력

    status(SELECT / CLARIFY / NO_MATCH) · recipe_id · candidate_recipe_ids ·
    reason · paths 를 돌려준다. paths 는 후보별 실행 경로이고 NO_MATCH 면 비어 있다.
    """
    return resolve_service.resolve(utterance, llm_client=OllamaClient())


@app.post("/nodes")
async def register_node_endpoint(form: NodeRegisterRequest) -> dict:
    """노드 등록. 온톨로지 · recipe · menu 가 함께 갱신된다.

    새로 생긴 것(node_id · node · recipe_ids · paths · new_solid_edges ·
    new_dotted_edges)과 등록 전후 개수(counts), 갱신된 version 을 돌려준다.
    """
    return node_service.register(form.model_dump(), llm_client=OllamaClient())


@app.post("/nodes/reset")
async def reset_nodes_endpoint() -> dict:
    """_init 사본으로 되돌린다. 등록한 노드와 recipe 가 모두 사라진다."""
    return node_service.reset()


@app.get("/health")
async def health_endpoint() -> dict:
    """시연 직전 점검용. 온톨로지 버전과 LLM 도달 여부.

    LLM 에 닿지 못해도 500 을 내지 않는다 — 못 닿는다는 사실 자체가 응답이다.
    닿는지 보는 일은 llm_engine 이 한다. 라우팅 계층이 HTTP 를 직접 던지면
    "LLM 호출을 한 곳에 가둔다" 는 약속이 깨진다.

    OLLAMA_MODEL 은 모듈 경유로 읽는다. from ... import 로 값을 베껴두면
    테스트가 그 전역을 갈아끼워도 보이지 않는다.
    """
    return {
        "ok": True,
        "ontology_version": ontology_service.ontology_version(),
        "llm": {"reachable": ollama.ping(), "model": ollama.OLLAMA_MODEL},
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("demo.api.main:app", host="0.0.0.0", port=8000, reload=True)
