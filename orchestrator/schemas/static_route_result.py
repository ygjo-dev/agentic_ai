"""LLM for Static Workflow 내부 Dataclass."""

from dataclasses import dataclass, field


@dataclass
class StaticRouteResult:
    status: str
    recipe_id: str | None = None
    candidate_recipe_ids: list[str] = field(default_factory=list)
    reason: str = ""
