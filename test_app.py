# test_app.py
# 역할: app.py 화면을 "로봇"이 대신 눌러보는 자동 테스트입니다.
#       (Streamlit의 AppTest: 브라우저 없이 입력 → 버튼 클릭 → 화면 내용 확인)
#
# ⚠️ 이 테스트는 ODsay를 절대 부르지 않아요.
#    - ODsay 주소로 가는 요청은 "부르면 즉시 테스트 실패"로 막아두었어요.
#    - 추천 결과 화면은 "가짜 이동시간 표"로 확인해요. (내 컴퓨터의 캐시에 기대지 않아서 어디서나 똑같이 동작)
#    카카오(장소 → 좌표)는 "없는 장소"·"한도 초과" 테스트에서만 실제로 부릅니다.

import os  # 파일 경로를 다루기 위한 도구
import tempfile  # 테스트용 임시 폴더를 만들기 위한 도구
from unittest import mock  # 진짜 함수를 가짜로 바꿔치기하는 도구

import requests  # 진짜 우체부 (카카오 호출에는 그대로 써요)
from streamlit.testing.v1 import AppTest  # Streamlit 화면 자동 테스트 도구

import transit

real_get = requests.get  # 바꿔치기하기 전에 진짜 우체부를 따로 챙겨둡니다.

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


def odsay_forbidden(url, *args, **kwargs):
    """
    주소가 ODsay면 바로 테스트를 실패시키고, 그 밖의 주소(카카오)는 진짜 우체부에게 넘기는 '가짜 우체부'
    (requests는 카카오와 ODsay가 함께 쓰는 도구라서, ODsay만 골라서 막아야 해요)
    """
    if "odsay.com" in url:
        raise AssertionError("테스트 중에 ODsay를 부르려고 했어요!")
    return real_get(url, *args, **kwargs)


def open_app():
    """app.py를 열고 첫 화면을 그립니다."""
    at = AppTest.from_file("app.py", default_timeout=30)
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
    assert len(at.text_input) == 2
    assert len(remove_buttons(at)) == 0  # 2명일 땐 ✕ 숨김
    assert at.radio[0].value == "fair"
    assert at.radio[0].options == ["⚖️ 공평하게", "⚡ 빠르게"]  # 기준은 2개
    assert f"오늘 ODsay 사용량: {transit.get_today_usage()}/30건" in text


def test_add_friend_max_3():
    """'+ 친구 추가'로 3칸까지만 늘어나고, 3칸이 되면 추가 버튼이 꺼지고 ✕가 생겨야 해요."""
    at = open_app()
    at = click(at, "+ 친구 추가")
    assert len(at.text_input) == 3
    assert len(remove_buttons(at)) == 3
    add_button = next(b for b in at.button if b.label == "+ 친구 추가")
    assert add_button.disabled


def test_remove_middle_friend():
    """가운데 친구를 지워도, 남은 친구들의 입력값이 밀리거나 섞이지 않아야 해요."""
    at = open_app()
    at = click(at, "+ 친구 추가")
    at.text_input[0].input("강남역")
    at.text_input[1].input("홍대입구역")
    at.text_input[2].input("수원역")
    at = at.run()

    at = remove_buttons(at)[1].click().run()  # 두 번째 친구(홍대입구역)의 ✕

    assert [t.value for t in at.text_input] == ["강남역", "수원역"]
    assert [t.label for t in at.text_input] == ["친구 1 출발지", "친구 2 출발지"]  # 번호는 다시 1, 2
    assert len(remove_buttons(at)) == 0  # 2명이 되면 ✕ 숨김


def test_remove_then_add():
    """지운 뒤 다시 추가하면, 새 칸은 빈칸이어야 해요. (지운 친구의 글자가 되살아나면 안 돼요)"""
    at = open_app()
    at = click(at, "+ 친구 추가")
    at.text_input[2].input("잠실역")
    at = at.run()
    at = remove_buttons(at)[2].click().run()  # 세 번째 친구 삭제
    at = click(at, "+ 친구 추가")  # 다시 추가

    assert len(at.text_input) == 3
    assert at.text_input[2].value == ""


def test_empty_input():
    """빈 칸이 있으면 친절하게 안내해야 해요."""
    at = open_app()
    at.text_input[0].input("강남역")
    at = click(at, "약속 장소 추천받기")
    assert "비어 있는 출발지 칸이 있어요" in all_text(at)
    assert not at.exception


def test_result_cards_and_switch_criterion():
    """결과 카드(경로 요약 + 자세히 보기) → 기준을 바꿔도 이동시간 표를 다시 만들지 않아야 해요."""
    fake_build = mock.Mock(return_value=FAKE_TABLE)
    with mock.patch("recommend.build_travel_table", fake_build):
        at = open_app()
        at.text_input[0].input("강남역")
        at.text_input[1].input("수원역")
        at = click(at, "약속 장소 추천받기")
        assert not at.exception, at.exception

        text = all_text(at)
        assert "🏆 1위 · 금정역" in text  # fair 기준 1위
        assert "40분 · 환승 1" in text  # 막대 옆 글자
        assert "**강남역** · 강남 → [2호선]" in text  # 친구별 경로 요약
        assert "강남 → [2호선] → 사당 (환승) → [4호선] → 금정" in text  # 카드의 경로 요약
        assert "🚇 2호선 강남 → 사당 (4개 역, 9분)" in text  # 펼치기 안의 자세한 경로
        assert at.expander[0].label == "자세한 경로 보기"

        # 카드는 3위까지만, 4~5위는 스위치를 켜야 보여요
        assert "4위 · " not in text
        at = at.toggle(key="show_others").set_value(True).run()
        assert "#### 4위 · " in all_text(at)

        # 기준을 fast로 바꾸면 사당이 1위, 그리고 이동시간 표는 다시 만들지 않음
        at = at.radio[0].set_value("fast").run()
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
        at = open_app()
        for box, name in zip(at.text_input, names):
            box.input(name)
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


def test_place_not_found():
    """없는 장소를 넣으면 친절하게 안내해야 해요. (카카오만 부르고 ODsay는 안 불러요)"""
    at = open_app()
    at.text_input[0].input("강남역")
    at.text_input[1].input("ㅁㄴㅇㄹ존재하지않는곳")
    at = click(at, "약속 장소 추천받기")
    assert not at.exception, at.exception
    assert "'ㅁㄴㅇㄹ존재하지않는곳'을(를) 찾을 수 없어요" in all_text(at)


def test_daily_limit_reached():
    """오늘 30건을 다 썼으면, ODsay를 부르지 않고 한도 안내를 해야 해요."""
    folder = tempfile.mkdtemp()
    fake_usage = os.path.join(folder, "usage.json")
    fake_cache = os.path.join(folder, "cache.json")  # 빈 메모장 → 무조건 ODsay가 필요한 상황
    transit.write_json(fake_usage, {"date": transit.today_kst(), "count": 30})

    with mock.patch("transit.USAGE_PATH", fake_usage), mock.patch("transit.CACHE_PATH", fake_cache):
        at = open_app()
        at.text_input[0].input("홍대입구역")
        at.text_input[1].input("잠실역")
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
        test_friend_name_is_escaped, test_place_not_found, test_daily_limit_reached,
    ]
    # 모든 테스트 동안 ODsay 우체부를 막아둡니다.
    with mock.patch("transit.requests.get", odsay_forbidden):
        for test in tests:
            test()  # 실패하면 여기서 AssertionError가 나며 멈춰요
            print(f"✅ {test.__name__}: {test.__doc__.strip().splitlines()[0]}")

    usage_after = transit.get_today_usage()
    assert usage_after == usage_before, "ODsay 사용량이 바뀌었어요!"
    print(f"\n🎉 테스트 {len(tests)}개 모두 통과! (ODsay 실제 호출 0번, 사용량 {usage_after}/30건 그대로)")
