# test_app.py
# 역할: app.py 화면을 "로봇"이 대신 눌러보는 자동 테스트입니다.
#       (Streamlit의 AppTest: 브라우저 없이 입력 → 버튼 클릭 → 화면 내용 확인)
#
# ⚠️ 이 테스트는 ODsay를 절대 부르지 않아요.
#    ODsay 우체부(requests.get)를 "부르면 즉시 테스트 실패"로 바꿔치기해두었어요.
#    카카오(장소 → 좌표)는 실제로 부릅니다.

import os  # 파일 경로를 다루기 위한 도구
import tempfile  # 테스트용 임시 폴더를 만들기 위한 도구
from unittest import mock  # 진짜 함수를 가짜로 바꿔치기하는 도구

import requests  # 진짜 우체부 (카카오 호출에는 그대로 써요)
from streamlit.testing.v1 import AppTest  # Streamlit 화면 자동 테스트 도구

import transit

real_get = requests.get  # 바꿔치기하기 전에 진짜 우체부를 따로 챙겨둡니다.


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


# ─────────────────────────────────────────────
# 테스트들
# ─────────────────────────────────────────────

def test_first_screen():
    """처음 화면: 제목, 입력칸 2개, 기본 기준 care, 사용량 표시"""
    at = open_app()
    text = all_text(at)
    assert "🚇 오늘은여기서" in text
    assert "친구들 모두에게 공정한 약속 장소 찾기" in text
    assert len(at.text_input) == 2
    assert at.radio[0].value == "care"
    assert f"오늘 ODsay 사용량: {transit.get_today_usage()}/30건" in text


def test_add_friend_max_3():
    """'+ 친구 추가'로 3칸까지만 늘어나고, 3칸이 되면 버튼이 꺼져야 해요."""
    at = open_app()
    at = click(at, "+ 친구 추가")
    assert len(at.text_input) == 3
    add_button = next(b for b in at.button if b.label == "+ 친구 추가")
    assert add_button.disabled


def test_empty_input():
    """빈 칸이 있으면 친절하게 안내해야 해요."""
    at = open_app()
    at.text_input[0].input("강남역")
    at = click(at, "약속 장소 추천받기")
    assert "비어 있는 출발지 칸이 있어요" in all_text(at)
    assert not at.exception


def test_gangnam_suwon_and_switch_criterion():
    """강남역+수원역 추천 (캐시 사용) → 기준을 바꿔도 ODsay를 부르지 않고 순위만 바뀌어야 해요."""
    at = open_app()
    at.text_input[0].input("강남역")
    at.text_input[1].input("수원역")
    at = click(at, "약속 장소 추천받기")
    assert not at.exception, at.exception

    text = all_text(at)
    assert "🏆 1위 · 금정역" in text  # care 기준 1위
    assert "**강남역** → 40분(환승 1)" in text
    assert "**수원역** → 19분(환승 0)" in text

    # 기준을 fast로 바꾸면 사당이 1위 (ODsay 우체부는 막혀 있으니, 불렀다면 여기서 실패해요)
    at = at.radio[0].set_value("fast").run()
    assert not at.exception, at.exception
    assert "🏆 1위 · 사당역" in all_text(at)

    # 출발지를 고치면 옛날 결과는 숨기고 안내
    at.text_input[1].input("판교역")
    at = at.run()
    text = all_text(at)
    assert "출발지가 바뀌었어요" in text
    assert "🏆" not in text


def test_place_not_found():
    """없는 장소를 넣으면 친절하게 안내해야 해요."""
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
    transit.write_json(fake_usage, {"date": transit.today_kst(), "count": 30})

    # 임시 기록부(30건)를 쓰도록 바꿔치기. 홍대입구/잠실은 메모장에 없어서 원래라면 ODsay가 필요해요.
    with mock.patch("transit.USAGE_PATH", fake_usage):
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
        test_first_screen, test_add_friend_max_3, test_empty_input,
        test_gangnam_suwon_and_switch_criterion, test_place_not_found, test_daily_limit_reached,
    ]
    # 모든 테스트 동안 ODsay 우체부를 막아둡니다.
    with mock.patch("transit.requests.get", odsay_forbidden):
        for test in tests:
            test()  # 실패하면 여기서 AssertionError가 나며 멈춰요
            print(f"✅ {test.__name__}: {test.__doc__.strip().splitlines()[0]}")

    usage_after = transit.get_today_usage()
    assert usage_after == usage_before, "ODsay 사용량이 바뀌었어요!"
    print(f"\n🎉 테스트 {len(tests)}개 모두 통과! (ODsay 실제 호출 0번, 사용량 {usage_after}/30건 그대로)")
