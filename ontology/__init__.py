"""온톨로지 도메인. 게시된 자산을 읽기만 한다.

부르는 쪽은 보통 `ONTOLOGY` 하나를 쓴다. 다른 파일을 읽어야 하는 곳(시험)만
`Ontology(path)` 로 따로 만든다.

    from ontology import ONTOLOGY
    ONTOLOGY.recipe_ids()

쓰는 API 는 없다. 노드 등록 · recipe 게시는 agentic_ai 밖의 등록 저장소 일이다.
"""

from ontology.ontology import (
    ABOUT,
    HAS_INPUT,
    HAS_OUTPUT,
    IS_A,
    ONTOLOGY,
    SUPPORTED_PREDICATES,
    Ontology,
)

__all__ = [
    "ABOUT",
    "HAS_INPUT",
    "HAS_OUTPUT",
    "IS_A",
    "ONTOLOGY",
    "SUPPORTED_PREDICATES",
    "Ontology",
]
