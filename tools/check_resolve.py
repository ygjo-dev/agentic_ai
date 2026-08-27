"""시연 발화가 지금 온톨로지에서 통하는지 재는 도구.

**아래 GT 는 잠정이다.** MCP 도구 38개로 recipe 가 40개가 됐고, 거기에 축 조회
(ontology/shortlist.py)가 붙었다. 무엇이 정답인지는 표를 보고 사람이 정한다.

같은 발화가 두 번 다르게 나온 적이 있어 한 번 눌러본 것은 근거가 안 된다.
발화마다 여러 번 돌려 무엇이 나왔는지 표로 찍는다. 표를 보고 사람이 발화를
고치고, 다시 돌리고, 확정한다.

    python tools/check_resolve.py                   1~31번 × 5회
    python tools/check_resolve.py --runs 3          지금 쓰는 회차. 왜 3 인지는 아래
    python tools/check_resolve.py --only 2          고친 발화만 다시
    python tools/check_resolve.py --only 1,2,3,4,5,6,7,8,9   기준선 아홉만
    python tools/check_resolve.py --model qwen3:4b  모델만 바꿔 (서버 재시작 없이)
    python tools/check_resolve.py --narrow          좁히기 길(두 번 부르기)로. 기본은 끔

## 「좁히기」 스위치 — 켜면 검산 칸이 「해당 없음」이 된다

`--narrow` 는 /resolve 에 `narrow=true` 를 실어 보낸다. 서버는 LLM 을 두 번 부른다 —
1차는 menu 없이 축 셋만, 온톨로지가 그 축으로 후보를 좁힌 뒤, 2차가 그 후보
문장만 보고 고른다 (demo/api/services/resolve_service.py). **기본은 끔이고, 끄면
서버도 이 도구도 스위치를 만들기 전과 한 글자도 다르지 않아야 한다.**

켜면 「검산」이라는 개념이 없어진다. 대조할 두 목록이 없다. 그래서
**LLM 단독 칸과 검산 표는 켰을 때 「해당 없음」으로 남긴다.** 칸을 없애지
않는 것은 마흔 번의 기록과 이어 읽기 위해서다. 적중 · 근접 · 빗나감 · 못 붙음
네 칸의 뜻은 두 길에서 같다.

켜면 표를 하나 더 찍는다 (좁히기 표).

    좁힌 후보 수   온톨로지가 1차 축으로 좁힌 후보 수 (shortlist_recipe_ids 의 길이)
    2차            2차를 부른 횟수. 후보가 하나면 안 부른다
    폴백 가        조회 후보가 비어 지금 길로 간 횟수
    폴백 나        2차가 "여기 없다" 고 해서 지금 길로 간 횟수
    1차 · 2차 · 폴백   각 단계의 LLM 시간 평균(초). 서버가 잰 값
    합계           이 도구가 잰 /resolve 한 번의 시간 평균(초). 끔 · 켬을 이 칸으로 견준다

끔일 때는 합계 시간만 찍는다. 다른 칸은 그 길에 없다.

## 두 묶음 — 아홉과 열아홉을 갈라 찍는다

발화가 스물여덟이다. **한 백분율로 합치지 않는다.**

    기준선 아홉   1~9번     서른한 번의 측정 기록이 이어져 있는 자
    확장 열아홉   10~31번   2026-08-26 「서른두째」에 만든 자
    합계          둘을 더한 값도 내지만 아홉의 값이 그 위에 따로 보인다

**두 묶음의 점수를 서로 견주지 않는다.** 발화가 다르므로 다른 자다.
한쪽만 돌리려면 `--only` 에 번호를 적는다 — 묶음을 고르는 옵션은 따로 안 만들었다.

**왜 늘렸나.** 커버리지가 첫째 이유가 아니다. 첫째는 한 발화의 무게다. 아홉이면
발화 하나가 흔들릴 때 점수가 11점 움직인다 — 「서른째」에서 발화 둘이 되묻기가
되자 100% 가 78% 가 됐다. 스물여덟이면 한 발화가 3.6% 다.

각 발화에 **표시** 한 칸이 붙는다 (`시연` · `위험` · `애매` · `-`). 낮은 점수가
무엇 때문인지 표에서 바로 읽으라고 둔 칸이고 판정에는 영향이 없다.
뜻은 `MARKS` 옆 주석에 있다.

화면이 지나는 것과 같은 경로여야 표를 믿을 수 있으므로 POST /resolve 를 부른다.
서버(uvicorn)가 떠 있어야 한다.

발화가 확정된 뒤에도 **이 파일은 지우지 않는다.** 온톨로지나 menu 가 바뀌면 다시
재야 하고, 그때 되살리는 것보다 두는 편이 싸다. 그래서 파일 하나에 담고
저장소의 다른 곳을 건드리지 않는다.

실측 기록과 "다시 시도하지 말 것" 은 NOTES.md 에 있다. 발화를 고치기 전에
읽는다 — 이미 재본 것을 또 재게 된다.

**여기와 NOTES.md 에 적힌 알아낸 것은 예전 온톨로지(철도 CCTV 14노드)와 예전
모델(qwen2.5:7b) 기준이다.** 지금 기본 모델은 `models.yaml` 의 qwen3:32b 다.

표를 네 장 찍는다. 적중 표 · 축 표 · 후보 표 · 검산 표다. 후보가 안 맞을 때 LLM 이
recipe 를 잘못 고른 것인지 축을 잘못 쓴 것인지는 축 표에서 갈린다. 축 표에는
발화에서 뽑은 인자(argument)도 함께 찍는다 — 축이 맞아도 인자가 흔들리면
실행이 엉뚱한 것을 조회한다.

## 적중 표의 네 칸 — 「빗나감」을 지우지 말 것

적중 표는 틀린 것을 셋으로 가른다. **넷을 더하면 시행 횟수가 된다.**

    적중     set(후보) == 기대값.  판정 규칙은 예전 그대로다
    근접     정답이 후보 안에 남아 있는데 하나로 못 좁혔다 (CLARIFY).
             사람이 고르면 되는 상태다
    빗나감   정답이 후보에 아예 없다.  ★ 제일 나쁘다
    못 붙음  NO_MATCH · 후보가 빔 · 호출 오류

**왜 「빗나감」이 제일 나쁜가.** 점수로는 근접도 빗나감도 똑같이 0 이다.
그런데 사람이 겪는 것은 전혀 다르다.

    근접     CLARIFY {034, 045, 046}   정답 045 가 후보 안에 있다. 사람이 고르면 된다
    빗나감   SELECT  {011}             확신하고 틀린다. 사람이 알 방법이 없다

「틀린 답보다 정직한 되물음이 낫다」가 이 저장소의 원칙이다. 한 칸짜리 적중률은
그 차이를 못 본다 — 되물음이 확신하고 틀린 것으로 바뀌어도 숫자는 안 움직인다.
실제로 그런 적이 있다(발화 4, 2026-08-24). 표가 못 보면 아무도 못 본다.

그러니 **이 칸을 합치지 말 것.** 적중률만 남기면 품질이 무너지는 것을 다시 놓친다.
빗나감이 늘고 근접이 줄었으면 적중률이 그대로여도 나빠진 것이다.

「빗나감」에는 SELECT 로 하나 고르고 틀린 것과, CLARIFY 인데 정답이 후보에 아예
없는 것이 함께 들어간다. 둘 다 사람이 정답에 닿을 길이 없다. 어느 쪽인지는 옆의
「틀렸을 때 나온 것」 칸에서 갈린다.

후보 표는 모델을 바꿔 재는 데 쓴다. 조회 후보 수는 그대로인데 LLM 후보 수만
줄면 모델 크기 탓이고, 둘 다 그대로면 menu 문장 탓이다.

5번(오송역 근처 충전소)이 그 자리였다 — 충전소 검색과 충전기 조회가 축 셋이
같아 조회로는 못 갈렸고 후보가 늘 둘이었다. **2026-08-26 에 충전기 조회
노드를 뺐다**(저쪽이 폐기 예정이라 적어 둔 `ev.searchChargers`). 이제 그
자리의 조회 후보는 하나다. 축 셋이 같은 짝이 또 생기면 여기에 다시 적는다.

## 「LLM 단독」 칸 — 검산이 값을 하는지 재는 자리

판정은 두 단계다.

    1  LLM 이 recipe_id 와 candidate_recipe_ids 를 쓴다
    2  LLM 이 쓴 축 셋으로 온톨로지를 조회하고(shortlist) 둘을 대조한다(_verdict)

**적중률은 2단계까지 거친 값이다.** 1단계만이면 몇 %인지 한 번도 안 쟀다.
「LLM 단독」 칸이 그 1단계다. 세는 법은 이렇다.

    LLM 이 쓴 recipe_id 하나가 기대값과 같은가
    recipe_id 가 비어 있으면 candidate_recipe_ids 를 본다
    둘 다 없으면 「없음」 으로 센다

**LLM 을 더 부르지 않는다.** /resolve 응답의 llm_recipe_id ·
llm_candidate_recipe_ids 를 읽을 뿐이라 기존 측정에 칸만 붙는다.
(그 두 key 는 이 칸을 재려고 2026-08-24 에 더했다. resolve_service.resolve 가
`**verdict` 로 recipe_id 와 candidate_recipe_ids 를 덮어써서 날것이 응답에
안 실리고 있었다. **덮어쓰는 쪽은 그대로 뒀다** — 적중 판정은 안 건드린다.)

## 세 갈래로 읽는다

    LLM 단독 ≈ 최종      검산이 하는 일이 없다. shortlist 를 걷어낼 수 있다
    LLM 단독 ≪ 최종      검산이 값을 한다. 남긴다
    LLM 단독 > 최종      ★ 검산이 맞는 답을 덮고 있다. _verdict 를 다시 봐야 한다

세 번째가 실제로 있었다. "철도 안전 문서 찾아줘" 는 LLM 이 문서 검색을 골랐는데
_verdict 의 「겹치는 것 0개면 조회 후보를 쓴다」 규칙이 웹 검색으로 덮었다
(NOTES 2026-08-23 열한째).

**이 칸은 적중 판정을 안 건드린다.** 적중 · 근접 · 빗나감 · 못 붙음 네 칸과
그 합계는 칸을 더하기 전과 같은 숫자가 나와야 한다. 달라지면 표가 아니라
코드가 틀린 것이다.

어느 자리에서 검산이 답을 바꿨는지는 네 번째 표(검산 표)가 발화별로 찍는다.

## 후보 표의 「조회 판정」 — 온톨로지만으로 좁혔을 때 정답이 살아남는가

지금은 LLM 을 부르면서 프롬프트에 menu 40문장을 통째로 넣는다. LLM 이 그중에서
고르고, 그 답을 온톨로지 조회(shortlist)와 교집합 내어 좁힌다. 순서를 뒤집는
안이 있다 — **온톨로지가 먼저 몇 개로 좁히고, LLM 은 그 몇 개 중에서 고른다.**
프롬프트가 40문장에서 몇 문장으로 줄면 「프롬프트 길이가 판정을 흔든다」는
문제가 대부분 사라진다.

**그 대신 안전장치가 없어진다.** 지금은 LLM 후보와 겹치는 것이 없으면 조회
후보를 쓰는 길이 있는데, 먼저 좁히면 축이 틀린 순간 정답이 후보에서 아예
빠진다. 되물음이 아니라 확신하고 틀리는 것이 된다.

그래서 좁히기를 만들기 전에 이것부터 잰다 — **기대값이 `shortlist_recipe_ids`
안에 들어 있는가.** 네 갈래로 센다. 넷을 더하면 시행 횟수가 된다.

    조회 적중   기대값 ⊆ 조회 후보 · 조회 후보가 기대값과 같다   좁히면 바로 SELECT 다
    조회 근접   기대값 ⊆ 조회 후보 · 조회 후보가 더 많다         좁힌 뒤 LLM 이 고르면 된다
    조회 빠짐   ★ 기대값이 조회 후보에 없다                      좁히면 정답에 못 닿는다
    조회 없음   조회 후보가 빈 목록                              축이 셋 다 null 인 자리

**「조회 빠짐」이 보려는 숫자다.** 0 이면 좁히기가 안전하고, 0 이 아니면 그
발화는 좁히기로 손해를 본다.

**`_verdict`(검산)를 지나기 전 값을 본다.** 최종 후보가 아니라
`shortlist_recipe_ids` 그대로를 기대값과 맞댄다. LLM 을 더 부르지 않으므로
기존 측정에 칸만 붙는다. 축 셋에서 결정론적으로 나오는 값이라 축이 같으면
이 칸도 같다 — 한 묶음이면 된다.

**이 칸도 적중 판정을 안 건드린다.** 적중 · 근접 · 빗나감 · 못 붙음 네 칸과
그 합계는 칸을 더하기 전과 같아야 한다.
"""

import argparse
import os
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

# (번호, 발화, 기대 recipe 집합, 기본 실행 여부)
#
# **기대값은 잠정이다.** 축 조회(ontology/shortlist.py)를 넣고 처음 재는
# 발화들이라 무엇이 정답인지 표를 보고 사람이 정한다.
#
#   001  말한 장소 → 장소 좌표 변환
#   020  말한 장소 → 장소 좌표 변환 → CCTV 조회
#   030  말한 장소 → 장소 좌표 변환 → 전기차 충전소 검색
#   038  말한 장소 → 장소 좌표 변환 → 지점 행정구역 판별 → 연령별 인구 구성 조회
#   007~010  말한 키워드 → 선거 네 데이터셋의 검색. 예전에는 발화만으로는
#            안 갈린다고 적어 뒀는데, description 을 다시 쓴 뒤(2026-08-23)
#            네 문장이 서로 갈린다. 6번 항목의 주석을 본다
#   012  말한 키워드 → 전기차 충전소 검색
#   013  말한 키워드 → 문서 검색
#   014  말한 식별자 → 국회의원 지역구 조회
#
# 1 과 2 는 같은 recipe 를 다르게 물은 것이다. 001 은 18개 recipe 의 앞토막이라
# 끝점이 실제로 갈리는지가 관건이고, 그것을 가르는 것이 want 축이다.
# (22개라고 적혀 있었다. 세어 보니 이번 변경 전이 20개, 뒤가 18개다.)
#
# **번호를 옮겼다. 기대값은 한 글자도 안 바꿨다** (식별자 타입 쪼개기, 2026-08-23).
# 사슬이 같은 recipe 를 찾아 그 새 번호를 넣었다. 사라진 사슬은 없다 —
# 아홉 발화의 기대 사슬이 전부 살아 있다.
# 042 부터 번호가 밀렸으므로 4번 하나만 움직였다. 나머지 여덟은 041 이하라
# 그대로다. NOTES 의 옛 측정과 맞대볼 수 있게 옛 번호를 옆에 남긴다.
#
# **또 옮겼다. 기대값은 여전히 한 글자도 안 바꿨다**
# (`말한 식별자 is-a 행정구역 코드` 떼기, 2026-08-24). 옛 018 · 019 · 020 이
# 사라지고 021 이후가 셋씩 당겨졌다. 사라진 사슬은 아홉 발화에 하나도 없다.
# 3 · 4 · 5 번이 그 뒤라 함께 움직였고 나머지 여섯은 017 이하라 그대로다.
#
# **세 번째로 옮겼다. 기대값은 이번에도 한 글자도 안 바꿨다**
# (`search_ev_chargers` 빼기, 2026-08-26. 저쪽이 폐기 예정이라 적어 둔 도구다).
# 옛 013 · 033 · 040 · 045 가 사라지고 014 이후가 하나씩 · 둘씩 · 셋씩 당겨졌다.
# 사라진 넷은 전부 충전기 조회를 거치는 사슬이라 아홉 발화에 하나도 없다.
# 3 · 4 · 5 · 8 · 9 번이 그 뒤라 움직였고 1 · 2 · 6 · 7 번은 012 이하라 그대로다.
#
# **네 번째로 옮겼다. 기대값은 이번에도 한 글자도 안 바꿨다**
# (`말한 식별자 is-a 충전소 번호` 떼기, 2026-08-26. 사람은 충전소 번호를
# 말하지 않는다). 옛 017(말한 식별자 → 충전소 상세 조회) 하나가 사라지고
# 018 이후가 하나씩 당겨졌다. 그 사슬은 아홉 발화에 없다.
# 3 · 4 · 5 번이 그 뒤라 움직였고 나머지 여섯은 016 이하라 그대로다.
UTTERANCES = [
    (1, "오송역 위치 보여줘",        {"recipe_001"}, True),
    (2, "오송역 좌표 알려줘",        {"recipe_001"}, True),
    (3, "오송역 CCTV 보여줘",        {"recipe_020"}, True),  # 옛 recipe_021 · 022 · 025
    (4, "청주시 인구 구성 알려줘",   {"recipe_038"}, True),  # 옛 recipe_039 · 042 · 046 · 045
    (5, "오송역 근처 충전소 찾아줘", {"recipe_030"}, True),  # 옛 recipe_031 · 032 · 035
    # 옛 기대값은 {007, 008, 009, 010} 이었다. "발화만으로는 안 갈린다" 를
    # 전제로 넷을 다 적었던 것이다. **그 전제가 이제 거짓이다.**
    # description 을 다시 쓴 뒤(2026-08-23) menu 의 네 문장이 이렇게 갈린다.
    #   007  제22대 국회의원 지역구를 선거구명과 시도, 코드로 검색한다
    #   008  전체 선거구를 공약 수와 분야 집계로 검색한다
    #   009  선거구 공약을 당선인과 정당, 분야로 검색한다
    #   010  2026 지방선거 시도별 대표 인물과 정당, 교통 공약 주제를 검색한다
    # "국회의원 선거구 찾아줘" 에 맞는 것은 007 하나다. 008·009 는 공약이고
    # 010 은 지방선거다. {007} 은 오답이 아니라 정답이다.
    # **숫자가 낮아서 고친 것이 아니다.** 근거는 menu 의 네 문장이고 그 문장은
    # 우리가 다시 쓴 것이다. 다른 여덟 발화의 기대값은 건드리지 않았다.
    (6, "국회의원 선거구 찾아줘", {"recipe_007"}, True),
    (7, "전기차 충전소 데이터 검색해줘", {"recipe_012"}, True),
    (8, "철도 안전 문서 찾아줘",         {"recipe_013"}, True),  # 옛 recipe_014
    (9, "충북 제1선거구 알려줘",         {"recipe_014"}, True),  # 옛 recipe_015

    # ── 여기부터 확장 열아홉 (2026-08-26 「서른두째」) ──────────────────
    #
    # **위의 아홉과 그 기대값은 한 글자도 안 바꿨다.** 서른한 번의 측정 기록이
    # 그 아홉으로 재어져 있다. 10번부터 이어 붙였을 뿐이다.
    #
    # **왜 늘렸나.** 커버리지가 첫째 이유가 아니다. 첫째는 **한 발화의 무게**다.
    # 아홉이면 발화 하나가 흔들릴 때 점수가 11점 움직인다 — 「서른째」에서
    # 발화 둘이 되묻기가 되자 100% 가 78% 가 됐다. 변경이 좋은지 나쁜지를 그
    # 자에 물으면 답이 요동친다. 스물여덟이면 한 발화가 3.6% 다.
    # 둘째 이유가 커버리지다. 아홉이 덮는 것은 recipe 40개 중 8개였다.
    #
    # **아래 열아홉의 기대 사슬은 넣기 전에 하나씩 확인했다** —
    # `ontology.graph.recipe_nodes` 로 40개를 전부 찍어 맞대 봤다 (2026-08-26).
    # 옆에 적은 사슬이 그 확인 결과다. 번호가 또 밀리면 여기부터 다시 확인한다.
    #
    # 값의 출처는 2026-08-26 쓸기(「스물아홉째」, 60발화 × 2모델 × 10회)다.
    # 쓸기는 정답을 안 보고 「무엇이 나오는가」만 적은 것이라 여기 기대값은
    # 그것을 보고 사람이 정한 것이다. **쓸기의 번호는 옛 번호다** — 「서른째」가
    # 옛 017 을 빼면서 018 이후가 하나씩 당겨졌다. 아래는 당긴 뒤의 번호다.

    # 시연용 열넷 — 쓸기에서 두 모델 모두 하나로 갔고 데이터도 나왔다.
    (10, "오송역이 어느 동인지 알려줘",   {"recipe_018"}, True),  # 장소 → 좌표 → 지점 행정구역 판별
    (11, "오송역 행정경계 보여줘",        {"recipe_017"}, True),  # 장소 → 좌표 → 행정구역 조회
    (12, "청주시 행정경계 보여줘",        {"recipe_004"}, True),  # 키워드 → 행정구역 조회
    (13, "오송역 국회의원 누구야",        {"recipe_024"}, True),  # 장소 → 좌표 → 지점 전체 선거구 판별
    (14, "오송역 국회의원 공약 보여줘",   {"recipe_025"}, True),  # 장소 → 좌표 → 선거구 공약 검색
    (15, "청주 선거구 찾아줘",            {"recipe_007"}, True),  # 키워드 → 지역구 검색
    (16, "교통 공약 많은 선거구 검색해줘", {"recipe_008"}, True),  # 키워드 → 전체 선거구 검색
    (17, "청주 국회의원 공약 검색해줘",   {"recipe_009"}, True),  # 키워드 → 선거구 공약 검색
    (18, "오송역 일대 인구 얼마야",       {"recipe_029"}, True),  # 장소 → 좌표 → 인구 통계
    (19, "인구 많은 시군구 순위 보여줘",  {"recipe_011"}, True),  # 키워드 → 인구 통계
    # **20번만 지명이 다르다** (오송역 아닌 대전역). 지명 하나에만 몰리는 것을
    # 피하려는 것이고, **쓸기에 없던 안 재본 값이다.** 되묻거나 빗나가면
    # 그 자체가 발견이다 — 지명 탓인지 경로 탓인지를 표에서 가른다.
    (20, "대전역 연령대별 인구 알려줘",   {"recipe_038"}, True),  # 장소 → 좌표 → 행정구역 판별 → 연령별 인구
    (21, "경부선 선형 데이터 줘",         {"recipe_002"}, True),  # 장소 → 철도 구간 형상
    (22, "오송역 지나는 노선 알려줘",     {"recipe_003"}, True),  # 장소 → 철도 노선 조회
    (23, "경부선 주변 CCTV 보여줘",       {"recipe_033"}, True),  # 장소 → 철도 구간 형상 → CCTV
    # 사슬이 넷인 유일한 발화다. 4단이 실제로 서는지를 이 한 줄이 지킨다.
    (24, "오송역 근처 충전소 자세히 알려줘", {"recipe_040"}, True),  # 장소 → 좌표 → 충전소 검색 → 상세

    # 문서 셋 — 시연 요구사항이라 두툼하게 둔다. 셋 다 013(키워드 → 문서 검색)이다.
    # 25 · 26 은 「서른한째」 화면 실측에서 조각 셋이 문서 이름 · 쪽과 함께
    # 나오는 것을 확인했다.
    (25, "문서에서 철도안전법 관련 내용 찾아줘", {"recipe_013"}, True),
    (26, "문서에서 철도 안전 교육 내용 찾아줘",  {"recipe_013"}, True),
    # ★ 위험 자리. 지금 웹 검색(006)으로 **확신하고 가서** 권한 없음으로 실패한다
    # (쓸기 52번, SELECT {006} 10/10). "문서" 라는 낱말이 없으면 새는 것을
    # 표에 남기려고 넣었다.
    #
    # **웹 검색도 말이 되는 읽기다.** 이상적인 답은 되묻기이고, 사슬 조건부
    # (문서 검색 → 0건이면 웹)나 UX 로 풀 일이다. **이번 범위가 아니다.**
    # 기대값을 013 으로 두는 이유는 시연 요구가 "문서에서 찾아온다" 이고
    # 지식베이스에 그 법이 들어 있기 때문이다(철도안전법 47쪽, 「서른한째」).
    (27, "철도안전법 내용 찾아줘",               {"recipe_013"}, True),

    # ★ 위험 자리 하나 더. 지금 {006, 013}(웹 검색 · 문서 검색)으로 되묻는다 —
    # 철도가 후보에 아예 안 든다. "경부선" 을 「말한 키워드」로 읽으면
    # 철도 경로(002 · 003 은 「말한 장소」로 시작한다)가 전부 빠지기 때문이다.
    (28, "경부선 노선 보여줘",            {"recipe_003"}, True),  # 장소 → 철도 노선 조회

    # ★ 애매 셋. **기대값은 사람이 정한 것이다** (2026-08-26). 셋 다 지금은
    # 되묻으므로 근접이나 빗나감으로 잡히고, 나중에 고치면 적중이 된다.
    # **고쳐야 할 자리라는 것이 표에 남는 것이 목적이다.** 기대값을 여럿으로
    # 적어 지금 상태를 적중으로 만들지 않는다.
    #
    # 29  청주시 전체를 물었으니 네 구가 다 나오는 011 이 맞다. 좌표 길(029)은
    #     `geo.geocode` 가 늘 1.1km 상자라 한 구만 준다(「스물다섯째」).
    #     지금은 {029, 038, 039} 로 되묻는다 — 011 이 후보에 아예 없다
    # 30  그 지점이 든 선거구 「이름」을 묻는 것이므로 검색이 아니라 판별(022)이다
    # 31  발화 6 과 같은 자리다. 선거구명을 달라는 뜻이므로 007
    (29, "청주시 인구 알려줘",            {"recipe_011"}, True),  # 키워드 → 인구 통계
    (30, "오송역 선거구 알려줘",          {"recipe_022"}, True),  # 장소 → 좌표 → 지점 선거구 판별
    (31, "청주 국회의원 선거구 검색해줘", {"recipe_007"}, True),  # 키워드 → 지역구 검색
]

# ── 표시 ────────────────────────────────────────────────────────────
#
# 적중 표에 한 칸으로 찍는다. **낮은 점수가 무엇 때문인지 표에서 바로 읽히게
# 하는 것이 전부다.** 판정에는 아무 영향이 없다 — 세는 법은 표시가 없을 때와
# 글자까지 같다.
#
#   시연  쓸기에서 두 모델 모두 하나로 갔고 데이터도 나왔다. 시연에서 쓸 발화다.
#         여기서 되묻기가 나오면 쓸기 때와 달라진 것이다
#   위험  **지금 확신하고 틀리는 것을 알고 넣었다.** 빗나감이 나오는 것이 정상이다.
#         고쳐야 할 자리를 표에 남기려고 둔 것이다
#   애매  사람이 기대값을 정한 자리. 지금은 되묻는다. 나중에 고치면 적중이 된다
#   -     기준선 아홉. 표시 없이 재던 것이라 그대로 둔다
DEMO, RISKY, VAGUE, PLAIN = "시연", "위험", "애매", "-"

# 번호 → 표시. 여기 없는 번호는 PLAIN 이다.
#
# **기존 아홉의 줄을 안 건드리려고 목록이 아니라 따로 둔 표다.** 튜플에 칸을
# 하나 더하면 1~9 번 줄도 함께 고쳐야 하는데, 그러면 `git diff` 만 보고
# 「아홉이 안 움직였다」를 확인할 수가 없다. 여기 두면 그 줄들의 diff 가 0 이다.
MARKS = {
    **{n: DEMO for n in range(10, 25)},   # 10~24  시연용 열넷 (24 는 4단)
    25: DEMO, 26: DEMO,                   # 문서 둘 — 화면 실측으로 확인했다
    27: RISKY, 28: RISKY,                 # 위험 둘
    29: VAGUE, 30: VAGUE, 31: VAGUE,      # 애매 셋
}


def _mark(number: int) -> str:
    return MARKS.get(number, PLAIN)


# ── 두 묶음 ─────────────────────────────────────────────────────────
#
# **둘을 합쳐 하나의 백분율로 만들지 않는다.** 1~9 번은 서른한 번의 측정 기록이
# 이어져 있는 기준선이고, 10 번부터는 이번에 새로 만든 것이다. 합치면 기준선의
# 값이 옛 기록과 안 맞아 이어 읽을 수가 없다. 합계 한 줄은 내되 아홉의 값이
# 그 위에 따로 보인다.
#
# **두 묶음의 점수를 서로 견주지도 않는다.** 발화가 다르므로 다른 자다.
BASELINE_LAST = 9
BASELINE_LABEL = "기준선 아홉"
EXTENSION_LABEL = "확장 열아홉"


def _groups(entries) -> list:
    """발화 목록을 기준선과 확장으로 가름.

    입력  발화 목록
    출력  [(묶음 이름, 그 묶음의 발화 목록)] — 빈 묶음은 뺌
    규칙  --only 로 한쪽만 돌리면 한 묶음만 나옴. 그때는 합계 줄을 안 찍음.
          소계 한 줄과 합계 한 줄이 같은 값으로 두 번 나오면 읽는 사람이
          둘을 다른 것으로 본다
    """
    baseline = [entry for entry in entries if entry[0] <= BASELINE_LAST]
    extension = [entry for entry in entries if entry[0] > BASELINE_LAST]
    return [
        (label, group)
        for label, group in ((BASELINE_LABEL, baseline), (EXTENSION_LABEL, extension))
        if group
    ]

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

# 화면이 부르는 주소와 같아야 표를 믿을 수 있다. 그래서 같은 환경변수를 본다.
BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
# models.yaml 의 가장 큰 timeout(qwen3:32b 900) 보다 짧으면 큰 모델을 잴 때
# 서버가 답하기 전에 여기서 끊겨 표가 오류로만 찬다. 화면(demo/ui/api_client.
# RESOLVE_TIMEOUT 180)과 달리 이 도구는 큰 모델도 재므로 값을 따로 둔다.
TIMEOUT = 900

RECIPES_DIR = REPO_ROOT / "workflows" / "static" / "recipes"
INIT_RECIPES_DIR = REPO_ROOT / "workflows" / "static" / "_init" / "recipes"

UTTERANCE_WIDTH = 38  # 표에서 발화 칸의 폭. 넘치면 자른다 — 번호로 알아본다.

# 좁히기 스위치. --narrow 가 켠다. **기본은 끔.** main() 만 바꾼다.
NARROW = False


# ── 한글 폭 ──────────────────────────────────────────────────────────
# 한글은 폭이 2 라 ljust 로는 표가 어긋난다. 표 라이브러리를 쓰지 않으므로
# 여기서 직접 센다.


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _clip(text: str, width: int) -> str:
    """폭 width 안에 들어가게 자름. 잘렸으면 끝에 … 를 붙임."""
    if _width(text) <= width:
        return text
    kept, used = "", 0
    for ch in text:
        ch_width = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if used + ch_width > width - 1:
            break
        kept, used = kept + ch, used + ch_width
    return kept + "…"


# ── 호출 ────────────────────────────────────────────────────────────


class ServerDown(RuntimeError):
    """서버에 닿지 못했다. 재시도하지 않고 즉시 멈춘다."""


def _short(recipe_ids) -> str:
    """{"recipe_004", "recipe_005"} → "{004, 005}"."""
    trimmed = sorted(rid[len("recipe_"):] if rid.startswith("recipe_") else rid for rid in recipe_ids)
    return "{" + ", ".join(trimmed) + "}"


def _axes(result: dict) -> tuple:
    """응답의 축 셋과 인자. 표에 한 줄로 찍을 형태.

    출력  (given, want, about, argument). 안 쓴 축과 못 뽑은 인자는 "-"
    규칙  Counter 의 key 라 튜플로 둠. 리스트는 해시가 안 됨
          argument 는 축과 같은 국면에서 나오므로 같은 표에 둠. 축이 맞는데
          인자만 흔들리는지가 여기서 갈림
    """
    return tuple(
        result.get(axis) or "-"
        for axis in ("given", "want", "about", "argument")
    )


def _tally(result: dict) -> tuple:
    """응답의 후보 수 셋과 조회 후보 집합. 후보 표에 한 줄로 찍을 형태.

    출력  (LLM 후보 수, 조회 후보 수, 최종 status, 조회 후보 집합).
          없는 key 는 "-", 조회 후보가 안 실렸으면 집합 자리가 None
    규칙  LLM 후보 수는 candidate_recipe_ids 의 길이.
          recipe_id 가 있고 그 목록에 없으면 하나 더 셈
          조회 후보 수는 shortlist_recipe_ids 의 길이
          Counter 의 key 라 문자열 튜플로 둠. 리스트는 해시가 안 됨.
          조회 후보 집합은 같은 이유로 frozenset 으로 둠
    이력  candidate_recipe_ids 는 resolve_service._verdict 를 지난 값이라
          LLM 이 부른 날것이 아니라 조회 후보와 겹친 것임. 날것은 응답에
          안 실림. 조회 후보 수와 나란히 보면 어느 쪽이 좁혔는지는 갈림
          집합을 함께 실은 것은 「조회 판정」 칸(2026-08-25) 때문임. 개수만으로는
          정답이 그 안에 들어 있는지 못 봄. **`_verdict` 를 지나기 전 값이라
          최종 후보와 다름 — 그것이 이 칸의 요점임**
    """
    spoken = result.get("candidate_recipe_ids")
    if spoken is None:
        llm_count = "-"
    else:
        chosen = result.get("recipe_id")
        llm_count = str(len(spoken) + (1 if chosen and chosen not in spoken else 0))

    looked_up = result.get("shortlist_recipe_ids")
    lookup_count = "-" if looked_up is None else str(len(looked_up))
    shortlist = None if looked_up is None else frozenset(looked_up)

    return llm_count, lookup_count, result.get("status") or "-", shortlist


def _alone(result: dict):
    """검산을 거치기 전에 LLM 이 쓴 후보 집합.

    입력  /resolve 응답
    출력  frozenset. 아무것도 안 썼으면 None
    규칙  llm_recipe_id 가 있으면 그 하나. **status 가 SELECT 가 아니어도
          recipe_id 는 오므로 그것을 봄**
          비어 있으면 llm_candidate_recipe_ids 를 봄
          둘 다 없으면 None. 표에서 「없음」 으로 셈
    제약  recipe_id · candidate_recipe_ids 를 보지 않는다.
          그 둘은 resolve_service._verdict 를 지난 값이라 LLM 이 쓴 것이 아님
    """
    chosen = result.get("llm_recipe_id")
    if chosen:
        return frozenset({chosen})
    spoken = result.get("llm_candidate_recipe_ids") or []
    return frozenset(spoken) if spoken else None


def _call_resolve(utterance: str, model: str | None = None) -> tuple:
    """POST /resolve 한 번.

    입력  발화 · 모델 이름(없으면 서버 기본 모델)
    출력  (후보 집합, status, 축 넷, 후보 수와 조회 후보 집합, LLM 단독 후보 집합,
           좁히기 칸). 후보는 recipe_id 와 candidate_recipe_ids 를 합친 것
          좁히기 칸은 응답의 narrow(켰을 때만 실림)에 이 도구가 잰 시간(elapsed)
          을 더한 dict. 끔이면 elapsed 만 있음
    규칙  서버에 못 닿으면 ServerDown. 재시도하지 않고 즉시 멈춤
          모델은 요청마다 실어 보냄. 모델을 바꾸는 데 서버를 다시 띄우지 않음
          status 를 후보와 함께 냄. 적중 표가 근접·빗나감을 가르는 데 씀 —
          후보 집합만으로는 CLARIFY 와 SELECT 가 안 갈림
          LLM 단독 후보는 같은 응답에서 읽음. 부르는 횟수가 안 늘어남
    """
    params = {"utterance": utterance}
    if model:
        params["model"] = model
    if NARROW:
        params["narrow"] = "true"

    started = time.perf_counter()
    try:
        response = requests.post(
            f"{BASE_URL}/resolve", params=params, timeout=TIMEOUT
        )
    except requests.exceptions.ConnectionError as exc:
        raise ServerDown(str(exc)) from exc
    elapsed = time.perf_counter() - started

    response.raise_for_status()
    result = response.json()
    found = [result.get("recipe_id"), *(result.get("candidate_recipe_ids") or [])]
    return (
        frozenset(rid for rid in found if rid),
        result.get("status") or "-",
        _axes(result),
        _tally(result),
        _alone(result),
        {**(result.get("narrow") or {}), "elapsed": elapsed},
    )


# ── 측정 ────────────────────────────────────────────────────────────


def _measure(
    entries, runs: int, outcomes: dict, axes: dict, tallies: dict, alones: dict,
    model: str | None = None, narrows: dict | None = None,
) -> None:
    """발화마다 runs 회 돌려 결과를 쌓음.

    입력  발화 목록 · 반복 횟수 · 채워 넣을 dict 넷 · 모델 이름
    규칙  outcomes[번호] 에 나온 (후보 집합, status) 조합의 Counter 를 쌓음.
          status 를 함께 묶는 것은 적중 표가 근접·빗나감을 가르기 위함임.
          적중 판정은 후보 집합만 봄 — 예전과 같은 숫자가 나와야 함
          axes[번호] 에 나온 (given, want, about, argument) 조합의 Counter 를 쌓음
          tallies[번호] 에 나온 (LLM 후보 수, 조회 후보 수, status, 조회 후보 집합)
          의 Counter 를 쌓음. 조회 후보 집합은 후보 표의 「조회 판정」 칸이 씀
          alones[번호] 에 나온 (LLM 단독 후보, 최종 후보, status) 의 Counter 를 쌓음.
          **outcomes 와 따로 둠.** 한 Counter 에 합치면 적중 표의 "틀렸을 때
          나온 것" 줄이 LLM 단독 값에 따라 더 쪼개져 표 모양이 바뀜.
          숫자는 안 바뀌지만 예전 표와 눈으로 못 맞대게 됨
          실행 하나가 끝날 때마다 점 하나를 찍음. 20회면 몇 분 걸려서
          아무것도 안 나오면 멈춘 줄 앎
          오류도 결과의 하나로 Counter 에 남김. 그때 축과 후보 수와 LLM 단독은
          안 쌓음. 응답이 없음
          narrows[번호] 에 회차마다 좁히기 칸(dict)을 목록으로 쌓음. 좁히기 표가 씀
          **NARROW 면 alones 를 안 쌓음.** 켜면 검산이 없어 그 칸은 「해당 없음」임
    제약  결과를 돌려주지 않는다.
          받은 dict 에 채움. 중간에 끊겨도(Ctrl-C · 서버 중단) 거기까지의
          결과가 부르는 쪽에 남아 있어야 표를 찍을 수 있음
    """
    for number, utterance, _expected, _default in entries:
        counter = Counter()
        axis_counter = Counter()
        tally_counter = Counter()
        alone_counter = Counter()
        narrow_rows = []
        outcomes[number] = counter
        axes[number] = axis_counter
        tallies[number] = tally_counter
        alones[number] = alone_counter
        if narrows is not None:
            narrows[number] = narrow_rows
        sys.stdout.write(f"  {number} ")
        sys.stdout.flush()
        for _ in range(runs):
            try:
                found, status, axis, tally, alone, narrow = _call_resolve(utterance, model)
                counter[(found, status)] += 1
                axis_counter[axis] += 1
                tally_counter[tally] += 1
                if not NARROW:
                    alone_counter[(alone, found, status)] += 1
                narrow_rows.append(narrow)
                sys.stdout.write(".")
            except ServerDown:
                sys.stdout.write("\n")
                raise
            except Exception as exc:  # noqa: BLE001 — 오류도 결과의 하나로 표에 남긴다.
                counter[(f"오류: {type(exc).__name__}", "-")] += 1
                sys.stdout.write("!")
            sys.stdout.flush()
        sys.stdout.write("\n")
        sys.stdout.flush()


# ── 표 ──────────────────────────────────────────────────────────────


# 적중 표의 네 칸. 자세한 뜻과 「빗나감」이 왜 제일 나쁜지는 파일 맨 위 주석에 있다.
HIT, NEAR, MISS, UNATTACHED = "적중", "근접", "빗나감", "못 붙음"

# 다섯째 칸. 검산을 거치기 전에 LLM 이 쓴 것만으로 잰 적중이다. **네 칸과 더하지
# 않는다** — 같은 시행을 다른 눈으로 본 것이라 합이 시행 횟수가 되지 않는다.
# 읽는 법은 파일 맨 위 주석에 있다.
ALONE = "LLM 단독"

# 칸 폭. 머리글보다 좁으면 표가 어긋난다 ("못 붙음" 이 폭 7).
NEAR_WIDTH = 8
MISS_WIDTH = 9
UNATTACHED_WIDTH = 10


def _grade(result, status: str, expected: set) -> str:
    """한 번의 결과를 네 칸 중 하나로 가름.

    입력  후보 집합(오류면 문자열) · 최종 status · 기대 recipe 집합
    출력  HIT · NEAR · MISS · UNATTACHED 중 하나
    규칙  넷이 서로 안 겹치고 빠짐이 없음. 그래야 넷의 합이 시행 횟수가 됨
          **적중 판정은 예전 그대로 set(result) == expected 임.**
          아래 순서를 바꿔도 적중 수는 안 변함 — 못 붙음이 먼저지만
          NO_MATCH 일 때 후보가 기대값과 같을 수는 없기 때문
          오류는 못 붙음에 넣음. 답이 안 붙은 것은 마찬가지임.
          몇 번이 오류였는지는 옆 "틀렸을 때 나온 것" 칸에 그대로 보임
    """
    if not isinstance(result, frozenset):  # 오류
        return UNATTACHED
    if status == "NO_MATCH" or not result:
        return UNATTACHED
    if set(result) == expected:
        return HIT
    if expected <= set(result):  # 하나로 못 좁혔을 뿐 정답이 남아 있다
        return NEAR
    return MISS


def _alone_hits(alone_counter, expected: set) -> tuple:
    """LLM 단독 적중 수.

    입력  alones[번호] Counter · 기대 recipe 집합
    출력  (적중 수, 잰 횟수, LLM 이 아무것도 안 쓴 횟수)
    규칙  적중 판정은 최종과 같은 모양임 — set(후보) == 기대값.
          최종은 검산을 지난 후보를 보고 여기는 LLM 이 쓴 후보를 봄.
          그 차이만이 두 칸의 차이임
          잰 횟수는 오류를 뺀 것임. 오류 회차는 alone_counter 에 안 쌓임
    """
    hits = done = missing = 0
    for (alone, _found, _status), count in (alone_counter or {}).items():
        done += count
        if alone is None:
            missing += count
        elif set(alone) == expected:
            hits += count
    return hits, done, missing


# 표시 칸의 폭. 머리글("표시" 폭 4)보다 좁으면 표가 어긋난다.
MARK_WIDTH = 6


def _print_rows(entries, outcomes: dict, alones: dict, widths: tuple) -> tuple:
    """한 묶음의 발화 줄을 찍고 그 묶음의 합을 돌려줌.

    입력  그 묶음의 발화 목록 · outcomes · alones · 칸 폭 묶음
    출력  (네 칸 Counter, 시행 횟수, LLM 단독 (적중, 잰 횟수, 안 쓴 횟수),
           완전 적중이 아닌 번호 목록)
    규칙  줄을 찍는 법은 묶음을 가르기 전과 글자까지 같음.
          **판정은 표시 칸을 안 봄** — 표시는 사람이 읽으라고 적는 칸이고
          _grade 는 예전 그대로 후보 집합과 status 만 봄
    제약  합계 줄은 안 찍는다. 부르는 쪽이 묶음마다 찍음
    """
    alone_width, hit_width, detail_column = widths

    total = Counter()
    total_runs = 0
    alone_total = alone_measured = alone_missing = 0
    imperfect = []

    for number, utterance, expected, _default in entries:
        counter = outcomes.get(number)
        done = sum(counter.values()) if counter else 0
        if done == 0:  # 끊겨서 아직 한 번도 안 돈 발화. 0/0 을 적으면 오해한다.
            continue

        graded = Counter()
        for (result, status), count in counter.items():
            graded[_grade(result, status, expected)] += count

        alone_hits, alone_done, missing = _alone_hits(alones.get(number), expected)
        alone_total += alone_hits
        alone_measured += alone_done
        alone_missing += missing

        hits = graded[HIT]
        total.update(graded)
        total_runs += done
        if hits < done:
            imperfect.append(number)

        misses = sorted(
            (
                (result, status, count)
                for (result, status), count in counter.items()
                if _grade(result, status, expected) != HIT
            ),
            key=lambda item: (
                -item[2],
                _short(item[0]) if isinstance(item[0], frozenset) else item[0],
            ),
        )

        head = (
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
            + _pad(_mark(number), MARK_WIDTH)
            + _pad(f"{alone_hits}/{alone_done}" if alone_done else "-", alone_width)
            + _pad(f"{hits}/{done}", hit_width)
            + _pad(str(graded[NEAR]), NEAR_WIDTH)
            + _pad(str(graded[MISS]), MISS_WIDTH)
            + _pad(str(graded[UNATTACHED]), UNATTACHED_WIDTH)
        )
        if not misses:
            print(head.rstrip())
            continue

        for index, (result, status, count) in enumerate(misses):
            shown = _short(result) if isinstance(result, frozenset) else result
            prefix = head if index == 0 else " " * detail_column
            print(
                prefix
                + _pad(shown, 20)
                + _pad(_grade(result, status, expected), 9)
                + _pad(status, 10)
                + f"{count}회"
            )

    return total, total_runs, (alone_total, alone_measured, alone_missing), imperfect


def _print_sum(label: str, total, total_runs: int, alone: tuple, widths: tuple) -> None:
    """한 줄짜리 합. 묶음마다 한 번, 맨 아래 합계에 한 번 쓴다.

    입력  줄 끝에 적을 이름 · 네 칸 Counter · 시행 횟수 · LLM 단독 셋 · 칸 폭
    규칙  적중 백분율 뒤에 이름을 붙임. **이름이 붙어야 어느 묶음의 값인지
          읽힌다** — 백분율 셋이 세로로 놓이면 어느 것이 아홉인지 못 가름
    """
    alone_width, hit_width, hit_column = widths
    grade_width = alone_width + hit_width + NEAR_WIDTH + MISS_WIDTH + UNATTACHED_WIDTH
    alone_total, alone_measured, alone_missing = alone

    percent = round(100 * total[HIT] / total_runs) if total_runs else 0
    alone_percent = round(100 * alone_total / alone_measured) if alone_measured else 0

    print(" " * hit_column + "─" * grade_width)
    print(
        " " * hit_column
        + _pad(f"{alone_total}/{alone_measured}" if alone_measured else "-", alone_width)
        + _pad(f"{total[HIT]}/{total_runs}", hit_width)
        + _pad(str(total[NEAR]), NEAR_WIDTH)
        + _pad(str(total[MISS]), MISS_WIDTH)
        + _pad(str(total[UNATTACHED]), UNATTACHED_WIDTH)
        + _pad(f"{percent}%", 7)
        + f"← {label}"
    )
    if alone_measured:
        print(
            " " * hit_column
            + _pad(f"{alone_percent}%", alone_width)
            + f"← {ALONE}"
            + (f" · LLM 이 아무것도 안 쓴 것 {alone_missing}회" if alone_missing else "")
        )
    elif NARROW:
        print(" " * hit_column + _pad("해당 없음", alone_width) + f"← {ALONE} (좁히기 켬 — 검산이 없다)")


def _print_table(entries, outcomes: dict, alones: dict, runs: int) -> None:
    """적중 표. **두 묶음을 갈라 찍는다.**

    입력  발화 목록 · outcomes · alones · 반복 횟수
    규칙  기준선 아홉과 확장 열아홉의 점수를 따로 냄. 합계 한 줄도 내지만
          아홉의 값이 그 위에 따로 보임. 둘을 한 백분율로 합치지 않음 —
          왜인지는 BASELINE_LAST 옆 주석에 있음
          한 묶음만 돌았으면(--only) 합계 줄은 안 찍음. 같은 값이 두 번 나옴
    """
    # 표의 "LLM 단독" 칸이 시작하는 자리. 표시 칸이 들어와 MARK_WIDTH 만큼 밀렸다.
    hit_column = 2 + 3 + UTTERANCE_WIDTH + 4 + MARK_WIDTH
    hit_width = len(f"{runs}/{runs}") + 4
    alone_width = max(hit_width, _width(ALONE) + 3)
    grade_width = alone_width + hit_width + NEAR_WIDTH + MISS_WIDTH + UNATTACHED_WIDTH
    detail_column = hit_column + grade_width  # "틀렸을 때 나온 것" 칸이 시작하는 자리.

    print()
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("표시", MARK_WIDTH)
        + _pad(ALONE, alone_width)
        + _pad(HIT, hit_width)
        + _pad(NEAR, NEAR_WIDTH)
        + _pad(MISS, MISS_WIDTH)
        + _pad(UNATTACHED, UNATTACHED_WIDTH)
        + "틀렸을 때 나온 것"
    )

    groups = _groups(entries)
    grand = Counter()
    grand_runs = 0
    grand_alone = [0, 0, 0]
    imperfect = []

    for label, group in groups:
        total, total_runs, alone, group_imperfect = _print_rows(
            group, outcomes, alones, (alone_width, hit_width, detail_column)
        )
        if total_runs == 0:  # 그 묶음이 아직 한 번도 안 돌았다
            continue
        _print_sum(label, total, total_runs, alone, (alone_width, hit_width, hit_column))
        grand.update(total)
        grand_runs += total_runs
        grand_alone = [a + b for a, b in zip(grand_alone, alone)]
        imperfect += group_imperfect

    if len(groups) > 1 and grand_runs:
        print()
        _print_sum(
            "합계", grand, grand_runs, tuple(grand_alone), (alone_width, hit_width, hit_column)
        )

    # 넷을 더하면 시행 횟수여야 한다. 아니면 _grade 에 구멍이 난 것이다.
    counted = grand[HIT] + grand[NEAR] + grand[MISS] + grand[UNATTACHED]
    if counted != grand_runs:
        print()
        print(f"  ⚠ 네 칸의 합 {counted} 가 시행 횟수 {grand_runs} 와 다르다 — _grade 를 본다")

    if imperfect:
        print()
        print("  ⚠ 완전 적중이 아닌 발화 : " + " · ".join(str(n) for n in imperfect))
        if grand[MISS]:
            print("  ★ 빗나감 " + str(grand[MISS]) + "회 — 확신하고 틀린 것이다. 근접보다 나쁘다")
            print(
                "     위험 · 애매 표시가 붙은 발화라면 그것이 알고 넣은 자리다."
                " 표시가 「시연」이나 「-」인데 빗나갔으면 ★ 그것이 발견이다"
            )


AXIS_WIDTH = 46  # 축 표에서 (given, want, about) 칸의 폭.

# 인자 칸의 폭. 축 셋과 한 칸에 담으면 표가 너무 넓어져 따로 둔다.
ARGUMENT_WIDTH = 22


def _print_axes(entries, axes: dict) -> None:
    """발화마다 어떤 축과 인자가 나왔는지.

    입력  발화 목록 · {번호: 축 조합 Counter}
    규칙  많이 나온 것부터. 조합이 하나면 한 줄, 갈리면 여러 줄
          적중 표가 안 맞을 때 무엇이 틀렸는지 여기서 갈림.
          축이 흔들렸는지, 축은 같은데 LLM 이 recipe 를 다르게 골랐는지
          인자는 축 셋과 따로 묶어 찍음. 세는 것은 넷을 함께 묶은 조합임
    """
    print()
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("given · want · about", AXIS_WIDTH)
        + _pad("argument", ARGUMENT_WIDTH)
        + "횟수"
    )

    for number, utterance, _expected, _default in entries:
        counter = axes.get(number)
        if not counter:
            continue

        head = (
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
        )
        rows = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        for index, (axis, count) in enumerate(rows):
            prefix = head if index == 0 else " " * _width(head)
            *three, argument = axis
            shown = _clip(" · ".join(three), AXIS_WIDTH - 2)
            print(
                prefix
                + _pad(shown, AXIS_WIDTH)
                + _pad(_clip(argument, ARGUMENT_WIDTH - 2), ARGUMENT_WIDTH)
                + f"{count}회"
            )


# 후보 표의 칸 폭. 머리글보다 좁으면 표가 어긋난다.
LLM_COUNT_WIDTH = 15
LOOKUP_COUNT_WIDTH = 16
STATUS_WIDTH = 12

# 후보 표의 「조회 판정」 네 갈래. 뜻은 파일 맨 위 주석에 있다. **적중 표의 네 칸과
# 다른 것을 센다** — 이쪽은 검산을 지나기 전 shortlist_recipe_ids 만 본다.
LOOKUP_HIT, LOOKUP_NEAR = "조회 적중", "조회 근접"
LOOKUP_MISS, LOOKUP_NONE = "★ 조회 빠짐", "조회 없음"

# 칸 폭. 머리글보다 좁으면 표가 어긋난다 ("★ 조회 빠짐" 이 폭 11).
LOOKUP_GRADE_WIDTH = 14


def _grade_lookup(shortlist, expected: set) -> str:
    """조회 후보만으로 정답에 닿는지를 네 갈래 중 하나로 가름.

    입력  조회 후보 집합(응답에 안 실렸으면 None) · 기대 recipe 집합
    출력  LOOKUP_HIT · LOOKUP_NEAR · LOOKUP_MISS · LOOKUP_NONE 중 하나
    규칙  넷이 서로 안 겹치고 빠짐이 없음. 그래야 넷의 합이 시행 횟수가 됨
          빈 목록과 응답에 안 실린 것을 함께 LOOKUP_NONE 으로 셈.
          둘 다 조회로는 아무 데도 못 닿는 자리임
          기대값과 같으면 적중, 기대값을 품고 더 많으면 근접,
          기대값을 못 품으면 빠짐
    제약  최종 후보를 보지 않는다. resolve_service._verdict 를 지나기 전
          shortlist_recipe_ids 그대로를 봄. 좁히기를 먼저 했을 때
          무엇이 남는지가 이 칸이 재려는 것임
    이력  「LLM 이 고를 범위를 온톨로지가 먼저 좁히는 안」의 전제를 재려고
          더함 (2026-08-25). 적중 표의 네 칸은 안 건드림
    """
    if not shortlist:
        return LOOKUP_NONE
    if set(shortlist) == expected:
        return LOOKUP_HIT
    if expected <= set(shortlist):
        return LOOKUP_NEAR
    return LOOKUP_MISS


def _print_candidates(entries, tallies: dict) -> None:
    """발화마다 후보가 몇 개까지 좁혀졌는지, 조회 후보에 정답이 남는지.

    입력  발화 목록 · {번호: 후보 수 조합 Counter}
    규칙  많이 나온 것부터. 조합이 하나면 한 줄, 갈리면 여러 줄
          축 표와 같은 모양. 나란히 놓고 읽음
          모델을 바꿔 잰 두 표를 견주는 것이 이 표의 쓸모.
          조회 후보 수는 그대로인데 LLM 후보 수만 줄면 모델이 문장을 읽어
          가른 것이고, 둘 다 그대로면 문장으로는 못 가르는 것
          「조회 판정」 칸은 조회 후보 수와 같은 줄에서 갈림. 개수가 같아도
          정답이 안 들어 있으면 좁히기로 손해를 보는 자리임
          표 아래에 네 갈래의 합계를 **묶음마다 한 줄씩** 적음. 적중 표와
          같은 이유로 기준선 아홉의 값이 따로 보여야 함
    """
    print()
    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("LLM 후보 수", LLM_COUNT_WIDTH)
        + _pad("조회 후보 수", LOOKUP_COUNT_WIDTH)
        + _pad("조회 판정", LOOKUP_GRADE_WIDTH)
        + _pad("status", STATUS_WIDTH)
        + "횟수"
    )

    totals = {label: Counter() for label, _group in _groups(entries)}
    for number, utterance, expected, _default in entries:
        counter = tallies.get(number)
        if not counter:
            continue
        total = totals[BASELINE_LABEL if number <= BASELINE_LAST else EXTENSION_LABEL]

        head = (
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
        )
        rows = sorted(counter.items(), key=lambda item: (-item[1], item[0][:3]))
        for index, (tally, count) in enumerate(rows):
            llm_count, lookup_count, status, shortlist = tally
            grade = _grade_lookup(shortlist, expected)
            total[grade] += count
            prefix = head if index == 0 else " " * _width(head)
            print(
                prefix
                + _pad(llm_count, LLM_COUNT_WIDTH)
                + _pad(lookup_count, LOOKUP_COUNT_WIDTH)
                + _pad(grade, LOOKUP_GRADE_WIDTH)
                + _pad(status, STATUS_WIDTH)
                + f"{count}회"
            )

    measured = [(label, total) for label, total in totals.items() if total]
    if not measured:
        return
    # 묶음 이름의 폭이 서로 달라 그냥 이으면 숫자 칸이 세로로 안 맞는다.
    label_width = max(_width(label) for label, _total in measured)

    def _line(label: str, total) -> None:
        print(
            "  조회 판정 · "
            + _pad(label, label_width)
            + "  "
            + " · ".join(
                f"{grade} {total[grade]}회"
                for grade in (LOOKUP_HIT, LOOKUP_NEAR, LOOKUP_MISS, LOOKUP_NONE)
            )
            + f"  (합 {sum(total.values())}회)"
        )

    print()
    for label, group_total in measured:
        _line(label, group_total)
    total = Counter()
    for _label, group_total in measured:
        total.update(group_total)
    if len(measured) > 1:
        _line("합계", total)
    if total[LOOKUP_MISS]:
        print(
            "  ★ 조회 후보에 정답이 없는 자리가 있다 — 지금 축으로 먼저 좁히면"
            " 그 발화는 정답에 못 닿는다"
        )
    else:
        print("  조회 빠짐 0 — 지금 축으로 먼저 좁혀도 정답이 후보에 남는다")


# 검산 표의 칸 폭. 머리글보다 좁으면 표가 어긋난다.
# LLM 이 CLARIFY 로 아홉 개를 늘어놓는 발화가 있다(6번). 그것이 한 줄에 들어가야
# 무엇을 골랐는지 보인다 — 잘라 놓으면 검산이 무엇을 걷어냈는지 못 읽는다.
ALONE_SET_WIDTH = 48
FINAL_SET_WIDTH = 24
CHANGE_WIDTH = 22

# 검산이 답을 바꾼 자리의 세 갈래. 파일 맨 위 주석의 세 갈래와 짝이다.
COVERED = "★ 맞는 답을 덮었다"
RESCUED = "검산이 살렸다"
NEUTRAL = "바꿨지만 판정은 같다"


def _print_verdict_changes(entries, alones: dict) -> None:
    """검산이 답을 바꾼 자리 전부.

    입력  발화 목록 · {번호: (LLM 단독 후보, 최종 후보, status) Counter}
    규칙  후보 집합이 달라진 회차만 찍음. 같으면 검산이 한 일이 없음
          바꾼 것이 좋게였는지 나쁘게였는지를 기대값으로 가름.
          맞는 답을 덮은 자리(COVERED)가 _verdict 를 다시 볼 근거임
          LLM 이 아무것도 안 쓴 회차(단독이 None)도 바꾼 것으로 셈 —
          없던 답을 검산이 만들어 준 것이라 그것도 검산이 한 일임
    제약  무엇이 맞는 배선인지 정하지 않는다. 바뀐 자리를 늘어놓을 뿐이고
          shortlist 를 어떻게 할지는 사람이 정한다
    """
    rows_by_number = {}
    for number, _utterance, expected, _default in entries:
        counter = alones.get(number)
        if not counter:
            continue
        rows = []
        for (alone, found, status), count in counter.items():
            if alone is not None and set(alone) == set(found):
                continue  # 검산이 한 일이 없다
            alone_hit = alone is not None and set(alone) == expected
            final_hit = _grade(found, status, expected) == HIT
            if alone_hit and not final_hit:
                change = COVERED
            elif final_hit and not alone_hit:
                change = RESCUED
            else:
                change = NEUTRAL
            rows.append((alone, found, status, change, count))
        if rows:
            rows_by_number[number] = sorted(rows, key=lambda row: -row[4])

    print()
    if not rows_by_number:
        print("  검산이 답을 바꾼 자리 : 없다 — LLM 단독과 최종이 회차마다 같았다")
        return

    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad(ALONE, ALONE_SET_WIDTH)
        + _pad("최종", FINAL_SET_WIDTH)
        + _pad("status", STATUS_WIDTH)
        + _pad("검산이 한 일", CHANGE_WIDTH)
        + "횟수"
    )

    tally = Counter()
    for number, utterance, _expected, _default in entries:
        rows = rows_by_number.get(number)
        if not rows:
            continue
        head = (
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
        )
        for index, (alone, found, status, change, count) in enumerate(rows):
            tally[change] += count
            prefix = head if index == 0 else " " * _width(head)
            print(
                prefix
                + _pad(
                    "없음" if alone is None else _clip(_short(alone), ALONE_SET_WIDTH - 2),
                    ALONE_SET_WIDTH,
                )
                + _pad(_clip(_short(found), FINAL_SET_WIDTH - 2), FINAL_SET_WIDTH)
                + _pad(status, STATUS_WIDTH)
                + _pad(change, CHANGE_WIDTH)
                + f"{count}회"
            )

    print()
    print(
        "  검산이 바꾼 회차 "
        + " · ".join(
            f"{label} {tally[label]}회" for label in (RESCUED, COVERED, NEUTRAL) if tally[label]
        )
    )
    if tally[COVERED]:
        print("  ★ 맞는 답을 덮은 자리가 있다 — resolve_service._verdict 를 다시 본다")


# ── 좁히기 표 ───────────────────────────────────────────────────────
#
# 켰을 때만 뜻이 있는 칸들. 끄면 합계 시간만 찍는다. 뜻은 파일 맨 위 주석에 있다.

NARROW_COUNT_WIDTH = 16
NARROW_CALL_WIDTH = 8
NARROW_FALLBACK_WIDTH = 9
NARROW_TIME_WIDTH = 9


def _mean(values) -> str:
    values = [v for v in values if v is not None]
    return f"{sum(values) / len(values):.1f}" if values else "-"


def _print_narrow(entries, narrows: dict) -> None:
    """좁히기 표. 발화마다 좁힌 후보 수 · 2차 · 폴백 둘 · 시간.

    입력  발화 목록 · {번호: [좁히기 칸 dict, ...]}
    규칙  좁힌 후보 수는 나온 값의 분포를 "2×3" 꼴로 적음 (후보 2개가 3회)
          2차 · 폴백 가 · 폴백 나는 그 발화에서 몇 회였는지
          시간은 평균(초). 1차 · 2차 · 폴백은 서버가 잰 LLM 시간, 합계는 이
          도구가 잰 /resolve 한 번의 시간 — 끔 · 켬을 이 칸으로 견줌
          묶음마다 합계 한 줄. 끔이면 합계 시간만 찍음
    제약  적중 판정을 안 건드린다. 응답의 narrow 칸과 시간만 읽음
    """
    print()
    if not NARROW:
        totals = {label: [] for label, _group in _groups(entries)}
        for number, _u, _e, _d in entries:
            rows = narrows.get(number) or []
            totals[BASELINE_LABEL if number <= BASELINE_LAST else EXTENSION_LABEL] += [
                row["elapsed"] for row in rows
            ]
        measured = [(label, values) for label, values in totals.items() if values]
        for label, values in measured:
            print(f"  시간 · {label}  /resolve 한 번 평균 {_mean(values)}초 (합 {len(values)}회)")
        if len(measured) > 1:
            everything = [v for _l, values in measured for v in values]
            print(f"  시간 · 합계         /resolve 한 번 평균 {_mean(everything)}초 (합 {len(everything)}회)")
        print("  좁히기 표 : 해당 없음 (끔 — 지금 길)")
        return

    print(
        "  "
        + _pad("#", 3)
        + _pad("발화", UTTERANCE_WIDTH + 4)
        + _pad("좁힌 후보 수", NARROW_COUNT_WIDTH)
        + _pad("2차", NARROW_CALL_WIDTH)
        + _pad("폴백 가", NARROW_FALLBACK_WIDTH)
        + _pad("폴백 나", NARROW_FALLBACK_WIDTH)
        + _pad("1차 s", NARROW_TIME_WIDTH)
        + _pad("2차 s", NARROW_TIME_WIDTH)
        + _pad("폴백 s", NARROW_TIME_WIDTH)
        + "합계 s"
    )

    totals = {label: Counter() for label, _group in _groups(entries)}
    times = {label: {"first": [], "second": [], "fallback": [], "elapsed": []} for label in totals}
    for number, utterance, _expected, _default in entries:
        rows = narrows.get(number) or []
        if not rows:
            continue
        label = BASELINE_LABEL if number <= BASELINE_LAST else EXTENSION_LABEL
        total, clock = totals[label], times[label]

        counts = Counter(row.get("shortlist_count", "-") for row in rows)
        second = sum(1 for row in rows if row.get("second_called"))
        empty = sum(1 for row in rows if row.get("fallback") == "empty")
        none = sum(1 for row in rows if row.get("fallback") == "none")
        total.update({"runs": len(rows), "second": second, "empty": empty, "none": none,
                      "single": counts.get(1, 0)})
        clock["first"] += [row.get("first_seconds") for row in rows]
        clock["second"] += [row.get("second_seconds") for row in rows]
        clock["fallback"] += [row.get("fallback_seconds") for row in rows]
        clock["elapsed"] += [row["elapsed"] for row in rows]

        shown = " ".join(f"{count}×{times_}" for count, times_ in sorted(counts.items(), key=lambda i: str(i[0])))
        print(
            "  "
            + _pad(str(number), 3)
            + _pad(_clip(utterance, UTTERANCE_WIDTH), UTTERANCE_WIDTH + 4)
            + _pad(_clip(shown, NARROW_COUNT_WIDTH - 2), NARROW_COUNT_WIDTH)
            + _pad(str(second), NARROW_CALL_WIDTH)
            + _pad(str(empty), NARROW_FALLBACK_WIDTH)
            + _pad(str(none), NARROW_FALLBACK_WIDTH)
            + _pad(_mean(row.get("first_seconds") for row in rows), NARROW_TIME_WIDTH)
            + _pad(_mean(row.get("second_seconds") for row in rows), NARROW_TIME_WIDTH)
            + _pad(_mean(row.get("fallback_seconds") for row in rows), NARROW_TIME_WIDTH)
            + _mean(row["elapsed"] for row in rows)
        )

    measured = [(label, totals[label], times[label]) for label in totals if totals[label]]
    if not measured:
        return
    label_width = max(_width(label) for label, _t, _c in measured)

    def _line(label, total, clock):
        print(
            "  좁히기 · "
            + _pad(label, label_width)
            + f"  시행 {total['runs']}회 · 후보 하나라 2차 안 부름 {total['single']}회"
            + f" · 2차 {total['second']}회 · 폴백 가 {total['empty']}회 · 폴백 나 {total['none']}회"
            + f" · 1차 {_mean(clock['first'])}s · 2차 {_mean(clock['second'])}s"
            + f" · 폴백 {_mean(clock['fallback'])}s · 합계 {_mean(clock['elapsed'])}s"
        )

    print()
    for label, total, clock in measured:
        _line(label, total, clock)
    if len(measured) > 1:
        grand = Counter()
        grand_clock = {"first": [], "second": [], "fallback": [], "elapsed": []}
        for _label, total, clock in measured:
            grand.update(total)
            for key in grand_clock:
                grand_clock[key] += clock[key]
        _line("합계", grand, grand_clock)
    print("  검산 표 : 해당 없음 (좁히기 켬 — 대조할 두 목록이 없다)")


def _recipe_state() -> str:
    """표 머리에 적을 지금 recipe 상태. _init 그대로인지, 노드가 등록됐는지."""
    current = sorted(p.stem for p in RECIPES_DIR.glob("recipe_*.yaml"))
    initial = sorted(p.stem for p in INIT_RECIPES_DIR.glob("recipe_*.yaml"))
    label = "_init" if current == initial else "등록됨"
    return f"{label} (recipe {len(current)})"


def main() -> int:
    parser = argparse.ArgumentParser(description="후보 발화가 지금 온톨로지에서 통하는지 잰다.")
    parser.add_argument("--runs", type=int, default=5, help="발화마다 몇 번 돌릴지 (기본 5)")
    parser.add_argument(
        "--only",
        default="",
        help="돌릴 발화 번호. 예: 2,4 (기준선 아홉만: 1,2,3,4,5,6,7,8,9)",
    )
    parser.add_argument("--model", default="", help="쓸 모델. 예: qwen2.5:7b (기본: 서버 기본 모델)")
    parser.add_argument(
        "--narrow", action="store_true",
        help="좁히기 길(LLM 두 번 부르기)로 잰다. 기본은 끔 — 지금 길",
    )
    args = parser.parse_args()

    global NARROW
    NARROW = args.narrow

    if args.only:
        wanted = [int(part) for part in args.only.replace(" ", "").split(",") if part]
        entries = [entry for entry in UTTERANCES if entry[0] in wanted]
        missing = sorted(set(wanted) - {entry[0] for entry in entries})
        if missing:
            print(f"목록에 없는 번호 : {missing}")
            return 2
    else:
        entries = [entry for entry in UTTERANCES if entry[3]]

    # 모델을 적는다. NOTES.md 의 측정 기록은 조건 없는 숫자를 받지 않는다.
    print(
        f"발화 {len(entries)}개 × {args.runs}회 · {_recipe_state()}"
        f" · 모델 {args.model or '서버 기본'}"
        f" · 좁히기 {'켬' if NARROW else '끔'}"
    )
    print()

    outcomes, axes, tallies, alones, narrows, note, status = {}, {}, {}, {}, {}, "", 0
    try:
        _measure(entries, args.runs, outcomes, axes, tallies, alones, args.model, narrows)
    except ServerDown:
        # 재시도하지 않는다. 여기까지 잰 것이 있으면 표는 찍는다.
        note, status = "uvicorn 을 먼저 실행하세요", 1
    except KeyboardInterrupt:
        # 오래 걸리는 도구라 중간에 끊는 일이 생긴다. 거기까지의 표를 찍는다.
        note = "(중단됨 — 여기까지의 결과)"

    if any(outcomes.values()):
        _print_table(entries, outcomes, alones, args.runs)
    if any(axes.values()):
        _print_axes(entries, axes)
    if any(tallies.values()):
        _print_candidates(entries, tallies)
    if any(alones.values()):
        _print_verdict_changes(entries, alones)
    if any(narrows.values()):
        _print_narrow(entries, narrows)
    if note:
        print()
        print(note)

    return status


if __name__ == "__main__":
    sys.exit(main())
