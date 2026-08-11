"""
Backend FastAPI 진입점.

라우팅과 오류 매핑만 둔다. 도메인 로직은 demo/api/services/ 가 안다.

(향후 타 샌드박스와의 소켓/HTTP 통신을 추가 예정).
"""

import sys
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException

# demo/api/main.py -> demo/api -> demo -> 저장소 뿌리. 한 단계 깊어졌다.
REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from demo.api.schemas.node import NodeRegisterRequest
from demo.api.schemas.render import RenderRequest
from demo.api.services import (
    graph_service,
    node_service,
    render_service,
    resolve_service,
)
from llm_engine import ollama
from llm_engine.ollama import OllamaClient
from ontology.registry import (
    DuplicateNode,
    InvalidInference,
    UnknownInterface,
    UnknownPropertyKey,
)
from orchestrator.route_resolver import RouteResolutionError

app = FastAPI(
    title="Recipe Resolver API",
    description="사용자 발화로부터 Recipe 선택",
    version="1.0.0",
)

# 422 로 내보낼 예외. "요청이 잘못됐거나 LLM 이 계약을 어겼다" 는 뜻이고,
# 서버가 고장난 것이 아니다. RouteResolutionError 는 RuntimeError, 나머지 넷은
# ValueError 라 서로 겹치지 않는다.
DOMAIN_ERRORS = (
    RouteResolutionError,
    DuplicateNode,
    UnknownInterface,
    UnknownPropertyKey,
    InvalidInference,
)


@app.get("/graph")
async def graph_endpoint() -> dict:
    """온톨로지 그래프 한 벌. 프론트엔드가 그리는 데 필요한 것 전부.

    version · colors · interfaces · nodes · solid_edges · dotted_edges 를 담아
    돌려준다. version 은 내용 해시라 프론트엔드 캐시 키가 되고, colors 는
    화면이 칩 · 배지 · 안내 문구에 쓸 색이다(색의 출처는 graph_svg 한 곳뿐이다).
    """
    try:
        return graph_service.graph_payload()
    except DOMAIN_ERRORS as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


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
    try:
        return render_service.render(form.mode, form.recipe_ids, form.mark)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except DOMAIN_ERRORS as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/resolve")
async def resolve_endpoint(utterance: str) -> dict:
    """
    사용자 발화로부터 Recipe 선택.

    Args:
        utterance: 사용자 자연어 입력

    status(SELECT / CLARIFY / NO_MATCH) · recipe_id · candidate_recipe_ids ·
    reason · paths 를 돌려준다. paths 는 후보별 실행 경로이고 NO_MATCH 면 비어 있다.
    """
    try:
        return resolve_service.resolve(utterance, llm_client=OllamaClient())
    except DOMAIN_ERRORS as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/nodes")
async def register_node_endpoint(form: NodeRegisterRequest) -> dict:
    """노드 등록. 온톨로지 · recipe · menu 가 함께 갱신된다.

    새로 생긴 것(node_id · node · recipe_ids · paths · new_solid_edges ·
    new_dotted_edges)과 등록 전후 개수(counts), 갱신된 version 을 돌려준다.
    """
    try:
        return node_service.register(form.model_dump(), llm_client=OllamaClient())
    except DOMAIN_ERRORS as e:
        # 화면이 원인을 그대로 보여준다. 예외 이름이 있어야 무엇이 잘못됐는지 읽힌다.
        raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/nodes/reset")
async def reset_nodes_endpoint() -> dict:
    """_init 사본으로 되돌린다. 등록한 노드와 recipe 가 모두 사라진다."""
    try:
        return node_service.reset()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/health")
async def health_endpoint() -> dict:
    """시연 직전 점검용. 온톨로지 버전과 LLM 도달 여부.

    LLM 에 닿지 못해도 500 을 내지 않는다 — 못 닿는다는 사실 자체가 응답이다.
    짧은 타임아웃을 쓴다. 점검이 오래 걸리면 점검이 아니다.

    OLLAMA_HOST / OLLAMA_MODEL 은 모듈 경유로 읽는다. from ... import 로 값을
    베껴두면 테스트가 그 전역을 갈아끼워도 보이지 않는다.
    """
    try:
        urllib.request.urlopen(f"{ollama.OLLAMA_HOST}/api/tags", timeout=3)
        reachable = True
    except Exception:  # noqa: BLE001 — 못 닿는 이유는 묻지 않는다. 닿는지만 본다.
        reachable = False

    return {
        "ok": True,
        "ontology_version": graph_service.ontology_version(),
        "llm": {"reachable": reachable, "model": ollama.OLLAMA_MODEL},
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("demo.api.main:app", host="0.0.0.0", port=8000, reload=True)
