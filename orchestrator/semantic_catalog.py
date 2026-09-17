"""발화가 말할 수 있는 semantic 이름의 단일 출처.

**여기 있는 것은 사람이 말한 값의 이름과 모양뿐이다.** 그 값이 어느 MCP 도구의
어느 칸에 어떤 말로 실릴지는 게시된 Recipe.execution 의 `map` · `default` 가 안다.
「도보」가 WALK 가 되는 것을 이 파일도 LLM 도 모른다.

    semantic 값   사람이 말한 값. place_name · travel_mode · travel_time_cutoffs_min
    physical 값   도구가 받는 값. WALK · availableOnly=true · adm_cd

셋이 이 목록 하나를 읽는다.

    llm_engine/roles/resolve/response_schemas  semantic_inputs[].name 의 enum
    orchestrator/semantic_validator            나온 값이 계약을 지키나
    execution/workflow_materializer            {from: spoken.<이름>} 으로 받아 감

넷이 갈리면 LLM 이 뽑은 이름을 실행이 못 읽거나, 실행이 부르는 이름을 LLM 이
영영 못 만든다. 갈렸는지는 dev/tests/test_architecture_contract.py 가 본다.

**문맥 · 부르는 순간 · 앞 단계가 주는 값은 여기 없다.** retrieval_top_k ·
document_names · admin_code · resolved_point · runtime_now 같은 것은 사람이 말한
값이 아니라 내부에서 정해지는 값이라 LLM 에게 시키지 않는다. 여기 없는 이름이
semantic_inputs 에 오면 semantic_validator 가 거부한다.
"""

from dataclasses import dataclass, field

# 값의 갈래.
TEXT = "text"        # 자유 문자열
INTEGER = "integer"  # 정수
NUMBER = "number"    # 정수 · 실수


@dataclass(frozen=True)
class Semantic:
    """semantic 이름 하나의 모양.

    kind      TEXT · INTEGER · NUMBER
    many      값이 목록인가. 거짓이면 값 하나임
    positive  0 보다 커야 하는가. 시간 · 개수 · 거리처럼 0 이하가 뜻을 못 갖는 칸만 참
    choices   닫힌 선택지. 비면 자유 값임 — **애매한 도메인 값을 억지로 닫지 않는다.**
              정당 이름 · 공약 분야 · 문서 힌트는 사람이 말하는 대로 들어옴
    max_items 목록 이름이 한 발화에서 받을 수 있는 칸 수의 상한. many 인 이름만 씀.
              **상한이 없는 목록은 폭주한다** — temperature 0 이 빈 칸을 max_tokens 까지
              되풀이해 JSON 이 잘렸다(2026-09-16 site_domains 실측 · HTTP 422). 응답
              schema 가 이 수로 maxItems 를 적고 semantic_validator 도 같은 수를 본다
    """

    kind: str
    many: bool = False
    positive: bool = False
    choices: tuple = field(default=())
    max_items: int = 0


# 발화가 말할 수 있는 semantic 이름과 그 모양. **차례가 곧 프롬프트에 적는 차례다.**
CATALOG = {
    # 무엇을 가리키나
    "place_name": Semantic(TEXT),
    "facility_name": Semantic(TEXT),
    "search_keyword": Semantic(TEXT),
    "district_ref": Semantic(TEXT),
    "railway_line": Semantic(TEXT),
    "station_name": Semantic(TEXT),
    "origin": Semantic(TEXT),
    "destination": Semantic(TEXT),
    "sido_filter": Semantic(TEXT),
    # 어떻게 다니나
    "travel_mode": Semantic(TEXT, choices=("도보", "자전거", "승용차", "대중교통")),
    "travel_time_cutoffs_min": Semantic(INTEGER, many=True, positive=True, max_items=8),
    "max_travel_time_min": Semantic(INTEGER, positive=True),
    "route_alternatives": Semantic(INTEGER, positive=True),
    # 언제
    "trip_date": Semantic(TEXT),
    "trip_time": Semantic(TEXT),
    "time_anchor": Semantic(TEXT),
    "reference_month": Semantic(TEXT),
    "period_range": Semantic(TEXT, many=True, max_items=2),
    # 얼마나
    "list_result_cap": Semantic(INTEGER, positive=True),
    "recent_snapshot_count": Semantic(INTEGER, positive=True),
    "search_radius_m": Semantic(INTEGER, positive=True),
    # 행정 · 인구
    "admin_level": Semantic(TEXT, choices=("시도", "시군구", "읍면동")),
    "population_metric": Semantic(TEXT),
    "ranking_order": Semantic(TEXT),
    # 선거
    "political_party": Semantic(TEXT),
    "elected_person": Semantic(TEXT),
    "pledge_category": Semantic(TEXT),
    # 충전소
    "charger_type": Semantic(TEXT),
    "charger_availability": Semantic(TEXT),
    "min_output_kw": Semantic(NUMBER, positive=True),
    # 문서 · 웹
    "document_hint": Semantic(TEXT),
    "site_domains": Semantic(TEXT, many=True, max_items=5),
}

# 이름만. CATALOG 차례 그대로.
NAMES = tuple(CATALOG)

# 숫자로 쓰는 이름. semantic_normalizer 가 이것만 수로 고친다.
NUMERIC_KINDS = (INTEGER, NUMBER)
