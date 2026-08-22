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
| `workflows/static/prompts/recipe_selection.md` 축 목록 | id + 이름 + 설명 730자 | 채운 프롬프트가 7133자다. `num_ctx` 는 32768(토큰) 이라 지금은 여유가 있다 — 옛 근거(8192 · 6758자)는 2026-08-21 측정 기록 쪽에 날짜와 함께 남아 있다. 선택지를 늘릴 때 다시 재는 것은 그대로다 |
| `ontology/registry.py` `MENU_BUDGET` | `6000` | 근거가 낡았다. `num_ctx` 8192 시절 값이고 지금은 32768 이다. 프로덕션에서 읽는 곳이 0 이고 테스트 하나가 보는 회귀 방지선이다 (`registry.py` 주석). 올릴 이유도 없다 — 진짜 제약은 컨텍스트 크기가 아니라 문장 변별력이다. menu 문장의 앞 30자가 23개나 같아서 shortlist 를 만들었다. 자수를 늘리면 오히려 나빠진다. 개편에서 잴 것은 자수가 아니라 "앞토막이 같은 문장 수" 다 |
| `ontology/registry.py` `MAX_STEPS` | `4` | 같은 성격이다. `registry.py` 주석이 스스로 "임시방편이다. 경로 길이가 문제가 아니라 말이 안 되는 조합이 섞이는 것이 문제" 라고 적고 있고, 그 조합 문제는 온톨로지 개편이 푼다. 개편에서 다시 본다 |
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
- **`STEP_OF` 의 headline 이 완결된 한국어 문장이라 부정형을 못 만든다.**
  `"{arg} 행정구역을 조회했습니다."` 같은 문형이라 0건일 때 `"…조회하지
  못했습니다."` 로 바꾸려면 어미를 문자열로 잘라야 한다. 문형이 하나 늘 때마다
  자르는 규칙이 하나 늘어 안 했다. 지금은 `workflow_answer` 가 빈 결과 · 오류일
  때 headline 을 통째로 버리고 `"찾지 못했습니다." / "조회하지 못했습니다."` 만
  쓴다 — 무엇을 조회하려던 것인지는 단계 줄이 말한다.
  headline 을 명사형(`"{arg} 행정구역"`)으로 바꾸면 성공 · 빈 결과 · 오류 셋을
  한 문장 틀로 합칠 수 있다. `STEP_OF` 48줄을 다시 쓰는 일이라 이번에 안 했다.

### 배선이 온톨로지의 선언을 반만 따른다 — 34개 중 13개

노드 아홉이 입력 타입을 **둘** 선언했는데 `STEP_OF` 는 노드 하나당 한 줄이라
하나만 적을 수 있다. 어느 쪽을 골랐느냐에 따라 오류가 거울처럼 갈린다.

```
                                   선언              배선이 고른 쪽
search_admin_boundaries            keyword+extent     keyword
get_vworld_boundaries              keyword+extent     keyword
get_railway_lines                  place_name+extent  place_name
search_assembly_districts          keyword+extent     keyword
search_assembly_pledge_districts   keyword+extent     keyword
search_local_pledge_summaries      keyword+extent     keyword
search_population_statistics       keyword+extent     keyword
search_ev_stations                 keyword+extent     extent
search_ev_chargers                 keyword+extent     extent
```

**A. 발화 인자를 버린다 (2개).** 첫 실행 노드인데 배선이 `$prev` 만 쓴다.

```
recipe_012  말한 키워드 -> search_ev_stations   ev.searchStations
recipe_013  말한 키워드 -> search_ev_chargers   ev.searchChargers
```

`_filled` 이 앞 단계 없는 `$prev` 칸을 빼므로 `{"radiusMeters": 15000}` 만
나간다. bbox 넷이 전부 optional 이라 오류 없이 전국 검색이 된다.

```
발화        "청주오스코 충전소 알려줘"
나가는 것    {"radiusMeters": 15000}      키워드가 사라졌다
```

`ev.searchStations` 스키마에 칸이 있다 (`KRRI_ASAP/ASAP-mcp/main.py:532`).

```
"query": { "type": "string", "description": "충전소명, 주소, 운영기관 키워드" }
```

**B. 앞 단계 결과를 안 쓴다 (11개).** 앞 단계가 있는데 배선이 `@arg` 만 쓴다.

```
recipe_022  geocode_place       -> search_admin_boundaries
recipe_024  geocode_place       -> get_vworld_boundaries
recipe_026  geocode_place       -> get_railway_lines
recipe_028  geocode_place       -> search_assembly_districts
recipe_030  geocode_place       -> search_assembly_pledge_districts
recipe_032  geocode_place       -> search_local_pledge_summaries
recipe_034  geocode_place       -> search_population_statistics
recipe_037  get_railway_section -> search_admin_boundaries
recipe_038  get_railway_section -> get_vworld_boundaries
recipe_040  get_railway_section -> get_railway_lines
recipe_041  web_search          -> web_fetch
```

recipe_022 가 화면에서 CLARIFY 후보로 나온 그것이다.

```
menu 문장   "말한 장소로 위치 좌표와 지도 범위를 찾고, 이름이나 코드, 지도
             범위로 시도와 시군구, 읍면동 경계를 조회한다."
실제        s1 geo.geocode                    {"query": "오송역"}
            s2 adminBoundary.searchBoundaries {"query": "오송역"}   앞 결과를 안 쓴다
```

geocode 를 부르고 버린다. 행정구역 DB 에 "오송역" 이라는 경계 이름이 없으니
0건이다. **menu 문장이 약속한 것과 실행되는 것이 다르다.**

B 가 전부 틀린 답인 것은 아니다.

```
낭비일 뿐    recipe_026  getRailwayLines(stationName="오송역")
             stationName 에 역 이름은 맞는 값이다. geocode 단계만 헛돈다
명백히 틀림  나머지 열.  역 이름 · 구간 이름을 경계 · 선거구 · 인구 검색어로 보낸다
             recipe_041 은 web_fetch 의 url 자리에 발화 인자를 넣는다.
             검색 결과에서 URL 을 꺼내야 맞다
```

**지금 고치지 않는다.** 한 줄을 채우면 반대쪽이 깨진다. 제대로 된 답은 배선을
노드별이 아니라 **간선별**(무엇에서 무엇으로)로 적는 것이고, 개편의
「도구를 온톨로지에 넣을 것인가」와 같은 결정이다.

**설명도 함께 빠졌다.** `search_ev_stations` 의 `description` 이 "지도 범위와
지역, 충전기 유형으로 전기차 충전소를 검색한다" 라 키워드로 찾는다는 말이 없다.
도구 description 을 옮기며 빠진 것이다. 개편에서 description 을 다시 쓸 때
**도구 `inputSchema` 의 입력 칸을 전부 훑어 빠진 능력이 없는지 본다.**

**세 층 중 관계만 맞았다.** 관계(hasInput 둘)는 정확했고 그 덕에 경로가 생겼다.
못 따라간 것은 파생물 둘(`description` · `STEP_OF`)이다.

### 화면 실측으로 셋이 한꺼번에 보였다 (2026-08-23 · 1회)

```
발화    "청주오스코 충전소 알려줘"
결과    SELECT recipe_048
        말한 장소 -> 장소 좌표 변환 -> 지점 행정구역 판별 -> 충전소 상세 조회
답      "충전소 상세 조회 기능이 아직 붙지 않아 실행할 수 없습니다."
        도구를 하나도 안 불렀다 (resolve 한 단계만)
```

**recipe_012 를 못 골랐다.** 그 menu 문장에 이름으로 찾는다는 말이 없다.
그래서 A 부류 둘은 "틀리게 도는" 것이 아니라 **도달 자체가 안 되는 죽은 능력**에
가깝다. 실제로 사용자에게 보이는 오류는 B 부류다.

**recipe_048 이 뽑혔다.** 「적을 수 없었던 경로」의 가짜 넷 중 하나다.
`find_admin_boundary_by_point` 가 내놓는 행정구역 코드와 `ev.getStation` 이 받는
충전소 번호를 온톨로지가 같은 `식별자` 타입으로 묶어 생긴 경로다.
`given` 이 `spoken_place` 로 갔다 — "청주오스코" 를 장소로 읽었고, `place_name`
이 지명 · 역 이름 · 구간 이름을 다 삼키는 문제와 같은 뿌리다.

**`unwired` 가 막았다.** "오송시" 사례와 정반대다. 그쪽은 전부 성공해서 틀린
답이 나갔고 이쪽은 정직하게 못 한다고 말했다. 반쪽 실행을 막아둔 판단이 값을
했다.

**1회다.** 반복해서 재지 않았으므로 비율로 읽으면 안 된다.

### 「찍은 지점」 시작 데이터 노드가 없다

저쪽 화면은 지도에서 찍은 점을 `context.selectedLocation` 으로 보내고 저쪽
프롬프트는 `$context.selectedLocation.lon` 을 쓴다. 우리는 그 칸을 안 읽는다.
그래서 "이 근처 CCTV 보여줘" 를 못 한다. 시작 데이터 노드를 더하면 `find_cctv`
가 혼자 첫 노드로 불리는 진짜 경우가 생기고, 그때 `$prev` 자리에 `$context` 가
들어가야 한다. 위 간선별 배선과 같은 자리에서 풀린다.

### 경로와 배선이 맞는지 세는 검사가 없다

recipe 를 배선표와 맞대어 A · B 를 세면 13개가 나온다. 스무 줄이면 된다.
개편 때 `tools/` 에 넣는다. 세는 규칙은 이렇다.

```
배선이 다 있는 recipe 만 본다 (unwired 가 빈 것)
첫 실행 노드인데 input 이 $prev 만 쓴다        -> A
앞 실행 노드가 있는데 input 이 @arg 만 쓴다    -> B
```

---

## 측정 기록

### 2026-08-23 · 어미가 판정을 가름 · recipe 48 · qwen3:32b · 각 1회

같은 뜻인데 갈렸다. 화면에서 한 번씩 쳐본 것이다.

```
  발화                        결과
  오송역 행정구역 보여줘      CLARIFY {recipe_022, recipe_023}
  오송역 행정구역 조회        SELECT recipe_023. 끝까지 실행되어 0건
```

**각 1회뿐이다.** 반복해서 잰 것이 아니므로 비율로 읽으면 안 된다.

옛 기록 「끝점은 동사가 정한다」(2026-08-15 · qwen2.5:7b · recipe 6)와 같은
성질이다. 그때는 `"…봐줘"` 9/10 · `"…분석해줘"` 10/10 이었다. recipe 48 ·
qwen3:32b 에서도 어미가 여전히 판정을 가른다. 옛 기록은 조건이 달라 그대로 둔다.

관찰 하나. 이번 CLARIFY 는 후보 둘(`recipe_022` · `recipe_023`)이 모두 행정구역
이고 reason 도 행정구역이라 서로 어긋나지 않았다. 예전에 후보와 reason 이
어긋나던 사례와는 발화가 다르므로 개선이라고 단정하지 않는다. 그 사례는 NOTES 에
기록이 없어 맞대볼 것도 없다.

### 2026-08-22 (넷째) · 답 문구 넷을 고침 · 실행 없이 trace 로 확인

화면 실측 넷을 고쳤다. 서버를 안 띄우고 실측 응답 모양으로 trace 를 손으로
만들어 `compose_workflow_answer` 를 직접 불러 문자열만 봤다.

```
  발화                          before                                after
  오송역 행정구역 알려줘        오송역 행정구역을 조회했습니다.       찾지 못했습니다.
                                (features 0개인데 성공 문구)          + "2. … 0건"
  오송시 cctv 보여줘            오송시 → 128.5944, 34.8225            오송시 → 경상남도 남해군
                                                                      삼동면 동천리 (128.5944, …)
  오송역 근처 충전소 찾아줘     {"count": 100, "totalMatches": 21…    100건 (전체 2,195건)
  철도 안전 문서 찾아줘         500 원문 + localhost:3000 URL         실패 · 이 도구를 쓸 권한이
                                + Gateway 응답 본문                   없습니다
  대전~김천 구간 CCTV 보여줘    s2 단계 필수 입력값이 비어 있습…      실패 · 필수 입력값이 비어
                                (단계 목록 없음)                      있습니다: minLon, minLat, …
  오송역 좌표 알려줘            오송역 → 127.3277, 36.6200            + 주소가 붙음. 나머지 그대로
```

**제일 나쁜 것은 두 번째였다.** `"오송시"` 는 없는 지명인데 `geo.geocode` 가
경상남도 남해 근처(128.5944, 34.8225)를 찍고 `road.getCctv` 가 거기 CCTV 2건을
진짜로 받아왔다. 두 호출 다 성공이라 어느 칸을 봐도 실패가 아니다. 좌표만
보이면 사람이 못 알아채므로 **주소를 반드시 답에 넣는다** — `geo.geocode` 응답에
`address` 가 이미 있다 (`asap_probe_out/geo.geocode.osong.json`).

**오류 분류를 문자열이 아니라 항목의 구조로 갈랐다.** vendor 의 한국어 문구
(`_friendly_workflow_tool_error` 셋)에 기대면 저쪽이 갱신될 때 조용히 깨진다.
trace 항목이 가진 것으로 가른다.

```
  error_detail 있음   도구 호출 자체가 터진 것. 원문을 화면에 안 낸다.
                      vendor 가 이미 logger.error 로 남겼다
  error_detail 없음   우리가 입력을 못 채운 것. vendor 문장에 필드 이름밖에
                      없어 그대로 보여도 안전하다. "{step_id} 단계 " 접두만 뗀다
```

영어 조각을 문자열로 보는 곳은 한 줄뿐이다 — `error_detail` 안의
`"is not applied for this user"`. 실측 : `web-search/web.search` 를 부르면
Gateway 가 500 과 함께 `"MCP tool 'web-search/web.search' is not applied for
this user."` 를 돌려준다. 권한이 없는 것은 잠깐 터진 것과 다르고 사용자가
알아야 할 사실이라 따로 뺐다.

**판정을 `errors` 만으로 못 한다.** Gateway 는 실패를 `200` + `{"error": {...}}`
로도 돌려주고(`asap_probe_out/geo.geocode.english_notfound.json`), `mcp_client`
가 예외를 안 올리므로 vendor 는 그것을 성공한 호출로 보고 `answer_draft` 에
성공 문구를 적는다. 그래서 판정이 `workflow_answer` 안에 있다.

**`_preview()` 를 지웠다.** JSON 을 화면에 내보내던 유일한 자리였다. 모르는
결과는 이제 최상위 칸 이름만 여섯 개까지 보여준다 (`칸: type · coordinates`).

**남은 것 하나.** 도구 이름이 18자를 넘으면 `TOOL_COLUMN` ljust 가 안 벌어져
요약과 붙는다 (`adminBoundary.findBoundaryByPoint0건`). 고치기 전에도 같았고
(`…findBoundaryByPoint{"features": …`) 이번 범위가 아니라 안 건드렸다.

#### 정정 (같은 날, 커밋 전 마무리)

**「남은 것 하나」의 ljust 문제를 이 커밋에서 함께 고쳤다.** `TOOL_COLUMN` 을
넓히지 않고 `TOOL_GAP = 2` 를 두어 최소 간격을 보장한다 —
`tool.ljust(TOOL_COLUMN - TOOL_GAP)` 뒤에 두 칸을 다시 붙인다. `TOOL_COLUMN` 을
가장 긴 이름(42자 · `election.findAssemblyPledgeDistrictByPoint`)에 맞추면 짧은
이름 쪽이 스무 칸 넘게 빈다. 짧은 이름의 정렬은 한 칸도 안 달라진다
(11 + 5 + 2 = 18).

```
before  adminBoundary.findBoundaryByPoint0건
after   adminBoundary.findBoundaryByPoint  0건
```

**`_verdict` 가 마지막 항목만 보던 것을 항목 전부를 훑는 것으로 바꿨다.**
`_execute_generic_mcp_workflow` 는 중단할 때 대개 trace 에 아무것도 안 남긴다 —
조기 반환 열한 곳 중 아홉이 append 없이 `_failed_workflow_result` 로 나가고,
그중 일곱은 trace 마지막이 "성공한 앞 단계" 다. 그러면 `errors` 가 차 있는데도
마지막 항목은 성공으로 읽힌다.

지금 그 구멍이 안 터지는 것은 우연이다. `_resolve_reference` 가 예외 대신 None
을 돌려주고, `step_service.plan` 이 중심 좌표가 없으면 어댑터를 안 걸고, vendor
의 허용 검사가 web-search 를 통과시킨다. 셋 다 다른 파일이라 판정이 거기 기대면
안 된다. 그래서 둘을 함께 했다.

```
compose_workflow_answer(intent, trace, *, failed=False)
    failed 는 키워드 전용이고 기본이 거짓이라 vendor 호출부는 안 바뀐다.
    execute_service._answer 만 failed=True 로 부른다 (errors 가 있을 때만 도달)
_verdict          항목 전부를 훑는다. 어느 항목이든 error 칸이나 200 오류면 ERROR
건수 0 판정        마지막 항목으로 남겼다. 발화에 답하는 것은 마지막이다
```

전부를 훑는 또 하나의 이유 : 중간 단계가 `200` + `{"error": ...}` 로 돌아오고
다음 도구가 그 칸을 optional 로 받으면 vendor 는 끝까지 돌고 `errors` 도 비어
있는데 결과는 쓰레기다. 마지막만 보면 EMPTY 나 SUCCESS 가 된다.

#### 정정 2 (2026-08-23 화면 확인)

**"오송시" 가 찍은 곳은 남해가 아니라 거제다.** 위 문단들에 「경상남도 남해」로
적힌 것은 좌표만 보고 우리가 짐작해 쓴 것이다. 좌표(128.5944, 34.8225)는 맞았고
주소가 틀렸다. 실측은 이렇다.

```
오송시 → 경상남도 거제시 동부면 오송리 143-2   (128.5944, 34.8225)
```

**거제시에 실제로 「오송리」가 있다.** `geo.geocode` 가 헛짚은 것이 아니라 가장
비슷한 실제 지명을 정직하게 돌려준 것이다. 좌표도 주소도 CCTV 2건도 전부
사실이고, 어느 층에도 버그가 없는데 답이 틀렸다. **없는 지명("오송시")을 실재하는
다른 지명("오송리")과 갈라줄 어휘 층이 없다는 뜻이다.** 「미뤄둔 것 — 어휘 층」의
첫 실제 사례다.

주소를 답에 넣은 것은 그래서 더 필요했다. 버그가 없으므로 판정으로는 영영 못
잡고, 사람이 주소를 읽고 아는 수밖에 없다.

**저쪽 화면이 연속 공백을 접는다.** 답이 마크다운 번호 목록으로 렌더되면서
공백이 한 칸으로 줄어든다 (실측).

```
코드가 내는 것   1. geo.geocode       오송시 → …
화면에 뜨는 것   1. geo.geocode 오송시 → …
```

즉 `TOOL_COLUMN` 의 정렬은 저쪽 화면에서 원래부터 안 보이고 있었다. 그래도
`TOOL_GAP` 은 필요했다 — 공백이 0개면 접을 것이 없어 `…ByPoint0건` 이 한 낱말로
그대로 남는다. 2개가 1개로 접히면서 낱말이 갈린다. 코드는 그대로 둔다.

답 형식을 다시 볼 때는 `TOOL_COLUMN` 을 없애고 눈에 보이는 구분자를 쓰는 편이
낫다. 지금 폭 맞추기는 화면에서 아무 일도 안 하면서 상수 둘을 유지하게 한다.

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

#### 정정 (2026-08-23)

- **「온전히 도는 것 24」는 "도구를 다 부른다" 는 뜻일 뿐이다.** 배선이 다 있는
  34개 중 13개가 온톨로지의 선언과 어긋나게 돈다 (위 열린 과제 A · B).
- **왜 안 보였는지 셋.** `unwired()` 가 "`STEP_OF` 에 줄이 있느냐" 만 보고 "그
  줄이 이 경로에 맞느냐" 는 안 본다 / 도구들이 관대해서 오류가 안 난다
  (`ev.searchStations` 는 bbox 넷이 optional, `searchBoundaries` 는 query 가 안
  맞으면 그냥 0건) / 어긋난 recipe 대부분이 화면에서 한 번도 안 켜졌다.
- **당시 적용한 규칙이 원인이다.** 이 기록에 "좌표를 받는 도구와 이름을 받는
  도구만 적었다" 고 있다. 도구를 둘 중 하나로 분류해 적었는데 아홉 개는
  둘 다였다.
- **저쪽에는 EV 배선이 아예 없다.** `ASAP-orchestrator/plugins` 12개와
  `harnesses` 3개에 EV 관련이 하나도 없다. 저쪽 전체에서 `ev.searchStations` 가
  나오는 곳은 프롬프트 예시 한 줄뿐이고 (`generic_mcp_executor.py:55`) 거기에도
  좌표 경우만 있다. 키워드 경우는 Gemini 가 `inputSchema` 를 읽고 스스로 쓴다.

```
저쪽   배선을 안 적는다      될 때도 있고 안 될 때도 있다. 재현이 안 된다
우리   한 줄로 적었다        늘 같게 돈다. 그 한 줄이 틀리면 늘 틀린다
```

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
