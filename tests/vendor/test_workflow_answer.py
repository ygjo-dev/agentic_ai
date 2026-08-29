"""대상 : vendor/asap/workflow_answer.py — trace 한 벌을 사람이 읽는 답으로

순수 함수다. 네트워크 · 온톨로지 · LLM · 파일을 하나도 안 쓴다. trace 를 손으로
만들어 나온 문자열만 본다.

여기 쓰는 결과 모양은 전부 asap_probe_out 의 실물이거나 2026-08-22 화면 실측이다.

`demo/` 테스트를 늘리지 말라는 규칙의 밖이다. 이 파일은 demo/ 가 아니고 입출력이
문자열뿐이라 그 계층의 구조가 바뀌어도 따라다니지 않는다.
"""

from vendor.asap.workflow_answer import compose_workflow_answer, step_failed

# asap_probe_out/geo.geocode.osong.json 실물.
OSONG = {
    "location": [127.3276666158151, 36.61995281117007],
    "bbox": [[127.3227, 36.615], [127.3327, 36.625]],
    "address": "충청북도 청주시 흥덕구 오송읍 봉산리 369-1",
}

# "오송시 cctv 보여줘" 가 찍은 곳 (2026-08-23 화면 실측).
# 거제시에 실제로 "오송리" 가 있다. geocode 가 헛짚은 것이 아니다.
WRONG_PLACE = {
    "location": [128.5944, 34.8225],
    "address": "경상남도 거제시 동부면 오송리 143-2",
}


def geocode_step(result, query="오송역"):
    return {"id": "s1", "tool": "geo.geocode", "input": {"query": query}, "result": result}


def test_an_empty_list_does_not_get_the_headline():
    """0건인데 headline 을 그대로 쓰면 성공한 것처럼 읽힘.

    실측 : adminBoundary.findBoundaryByPoint 가 features 0개를 돌려준 발화에
    "오송역 행정구역을 조회했습니다." 가 그대로 나갔음.
    """
    trace = [
        geocode_step(OSONG),
        {
            "id": "s2",
            "tool": "adminBoundary.findBoundaryByPoint",
            "input": {"lon": 127.3, "lat": 36.6},
            "result": {"features": [], "count": 0, "crs": "EPSG:4326"},
        },
    ]
    answer = compose_workflow_answer({"answer_instruction": "오송역 행정구역을 조회했습니다."}, trace)

    assert answer.startswith("찾지 못했습니다.")
    assert "오송역 행정구역을 조회했습니다." not in answer
    assert "0건" in answer


def test_the_geocoded_address_is_in_the_answer():
    """좌표만 보이면 어디를 찍었는지 사람이 못 알아봄. 주소가 판정 근거임."""
    answer = compose_workflow_answer(
        {"answer_instruction": "오송역 좌표를 조회했습니다."}, [geocode_step(OSONG)]
    )

    assert "충청북도 청주시 흥덕구 오송읍 봉산리 369-1" in answer
    assert "127.3277, 36.6200" in answer


def test_a_wrong_place_shows_its_own_address():
    """없는 지명이 실재하는 비슷한 지명으로 풀려도 성공으로 보임. 주소가 그것을 드러냄.

    실측 : "오송시" 가 경상남도 거제시 동부면 오송리(128.5944, 34.8225)로 풀리고
    거기 CCTV 2건이 실제로 왔음. 거제시에 오송리가 있으므로 geocode 는 가장
    비슷한 실제 지명을 정직하게 돌려준 것이고 어느 층에도 버그가 없음.
    그런데 답에 "오송시 CCTV 를 조회했습니다." 만 있어 알아챌 방법이 없었음.
    """
    trace = [
        geocode_step(WRONG_PLACE, query="오송시"),
        {
            "id": "s2",
            "tool": "road.getCctv",
            "input": {"minLon": 128.4, "minLat": 34.7, "maxLon": 128.7, "maxLat": 34.9},
            "result": [{"cctvname": "cctv-1"}, {"cctvname": "cctv-2"}],
        },
    ]
    answer = compose_workflow_answer({"answer_instruction": "오송시 CCTV 를 조회했습니다."}, trace)

    assert "경상남도 거제시 동부면 오송리 143-2" in answer
    assert "2건" in answer


def test_no_result_value_reaches_the_answer():
    """geojson · cctvUrl 이 화면에 raw JSON 으로 새던 자리를 막았음.

    실측 : ev.searchChargers 의 답이 {"count": 100, "totalMatches": 2195, …
    "geojson": {"type": "FeatureCo… 로 잘린 채 화면에 떴음.
    """
    trace = [
        geocode_step(OSONG),
        {
            "id": "s2",
            "tool": "ev.searchChargers",
            "input": {"center": [127.3, 36.6]},
            "result": {
                "count": 100,
                "totalMatches": 2195,
                "geojson": {"type": "FeatureCollection", "features": [{"id": "충전기"}]},
            },
        },
    ]
    answer = compose_workflow_answer({"answer_instruction": "오송역 전기차 충전기를 조회했습니다."}, trace)

    assert "100건 (전체 2,195건)" in answer
    assert "FeatureCollection" not in answer
    assert "충전기" not in answer.replace("전기차 충전기를 조회했습니다.", "")


def test_an_error_body_that_came_back_with_200_is_a_failure():
    """Gateway 가 실패를 200 + {"error": {...}} 로 돌려줌.

    mcp_client 가 예외를 안 올려 vendor 는 이것을 성공한 호출로 봄.
    실물 : asap_probe_out/geo.geocode.english_notfound.json
    """
    result = {"error": {"code": "NOT_FOUND", "message": "장소 'Osong Station'을(를) 찾을 수 없습니다."}}
    answer = compose_workflow_answer(
        {"answer_instruction": "Osong Station 좌표를 조회했습니다."},
        [geocode_step(result, query="Osong Station")],
    )

    assert answer.startswith("조회하지 못했습니다.")
    assert "Osong Station 좌표를 조회했습니다." not in answer
    assert "찾을 수 없습니다" in answer
    assert "NOT_FOUND" not in answer


def test_a_raw_tool_error_never_reaches_the_answer():
    """error_detail 은 HTTP 오류 문장 · 내부 URL · Gateway 응답 본문을 담음.

    실측 : web-search/web.search 가 권한이 없어 500 이고, vendor 문구가 그
    원문을 통째로 답에 넣었음. 사람에게 필요한 것은 권한이 없다는 사실뿐임.
    """
    trace = [{
        "id": "s1",
        "tool": "web.search",
        "input": {"query": "철도 안전"},
        "error": "s1 단계 MCP tool 실행에 실패했습니다: Server error '500 Internal Server Error'",
        "error_detail": (
            "Server error '500 Internal Server Error' for url "
            "'http://localhost:3000/api/tools/execute' Response body: "
            "MCP tool 'web-search/web.search' is not applied for this user."
        ),
    }]
    answer = compose_workflow_answer({"answer_instruction": "철도 안전 문서를 조회했습니다."}, trace)

    assert answer.startswith("조회하지 못했습니다.")
    assert "이 도구를 쓸 권한이 없습니다" in answer
    assert "localhost" not in answer
    assert "500" not in answer


def test_missing_input_fields_stay_in_the_answer():
    """error_detail 이 없는 항목은 우리가 입력을 못 채운 것. 필드 이름뿐이라 안전함.

    사람에게 뜻이 없는 "{step_id} 단계 " 접두만 뗌.
    """
    trace = [{
        "id": "s1",
        "tool": "road.getCctv",
        "input": {},
        "error": "s1 단계 필수 입력값이 비어 있습니다: minLon, minLat, maxLon, maxLat",
    }]
    answer = compose_workflow_answer({"answer_instruction": "대전~김천 CCTV 를 조회했습니다."}, trace)

    assert "필수 입력값이 비어 있습니다: minLon, minLat, maxLon, maxLat" in answer
    assert "s1 단계" not in answer


def test_a_failed_run_never_shows_the_success_headline():
    """vendor 는 중단할 때 대개 trace 에 아무것도 안 남김.

    조기 반환 열한 곳 중 아홉이 append 없이 _failed_workflow_result 로 나가고
    그중 일곱은 trace 마지막이 성공한 앞 단계다. trace 만 보면 성공으로 읽히므로
    부르는 쪽이 아는 것(errors)을 failed 로 넘긴다.
    """
    answer = compose_workflow_answer(
        {"answer_instruction": "오송역 전기차 충전기를 조회했습니다."},
        [geocode_step(OSONG)],
        failed=True,
    )

    assert answer.startswith("조회하지 못했습니다.")
    assert "오송역 전기차 충전기를 조회했습니다." not in answer


def test_a_middle_step_error_beats_a_later_success():
    """중간 단계가 200 오류인데 다음 도구가 그 칸을 optional 로 받으면 끝까지 돔.

    vendor 는 예외를 못 받아 errors 도 비어 있고, 마지막 항목만 보면 건수가
    차 있어 성공이다. 앞 단계가 안 풀렸으니 그 건수는 발화와 상관이 없다.
    """
    trace = [
        geocode_step({"error": {"code": "NOT_FOUND", "message": "장소를 찾을 수 없습니다."}}),
        {
            "id": "s2",
            "tool": "election.findAssemblyPledgeDistrictByPoint",
            "input": {},
            "result": {"features": [{"id": "충북 제1선거구"}], "count": 1},
        },
    ]
    answer = compose_workflow_answer({"answer_instruction": "오송역 공약을 조회했습니다."}, trace)

    assert answer.startswith("조회하지 못했습니다.")
    assert "오송역 공약을 조회했습니다." not in answer
    assert "election.findAssemblyPledgeDistrictByPoint  1건" in answer


def test_a_successful_trace_keeps_its_shape():
    """성공한 발화의 답은 안 바뀜. headline · 빈 줄 · 번호 붙은 단계 목록."""
    answer = compose_workflow_answer(
        {"answer_instruction": "오송역 좌표를 조회했습니다."}, [geocode_step(OSONG)]
    )

    assert answer == (
        "오송역 좌표를 조회했습니다.\n"
        "\n"
        "1. geo.geocode       오송역 → 충청북도 청주시 흥덕구 오송읍 봉산리 369-1 "
        "(127.3277, 36.6200)"
    )


def test_an_empty_result_carries_its_reason():
    """0건이 우리 배선 탓인지 저쪽 데이터 탓인지가 화면에서 갈려야 함.

    실측 : adminBoundary.findBoundaryByPoint 가 0건과 함께 warning 을 실어 보냄.
    이유가 응답에 이미 있는데 답에는 "0건" 까지만 나왔음.
    """
    trace = [
        geocode_step(OSONG),
        {
            "id": "s2",
            "tool": "adminBoundary.findBoundaryByPoint",
            "input": {"lon": 127.3, "lat": 36.6},
            "result": {
                "features": [],
                "count": 0,
                "warning": "행정구역 DB 데이터가 없거나 PostGIS 연결을 사용할 수 없습니다.",
            },
        },
    ]
    answer = compose_workflow_answer({"answer_instruction": "오송역 행정구역을 조회했습니다."}, trace)

    assert answer.startswith("찾지 못했습니다.")
    assert "0건 · 행정구역 DB 데이터가 없거나 PostGIS 연결을 사용할 수 없습니다." in answer


def test_a_warning_next_to_a_count_never_shows():
    """건수가 있으면 답이 나온 것임. 거기 warning 을 붙이면 사람이 헷갈림."""
    trace = [
        geocode_step(OSONG),
        {
            "id": "s2",
            "tool": "adminBoundary.searchBoundaries",
            "input": {"query": "오송읍"},
            "result": {"features": [{"id": "오송읍"}], "count": 1, "warning": "일부만 반환했습니다."},
        },
    ]
    answer = compose_workflow_answer({"answer_instruction": "오송읍 행정구역을 조회했습니다."}, trace)

    assert "1건" in answer
    assert "일부만 반환했습니다." not in answer


# ── 단계 하나가 터졌는가 ────────────────────────────────────────────
#
# 답과 진행 표시가 같은 판정을 써야 한다. demo 의 진행 표시가 item["error"] 만
# 봐서 200 오류를 "완료" 로 찍었고, 그 탓에 "대전~김천 구간이 유효하다" 는 틀린
# 사실이 문서에 박혔다 (NOTES.md 2026-08-22 넷째의 정정).


def test_200_으로_돌아온_오류도_실패다():
    """Gateway 는 실패를 200 과 {"error": {...}} 로도 돌려줌.

    그것은 item["result"] 에 담기고 item["error"] 는 비어 있음. 그 칸만 보면
    터진 호출이 "완료" 로 찍힘.
    """
    item = {
        "id": "s1",
        "tool": "rail.getSectionGeometry",
        "input": {"sectionName": "대전~김천"},
        "result": {"error": {"code": "NOT_FOUND", "message": "구간을 찾지 못했습니다."}},
    }

    assert step_failed(item)
    assert "error" not in item, "이 항목의 error 칸은 비어 있어야 시험이 성립함"


def test_0건은_실패가_아니다():
    """호출은 끝났고 결과가 없는 것뿐임.

    답 문구가 "찾지 못했습니다" 로 이미 말하므로 진행 표시까지 "실패" 라고
    찍으면 도구가 터진 것과 안 갈림.
    """
    item = {
        "id": "s2",
        "tool": "adminBoundary.findBoundaryByPoint",
        "input": {"lon": 127.3, "lat": 36.6},
        "result": {"features": [], "count": 0, "warning": "행정구역 DB 데이터가 없거나…"},
    }

    assert not step_failed(item)


# ── 목록형이 아닌 응답 · 여럿 중 하나 ──────────────────────────────
#
# 건수 칸이 없는 응답은 칸 이름만 찍혔고(인구), 여덟 건 중 하나를 줄 때
# 나머지 일곱을 안 알렸다(선거). 아래 결과는 전부 tools/probe_out 의 실물에서
# 필요한 만큼만 잘라 온 것이다.


# tools/probe_out/population.getAgeProfile.sigungu-43113-2026-08-24.json 실물.
# ageBands 23건 · ages 111건 중 각 한 건만 남겼다. 나머지는 같은 모양의 반복이다.
AGE_PROFILE = {
    "datasetId": "mois-legal-dong-resident-population",
    "referenceDate": "2026-06-30",
    "level": "sigungu",
    "code": "43113",
    "sourceAreaCodes": ["43113"],
    "boundaryMatch": "exact",
    "name": "청주시 흥덕구",
    "totalPopulation": 292625,
    "malePopulation": 149484,
    "femalePopulation": 143141,
    "ageBands": [
        {"label": "0~4세", "minAge": 0, "maxAge": 4, "total": 10849, "male": 5479,
         "female": 5370, "rate": 3.71},
    ],
    "ages": [{"age": 0, "total": 1875, "male": 964, "female": 911}],
}


def age_profile_step(result=AGE_PROFILE):
    return {
        "id": "s3",
        "tool": "population.getAgeProfile",
        "input": {"level": "sigungu", "code": "43113"},
        "result": result,
    }


def test_인구_응답의_수치가_답에_실린다():
    """건수 칸이 없는 응답이 칸 이름만 찍혔음.

    실측 (2026-08-24 화면) : "춘천역 연령대별 인구 구성을 조회했습니다" 뒤에
    "칸: datasetId · referenceDate · level · code · sourceAreaCodes ·
    boundaryMatch" 만 나왔음. 일곱째 name 과 여덟째 totalPopulation 이
    KEY_LIMIT 6 에서 잘려 수치가 하나도 안 실렸음.
    """
    answer = compose_workflow_answer(
        {"answer_instruction": "청주시 흥덕구 연령대별 인구 구성을 조회했습니다."},
        [age_profile_step()],
    )

    assert "청주시 흥덕구 292,625명 (남 149,484 · 여 143,141) · 2026-06-30 기준" in answer
    assert "칸: datasetId" not in answer


def test_인구_응답의_목록_값은_안_샌다():
    """ageBands 23건 · ages 111건이 답에 통째로 실리면 화면이 raw JSON 이 됨."""
    answer = compose_workflow_answer(
        {"answer_instruction": "청주시 흥덕구 연령대별 인구 구성을 조회했습니다."},
        [age_profile_step()],
    )

    assert "0~4세" not in answer
    assert "minAge" not in answer
    assert "10,849" not in answer


def test_여럿_중_하나를_준_것을_밝힌다():
    """여덟 건이 맞는데 하나만 주면서 나머지 일곱을 안 알렸음.

    실물 : tools/probe_out/election.getDistrict.name-앞두글자충북-2026-08-25.json.
    name="충북" 이 부분 이름으로 걸려 count 1 · totalMatches 8 이 왔고 답은
    "1건 (전체 8건)" 이라 무엇을 받았는지도 여럿 중 하나인지도 안 보였음.
    """
    trace = [{
        "id": "s1",
        "tool": "election.getDistrict",
        "input": {"name": "충북"},
        "result": {
            "type": "FeatureCollection",
            "features": [],
            "item": {"code": "2431401", "name": "충북 청주서원", "sido": "충북",
                     "district": "청주서원"},
            "count": 1,
            "totalMatches": 8,
        },
    }]
    answer = compose_workflow_answer({"answer_instruction": "충북 선거구를 조회했습니다."}, trace)

    assert "충북 청주서원" in answer
    assert "전체 8건 중 하나" in answer


def test_전체가_받은_것과_같으면_중_하나라고_안_한다():
    """totalMatches 1 은 여럿이 아님. 실물 : election.getDistrict.name-실제이름.json."""
    trace = [{
        "id": "s1",
        "tool": "election.getDistrict",
        "input": {"name": "충북 청주서원"},
        "result": {
            "features": [],
            "item": {"code": "2431401", "name": "충북 청주서원", "sido": "충북"},
            "count": 1,
            "totalMatches": 1,
        },
    }]
    answer = compose_workflow_answer({"answer_instruction": "선거구를 조회했습니다."}, trace)

    assert "충북 청주서원 · 1건" in answer
    assert "중 하나" not in answer


def test_totalMatches_가_없으면_지어내지_않는다():
    """그 칸을 안 주는 도구가 있음. 실물 : ev.getStation.statId-stationId.json."""
    trace = [{
        "id": "s1",
        "tool": "ev.getStation",
        "input": {"statId": "PL033780"},
        "result": {
            "item": {"id": "ev_station_PL033780", "stationId": "PL033780", "name": "포빌",
                     "address": "충북 청주시 흥덕구 사직대로 38"},
            "chargers": [{"chargerId": "00", "outputKw": 7}],
            "count": 1,
        },
    }]
    answer = compose_workflow_answer({"answer_instruction": "포빌 충전소를 조회했습니다."}, trace)

    assert "포빌 · 1건" in answer
    assert "중 하나" not in answer
    assert "전체" not in answer


def test_단위를_모르는_수치는_이름_옆에_안_붙인다():
    """무엇의 수인지 못 말하는 숫자는 딴 뜻으로 읽힘.

    실물 : ev.getDatasetInfo.기본.json 의 totalRegionCount 는 17 인데,
    이름 옆에 "17" 만 붙으면 충전소 수로 읽힘. 그 도구는 충전소가 93,353 이다.
    """
    trace = [{
        "id": "s1",
        "tool": "ev.getDatasetInfo",
        "input": {},
        "result": {
            "id": "kr-ev-chargers-keco-current",
            "name": "한국환경공단 전기자동차 충전소",
            "stationCount": 93353,
            "chargerCount": 492390,
            "readyRegionCount": 15,
            "totalRegionCount": 17,
        },
    }]
    answer = compose_workflow_answer({"answer_instruction": "충전소 데이터를 조회했습니다."}, trace)

    assert "ev.getDatasetInfo  한국환경공단 전기자동차 충전소" in answer
    assert "17" not in answer


def test_이름도_수치도_없으면_칸_이름_그대로():
    """모르는 모양은 여전히 칸 이름만. 실물 : rail.getSectionGeometry.nm-오송역.json.

    geometry 를 값으로 내면 화면이 raw JSON 이 됨.
    """
    trace = [{
        "id": "s1",
        "tool": "rail.getSectionGeometry",
        "input": {"sectionName": "오송역"},
        "result": {
            "sectionId": 1234,
            "geometry": {"type": "LineString", "coordinates": [[127.3, 36.6]]},
            "bbox": [[127.3, 36.6], [127.4, 36.7]],
        },
    }]
    answer = compose_workflow_answer({"answer_instruction": "오송역 구간을 조회했습니다."}, trace)

    assert "칸: sectionId · geometry · bbox" in answer
    assert "LineString" not in answer


# ── 무엇으로 불렀는가 ───────────────────────────────────────────────
#
# 화면에 건수만 나와 인자가 잘못 들어갔는지 · 데이터가 없는 것인지 · 도구가
# 터진 것인지를 사람이 못 갈랐다 (2026-08-25 화면 실측, NOTES.md 「스물셋째」의
# 「★ 미완성이다」). 아래 input 은 전부 그 실측에서 실제로 나간 값이다.


def test_무엇으로_불렀는지_단계_줄에_적힌다():
    """"전기차 충전소 데이터 검색해줘" 가 "ev.searchStations 120건" 만 냈음.

    무엇으로 검색해 120건인지가 화면에 없었음.
    """
    trace = [{
        "id": "s1",
        "tool": "ev.searchStations",
        "input": {"query": "전기차 충전소"},
        "result": {"count": 120, "totalMatches": 120},
    }]
    answer = compose_workflow_answer({"answer_instruction": "전기차 충전소를 조회했습니다."}, trace)

    assert 'query="전기차 충전소"' in answer
    assert "120건" in answer


def test_결과에_이미_나온_인자는_다시_안_적는다():
    """geo.geocode 는 "오송역 → 주소 (경도, 위도)" 로 인자를 이미 말함.

    앞에 query="오송역" 을 또 적으면 같은 값이 한 줄에 두 번 나감.
    """
    answer = compose_workflow_answer(
        {"answer_instruction": "오송역 좌표를 조회했습니다."}, [geocode_step(OSONG)]
    )

    assert 'query=' not in answer
    assert answer.count("오송역") == 2, "머리말 하나와 단계 줄 하나뿐이어야 함"


def test_인자가_비면_그_자리가_통째로_빠진다():
    """빈 dict 에 "input: {}" 를 찍으면 읽을 것이 없는 칸이 화면을 먹음."""
    trace = [{"id": "s1", "tool": "bim.listModels", "input": {}, "result": []}]
    answer = compose_workflow_answer({"answer_instruction": "모델을 조회했습니다."}, trace)

    assert answer.endswith("bim.listModels    0건")


def test_인자의_목록값은_안_적는다():
    """bbox 두 겹 · 좌표 배열이 인자 자리로 새면 결과 쪽을 막은 뜻이 없음.

    실측 : rail.getSectionGeometry 뒤에 오는 단계가 bbox 를 두 겹으로 받음.
    """
    trace = [{
        "id": "s1",
        "tool": "geo.getRailwayLines",
        "input": {"bbox": [[126.868587, 36.619576], [127.328115, 37.554557]], "limit": 50},
        "result": [],
    }]
    answer = compose_workflow_answer({"answer_instruction": "철도 노선을 조회했습니다."}, trace)

    assert "bbox" not in answer
    assert "126.868587" not in answer
    assert "limit=50" in answer


def test_실수_인자는_좌표_자리수로_자른다():
    """어댑터가 만든 bbox 는 소수점이 열대여섯 자리임. 그대로 적으면 줄이 넘침."""
    trace = [{
        "id": "s2",
        "tool": "road.getCctv",
        "input": {
            "minLon": 127.15983291624491,
            "minLat": 36.48522063242652,
            "maxLon": 127.49556031538508,
            "maxLat": 36.75467936757348,
        },
        "result": [],
    }]
    answer = compose_workflow_answer({"answer_instruction": "오송역 CCTV 를 조회했습니다."}, trace)

    assert "minLon=127.1598" in answer
    assert "127.15983291624491" not in answer


# ── 못 찾은 것을 못 찾았다고 말한다 ─────────────────────────────────
#
# 건수 칸이 아예 없는 응답은 0건 판정에 안 걸려 _notice 가 안 붙었다. 화면에
# "칸: status · message · dataset · query" 만 나왔다 (2026-08-25 화면 실측).


# tools/probe_out/election.getDistrict.name-발화.json 실물.
# dataset 의 나머지 칸은 같은 모양의 설명이라 뺐다.
NOT_FOUND = {
    "status": "not_found",
    "message": "조건에 맞는 선거구를 찾지 못했습니다.",
    "dataset": {
        "datasetId": "kr-assembly-districts-2024",
        "name": "2024 제22대 국회의원 선거구",
        "districtCount": 254,
        "bbox": [[124.61169218381582, 33.11579804189935],
                 [130.91785921273643, 38.61114065497731]],
    },
    "query": {"code": None, "name": "충북 제1선거구"},
}


def test_못_찾았다는_응답이_제_사유를_말한다():
    """message 에 사유가 있는데 칸 이름만 찍혔음."""
    trace = [{
        "id": "s1",
        "tool": "election.getDistrict",
        "input": {"name": "충북 제1선거구"},
        "result": NOT_FOUND,
    }]
    answer = compose_workflow_answer(
        {"answer_instruction": "충북 제1선거구 국회의원 지역구를 조회했습니다."}, trace
    )

    assert answer.startswith("찾지 못했습니다.")
    assert "충북 제1선거구 국회의원 지역구를 조회했습니다." not in answer
    assert "조건에 맞는 선거구를 찾지 못했습니다." in answer
    assert "칸: status" not in answer


def test_못_찾았을_때_무엇으로_물었는지도_남는다():
    """인자가 틀려서 못 찾은 것인지 데이터가 없는 것인지를 갈라야 함."""
    trace = [{
        "id": "s1",
        "tool": "election.getDistrict",
        "input": {"name": "충북 제1선거구"},
        "result": NOT_FOUND,
    }]
    answer = compose_workflow_answer({"answer_instruction": "지역구를 조회했습니다."}, trace)

    assert 'name="충북 제1선거구"' in answer


def test_못_찾았다는_응답도_큰_값은_안_샌다():
    """dataset 안에 bbox 와 설명이 통째로 들어 있음."""
    trace = [{
        "id": "s1",
        "tool": "election.getDistrict",
        "input": {"name": "충북 제1선거구"},
        "result": NOT_FOUND,
    }]
    answer = compose_workflow_answer({"answer_instruction": "지역구를 조회했습니다."}, trace)

    assert "kr-assembly-districts-2024" not in answer
    assert "124.61169218381582" not in answer


def test_데이터가_있는_status_는_못_찾았다고_안_한다():
    """status 넷 중 ready · syncing 은 데이터가 있는 상태임.

    실물 : ev.getDatasetInfo.기본.json 이 status "syncing" 인데 충전소가
    93,353건 들어 있음. 그것을 "찾지 못했습니다" 로 내면 거짓말이 됨.
    """
    trace = [{
        "id": "s1",
        "tool": "ev.getDatasetInfo",
        "input": {},
        "result": {
            "id": "kr-ev-chargers-keco-current",
            "name": "한국환경공단 전기자동차 충전소",
            "status": "syncing",
            "stationCount": 93353,
        },
    }]
    answer = compose_workflow_answer({"answer_instruction": "충전소 데이터를 조회했습니다."}, trace)

    assert answer.startswith("충전소 데이터를 조회했습니다.")
    assert "찾지 못했습니다" not in answer
    assert "한국환경공단 전기자동차 충전소" in answer


def test_적재된_것이_없으면_없다고_한다():
    """status "empty" 는 데이터가 하나도 안 들어온 것임. message 는 안 옴.

    실물 : ev.getDatasetInfo.json 이 stationCount 0 · totalRegionCount 17 임.
    """
    trace = [{
        "id": "s1",
        "tool": "ev.getDatasetInfo",
        "input": {},
        "result": {
            "id": "kr-ev-chargers-keco-current",
            "name": "한국환경공단 전기자동차 충전소",
            "status": "empty",
            "stationCount": 0,
            "totalRegionCount": 17,
        },
    }]
    answer = compose_workflow_answer({"answer_instruction": "충전소 데이터를 조회했습니다."}, trace)

    assert answer.startswith("찾지 못했습니다.")
    assert "데이터가 없습니다" in answer


# ── 목록형 응답의 내용 ──────────────────────────────────────────────
#
# knowledge.query 가 본문을 돌려주는데 화면에는 "4건" 만 나왔다. 시연
# 요구사항인 "문서에서 내용을 찾아온다" 가 도구 쪽은 되고 화면 쪽만 안 됐다.


# tools/probe_out/knowledge.query.철도안전-2026-08-25.json 실물.
# 네 건 중 첫 건만 남기고 content 는 앞 120자까지만 남겼다 (원문은 964자).
# metadata 는 열여섯 칸 중 화면이 읽는 둘과 그 옆 몇을 남겼다.
KNOWLEDGE = [{
    "content": (
        "법제처                                                            1"
        "                                                       국가법령정보센터\n"
        "철도안전법\n철도안전법\n[시행 2026. 3. 3.] [법률 제21188호, 2025. 3. 4., 일부개정]"
    ),
    "metadata": {
        "producer": "iText 2.1.7 by 1T3XT",
        "title": "",
        "file_path": "/tmp/철도안전법(법률)(제21188호)(20260303).pdf",
        "page": "0",
        "total_pages": "47",
        "source": "철도안전법(법률)(제21188호)(20260303).pdf",
    },
}]


def knowledge_step(result=KNOWLEDGE):
    return {"id": "s1", "tool": "knowledge.query", "input": {"query": "철도 안전"}, "result": result}


def test_문서_이름과_본문이_답에_실린다():
    """본문이 오는데 세기만 했음. "4건" 은 문서 수도 아니고 k 의 기본값임."""
    answer = compose_workflow_answer(
        {"answer_instruction": "철도 안전 문서를 조회했습니다."}, [knowledge_step()]
    )

    assert "「철도안전법(법률)(제21188호)(20260303).pdf」" in answer
    assert "국가법령정보센터" in answer
    assert "1건" in answer


def test_본문은_잘라서_싣고_잘랐다고_밝힌다():
    """content 가 962~995자임. 통째로 실으면 화면이 응답 전문이 됨."""
    answer = compose_workflow_answer(
        {"answer_instruction": "철도 안전 문서를 조회했습니다."}, [knowledge_step()]
    )

    assert "…" in answer
    assert "일부개정" not in answer, "본문 끝까지 실리면 안 됨"


def test_본문의_잇단_공백은_한_칸으로_붙인다():
    """PDF 본문이 공백 수십 칸을 달고 옴. 그대로 실으면 한 줄이 텅 빔."""
    answer = compose_workflow_answer(
        {"answer_instruction": "철도 안전 문서를 조회했습니다."}, [knowledge_step()]
    )

    assert "  " not in answer.split("knowledge.query")[1].split("「")[1]


def test_경로는_안_보여준다():
    """metadata.file_path 는 저쪽 컨테이너의 /tmp 경로임. 사람이 볼 것이 아님."""
    answer = compose_workflow_answer(
        {"answer_instruction": "철도 안전 문서를 조회했습니다."}, [knowledge_step()]
    )

    assert "/tmp" not in answer
    assert "1T3XT" not in answer


def test_첫_목록이_비면_다음_목록을_본다():
    """한 응답이 목록을 둘 담아 오고 첫째가 비어 있음.

    실물 : adminBoundary.findBoundaryByPoint 가 features 0건 · items 3건.
    features 에서 멈추면 이름이 있는 items 를 못 봄.
    """
    trace = [{
        "id": "s2",
        "tool": "adminBoundary.findBoundaryByPoint",
        "input": {"lon": 127.3277, "lat": 36.62},
        "result": {
            "type": "FeatureCollection",
            "features": [],
            "items": [
                {"id": "43", "name": "충청북도", "code": "43", "layerId": "sido",
                 "bbox": [127.275651, 36.01243, 128.652096, 37.258334]},
                {"id": "43113", "name": "청주시 흥덕구", "code": "43113", "layerId": "sigungu"},
            ],
            "count": 2,
            "totalMatches": 2,
        },
    }]
    answer = compose_workflow_answer({"answer_instruction": "오송역 행정구역을 조회했습니다."}, trace)

    assert "2건 · 충청북도" in answer
    assert "청주시 흥덕구" not in answer, "첫 항목 하나만 봄"
    assert "127.275651" not in answer


def test_첫_항목이_좌표_덩어리면_건수만_낸다():
    """geojson feature 는 {geometry, properties, type} 이라 읽을 칸이 없음.

    properties 안에 name 이 있지만 안 파고듦. 그 안에는 좌표와 목록이 함께 있음.
    """
    trace = [{
        "id": "s1",
        "tool": "election.findAssemblyDistrictByPoint",
        "input": {"lon": 127.3277, "lat": 36.62},
        "result": {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "MultiPolygon",
                             "coordinates": [[[[127.27565045721593, 36.56168453000288]]]]},
                "properties": {"name": "청주시 흥덕구", "est_color": "#D8E4BC",
                               "winner_names": ["이연희"]},
            }],
            "count": 1,
        },
    }]
    answer = compose_workflow_answer({"answer_instruction": "오송역 지역구를 조회했습니다."}, trace)

    assert "election.findAssemblyDistrictByPoint  lon=127.3277 · lat=36.6200  1건" in answer
    assert "MultiPolygon" not in answer
    assert "127.27565045721593" not in answer
    assert "#D8E4BC" not in answer


def test_cctv_주소는_첫_항목이어도_안_샌다():
    """cctvUrl 이 화면에 raw 로 새던 값 중 하나임. 88자짜리 서명 붙은 주소임.

    실물 : tools/probe_out/road.getCctv.cctv-오송역.json 의 첫 항목.
    """
    trace = [{
        "id": "s2",
        "tool": "road.getCctv",
        "input": {"minLon": 127.1598, "minLat": 36.4852},
        "result": [{
            "cctvId": "its_[수도권제1순환선] 판교분기점",
            "cctvName": "[수도권제1순환선] 판교분기점",
            "centerLon": 127.09706,
            "centerLat": 37.40665,
            "cctvUrl": ("http://cctvsec.ktict.co.kr/1/ablsJ6ueB0MmE96fJiebiicMsYWjFmEqTpAmr"
                        "cTpNszF6iT0v3zXs9gjInwfiK54qeyHEF+LDDjdjRDOXeKA5A=="),
            "cctvFormat": "HLS",
        }],
    }]
    answer = compose_workflow_answer({"answer_instruction": "오송역 CCTV 를 조회했습니다."}, trace)

    assert "1건" in answer
    assert "http" not in answer
    assert "ablsJ6ueB0MmE96" not in answer


# ── 글 목록은 조각 두셋을 보여준다 ──────────────────────────────────
#
# 조각 하나로는 "문서에서 내용을 찾아온다" 가 안 보인다. 항목이 글(TEXT_KEYS)인
# 목록만 앞 두셋을 아래 줄로 늘어놓고, 글이 아닌 목록은 예전대로 첫 항목이다.
# 도구 이름이 아니라 결과 모양으로 가른다 — 이 파일은 도구 이름을 모른다.


# tools/probe_out/knowledge.query.2026-08-26.철도_안전_교육.k6.json 실물.
# 여섯 건 중 앞 넷만 남기고 content 는 앞 토막만, metadata 는 화면이 읽는
# 칸과 그 옆 몇만 남겼다. page 는 실물 그대로 0부터 세는 정수다.
KNOWLEDGE_CHUNKS = [
    {
        "content": "법제처                                        12    국가법령정보센터\n철도안전법\n제24조",
        "metadata": {"source": "철도안전법(법률)(제21188호)(20260303).pdf",
                     "page": 11, "title": "", "total_pages": 47},
    },
    {
        "content": "효기간 만료일”이라 한다) 전 12개월 이내에 실시한다. 이 경우 정기검사의 유효기간은",
        "metadata": {"source": "철도안전법 시행규칙(국토교통부령)(제01571호)(20260324).pdf",
                     "page": 16, "title": "", "total_pages": 52},
    },
    {
        "content": "법제처                                        33    국가법령정보센터\n철도안전법\n제41조",
        "metadata": {"source": "철도안전법(법률)(제21188호)(20260303).pdf",
                     "page": 32, "title": "", "total_pages": 47},
    },
    {
        "content": "넷째조각표시글 안전관리체계의 승인을 받은 철도운영자등은",
        "metadata": {"source": "철도안전법(법률)(제21188호)(20260303).pdf",
                     "page": 33, "title": "", "total_pages": 47},
    },
]


def knowledge_chunks_step(result=KNOWLEDGE_CHUNKS):
    return {"id": "s1", "tool": "knowledge.query",
            "input": {"query": "철도 안전 교육"}, "result": result}


def test_글_목록은_조각_두셋이_각각_문서_이름과_쪽으로_나온다():
    """첫 조각만 보이면 나머지를 찾아온 것이 화면에 없음.

    실측 (2026-08-26) : "철도 안전 교육" k=6 이 법 4 · 시행규칙 2 조각을
    돌려주는데 화면에는 첫 조각 하나만 나왔음.
    """
    answer = compose_workflow_answer(
        {"answer_instruction": "철도 안전 교육 문서를 조회했습니다."},
        [knowledge_chunks_step()],
    )

    assert "4건" in answer
    assert answer.count("「철도안전법(법률)(제21188호)(20260303).pdf」") == 2
    assert "「철도안전법 시행규칙(국토교통부령)(제01571호)(20260324).pdf」" in answer
    assert "제24조" in answer and "유효기간" in answer and "제41조" in answer


def test_넷째_조각부터는_안_실린다():
    """전부 늘어놓으면 화면이 응답 전문이 됨. 두셋에서 멈춰야 함."""
    answer = compose_workflow_answer(
        {"answer_instruction": "철도 안전 교육 문서를 조회했습니다."},
        [knowledge_chunks_step()],
    )

    assert "넷째조각표시글" not in answer


def test_쪽수는_사람이_세는_수로_낸다():
    """응답의 page 는 0부터 셈. 그대로 내면 문서에 찍힌 쪽과 하나 어긋남.

    실측 : page 11 조각의 본문 머리가 "12", page 50 조각이 "51"
    (2026-08-26, tools/probe_out 의 knowledge.query 응답 전문).
    """
    answer = compose_workflow_answer(
        {"answer_instruction": "철도 안전 교육 문서를 조회했습니다."},
        [knowledge_chunks_step()],
    )

    assert "12쪽" in answer
    assert "17쪽" in answer
    assert "11쪽" not in answer


def test_쪽을_못_읽으면_출처만_남는다():
    """page 가 없거나 수가 아닌 응답도 조용히 돌아야 함. 지어내지 않음."""
    chunk = {
        "content": "안전관리체계의 승인을 받은 철도운영자등은",
        "metadata": {"source": "철도안전법(법률)(제21188호)(20260303).pdf", "title": ""},
    }
    answer = compose_workflow_answer(
        {"answer_instruction": "철도 안전 문서를 조회했습니다."},
        [knowledge_chunks_step([chunk])],
    )

    assert "「철도안전법(법률)(제21188호)(20260303).pdf」" in answer
    assert "쪽" not in answer


def test_글이_아닌_목록은_예전대로_첫_항목만이다():
    """이름 목록에 두셋 규칙이 걸리면 다른 도구의 답이 세 줄로 늘어남.

    글 목록 판정은 첫 항목의 TEXT_KEYS 임. 이름만 있는 항목은 안 걸림.
    """
    trace = [{
        "id": "s1",
        "tool": "adminBoundary.searchBoundaries",
        "input": {"query": "청주"},
        "result": [{"name": "청주시 상당구"}, {"name": "청주시 서원구"},
                   {"name": "청주시 흥덕구"}],
    }]
    answer = compose_workflow_answer({"answer_instruction": "청주 행정구역을 조회했습니다."}, trace)

    assert "3건 · 청주시 상당구" in answer
    assert "청주시 서원구" not in answer, "첫 항목 하나만 봄"


def test_낱자로_풀린_문서_이름은_붙여서_전부_보인다():
    """실물 source 는 한글이 낱자(NFD)로 풀려 옴. 낱자로 세면 눈에 41자인
    이름이 len 67 이라 48 한도에서 어중간하게 잘림 (2026-08-26 화면 실측 —
    "「철도안전법 시행규칙(국토교통부령)(제015…」" 로 나왔음).
    """
    import unicodedata

    name = unicodedata.normalize(
        "NFD", "철도안전법 시행규칙(국토교통부령)(제01571호)(20260324).pdf"
    )
    chunk = {
        "content": "효기간 만료일”이라 한다) 전 12개월 이내에 실시한다.",
        "metadata": {"source": name, "page": 16, "title": ""},
    }
    answer = compose_workflow_answer(
        {"answer_instruction": "철도 안전 교육 문서를 조회했습니다."},
        [knowledge_chunks_step([chunk])],
    )

    assert "「철도안전법 시행규칙(국토교통부령)(제01571호)(20260324).pdf」" in answer


def test_조각_여럿이어도_긴_토막은_안_샌다():
    """조각마다 본문 · 출처가 실리므로 자르는 상한이 조각 수만큼 돌아야 함."""
    answer = compose_workflow_answer(
        {"answer_instruction": "철도 안전 교육 문서를 조회했습니다."},
        [knowledge_chunks_step()],
    )

    longest = max(answer.split(), key=len)
    assert len(longest) <= 60, f"{longest} 가 통째로 나갔음"


def test_어떤_결과도_긴_토막을_화면에_안_흘린다():
    """자르는 상한을 하나라도 빠뜨리면 여기서 걸림.

    위 시험들은 아는 값 하나씩을 짚는다. 이것은 모르는 값을 막는다 —
    답에 든 낱말이 길면 그것은 사람이 읽을 것이 아니라 새어 나온 값이다.
    """
    for result in (KNOWLEDGE, NOT_FOUND, AGE_PROFILE):
        answer = compose_workflow_answer(
            {"answer_instruction": "조회했습니다."},
            [{"id": "s1", "tool": "t", "input": {"query": "철도 안전"}, "result": result}],
        )
        longest = max(answer.split(), key=len)
        assert len(longest) <= 60, f"{longest} 가 통째로 나갔음"


# ── 0건일 때 무엇으로 찾았고 어떻게 말하면 되는지 (2026-08-30) ──────
#
# Gateway 직접 호출 실물이다 (user_context 는 execute_service.USER_CONTEXT).
# 셋 다 화면에서 0건 · not_found 가 나던 자리다.

# election.searchDistricts {"query": "국회의원 선거구"} 0건.
SEARCH_DISTRICTS_EMPTY = {
    "type": "FeatureCollection",
    "features": [],
    "items": [],
    "count": 0,
    "totalMatches": 0,
    "limit": 20,
    "dataset": {
        "datasetId": "kr-assembly-districts-2024",
        "name": "2024 제22대 국회의원 선거구",
        "electionDate": "2024-04-10",
        "districtCount": 254,
        "crs": "EPSG:4326",
        "format": "GeoJSON FeatureCollection",
        "source": "https://github.com/OhmyNews/2024_22_elec_map",
        "properties": ["SGG_Code", "SIDO_SGG", "SIDO", "SGG"],
        "bbox": [[124.61169218381582, 33.11579804189935],
                 [130.91785921273643, 38.61114065497731]],
    },
    "query": {"text": "국회의원 선거구", "sido": None, "code": None, "all": False},
}

# adminBoundary.searchBoundaries {"query": "행정경계"} 0건.
# dataset 에 name 이 없고 source 만 있다.
SEARCH_BOUNDARIES_EMPTY = {
    "type": "FeatureCollection",
    "features": [],
    "count": 0,
    "totalMatches": 0,
    "limit": 20,
    "bbox": None,
    "items": [],
    "dataset": {
        "source": "2026 지방선거 공약 GIS 프로젝트 행정구역 shapefile",
        "datasetVersion": "2026",
        "crs": "EPSG:4326",
        "format": "PostGIS",
        "featureCount": 252,
    },
    "query": {"layer": "sigungu", "query": "행정경계", "limit": 20},
}


def test_0건이면_어디를_뒤졌고_어떻게_말하면_되는지가_함께_나온다():
    """"찾지 못했습니다." 한 줄로는 다음에 무엇을 할지 알 수 없음.

    실측 : 화면에 "찾지 못했습니다." 와 단계 줄 하나만 나왔고 사용자가
    발화를 어떻게 고쳐야 하는지가 없었음 (2026-08-30).
    """
    trace = [{
        "id": "s1",
        "tool": "election.searchDistricts",
        "input": {"query": "국회의원 선거구"},
        "result": SEARCH_DISTRICTS_EMPTY,
    }]
    answer = compose_workflow_answer(
        {"answer_instruction": "국회의원 선거구 국회의원 지역구 목록을 조회했습니다."}, trace
    )

    assert answer.startswith("찾지 못했습니다.")
    assert "「2024 제22대 국회의원 선거구」" in answer
    assert "다른 낱말로 다시 말씀해 주세요." in answer


def test_어디를_뒤졌는지는_응답이_들고_온_이름으로만_적는다():
    """이름을 코드에 안 적음. 응답의 dataset.name 하나만 봄.

    source 는 데이터의 출처지 사람이 읽을 이름이 아님 — 그 칸만 있는
    응답은 어디를 뒤졌는지 줄이 통째로 빠짐.
    """
    trace = [{
        "id": "s1",
        "tool": "adminBoundary.searchBoundaries",
        "input": {"query": "행정경계"},
        "result": SEARCH_BOUNDARIES_EMPTY,
    }]
    answer = compose_workflow_answer(
        {"answer_instruction": "행정경계 행정구역 경계를 조회했습니다."}, trace
    )

    assert answer.startswith("찾지 못했습니다.")
    assert "찾아본 곳은" not in answer
    assert "shapefile" not in answer
    assert "다른 낱말로 다시 말씀해 주세요." in answer


def test_not_found_는_0건과_다르게_말한다():
    """뜻이 다름. 0건은 낱말이 안 겹친 것이고 not_found 는 그 이름이 없는 것임.

    낱말을 바꿔 보라고 하면 안 됨 — 이름을 지정해 집어 오는 호출이라
    데이터에 있는 이름을 그대로 대야 함.
    """
    trace = [{
        "id": "s1",
        "tool": "election.getDistrict",
        "input": {"name": "충북 제1선거구"},
        "result": NOT_FOUND,
    }]
    answer = compose_workflow_answer({"answer_instruction": "지역구를 조회했습니다."}, trace)

    assert "데이터에 있는 이름을 그대로 말씀해 주세요." in answer
    assert "다른 낱말로 다시 말씀해 주세요." not in answer


def test_적재된_것이_없으면_다시_말하라고_안_한다():
    """status "empty" 는 데이터가 안 들어온 것임. 사람이 다시 말해서 될 일이 아님."""
    trace = [{
        "id": "s1",
        "tool": "ev.getDatasetInfo",
        "input": {"query": "충전소"},
        "result": {
            "id": "kr-ev-chargers-keco-current",
            "name": "한국환경공단 전기자동차 충전소",
            "status": "empty",
            "stationCount": 0,
            "dataset": {"name": "한국환경공단 전기자동차 충전소"},
        },
    }]
    answer = compose_workflow_answer({"answer_instruction": "충전소 데이터를 조회했습니다."}, trace)

    assert "말씀해 주세요" not in answer


def test_좌표로만_부른_0건에는_다시_말하라고_안_한다():
    """그 단계에 사람이 고쳐 말할 낱말이 없음. 지점을 찍어 부른 호출임."""
    trace = [
        geocode_step(OSONG),
        {
            "id": "s2",
            "tool": "election.findDistrictByPoint",
            "input": {"lon": 127.3276, "lat": 36.6199},
            "result": {
                "features": [],
                "count": 0,
                "dataset": {"name": "2024 제22대 국회의원 선거구"},
            },
        },
    ]
    answer = compose_workflow_answer({"answer_instruction": "선거구를 조회했습니다."}, trace)

    assert "「2024 제22대 국회의원 선거구」" in answer
    assert "말씀해 주세요" not in answer


def test_넓어진_머리말도_raw_JSON_을_안_흘린다():
    """dataset 안에 bbox 두 겹과 datasetId 가 통째로 들어 있음."""
    for result in (SEARCH_DISTRICTS_EMPTY, SEARCH_BOUNDARIES_EMPTY, NOT_FOUND):
        answer = compose_workflow_answer(
            {"answer_instruction": "조회했습니다."},
            [{"id": "s1", "tool": "t", "input": {"query": "선거구"}, "result": result}],
        )
        assert "kr-assembly-districts-2024" not in answer
        assert "124.61169218381582" not in answer
        assert "EPSG:4326" not in answer
        longest = max(answer.split(), key=len)
        assert len(longest) <= 60, f"{longest} 가 통째로 나갔음"


def test_0건이_아닌_답은_머리말이_한_줄_그대로다():
    """넓힌 것은 0건 자리뿐임. 성공 · 오류 문구가 한 글자도 안 달라져야 함."""
    success = compose_workflow_answer(
        {"answer_instruction": "오송역 좌표를 조회했습니다."}, [geocode_step(OSONG)]
    )
    assert success.splitlines()[0] == "오송역 좌표를 조회했습니다."
    assert "말씀해 주세요" not in success
    assert "찾아본 곳은" not in success

    failure = compose_workflow_answer(
        {"answer_instruction": "오송역 좌표를 조회했습니다."},
        [{"id": "s1", "tool": "geo.geocode", "input": {"query": "지금 보이는 곳"},
          "error": "s1 단계 장소 '지금 보이는 곳'을(를) 찾을 수 없습니다."}],
    )
    assert failure.splitlines()[0] == "조회하지 못했습니다."
    assert "말씀해 주세요" not in failure
    assert "찾아본 곳은" not in failure
