# test_app.py
# 역할: app.py 화면을 "로봇"이 대신 눌러보는 자동 테스트입니다.
#       (Streamlit의 AppTest: 브라우저 없이 입력 → 버튼 클릭 → 화면 내용 확인)
#
# ⚠️ 이 테스트는 인터넷을 전혀 쓰지 않아요. (ODsay 0번, 카카오 0번)
#    - 출발지 검색(카카오)은 "가짜 검색 결과(FAKE_PLACES)"로 바꿔치기해요.
#    - 역 주변 맛집·놀거리 검색도 "가짜 주변 장소(FAKE_NEARBY)"로 바꿔치기해요.
#    - 인터넷으로 나가는 요청은 "부르면 즉시 테스트 실패"로 막아두었어요.
#    - 추천 결과 화면은 "가짜 이동시간 표"로 확인해요. (내 컴퓨터의 캐시에 기대지 않아서 어디서나 똑같이 동작)
#    가짜 검색 결과에는 공공장소만 써요. (실제 개인 주소는 절대 적지 않기!)

import os  # 파일 경로를 다루기 위한 도구
import tempfile  # 테스트용 임시 폴더를 만들기 위한 도구
from unittest import mock  # 진짜 함수를 가짜로 바꿔치기하는 도구

import streamlit as st  # 검색 결과 기억(cache)을 비우기 위한 도구
from streamlit.testing.v1 import AppTest  # Streamlit 화면 자동 테스트 도구

import transit


def place(name, address, lat, lng):
    """가짜 검색 결과 하나를 만들어줍니다. (geocode.search_places가 돌려주는 모양과 같아요)"""
    return {"name": name, "address": address, "lat": lat, "lng": lng}


# 가짜 검색 결과: 검색어 → 결과 목록 (여기에 없는 검색어는 "못 찾음")
LOTTE_WORLD = [
    place("롯데월드 어드벤처", "서울 송파구 올림픽로 240", 37.511, 127.098),
    place("롯데월드몰", "서울 송파구 올림픽로 300", 37.513, 127.104),
    place("롯데월드 민속박물관", "서울 송파구 올림픽로 240", 37.512, 127.097),
]
FAKE_PLACES = {
    "강남역": [place("강남역", "서울 강남구 강남대로 396", 37.49809, 127.02800)],
    "수원역": [place("수원역", "경기 수원시 팔달구 덕영대로 924", 37.26579, 127.00009)],
    "홍대입구역": [place("홍대입구역", "서울 마포구 양화로 160", 37.55720, 126.92450)],
    "잠실역": [place("잠실역", "서울 송파구 올림픽로 265", 37.51330, 127.10010)],
    "롯데월드": LOTTE_WORLD,
    "<b>해킹</b>": [place("<b>해킹</b>", "", 37.5, 127.0)],
}


def fake_search(query):
    """가짜 출발지 검색: FAKE_PLACES에서 찾아서 돌려줘요. 없으면 빈 리스트(못 찾음)"""
    return FAKE_PLACES.get(query, [])


def nearby_place(name, category, distance, place_id):
    """가짜 주변 장소 하나를 만들어줍니다. (places.get_nearby_places가 돌려주는 모양과 같아요)"""
    return {"name": name, "category": category, "distance_m": distance,
            "url": f"http://place.map.kakao.com/{place_id}"}


# 가짜 주변 장소: 음식점·카페는 있고, 문화시설·관광명소는 없음
FAKE_NEARBY = {
    "food": [nearby_place("가짜국밥", "한식 > 국밥", 120, 1), nearby_place("가짜분식", "분식", 300, 2)],
    "cafe": [nearby_place("가짜카페", "커피전문점", 80, 3)],
    "culture": [],
    "attraction": [],
}
nearby_calls = []  # 가짜 주변 검색이 어떤 역으로 불렸는지 기록 (역 이름, 좌표, 종류)


def fake_nearby(station_coord, kind, station_name=""):
    """가짜 주변 장소 검색: 종류별로 FAKE_NEARBY를 돌려줘요."""
    nearby_calls.append((station_name, station_coord, kind))
    return FAKE_NEARBY[kind]


def fake_find_station(name):
    """가짜 역 찾기: "사당"(또는 "사당역")만 찾을 수 있어요."""
    if name in ("사당", "사당역"):
        return {"name": "사당역 2호선", "address": "서울 동작구 남부순환로 지하2089", "lat": 37.47656, "lng": 126.98156}
    return None

# 가짜 이동시간 표: 강남역 + 수원역 → 후보 5곳
# (fair는 금정이 1위, fast로 바꾸면 사당이 1위가 되도록 만든 숫자예요)
GANGNAM_GEUMJEONG = {"time_min": 40, "transfers": 1, "segments": [
    {"type": "walk", "minutes": 1, "distance_m": 37},
    {"type": "subway", "line": "2호선", "start": "강남", "end": "사당", "minutes": 9, "stations": 4},
    {"type": "walk", "minutes": 3, "distance_m": 0},
    {"type": "subway", "line": "4호선", "start": "사당", "end": "금정", "minutes": 23, "stations": 10},
]}


def simple_route(minutes, line, start, end):
    """환승 없는 가짜 경로 하나를 만들어줍니다."""
    return {"time_min": minutes, "transfers": 0, "segments": [
        {"type": "subway", "line": line, "start": start, "end": end, "minutes": minutes, "stations": 5},
    ]}


FAKE_TABLE = {
    "friends": ["강남역", "수원역"],
    "stations": [
        {"name": "금정", "routes": [GANGNAM_GEUMJEONG, simple_route(19, "1호선", "수원", "금정")]},
        {"name": "사당", "routes": [simple_route(11, "2호선", "강남", "사당"), simple_route(42, "1호선", "수원", "사당")]},
        {"name": "판교", "routes": [simple_route(16, "신분당선", "강남", "판교"), simple_route(50, "수인분당선", "수원", "판교")]},
        {"name": "과천", "routes": [simple_route(30, "4호선", "강남", "과천"), simple_route(45, "4호선", "수원", "과천")]},
        {"name": "범계", "routes": [simple_route(44, "4호선", "강남", "범계"), simple_route(46, "1호선", "수원", "범계")]},
    ],
}


def internet_forbidden(url, *args, **kwargs):
    """어디로든 인터넷 요청을 보내려고 하면 바로 테스트를 실패시키는 '가짜 우체부'"""
    raise AssertionError(f"테스트 중에 인터넷({url})을 부르려고 했어요!")


def open_app():
    """app.py를 열고 첫 화면을 그립니다."""
    st.cache_data.clear()  # 앞 테스트의 검색 결과 기억을 지우고 새로 시작
    at = AppTest.from_file("app.py", default_timeout=30)
    return at.run()


def friend_inputs(at):
    """친구 출발지 입력칸들만 골라줍니다. ("이미 장소를 정했어요" 탭의 입력칸은 빼고)"""
    return [box for box in at.text_input if box.key.startswith("place_")]


def type_places(at, names):
    """입력칸에 출발지들을 차례로 적고 화면을 다시 그립니다."""
    for box, name in zip(friend_inputs(at), names):
        box.input(name)
    return at.run()


def click(at, label):
    """글자가 label인 버튼을 누르고 화면을 다시 그립니다."""
    button = next(b for b in at.button if b.label == label)
    return button.click().run()


def all_text(at):
    """화면에 보이는 글자들을 전부 하나로 이어 붙입니다. (확인용)"""
    parts = []
    for kind in [at.title, at.markdown, at.caption, at.warning, at.error, at.info, at.subheader]:
        parts += [str(element.value) for element in kind]
    return "\n".join(parts)


def remove_buttons(at):
    """화면에 있는 ✕(친구 삭제) 버튼들"""
    return [b for b in at.button if b.label == "✕"]


# ─────────────────────────────────────────────
# 테스트들
# ─────────────────────────────────────────────

def test_first_screen():
    """처음 화면: 제목, 입력칸 2개, ✕ 없음, 기본 기준 fair, 사용량 표시"""
    at = open_app()
    text = all_text(at)
    assert "🚇 오늘은여기서" in text
    assert "친구들 모두에게 공정한 약속 장소 찾기" in text
    assert len(friend_inputs(at)) == 2
    assert len(remove_buttons(at)) == 0  # 2명일 땐 ✕ 숨김
    assert friend_inputs(at)[0].placeholder == "주소, 아파트 이름, 역 이름 모두 가능해요"
    assert at.radio(key="criterion").value == "fair"
    assert at.radio(key="criterion").options == ["⚖️ 공평하게", "⚡ 빠르게"]  # 기준은 2개
    assert f"오늘 ODsay 사용량: {transit.get_today_usage()}/30건" in text


def test_add_friend_max_3():
    """'+ 친구 추가'로 3칸까지만 늘어나고, 3칸이 되면 추가 버튼이 꺼지고 ✕가 생겨야 해요."""
    at = open_app()
    at = click(at, "+ 친구 추가")
    assert len(friend_inputs(at)) == 3
    assert len(remove_buttons(at)) == 3
    add_button = next(b for b in at.button if b.label == "+ 친구 추가")
    assert add_button.disabled


def test_remove_middle_friend():
    """가운데 친구를 지워도, 남은 친구들의 입력값이 밀리거나 섞이지 않아야 해요."""
    at = open_app()
    at = click(at, "+ 친구 추가")
    friend_inputs(at)[0].input("강남역")
    friend_inputs(at)[1].input("홍대입구역")
    friend_inputs(at)[2].input("수원역")
    at = at.run()

    at = remove_buttons(at)[1].click().run()  # 두 번째 친구(홍대입구역)의 ✕

    assert [t.value for t in friend_inputs(at)] == ["강남역", "수원역"]
    assert [t.label for t in friend_inputs(at)] == ["친구 1 출발지", "친구 2 출발지"]  # 번호는 다시 1, 2
    assert len(remove_buttons(at)) == 0  # 2명이 되면 ✕ 숨김


def test_remove_then_add():
    """지운 뒤 다시 추가하면, 새 칸은 빈칸이어야 해요. (지운 친구의 글자가 되살아나면 안 돼요)"""
    at = open_app()
    at = click(at, "+ 친구 추가")
    friend_inputs(at)[2].input("잠실역")
    at = at.run()
    at = remove_buttons(at)[2].click().run()  # 세 번째 친구 삭제
    at = click(at, "+ 친구 추가")  # 다시 추가

    assert len(friend_inputs(at)) == 3
    assert friend_inputs(at)[2].value == ""


def test_empty_input():
    """빈 칸이 있으면 친절하게 안내해야 해요."""
    at = open_app()
    friend_inputs(at)[0].input("강남역")
    at = click(at, "약속 장소 추천받기")
    assert "비어 있는 출발지 칸이 있어요" in all_text(at)
    assert not at.exception


def test_result_cards_and_switch_criterion():
    """결과 카드(경로 요약 + 자세히 보기) → 기준을 바꿔도 이동시간 표를 다시 만들지 않아야 해요."""
    fake_build = mock.Mock(return_value=FAKE_TABLE)
    with mock.patch("recommend.build_travel_table", fake_build):
        at = type_places(open_app(), ["강남역", "수원역"])
        assert "📍 강남역 (서울 강남구 강남대로 396)" in all_text(at)  # 위치 확인 문구
        at = click(at, "약속 장소 추천받기")
        assert not at.exception, at.exception

        # 이동시간 표는 "고른 위치의 이름"과 "좌표"로 만들어요
        assert fake_build.call_args.args == (["강남역", "수원역"], [(37.49809, 127.028), (37.26579, 127.00009)])

        text = all_text(at)
        assert "🏆 1위 · 금정역" in text  # fair 기준 1위
        assert "40분 · 환승 1" in text  # 막대 옆 글자
        assert "**강남역** · 🏠 → 도보 1분 → 강남역 [2호선] → 사당역 [4호선] → 금정역" in text  # 경로 요약
        assert "🏠 출발지에서 강남역까지 도보 1분 (37m)" in text  # 펼치기 안: 집에서 첫 역까지
        assert "🚇 2호선 강남역 → 사당역 (4개 역, 9분)" in text  # 펼치기 안의 자세한 경로
        assert at.expander[0].label == "자세한 경로 보기"

        # 카드는 3위까지만, 4~5위는 스위치를 켜야 보여요
        assert "4위 · " not in text
        at = at.toggle(key="show_others").set_value(True).run()
        assert "#### 4위 · " in all_text(at)

        # 기준을 fast로 바꾸면 사당이 1위, 그리고 이동시간 표는 다시 만들지 않음
        at = at.radio(key="criterion").set_value("fast").run()
        assert not at.exception, at.exception
        text = all_text(at)
        assert "🏆 1위 · 사당역" in text
        assert "두 기준 모두 같은 역을 추천해요" not in all_success(at)  # 1위가 다르니까 안내 없음
        assert fake_build.call_count == 1  # 버튼을 누른 1번뿐!

        # 친구를 추가하면(출발지 변경) 옛 결과는 숨기고 안내
        at = click(at, "+ 친구 추가")
        text = all_text(at)
        assert "출발지가 바뀌었어요" in text
        assert "🏆" not in text


def show_result(table, names=("강남역", "수원역")):
    """가짜 이동시간 표로 추천 결과 화면을 띄워줍니다."""
    with mock.patch("recommend.build_travel_table", mock.Mock(return_value=table)):
        at = type_places(open_app(), names)
        return click(at, "약속 장소 추천받기")


def bar_rows(at):
    """화면의 막대 그래프 HTML들만 모아줍니다."""
    return [m.value for m in at.markdown if 'class="travel-bars"' in m.value]


def all_success(at):
    """초록 안내 상자(st.success)의 글자들"""
    return "\n".join(str(s.value) for s in at.success)


def test_travel_bars():
    """카드마다 친구 수만큼 막대가 있고, 모든 카드가 같은 눈금을 써야 해요."""
    at = show_result(FAKE_TABLE)
    bars = bar_rows(at)
    assert len(bars) == 3  # 1~3위 카드마다 막대 그래프 1개
    assert all(b.count('class="bar"') == 2 for b in bars)  # 친구 2명 → 막대 2개

    # 눈금 기준 = 순위에 든 역 중 가장 긴 시간(판교 50분) → 50분은 80%, 40분은 64%
    assert "width:64.0%" in bars[0]  # 1위 금정, 강남역 40분
    at = at.toggle(key="show_others").set_value(True).run()
    assert any("width:80.0%" in b for b in bar_rows(at))  # 판교 50분 (4위 이하)


def test_same_winner_message():
    """두 기준의 1위가 같은 역이면 '모두에게 좋은 장소' 안내가 나와야 해요."""
    table = {"friends": ["강남역", "수원역"], "stations": [
        {"name": "과천", "routes": [{"time_min": 28, "transfers": 1}, {"time_min": 31, "transfers": 1}]},
        {"name": "정자", "routes": [{"time_min": 21, "transfers": 0}, {"time_min": 41, "transfers": 0}]},
    ]}
    at = show_result(table)
    assert "두 기준 모두 같은 역을 추천해요. 모두에게 좋은 장소예요! 👍" in all_success(at)


def test_friend_name_is_escaped():
    """친구 이름에 HTML 글자가 있어도, 막대 그래프 안에서 그대로 실행되지 않고 글자로만 보여야 해요."""
    table = {"friends": ["<b>해킹</b>", "수원역"], "stations": [
        {"name": "과천", "routes": [{"time_min": 28, "transfers": 1}, {"time_min": 31, "transfers": 1}]},
    ]}
    at = show_result(table, names=("<b>해킹</b>", "수원역"))
    bars = bar_rows(at)[0]
    assert "&lt;b&gt;해킹&lt;/b&gt;" in bars
    assert "<b>해킹</b>" not in bars


def test_choose_among_results():
    """검색 결과가 여러 개면 상위 3개 중에서 고르고, 고른 위치로 이동시간을 계산해야 해요."""
    fake_build = mock.Mock(return_value=FAKE_TABLE)
    with mock.patch("recommend.build_travel_table", fake_build):
        at = type_places(open_app(), ["롯데월드", "수원역"])
        pick = at.radio(key="pick_0_롯데월드")
        assert pick.label == "어느 곳인가요?"
        assert pick.options == [
            "롯데월드 어드벤처 (서울 송파구 올림픽로 240)",
            "롯데월드몰 (서울 송파구 올림픽로 300)",
            "롯데월드 민속박물관 (서울 송파구 올림픽로 240)",
        ]
        assert "📍 롯데월드 어드벤처 (서울 송파구 올림픽로 240)" in all_text(at)  # 처음엔 1번이 선택됨

        # 두 번째 결과를 고르면 확인 문구도 바뀌어요
        at = pick.set_value(1).run()
        assert "📍 롯데월드몰 (서울 송파구 올림픽로 300)" in all_text(at)

        at = click(at, "약속 장소 추천받기")
        assert not at.exception, at.exception
        names, coords = fake_build.call_args.args
        assert names == ["롯데월드몰", "수원역"]
        assert coords[0] == (37.513, 127.104)  # 고른 곳의 좌표

        # 결과를 본 뒤 다른 위치를 고르면, 옛 결과는 숨기고 안내해요
        at = at.radio(key="pick_0_롯데월드").set_value(2).run()
        text = all_text(at)
        assert "출발지가 바뀌었어요" in text
        assert "🏆" not in text


def test_top_station_nearby():
    """1위 역 카드 아래에 주변 장소 탭 4개가 나오고, 기준을 바꿔 1위가 바뀌면 새 1위 역으로 바뀌어야 해요."""
    # 가짜 표에 역 좌표를 넣어요 (실제 표에는 build_travel_table이 넣어줘요)
    coords = {"금정": (37.37247, 126.94347), "사당": (37.47656, 126.98156)}
    table = {"friends": FAKE_TABLE["friends"], "stations": [
        {**s, "lat": coords.get(s["name"], (37.4, 127.0))[0], "lng": coords.get(s["name"], (37.4, 127.0))[1]}
        for s in FAKE_TABLE["stations"]
    ]}
    nearby_calls.clear()
    at = show_result(table)
    assert not at.exception, at.exception
    text = all_text(at)

    assert "🗺️ 금정역 주변 맛집과 놀거리" in text  # fair 1위 = 금정
    assert "정렬: 카카오 검색 정확도/거리 기준" in text
    kind_tabs = [t.label for t in at.tabs if t.label[0] in "🍜☕🎬🎡"]  # 맨 위 탭 2개는 빼고
    assert kind_tabs == ["🍜 음식점", "☕ 카페", "🎬 문화시설", "🎡 관광명소"]
    assert "- **[가짜국밥](http://place.map.kakao.com/1)** · 한식 > 국밥 · 120m" in text
    assert "- **[가짜카페](http://place.map.kakao.com/3)** · 커피전문점 · 80m" in text
    assert [str(i.value) for i in at.info].count("주변에 찾은 곳이 없어요") == 2  # 문화시설, 관광명소
    assert ("금정", coords["금정"], "food") in nearby_calls  # 1위 역의 이름과 좌표로 검색
    assert all(name == "금정" for name, _, _ in nearby_calls)  # 2위 이하 역은 검색하지 않음

    # 기준을 fast로 바꾸면 1위가 사당 → 주변 장소도 사당역 기준
    at = at.radio(key="criterion").set_value("fast").run()
    assert "🗺️ 사당역 주변 맛집과 놀거리" in all_text(at)
    assert "🗺️ 금정역" not in all_text(at)


def test_decided_tab():
    """'이미 장소를 정했어요' 탭: 역 이름만 넣으면 위치 확인 문구와 주변 장소가 바로 나와야 해요."""
    at = open_app()
    assert [t.label for t in at.tabs] == ["🔎 약속 장소 추천받기", "📍 이미 장소를 정했어요"]

    at = at.text_input(key="decided_station").input("사당").run()
    assert not at.exception, at.exception
    text = all_text(at)
    assert "📍 사당역 2호선 (서울 동작구 남부순환로 지하2089)" in text
    assert "🗺️ 사당역 주변 맛집과 놀거리" in text
    assert "정렬: 카카오 검색 정확도/거리 기준" in text
    assert "가짜국밥" in text

    # 없는 역 이름이면 안내만 하고 멈추지 않아요
    at = at.text_input(key="decided_station").input("없는역이름").run()
    assert not at.exception, at.exception
    assert "지하철역을 찾을 수 없어요" in all_text(at)


def test_place_not_found():
    """없는 장소를 넣으면 입력칸 아래에서 바로 안내하고, 추천 버튼을 눌러도 멈추지 않아야 해요."""
    at = type_places(open_app(), ["강남역", "ㅁㄴㅇㄹ존재하지않는곳"])
    assert "'ㅁㄴㅇㄹ존재하지않는곳'을(를) 찾을 수 없어요" in all_text(at)

    at = click(at, "약속 장소 추천받기")
    assert not at.exception, at.exception
    assert "찾지 못한 출발지가 있어요" in all_text(at)


def test_daily_limit_reached():
    """오늘 30건을 다 썼으면, ODsay를 부르지 않고 한도 안내를 해야 해요."""
    folder = tempfile.mkdtemp()
    fake_usage = os.path.join(folder, "usage.json")
    fake_cache = os.path.join(folder, "cache.json")  # 빈 메모장 → 무조건 ODsay가 필요한 상황
    transit.write_json(fake_usage, {"date": transit.today_kst(), "count": 30})

    with mock.patch("transit.USAGE_PATH", fake_usage), mock.patch("transit.CACHE_PATH", fake_cache):
        at = type_places(open_app(), ["홍대입구역", "잠실역"])
        at = click(at, "약속 장소 추천받기")
        text = all_text(at)

    assert not at.exception, at.exception
    assert "오늘 대중교통 조회 한도를 다 썼어요" in text
    assert "오늘 ODsay 사용량: 30/30건" in text


# 이 파일을 직접 실행하면 위의 테스트들을 차례로 실행합니다.
if __name__ == "__main__":
    usage_before = transit.get_today_usage()

    tests = [
        test_first_screen, test_add_friend_max_3, test_remove_middle_friend, test_remove_then_add,
        test_empty_input, test_result_cards_and_switch_criterion, test_travel_bars, test_same_winner_message,
        test_friend_name_is_escaped, test_choose_among_results, test_top_station_nearby, test_decided_tab,
        test_place_not_found, test_daily_limit_reached,
    ]
    # 모든 테스트 동안 출발지 검색은 가짜로 바꾸고, 인터넷 요청(카카오·ODsay)은 막아둡니다.
    # (주변 장소 검색과 역 찾기도 가짜로 바꿔요)
    with mock.patch("geocode.search_places", fake_search), mock.patch("requests.get", internet_forbidden), \
            mock.patch("places.get_nearby_places", fake_nearby), mock.patch("places.find_station", fake_find_station):
        for test in tests:
            test()  # 실패하면 여기서 AssertionError가 나며 멈춰요
            print(f"✅ {test.__name__}: {test.__doc__.strip().splitlines()[0]}")

    usage_after = transit.get_today_usage()
    assert usage_after == usage_before, "ODsay 사용량이 바뀌었어요!"
    print(f"\n🎉 테스트 {len(tests)}개 모두 통과! (카카오·ODsay 실제 호출 0번, 사용량 {usage_after}/30건 그대로)")
