# Test Suite v2 live run — failure classification (23 of 219)

These are evaluation results, not bugs I fixed. No prompt, schema, GT or Resolve change was made in response. This was a single run; nothing was rerun.

## Summary

| class | count | cases |
|---|---|---|
| Ambiguous Recipe boundary (a known or plausible menu overlap; the model asked back with the right recipe among the candidates) | 9 | 46, 47, 49, 53, 82, 85, 99, 114 (CLARIFY) · 48 (picked the overlapping 016) |
| Wrong Recipe (a clear model error) | 2 | 119, 191 |
| Semantic extraction | 3 | 59, 96, 97 |
| OOS handling | 8 | 199, 205, 206, 207, 208, 210, 213, 218 |
| GT/design question (OOS expectation arguably too strict) | 1 | 211 |
| Evaluator/runtime error | 0 | – |

## In-scope — function (11)

| case | utterance | expected | actual | class | note |
|---|---|---|---|---|---|
| 46 | 서울 종로 선거구 조회해줘 | 015 | CLARIFY [015, 016] | boundary | Same 015/016 overlap that FULL48 #10 flags as QUESTION. 「조회」 doesn't say whether winner or pledges are wanted |
| 47 | 경기 수원시갑 선거구 알려줘 | 015 | CLARIFY [015, 016] | boundary | same |
| 48 | 부산 해운대구을 지역구 정보 찾아줘 | 015 | SELECT 016 | boundary | 「정보」 was read as including winner and pledges. The only MISS in the run |
| 49 | 인천 연수구갑 선거구 하나만 보여줘 | 015 | CLARIFY [015, 016] | boundary | same |
| 53 | 대전 유성구 지역구 의원이랑 공약 다 보여줘 | 016 | CLARIFY [016, 042] | boundary | Admin name (016) vs place → district pledges (042). 대전 유성구 works as either |
| 82 | 청주역 지역구 공약 중에 교통 분야만 보여줘 | 042 | CLARIFY [010, 042] | boundary | The 「교통 분야」 filter pulled in 010 (pledge search by field) |
| 85 | 강릉역 선거구 의원 공약 목록 줘 | 042 | CLARIFY [016, 042] | boundary | 016 includes pledges too, but it takes an admin/district name, not a station |
| 99 | GS칼텍스 전기차 충전소 지금 쓸 수 있는지 봐줘 | 052 | CLARIFY [052, 060] | boundary | Same 052/060 overlap as FULL48 #20 (QUESTION) |
| 114 | 강남역 부근 전기차 충전소 빈 충전기 몇 대야 | 060 | CLARIFY [052, 060] | boundary | The mirror of #99 |
| 119 | 대전역 도달권 지도에 그려줘 | 061 | CLARIFY [061, 063] | **wrong recipe** | The utterance names a place, and 063 is for no place name. Likely v1's "only the method differs → CLARIFY" rule firing on the unspecified mode. FULL48 #25 「의왕역에서 도달권 보여줘」 passes; this phrasing has no 「에서」 |
| 191 | 지금 보이는 곳 충전소 빈 충전기 알려줘 | 056 | CLARIFY [026, 056] | **wrong recipe** | 026 is screen CCTV, which has nothing to do with chargers. A candidate-set error |

## In-scope — input (3)

| case | utterance | field | expected | actual | class | note |
|---|---|---|---|---|---|---|
| 59 | 경복궁 일대 동 경계 보여줘 | admin_level | 읍면동 | null | semantic extraction | The model treated 경복궁 as a POI → null and dropped the explicit level word 「동」. The GT follows policy (explicit level word → level) |
| 96 | 환경부 충전소 충전기 몇 대 비었어 | argument | 환경부 | 환경부 충전소 | semantic extraction | The category noun 충전소 was kept. ev.searchStations.query matches name/address/operator, so 「환경부 충전소」 probably misses the operator 환경부. The GT follows the FULL48 convention (search target only). *Design note:* this is the first time the convention for "keyword + category noun" is being tested |
| 97 | 이마트 충전소에 빈 충전기 있는지 알려줘 | argument | 이마트 | 이마트 충전소 | semantic extraction | same |

## Out-of-scope — scope (9)

| case | utterance | category | accepted | actual outcome | class | note |
|---|---|---|---|---|---|---|
| 199 | 이번 달 철도 사고 보고서 써줘 | unsupported | NO_MATCH | SELECT 014 → READY | OOS handling | A writing request was mapped onto document search. Over-selection |
| 205 | 도달권 보여줘 | ambiguous | CLARIFY | SELECT 063 → READY | OOS handling | Collapsed to point-based with no deixis. It would run on the selected point |
| 206 | 행정경계 보여줘 | ambiguous | CLARIFY | SELECT 005 → MISSING_ARGUMENT | OOS handling | Safe (not executed), but it didn't ask back |
| 207 | 충전소 빈 충전기 알려줘 | ambiguous | CLARIFY | SELECT 052 → MISSING_ARGUMENT | OOS handling | same |
| 208 | 인구 얼마나 돼 | ambiguous | CLARIFY | SELECT 031 → READY | OOS handling | Defaulted to the screen with no screen word |
| 210 | 철도 노선 뭐 있어 | ambiguous | CLARIFY | SELECT 003 → MISSING_ARGUMENT | OOS handling | Safe, but it didn't ask back |
| 211 | 여기 선거구 알려줘 | ambiguous | CLARIFY | SELECT 020 → READY | **GT/design question** | 020 (district name only) is a defensible reading. The CLARIFY expectation came from the old FULL48 note of CLARIFY {020, 021}. A human should decide whether this belongs in ambiguous |
| 213 | 좌표 알려줘 | insufficient | CLARIFY / MISSING_ARGUMENT | NO_MATCH | OOS handling | Told the user "unsupported" instead of asking for a place |
| 218 | 그 충전소 충전기 비었는지 봐줘 | insufficient | CLARIFY / MISSING_ARGUMENT | SELECT 056 → READY | OOS handling | Read 「그」 as the current screen. It would run on screen context, the riskiest of the OOS misses |

## Observations for the next decision (not acted on)

1. **The ambiguous-OOS weakness is structural:** 6 of 8 ambiguous utterances collapsed to a single recipe. v1's "all method-only variants → CLARIFY" rule doesn't fire when there's no anchor at all. Three of them still end MISSING_ARGUMENT, so nothing wrong would execute. Two would execute on the screen or point context (#205, #208).
2. **The boundaries are the ones already flagged in the FULL48 audit** (015/016, 052/060), plus two new pairs: 016/042 (admin name vs place) and 010/042 (field filter). They show up as NEAR (CLARIFY with the right answer present), not as wrong answers.
3. **The only in-scope wrong-recipe errors are #119 and #191.** Every picked-point case passed, 45/45.
4. **Extraction is strong (187/190).** The two argument misses share one pattern: an operator or brand keyword followed by the category noun 충전소.
5. **FULL48 finding from the leak check:** FULL48 #26 contains the prompt's example string `15분, 30분, 60분`. FULL48 is frozen, so this is recorded and not changed.
