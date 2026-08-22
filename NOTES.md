# NOTES

개발할 때 필요한 맥락을 모아둔다. 소스의 주석은 그 파일의 로직을 설명하고,
"무엇을 재봤고 무엇이 안 됐나" 는 여기 적는다.

두 구역이고 규칙이 다르다.

**열린 과제** — 아직 안 한 것 · 아직 모르는 것. 자유롭게 고치고 해결되면 지운다.

**측정 기록** — **덧붙이기만 한다. 지우지 않는다.**
틀린 것이 밝혀져도 지우지 말고 아래에 정정을 덧붙인다. 옛 기록과 정정이 나란히
있어야 "무엇이 언제 바뀌었나" 를 읽을 수 있다. 실제로 2026-08-15 기록이 남아
있었기 때문에 08-19 에 환경이 움직였다는 것을 알아냈다.
날짜 · 모델 · recipe 수 · 반복 횟수를 반드시 적는다. 조건 없는 숫자는 쓸모없다.

재는 방법은 `python tools/check_resolve.py --runs 10` (uvicorn 이 떠 있어야 함).

---

## 건드리기 전에 읽을 것

소스에는 값만 있고 이유는 여기 있다. 고치기 전에 본다.

| 어디 | 지금 값 | 왜 |
|---|---|---|
| `models.yaml` `default` | `qwen3:32b` | 8b 와 아홉 발화를 각 10회 재서 갈랐다 — 20/90 대 50/90. 갈린 것은 `want` 축 하나다 (아래 2026-08-22 (이어서) 참고). 더 작은 것으로도 못 내린다. qwen2.5:7b · qwen3:4b 는 발화 하나씩을 못 맞춘다 |
| `llm_engine/ollama.py` `options` | `repeat_penalty` 없음 | 올리면 반복은 멎지만 판정까지 깎인다. 반복은 아래 `maxLength` 로 막는다 |
| `models.yaml` `defaults.reason_max_length` | `200` | 없애면 모델이 recipe id 나열을 무한 반복해 202초에 끊긴다. 올려도 답은 그대로이고 시간만 는다 (200 · 400 · 600 -> 30 · 50 · 70초) |
| `workflows/static/prompts/recipe_selection.md` | reason 에 ID 금지 | 이 규칙이 루프와 판정을 함께 잡는다. 빼면 3번 발화가 0/10 |
| `workflows/static/menu/menu.yaml` | recipe 를 끝에 이어 붙임 | 대상별로 묶는 것을 재봤는데 모델에 따라 반대로 작용한다 |
| `workflows/static/prompts/recipe_selection.md` 축 목록 | id + 이름 + 설명 730자 | 채운 프롬프트가 6758자다. `num_ctx` 8192(토큰) 에 여유가 많지 않으므로 선택지를 늘릴 때는 프롬프트 길이를 다시 재고 넣는다 |
| `ontology/shortlist.py` `candidates()` about | 두 단 (걸린 것 우선, 없으면 범용) | 범용 recipe 를 늘 통과시키면 "국회의원 선거구" 에 웹 검색과 VWorld 경계가 따라오고, 늘 빼면 대상 없는 발화에서 후보가 0개가 된다 |

모델마다 다른 값(`num_ctx` · `timeout` · `reason_max_length`)은 `models.yaml` 에 있다.
목록에 없는 모델은 `defaults` 로 돈다. 어디에 붙는가(`OLLAMA_HOST` · `BACKEND_URL`)는
기계마다 다르므로 환경변수로 두고 커밋하지 않는다 — `.env.example` 을 복사해 쓴다.

---

## 테스트를 어떻게 쓰는가

무엇을 지키는 테스트인지가 폴더로 갈린다.

```
ontology · orchestrator · llm_engine   제품 명세. 함수 이름이 요구사항 한 문장이고
                                       docstring 에 왜 그런지가 있다
demo/graph_svg                         배치 불변식. 눈이 못 보는 것만
```

**`demo/` 는 189개 중 126개를 지우고 63개를 남겼다.** 남긴 기준은 하나다 —
화면을 봐도 확인할 수 없는 것.

```
로직 오염   "말이 안 되는 경로가 등록됐다"   화면을 보면 안다    -> 지웠다
배치 오염   "노드가 3pt 움직였다"            화면을 봐도 모른다  -> 남겼다
```

3pt 는 안 보이고 30pt 면 이미 시연이 깨진 뒤다. 사람의 눈을 대신하는 테스트는
버리고 눈이 못 보는 것만 남긴다. 지운 126개는 회귀를 잡는 게 아니라 변경을
따라다니고 있었다 — 제품 코드는 한 번에 고쳐지는데 테스트만 네 번씩
실패-수정-재실행이 돌았고, 그 네 번이 전부 "요구사항이 바뀌어서" 였다.

남긴 배치 불변식은 몇 주에 걸쳐 실측으로 알아낸 것들이다. 어떤 강조 조합에서도
좌표가 같다 · 노드를 등록해도 기존 노드가 안 움직인다 · `inputscale=72` ·
핀이 있으면 `overlap` 금지 · 회전은 최초 배치에만. 지우면 다시 알아낼 방법이
없으므로 함부로 손대지 않는다.

**개수를 세어 적지 않는다.** `tests/README.md` 가 폴더별 개수와 합계를 적어뒀다가
조용히 틀렸다. 2026-08-20 에 재보니 여덟 군데가 전부 어긋나 있었다 (리뷰 대상
38 -> 41, `demo/` 58 -> 71, 전체 101 -> 112, `pytest` 가 세는 것 117 -> 128).
어긋나도 빨간불이 없어 아무도 모른다. 그래서 그 문서를 지우고 갱신이 필요 없는
것만 여기로 옮겼다. 개수가 궁금하면 `pytest` 가 언제든 센다.

---

## 열린 과제

- **온톨로지의 식별자 타입이 셋을 하나로 묶고 있다.** 행정구역 코드 · 선거구
  코드 · 충전소 번호가 한 타입이라 recipe 042 · 043 · 044 · 048 이 배선을
  적을 수 없는 경로로 만들어졌다. 쪼개면 사라지지만 recipe 번호가 통째로
  바뀐다. 시연 뒤에 한다 (아래 2026-08-21 (셋째) 참고).
- **배선을 적은 도구 넷을 아직 안 눌러봤다.** `rail.getSectionGeometry` ·
  `geo.getRailwayLines` · `vworld.getAdministrativeBoundaries` ·
  `population.searchStatistics`. 응답 모양과 역 이름 검색이 되는지를 모른다.
- **노드 등록 후(recipe 8)의 판정을 안 쟀다.** 등록 전 6개에서만 30/30 을
  굳혔다. 등록 장면이 시연의 핵심이라 재야 한다. 8개에서 3번 발화가 흔들린
  전례가 있다 (아래 2026-08-19 참고).
- **2026-08-15 측정이 재현되지 않는 이유를 못 찾았다.** 저장소 안에는 원인이
  없다. 남는 것은 Ollama 런타임(0.32.14)뿐이다.
- 형식 동의어("워드" · "피피티" · "파워포인트")를 프롬프트 지시문에 명시하는
  안. menu 문장(데이터)에 담는 것은 실패했다 (아래 2026-08-15 참고).
- **`recipe_035` 의 menu 문장에 "충전기 유형" 이 들어 있다.** 그래서 "충전소"
  발화가 `recipe_036` 으로 간다. `description` 을 고치면 문장이 바뀌지만
  온톨로지 개편에서 어차피 다시 만들어진다. 개편 때 함께 본다.
- **발화 8 의 기대값이 잠정이다.** `"철도 안전 문서 찾아줘"` 가
  `recipe_006`(웹 검색)으로 가는데 그것이 틀린 것인지 GT 가 틀린 것인지
  안 정했다.

---

## 측정 기록

### 2026-08-22 (셋째) · Gateway 도구 42개 훑기

`tools/probe_tools.py` 로 42개를 한 번씩 눌렀다. 배선을 어디에 적을지 정하려고
무엇이 실제로 데이터를 주는지 먼저 쟀다. 도구 목록은 이 장비에 `tools.json` 이
없어 `curl -s http://localhost:3000/api/tools -o /tmp/tools.json` 으로 받았다.

```
  도구                                      상태        건수    비고
  rail.getSectionGeometry                   실패        -       구간 '오송역'을(를) 찾을 수 없습니다.
  road.getCctv                              데이터      84
  geo.geocode                               데이터      1
  geo.getRailwayLines                       데이터      3683
  adminBoundary.getDatasetInfo              데이터      1
  adminBoundary.searchBoundaries            빈 결과     0       행정구역 DB 데이터가 없거나 PostGIS 연결을 사용할 수 없습니…
  adminBoundary.findBoundaryByPoint         빈 결과     0       행정구역 DB 데이터가 없거나 PostGIS 연결을 사용할 수 없습니…
  population.getDatasetInfo                 데이터      1
  population.searchStatistics               빈 결과     0       인구 통계 DB 데이터가 없거나 PostGIS 연결을 사용할 수 없습…
  population.getAgeProfile                  인자 없음   -       level, code
  population.getTrend                       인자 없음   -       level, code
  vworld.getDatasetInfo                     데이터      1
  vworld.getAdministrativeBoundaries        데이터      200
  knowledge.query                           빈 결과     0
  knowledge.listDocs                        빈 결과     0
  knowledge.deleteDoc                       인자 없음   -       문서를 지움
  bim.listModels                            빈 결과     0
  bim.updateModel                           인자 없음   -       모델을 고침
  bim.deleteModel                           인자 없음   -       모델을 지움
  dem.getInfo                               실패        -       layer.json not found: /app/data/dem/90m_GRS80/layer.json
  ev.getDatasetInfo                         데이터      1
  ev.searchStations                         빈 결과     0
  ev.getStation                             인자 없음   -       statId
  ev.searchChargers                         빈 결과     0
  election.getDatasetInfo                   데이터      1
  election.searchDistricts                  데이터      20
  election.getDistrict                      데이터      1
  election.findDistrictByPoint              데이터      1
  election.getAssemblyDistrictDatasetInfo   데이터      1
  election.searchAssemblyDistricts          데이터      20
  election.getAssemblyDistrict              데이터      1
  election.findAssemblyDistrictByPoint      데이터      1
  election.getAssemblyPledgeDatasetInfo     데이터      1
  election.searchAssemblyPledgeDistricts    데이터      20
  election.getAssemblyPledgeDistrict        데이터      1
  election.findAssemblyPledgeDistrictByPo…  데이터      1
  election.getLocalPledgeSummaryDatasetIn…  데이터      1       2026 지방선거 시도별 공약 요약 DB 데이터가 적재되지 않았습…
  election.searchLocalPledgeSummaries       빈 결과     0       2026 지방선거 시도별 공약 요약 데이터를 조회하지 못했습니다.
  election.getLocalPledgeSummary            데이터      1       조건에 맞는 2026 지방선거 시도별 공약 요약을 찾지 못했습니…
  election.findLocalPledgeSummaryByPoint    데이터      1       해당 좌표를 포함하는 시도 공약 요약을 찾지 못했습니다.
  web.search                                실패        -       MCP tool 'web-search/web.search' is not applied for this us…
  web.fetch                                 인자 없음   -       url
  ─────────────────────────────────────────────────────────────────────────────
  도구 42개                                 데이터 23 · 빈 결과 9 · 실패 3 · 인자 없음 7
```

앞서 42개가 전부 `"Tool name is required"` 로 실패했던 것은 본문 모양 탓이었고
`919b09a` 에서 `vendor/asap/mcp_client.py` 와 같은 모양(`tool` · `input` ·
`user_context` · `server_id`)으로 고쳤다. 이번에는 전부 응답이 왔다.

#### 「데이터」 23 을 그대로 믿으면 안 된다

건수만 보면 안 되는 줄이 넷이다.

`election.getLocalPledgeSummary` · `election.findLocalPledgeSummaryByPoint` 는
건수 1인데 `warning` 이 "찾지 못했습니다" 다. 껍데기 객체 하나를 세었을 뿐
알맹이는 없다. 같은 데이터셋의 `getLocalPledgeSummaryDatasetInfo` 도 "적재되지
않았습니다" 라고 답한다. 셋이 같은 말을 한다 — 2026 지방선거 공약 요약은
저쪽에 안 들어와 있다.

`getDatasetInfo` 계열 다섯은 건수 1이 곧 메타데이터 한 덩이다. 데이터가 있다는
뜻이 아니다. `ev.getDatasetInfo` 는 `status: "empty"`, `stationCount: 0`,
`missingRegionCodes` 에 시도 17개가 전부 들어 있다. `population.getDatasetInfo`
도 `status: "empty"`, `totalPopulation: 0` 이다.

`required` 가 없는 도구는 probe 가 인자 없이 불렀다. `election.searchDistricts`
셋의 20건은 `limit` 이 20이라 잘린 전체 목록이지 `query` 가 거른 결과가 아니다.
그래서 `query` 를 따로 눌러 확인했다 — `"청주"` 로 4건 · 5건, `"철도"` 로
206건이 나왔다. 거르기가 실제로 돈다.

#### 0건인 도구와 그 warning

```
adminBoundary.searchBoundaries      행정구역 DB 데이터가 없거나 PostGIS 연결을 사용할 수 없습니다.
adminBoundary.findBoundaryByPoint   행정구역 DB 데이터가 없거나 PostGIS 연결을 사용할 수 없습니다.
population.searchStatistics         인구 통계 DB 데이터가 없거나 PostGIS 연결을 사용할 수 없습니다.
election.searchLocalPledgeSummaries 2026 지방선거 시도별 공약 요약 데이터를 조회하지 못했습니다.
ev.searchStations                   (warning 없음. dataset.status = "empty")
ev.searchChargers                   (warning 없음. dataset.status = "empty")
knowledge.query                     (응답이 [] 하나. warning 자리가 없음)
knowledge.listDocs                  (응답이 [] 하나)
bim.listModels                      (응답이 [] 하나)
```

전부 저쪽 데이터다. 우리가 채울 수 없다.

`adminBoundary` 는 `getDatasetInfo` 가 sido · sigungu · emd 세 층 전부
`featureCount: 0` 이라고 답한다. PostGIS 는 붙어 있고 테이블만 비었다.
`knowledge` 는 `listDocs` 도 `[]` 라 질의가 틀린 것이 아니라 지식베이스에
문서가 하나도 없는 것이다. `ev` 는 시도 17개가 전부 `missingRegionCodes` 라
동기화가 한 번도 안 돌았다.

`MEMORY.md` 의 「KRRI_ASAP gitignore 데이터 누락」 과 같은 줄기다. clone 과
build 는 끝났는데 gitignore 로 빠진 런타임 데이터가 안 들어와 있다.

#### 「인자 없음」 일곱

probe 가 값을 지어내지 않아 안 부른 것들이다. 도구가 고장 났다는 뜻이 아니다.

```
population.getAgeProfile        level, code   행정구역 코드를 어디서 받을지 모름
population.getTrend             level, code   행정구역 코드를 어디서 받을지 모름
ev.getStation                   statId        충전소 번호를 지어낼 수 없음
web.fetch                       url           URL 을 지어낼 수 없음
knowledge.deleteDoc             filename      남의 문서를 지움. 일부러 안 부름
bim.updateModel                 -             남의 모델을 고침. 일부러 안 부름
bim.deleteModel                 -             남의 모델을 지움. 일부러 안 부름
```

앞의 넷은 `ARGUMENT_RULES` 에 값이 없어서고 뒤의 셋은 `REFUSED_TOOLS` 라서다.
뒤의 셋은 앞으로도 누르지 않는다.

#### 「실패」 셋

```
rail.getSectionGeometry   구간 '오송역'을(를) 찾을 수 없습니다.
dem.getInfo               layer.json not found: /app/data/dem/90m_GRS80/layer.json
web.search                MCP tool 'web-search/web.search' is not applied for this user.
```

`rail.getSectionGeometry` 는 도구가 아니라 인자 탓이다. `"오송역"` 은 역 이름이지
구간명이 아니다. 구간명 하나를 알면 다시 재야 한다. 배선(`get_railway_section`)은
이미 적혀 있고 `sectionName` 을 발화에서 받으므로 이대로 둔다.

`dem.getInfo` 는 DEM 타일셋이 컨테이너 안에 없다. `MEMORY.md` 에 적어 둔 그
누락이다.

`web.search` 는 데이터 문제가 아니다. 우리 `USER_CONTEXT` 에 `web-search` 서버가
안 열려 있다. KRRI_ASAP 쪽 사용자 권한이라 우리가 못 연다.

#### `web.search` · `web.fetch` 는 서버가 다르다

42개 중 마흔은 `serverId` 가 `asap-mcp-core` 인데 이 둘만 `web-search` 다.
`STEP_OF` 가 `SERVER_ID` 를 통째로 쓰고 있어 그대로 적으면 Gateway 가 도구를
못 찾는다. `WEB_SERVER_ID` 를 따로 두었다.

#### 이번에 적은 배선 일곱

`STEP_OF` 가 14 -> 21 이 됐다. 전부 발화에서 온 말 하나만 받는 도구라 앞 단계가
필요 없다.

```
노드                              도구                                     상태
search_election_districts         election.searchDistricts                 데이터 254
search_assembly_districts         election.searchAssemblyDistricts         데이터 254
search_assembly_pledge_districts  election.searchAssemblyPledgeDistricts   데이터 476
search_local_pledge_summaries     election.searchLocalPledgeSummaries      0건
search_documents                  knowledge.query                          0건
web_search                        web.search                               권한 막힘
web_fetch                         web.fetch                                안 눌러봄
```

아래 넷도 적었다. **배선이 없는 것과 데이터가 없는 것은 다르다.** 적어 두면
저쪽에 데이터가 들어왔을 때 고칠 것 없이 그대로 돈다. 왜 지금 비었는지는
`STEP_OF` 의 각 줄 위 주석에 적었다.

#### 여전히 못 적는 것

`get_age_profile` · `get_population_trend` · `get_local_pledge_summary` 는
이번에도 못 적었다. `adminBoundary.findBoundaryByPoint` 가 0건이라 `features` 가
비어 있었고 행정구역 코드가 어느 필드로 오는지 볼 것이 없었다.
`getDatasetInfo` 가 `codeField` 로 `ctprvn_cd` · `SIG_CD` · `emd_cd` 를 말하지만
그것은 shapefile 컬럼 이름이지 응답 필드 이름이 아니다. 짐작으로 적지 않는다.

`get_election_district` · `get_assembly_district` · `get_assembly_pledge_district`
· `get_ev_station` 은 「적을 수 없었던 경로」 그대로다. 식별자 체계가 다르다.

#### 앞 단계가 없으면 그 칸을 안 보낸다

`recipe_012` · `013` 은 `spoken_keyword -> search_ev_stations` 인데 그 배선의
`center` 가 `$prev.location` 이라 첫 step 에서 `plan()` 이 `ValueError` 로
멈췄다. 같은 노드가 두 자리에 쓰이기 때문이다 — 키워드 뒤(012 · 013)에도 오고
geocode 뒤(035 · 036)에도 온다. 배선은 한 벌뿐이다.

`_filled` 이 `ValueError` 를 올리던 것을 「그 칸을 빼고 부른다」 로 바꿨다.

근거는 `ev.searchStations` 의 bbox 넷이 전부 optional 이라는 것이다. 없어도
도구가 돌고 전국을 검색한다. 값을 지어내는 것보다 안 보내는 것이 낫다.
`radiusMeters` 만 남은 input 으로 실제로 눌러 확인했다 — HTTP 200 이고
스키마에 없는 `radiusMeters` 도 거부하지 않는다.

`inputAdapter` 도 함께 뺀다. `point_radius_to_bbox` 는 `center` · `point` ·
`coordinate` · `coordinates` · `location` 중 하나를 찾고 못 찾으면
`ValueError("point_radius_to_bbox에는 center/location 좌표가 필요합니다")` 를
올린다. 걸 것이 없는데 걸면 옮겨 온 셈이라 `plan` 이 싣기 전에 본다.

`required` 인 칸이 `$prev` 를 쓰는데 앞 단계가 없으면 그때는 도구가 거부한다.
그건 배선이 틀린 것이지 선택의 문제가 아니라 여기서 가리지 않는다.

**조영곤님이 자리에 없는 동안 대신 정한 판단이다.** 되돌릴 때는 `_filled` 과
`plan` 의 `inputAdapter` 한 줄만 보면 된다. `_filled` 의 이력 절에도 적었다.

##### 전후

`step_service.unwired()` 가 빈 목록을 내는 recipe 를 셌다. LLM 을 안 부르는
코드 계산이다.

```
                          전    후
온전히 도는 것            24    34
반쪽                      10     7
하나도 못 부름            14     7
                          48    48
```

`plan()` 이 터지던 `recipe_012` · `013` 까지 세면 실제로 돌던 것은 22 였다.
`unwired()` 는 배선이 있는지만 보고 `$prev` 가 풀리는지는 안 본다.

늘어난 recipe 는 열둘이다.

```
006 007 008 009 010 014 041   이번에 적은 배선 일곱으로
012 013                       앞 단계 없을 때 규칙으로
028 030 032                   반쪽이던 것이 채워져서
```

##### 돈다고 답이 나오는 것은 아니다

34 중 도구가 실제로 데이터를 주는 것은 18이다. 나머지 16은 호출까지 가고
빈 결과나 권한 오류를 받는다. 저쪽 데이터가 채워지면 그대로 답이 나온다.

```
데이터가 나옴 18   001 002 003 005 007 008 009 024 025 026 027 028 029 030 031 038 039 040
빈 결과 14         004 010 011 012 013 014 022 023 032 033 034 035 036 037
권한 막힘 2        006 041
```

`007` · `008` · `009` 가 새로 데이터가 나오는 쪽에 들었다 —
`election.search*` 셋이 이번 배선의 수확이다.

### 2026-08-22 (이어서) · qwen3:8b 대 qwen3:32b · recipe 48 · 각 10회

```
발화                          8b        32b
1 오송역 위치 보여줘          0/10      10/10
2 오송역 좌표 알려줘          10/10     10/10
3 오송역 CCTV 보여줘          10/10     10/10
4 청주시 인구 구성 알려줘     0/10      10/10
5 오송역 근처 충전소 찾아줘   0/10      0/10
6 국회의원 선거구 찾아줘      0/10      0/10
7 전기차 충전소 데이터 검색   0/10      0/10
8 철도 안전 문서 찾아줘       0/10      0/10
9 충북 제1선거구 알려줘       0/10      10/10
                            20/90 22%  50/90 56%
```

`want` 축이 갈랐다. 8b 는 1번을 `map_extent`, 7번을 `dataset_info`, 9번을
`record_key` 로 썼고 셋 다 오판이다. 7번과 9번은 그 탓에 조회 후보가 0이 되어
LLM 목록(5개 · 22개)이 그대로 CLARIFY 로 나갔다. 32b 는 셋 다 맞게 썼다.
`given` 과 `about` 은 두 모델 다 안정적이었다 — 흔들린 것은 `want` 하나다.

`argument` 는 두 모델 다 9/9 정확했다. 10회 내내 흔들림이 없었고 조사도
요청하는 말도 안 섞였다. `place_in` 이 못 잡던 키워드와 식별자도 맞다.
인자 추출에는 8b 로 충분하다.

1번의 회귀는 모델 탓이었다. 앞 커밋에서 프롬프트가 6758자에서 7133자로
늘면서 8b 가 "위치" 를 `map_extent` 로 읽어 10/10 이 0/10 이 됐다.
32b 에서 `point` 로 돌아왔다. menu 문장을 고치지 않아도 됐다.

5번(충전소 대 충전기)이 이번 비교의 물음이었다. 32b 는 후보를 하나로
좁혔지만 틀린 쪽(036 충전기)을 골랐다. 조회 후보는 두 모델 다 2로 같다.
좁히기는 되고 고르기가 안 되는 것이라 원인은 menu 문장에 있다 —
`recipe_035` 문장 안에 "충전기 유형" 이 들어 있어 "충전소" 라는 말로는
두 문장이 안 갈린다.

6번은 발화가 모호한 것이 맞다. 32b 가 `{007, 008}` 로 CLARIFY 하는 것은
정직한 결과다. 8번은 기대값(`recipe_014`)이 잠정이라 GT 를 다시 봐야 한다.

### 2026-08-22 · 발화에서 인자를 LLM 이 뽑음 (argument) · recipe 48

`place_in` 정규식은 끝 글자가 역·시·군·구·읍·면·동·리 인 어절 하나만 뽑았다.
그래서 `"충북대 근처 CCTV"` 는 끝 글자가 안 맞아 못 잡고, `"국회의원 선거구
찾아줘"` 는 장소가 없어 `execute_service` 가 거기서 멈췄고, `"충북 제1선거구"`
같은 식별자는 뽑는 코드가 아예 없었다. 축 셋을 받는 그 자리에서 인자도 함께
받게 했다.

응답 스키마에 칸 하나(`argument`)를 더했다. **셋으로 나누지 않았다** — `given`
이 이미 그 값이 장소인지 키워드인지 식별자인지 말하므로, `place`/`keyword`/
`identifier` 를 따로 두면 `given` 과 어긋날 수 있고 프롬프트도 그만큼 길어진다.

```
채운 프롬프트   6758자 -> 7133자   (+375, 발화 "오송역 위치 보여줘" 기준)
프롬프트 원본   1763자 -> 2138자
```

`num_ctx` 는 32768 이라 여유가 있다. 위 「건드리기 전에 읽을 것」 표의 6758자는
이 변경 전 값이다.

**아직 LLM 으로 안 쟀다.** `argument` 가 실제로 어떻게 나오는지는
`python tools/check_resolve.py --runs 10` 으로 재야 한다. 축 표에 `argument`
칸을 더해뒀다. 이 커밋의 숫자는 프롬프트 길이와 테스트뿐이다.

#### `@place` 를 `@arg` 로 바꿨다

`STEP_OF` 의 표시 이름이다. 키워드를 받는 도구(`search_documents` ·
`search_election_districts`)도 같은 칸에 발화에서 온 값을 넣으므로 표시가
"장소" 를 뜻하면 안 된다. 배선 여섯(`geocode_place` · `get_railway_section` ·
`get_railway_lines` · `search_admin_boundaries` · `get_vworld_boundaries` ·
`search_population_statistics`)과 headline 열넷이 함께 바뀌었다.
**배선은 새로 안 적었다.** 남은 25개는 다음 커밋이다.

`place_in` 은 지웠다가 다시 넣을 값이 아니라 그대로 뒀다. LLM 이 `argument` 를
빠뜨리거나 흔들려도 장소 발화만은 여전히 돌아야 한다. 지금은 `argument` 가
null 일 때만 돈다.

#### 안내 문구를 `given` 으로 갈랐다

`NO_PLACE_ANSWER` 하나만 있어서 `"국회의원 선거구 찾아줘"` 에 장소를 대라고
답했다. `spoken_keyword` 는 무엇을 찾을지, `spoken_identifier` 는 이름이나
코드를 말해 달라고 한다. `given` 이 null 이거나 모르는 값이면 예전 문구다.

#### 재는 발화를 셋 늘렸다

7 `"전기차 충전소 데이터 검색해줘"` · 8 `"철도 안전 문서 찾아줘"` ·
9 `"충북 제1선거구 알려줘"`. **기대값은 잠정이다.** 셋 다 배선이 없어 실행까지
안 가고, 지금 보는 것은 축과 `argument` 가 맞게 나오는지뿐이다.

#### 안 고친 것

`"국회의원 선거구 찾아줘"` 의 `want` 가 `record_key` 로 나와 조회 후보가 0이
되는 것을 앞선 측정에서 봤다. 원인이 `want` 선택지 설계에 있고, 온톨로지
개편에서 식별자 타입이 쪼개지면 선택지가 통째로 달라진다. 지금 손대면 두 번
일한다.

recipe 012 · 013 은 `spoken_keyword -> search_ev_stations` 인데 그 배선의
input 이 `$prev.location` 이라 첫 step 에서 `plan()` 이 멈춘다. 이번 범위가
아니라(배선을 새로 안 적음) 그대로 뒀다. 다음 커밋에서 볼 것.

테스트 156 passed / 1 failed. 실패 하나는 `test_dense_graph_would_move_if_
overlap_removal_were_used` 로 이 장비의 graphviz 버전 차이다(제품 경로 아님).

### 2026-08-21 (셋째) · STEP_OF 배선 열둘 · recipe 48

바로 아래 기록에서 반쪽 실행을 `unwired()` 로 막아놓고 배선은 안 늘렸다.
이번에 그 표에 열두 줄을 채웠다.

```
recipe 48   온전히 도는 것       2 -> 24
            반쪽으로 남은 것    22 -> 10
            하나도 못 부르는 것 24 -> 14
```

늘어난 22개는 002 003 004 005 011 012 013 022 023 024 026 027 029 031 033
034 035 036 037 038 039 040 이다. **LLM 을 부르지 않은 코드 계산이다** —
`unwired()` 가 빈 목록을 내는 recipe 를 센 것이고, 도구를 실제로 눌러본 것은
아래 「눌러보지 않은 것」 에 적었다.

좌표를 받는 도구(`lon`/`lat`)와 이름을 받는 도구(`query`/`stationName`/
`sectionName`)만 적었다. geocode 가 내주는 `bbox` 는 한 변이 1km 라 그것을
그대로 넘기는 배선은 안 적었다 — 오송역 CCTV 가 그 bbox 로는 0건, 좌표
+ 15km 로는 83건이었다(어제 실측).

#### ev 두 개만 어댑터를 명시했다

`_apply_input_adapter` 는 대상 도구의 `required` 에 bbox 넷이 다 있을 때만
`point_radius_to_bbox` 를 저절로 건다. `road.getCctv` 는 넷이 전부 required 라
걸리고, `ev.searchStations` · `ev.searchChargers` 는 넷 다 optional 이라 안
걸린다. 그래서 `STEP_OF` 에 `adapter` 칸을 만들고 그 둘에만 적었다.
`step_service.plan()` 이 그 값을 step 의 `inputAdapter` 로 실어 보낸다.

#### 적을 수 없었던 경로

```
recipe 042  geocode -> 지점 행정구역 판별 -> 국회의원 지역구 상세
recipe 043  geocode -> 지점 행정구역 판별 -> 국회의원 전체 선거구 상세
recipe 044  geocode -> 지점 행정구역 판별 -> 국회의원 선거구 공약 상세
recipe 048  geocode -> 지점 행정구역 판별 -> 충전소 상세 조회
```

앞 단계 `adminBoundary.findBoundaryByPoint` 가 내놓는 것은 행정구역 코드다.
마지막 도구가 받는 것은 선거구 코드(`election.getDistrict` 의 `code`/`name`)와
충전소 번호(`ev.getStation` 의 `statId`)라 체계가 다르다. 앞 단계 결과에서
옮겨 적을 값이 없어 배선 자체를 적을 수가 없었다.

**온톨로지의 식별자 타입이 셋을 하나로 묶은 탓이다.** 행정구역 코드 · 선거구
코드 · 충전소 번호가 한 타입이라 경로 생성기가 이 넷을 말이 되는 경로로 봤다.
타입을 쪼개면 이 recipe 들이 애초에 안 만들어지고 문제가 사라진다.

**지금 고치지 않는다.** 타입을 쪼개면 경로 집합이 달라져 recipe 번호가 통째로
바뀐다. 2026-08-21 (이어서) 의 발화별 후보 표가 그 번호로 적혀 있어 통째로
무효가 된다. 시연이 끝난 뒤에 한다.

045 · 046 · 047 은 이것과 다르다. `population.getAgeProfile` ·
`population.getTrend` 가 받는 `level` · `code` 는 행정구역 코드가 맞다.
`findBoundaryByPoint` 가 그 코드를 어떤 필드 이름으로 내놓는지 안 눌러봐서
못 적었을 뿐이다. 눌러보면 적을 수 있다.

#### 눌러보지 않은 것

```
rail.getSectionGeometry              응답에 location 이 있는지 모름
geo.getRailwayLines                  stationName 으로 오송역이 걸리는지 모름
vworld.getAdministrativeBoundaries   query 에 "오송역" 같은 역 이름이 걸리는지 모름
population.searchStatistics          query 에 역 이름이 걸리는지 모름
```

recipe 039 (철도 구간 -> CCTV)가 `$prev.location` 을 쓴다. `rail.getSectionGeometry`
응답에 `location` 이 없으면 참조가 None 이 되고, 중심 좌표가 없으니 어댑터가
안 걸려 `road.getCctv` 의 필수 입력이 비었다는 실패로 끝난다. 틀린 답이 나가는
것이 아니라 실패 문구가 나가므로 그대로 뒀다.

---

### 2026-08-21 (이어서) · 발화 해석에 축 조회를 넣음 · recipe 48

바로 아래 측정에서 다섯 발화가 전부 CLARIFY 가 됐고, 원인은 menu 문장의 공통
앞토막이었다. LLM 이 쓴 `reason` 은 맞았다. 발화는 읽었고 48문장 사이에서 못
고른 것이다. 그래서 그 `reason` 이 말한 것을 닫힌 목록의 객관식(축 셋)으로 받고,
그 값으로 온톨로지를 조회해 후보를 뽑게 했다. LLM 호출은 그대로 한 번이다.

**아래는 LLM 을 부르지 않은 코드 계산이다.** 축이 맞다고 놓고 조회만 돌린 것이라
LLM 이 그 축을 실제로 쓰는지는 아직 모른다.

```
발화                        (given, want, about)                        후보
오송역 위치 보여줘          spoken_place · point · -                     1  (001)
오송역 좌표 알려줘          spoken_place · point · -                     1  (001)
오송역 CCTV 보여줘          spoken_place · item_list · group_transport   5  (003 025 026 039 040)
청주시 인구 구성 알려줘     spoken_place · statistics · group_population 3  (034 046 047)
오송역 근처 충전소 찾아줘   spoken_place · item_list · group_ev          2  (035 036)
국회의원 선거구 찾아줘      spoken_keyword · - · group_election          4  (007 008 009 010)
```

48개가 1~5개로 준다. 2번 발화의 후보 15개(앞토막이 같은 것들)를 가르는 것은
`want` 다. 좌표를 내놓고 끝나는 recipe 는 001 하나뿐이라 나머지가 전부 빠진다.
6번의 넷은 여기서도 안 갈린다. 발화가 모호한 것이라 되묻는 것이 맞다.

**프롬프트가 5656자에서 6758자가 됐다** (menu 4316 · 축 목록 730 · 틀 1712).
`num_ctx` 는 8192 토큰이라 여유가 많지 않다. 선택지를 늘릴 때 다시 재야 한다.

#### 배선이 없는 recipe 를 부르고 있었다

`step_service.plan()` 이 `STEP_OF` 에 없는 노드를 조용히 건너뛴다. recipe_022
(geocode -> 행정구역 경계)를 고르면 geocode 만 부르고 "좌표를 조회했습니다" 라고
답한다. 반쪽 결과가 온전한 답처럼 나간다.

```
recipe 48   온전히 도는 것  2  (001 · 025)
            반쪽으로 도는 것 22
            하나도 못 부르는 것 24
```

`step_service.unwired()` 를 만들어 `execute_service.run()` 이 실행 전에 본다.
비어 있지 않으면 도구를 하나도 안 부르고 아직 안 붙은 기능의 이름을 답에 적는다.
**배선(`STEP_OF`)은 늘리지 않았다.** 이번에 한 것은 없는 기능을 있는 척하지
않게 막은 것뿐이다.

#### 다시 시도하지 말 것

- **축 조회에서 `is-a` 를 타고 올라가기** — `want` 를 조상까지 올리면 상위 타입
  하나가 하위 전부를 끌어와 좁히는 뜻이 없어진다. `given` 도 같다. `record_key`
  로 물으면 `spoken_identifier` 로 시작하는 일곱 개가 딸려온다.
- **축이 셋 다 null 일 때 조회 결과를 쓰기** — `candidates()` 는 그때 48개를
  전부 낸다. 그것을 후보로 삼으면 영역 밖 발화의 NO_MATCH 가 48개 CLARIFY 로
  뒤집힌다. 고를 근거가 하나도 없다는 뜻이므로 LLM 이 쓴 것을 그대로 둔다.

---

### 2026-08-21 · MCP 도구 39개 · recipe 48 · qwen3:8b

Gateway catalog 의 도구를 온톨로지에 넣고 발화 해석이 몇 개까지 버티는지 쟀다.

**환경** : qwen3:8b · `num_ctx` 8192 · `reason_max_length` 200 ·
노드 58 (타입 11 · 대상 5 · 시작 데이터 3 · 기능 39) · recipe 48 ·
menu.yaml 4316자 (`MENU_BUDGET` 6000) · `MAX_STEPS` 4 (안 건드림).

**다섯 발화 모두 CLARIFY. SELECT 0개.** recipe 2개일 때는 1·2번이 SELECT 였다.

```
발화                        status    recipe_id   후보 수
오송역 CCTV 보여줘          CLARIFY   -            2   (025 · 039)
오송역 좌표 알려줘          CLARIFY   -           15
청주시 인구 구성 알려줘     CLARIFY   -            5
오송역 근처 충전소 찾아줘   CLARIFY   -            5
국회의원 선거구 찾아줘      CLARIFY   -           20
```

**무너지는 원인은 menu 문장의 공통 앞토막이다.** 48문장 중 중복은 0개인데
앞 30자가 같은 것이 23개다("말한 장소로 장소 이름으로 위치 좌표와 지도 범위를
찾…"). 구별하는 말이 전부 문장 꼬리에 있다.

```
앞 14자 같음   23개  말한 장소로 장소 이름으로…
                5개  말한 장소로 구간 이름으로…
앞 30자 같음   23개 · 5개  (위와 같음)
앞 60자 같음    2개  4단 인구 recipe 둘(046 · 047)
문장 길이       최소 29 · 평균 59 · 최대 100자
```

**후보가 앞토막으로 뭉친다.** 2번(좌표) 후보 15개는 전부 `geocode_place` 로
시작하는 것들이고, 끝점이 좌표인 recipe_001 과 좌표에서 더 나아간 14개를 못
가른다. **앞토막 문제가 다시 왔다** — `6bf034a` 때는 2단 recipe 가 3단의
앞토막이라 35/35 가 5/35 가 됐고, 이번에는 3단·4단이 다 같은 2단으로 시작한다.

5번(선거구) 후보 20개는 네 데이터셋(지역구 · 전체 선거구 · 선거구 공약 ·
지방선거 공약)을 못 가른 것이다. 사람도 발화만으로는 못 가른다 — 발화가 모호한
것이지 온톨로지가 틀린 것이 아니다.

4번(충전소)에 recipe_025(CCTV 조회)가 섞였다. 앞토막이 같아서다 — 꼬리의
"CCTV 목록" 과 "전기차 충전소" 가 안 갈렸다.

**뒤집어 보면 대상(about) 차단은 제대로 일했다.** 54개 중 6개를 버렸고 남은
48개에 어긋나는 것이 없다. 버린 6개는 전부 철도 구간(교통)에서 선거 · 인구 ·
전기차로 건너뛰는 것이다.

#### 이번에 알아낸 구조 제약

- **`hasInput` 이 하나도 없는 도구는 recipe 가 될 수 없다.** `getDatasetInfo`
  아홉과 `knowledge.listDocs` · `bim.listModels`, 열한 개다. `can_connect` 가
  받는 것이 없는 노드를 누구 뒤에도 안 세우고 `start_ids` 는 실행 노드를
  빼므로 첫 칸에도 못 온다. 온톨로지에는 있고 menu 에는 없다.
- **다음 도구가 받는 타입을 내놓게 하면 경로가 폭발한다.** 좌표를 내놓는 것을
  둘(`geocode_place` · `get_railway_section`)로, 식별자를 내놓는 것을
  하나(`find_admin_boundary_by_point`)로 묶어 48개에 그쳤다. 인구 통계 조회가
  설명대로 지도 범위를 내놓게 했으면 그 뒤에 지도 범위를 받는 열 개가 붙는다.

#### 다시 시도하지 말 것

- **대상별로 타입을 나누기** — "선거구 목록" · "충전소 목록" 처럼 나눠도 경로
  생성은 그대로다. 무엇에 관한 목록인지는 `about` 이 이미 말한다. 타입만
  대상 수만큼 곱해진다.
- **계열(`election` · `population` …)마다 대상 노드 만들기** — `road.getCctv`
  와 `rail.getSectionGeometry` 를 가르면 "철도 구간을 찾아 그 범위의 CCTV 를
  본다" 가 `crosses_groups` 에 걸려 죽는다. 범용 도구(`geo.geocode` 등 아홉)에
  `about` 을 붙이면 지금 유일하게 돌던 경로도 함께 죽는다.

---

### 2026-08-19 · qwen2.5:7b -> qwen3:8b

`llm_engine/ollama.py` 의 기본 모델을 옮기고, `reason` 을 짧게 묶었다.

**옛 측정이 재현되지 않았다.** 1번 발화가 10/10 -> 0/10. 저장소는 안 바뀌었다
(프롬프트 2026-08-11 이후, `_init` 2026-08-15 `6bf034a` 이후 불변, 모델 digest
동일, 작업 트리가 커밋 상태와 일치). 원인을 저장소 안에서 못 찾았다.

**모델** (recipe 6 · 각 10회 · 1번 · 2번 · 3번 발화)

```
qwen2.5:7b     0/10  10/10  10/10
qwen3:4b      10/10   0/10   0/10   2번을 부순다
qwen3:14b       —      —      —     183초. urlopen timeout(180)을 넘긴다
qwen3:8b      10/10  10/10  10/10   <- 골랐다
```

**reason 이 무한 반복에 빠진다 — 시간만이 아니라 답을 망친다.**
qwen3:8b 가 3번 발화에서 recipe id 나열을 되풀이한다
("recipe_002와 recipe_007, recipe_003, recipe_007, recipe_008가" 반복).
상한이 없으면 5/5 가 202초에 끊겼다. 근거에 recipe_003 을 적어놓고 후보에서
뺐다 — 목록을 끝맺지 못한 채 후보 필드를 반쪽만 채운다.

`maxLength` 를 200 · 400 · 600 으로 바꿔 재니 셋 다 정확히 상한까지 채웠고 답이
똑같았다(모두 오답). 상한이 근거를 잘라 판정을 깎는 것이 아니라 어차피 무너진
근거를 자를 뿐이다. 그래서 제일 짧은 200 을 쓴다 (30초 · 50초 · 70초).

**reason 에 Recipe ID 를 못 쓰게 하니 루프와 판정이 함께 풀렸다.**
되풀이할 재료가 사라진다. reason 이 200자(상한 도달) -> 44~60자가 되고 응답도
30초 -> 18초로 줄었다. 3번 발화가 0/10 -> 10/10.
"하나 찾아도 멈추지 말고 Menu 끝까지 훑어라" 를 더한 변형도 15/15 로 같아서
넣지 않았다. ID 금지만으로 충분하다.

**확정** (recipe 6 · qwen3:8b · 1~3번 10회 · 4번 5회) — 10/10 · 10/10 · 10/10 · 5/5

#### 다시 시도하지 말 것

- **menu 를 steps 목록으로 펼치기** — 10/30 -> 0/30. 끝점을 마지막 항목으로
  만들어 "부재 판정" 을 "위치 판정" 으로 바꾸려 했는데 반대로 갔다. 목록으로
  펼치니 공통 앞토막(대상 · 프레임 추출 · 분석)이 글자 그대로 반복돼 도드라지고,
  대상 매칭이 끝점 매칭을 덮었다. 멀쩡하던 2번이 10/10 -> 0/10.
  크기는 문제가 아니었다 (steps 형식 1073자 · `MENU_BUDGET` 6000).
  `test_registry` 가 적어둔 거절 사유(context 초과)는 function 을 **남긴 채**
  steps 를 더할 때의 얘기다. 교체는 크기로는 안전하다.
- **menu 를 대상별로 묶기** — 모델에 따라 반대로 작용한다. 007(승강장 Excel)이
  궤도 recipe 셋에 가로막혀 형제와 떨어져 있으면 밀린다.
  qwen2.5:7b · recipe 8 에서는 끝에 두면 `{002,003}` 10/10 (007 빠짐),
  승강장 묶음 안에 두면 `{002,003,007}` 10/10 이었다.
  그런데 qwen3:8b 에서는 묶으면 오히려 `{002,007}` -> `{002}` 로 나빠졌다.
- **`repeat_penalty` 1.2** — 반복은 멎지만 판정까지 깎여 3번 발화가 후보 둘에서
  하나로 좁아진다.

#### 환경

이 기계는 CPU 로만 추론한다. **5.9 tok/s.** `nvidia-smi` 없음 · `/api/ps` 의
`size_vram` 0. RAM 16.4GB. 모델이 여럿 올라가 있으면(`keep_alive` 2h) RAM 을
넘겨 스와핑이 난다 — 실험 사이에 안 쓰는 모델을 내려야 시간이 안 튄다.

---

### 2026-08-15 · qwen2.5:7b (`4a55c44` ~ `e8fcdc2`)

따로 적지 않았으면 `_init` recipe 6 기준.
**이 구역은 전부 qwen2.5:7b 로 잰 것이다. 지금 모델의 성질이 아니다.**

**형식은 발화와 menu 의 표기가 글자 그대로 겹칠 때만 갈린다.**

```
"워드"          0/10   menu 는 "Word"
"Word 문서로"   9/10
"Word로"        9/10   오답이 {004,005} 로 바뀐다 — 형식이 아니라 길이가 갈린다
```

menu 에 "Word(워드)" 로 두 표기를 함께 담는 것은 안 들었다 (0/10).

**숫자 + "번" 이 붙으면 무너진다.**

```
"3번 승강장에 …"      0/5
"동대구역 승강장에 …"  5/5
"지금 승강장에 …"      4/5
"승강장에 …"          5/5
```

역명도 시각도 통한다. "3번" 만 다르다 — recipe 번호로 읽히는 것으로 보인다.

**끝점은 동사가 정한다.** `"…봐줘"` 9/10 (10에 1번 문서까지 끌고 간다) ·
`"…분석해줘"` 10/10.

**NO_MATCH 는 영역으로 갈린다. 어휘 겹침이 아니다.**

```
"오늘 지하철 요금 알려줘"          5/5   영역 밖
"CCTV 화면이 뿌옇지 않은지 봐줘"    0/5   영역 안이라 뭐라도 집는다
"화면이 뿌옇게 나오는데 확인해줘"   0/5   겹치는 어휘가 없는데도 마찬가지
```

**앞토막 recipe 는 판정을 무너뜨린다** (`e8fcdc2`).

```
recipe 6개                          35/35
+ 앞토막 둘 (데이터 → 프레임 추출)     5/35
+ 프롬프트를 절차형으로 전환           25/45
```

앞토막이 다른 모든 recipe 에 포개져 "어디서 끝나는가" 를 못 가른다. 프롬프트로
절반은 회복되지만 나머지를 못 채우고, 조일수록 끝점을 모호하게 말하는 발화가
대신 무너진다 (`"…봐줘"` 9/10 -> 0/5).

**프롬프트를 절차로 나누면 판정이 나아진다.** 규칙 셋을 동시에 저울질하는 대신
순서 있는 단계로 쪼갠 것. 샘플 셋이 0/10 -> 10/10 이 됐고 시연에 안 쓰는 발화도
9/10 -> 5/5 로 올랐다. 다만 recipe 8개에서도 2번 발화를 못 채워 되돌렸다.
recipe 가 늘어나면 다시 꺼낼 카드다.

**확정** (각 10회 · NO_MATCH 는 5회) — 10/10 · 10/10 · 10/10 · 5/5

**샘플 목록(`sample_picker.SAMPLES`)에서 무엇이 빠졌나.**
형식을 지정해 하나로 좁히는 발화가 없다. `"Word로 만들어줘"` 가 9/10 이라 뺐다.
그래서 이 목록만으로는 "형식을 밝히면 하나가 된다" 를 못 보여준다. 필요하면
발표자가 직접 `"궤도 균열 확인한 거 Word로 만들어줘"` 를 친다 — 10에 1번은
`{004, 005}` 로 갈린다.
`recipe_005` · `recipe_006` 은 이 목록으로는 한 번도 안 켜진다.
