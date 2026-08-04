"""
Backend FastAPI 진입점.

(향후 타 샌드박스와의 소켓/HTTP 통신을 추가 예정).
"""

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException

REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

import paths
from orchestrator.route_resolver import resolve_route, RouteResolutionError
from orchestrator.schemas.response_schema import RESPONSE_SCHEMA
from workflows.static.menu.load import load_menu
from llm_engine.ollama import OllamaClient

app = FastAPI(
    title="Recipe Resolver API",
    description="사용자 발화로부터 Recipe 선택",
    version="1.0.0",
)


@app.post("/resolve")
async def resolve_endpoint(utterance: str) -> dict:
    """
    사용자 발화로부터 Recipe 선택.

    Args:
        utterance: 사용자 자연어 입력

    Returns: RESPONSE_SCHEMA
    """
    try:
        result = resolve_route(
            prompt=paths.RECIPE_SELECTION_PROMPT_PATH.read_text(encoding="utf-8"),
            variables={"menu": load_menu(), "utterance": utterance},
            response_schema=RESPONSE_SCHEMA,
            llm_client=OllamaClient(),
        )
        return result
    except RouteResolutionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
