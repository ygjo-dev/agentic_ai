# Test Run 20260918-161110-test_suite_v2-e2cf28

- Test Suite: 테스트 세트 v2 (v2, sha256 50244e5bb343, 219 cases)
- model: solar-open2-250b · vllm · role v1
- started 2026-09-18T16:11:10.260482+09:00 · finished 2026-09-18T16:33:43.479402+09:00 · elapsed 1353.2 s
- stopped: None

| metric | result |
|---|---|
| Selection | 184/195 (94.4%) |
| Semantic fields | 187/190 (98.4%) |
| Semantic cases | 147/150 (98.0%) |
| Joint | 181/195 (92.8%) |
| OOS | 15/24 (62.5%) |
| READY | 185/195 (94.9%) |
| Errors | 0 |

latency (s): min 1.066 · median 1.637 · p95 1.882 · max 2.182
GPU: available True · start 37 · max 70 · end 70 · pauses 14 · throttle False

## failed cases

- #46 [function] 서울 종로 선거구 조회해줘 · expected ['recipe_015'] · actual CLARIFY None ['recipe_015', 'recipe_016'] outcome CLARIFY 
- #47 [function] 경기 수원시갑 선거구 알려줘 · expected ['recipe_015'] · actual CLARIFY None ['recipe_015', 'recipe_016'] outcome CLARIFY 
- #48 [function] 부산 해운대구을 지역구 정보 찾아줘 · expected ['recipe_015'] · actual SELECT recipe_016 ['recipe_016'] outcome READY 
- #49 [function] 인천 연수구갑 선거구 하나만 보여줘 · expected ['recipe_015'] · actual CLARIFY None ['recipe_015', 'recipe_016'] outcome CLARIFY 
- #53 [function] 대전 유성구 지역구 의원이랑 공약 다 보여줘 · expected ['recipe_016'] · actual CLARIFY None ['recipe_016', 'recipe_042'] outcome CLARIFY 
- #59 [input] 경복궁 일대 동 경계 보여줘 · expected ['recipe_033'] · actual SELECT recipe_033 ['recipe_033'] outcome READY admin_level '읍면동'->None
- #82 [function] 청주역 지역구 공약 중에 교통 분야만 보여줘 · expected ['recipe_042'] · actual CLARIFY None ['recipe_010', 'recipe_042'] outcome CLARIFY 
- #85 [function] 강릉역 선거구 의원 공약 목록 줘 · expected ['recipe_042'] · actual CLARIFY None ['recipe_016', 'recipe_042'] outcome CLARIFY 
- #96 [input] 환경부 충전소 충전기 몇 대 비었어 · expected ['recipe_052'] · actual SELECT recipe_052 ['recipe_052'] outcome READY argument '환경부'->'환경부 충전소'
- #97 [input] 이마트 충전소에 빈 충전기 있는지 알려줘 · expected ['recipe_052'] · actual SELECT recipe_052 ['recipe_052'] outcome READY argument '이마트'->'이마트 충전소'
- #99 [function] GS칼텍스 전기차 충전소 지금 쓸 수 있는지 봐줘 · expected ['recipe_052'] · actual CLARIFY None ['recipe_052', 'recipe_060'] outcome CLARIFY 
- #114 [function] 강남역 부근 전기차 충전소 빈 충전기 몇 대야 · expected ['recipe_060'] · actual CLARIFY None ['recipe_052', 'recipe_060'] outcome CLARIFY 
- #119 [function] 대전역 도달권 지도에 그려줘 · expected ['recipe_061'] · actual CLARIFY None ['recipe_061', 'recipe_063'] outcome CLARIFY 
- #191 [function] 지금 보이는 곳 충전소 빈 충전기 알려줘 · expected ['recipe_056'] · actual CLARIFY None ['recipe_026', 'recipe_056'] outcome CLARIFY 
- #199 [scope] 이번 달 철도 사고 보고서 써줘 · expected ['NO_MATCH'] · actual SELECT recipe_014 ['recipe_014'] outcome READY 
- #205 [scope] 도달권 보여줘 · expected ['CLARIFY'] · actual SELECT recipe_063 ['recipe_063'] outcome READY 
- #206 [scope] 행정경계 보여줘 · expected ['CLARIFY'] · actual SELECT recipe_005 ['recipe_005'] outcome MISSING_ARGUMENT 
- #207 [scope] 충전소 빈 충전기 알려줘 · expected ['CLARIFY'] · actual SELECT recipe_052 ['recipe_052'] outcome MISSING_ARGUMENT 
- #208 [scope] 인구 얼마나 돼 · expected ['CLARIFY'] · actual SELECT recipe_031 ['recipe_031'] outcome READY 
- #210 [scope] 철도 노선 뭐 있어 · expected ['CLARIFY'] · actual SELECT recipe_003 ['recipe_003'] outcome MISSING_ARGUMENT 
- #211 [scope] 여기 선거구 알려줘 · expected ['CLARIFY'] · actual SELECT recipe_020 ['recipe_020'] outcome READY 
- #213 [scope] 좌표 알려줘 · expected ['CLARIFY', 'MISSING_ARGUMENT'] · actual NO_MATCH None [] outcome NO_MATCH 
- #218 [scope] 그 충전소 충전기 비었는지 봐줘 · expected ['CLARIFY', 'MISSING_ARGUMENT'] · actual SELECT recipe_056 ['recipe_056'] outcome READY 
