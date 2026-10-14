# test_transit.py
# 역할: transit.py의 캐시, 호출 한도, 오류 안내를 "가짜 답장"으로 테스트합니다.
#
# ⚠️ 이 테스트는 ODsay를 한 번도 실제로 부르지 않아요!
#    requests.get(진짜 우체부)을 가짜 우체부로 바꿔치기해서, 정해둔 가짜 답장만 돌려받습니다.
#    또 임시 폴더의 파일을 쓰기 때문에, 진짜 메모장(캐시)과 기록부는 건드리지 않아요.

import os  # 파일 경로를 다루기 위한 도구
import tempfile  # 테스트용 임시 폴더를 만들기 위한 도구
from unittest import mock  # 진짜 함수를 가짜로 바꿔치기하는 도구

import requests  # 가짜 "인터넷 오류"를 만들 때 쓰는 도구

import transit  # 테스트할 파일

START = (37.49809, 127.02800)  # 테스트용 출발 좌표 (강남역)
END = (37.37247, 126.94347)  # 테스트용 도착 좌표 (금정역)

# ── 가짜 답장들 ──
# 정상 답장 (실제 응답을 줄인 모양: 2호선 → 4호선, 40분)
FAKE_OK = {"result": {"path": [
    {"info": {"totalTime": 55, "payment": 1850, "busTransitCount": 1, "subwayTransitCount": 1},
     "subPath": [
         {"trafficType": 2, "sectionTime": 16, "stationCount": 8, "startName": "강남역9번출구", "endName": "이수역",
          "lane": [{"busNo": "040"}, {"busNo": "N64"}]},
     ]},
    {"info": {"totalTime": 40, "payment": 1850, "busTransitCount": 0, "subwayTransitCount": 2},
     "subPath": [
         {"trafficType": 3, "sectionTime": 1, "distance": 37},
         {"trafficType": 1, "sectionTime": 9, "stationCount": 4, "startName": "강남", "endName": "사당",
          "lane": [{"name": "수도권 2호선"}]},
         {"trafficType": 3, "sectionTime": 3, "distance": 0},
         {"trafficType": 1, "sectionTime": 23, "stationCount": 10, "startName": "사당", "endName": "금정",
          "lane": [{"name": "수도권 4호선"}]},
         {"trafficType": 3, "sectionTime": 1, "distance": 14},
     ]},
]}}

# FAKE_OK에서 가장 빠른 경로(40분)를 정리하면 이렇게 나와야 해요
EXPECTED_OK = {
    "time_min": 40, "transfers": 1, "fare": 1850,
    "segments": [
        {"type": "walk", "minutes": 1, "distance_m": 37},
        {"type": "subway", "line": "2호선", "start": "강남", "end": "사당", "minutes": 9, "stations": 4},
        {"type": "walk", "minutes": 3, "distance_m": 0},
        {"type": "subway", "line": "4호선", "start": "사당", "end": "금정", "minutes": 23, "stations": 10},
        {"type": "walk", "minutes": 1, "distance_m": 14},
    ],
}
# 틀린 API 키 (오늘 실제로 받아본 오류 응답과 똑같은 모양)
FAKE_WRONG_KEY = {"error": [{"code": "500", "message": "[ApiKeyAuthFailed] ApiKey authentication failed."}]}
# 너무 가까움
FAKE_TOO_CLOSE = {"error": {"code": "-98", "msg": "출, 도착지가 700m이내입니다."}}


def fake_postman(answer):
    """가짜 우체부를 만듭니다. 누가 요청하든 answer를 답장으로 돌려줘요."""
    fake_response = mock.Mock()
    fake_response.json.return_value = answer
    return mock.Mock(return_value=fake_response)


def fresh_files():
    """매 테스트마다 빈 임시 폴더를 만들어, 메모장/기록부 파일 위치를 그쪽으로 바꿉니다."""
    folder = tempfile.mkdtemp()
    transit.CACHE_PATH = os.path.join(folder, "cache.json")
    transit.USAGE_PATH = os.path.join(folder, "usage.json")


def ask(postman):
    """가짜 우체부를 써서 get_transit_info를 부르고, (결과 또는 오류 메시지)를 돌려줍니다."""
    with mock.patch("transit.requests.get", postman), mock.patch("transit.ODSAY_API_KEY", "FAKE_KEY"):
        try:
            return transit.get_transit_info(START, END)
        except ValueError as error:
            return str(error)


# ─────────────────────────────────────────────
# 테스트들
# ─────────────────────────────────────────────

def test_cache():
    """같은 구간을 두 번 물으면, ODsay는 1번만 불러야 해요."""
    fresh_files()
    postman = fake_postman(FAKE_OK)

    first = ask(postman)
    second = ask(postman)

    assert first == EXPECTED_OK, first
    assert second == first  # 두 번째도 같은 결과
    assert postman.call_count == 1  # 우체부는 딱 1번만 일함
    assert transit.get_today_usage() == 1  # 기록부에도 1번만 적힘


def test_segments_parsed():
    """구간 정보: 호선 이름에서 "수도권 "을 빼고, 버스는 여러 번호를 함께 보여줘야 해요."""
    result = transit.parse_transit_response(FAKE_OK)
    assert result == EXPECTED_OK, result

    bus = transit.parse_segments(FAKE_OK["result"]["path"][0]["subPath"])[0]
    assert bus["type"] == "bus" and bus["line"] == "040/N64번", bus


def test_old_cache_without_segments():
    """경로 정보가 없는 예전 메모는 '없는 것'으로 보고 다시 물어본 뒤, 경로 정보까지 저장해야 해요."""
    fresh_files()
    old_memo = {"time_min": 40, "transfers": 1, "fare": 1850}  # 예전 모양 (segments 없음)
    transit.write_json(transit.CACHE_PATH, {transit.make_cache_key(START, END): old_memo})
    assert not transit.is_cached(START, END)  # 호출 수 미리 세기에서도 "필요함"으로 셈

    postman = fake_postman(FAKE_OK)
    result = ask(postman)

    assert postman.call_count == 1  # 다시 물어봄
    assert result == EXPECTED_OK
    assert transit.is_cached(START, END)  # 이제는 경로 정보까지 저장됨


def test_wrong_key():
    """틀린 키 → 한국어 안내. 그리고 메모장에 적지 않아야 해요(키를 고치면 다시 물어봐야 하니까)."""
    fresh_files()
    postman = fake_postman(FAKE_WRONG_KEY)

    message = ask(postman)
    ask(postman)  # 한 번 더 물어보기

    assert "API 키 인증에 실패" in message, message
    assert postman.call_count == 2  # 메모장에 없으니 다시 물어봄


def test_too_close():
    """너무 가까움 → 안내. 그리고 메모장에 적어서 다음엔 ODsay를 부르지 않아야 해요."""
    fresh_files()
    postman = fake_postman(FAKE_TOO_CLOSE)

    first = ask(postman)
    second = ask(postman)

    assert "너무 가까워요" in first, first
    assert second == first
    assert postman.call_count == 1  # 두 번째는 메모장에서 꺼냄


def test_daily_limit():
    """오늘 이미 30번 불렀으면, ODsay를 부르지 않고 한도 안내를 해야 해요."""
    fresh_files()
    transit.write_json(transit.USAGE_PATH, {"date": transit.today_kst(), "count": 30})
    postman = fake_postman(FAKE_OK)

    message = ask(postman)

    assert "오늘 대중교통 조회 한도를 다 썼어요" in message, message
    assert postman.call_count == 0  # 우체부는 한 번도 안 나감


def test_new_day():
    """어제 30번 썼어도, 오늘은 0부터 다시 세야 해요."""
    fresh_files()
    transit.write_json(transit.USAGE_PATH, {"date": "2000-01-01", "count": 30})
    postman = fake_postman(FAKE_OK)

    result = ask(postman)

    assert result["time_min"] == 40, result
    assert transit.get_today_usage() == 1  # 오늘 첫 호출


def test_network_error():
    """인터넷이 끊겨도 프로그램이 멈추지 않고 안내해야 해요."""
    fresh_files()
    postman = mock.Mock(side_effect=requests.ConnectionError())

    message = ask(postman)

    assert "인터넷 연결을 확인" in message, message


# 이 파일을 직접 실행하면 위의 테스트들을 차례로 실행합니다.
if __name__ == "__main__":
    tests = [test_cache, test_segments_parsed, test_old_cache_without_segments, test_wrong_key, test_too_close, test_daily_limit, test_new_day, test_network_error]
    for test in tests:
        test()  # 실패하면 여기서 AssertionError가 나며 멈춰요
        print(f"✅ {test.__name__}: {test.__doc__.strip().splitlines()[0]}")
    print(f"\n🎉 테스트 {len(tests)}개 모두 통과! (ODsay 실제 호출 0번)")
