# Test Run 20260921-090538-test_suite_v2-87532e

- Test Suite: 테스트 세트 v2 (v2, sha256 e032664fd667, 203 cases)
- model: solar-open2-250b · vllm · role v1 · request {"reasoning_effort": "none", "temperature": 0, "seed": 0, "max_tokens": 1024}
- environment: GPU0 NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition 97887 MiB, GPU1 NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition 97887 MiB, GPU2 NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition 97887 MiB, GPU3 NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition 97887 MiB
- started 2026-09-21T09:05:38.039154+09:00 · finished 2026-09-21T09:31:37.047912+09:00 · elapsed 1559.0 s
- stopped: None

| metric | result |
|---|---|
| Selection | 184/195 (94.4%) |
| Semantic fields | 187/190 (98.4%) |
| Semantic cases | 147/150 (98.0%) |
| Joint | 181/195 (92.8%) |
| OOS | 7/8 (87.5%) |
| Errors | 0 |

latency (s): min 1.061 · median 1.628 · p95 1.863 · max 3.275

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
