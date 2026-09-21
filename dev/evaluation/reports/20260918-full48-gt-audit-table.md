# Full48 GT audit table (2026-09-18)

기준: 기대 recipe 의 Recipe.execution 이 `{from: spoken.<이름>}` 으로 읽는 칸 (dev/evaluation/spoken_audit.py 로 추출).
`required` = 없으면 MISSING_ARGUMENT · `default=` = null 이면 기본값으로 실행 · `if/unless_endswith` = 조건부.

| case | group | utterance | recipe | recipe audit | execution spoken refs | current GT | audited GT | action | note |
|---|---|---|---|---|---|---|---|---|---|
| 1 | spoken | 익산역 위치 보여줘 | recipe_001 | PASS | argument(required) | - | argument="익산역" | ADD argument |  |
| 2 | spoken | 경부선 위치 보여줘 | recipe_002 | PASS | argument(required) | - | argument="경부선" | ADD argument |  |
| 3 | spoken | 천안역에 무슨 노선 다녀 | recipe_003 | PASS | argument(unless_endswith=선); argument(if_endswith=선) | - | argument="천안역" | ADD argument | 003 조건: 선으로 끝나면 railwayName, 아니면 stationName → 천안역=stationName |
| 4 | spoken | 오송 테스트트랙 교량 화면에 띄워줘 | recipe_004 | PASS | argument(required) | - | argument="오송 테스트트랙 교량" | ADD argument | frontend 명령 facilityName. KRRI show-facility plugin 에 alias 표 없음 → 발화 구 그대로 |
| 5 | spoken | 논산 행정경계 보여줘 | recipe_005 | PASS | argument(required); admin_level(default="시군구") | - | argument="논산", admin_level="시군구" | ADD admin_level · ADD argument | 명명 행정구역 → 층위(#21·#22·#27·#29 선례). null 도 default 시군구로 실행 동일 |
| 6 | spoken | 대구 선거구들 알려줘 | recipe_008 | PASS | argument(required) | - | argument="대구" | ADD argument | searchDistricts query=충북 ≡ sido=충북 (8=8 실측) → query=대구 유효 |
| 7 | spoken | 철도 공약 낸 의원 찾아줘 | recipe_010 | PASS | argument(required) | - | argument="철도" | ADD argument | tool 설명 예 「철도」. 「철도 공약」은 공약 내용 substring 이 아님 |
| 8 | spoken | 청주시 인구 몇 명이야 | recipe_012 | PASS | argument(required) | - | argument="청주시" | ADD argument | searchStatistics(query=청주시) sigungu 4건(구 4개) 반환 — 결과 모양 note |
| 9 | spoken | 철도안전법 조문 문서에서 찾아줘 | recipe_014 | PASS | argument(required) | - | - | REVIEW argument | REVIEW: 「철도안전법」 vs 「철도안전법 조문」 둘 다 knowledge.query 로 성립. 사람이 정할 자리 |
| 10 | spoken | 충북 청주서원 선거구 정보 줘 | recipe_015 | QUESTION | argument(required) | - | argument="충북 청주서원" | ADD argument | 015 vs 016: 「정보」가 당선인·공약 포함 여부를 안 가름 (기존 mark 겹침); getDistrict(name=충북 청주서원) 1건 실측 |
| 11 | spoken | 청주시 흥덕구 당선인이랑 공약까지 같이 보여줘 | recipe_016 | PASS | argument(required) | - | argument="청주시 흥덕구" | ADD argument | getAssemblyDistrict(name=청주시 흥덕구) 1건 실측 |
| 12 | spoken | 동대구역 행정경계 보여줘 | recipe_033 | PASS | argument(required); admin_level(default="시군구") | - | argument="동대구역", admin_level=null | ADD admin_level · ADD argument | 역(POI) → 층위 안 말함 → null (지어내면 layer 가 바뀜) |
| 13 | spoken | 부산역이 무슨 구에 있어 | recipe_034 | PASS | argument(required); admin_level(default="시군구") | - | argument="부산역", admin_level="시군구" | ADD admin_level · ADD argument | 「무슨 구」 = 시군구 명시 |
| 14 | spoken | 수원역 근처 CCTV 띄워줘 | recipe_036 | PASS | argument(required) | - | argument="수원역" | ADD argument |  |
| 15 | spoken | 광주송정역은 어느 선거구야 | recipe_038 | PASS | argument(required) | - | argument="광주송정역" | ADD argument |  |
| 16 | spoken | 동대구역 지역구 의원 누구야 | recipe_040 | PASS | argument(required) | - | argument="동대구역" | ADD argument |  |
| 17 | spoken | 부산역 쪽 의원 공약 뭐 있어 | recipe_042 | PASS | argument(required) | - | argument="부산역" | ADD argument |  |
| 18 | spoken | 대전역 주변에 사람 얼마나 살아 | recipe_045 | PASS | argument(required) | - | argument="대전역" | ADD argument |  |
| 19 | spoken | 충북선 따라 CCTV 보여줘 | recipe_049 | PASS | argument(required) | - | argument="충북선" | ADD argument | getSectionGeometry(충북선) 1건 실측 |
| 20 | spoken | 탄방동 충전소 비었는지 알려줘 | recipe_052 | QUESTION | argument(required) | - | argument="탄방동" | ADD argument | 052(키워드) vs 060(좌표 둘레): 탄방동은 주소 키워드이자 장소; ev.searchStations(query=탄방동) 11건 실측 |
| 21 | spoken | 전주시 연령대별 인구 알려줘 | recipe_058 | PASS | argument(required); admin_level(default="시군구") | admin_level="시군구" | argument="전주시", admin_level="시군구" | KEEP admin_level · ADD argument | sigungu layer 는 일반구 도시에서 구를 줌(전주시→완산/덕진구) — 실행 결과 note, GT 무관 |
| 22 | spoken | 군산시 인구 변화 알려줘 | recipe_059 | PASS | argument(required); admin_level(default="시군구") | admin_level="시군구" | argument="군산시", admin_level="시군구" | KEEP admin_level · ADD argument |  |
| 23 | spoken | 광주송정역 근처 충전소 충전기 비었는지 알려줘 | recipe_060 | PASS | argument(required) | - | argument="광주송정역" | ADD argument |  |
| 24 | spoken | 의왕역에서 걸어서 30분이면 어디까지 갈 수 있어 | recipe_061 | PASS | argument(required); minutes(default=[30]); travel_mode(default="대중교통") | travel_mode="도보", minutes=[30] | argument="의왕역", travel_mode="도보", minutes=[30] | ADD argument · KEEP minutes · KEEP travel_mode |  |
| 25 | spoken | 의왕역에서 도달권 보여줘 | recipe_061 | PASS | argument(required); minutes(default=[30]); travel_mode(default="대중교통") | travel_mode=null, minutes=null | argument="의왕역", travel_mode=null, minutes=null | ADD argument · KEEP minutes · KEEP travel_mode |  |
| 26 | spoken | 의왕역에서 자전거로 15분, 30분, 60분 도달권 보여줘 | recipe_061 | PASS | argument(required); minutes(default=[30]); travel_mode(default="대중교통") | travel_mode="자전거", minutes=[15, 30, 60] | argument="의왕역", travel_mode="자전거", minutes=[15, 30, 60] | ADD argument · KEEP minutes · KEEP travel_mode |  |
| 27 | spoken | 오송읍 행정경계 보여줘 | recipe_005 | PASS | argument(required); admin_level(default="시군구") | admin_level="읍면동" | argument="오송읍", admin_level="읍면동" | KEEP admin_level · ADD argument |  |
| 28 | spoken | 부산역 주변 행정경계 보여줘 | recipe_033 | PASS | argument(required); admin_level(default="시군구") | - | argument="부산역", admin_level=null | ADD admin_level · ADD argument | 역(POI) + 주변 → 층위 안 말함 → null |
| 29 | spoken | 충청북도 연령대별 인구 알려줘 | recipe_058 | PASS | argument(required); admin_level(default="시군구") | admin_level="시도" | argument="충청북도", admin_level="시도" | KEEP admin_level · ADD argument | 충청북도 → 시도 (sido 43 실측) |
| 30 | picked_point | 여기 어느 동이야 | recipe_018 | PASS | admin_level(default="시군구") | admin_level="읍면동" | admin_level="읍면동" | KEEP admin_level | 「동」 → 읍면동 |
| 31 | picked_point | 여기 CCTV 띄워줘 | recipe_019 | QUESTION | - | - | - | KEEP (읽는 칸 없음) | 019(찍은 지점) vs 026(보이는 범위): 「여기」가 지점인지 화면인지 발화에 답 없음 (기존 주석 함께 걸림 026) |
| 32 | picked_point | 여기 선거구 이름 뭐야 | recipe_020 | PASS | - | - | - | KEEP (읽는 칸 없음) |  |
| 33 | picked_point | 여기 국회의원 누구야 | recipe_021 | PASS | - | - | - | KEEP (읽는 칸 없음) |  |
| 34 | picked_point | 여기 의원 공약 보여줘 | recipe_022 | PASS | - | - | - | KEEP (읽는 칸 없음) |  |
| 35 | picked_point | 여기 연령대별 인구 알려줘 | recipe_054 | PASS | admin_level(default="시군구") | - | admin_level=null | ADD admin_level | 층위 안 말함 → null |
| 36 | picked_point | 여기 인구 변화 알려줘 | recipe_055 | PASS | admin_level(default="시군구") | - | admin_level=null | ADD admin_level | 층위 안 말함 → null |
| 37 | picked_point | 여기서 조치원역까지 어떻게 가 | recipe_062 | PASS | argument(required) | - | argument="조치원역" | ADD argument | 062 는 argument 를 도착지 geocode 로만 읽음. 출발지는 context |
| 38 | picked_point | 여기서 걸어서 20분이면 어디까지 갈 수 있어 | recipe_063 | PASS | minutes(default=[30]); travel_mode(default="대중교통") | travel_mode="도보", minutes=[20] | travel_mode="도보", minutes=[20] | KEEP minutes · KEEP travel_mode |  |
| 39 | picked_point | 여기서 도달권 보여줘 | recipe_063 | PASS | minutes(default=[30]); travel_mode(default="대중교통") | travel_mode=null, minutes=null | travel_mode=null, minutes=null | KEEP minutes · KEEP travel_mode |  |
| 40 | picked_point | 선택한 지점에서 도달권 보여줘 | recipe_063 | PASS | minutes(default=[30]); travel_mode(default="대중교통") | travel_mode=null, minutes=null | travel_mode=null, minutes=null | KEEP minutes · KEEP travel_mode |  |
| 41 | view_extent | 지금 보이는 범위 행정경계 그려줘 | recipe_024 | PASS | admin_level(default="시군구") | admin_level=null | admin_level=null | KEEP admin_level | 층위 안 말함 → null (기존) |
| 42 | view_extent | 지금 보이는 데 CCTV 다 띄워줘 | recipe_026 | PASS | - | - | - | KEEP (읽는 칸 없음) |  |
| 43 | view_extent | 지금 보이는 데 철도 노선 뭐뭐 있어 | recipe_027 | PASS | - | - | - | KEEP (읽는 칸 없음) |  |
| 44 | view_extent | 지금 보이는 데 의원 공약 검색해줘 | recipe_029 | PASS | - | - | - | KEEP (읽는 칸 없음) |  |
| 45 | view_extent | 현재 화면 인구 알려줘 | recipe_031 | PASS | - | - | - | KEEP (읽는 칸 없음) |  |
| 46 | view_extent | 지금 보이는 데 충전소 충전기 비었는지 알려줘 | recipe_056 | PASS | - | - | - | KEEP (읽는 칸 없음) |  |
| 47 | view_extent | 지금 보이는 범위 행정경계 보여줘 | recipe_024 | PASS | admin_level(default="시군구") | admin_level=null | admin_level=null | KEEP admin_level | 층위 안 말함 → null (기존) |
| 48 | view_extent | 지금 화면에 든 읍면동 경계 표시해줘 | recipe_024 | PASS | admin_level(default="시군구") | admin_level="읍면동" | admin_level="읍면동" | KEEP admin_level | 「읍면동」 명시 (기존) |
