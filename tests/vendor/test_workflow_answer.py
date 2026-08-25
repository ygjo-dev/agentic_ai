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
