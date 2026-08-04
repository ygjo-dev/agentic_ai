"""
LLM for Static Workflow의 구조화된 Output Schema.
"""

SELECT = "SELECT"
CLARIFY = "CLARIFY"
NO_MATCH = "NO_MATCH"

# LLM 응답 구조(json) for static workflow.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "candidate_recipe_ids": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string", "enum": [SELECT, CLARIFY, NO_MATCH]},
        "recipe_id": {"type": ["string", "null"]},
    },
    "required": ["reason", "candidate_recipe_ids", "status", "recipe_id"],
}
