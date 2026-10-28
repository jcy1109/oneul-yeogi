# test_app.py
# 역할: app.py 화면을 "로봇"이 대신 눌러보는 자동 테스트입니다.
#       (Streamlit의 AppTest: 브라우저 없이 입력 → 버튼 클릭 → 화면 내용 확인)
#
# ⚠️ 이 테스트는 인터넷을 전혀 쓰지 않아요. (ODsay 0번, 카카오 0번)
#    - 출발지 검색(카카오)은 "가짜 검색 결과(FAKE_PLACES)"로 바꿔치기해요.
#    - 인터넷으로 나가는 요청은 "부르면 즉시 테스트 실패"로 막아두었어요.
#    - 추천 결과 화면은 "가짜 이동시간 표"로 확인해요. (내 컴퓨터의 캐시에 기대지 않아서 어디서나 똑같이 동작)
#    가짜 검색 결과에는 공공장소만 써요. (실제 개인 주소는 절대 적지 않기!)

import os  # 파일 경로를 다루기 위한 도구
from contextlib import ExitStack  # 여러 개의 바꿔치기(mock.patch)를 한꺼번에 켜고 끄기 위한 도구
from datetime import time  # 약속 시각(예: 19:00)을 만들기 위한 도구
from urllib.parse import quote  # 링크 주소 속 한글을 확인하기 위한 도구
import tempfile  # 테스트용 임시 폴더를 만들기 위한 도구
from unittest import mock  # 진짜 함수를 가짜로 바꿔치기하는 도구

import streamlit as st  # 검색 결과 기억(cache)을 비우기 위한 도구
from streamlit.testing.v1 import AppTest  # Streamlit 화면 자동 테스트 도구

import last_train
import transit
from test_last_train import load


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
    "스타필드시티 위례": [place("스타필드시티 위례", "경기 하남시 위례대로 200", 37.48013, 127.14813)],
    "복정역": [place("복정역 8호선", "서울 송파구 송파대로 지하 6", 37.47074, 127.12672)],
    "<b>해킹</b>": [place("<b>해킹</b>", "", 37.5, 127.0)],
}


def fake_search(query):
    """가짜 출발지 검색: FAKE_PLACES에서 찾아서 돌려줘요. 없으면 빈 리스트(못 찾음)"""
    return FAKE_PLACES.get(query, [])

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


def origins(at):
    """친구별 출발지 입력칸들 (막차 목표 지점 칸은 빼고)"""
    return [box for box in at.text_input if box.key.startswith("place_")]


def goals(at):
    """친구별 '막차로 꼭 도착해야 하는 곳' 입력칸들"""
    return [box for box in at.text_input if box.key.startswith("goal_")]


def type_places(at, names):
    """입력칸에 출발지들을 차례로 적고 화면을 다시 그립니다."""
    for box, name in zip(origins(at), names):
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
    assert len(origins(at)) == 2
    assert len(remove_buttons(at)) == 0  # 2명일 땐 ✕ 숨김
    assert origins(at)[0].placeholder == "주소, 아파트 이름, 역 이름 모두 가능해요"
    # 친구마다 "막차로 꼭 도착해야 하는 곳" 칸도 있어요 (선택)
    assert [box.label for box in goals(at)] == ["🌙 막차로 꼭 도착해야 하는 곳 (선택)"] * 2
    assert at.radio(key="criterion").value == "fair"
    assert at.radio(key="criterion").options == ["⚖️ 공평하게", "⚡ 빠르게"]  # 기준은 2개
    assert at.radio(key="day_type").options == ["평일", "토요일", "일요일·공휴일"]  # 약속 날짜 종류
    assert at.radio(key="day_type").value == "weekday"  # 처음엔 평일
    assert at.time_input(key="meeting_time").value == time(19, 0)  # 처음엔 저녁 7시
    assert len(at.tabs) == 0  # 맛집 기능의 탭은 없어졌어요
    assert f"오늘 ODsay 사용량: {transit.get_today_usage()}/30건" in text
    # 테스트 모드: 사이드바 스위치는 처음에 켜져 있고, 화면 위쪽에 표시돼요
    assert at.toggle(key="test_mode").label == "🧪 테스트 모드 (ODsay 호출 안 함)"
    assert at.toggle(key="test_mode").value is True
    badge = at.info[0]  # 화면 위쪽의 파란 안내 상자
    assert badge.value == "테스트 모드 · ODsay를 부르지 않고 저장된 결과만 써요" and badge.icon == "🧪"


def test_add_friend_max_3():
    """'+ 친구 추가'로 3칸까지만 늘어나고, 3칸이 되면 추가 버튼이 꺼지고 ✕가 생겨야 해요."""
    at = open_app()
    at = click(at, "+ 친구 추가")
    assert len(origins(at)) == 3
    assert len(remove_buttons(at)) == 3
    add_button = next(b for b in at.button if b.label == "+ 친구 추가")
    assert add_button.disabled


def test_remove_middle_friend():
    """가운데 친구를 지워도, 남은 친구들의 입력값이 밀리거나 섞이지 않아야 해요."""
    at = open_app()
    at = click(at, "+ 친구 추가")
    origins(at)[0].input("강남역")
    origins(at)[1].input("홍대입구역")
    origins(at)[2].input("수원역")
    at = at.run()

    at = remove_buttons(at)[1].click().run()  # 두 번째 친구(홍대입구역)의 ✕

    assert [t.value for t in origins(at)] == ["강남역", "수원역"]
    assert [t.label for t in origins(at)] == ["친구 1 출발지", "친구 2 출발지"]  # 번호는 다시 1, 2
    assert len(remove_buttons(at)) == 0  # 2명이 되면 ✕ 숨김


def test_remove_then_add():
    """지운 뒤 다시 추가하면, 새 칸은 빈칸이어야 해요. (지운 친구의 글자가 되살아나면 안 돼요)"""
    at = open_app()
    at = click(at, "+ 친구 추가")
    origins(at)[2].input("잠실역")
    at = at.run()
    at = remove_buttons(at)[2].click().run()  # 세 번째 친구 삭제
    at = click(at, "+ 친구 추가")  # 다시 추가

    assert len(origins(at)) == 3
    assert origins(at)[2].value == ""


def test_empty_input():
    """빈 칸이 있으면 친절하게 안내해야 해요."""
    at = open_app()
    origins(at)[0].input("강남역")
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


def test_departure_times():
    """카드마다 친구별 출발 시각이 나오고, 약속 시각을 바꾸면 이동시간 표를 다시 만들지 않고 다시 계산해야 해요."""
    fake_build = mock.Mock(return_value=FAKE_TABLE)
    with mock.patch("recommend.build_travel_table", fake_build):
        at = type_places(open_app(), ["강남역", "수원역"])
        at = click(at, "약속 장소 추천받기")
        assert not at.exception, at.exception
        text = all_text(at)

        # 1위 금정: 강남역 40분, 수원역 19분 → 19:00 - 이동시간 - 여유 5분
        assert "⏰ 평일 19:00 약속 기준" in text
        assert "- 🏠 강남역 친구: **18:15 출발**\n- 🏠 수원역 친구: **18:36 출발**" in text
        assert text.count("이동시간은 평균 기준이라 실제와 몇 분 다를 수 있어요") == 3  # 카드 3개마다

        # 토요일 20:30으로 바꾸면 출발 시각도 바뀌어요 (옛 결과를 숨기지 않아요)
        at = at.radio(key="day_type").set_value("saturday").run()
        at = at.time_input(key="meeting_time").set_value(time(20, 30)).run()
        assert not at.exception, at.exception
        text = all_text(at)
        assert "⏰ 토요일 20:30 약속 기준" in text
        assert "🏠 강남역 친구: **19:45 출발**" in text
        assert "출발지가 바뀌었어요" not in text
        assert fake_build.call_count == 1  # 이동시간 표는 처음 1번만 (ODsay 다시 안 부름)


def test_kakao_map_link():
    """추천역 카드마다 카카오맵에서 그 역을 검색한 화면으로 가는 링크가 있어야 해요."""
    at = show_result(FAKE_TABLE)
    links = [m.value for m in at.markdown if "카카오맵에서 주변 둘러보기" in m.value]
    assert len(links) == 3  # 1~3위 카드마다 1개
    assert links[0] == f"[🗺️ 카카오맵에서 주변 둘러보기](https://map.kakao.com/?q={quote('금정역')})"


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
        at = open_app()
        at = at.toggle(key="test_mode").set_value(False).run()  # 테스트 모드를 꺼야 ODsay를 쓰려고 해요
        at = type_places(at, ["홍대입구역", "잠실역"])
        at = click(at, "약속 장소 추천받기")
        text = all_text(at)

    assert not at.exception, at.exception
    assert "오늘 대중교통 조회 한도를 다 썼어요" in text
    assert "오늘 ODsay 사용량: 30/30건" in text


def empty_cache_files():
    """빈 메모장과 오늘 0건인 기록부를 임시 폴더에 만들어 (메모장 경로, 기록부 경로)를 돌려줍니다."""
    folder = tempfile.mkdtemp()
    fake_usage = os.path.join(folder, "usage.json")
    transit.write_json(fake_usage, {"date": transit.today_kst(), "count": 0})
    return os.path.join(folder, "cache.json"), fake_usage


def test_test_mode_without_saved_result():
    """테스트 모드에서 메모장에 없는 출발지면, ODsay를 부르지 않고 '저장된 결과가 없어요'라고 안내해야 해요."""
    fake_cache, fake_usage = empty_cache_files()
    with mock.patch("transit.USAGE_PATH", fake_usage), mock.patch("transit.CACHE_PATH", fake_cache):
        at = type_places(open_app(), ["홍대입구역", "잠실역"])
        at = click(at, "약속 장소 추천받기")
        text = all_text(at)

    assert not at.exception, at.exception
    assert "테스트 모드에서는 저장된 결과가 없어요" in text
    assert "저장된 예시 불러오기" in text
    assert "오늘 ODsay 사용량: 0/30건" in text  # 사용량이 늘지 않았어요
    assert "🏆" not in text


def test_load_saved_example():
    """'저장된 예시 불러오기'를 누르면, 모든 구간이 메모장에 있는 조합이 입력칸에 채워져야 해요."""
    gangnam_suwon = [(37.49809, 127.028), (37.26579, 127.00009)]

    def fake_estimate(coords):
        # 강남역 + 수원역 조합만 "모두 저장됨(0건)", 나머지는 저장 안 됨
        return (0 if coords == gangnam_suwon else 3), []

    with mock.patch("recommend.estimate_calls", fake_estimate):
        at = open_app()
        at = click(at, "+ 친구 추가")  # 3칸이었다가
        origins(at)[0].input("잠실역")
        at = click(at.run(), "저장된 예시 불러오기")

    assert not at.exception, at.exception
    assert [t.value for t in origins(at)] == ["강남역", "수원역"]  # 예시 2명으로 바뀜
    assert "예시를 불러왔어요: 강남역 + 수원역" in "\n".join(str(s.value) for s in at.success)


def test_load_saved_example_none():
    """저장된 예시가 하나도 없으면, 입력칸은 그대로 두고 안내만 해야 해요."""
    with mock.patch("recommend.estimate_calls", lambda coords: (5, [])):
        at = open_app()
        origins(at)[0].input("잠실역")
        at = click(at.run(), "저장된 예시 불러오기")

    assert not at.exception, at.exception
    assert origins(at)[0].value == "잠실역"
    assert "저장된 예시가 없어요" in "\n".join(str(w.value) for w in at.warning)


# ── 귀갓길 막차 ──
JEONGJA = (37.3661737923199, 127.108097457244)  # 1위 역(정자) 좌표
SUWON = (37.26579, 127.00009)  # 가짜 검색 결과의 수원역 좌표
GANGNAM = (37.49809, 127.028)  # 가짜 검색 결과의 강남역 좌표
WIRYE = (37.48013, 127.14813)  # 가짜 검색 결과의 스타필드시티 위례 좌표
BOKJEONG = (37.47074, 127.12672)  # 가짜 검색 결과의 복정역 좌표 (실제 카카오 첫 번째 결과와 같은 곳)

# 1위가 정자인 가짜 이동시간 표 (막차 계산에는 역 좌표가 필요해요)
JEONGJA_TABLE = {"friends": ["스타필드시티 위례", "수원역"], "stations": [
    {"name": "정자", "lat": JEONGJA[0], "lng": JEONGJA[1],
     "routes": [simple_route(39, "수인분당선", "복정", "정자"), simple_route(41, "수인분당선", "수원", "정자")]},
]}


def seeded_last_train_files():
    """
    막차 계산에 필요한 메모장을 임시 폴더에 만들어요. (메모장 경로, 시간표 메모장 경로, 기록부 경로)
      - 정자 → 수원: 실제 길찾기 답장 + 실제 정자역 시간표 (평일 23:38 고색행)
      - 정자 → 강남역: 실제 740번 버스 구간으로 만든 가짜 경로 (약 24:04)
      - 정자 → 스타필드시티 위례: 실제 귀갓길 (수인분당선 → 3217번, 버스 막차 값이 하나뿐)
      - 정자 → 복정역: 실제 귀갓길 (수인분당선만)
    """
    folder = tempfile.mkdtemp()
    paths = [os.path.join(folder, name) for name in ("cache.json", "timetable.json", "usage.json")]
    transit.write_json(paths[2], {"date": transit.today_kst(), "count": 0})
    bus_path = load("path_gangnam_to_hongdae_bus_only.json")["result"]["path"][0]["subPath"]
    transit.write_json(paths[0], {
        transit.make_cache_key(JEONGJA, SUWON): transit.parse_transit_response(load("path_jeongja_to_suwon.json")),
        transit.make_cache_key(JEONGJA, GANGNAM): {"time_min": 60, "transfers": 0,
                                                   "segments": transit.parse_segments(bus_path)},
        transit.make_cache_key(JEONGJA, WIRYE): load("route_jeongja_to_wirye.json"),
        transit.make_cache_key(JEONGJA, BOKJEONG): load("route_jeongja_to_bokjeong.json"),
    })
    with mock.patch("last_train.TIMETABLE_CACHE_PATH", paths[1]):
        last_train.save_timetable("subway", 1530, load("subway_schedule_1530_jeongja_suinbundang.json"))
        last_train.save_timetable("bus", 1273, load("bus_lane_1273_bus740.json"))
        last_train.save_timetable("bus", 1018, load("bus_lane_1018_bus3217.json"))
    return paths


def test_last_train_flow():
    """막차 확인하기 → 모임 종료 시각과 친구별 막차, 날짜 종류를 바꾸면 메모장으로 다시 계산 (ODsay 0건)"""
    cache, timetable, usage = seeded_last_train_files()
    with mock.patch("transit.CACHE_PATH", cache), mock.patch("transit.USAGE_PATH", usage), \
            mock.patch("last_train.TIMETABLE_CACHE_PATH", timetable), \
            mock.patch("recommend.build_travel_table", mock.Mock(return_value=JEONGJA_TABLE)):
        at = type_places(open_app(), ["스타필드시티 위례", "수원역"])
        goals(at)[0].input("강남역")  # 위례 친구는 강남역까지만 가면 돼요 / 수원역 친구는 빈칸 → 출발지까지
        at = click(at.run(), "약속 장소 추천받기")
        text = all_text(at)
        assert "🌙 귀갓길 막차 · 정자역에서" in text
        assert "🧪 테스트 모드: 저장된 경로와 시간표만 써요. (ODsay 0건)" in text
        assert "이 모임은" not in all_success(at)  # 누르기 전에는 계산하지 않아요

        at = click(at, "🌙 막차 확인하기")
        assert not at.exception, at.exception
        text = all_text(at)
        # 수원역 친구: 23:38 열차 - 도보 1분 = 23:37 / 위례 친구: 버스 약 24:04 - 도보 2분 = 24:02
        # → 가장 이른 23:37 - 여유 10분 = 23:27
        summary = next(box for box in at.success if "이 모임은" in box.value)
        assert (summary.value, summary.icon) == ("이 모임은 23:27까지 놀 수 있어요 (수원역 친구 기준)", "🌙")
        assert "- 🏠 **수원역** 친구 → 출발지: 늦어도 **23:37**에 정자역에서 출발 (타는 곳까지 도보 1분)" in text
        assert "    - 🚇 수인.분당선 정자역 **23:38** 열차 (고색행)" in text
        assert "- 🏠 **스타필드시티 위례** 친구 → 강남역: 늦어도 **00:02**에 정자역에서 출발" in text
        assert "    - 🚌 740번 강남역9번출구 **약 00:04 (추정)**" in text
        assert "📅 평일 시간표 기준" in text
        assert "경로는 평소 기준이라 밤늦게는 다를 수 있어요" in text
        assert "💡 '막차로 꼭 도착해야 하는 곳'을 지하철역으로 정하면 더 정확해요." in text
        # 기준이 된 수원역 친구는 지하철만 타니까 버스 경고는 없어요
        assert "버스 막차는 실제와 다를 수 있어요" not in all_text(at)

        # 토요일로 바꾸면 버튼을 다시 누르지 않아도 토요일 시간표로 다시 계산해요 (수원 23:27 열차)
        at = at.radio(key="day_type").set_value("saturday").run()
        assert not at.exception, at.exception
        assert "이 모임은 23:16까지 놀 수 있어요 (수원역 친구 기준)" in all_success(at)
        assert "📅 토요일 시간표 기준" in all_text(at)

        # 목표 지점을 바꾸면 옛 결과는 숨기고 다시 누르라고 안내해요
        goals(at)[0].input("")
        at = at.run()
        assert "장소나 귀가 목표 지점이 바뀌었어요" in all_text(at)
        assert "이 모임은" not in all_success(at)

    assert transit.read_json(usage, {})["count"] == 0  # ODsay 0건


def test_last_train_bus_warning():
    """
    [실제 데이터] 위례 친구(수인분당선 → 3217번 버스)가 모임 종료 기준이면,
    버스 막차 경고와 카카오맵 버스 노선 링크가 나오고, 막차 값이 하나뿐인 3217번은 이른 쪽 해석을 써야 해요.
    """
    cache, timetable, usage = seeded_last_train_files()
    with mock.patch("transit.CACHE_PATH", cache), mock.patch("transit.USAGE_PATH", usage), \
            mock.patch("last_train.TIMETABLE_CACHE_PATH", timetable), \
            mock.patch("recommend.build_travel_table", mock.Mock(return_value=JEONGJA_TABLE)):
        at = click(type_places(open_app(), ["스타필드시티 위례", "수원역"]), "약속 장소 추천받기")
        at = click(at, "🌙 막차 확인하기")  # 두 친구 모두 목표 지점은 빈칸 → 출발지까지
        assert not at.exception, at.exception
        text = all_text(at)

        # 3217번: ODsay 막차 23:45 하나뿐 → 회차점 기준 해석(23:45 - 80분) 22:25를 써요 (네이버 실제 22:45)
        assert "    - 🚌 3217번 복정역환승센터3번승강장 **약 22:25 (추정 · 확인 필요)**" in text
        summary = next(box.value for box in at.success if "이 모임은" in box.value)
        assert summary.endswith("(스타필드시티 위례 친구 기준)"), summary

        warning = next(box for box in at.warning if "버스 막차는" in box.value)
        assert (warning.value, warning.icon) == ("버스 막차는 실제와 다를 수 있어요. 버스 시간표를 꼭 확인하세요.", "⚠️")
        link = f"[🚌 카카오맵에서 3217번 버스 시간표 보기](https://map.kakao.com/?q={quote('3217번 버스')})"
        assert link in text

    assert transit.read_json(usage, {})["count"] == 0  # ODsay 0건 (링크는 주소만 만들어요)


def meeting_summary(at):
    """화면의 "이 모임은 ○○:○○까지 놀 수 있어요 (○○ 친구 기준)" 문장 (없으면 None)"""
    return next((box.value for box in at.success if "이 모임은" in box.value), None)


def test_video_scenario():
    """
    [영상 핵심 시나리오 · 결과가 바뀌면 안 돼요] 스타필드시티 위례 + 수원역 → 1위 정자역
      - 위례 친구 목표 = 복정역: 평일 23:24 (위례 친구 기준), 토요일 23:16 (수원역 친구 기준)
      - 위례 친구 목표 = 집(빈칸): 평일 21:43 (3217번 버스 → 버스 경고)
    """
    cache, timetable, usage = seeded_last_train_files()
    with mock.patch("transit.CACHE_PATH", cache), mock.patch("transit.USAGE_PATH", usage), \
            mock.patch("last_train.TIMETABLE_CACHE_PATH", timetable), \
            mock.patch("recommend.build_travel_table", mock.Mock(return_value=JEONGJA_TABLE)):
        at = type_places(open_app(), ["스타필드시티 위례", "수원역"])
        at = click(at, "약속 장소 추천받기")
        assert at.toggle(key="test_mode").value is True  # 테스트 모드 그대로

        # 1) 위례 친구 목표 = 복정역, 평일
        goals(at)[0].input("복정역")
        at = click(at.run(), "🌙 막차 확인하기")
        assert not at.exception, at.exception
        assert meeting_summary(at) == "이 모임은 23:24까지 놀 수 있어요 (스타필드시티 위례 친구 기준)"
        text = all_text(at)
        assert "    - 🚇 수인.분당선 정자역 **23:35** 열차 (왕십리행)" in text  # 23:35 - 도보 1분 - 여유 10분
        assert "버스 막차는 실제와 다를 수 있어요" not in text  # 지하철만 타니까 버스 경고 없음

        # 2) 토요일: 위례 23:41 열차가 평일보다 늦고, 수원 23:27이 더 일러서 기준 친구가 바뀌어요
        at = at.radio(key="day_type").set_value("saturday").run()
        assert meeting_summary(at) == "이 모임은 23:16까지 놀 수 있어요 (수원역 친구 기준)"

        # 3) 위례 친구 목표 = 집(빈칸), 평일 → 3217번 버스 때문에 21:43, 버스 경고
        at = at.radio(key="day_type").set_value("weekday").run()
        goals(at)[0].input("")
        at = click(at.run(), "🌙 막차 확인하기")
        assert not at.exception, at.exception
        assert meeting_summary(at) == "이 모임은 21:43까지 놀 수 있어요 (스타필드시티 위례 친구 기준)"
        assert "버스 막차는 실제와 다를 수 있어요. 버스 시간표를 꼭 확인하세요." in [w.value for w in at.warning]

    assert transit.read_json(usage, {})["count"] == 0  # 전부 메모장으로 계산 (ODsay 0건)


def test_last_train_call_count_and_bad_goal():
    """테스트 모드를 끄면 누르기 전에 필요한 ODsay 건수를 보여주고, 못 찾은 목표 지점이 있으면 안내해야 해요."""
    fake_cache, fake_usage = empty_cache_files()
    timetable = os.path.join(os.path.dirname(fake_cache), "timetable.json")
    with mock.patch("transit.CACHE_PATH", fake_cache), mock.patch("transit.USAGE_PATH", fake_usage), \
            mock.patch("last_train.TIMETABLE_CACHE_PATH", timetable), \
            mock.patch("recommend.build_travel_table", mock.Mock(return_value=JEONGJA_TABLE)):
        at = open_app()
        at = at.toggle(key="test_mode").set_value(False).run()
        at = click(type_places(at, ["스타필드시티 위례", "수원역"]), "약속 장소 추천받기")
        # 귀갓길이 저장되지 않은 친구 2명 → (경로 1 + 시간표 최대 2) × 2 = 최대 6건
        assert "ODsay 최대 6건이 필요해요 (오늘 남은 횟수 30건)" in all_text(at)

        goals(at)[1].input("ㅁㄴㅇㄹ존재하지않는곳")
        at = at.run()
        assert "찾지 못한 '막차로 꼭 도착해야 하는 곳'이 있어요" in all_text(at)
        assert not any(b.label == "🌙 막차 확인하기" for b in at.button)


# ── 데모 모드 (API 키 없음 → demo_data/만 사용) ──
def demo_mode_patches(usage):
    """
    키가 없는 컴퓨터처럼 만들고, 데모 모드가 바꾸는 값들(메모장 위치 등)은 테스트가 끝나면 원래대로 돌려놔요.
    usage: 임시 기록부 경로 (ODsay를 몇 번 불렀는지 확인용)
    """
    return [
        mock.patch("geocode.KAKAO_REST_API_KEY", None), mock.patch("transit.ODSAY_API_KEY", None),
        mock.patch.object(transit, "CACHE_PATH", transit.CACHE_PATH),
        mock.patch.object(last_train, "TIMETABLE_CACHE_PATH", last_train.TIMETABLE_CACHE_PATH),
        mock.patch.object(last_train, "CHECK_EXPIRY", last_train.CHECK_EXPIRY),
        mock.patch("transit.USAGE_PATH", usage),
    ]


def read_demo_files():
    """demo_data/ 폴더의 파일 내용을 모두 읽어요. (테스트 전후로 바뀌지 않았는지 비교용)"""
    folder = "demo_data"
    return {name: open(os.path.join(folder, name), encoding="utf-8").read() for name in sorted(os.listdir(folder))}


def test_demo_mode_full_example():
    """
    [데모 모드] 키가 없으면 테스트 모드가 켜진 채로 잠기고, demo_data만으로 예시 전체가 실행돼야 해요.
    (시간표가 30일 넘게 지난 날이어도 멈추지 않아야 해요)
    """
    _, usage = empty_cache_files()
    before = read_demo_files()
    with ExitStack() as stack:
        for patch in demo_mode_patches(usage):
            stack.enter_context(patch)
        stack.enter_context(mock.patch("last_train.today_kst", lambda: "2027-06-01"))  # 저장 후 7개월 뒤

        at = open_app()
        assert at.toggle(key="test_mode").value is True and at.toggle(key="test_mode").disabled
        assert "데모 모드" in all_text(at)

        at = click(at, "저장된 예시 불러오기")
        assert [t.value for t in origins(at)] == ["스타필드시티 위례", "수원역"]

        at = click(at, "약속 장소 추천받기")
        assert not at.exception, at.exception
        assert "### 🏆 1위 · 정자역" in all_text(at)

        # 위례 친구 목표 = 복정역 → 평일 23:24 (영상 시나리오와 같은 결과)
        goals(at)[0].input("복정역")
        at = click(at.run(), "🌙 막차 확인하기")
        assert not at.exception, at.exception
        assert meeting_summary(at) == "이 모임은 23:24까지 놀 수 있어요 (스타필드시티 위례 친구 기준)"

        # 위례 친구 목표 = 집(빈칸) → 3217번 버스 때문에 21:43
        goals(at)[0].input("")
        at = click(at.run(), "🌙 막차 확인하기")
        assert meeting_summary(at) == "이 모임은 21:43까지 놀 수 있어요 (스타필드시티 위례 친구 기준)"

    assert transit.read_json(usage, {})["count"] == 0  # ODsay 0건
    assert read_demo_files() == before  # demo_data는 읽기만 하고 바꾸지 않아요


def test_demo_mode_unknown_place():
    """[데모 모드] 예시에 없는 장소는 카카오를 부르지 않고, 쓸 수 있는 장소 이름을 안내해야 해요."""
    _, usage = empty_cache_files()
    with ExitStack() as stack:
        for patch in demo_mode_patches(usage):
            stack.enter_context(patch)
        at = type_places(open_app(), ["강남역", "수원역"])  # 강남역은 데모 데이터에 없어요

    assert not at.exception, at.exception
    warning = next(w.value for w in at.warning if "강남역" in w.value)
    assert "데모 모드에서는 이 장소만 쓸 수 있어요: 스타필드시티 위례, 수원역, 복정역" in warning


# 이 파일을 직접 실행하면 위의 테스트들을 차례로 실행합니다.
if __name__ == "__main__":
    usage_before = transit.get_today_usage()

    tests = [
        test_first_screen, test_add_friend_max_3, test_remove_middle_friend, test_remove_then_add,
        test_empty_input, test_result_cards_and_switch_criterion, test_travel_bars, test_same_winner_message,
        test_friend_name_is_escaped, test_choose_among_results, test_departure_times, test_kakao_map_link,
        test_place_not_found, test_daily_limit_reached, test_test_mode_without_saved_result,
        test_load_saved_example, test_load_saved_example_none, test_last_train_flow, test_last_train_bus_warning,
        test_video_scenario,
        test_last_train_call_count_and_bad_goal,
        test_demo_mode_full_example, test_demo_mode_unknown_place,
    ]
    # 모든 테스트 동안 출발지 검색은 가짜로 바꾸고, 인터넷 요청(카카오·ODsay)은 막아둡니다.
    # API 키도 가짜로 넣어둬요. (키가 없는 컴퓨터에서 돌려도 데모 모드가 아닌 보통 화면을 테스트하도록.
    #  데모 모드 테스트는 키를 다시 빼서 확인해요)
    with mock.patch("geocode.search_places", fake_search), mock.patch("requests.get", internet_forbidden), \
            mock.patch("geocode.KAKAO_REST_API_KEY", "FAKE_KEY"), mock.patch("transit.ODSAY_API_KEY", "FAKE_KEY"):
        for test in tests:
            test()  # 실패하면 여기서 AssertionError가 나며 멈춰요
            print(f"✅ {test.__name__}: {test.__doc__.strip().splitlines()[0]}")

    usage_after = transit.get_today_usage()
    assert usage_after == usage_before, "ODsay 사용량이 바뀌었어요!"
    print(f"\n🎉 테스트 {len(tests)}개 모두 통과! (카카오·ODsay 실제 호출 0번, 사용량 {usage_after}/30건 그대로)")
