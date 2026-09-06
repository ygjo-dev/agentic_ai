# -*- coding: utf-8 -*-
"""
MCP (Model Context Protocol) 클라이언트 서비스
Gateway의 Tool Registry를 활용하여 MCP 서버와 통신합니다.
"""

from typing import Dict, Any, Optional, List
import time
import httpx

from vendor_to_be_deleted.asap.config import settings
from logging import getLogger as get_logger

logger = get_logger("core.mcp_client")


class MCPClient:
    """Gateway를 통한 MCP Tool 클라이언트"""
    
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = base_url or settings.GATEWAY_URL
        self.timeout = timeout or settings.MCP_TIMEOUT
        self._tools_cache: List[Dict[str, Any]] = []
        self._tools_cache_loaded_at = 0.0
    
    # === Tool 목록 조회 ===
    
    def get_tools(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """Gateway에 등록된 모든 Tool 목록 조회"""
        if self._tools_cache and not refresh and not self._is_tools_cache_expired():
            return self._tools_cache
            
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.base_url}/api/tools")
                resp.raise_for_status()
                self._tools_cache = resp.json()
                self._tools_cache_loaded_at = time.time()
                logger.info(f"Loaded {len(self._tools_cache)} tools from Gateway")
                return self._tools_cache
        except Exception as e:
            logger.error(f"Failed to fetch tools from Gateway: {e}")
            return []
    
    # === 범용 Tool 실행 ===
    
    def execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        user_context: Optional[Dict[str, Any]] = None,
        server_id: Optional[str] = None,
    ) -> Any:
        """범용 Tool 실행 (동기)"""
        payload = {"tool": tool_name, "input": args}
        if user_context:
            payload["user_context"] = user_context
        if server_id:
            payload["server_id"] = server_id
        logger.info(f"Executing tool '{tool_name}' with args: {args}, user: {user_context.get('username') if user_context else 'None'}")
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/api/tools/execute",
                    json=payload
                )
                _raise_for_status_with_body(resp)
                data = resp.json()
                logger.info(f"Tool '{tool_name}' executed successfully")
                return data
        except Exception as e:
            logger.error(f"Tool execution failed ({tool_name}): {e}")
            raise
    
    def _is_tools_cache_expired(self) -> bool:
        """Return True when the cached Gateway tool list should be refreshed."""
        ttl = max(float(settings.MCP_TOOLS_CACHE_TTL or 0), 0.0)
        if ttl <= 0:
            return False
        return (time.time() - self._tools_cache_loaded_at) > ttl


# 전역 클라이언트 인스턴스
mcp_client = MCPClient()


def _raise_for_status_with_body(response: httpx.Response) -> None:
    """Raise HTTP errors with Gateway response body preserved."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _extract_error_detail(response)
        message = f"{exc} Response body: {detail}" if detail else str(exc)
        raise RuntimeError(message) from exc


def _extract_error_detail(response: httpx.Response) -> str:
    """Extract a compact error detail from a failed Gateway response."""
    try:
        data = response.json()
        if isinstance(data, dict):
            return str(data.get("error") or data)
        return str(data)
    except Exception:
        return response.text[:1000]
