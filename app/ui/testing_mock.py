"""테스트 탭 화면 시안용 가짜 결과 200건.

**정답표가 아니다.** 실제 평가 결과도 아니다. 테스트 탭이 어떻게 보이고 어떻게
조작되는지를 먼저 확정하려고 만든 화면 데이터다. 발화 · 정답 · 모델 출력이 모두
지어낸 것이고, 기능 설명도 화면에 긴 글이 어떻게 들어가는지 보려고 menu 를 줄여
옮긴 것이다 — menu 를 읽지 않는다.

**난수를 안 쓴다.** 고정 목록과 고정 순번으로만 만든다. 화면을 다시 띄워도 같은
발화 · 같은 성공/실패 수 · 같은 상세가 나와야 시안을 두고 이야기할 수 있다.

    전체 200 = 성공 187 + 기능 선택 실패 5 + 인자 추출 실패 8

성공 187 중 몇 건은 「값은 다른데 채점에 안 쓰는 인자」를 일부러 담았다.
값 차이가 곧 실패처럼 보이지 않는지 화면에서 확인하려는 것이다.

결과 한 건의 모양은 화면이 그리는 데 쓰는 내부 view model 이다. 평가 계약으로
정한 것이 아니다 — 나중에 실제 평가기가 붙으면 그 결과를 이 모양으로 옮겨
mock_test_results() 자리만 바꾼다.

    {
        "id": 7,
        "utterance": "...",
        "passed": False,
        "failure_stage": "input",          # None | "function" | "input"
        "answer": {
            "function_id": "recipe_010",
            "function_label": "기능 010",
            "function_description": "...",
            "inputs": {...},
        },
        "model_output": {
            "function_id": "recipe_010",     # 모델이 고르지 않았으면 None
            "function_label": "기능 010",
            "function_description": "...",
            "inputs": {...},
            "reason": "...",
            "candidate_ids": [...],
            "status": "SELECT",
        },
        "graded_fields": [...],            # 성공/실패를 가르는 데 쓰는 인자
    }
"""

TEST_SET_LABEL = "화면 시안 · 200개 발화"

# 지금 인자 넷. 채점에 쓰는 기본 목록이기도 하다.
V1_FIELDS = ("argument", "travel_mode", "minutes", "admin_level")

# 기능 번호 -> 화면에 보일 설명. 시안용으로 줄여 옮긴 것이다.
FUNCTIONS = {
    "recipe_001": "장소 이름을 말하면 그곳이 지도 어디인지 위경도 좌표로 짚어 준다. 좌표까지만 주고 끝낸다.",
    "recipe_002": "철도 구간 이름을 말하면 그 구간 선로가 어떻게 놓였는지 선형 좌표만 준다.",
    "recipe_003": "역 이름이나 노선 이름을 말하면 그 이름으로 철도 노선과 역을 조회해 알려준다.",
    "recipe_005": "행정구역 이름이나 코드를 그대로 대면 그 이름으로 행정경계를 조회해 준다.",
    "recipe_008": "지역 이름이나 시도 약칭을 대면 거기 제22대 국회의원 선거구 목록을 뽑는다.",
    "recipe_010": "지역·당선인·정당을 대면 제22대 국회의원이 내건 공약 자체를 검색해 보여준다.",
    "recipe_012": "지역 단위나 이름을 대면 지역별 인구 수와 순위를 집계해 낸다.",
    "recipe_014": "문서 이름이나 그 안에 나올 말을 대면 지식베이스 문서 본문에서 찾아 준다.",
    "recipe_015": "선거구 이름이나 선거구 코드를 집어 말하면 그 선거구 한 곳의 정보를 조회한다. 당선인·정당·공약은 주지 않는다.",
    "recipe_016": "행정구역 이름이나 선거구 코드를 집어 말하면 그 선거구 한 곳을 당선인·정당·공약까지 붙여 조회한다.",
    "recipe_019": "장소 이름 없이 「이 위치」라고 가리키면 그 자리 둘레에 있는 CCTV 를 보여준다.",
    "recipe_021": (
        "발화에 장소 이름이 없고 「여기」·「이 위치」·「선택한 위치」라고 가리키면 그 자리 "
        "제22대 국회의원 선거구의 당선인이 누구고 어느 정당인지 알려준다. 공약은 몇 건인지 "
        "세기만 하고 공약 내용은 주지 않는다."
    ),
    "recipe_022": "장소 이름 없이 「이 위치」라고 가리키면 그 자리 선거구가 내건 공약을 분야로 걸러 보여준다.",
    "recipe_024": "「현재 화면」이라고 하면 그 화면에 걸친 행정구역 경계를 이름·코드로 조회해 준다.",
    "recipe_026": "「현재 화면」이라고 하면 그 화면 안에 있는 CCTV 를 보여준다.",
    "recipe_029": "「현재 화면」이라고 하면 그 화면에 걸친 국회의원 공약을 당선인·정당·분야로 검색한다.",
    "recipe_031": "「현재 화면」이라고 하면 그 화면 안에 사람이 몇 명이나 사는지 인구 수와 순위를 낸다.",
    "recipe_033": "역·시설처럼 행정구역이 아닌 곳을 말하면 그 좌표를 찾고 둘레의 행정구역 경계를 조회한다.",
    "recipe_034": "장소 이름을 말하면 그곳이 어느 시·군·구·동인지와 행정구역 코드를 알려준다.",
    "recipe_036": "장소 이름을 말하면 그 자리 둘레에 있는 CCTV 를 보여준다.",
    "recipe_038": "장소 이름을 말하면 그곳이 무슨 국회의원 선거구에 드는지 선거구 이름만 알려준다.",
    "recipe_040": "장소 이름을 말하면 그곳 선거구의 당선인이 누구고 어느 정당인지 알려준다.",
    "recipe_045": "장소 이름을 말하면 그 둘레에 사람이 몇 명이나 사는지 인구 수와 순위를 낸다.",
    "recipe_049": "철도 노선이나 구간 이름을 말하면 그 선로를 따라가며 CCTV 를 보여준다.",
    "recipe_052": "전기차 충전소를 이름·주소·운영기관으로 검색해 충전기가 몇 대 비어 있는지까지 알려준다.",
    "recipe_054": "장소 이름 없이 「이 위치」라고 가리키면 그 자리 행정구역의 연령대별 남녀 인구 구성을 알려준다.",
    "recipe_055": "장소 이름 없이 「이 위치」라고 가리키면 그 자리 행정구역에서 달마다 인구가 얼마나 늘고 줄었는지 알려준다.",
    "recipe_059": "장소 이름을 말하면 그곳 행정구역에서 달마다 인구가 얼마나 늘고 줄었는지 알려준다.",
    "recipe_060": "장소 이름과 그 둘레를 함께 말하면 둘레의 전기차 충전소를 찾아 빈 충전기 수까지 알려준다.",
    "recipe_061": (
        "출발할 장소 이름을 말하면 그곳에서 걸어서나 자전거·차·대중교통으로 말한 시간 안에 "
        "닿는 범위를 계산해 지도에 그려 준다."
    ),
    "recipe_062": "찍어 둔 자리에서 이름을 말한 곳까지 대중교통으로 어떻게 가는지, 갈아타는 곳과 걸리는 시간을 알려준다.",
    "recipe_063": "「여기서」라고 가리키면 그 자리에서 말한 이동 방식과 시간 안에 닿는 범위를 지도에 그려 준다.",
}

# ------------------------------------------------------------------ 성공 발화의 틀
# 틀마다 순번 n 을 받아 값과 말투를 고른다. 틀과 값을 순번으로 돌려 성공 187건을 만든다.
PLACES = ["오송역", "대전역", "익산역", "부산역", "천안아산역", "서대전역", "청주공항", "수원역", "광주송정역", "강릉역"]
LINES = ["경부선", "호남선", "중앙선", "전라선", "충북선", "장항선", "경전선", "동해선"]
REGIONS = ["청주", "대전", "세종", "논산시", "충청북도", "전주시", "공주시", "아산시"]
TOPICS = ["철도", "대중교통", "교통안전", "도시재생", "주차", "보육", "청년 주거", "관광"]
DOCS = ["철도안전법", "산업안전보건법", "도시철도법", "건설기술 진흥법", "철도산업발전기본법", "교통안전법", "철도사업법", "궤도운송법"]
DISTRICTS = ["대전 서구갑", "청주서원", "천안을", "세종갑", "전주병", "공주부여청양", "아산을", "논산계룡금산"]
MODES = [("도보", "걸어서", [10]), ("자전거", "자전거로", [15]), ("승용차", "차로", [20, 30]), ("대중교통", "대중교통으로", [30])]
LEVELS = ["시군구", "읍면동", "시도"]


def _inputs(argument=None, travel_mode=None, minutes=None, admin_level=None) -> dict:
    """인자 넷. 적지 않은 칸은 None."""
    return {
        "argument": argument,
        "travel_mode": travel_mode,
        "minutes": minutes,
        "admin_level": admin_level,
    }


def _plain(fid, utterance, candidates, reason, **inputs):
    """틀 한 건. 성공 발화라 정답표와 모델 출력이 같음."""
    return {"fid": fid, "utterance": utterance, "inputs": _inputs(**inputs), "candidates": candidates, "reason": reason}


def _pick(options, n):
    """순번 n 으로 고른 하나. 값 목록을 한 바퀴 돌 때마다 말투를 바꾸는 데 씀."""
    return options[n % len(options)]


def _pass_templates():
    """성공 발화 틀 목록. 각 틀은 순번 n 을 받아 한 건을 냄."""
    place = lambda n: PLACES[n % len(PLACES)]  # noqa: E731
    line = lambda n: LINES[n % len(LINES)]  # noqa: E731
    level = lambda n: LEVELS[n % 3]  # noqa: E731
    mode = lambda n: MODES[n % 4]  # noqa: E731
    return [
        lambda n: _plain("recipe_001", f"{place(n)} 위치 보여줘", ["recipe_001", "recipe_034"],
                         f"「{place(n)}」의 좌표만 묻는 발화라 위치를 짚는 기능을 고른다.", argument=place(n)),
        lambda n: _plain("recipe_002", f"{line(n)} 선로 선형 좌표 줘", ["recipe_002"],
                         f"「{line(n)}」 구간의 선형만 묻는다. 노선 목록은 원하지 않는다.", argument=line(n)),
        lambda n: _plain("recipe_003", f"{place(n)}에 어떤 철도 노선이 들어와", ["recipe_003"],
                         f"「{place(n)}」에 들어오는 노선을 묻는다.", argument=place(n)),
        lambda n: _plain("recipe_005", f"{REGIONS[n % len(REGIONS)]} 행정경계 보여줘", ["recipe_005", "recipe_033"],
                         "행정구역 이름 자체를 말했으므로 경계를 바로 조회한다.",
                         argument=REGIONS[n % len(REGIONS)], admin_level="시군구"),
        lambda n: _plain("recipe_008", f"{REGIONS[n % len(REGIONS)]} 지역구 목록 뽑아줘", ["recipe_008"],
                         "지역 이름으로 선거구 목록을 원한다.", argument=REGIONS[n % len(REGIONS)]),
        lambda n: _plain("recipe_010", f"{TOPICS[n % len(TOPICS)]} 공약 내놓은 의원 모아줘", ["recipe_010"],
                         f"「{TOPICS[n % len(TOPICS)]}」 분야 공약 자체를 찾는 발화다.", argument=TOPICS[n % len(TOPICS)]),
        lambda n: _plain("recipe_012", _pick([f"{level(n)}별 인구 순위 매겨줘", f"{level(n)} 단위로 인구 많은 순서 보여줘",
                                        f"인구 제일 많은 {level(n)} 어디야"], n // 3),
                         ["recipe_012", "recipe_031"], "장소 없이 지역 단위별 인구 순위를 묻는다.", admin_level=level(n)),
        lambda n: _plain("recipe_014", f"{DOCS[n % len(DOCS)]} 조문 원문 보여줘", ["recipe_014"],
                         "문서 이름을 대고 본문을 원한다.", argument=DOCS[n % len(DOCS)]),
        lambda n: _plain("recipe_015", f"{DISTRICTS[n % len(DISTRICTS)]} 선거구 정보 줘", ["recipe_015", "recipe_016"],
                         "선거구 이름을 집어 말했고 당선인·공약은 묻지 않았다.", argument=DISTRICTS[n % len(DISTRICTS)]),
        lambda n: _plain("recipe_019", _pick(["이 위치 둘레 CCTV 보여줘", "여기 주변 CCTV 띄워줘", "선택한 위치 근처 CCTV",
                                        "찍은 곳 둘레 CCTV 영상 볼래", "이 지점 CCTV 어디 있어", "여기 근처 교통 CCTV 켜줘",
                                        "선택한 지점 둘레 CCTV 목록", "이 위치에서 가까운 CCTV 보여줘"], n),
                         ["recipe_019"], "장소 이름 없이 찍은 자리를 가리킨다."),
        lambda n: _plain("recipe_022", f"이 위치 선거구가 내건 {TOPICS[n % len(TOPICS)]} 공약 보여줘", ["recipe_022"],
                         "찍은 자리의 선거구 공약을 분야로 거른다.", argument=TOPICS[n % len(TOPICS)]),
        lambda n: _plain("recipe_024", _pick([f"지금 화면에 든 {level(n)} 경계선 표시해줘", f"현재 화면 {level(n)} 경계 보여줘",
                                        f"보이는 곳 {level(n)} 경계 그려줘"], n // 3),
                         ["recipe_024"], "보이는 범위의 행정경계를 원한다.", admin_level=level(n)),
        lambda n: _plain("recipe_026", _pick(["현재 화면에 걸린 CCTV 전부 띄워줘", "지금 보이는 곳 CCTV 보여줘", "화면 안 CCTV 다 켜줘",
                                        "지금 화면에 CCTV 몇 대 있어", "현재 화면 범위 CCTV 목록", "보이는 지도 안 CCTV 띄워줘",
                                        "이 화면 CCTV 위치 찍어줘", "현재 보이는 곳 교통 CCTV"], n),
                         ["recipe_026", "recipe_019"], "「현재 화면」 범위의 CCTV 를 묻는다."),
        lambda n: _plain("recipe_031", _pick(["지금 화면 안에 사람 몇 명 살아", "현재 화면 인구 순위 보여줘", "보이는 곳 인구 합계 알려줘",
                                        "지금 화면 동네별 인구 비교해줘", "현재 화면 안 인구 제일 많은 곳", "화면에 보이는 지역 인구 줘",
                                        "지금 보이는 범위 인구 순위", "이 화면 안 인구 얼마나 돼"], n),
                         ["recipe_031", "recipe_012"], "보이는 범위의 인구를 묻는다.", admin_level="시군구"),
        lambda n: _plain("recipe_034", f"{place(n)}이 어느 동에 속하는지 알려줘", ["recipe_034", "recipe_001"],
                         f"「{place(n)}」의 소속 행정구역을 묻는다.", argument=place(n), admin_level="읍면동"),
        lambda n: _plain("recipe_036", f"{place(n)} 둘레 CCTV 보여줘", ["recipe_036"],
                         f"「{place(n)}」 둘레 CCTV 를 원한다.", argument=place(n)),
        lambda n: _plain("recipe_038", f"{place(n)}은 무슨 선거구에 들어가", ["recipe_038", "recipe_040"],
                         "선거구 이름만 묻는다.", argument=place(n)),
        lambda n: _plain("recipe_045", f"{place(n)} 주변에 사람 몇 명이나 사나", ["recipe_045"],
                         f"「{place(n)}」 둘레 인구를 묻는다.", argument=place(n)),
        lambda n: _plain("recipe_049", f"{line(n)} 선로 따라 CCTV 띄워줘", ["recipe_049", "recipe_036"],
                         "노선을 따라가는 CCTV 를 원한다.", argument=line(n)),
        lambda n: _plain("recipe_059", f"{place(n)} 일대 인구 달마다 얼마나 늘었어", ["recipe_059"],
                         "월별 인구 증감을 묻는다.", argument=place(n)),
        lambda n: _plain("recipe_060", f"{place(n)} 옆 충전소 충전기 몇 개 비었는지까지 줘", ["recipe_060", "recipe_052"],
                         "장소 둘레 충전소와 빈 충전기 수를 원한다.", argument=place(n)),
        lambda n: _plain("recipe_061", f"{place(n)}에서 {MODES[n % 4][1]} {MODES[n % 4][2][0]}분 안에 갈 수 있는 곳",
                         ["recipe_061", "recipe_062"], "출발 장소 · 이동 방식 · 시간이 모두 있다.",
                         argument=place(n), travel_mode=MODES[n % 4][0], minutes=list(MODES[n % 4][2])),
        lambda n: _plain("recipe_063", _pick([f"여기서 {mode(n)[1]} {mode(n)[2][0]}분 거리 그려줘",
                                        f"이 위치에서 {mode(n)[1]} {mode(n)[2][0]}분 안에 닿는 곳"], n // 4),
                         ["recipe_063", "recipe_061"], "출발 장소 이름 없이 찍은 자리에서 출발한다.",
                         travel_mode=mode(n)[0], minutes=list(mode(n)[2])),
    ]


# ------------------------------------------------------------------ 손으로 쓴 경우
# 번호 -> 한 건. 실패 13건과 화면이 버티는지 볼 성공 몇 건이다.
# answer / model 에는 inputs 만 적고, 기능 설명은 FUNCTIONS 에서 붙인다.
_LONG_REASON = (
    "발화는 「이 위치」라고 찍은 자리를 가리키고 장소 이름을 말하지 않았다. 그 자리의 국회의원 "
    "선거구를 묻는데, 당선인이 누구이고 어느 정당인지를 함께 원한다. 공약 내용은 묻지 않았고 "
    "「몇 건」만 궁금해하므로 공약 목록을 펼치는 기능(022)이 아니라 당선인과 정당을 알려주고 공약은 "
    "세기만 하는 기능(021)이 맞다. 선거구 이름만 알려주는 기능(020)은 당선인을 주지 않으므로 뺀다. "
    "장소 이름이 없으므로 이름을 받는 기능(040)도 후보에서 내린다."
)

SPECIAL_CASES = {
    # ---- 기능 선택 실패 5
    4: {
        "utterance": "청주서원 선거구 알려줘",
        "stage": "function",
        "answer": ("recipe_015", _inputs(argument="청주서원")),
        "model": ("recipe_016", _inputs(argument="청주서원")),
        "candidates": ["recipe_015", "recipe_016", "recipe_008"],
        "reason": "선거구 이름을 말했고, 선거구를 묻는 발화는 대개 당선인까지 궁금해하므로 당선인·공약을 붙여 주는 기능을 고른다.",
    },
    23: {
        "utterance": "대전역 근처 선거구 당선인 누구야",
        "stage": "function",
        "answer": ("recipe_040", _inputs(argument="대전역")),
        "model": ("recipe_038", _inputs(argument="대전역")),
        "candidates": ["recipe_038", "recipe_040"],
        "reason": "대전역이 드는 선거구를 묻는다.",
    },
    61: {
        "utterance": "이 위치 인구가 달마다 얼마나 변했는지 보여줘",
        "stage": "function",
        "answer": ("recipe_055", _inputs()),
        "model": ("recipe_054", _inputs()),
        "candidates": ["recipe_054", "recipe_055", "recipe_059"],
        "reason": "찍은 자리의 인구 구성을 묻는다.",
    },
    97: {
        "utterance": "세종시 전기차 충전소 알려줘",
        "stage": "function",
        "status": "CLARIFY",
        "answer": ("recipe_060", _inputs(argument="세종시")),
        "model": (None, _inputs(argument="세종시")),
        "candidates": ["recipe_052", "recipe_060"],
        "reason": "충전소를 이름·주소로 찾는지 세종시 둘레를 찾는지 발화만으로 가를 수 없어 되묻는다.",
    },
    142: {
        "utterance": (
            "지난번 회의 때 이야기 나왔던 것처럼 오송역에서 출발해서 대중교통으로 30분이나 45분 안에 "
            "갈 수 있는 범위를 지도에 한 번 그려서 보여줄 수 있을까요, 가능하면 환승 포함해서요"
        ),
        "stage": "function",
        "answer": ("recipe_061", _inputs(argument="오송역", travel_mode="대중교통", minutes=[30, 45])),
        "model": ("recipe_062", _inputs(argument="오송역", travel_mode="대중교통", minutes=[30, 45])),
        "candidates": ["recipe_061", "recipe_062", "recipe_063"],
        "reason": "「환승」과 「대중교통」이 나오므로 갈아타는 길을 알려주는 기능을 고른다.",
    },
    # ---- 인자 추출 실패 8
    3: {
        "utterance": "철도 공약 낸 의원",
        "stage": "input",
        "answer": ("recipe_010", _inputs(argument="철도")),
        "model": ("recipe_010", _inputs(argument="철도 공약")),
        "candidates": ["recipe_010"],
        "reason": "철도 분야 공약을 낸 의원을 찾는다.",
    },
    17: {
        "utterance": "읍면동 단위로 인구 순위 매겨줘",
        "stage": "input",
        "answer": ("recipe_012", _inputs(admin_level="읍면동")),
        "model": ("recipe_012", _inputs(admin_level="시군구")),
        "candidates": ["recipe_012", "recipe_031"],
        "reason": "지역 단위별 인구 순위를 묻는다.",
    },
    44: {
        "utterance": "부산역에서 걸어서 20분 안에 닿는 곳",
        "stage": "input",
        "answer": ("recipe_061", _inputs(argument="부산역", travel_mode="도보", minutes=[20])),
        "model": ("recipe_061", _inputs(argument="부산역", travel_mode="대중교통", minutes=[20])),
        "candidates": ["recipe_061", "recipe_062"],
        "reason": "부산역에서 출발해 20분 안에 닿는 범위를 원한다.",
    },
    73: {
        "utterance": "서대전역에서 자전거로 10분, 20분 안에 닿는 곳 그려줘",
        "stage": "input",
        "answer": ("recipe_061", _inputs(argument="서대전역", travel_mode="자전거", minutes=[10, 20])),
        "model": ("recipe_061", _inputs(argument="서대전역", travel_mode="도보", minutes=[10])),
        "candidates": ["recipe_061"],
        "reason": "출발 장소와 시간이 있다.",
    },
    108: {
        "utterance": "천안아산역에서 차로 15분, 30분 걸리는 범위를 동 단위로 보여줘",
        "stage": "input",
        "answer": ("recipe_061", _inputs(argument="천안아산역", travel_mode="승용차", minutes=[15, 30])),
        "model": ("recipe_061", _inputs(argument="천안아산", travel_mode=None, minutes=[15], admin_level="읍면동")),
        "candidates": ["recipe_061", "recipe_033"],
        "reason": "천안아산에서 출발하는 범위를 동 단위로 원한다.",
    },
    126: {
        "utterance": "논산시 경계 그려줘",
        "stage": "input",
        "answer": ("recipe_005", _inputs(argument="논산시", admin_level="시군구")),
        "model": ("recipe_005", _inputs(argument="논산시", admin_level="읍면동")),
        "candidates": ["recipe_005"],
        "reason": "행정구역 이름을 말했다.",
    },
    163: {
        "utterance": "대전역 둘레 행정구역 경계 띄워줘",
        "stage": "input",
        "answer": ("recipe_033", _inputs(argument="대전역")),
        "model": ("recipe_033", _inputs()),
        "candidates": ["recipe_033", "recipe_005"],
        "reason": "역 둘레의 행정구역 경계를 원한다. 장소 이름은 좌표를 찾는 데만 쓴다.",
    },
    188: {
        "utterance": "지금 화면에 보이는 곳 안에서 국민의힘 교통 분야 공약을 당선인별로 정리해 줘",
        "stage": "input",
        "answer": ("recipe_029", _inputs(argument="교통")),
        "model": ("recipe_029", {**_inputs(argument="국민의힘"), "party": "국민의힘"}),
        "candidates": ["recipe_029", "recipe_010"],
        "reason": "보이는 범위의 공약을 정당으로 거른다.",
    },
    # ---- 성공이지만 채점에 안 쓰는 인자가 다른 것
    9: {
        "utterance": "공주시 인구 달마다 얼마나 늘었어",
        "graded": ("argument", "travel_mode", "minutes"),
        "answer": ("recipe_059", _inputs(argument="공주시")),
        "model": ("recipe_059", _inputs(argument="공주시", admin_level="시군구")),
        "candidates": ["recipe_059"],
        "reason": "공주시의 월별 인구 증감을 묻는다.",
    },
    52: {
        "utterance": "익산역 근처 CCTV 좀 띄워줘",
        "graded": ("argument",),
        "answer": ("recipe_036", _inputs(argument="익산역")),
        "model": ("recipe_036", _inputs(argument="익산역", admin_level="읍면동", minutes=[5])),
        "candidates": ["recipe_036", "recipe_019"],
        "reason": "익산역 둘레 CCTV 를 원한다.",
    },
    115: {
        "utterance": "청주 교통 공약 모아줘",
        "graded": ("argument",),
        "answer": ("recipe_010", {**_inputs(argument="교통"), "region": "청주"}),
        "model": ("recipe_010", {**_inputs(argument="교통"), "region": "청주시"}),
        "candidates": ["recipe_010", "recipe_022"],
        "reason": "청주 지역의 교통 공약을 찾는다.",
    },
    # ---- 성공이지만 화면이 버티는지 볼 것: 긴 판단 · 긴 설명 · 후보 여럿 · 모르는 인자
    30: {
        "utterance": "선택한 위치 당선인이랑 정당 알려줘",
        "answer": ("recipe_021", _inputs()),
        "model": ("recipe_021", _inputs()),
        "candidates": ["recipe_020", "recipe_021", "recipe_022", "recipe_040"],
        "reason": _LONG_REASON,
    },
    86: {
        "utterance": (
            "다음 주 현장 점검 가기 전에 미리 확인하려고 하는데 대전역 주변 충전소 가운데 지금 충전기가 "
            "비어 있는 곳이 몇 군데인지까지 자세하게 알려줄 수 있을까"
        ),
        "answer": ("recipe_060", _inputs(argument="대전역")),
        "model": ("recipe_060", _inputs(argument="대전역")),
        "candidates": ["recipe_060", "recipe_052", "recipe_056", "recipe_036", "recipe_045"],
        "reason": "장소 이름과 「주변」을 함께 말했고 빈 충전기 수까지 원한다.",
    },
    150: {
        "utterance": "건설기술 진흥법 2024년 개정 조문 보여줘",
        "graded": ("argument", "travel_mode", "minutes", "admin_level", "date_range"),
        "answer": ("recipe_014", {**_inputs(argument="건설기술 진흥법"), "date_range": "2024"}),
        "model": ("recipe_014", {**_inputs(argument="건설기술 진흥법"), "date_range": "2024"}),
        "candidates": ["recipe_014"],
        "reason": "문서 이름과 개정 연도를 말했다.",
    },
}

TOTAL = 200


def _side(fid: str | None, inputs: dict) -> dict:
    """정답표나 모델 출력 한쪽. 기능 번호에 화면 이름과 설명을 붙임."""
    return {
        "function_id": fid,
        "function_label": f"기능 {fid.split('_')[-1]}" if fid else None,
        "function_description": FUNCTIONS.get(fid) if fid else None,
        "inputs": dict(inputs),
    }


def _special(case_id: int, spec: dict) -> dict:
    """손으로 쓴 한 건을 결과 모양으로.

    규칙  stage 가 없으면 성공. graded 가 없으면 인자 넷을 모두 채점에 씀
    """
    answer_fid, answer_inputs = spec["answer"]
    model_fid, model_inputs = spec["model"]
    stage = spec.get("stage")
    model_output = _side(model_fid, model_inputs)
    model_output.update(
        reason=spec["reason"],
        candidate_ids=list(spec["candidates"]),
        status=spec.get("status", "SELECT"),
    )
    return {
        "id": case_id,
        "utterance": spec["utterance"],
        "passed": stage is None,
        "failure_stage": stage,
        "answer": _side(answer_fid, answer_inputs),
        "model_output": model_output,
        "graded_fields": list(spec.get("graded", V1_FIELDS)),
    }


def _from_template(case_id: int, plain: dict) -> dict:
    """성공 틀 한 건을 결과 모양으로. 정답표와 모델 출력이 같음."""
    model_output = _side(plain["fid"], plain["inputs"])
    model_output.update(reason=plain["reason"], candidate_ids=list(plain["candidates"]), status="SELECT")
    return {
        "id": case_id,
        "utterance": plain["utterance"],
        "passed": True,
        "failure_stage": None,
        "answer": _side(plain["fid"], plain["inputs"]),
        "model_output": model_output,
        "graded_fields": list(V1_FIELDS),
    }


def mock_test_results() -> list[dict]:
    """화면 시안용 결과 200건. 부를 때마다 같은 목록을 새로 만듦.

    출력  id 1~200 순서의 결과 목록
    규칙  SPECIAL_CASES 번호는 그 한 건을 그대로 씀. 나머지는 성공 틀을 순번으로 돌림
          틀 번호와 값 번호를 서로 다른 속도로 돌려 같은 발화가 되풀이되지 않게 함
    제약  난수를 쓰지 않는다
    """
    templates = _pass_templates()
    results, n = [], 0
    for case_id in range(1, TOTAL + 1):
        if case_id in SPECIAL_CASES:
            results.append(_special(case_id, SPECIAL_CASES[case_id]))
            continue
        template = templates[n % len(templates)]
        # 값 번호 = 돈 바퀴 수 + 틀 번호. 같은 틀이 돌 때마다 다음 값을 쓴다.
        results.append(_from_template(case_id, template(n // len(templates) + n % len(templates))))
        n += 1
    return results


def mock_run_conditions() -> dict:
    """실행 조건 네 줄. 지금 저장소 파일 이름을 그대로 적은 값임.

    출력  {"모델", "프롬프트 파일", "응답 형식 파일", "기능 정의 파일"}
    제약  설정 파일을 여기서 읽지 않는다.
          화면은 llm_engine · paths 를 import 하지 않음. 실제 실행이 붙으면
          그 실행이 쓴 조건을 결과와 함께 받아 이 자리를 바꿈
    """
    return {
        "모델": "solar-open2-250b",
        "프롬프트 파일": "llm_engine/roles/resolve/prompts/v1.yaml",
        "응답 형식 파일": "llm_engine/roles/resolve/response_schemas/v1.yaml",
        "기능 정의 파일": "KRRI_Ontology_Registry/menu/menu.yaml",
    }
