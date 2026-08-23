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

### 막힌 노드 여덟과 그것이 지나는 recipe 18개 (2026-08-23 실측)

recipe 가 될 수 있는 노드 28개 중 여덟이 데이터가 없거나 권한이 없다.
recipe 48개 중 18개가 그 여덟 중 하나를 지난다.

```
search_admin_boundaries             0건   shapefile 원본이 저장소에 없다
find_admin_boundary_by_point        0건   같은 이유.  ★ 이것 하나가 일곱을 막는다
                                          042 043 044 045 046 047 048
search_documents                    0건   지식베이스에 문서가 0개
search_local_pledge_summaries       0건   2026 지방선거 공약 미적재
get_local_pledge_summary            0건   같은 데이터셋
find_local_pledge_summary_by_point  0건   같은 데이터셋
web_search                          권한   user_context 에 web-search 가 안 열려 있다
web_fetch                           권한   같은 서버.  안 눌러봐서 추정이다

막힌 노드를 지나는 recipe 18개
  004 006 010 014 018 022 023 032 033 037 041 042 043 044 045 046 047 048
```

**전부 저쪽 데이터이고 우리가 못 채운다.** 오늘 철도가 보여준 대로, 채워지면
코드를 한 줄도 안 고치고 그대로 돈다 — `import_railways.py` 한 번에
`rail.sections` 2,243건이 들어가자 `rail.getSectionGeometry` 가 답하기 시작했다.

**조대표님께 여쭐 것.** `import_admin_boundaries.py` 는 `--source-root` 로
shapefile 폴더를 받는데 그 `.shp` 원본이 저장소에 없다(`find` 로 0개).
그것만 받으면 일곱이 살아난다.

**이 여덟은 개편이 못 고친다.** 개편이 고치는 것은 "경로가 진짜인가" 이고
이것은 "데이터가 있는가" 다. 층이 다르다.

이 여덟이 0건일 때 그 이유는 이제 답에 실린다 — `workflow_answer` 가
0건이면서 `warning` · `message` 가 온 응답의 그 문장을 건수 뒤에 붙인다.
`knowledge.query` · `knowledge.listDocs` · `bim.listModels` 셋은 응답이 `[]`
하나라 실릴 자리가 없어 "0건" 까지만 나온다.

### 화면 실측으로 셋이 한꺼번에 보였다 (2026-08-23 · 1회)

```
발화    "청주오스코 충전소 알려줘"
결과    SELECT recipe_048
        말한 장소 -> 장소 좌표 변환 -> 지점 행정구역 판별 -> 충전소 상세 조회
답      "충전소 상세 조회 기능이 아직 붙지 않아 실행할 수 없습니다."
        도구를 하나도 안 불렀다 (resolve 한 단계만)
```

**recipe_012 를 못 골랐다.** 그 menu 문장에 이름으로 찾는다는 말이 없다.

> **정정 (2026-08-23 밤, 기준선 측정).** 바로 위 두 문장 중 "죽은 능력" 이라는
> 판단은 틀렸다. 발화 7 "전기차 충전소 데이터 검색해줘" 가 `{012, 013}` 을
> 10/10 으로 후보에 올렸다.
>
> ```
> recipe_012 는 후보에는 오른다. 다만 recipe_013 과 영원히 비겨 SELECT 가 안 된다.
> 사람이 CLARIFY 에서 1번을 골라 실행하는 길이 생기면 그때 인자를 버리는 것이
> 실제로 보이게 된다. "죽은 능력" 이 아니라 "아직 안 드러난 오류" 다.
> "청주오스코 충전소 알려줘" 가 recipe_048 로 간 것과는 별개의 사실이다.
> ```
>
> 따라서 "실제로 사용자에게 보이는 오류는 B 부류다" 도 반만 맞다. A 부류는
> 안 보이는 것이 아니라 CLARIFY 에 가려 아직 안 보인 것이다.

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

### 2026-08-23 (일곱째) · 온톨로지 개편 8안을 실제로 넣음 · 네 커밋

**왜 했는가.** 여섯째 항목에서 8안이 확정됐다. `record_key`("식별자") 하나가
자릿수도 발급처도 다른 값 셋을 묶고 있었고, 그래서 행정구역 코드가 충전소
상세로, 충전소 번호가 연령별 인구 구성으로 흘러가는 **가짜 경로 넷**이
만들어졌다 — 실행하면 반드시 터지는 경로다.

```
행정구역 코드   43113 (5자리).  find_admin_boundary_by_point 가 내놓는다
선거구 코드     4311101 (7자리)
충전소 번호     ev_station_PW012325.  ev.searchStations 도 내놓는다
```

3안(말한 식별자를 코드 하나에만 거는 것)은 018~021 을 함께 죽인다.
8안은 말한 식별자에 코드 셋 모두를 걸어 그 넷을 살리고 가짜만 없앤다.

네 커밋으로 나눴다. 판정이 달라졌을 때 무엇 탓인지 갈리게 하려는 것이다.

```
08e8a8e  0건일 때 그 이유를 답에 적는다              개편 전에 있던 것
2f8b926  식별자 타입을 셋으로 쪼개 가짜 경로 넷을 없앤다
ce13dfb  GT 를 개편 뒤 번호로 옮긴다
(이 커밋) 배선을 노드와 입력 타입의 짝마다 한 줄로
```

되돌리는 길은 `git reset --hard before-ontology-rework` 하나다.

#### ① 온톨로지를 쪼갠 전후

**시뮬레이션 숫자와 실제가 한 자리도 다르지 않았다.**

```
                    여섯째의 시뮬레이션    실제
남은 recipe         48개                   48개
전체 경로           56개 · 버림 8개        56개 · 버림 8개
menu.yaml           약 4,267자             4,268자 (MENU_BUDGET 6000)
```

recipe 번호 대응표 전문. **041 까지는 그대로이고 042 부터 밀렸다.**

```
새 번호     옛 번호      경로
001~041     같음         (변화 없음)
042         (새것)       말한 키워드 → 전기차 충전소 검색 → 충전소 상세 조회
043         (새것)       말한 키워드 → 전기차 충전기 조회 → 충전소 상세 조회
044         045          말한 장소 → 좌표 → 지점 행정구역 판별 → 지방선거 교통 공약 상세
045         046          말한 장소 → 좌표 → 지점 행정구역 판별 → 연령별 인구 구성 조회
046         047          말한 장소 → 좌표 → 지점 행정구역 판별 → 인구 변화 추이 조회
047         (새것)       말한 장소 → 좌표 → 전기차 충전소 검색 → 충전소 상세 조회
048         (새것)       말한 장소 → 좌표 → 전기차 충전기 조회 → 충전소 상세 조회

사라진 넷   옛 042 · 043 · 044 · 048.  전부 가짜다
살아남은 것 025(좌표 → CCTV) · 039(철도 구간 → CCTV) · 018~021(말한 식별자 2단)
```

새로 생긴 넷의 근거는 `ev.searchStations` 응답의 `items[0].id` 다. 검색이
충전소 번호를 내놓으므로 검색 → 상세가 진짜 경로다.

`pytest` 173 passed / 1 failed. 실패 1건은 graphviz 버전 차이에서 오는 음성
대조군이고 개편과 무관하다.

#### ② GT 를 새 번호로 옮긴 뒤의 세 묶음

**기대값은 한 글자도 안 바꿨다. 번호만 옮겼다.** 사슬이 같은 recipe 를 찾아
그 새 번호를 넣었다. 사라진 사슬은 없다. 움직인 것은 발화 4 하나뿐이다
(`recipe_046` → `recipe_045`).

```
발화                        기준선(밤)   개편 뒤
1 오송역 위치 보여줘        10/10        10/10
2 오송역 좌표 알려줘        10/10        10/10
3 오송역 CCTV 보여줘        10/10        10/10
4 청주시 인구 구성 알려줘   10/10         0/10   ★ 떨어졌다
5 오송역 근처 충전소 찾아줘  0/10         1/10   ★ 올랐다
6 국회의원 선거구 찾아줘     0/10         0/10
7 전기차 충전소 데이터 검색  0/10         0/10
8 철도 안전 문서 찾아줘      0/10         0/10
9 충북 제1선거구 알려줘     10/10        10/10
                            ─────        ─────
                            50/90        41/90
                            56%          46%

qwen3:32b · 발화 9개 × 10회 · _init(recipe 48) · 묶음 셋
세 묶음이 md5 까지 같다. 기준선도 그랬다.
```

**판정이 열 점 떨어졌다. 전부 발화 4 한 건이다.**

```
            LLM 후보 수   조회 후보 수   status
기준선      1             3              SELECT   10회
개편 뒤     3             3              CLARIFY  10회
```

**조회 후보 수는 3 으로 그대로다.** 온톨로지가 후보를 넓힌 것이 아니다.
LLM 이 `{034, 045, 046}` 을 셋 다 내놓아 SELECT 가 CLARIFY 로 바뀌었다.
셋은 인구 통계 조회 · 연령별 인구 구성 · 인구 변화 추이이고 "인구 구성" 이라는
말만으로는 실제로 갈리지 않는다. menu 문장의 번호가 바뀌면서 LLM 이 다르게
답한 것으로 본다.

발화 6 의 튀는 한 번은 후보 14개에서 3개로 줄었다(`{007, 008, 009, 015, 016,
017, 027, 028, 029, 030, 031, 042, 043, 044}` → `{007, 008, 009}`).
발화 7 의 조회 후보 수는 2 에서 4 로 늘었다.

**숫자를 좋게 만들려고 기대값이나 규칙을 고치지 않았다.** 이것이 개편 직후의
사실이다. `description` 을 사람이 손보면 다시 잰다.

#### ③ 배선을 (노드 × 입력 타입)당 한 줄로

`STEP_OF` 가 노드당 한 줄이라 같은 노드가 두 자리에 올 때 한쪽을 버렸다.
키를 `(노드 id, 입력 타입 id)` 로 바꾸고 온톨로지의 `hasInput` 선언과 1:1 로
맞췄다. 도구 이름과 답 첫 줄은 노드당 하나이므로 `TOOL_OF` 로 갈랐다 — 한 표에
두면 줄마다 복사된다.

```
                          전         후
TOOL_OF (노드)            —          21줄
STEP_OF (노드 × 타입)     21줄       31줄
배선이 다 있는 recipe     34개       38개
check_wiring  A           2          0
              B           11         0
              C (새 규칙) —          7
pytest                    173/1      175/1
```

C 는 "선언에는 있는데 배선이 없는 자리" 다. **0 이어야 하는 것이 아니다.**
응답 모양을 못 본 자리는 지어내지 않고 비워 두는 것이 규칙이다.

```
web_fetch × 웹 주소                     web.search 가 권한에 막혀 응답 모양을
                                        한 번도 못 봤다. 예전 {url: @arg} 는
                                        발화를 URL 로 쓰는 것이라 지웠다
get_election_district           × 선거구 코드
get_assembly_district           × 선거구 코드   선거구 코드를 내놓는 도구가 없다.
get_assembly_pledge_district    × 선거구 코드   name 칸으로 보내는 것이 맞을 수
                                                있으나 안 눌러봤다
get_local_pledge_summary        × 행정구역 코드
get_age_profile                 × 행정구역 코드  findBoundaryByPoint 가 코드를 어느
get_population_trend            × 행정구역 코드  필드로 내놓는지 아직 모른다(0건)
```

**오늘 실측이 준 것 셋.**

```
find_cctv   앞이 철도 구간 조회면   bbox 넷을 그대로.  실측 bbox
                                    [[126.868587, 36.619576], [127.328115, 37.554557]]
            앞이 geocode 면         좌표 + 반경 15km.  geocode bbox 는 한 변이
                                    1km 라 그걸 쓰면 0건
ev.getStation 의 statId 는 stationId 이지 id 가 아니다
            statId="PL033780"             item 이 온다
            statId="ev_station_PL033780"  item null · 0건 ·
                                          "충전소 …를 찾지 못했거나 DB 연결을…"
            tools/probe_out/ev.getStation.statId-stationId.json
            tools/probe_out/ev.getStation.statId-id.json 이 그 둘이다
ev.searchStations · searchChargers 의 inputSchema 에 query 가 있다
            "충전소명, 주소, 운영기관 키워드".  말한 키워드가 갈 자리가 여기다
```

**범위 밖으로 나간 것 하나.** ①에서 안 적은 온톨로지 한 줄을 ③에서 더했다.

```
- { from: find_cctv, to: point, predicate: hasInput }
```

받는 것이 하나면 배선 줄도 하나뿐이라 철도 뒤와 geocode 뒤를 못 가른다.
`road.getCctv` 의 required 는 bbox 넷이지만 노드는 좌표도 받는다 — 예전부터
`location + radiusMeters` 로 그렇게 불러 왔고 선언만 빠져 있던 것이다.
이 줄로 recipe 는 하나도 안 바뀐다(`rebuild_init` 미리보기로 확인. 좌표를
내놓는 것이 `geocode_place` 하나뿐이라 이을 자리가 안 늘어난다).

**진행 표시 판정을 답과 맞췄다.** `execute_service` 가 `item["error"]` 만 봤다.
Gateway 는 실패를 `200` + `{"error": {...}}` 로도 돌려주고 그것은
`item["result"]` 에 담기므로 화면이 "완료" 라고 찍었다. **그 탓에 "대전~김천
구간이 유효하다" 는 틀린 사실이 문서에 박혔다**(아래 2026-08-22 넷째의 정정).
`workflow_answer.step_failed` 를 새로 두고 `_outcome` · `_verdict` · 진행 표시
셋이 그것을 부르게 했다. **0건은 실패로 보지 않는다** — 호출은 끝났고 결과가
없는 것뿐이고 답 문구가 이미 "찾지 못했습니다" 로 말한다.
`tests/vendor/test_workflow_answer.py` 가 열둘에서 열넷이 됐다.

배선을 바꾼 뒤 세 묶음을 다시 쟀다(`/tmp/after2_*`). **②의 세 묶음과 md5 까지
같다.** 배선은 판정과 무관하다는 것이 이것으로 확인됐다.

#### 안 한 것

`description` 과 `grounding.yaml` 은 손대지 않았다. 사람이 한다.

「열린 과제」에서 「온톨로지의 식별자 타입이 셋을 하나로 묶고 있다」와
「배선이 온톨로지의 선언을 반만 따른다 — 34개 중 13개」를 지웠다. 이번에
해결됐다. 아래 2026-08-23 (넷째)에 그 절을 가리키는 줄이 남아 있는데
**측정 기록은 한 줄도 안 지우는 것이 규칙이라 그대로 뒀다.**

`search_ev_stations` · `search_ev_chargers` 의 「지도 범위」 줄은 실제로는
좌표를 받아 반경으로 넓힌다(`center` + `radiusMeters`). `find_cctv` 와 달리
철도 뒤에 올 일이 없어(대상이 어긋나 걸러진다) 줄이 갈릴 이유가 없었다.
선언과 어긋난 자리로 남아 있다.

### 2026-08-23 (여섯째) · 8안 하나를 더 잼 · 철도 적재 뒤의 실측 · 재기만 함

**왜 쟀는가.** 어젯밤 일곱 안에 없던 조합 하나가 남아 있었다.
3안(식별자 셋 + `ev` 가 번호를 내놓음)에서 `spoken_identifier` 의 `is-a` 만
셋으로 넓힌 것이다. **어느 안이 낫다는 판단은 여기 안 적는다.**

```
3안   spoken_identifier is-a district_code                        하나만
8안   spoken_identifier is-a admin_code · district_code · station_id  셋 다
```

**장소 이름은 안 쪼갰다.** 오늘 철도 적재로 근거가 사라졌다 — 아래 실측 ④.

**어떻게 쟀는가.** 어젯밤과 같다. `/tmp/rework_sim/run.py` 에 `V8` 갈래만 더했다.
`rebuild(write=False)` · 온톨로지 경로 둘만 교체 · `--write` 안 붙임.

```
                     V0(지금)   V3         V8
전체 경로              54        52         56
버린 수                 6         8          8
  그중 2단 미만          0         0          0
남은 recipe            48        44         48
새로 생긴 것            0         4          4
사라진 recipe           0         8          4
                                018·019·020·021    042·043·044·048
                                042·043·044·048
menu 자수            4315      3962       4267    (MENU_BUDGET 6000)
앞토막 충돌 묶음         2         4          4
최대 묶음              23        21         21
```

최대 앞토막은 셋 다 같다 : `말한 장소로 장소 이름으로 위치 좌표와 지도 범위를 찾`.
노드 수 V0 58 · V3 60 · V8 60. `MAX_STEPS` 4.

**사슬 판정 넷.**

```
                              V0      V3      V8
가짜 넷이 남았나             4개남음  0 사라짐  0 사라짐
search_ev_stations→get_ev_station   0       2       2
search_ev_chargers→get_ev_station   0       2       2
get_railway_section→find_cctv       1       1       1
025  spoken_place→geocode_place→find_cctv   있음   있음   있음
```

**3안에서 죽었던 넷이 8안에서 살아났는가** (`spoken_identifier` 로 시작하는 2단).

```
             V0   V3   V8
recipe_018    O    X    O    말한 식별자 → 지방선거 교통 공약 상세
recipe_019    O    X    O    말한 식별자 → 연령별 인구 구성 조회
recipe_020    O    X    O    말한 식별자 → 인구 변화 추이 조회
recipe_021    O    X    O    말한 식별자 → 충전소 상세 조회
```

8안에서 새로 생긴 넷은 이것이다.

```
말한 키워드 → 전기차 충전소 검색 → 충전소 상세 조회
말한 키워드 → 전기차 충전기 조회 → 충전소 상세 조회
말한 장소 → 장소 좌표 변환 → 전기차 충전소 검색 → 충전소 상세 조회
말한 장소 → 장소 좌표 변환 → 전기차 충전기 조회 → 충전소 상세 조회
```

**8안은 어젯밤 V7 과 글자 그대로 같은 온톨로지다.** `run.py` 의 `V7` 갈래가 이미
`split_identifier(셋) + EV_SEARCH_EDGES` 였다. 어젯밤에 이미 잰 조합이고,
숫자도 그대로 나온다. 새로 잰 것은 018~021 살아남 판정뿐이다.

#### 철도 적재 — 오늘 한 일

```
적재      docker exec krri_asap-mcp-1 python scripts/import_railways.py
          Imported 2243 railway sections from /app/2022_rail_utmk_updated.geojson
          rail 스키마가 새로 생겼다. 전에는 스키마 자체가 없었다
```

**눌러본 결과 (실측).**

```
"대전~김천"     NOT_FOUND        그런 이름은 DB 에 없다
"오송역"        성공  coords 18  bbox [[126.8686, 36.6196], [127.3281, 37.5546]]
"서울역"        성공  coords 10
"경부선"        성공  ★ 서울역과 sectionId 가 같다
"경부선(고속)"  성공  ★ 역시 같다
응답 칸 : sectionId · geometry(MultiLineString) · bbox
location 칸은 없다
```

**무엇이 갈렸나.**

```
① location 이 없다. recipe_039 의 $prev.location 배선은 못 쓴다
② bbox 가 [[a,b],[c,d]] 중첩형이라 vendor 의 $prev.minLon 이 푼다.
   find_cctv 를 bbox 넷으로 배선하면 「구간 → CCTV」가 바로 돈다
③ geocode 의 bbox 는 한 변 1km 라 그것으로 CCTV 를 뽑으면 0건이다.
   같은 find_cctv 인데 앞이 geocode 면 좌표+반경, 앞이 구간 조회면 bbox 다.
   노드당 한 줄로는 못 적는다는 실측 사례다
④ 역 이름으로도 노선 이름으로도 같은 한 건이 나온다.
   rail_repository 가 f_name · t_name · r_name_1~3 을 ILIKE 로 훑고 LIMIT 1 이다.
   「구간 이름」이 별도 타입으로 안 갈린다
⑤ sectionId 는 sha256 해시다. 사람이 말할 수 있는 값이 아니다
```

**정정.** 옛 기록의 「`"오송역"` 은 역 이름이지 구간명이 아니다 · 구간명 하나를
알면 다시 재야 한다」(이 문서 아래쪽 2026-08-22 · 2026-08-21 대목)는 **틀렸다.**
적재 뒤 실측에서 `"오송역"` 은 성공한다. 옛 오류는 인자 탓이 아니라 `rail.sections`
테이블 자체가 없었기 때문이다. 구간을 「출발역~도착역」으로 식별한다는 이해도
틀렸다 — `"대전~김천"` 은 NOT_FOUND 이고, 역 이름 하나 · 노선 이름 하나가
똑같이 통한다. 옛 기록은 지우지 않고 그 자리에 둔다.

### 2026-08-23 (다섯째) · 온톨로지 타입 쪼개기 일곱 안을 미리 잼 · 재기만 함

**왜 쟀는가.** 개편에서 `record_key` 와 `place_name` 을 쪼갤 참인데, 쪼갰을 때
경로가 몇 개가 되는지 아무도 몰랐다. 고르기 전에 숫자를 본다.
**어느 안이 낫다는 판단은 여기 안 적는다.** 재기만 했다.

**어떻게 쟀는가.** `tools/rebuild_init.py` 의 `rebuild(write=False)` 를 그대로
돌렸다. 바꾼 것은 그것이 읽는 온톨로지 경로 둘(`paths.ONTOLOGY_PATH` ·
`paths.INIT_ONTOLOGY_PATH`)뿐이다.

```
변형 온톨로지   /tmp/rework_sim/V*.yaml   버릴 파일이라 yaml.dump 로 다시 씀
실행 스크립트   /tmp/rework_sim/run.py    변형마다 새 파이썬 프로세스
INIT_RECIPES_DIR · INIT_MENU_YAML_PATH 는 진짜를 그대로 뒀다.
그래야 "사라진 recipe" 가 지금 48개와 맞대어진다.
```

저장소 파일은 이 NOTES.md 하나만 고쳤다. `ontology/ontology.yaml` ·
`ontology/_init/ontology.yaml` · recipe · menu · `STEP_OF` · 코드 전부 무수정이고
`--write` 는 한 번도 안 붙였다. (`tools/probe_out/` 는 `.gitignore` 라
아래 Gateway 응답 전문은 git 에 안 잡힌다.)

#### 변형 일곱이 무엇인가

```
V0  지금 그대로. 기준선
V1  식별자를 셋으로(admin_code · district_code · station_id).
    record_key 는 지움. spoken_identifier is-a 는 셋 다
V2  V1 인데 spoken_identifier is-a 는 district_code 하나만
V3  V2 + search_ev_stations · search_ev_chargers 가 station_id 를 내놓음
V4  장소 이름을 넷으로(place_label · station_name · line_name · section_name).
    place_name 은 지움. spoken_place is-a 는 place_label · station_name 둘
V5  V3 + V4
V6  V5 + 시작 데이터 노드 spoken_section (「말한 구간」) is-a section_name
```

#### 표 — 변형 일곱

```
변형  노드  전체   버림  2단   남은      새로    사라진   menu    앞토막   최대   묶음 크기
            경로         미만  recipe    생긴것  recipe   자수     묶음     묶음   변화
V0     58    54     6     0     48★        0       0     4,315★     2      23     기준
V1     60    50     6     0     44          0       4     3,815      2      19     -4
V2     60    46     6     0     40          0       8     3,510      2      19     -4
V3     60    52     8     0     44          4       8     3,962      4      21     -2
V4     61    43     0     0     43          0       5     3,860      1      23      0
V5     63    39     0     0     39          4      13     3,507      3      21     -2
V6     64    52     8     0     44          9      13     3,967      4      21     -2

★ V0 재현 확인. recipe 48개 · menu 미리보기 4,315자.
  앞토막 묶음 = 문장 앞 30자가 같은 것이 2개 이상인 묶음의 수
  최대 묶음   = 그중 가장 큰 것의 크기. 앞토막은 일곱 변형 모두 같다 —
                "말한 장소로 장소 이름으로 위치 좌표와 지도 범위를 찾"
  남은 recipe = 48 - 사라진 + 새로 생긴 것. 일곱 다 맞는다
```

사라진 recipe 를 이름으로 편 것.

```
recipe_002  말한 장소 → 철도 구간 형상 조회                         V4 V5
recipe_018  말한 식별자 → 지방선거 교통 공약 상세                    V2 V3 V5 V6
recipe_019  말한 식별자 → 연령별 인구 구성 조회                      V2 V3 V5 V6
recipe_020  말한 식별자 → 인구 변화 추이 조회                        V2 V3 V5 V6
recipe_021  말한 식별자 → 충전소 상세 조회                           V2 V3 V5 V6
recipe_037  말한 장소 → 철도 구간 형상 조회 → 행정구역 조회           V4 V5
recipe_038  말한 장소 → 철도 구간 형상 조회 → VWorld 행정경계 조회    V4 V5
recipe_039  말한 장소 → 철도 구간 형상 조회 → CCTV 조회               V4 V5
recipe_040  말한 장소 → 철도 구간 형상 조회 → 철도 노선 조회          V4 V5
recipe_042  말한 장소 → 좌표 → 지점 행정구역 판별 → 국회의원 지역구 상세        V1 V2 V3 V5 V6
recipe_043  말한 장소 → 좌표 → 지점 행정구역 판별 → 국회의원 전체 선거구 상세   V1 V2 V3 V5 V6
recipe_044  말한 장소 → 좌표 → 지점 행정구역 판별 → 국회의원 선거구 공약 상세   V1 V2 V3 V5 V6
recipe_048  말한 장소 → 좌표 → 지점 행정구역 판별 → 충전소 상세 조회           V1 V2 V3 V5 V6
```

V6 의 사라진 열셋 중 037~040 과 002 는 없어진 것이 아니라 **시작 데이터가
바뀐 것**이다. `말한 구간 → 철도 구간 형상 조회 → …` 넷과 `말한 구간 → 철도
구간 형상 조회` 하나가 새로 생겨 자리를 메운다. 사슬이 달라졌으므로 번호 대응은
끊긴다.

#### 사슬 판정 넷

```
                                  V0  V1  V2  V3  V4  V5  V6
가짜 넷이 사라졌는가              X   O   O   O   X   O   O
  (042·043·044·048 의 사슬)      4   0   0   0   4   0   0   ← 남은 개수
새 경로가 생겼는가                X   X   X   O   X   O   O
  search_ev_stations → get_ev_station   0   0   0   2   0   2   2
  search_ev_chargers → get_ev_station   0   0   0   2   0   2   2
구간 → CCTV 가 남았나             O   O   O   O   X   X   O
  (get_railway_section → find_cctv)
025 CCTV 가 살아 있나             O   O   O   O   O   O   O
  (spoken_place → geocode_place → find_cctv)
```

**025 는 일곱 변형 전부에서 살아 있다.** 시연에서 도는 유일한 경로가 어느 안에서도
안 죽는다.

#### 앞토막 충돌을 편 것

```
V0  23  말한 장소로 장소 이름으로 위치 좌표와 지도 범위를 찾
     5  말한 장소로 구간 이름으로 철도 선형 좌표와 지도 범위
V1  19 / 5   (같은 둘)
V2  19 / 5   (같은 둘)
V3  21 / 5 + 2 말한 키워드로 지도 범위와 지역, 충전기 유형으로 전기
                2 말한 키워드로 지도 범위와 지역으로 전기차 충전기를 조
V4  23       (구간 묶음 5 가 통째로 사라져 묶음이 하나만 남음)
V5  21 / 2 / 2
V6  21 / 5 / 2 / 2   구간 묶음의 앞토막이 "말한 구간으로 …" 로 바뀜
```

#### 타입 노드는 menu 문장에 안 나온다 — 확인했다

`function_for` 는 사슬의 실행 노드 description 과 시작 데이터 노드 이름만 쓴다.
타입 노드는 사슬에 못 들어가므로 이름을 무엇으로 붙이든 문장이 안 바뀐다.
문장에 보이는 "장소 이름으로" 는 `place_name` 의 이름이 아니라
`geocode_place` 의 description 문구다. **그래서 V4 처럼 `place_name` 을 넷으로
쪼개도 남아 있는 문장은 한 글자도 안 바뀐다.** 자수가 준 것은 경로가 준 탓이다.

#### 덤 — `geo.getRailwayLines` 를 railwayName 으로 눌렀다

```
railwayName="경부선"   HTTP 200   features 224건   3,405,330자
railwayName="호남선"   HTTP 200   features  79건   1,408,664자

최상위 칸   type("FeatureCollection") · features
features[0] type · properties · geometry(MultiLineString)
properties  AF_F_N · AF_T_N · RA_F_N · RA_T_N · F_NAME · T_NAME ·
            R_NAME_1 · R_NAME_2 · R_NAME_3 · AVG_DIST · AVG_TIME ·
            L_TRANS · L_RAPID · SPEED · L_TYPE · railCode
전문        tools/probe_out/geo.getRailwayLines.railwayName-<값>.json
```

`stationName="경부선"` 은 0건이었다(2026-08-23 실측). 같은 값을 `railwayName`
으로 넣으면 224건이다. **한 도구가 받는 두 칸이 서로 다른 이름 체계다** —
V4 가 `station_name` 과 `line_name` 을 가른 근거가 이것이다.

#### 예상과 어긋난 것

1. **경로 수가 늘어난 변형이 하나도 없다.** 타입을 쪼개면 경로가 늘 줄 알았는데
   일곱 다 V0(54)보다 적다. 가장 적은 것은 V5 의 39개로 **0.72배**다. 늘어난
   변형이 없으므로 "가장 많이 늘어난 변형" 은 없다. 이유는 단순하다 — 쪼개면
   `can_connect` 가 맞춰 볼 타입이 좁아져 이어지던 것이 끊긴다.
2. **V2 에서 가짜 넷 말고 넷이 더 죽는다.** `spoken_identifier` 를
   `district_code` 하나에만 매면 recipe_018~021(말한 식별자로 바로 상세를 무는
   경로 넷)이 통째로 사라진다. V1(셋 다 매는 것)에서는 안 사라진다. 발화가
   "충북 제1선거구 알려줘" 하나뿐이라는 근거로 좁혔을 때 같이 딸려 나가는 것이다.
3. **V4·V5 에서 039(구간 → CCTV)가 죽는다.** `get_railway_section` 이
   `section_name` 만 받는데 `spoken_place` 는 `place_label` 과 `station_name`
   에만 매여 있어 시작점이 없다. 철도 구간에서 출발하던 다섯(002 · 037~040)이
   한꺼번에 사라진다. V6 의 `spoken_section` 노드 하나가 그것을 되살린다.
4. **V4·V5 에서 버린 수가 6 에서 0 이 된다.** `crosses_groups` 에 걸리던 여섯이
   전부 철도 구간에서 출발하던 경로라, 경로 자체가 없어지면서 거를 것도 없어졌다.
   차단기가 좋아진 것이 아니라 차단할 대상이 사라진 것이다.
5. **V3 에서 앞토막 충돌 묶음이 2 에서 4 로 는다.** 새로 생긴 충전소 경로 넷이
   기존 문장과 앞 30자를 나눠 갖는다. 경로를 늘리면 앞토막도 같이 는다.
6. **최대 묶음은 거의 안 움직인다.** 19~23 사이다. `geocode_place` 로 시작하는
   묶음이 제일 큰데 어느 안도 그것을 안 건드린다.
7. **미리보기 자수는 실측보다 1자 적다.** V0 이 4,315자로 찍히는데 실제
   `_init/menu/menu.yaml` 은 4,316자다. 추정식이 덩어리 사이 빈 줄을 문장 수(48)
   만큼 세는데 실제 이어붙임은 47개다. NOTES 에 적힌 4,316 은 실측이라 어긋난
   것이 아니다. **표의 자수는 전부 미리보기 값이라 서로 견주는 데만 쓴다.**

#### 안 한 것

- 어느 안을 고를지 안 정했다. 고르는 것은 사람이 한다.
- `--write` 를 안 붙였다. `_init` 은 그대로다.
- 발화를 안 돌렸다. 이 표는 전부 경로 생성 결과지 발화 해석 결과가 아니다.
  앞토막 묶음이 실제로 판정을 가르는지는 재봐야 안다.
- `MIN_STEPS` · `MAX_STEPS` 를 안 건드렸다. 일곱 다 2 와 4 그대로다.


### 2026-08-23 (넷째) · 개편의 계기판 둘 · check_wiring · probe_shapes

**왜 만들었는가.** 개편에서 배선을 노드별에서 간선별로 다시 적는다. 그때 계속
부를 눈 둘이 없었다.

```
tools/check_wiring.py   경로와 배선이 맞는지 센다.  서버도 LLM 도 안 쓴다
tools/probe_shapes.py   도구 42개가 어떤 칸으로 답하는지 적는다
```

바로 위 「열린 과제」의 "경로와 배선이 맞는지 세는 검사가 없다" 와 인수인계
문서의 "output 모양을 모르는 것이 걸림돌" 을 각각 없애려는 것이다.
**둘 다 재기만 한다.** 온톨로지 · `STEP_OF` · recipe · menu · description 은
한 글자도 안 고쳤다.

#### check_wiring — 13개를 그대로 재현했다

```
  A  발화 인자를 버린다 (2개)
  recipe        첫 실행 노드                    도구
  recipe_012    search_ev_stations              ev.searchStations
  recipe_013    search_ev_chargers              ev.searchChargers

  B  앞 단계 결과를 안 쓴다 (11개)
  recipe        앞 노드 -> 노드                             도구
  recipe_022    geocode_place -> search_admin_boundaries    adminBoundary.searchBoundaries
  recipe_024    geocode_place -> get_vworld_boundaries      vworld.getAdministrativeBoundaries
  recipe_026    geocode_place -> get_railway_lines          geo.getRailwayLines
  recipe_028    geocode_place -> search_assembly_districts  election.searchAssemblyDistricts
  recipe_030    geocode_place -> search_assembly_pledge_districts
  recipe_032    geocode_place -> search_local_pledge_summaries
  recipe_034    geocode_place -> search_population_statistics
  recipe_037    get_railway_section -> search_admin_boundaries
  recipe_038    get_railway_section -> get_vworld_boundaries
  recipe_040    get_railway_section -> get_railway_lines
  recipe_041    web_search -> web_fetch                     web.fetch

  recipe 48개 · 배선이 다 있는 것 34개 · A 2개 · B 11개 · 합계 13개
```

손으로 센 것(위 「배선이 온톨로지의 선언을 반만 따른다」)과 recipe 번호까지
같다. **규칙을 숫자에 맞추려고 고친 적 없다.** 한 번에 나왔다.

`STEP_OF` · `unwired` · `SPOKEN_VALUE` · `PREVIOUS_STEP` 을 `step_service` 에서
import 한다. 표를 옮겨 적으면 배선을 고칠 때 두 곳이 조용히 어긋나고 그러면
세는 숫자를 못 믿는다. 테스트는 안 두었다 — `tools/` 는 재는 도구이고 이 숫자가
안 나오면 그 자리에서 드러난다.

#### 응답 모양 사전 — 도구 42개

`tools/probe_shapes.py`. 목록은 `curl -s http://localhost:3000/api/tools` 로
받았다 (**이 장비는 3.0초**. Windows 21.1초). 42개를 다 누르는 데 **10.6초**.

```
  도구                                        결과       건수   좌표 칸                 bbox 칸               코드 칸                          최상위 칸                                     0건 문구 · 비고
  rail.getSectionGeometry                     오류       -      -                       -                     -                                -                                             구간 '오송역'을(를) 찾을 수 없습니다.
  road.getCctv                                데이터     82     [0].centerLon=수 …      -                     -                                cctvId cctvName centerLon centerLat cctvUrl…  -
  geo.geocode                                 데이터     ?      location=[a,b]          bbox=[[a,b],[c,d]]    -                                location bbox address                         -
  geo.getRailwayLines                         데이터     31     -                       -                     -                                type features                                 -
  adminBoundary.getDatasetInfo                데이터     ?      -                       bbox=없음             -                                source datasetVersion crs format layers bbo…  -
  adminBoundary.searchBoundaries              0건        0      -                       -                     -                                type features count totalMatches query warn…  행정구역 DB 데이터가 없거나 PostGIS…
  adminBoundary.findBoundaryByPoint           0건        0      -                       -                     -                                type features count totalMatches query warn…  행정구역 DB 데이터가 없거나 PostGIS…
  population.getDatasetInfo                   데이터     ?      -                       -                     id=문자                          id name source sourcePage sourceUrl format …  -
  population.searchStatistics                 데이터     4      -                       bbox=없음             level=sigungu items[0].code=…    type features count totalMatches referenceD…  -
  population.getAgeProfile                    인자 없음  -      -                       -                     -                                -                                             level, code
  population.getTrend                         인자 없음  -      -                       -                     -                                -                                             level, code
  vworld.getDatasetInfo                       데이터     ?      -                       -                     -                                source reference crs requestLimit adminBoun…  -
  vworld.getAdministrativeBoundaries          데이터     4      -                       bbox=[a,b,c,d]       items[0].sig_cd=43111 …          type features items count totalFetched data…  -
  knowledge.query                             0건        0      -                       -                     -                                -                                             문구 없음
  knowledge.listDocs                          0건        0      -                       -                     -                                -                                             문구 없음
  knowledge.deleteDoc                         인자 없음  -      -                       -                     -                                -                                             문서를 지움
  bim.listModels                              0건        0      -                       -                     -                                -                                             문구 없음
  bim.updateModel                             인자 없음  -      -                       -                     -                                -                                             모델을 고침
  bim.deleteModel                             인자 없음  -      -                       -                     -                                -                                             모델을 지움
  dem.getInfo                                 오류       -      -                       -                     -                                -                                             layer.json not found: /app/data/dem…
  ev.getDatasetInfo                           데이터     ?      -                       bbox=[a,b,c,d]       id=문자                          id name source format status stationCount c…  -
  ev.searchStations                           데이터     500    items[0].centerLon=수 … -                     items[0].id=ev_station_PW012325  count totalMatches pageNo limit aggregation…  -
  ev.getStation                               인자 없음  -      -                       -                     -                                -                                             statId
  ev.searchChargers                           데이터     100    items[0].centerLon=수 … -                     items[0].id=ev_station_PW012325  count totalMatches pageNo limit aggregation…  -
  election.getDatasetInfo                     데이터     ?      -                       bbox=[[a,b],[c,d]]    datasetId=문자                   datasetId name electionDate districtCount c…  -
  election.searchDistricts                    데이터     4      -                       bbox=[[a,b],[c,d]]    items[0].code=2431401 …          type features items count totalMatches limi…  -
  election.getDistrict                        데이터     1      -                       bbox=[[a,b],[c,d]]    features[0].id=문자              type features item count totalMatches datas…  -
  election.findDistrictByPoint                데이터     1      -                       bbox=[[a,b],[c,d]]    features[0].id=문자              type features item count dataset query bbox   -
  election.getAssemblyDistrictDatasetInfo     데이터     ?      -                       bbox=[[a,b],[c,d]]    datasetId=문자                   datasetId name electionDate featureCount di…  -
  election.searchAssemblyDistricts            데이터     5      -                       bbox=[[a,b],[c,d]]    items[0].code=4311101 …          type features items count totalMatches limi…  -
  election.getAssemblyDistrict                데이터     1      -                       bbox=[[a,b],[c,d]]    features[0].id=1141001           type features item count totalMatches datas…  -
  election.findAssemblyDistrictByPoint        데이터     1      -                       bbox=[[a,b],[c,d]]    items[0].code=4311301 …          type features items count totalMatches limi…  -
  election.getAssemblyPledgeDatasetInfo       데이터     ?      -                       bbox=[[a,b],[c,d]]    datasetId=문자                   datasetId name electionDate featureCount di…  -
  election.searchAssemblyPledgeDistricts      데이터     20     -                       bbox=[[a,b],[c,d]]    items[0].code=4313001 …          type features items count totalMatches limi…  -
  election.getAssemblyPledgeDistrict          데이터     1      -                       bbox=[[a,b],[c,d]]    features[0].id=문자              type features item count totalMatches datas…  -
  election.findAssemblyPledgeDistrictByPoint  데이터     1      -                       bbox=[[a,b],[c,d]]    items[0].code=4311301 …          type features items count totalMatches limi…  -
  election.getLocalPledgeSummaryDatasetInfo   데이터     ?      -                       -                     datasetId=문자                   datasetId name electionDate featureCount si…  2026 지방선거 시도별 공약 요약 DB…
  election.searchLocalPledgeSummaries         0건        0      -                       -                     -                                type features items count totalMatches data…  2026 지방선거 시도별 공약 요약 데이…
  election.getLocalPledgeSummary              0건        0      -                       -                     -                                status message dataset query                  조건에 맞는 2026 지방선거 시도별…
  election.findLocalPledgeSummaryByPoint      0건        0      -                       -                     -                                status message dataset query                  해당 좌표를 포함하는 시도 공약 요…
  web.search                                  권한 없음  -      -                       -                     -                                -                                             MCP tool 'web-search/web.search' i…
  web.fetch                                   인자 없음  -      -                       -                     -                                -                                             url
  ─────────────────────────────────────────────────────────────────────────────
  도구 42개                                   데이터 24 · 0건 8 · 오류 2 · 인자 없음 7 · 권한 없음 1
```

**표에 값을 적지 않았다.** 어제 vworld 응답이 405KB 였다. `geojson` ·
`coordinates` · `features` 는 길이만 적고 모양은 `[a,b]` 처럼 자리로만 적는다.
값이 필요하면 `tools/probe_out/<도구>.<라벨>.json` 을 본다.

**건수는 `count`(한 쪽)지 `totalMatches`(전체)가 아니다.** 세는 순서가
`probe_tools` 와 같아서 그렇다. 크게 갈리는 줄이 셋이다.

```
ev.searchStations                       count 500  totalMatches 93353   limit 500
ev.searchChargers                       count 100  totalMatches 93353   limit 100
election.searchAssemblyPledgeDistricts  count 20   totalMatches 206     limit 20
```

**`ARGUMENT_RULES` 를 그대로 쓰면 표가 비었다.** 모든 `query` 에 "오송역" 이
들어가 행정구역 · 인구 · 선거 도구가 전부 0건이 된다. 0건이면 칸 이름을 볼 것이
없어 사전이 안 만들어진다. `ARGUMENT_OVERRIDES` 를 따로 두었고 **어젯밤 실측으로
확인된 값만** 적었다.

```
adminBoundary.searchBoundaries          query="청주시"
vworld.getAdministrativeBoundaries      query="청주시"      오송역 0건 · 청주시 4건
population.searchStatistics             query="청주시"      오송역 0건 · 청주시 4건
geo.getRailwayLines                     stationName="오송역"  31건 (인자 없이 3683건)
election.searchDistricts                query="청주"        4건 (인자 없이 254건)
election.searchAssemblyDistricts        query="청주"        5건
election.searchAssemblyPledgeDistricts  query="철도"        totalMatches 206건
```

#### ★ 배선 재료 — 개편에서 간선별 배선을 적을 때 이 표를 본다

**무엇을 어떻게 이을지는 안 적는다. 재료만 적는다.**

**좌표를 내놓는 도구 넷.**

```
geo.geocode         location=[lon,lat]                       최상위
road.getCctv        [0].centerLon=수  [0].centerLat=수        최상위가 배열
ev.searchStations   items[0].centerLon=수  items[0].centerLat=수
ev.searchChargers   items[0].centerLon=수  items[0].centerLat=수
```

좌표를 한 칸에 배열로 주는 것은 `geo.geocode` 하나뿐이다. 나머지 셋은 경도와
위도를 두 칸으로 쪼개 준다. **`ev` 둘에는 `location` 칸이 있는데 값이 빈
문자열이다** (`items[0].location=""`). 이름만 보고 `$prev.location` 을 적으면
좌표가 아니라 `""` 가 간다.

**bbox 모양이 두 가지로 갈린다.** 17개가 `bbox` 를 내놓고 그중 둘이 다르다.

```
[[a,b],[c,d]]   geo.geocode · election 열하나                  13개
[a,b,c,d]       vworld.getAdministrativeBoundaries
                ev.getDatasetInfo                              2개
없음(null)       adminBoundary.getDatasetInfo
                population.searchStatistics                    2개
```

`STEP_OF` 의 `POINT_RADIUS_TO_BBOX` 는 중심 좌표와 반경으로 bbox 를 만드는
것이라 이 두 모양과는 다른 자리다. **어제 이 갈림을 안 재고 배선을 적었다.**

**코드를 내놓는 도구 19개.** 그중 다음 도구의 입력으로 쓸 수 있어 보이는 것.

```
population.searchStatistics         level=sigungu  items[0].code=43113
                                    items[0].id=2026-06-30-sigungu-43113
vworld.getAdministrativeBoundaries  items[0].sig_cd=43111  items[0].datasetId=sigungu
                                    items[0].id=lt_c_adsigg_info.66
election.searchDistricts            items[0].code=2431401
election.searchAssemblyDistricts    items[0].code=4311101   features[0].id=4311101
election.searchAssemblyPledgeDistricts  items[0].code=4313001
election.findAssemblyDistrictByPoint    items[0].code=4311301
election.findAssemblyPledgeDistrictByPoint  items[0].code=4311301
election.getAssemblyDistrict        features[0].id=1141001
ev.searchStations · ev.searchChargers   items[0].id=ev_station_PW012325
```

**코드를 받는 도구 12개.** `inputSchema` 의 어느 칸인가.

```
adminBoundary.searchBoundaries          code(선택)
population.searchStatistics             level(선택)  code(선택)
population.getAgeProfile                level(필수)  code(필수)
population.getTrend                     level(필수)  code(필수)
ev.getStation                           statId(필수)
ev.searchChargers                       statId(선택)
election.searchDistricts                code(선택)
election.getDistrict                    code(선택)
election.searchAssemblyDistricts        code(선택)
election.getAssemblyDistrict            code(선택)
election.searchAssemblyPledgeDistricts  code(선택)
election.getAssemblyPledgeDistrict      code(선택)
```

**0건인데 문구가 없는 도구 셋.** 화면에 "찾지 못했습니다" 만 나간다.

```
knowledge.query      응답이 [] 하나. warning 자리가 없다
knowledge.listDocs   응답이 [] 하나
bim.listModels       응답이 [] 하나
```

#### 어제와 어긋난 것

**`ev` 데이터가 들어왔다.** 어제(08-22 15:50)는 `dataset.status: "empty"` ·
`stationCount: 0` · 시도 17개가 전부 `missingRegionCodes` 였다. 지금은 이렇다.

```
status          syncing
stationCount    93353
chargerCount    492390
infoSyncedAt    2026-08-22T13:36:10Z
```

그래서 `ev.searchStations` 가 0건에서 500건(전체 93353)이 됐다. **위 A 부류
(recipe_012 · 013)가 인자를 버리고 전국을 검색하는 것이 이제 실제로 결과를
낸다.** 어제는 0건이라 티가 안 났다.

**행정구역만 여전히 비어 있다.** `query="청주시"` 로 눌러도 0건이고 warning 이
어제와 같다 ("행정구역 DB 데이터가 없거나 PostGIS 연결을 사용할 수 없습니다").
인구 통계는 채워졌는데(4건) 행정구역은 아니다. `STEP_OF` 아래 주석 2번
(`get_age_profile` 계열이 코드 필드 이름을 모른다)의 전제가 그대로 남아 있다.

다만 **`population.searchStatistics` 자신이 `level` 과 `code` 를 내놓는다**
(`level=sigungu` · `items[0].code=43113`). 주석 2번이 그 코드의 출처로 본 것은
`adminBoundary.findBoundaryByPoint` 였다. **어느 쪽을 쓸지는 안 정했다. 사람이
정할 일이다.**

**`election.getLocalPledgeSummary` 둘을 0건으로 고쳐 세었다.** 어제 표는 이 둘을
"데이터 1" 로 세었고 그 자리에서 "그대로 믿으면 안 된다" 고 적었다. 응답에
`status: "not_found"` 가 실려 있어 이번에는 세는 규칙에 넣었다. 그래서 데이터
24 · 0건 8 이다 (어제 셈법으로는 데이터 26 · 0건 6).

**`road.getCctv` 84 -> 82.** 실시간 CCTV라 부를 때마다 다르다.

**`rail.getSectionGeometry` 는 어제와 같이 오류다.** `"오송역"` 은 역 이름이지
구간명이 아니다. 구간명을 하나도 못 얻어 이번에도 못 눌렀다.

> **정정 (2026-08-23 여섯째).** 위는 틀렸다. `import_railways.py` 로
> `rail.sections` 2,243건을 넣은 뒤 `"오송역"` 은 성공한다. 옛 오류는 인자 탓이
> 아니라 테이블이 없었기 때문이다. 구간이 「출발역~도착역」이라는 이해도 틀렸다 —
> `"대전~김천"` 은 NOT_FOUND 이고 `"서울역"` · `"경부선"` 이 같은 한 건을 돌려준다.
> 근거는 맨 앞 2026-08-23 (여섯째) 항목.

#### 안 한 것

```
철도 적재(import_railways.py)   남의 DB 에 쓰는 일이라 안 돌렸다
bim.updateModel · bim.deleteModel · knowledge.deleteDoc
                                REFUSED_TOOLS 그대로. 앞으로도 안 누른다
온톨로지 · STEP_OF · recipe · menu · description   한 글자도 안 고쳤다
```

### 2026-08-23 (밤) · 개편 직전 기준선 · recipe 48 · qwen3:32b · 각 10회 · 묶음 셋

**왜 쟀는가.** 개편 직전 기준선이다. recipe 번호가 통째로 바뀌므로 아래 표는
개편 뒤 그대로는 무효가 된다. 그래도 전후를 맞대볼 수 있는 유일한 근거다.
`git tag before-ontology-rework` 가 이 지점이다.

원자료는 `/tmp/before.txt`(묶음 1) · `/tmp/block_2.txt` · `/tmp/block_3.txt`.

#### 표 — 묶음 셋을 나란히. 합치지 않는다

```
#  발화                            묶음1     묶음2     묶음3    틀렸을 때 나온 것
1  오송역 위치 보여줘              10/10     10/10     10/10
2  오송역 좌표 알려줘              10/10     10/10     10/10
3  오송역 CCTV 보여줘              10/10     10/10     10/10
4  청주시 인구 구성 알려줘         10/10     10/10     10/10
5  오송역 근처 충전소 찾아줘        0/10      0/10      0/10    {036}      10회
6  국회의원 선거구 찾아줘           0/10      0/10      0/10    {007,008}   9회
                                                               14개 후보    1회
7  전기차 충전소 데이터 검색해줘    0/10      0/10      0/10    {012,013}  10회
8  철도 안전 문서 찾아줘            0/10      0/10      0/10    {006}      10회
9  충북 제1선거구 알려줘           10/10     10/10     10/10
                                  ─────     ─────     ─────
                                  50/90     50/90     50/90
                                   56%       56%       56%
```

#### 묶음 간 차이 — 없다. 한 발화도 안 흔들렸다

```
세 파일이 바이트 단위로 같다.
  289200511d6fd0a361c0eb7e965b295b  /tmp/before.txt
  289200511d6fd0a361c0eb7e965b295b  /tmp/block_2.txt
  289200511d6fd0a361c0eb7e965b295b  /tmp/block_3.txt
```

적중 · 축 · 인자 · 후보 수 · status 가 전부 같다. 발화 6 의 1/10 짜리
14개-후보 이탈까지 세 묶음에 똑같이 한 번씩 나왔다.

**「한 묶음 안에서는 완벽히 같고 묶음 간에는 흔들린다」는 이번에 재현되지
않았다.** 흔들림의 자리를 찾다가 이유를 하나 봤다.

```
llm_engine/ollama.py:89   "options": {"temperature": 0, "seed": 0, ...}
```

온도도 seed 도 고정이다. 같은 프롬프트면 같은 답이 나오는 것이 정상이다.
그러면 예전에 묶음 간에 흔들린 것은 프롬프트 · 온톨로지 · 모델 중 무엇이
그 사이에 바뀌었기 때문이라는 뜻이 된다. **어느 쪽인지는 여기서 정하지
않는다.** 지금 적을 수 있는 사실은 "이 커밋 · 이 모델에서는 세 묶음이
완전히 같다" 까지다.

기준선으로서는 이쪽이 낫다. 개편 뒤 숫자가 달라지면 그것은 흔들림이 아니라
개편의 효과다.

#### 묶음 1 에서 이미 읽히는 것 넷

**축이 완벽하다.** `given · want · about · argument` 가 89/90 동일하다.
흔들린 1회는 발화 6 의 축 셋이 전부 `null` 인 것이다.
**인자 추출은 더 다룰 문제가 아니다.**

**3번이 돌아왔다.** "오송역 CCTV 보여줘" 10/10. 예전에 10/10 -> 0/5 로
뒤집혔던 발화다. 039 간섭이 이 묶음에는 없었다. 한 묶음이므로 굳히지 않는다.
(이번에 세 묶음 모두 10/10 이었다는 것은 위 표에 있다.)

**6번의 1/10 이 재현됐다.** `{007,008}` 9회 + 14개 1회. 지난번과 같은 비율이다.

**★ 실패 넷 중 셋이 같은 모양이다.**

```
5번  {036}
7번  {012, 013}
6번  {007, 008}
```

전부 **비슷한 문장 두 개가 비기는 것**이다. 축은 세 경우 다 정확했다.
타입이 굵어서가 아니라 **menu 문장이 안 갈린다.**
**타입만 쪼개면 이 셋은 안 고쳐진다는 뜻이다.**

#### 안 눌러본 도구 넷을 눌렀다 (여덟 번)

Gateway 를 직접 불렀다(`POST /api/tools/execute`). `tools/probe_tools.py` 는
`ARGUMENT_RULES` 가 "오송역" 고정이라 인자를 못 바꾼다.
응답 전문은 `tools/probe_out/<도구>.<인자>.json` (gitignore).

```
도구                                인자        건수   최상위 칸
rail.getSectionGeometry             대전~김천   오류   error{code,message}
rail.getSectionGeometry             오송역      오류   error{code,message}
geo.getRailwayLines                 오송역      31     type · features
geo.getRailwayLines                 경부선      0      type · features
vworld.getAdministrativeBoundaries  청주시      4      type · features · items · count ·
                                                       totalFetched · dataset · query · bbox
vworld.getAdministrativeBoundaries  오송역      0      위와 같음 (bbox 칸이 사라진다)
population.searchStatistics         청주시      4      type · features · count · totalMatches ·
                                                       referenceDate · level · metric ·
                                                       metricLabel · unit · bbox · items · query
population.searchStatistics         오송역      0      위와 같음
```

**`location` 칸은 넷 어디에도 없다.**

**`rail.getSectionGeometry` 는 이 장비에서 어떤 인자로도 응답이 없다.**
"대전~김천" · "오송역" 둘 다 NOT_FOUND 다. 인자를 잘못 준 것이 아닌지 확인했다.

```
KRRI_ASAP/ASAP-mcp/app/tools/rail.py       DB -> 없으면 MOCK_RAIL_DATA -> 없으면 NOT_FOUND
KRRI_ASAP/ASAP-mcp/app/core/data.py:42     MOCK_RAIL_DATA 키는 "부산역" · "서울역" 둘뿐
postgis                                    relation "rail.sections" does not exist
```

`sectionName="서울역"` 도 눌러봤다. 역시 NOT_FOUND 다
(`tools/probe_out/rail.getSectionGeometry.서울역.json`). DB 테이블이 없고
컨테이너의 MOCK 도 비어 있다. 소스가 선언하는 성공 시 모양은 이렇다.

```
{ sectionId, geometry{type,coordinates}, bbox }      location 이 없다
```

**recipe_039 의 `$prev.location` 은 이 도구로 풀리지 않는다.** 칸이 없어서
못 푸는 것이 첫째고, 지금은 응답 자체가 안 나오는 것이 그보다 앞선다.
(gitignore 런타임 데이터 누락과 같은 부류로 보인다. 여기서 고치지 않는다.)

**행정구역 코드는 둘 다 준다.** `findBoundaryByPoint` 를 안 거쳐도 된다.

```
population.searchStatistics   최상위 level="sigungu"
                              items[].code="43113"     ← level · code 를 그대로 준다
                              items[].sidoName · sigunguName · name
vworld.getAdministrativeBoundaries
                              items[].properties.sig_cd="43111"
                              dataset.id="sigungu" · items[].datasetId="sigungu"
                              items[].properties.full_nm="충청북도 청주시 상당구"
```

recipe_045 · 046 · 047 의 `level` · `code` 배선을 적을 근거가 여기 있다.
필드 이름은 population 쪽이 그대로 `level` · `code`, vworld 쪽이
`datasetId` · `properties.sig_cd` 다. **어느 쪽을 쓸지는 사람이 정한다.**

**bbox 모양.**

```
vworld       최상위 bbox = [127.27565046, ...]  평평한 넷
             items[].bbox = [127.44526401, ...] 평평한 넷
             0건이면 최상위 bbox 칸이 아예 없어진다
population   includeBbox:true 인데 최상위 bbox · items[].bbox 가 전부 null
geo.getRailwayLines  bbox 칸이 없다. geometry.coordinates(MultiLineString) 뿐
```

**0건일 때 warning 문구.**

```
geo.getRailwayLines "경부선"                 {"type":"FeatureCollection","features":[]}
vworld... "오송역"                           count:0 · features:[] · items:[]
population... "오송역"                       count:0 · totalMatches:0 · items:[]
```

셋 다 **warning 문구가 없다.** 조용히 0건이다. `query` 칸에 보낸 값이
그대로 돌아오는 것이 vworld · population 의 유일한 단서다.
`geo.getRailwayLines` 는 그것도 없다.

**"경부선" 0건은 인자 이름 때문이다.** `stationName` 으로 보냈다.
노선명 칸은 `railwayName` 이 따로 있다(`ASAP-mcp/main.py:277`). 도구 잘못이
아니라 이번 호출이 그렇게 물어본 것이다. 적어두고 넘어간다.

geojson · coordinates 값은 적지 않았다. 칸 이름과 길이만 봤다.


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

> **정정 (2026-08-23 여섯째).** 위는 틀렸다. `import_railways.py` 로
> `rail.sections` 2,243건을 넣은 뒤 `"오송역"` 은 성공한다. 옛 오류는 인자 탓이
> 아니라 테이블이 없었기 때문이다. 구간이 「출발역~도착역」이라는 이해도 틀렸다 —
> `"대전~김천"` 은 NOT_FOUND 이고 `"서울역"` · `"경부선"` 이 같은 한 건을 돌려준다.
> 근거는 맨 앞 2026-08-23 (여섯째) 항목.

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
