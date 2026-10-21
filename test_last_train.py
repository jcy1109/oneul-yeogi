# test_last_train.py
# 역할: last_train.py의 막차 계산을 "가짜 데이터"로 테스트합니다.
#
# ⚠️ 이 테스트는 ODsay를 한 번도 실제로 부르지 않아요!
#    - test_data/ 폴더의 답장은 2026-10-21에 실제로 받은 ODsay 답장을 줄인 것이에요. (API 키·개인정보 없음)
#      정자역·강남역 지하철 시간표, 740번·3217번 버스 노선, 정자→수원 / 강남→홍대입구 길찾기
#      (정자→위례 귀갓길은 실제 답장을 우리 앱 모양으로 정리해서 메모장에 저장된 것이에요)
#    - 특별한 경우(갈래 노선, 순환선, 환승 3번 등)는 작은 가짜 경로를 직접 만들어서 확인해요.
#    - 메모장 파일은 임시 폴더를 써서, 진짜 메모장과 기록부는 건드리지 않아요.

import json  # test_data의 답장 파일을 읽기 위한 도구
import os  # 파일 경로를 다루기 위한 도구
import tempfile  # 테스트용 임시 폴더를 만들기 위한 도구
from unittest import mock  # 진짜 함수를 가짜로 바꿔치기하는 도구

import last_train
import transit
from last_train import clock_text, plan_route, to_minutes

TEST_DATA = "test_data"
JEONGJA = (37.3661737923199, 127.108097457244)  # 정자역 (공공장소)
SUWON = (37.26579, 127.00009)  # 수원역 (공공장소)


def load(name):
    """test_data 폴더의 실제 답장 파일을 읽어요."""
    with open(os.path.join(TEST_DATA, name), encoding="utf-8") as f:
        return json.load(f)


def fresh_files(seed=True):
    """
    임시 폴더에 빈 메모장과 기록부를 만들어요.
    seed=True면 실제 답장(정자·강남 시간표, 740번 버스)을 시간표 메모장에 넣어둬요.
    """
    folder = tempfile.mkdtemp()
    transit.CACHE_PATH = os.path.join(folder, "cache.json")
    transit.USAGE_PATH = os.path.join(folder, "usage.json")
    last_train.TIMETABLE_CACHE_PATH = os.path.join(folder, "timetable.json")
    if seed:
        last_train.save_timetable("subway", 1530, load("subway_schedule_1530_jeongja_suinbundang.json"))
        last_train.save_timetable("subway", 222, load("subway_schedule_222_gangnam_line2.json"))
        last_train.save_timetable("bus", 1273, load("bus_lane_1273_bus740.json"))
        last_train.save_timetable("bus", 1018, load("bus_lane_1018_bus3217.json"))


def real_route(name):
    """실제 길찾기 답장을 우리 앱의 경로 모양으로 바꿔요. (가장 빠른 경로)"""
    return transit.parse_transit_response(load(name))


def walk(minutes):
    """가짜 도보 구간"""
    return {"type": "walk", "minutes": minutes, "distance_m": minutes * 70}


def subway(line, stops, minutes, start_id, way_code=2):
    """가짜 지하철 구간 (stops: 타는 역 ~ 내리는 역)"""
    return {"type": "subway", "line": line, "start": stops[0], "end": stops[-1], "minutes": minutes,
            "stations": len(stops) - 1, "start_id": start_id, "end_id": None, "way_code": way_code, "stops": stops}


def put_subway_timetable(code, down_trains, day_type="weekday"):
    """가짜 지하철 시간표를 메모장에 넣어요. down_trains: [("23:30", "인천", 0), ...]"""
    schedules = {day: {"up": [], "down": []} for day in last_train.SCHEDULE_KEYS}
    schedules[day_type]["down"] = [list(t) for t in down_trains]
    cache = transit.read_json(last_train.TIMETABLE_CACHE_PATH, {})
    cache[f"subway:{code}"] = {"saved": transit.today_kst(), "data": {"name": "", "line": "", "schedules": schedules}}
    transit.write_json(last_train.TIMETABLE_CACHE_PATH, cache)


def no_internet(*args, **kwargs):
    """ODsay를 부르려고 하면 바로 테스트를 실패시키는 가짜 함수"""
    raise AssertionError("테스트 중에 ODsay를 부르려고 했어요!")


# ─────────────────────────────────────────────
# 테스트들
# ─────────────────────────────────────────────

def test_time_helpers():
    """시각 도우미: "24:38"은 자정 넘은 시각, "00:30"도 밤의 연장으로 봐야 해요."""
    assert to_minutes("23:38") == 23 * 60 + 38
    assert to_minutes("24:38") == 24 * 60 + 38  # ODsay 시간표의 자정 넘은 시각
    assert to_minutes("00:30") == 24 * 60 + 30  # 혹시 이렇게 와도 "다음 날 0시 30분"
    assert to_minutes("05:44") == 5 * 60 + 44  # 첫차 시각은 그대로
    assert clock_text(24 * 60 + 21) == "00:21"
    assert clock_text(23 * 60 + 5) == "23:05"


def test_real_jeongja_to_suwon():
    """[실제 데이터] 정자 → 수원: 시간표 맨 끝의 24:22 죽전행이 아니라 23:38 고색행이 막차여야 해요."""
    fresh_files()
    route = real_route("path_jeongja_to_suwon.json")
    assert [s["type"] for s in route["segments"]] == ["walk", "subway", "walk"]

    result = plan_route(route, "weekday", offline=True)
    assert result["status"] == "ok", result
    leg = result["legs"][0]
    assert (clock_text(leg["depart"]), leg["terminus"]) == ("23:38", "고색")  # 죽전행(24:22)은 수원까지 안 가요
    assert result["walk_min"] == 1  # 정자역 안에서 타는 곳까지 1분
    assert clock_text(result["leave_by"]) == "23:37"  # 23:38 - 도보 1분

    # 토요일·휴일은 다른 시간표를 써요
    saturday = plan_route(route, "saturday", offline=True)
    assert clock_text(saturday["legs"][0]["depart"]) == "23:27"


def test_real_gangnam_line2_after_midnight():
    """[실제 데이터] 2호선 강남 → 홍대입구: 평일은 자정 넘은 00:21 홍대입구행, 토요일은 23:24여야 해요."""
    fresh_files()
    route = real_route("path_gangnam_to_hongdae.json")
    weekday = plan_route(route, "weekday", offline=True)
    # 24:33 신도림행, 24:46 서울대입구행은 홍대입구 앞에서 끝나서 못 타요
    assert (clock_text(weekday["legs"][0]["depart"]), weekday["legs"][0]["terminus"]) == ("00:21", "홍대입구")
    assert weekday["legs"][0]["depart"] == 24 * 60 + 21  # 계산은 24시를 넘는 분으로 해요

    saturday = plan_route(route, "saturday", offline=True)
    assert clock_text(saturday["legs"][0]["depart"]) == "23:24"


def test_real_bus_740_turning_point():
    """[실제 데이터] 740번: 강남역9번출구는 회차점(삼성역) 뒤라서 회차점 막차(24:00)로 추정해야 해요."""
    fresh_files()
    bus_path = load("path_gangnam_to_hongdae_bus_only.json")["result"]["path"][0]["subPath"]
    route = {"segments": transit.parse_segments(bus_path)}
    ride = route["segments"][1]
    assert (ride["start_id"], ride["bus_ids"]) == (157359, [1273])

    result = plan_route(route, "weekday", offline=True)
    leg = result["legs"][0]
    # 24:00 + 회차점부터 3,255m ÷ 시속 40km(4.9분 → 내림 4분) = 24:04
    # (기점 막차 22:40으로 계산했다면 23:20으로 44분이나 틀렸을 거예요)
    assert clock_text(leg["depart"]) == "00:04" and leg["estimated"]
    assert (leg["label"], leg["bus_no"]) == ("추정", "740")
    assert "**약 00:04 (추정)**" in last_train.leg_text(leg)


def test_real_bus_740_start_label():
    """[실제 데이터] 740번을 기점(덕은동종점, 0번 정류장)에서 타면 기점 막차 22:40 그대로, "(기점 막차)"로 표시해요."""
    fresh_files()
    ride = {"type": "bus", "line": "740번", "start": "덕은동종점", "minutes": 30, "start_id": 101691, "bus_ids": [1273]}
    result = plan_route({"segments": [ride]}, "weekday", offline=True)
    leg = result["legs"][0]
    assert (clock_text(leg["depart"]), leg["label"], leg["estimated"]) == ("22:40", "기점 막차", False)
    assert last_train.leg_text(leg) == "🚌 740번 덕은동종점 **22:40 (기점 막차)**"


def test_real_bus_3217_single_value():
    """
    [실제 데이터] 3217번은 막차 값이 23:45 하나뿐이에요. (네이버 확인: 복정역 출발 막차 22:45)
    두 해석 중 이른 쪽(23:45 - 회차점까지 19.8km ÷ 시속 15km = 22:25)을 쓰고, "(추정 · 확인 필요)"로 표시해야 해요.
    """
    fresh_files()
    route = load("route_jeongja_to_wirye.json")  # 정자 → [수인분당선] → 복정 → [3217번] → 위례
    result = plan_route(route, "weekday", offline=True)
    assert result["status"] == "ok", result
    subway_leg, bus_leg = result["legs"]

    # 버스: 해석 A(기점 기준) 23:45 + 0분 / 해석 B(회차점 기준) 23:45 - 80분 = 22:25 → 이른 쪽
    assert (clock_text(bus_leg["depart"]), bus_leg["label"]) == ("22:25", "추정 · 확인 필요")
    assert bus_leg["depart"] <= to_minutes("22:45")  # 네이버 실제 막차보다 이르거나 같아야 안전해요
    assert last_train.leg_text(bus_leg) == "🚌 3217번 복정역환승센터3번승강장 **약 22:25 (추정 · 확인 필요)**"

    # 지하철: 22:25 - 19분(이동) - 1분(환승 도보) = 22:05 이전의 마지막 왕십리 방향 열차
    assert subway_leg["depart"] <= to_minutes("22:05")
    assert last_train.has_bus(result)


def test_old_bus_memo_is_refetched():
    """기점 이름 등을 저장하기 전의 예전 버스 메모는 '없는 것'으로 보고 다시 물어봐야 해요."""
    fresh_files(seed=False)
    old = {"bus_no": "3217", "last": "23:45", "ep_last": None, "turning": 41, "interval": "12",
           "intervals": {}, "stations": [[5008839, 0]]}  # 예전 모양
    transit.write_json(last_train.TIMETABLE_CACHE_PATH, {"bus:1018": {"saved": transit.today_kst(), "data": old}})
    assert not last_train.is_timetable_cached("bus", 1018)


def test_bus_bound_minus_interval():
    """버스 정류장 막차보다 다음 구간이 더 일찍 끝나면, 그 시각에서 배차간격(12분)만큼 더 빼야 해요."""
    fresh_files()
    bus_path = load("path_gangnam_to_hongdae_bus_only.json")["result"]["path"][0]["subPath"]
    ride = transit.parse_segments(bus_path)[1]
    assert last_train.bus_departure(ride, to_minutes("23:30"), "weekday", offline=True) == (to_minutes("23:18"), "추정", "740")


def test_backward_two_rides():
    """버스 → 지하철 2구간: 지하철 막차에서 버스 이동시간과 갈아타는 도보 시간을 빼고 거꾸로 계산해야 해요."""
    fresh_files()
    bus_path = load("path_gangnam_to_hongdae_bus_only.json")["result"]["path"][0]["subPath"]
    bus_ride = transit.parse_segments(bus_path)[1]  # 740번, 정류장 막차 추정 24:04, 43분 이동
    put_subway_timetable(900, [("23:40", "인천", 0), ("24:10", "인천", 0), ("24:30", "인천", 0)])
    route = {"segments": [
        walk(2), bus_ride, walk(5),
        subway("7호선", ["가", "나", "인천"], 10, start_id=900),
    ]}
    result = plan_route(route, "weekday", offline=True)
    assert result["status"] == "ok", result
    # 지하철 마지막 차 24:30 → 버스는 24:30 - 43분 - 도보 5분 = 23:42 이전에 출발해야 해요
    # 버스 정류장 막차(24:04)보다 이르니까, 배차간격 12분을 더 빼서 23:30
    assert [clock_text(leg["depart"]) for leg in result["legs"]] == ["23:30", "00:30"]
    assert clock_text(result["leave_by"]) == "23:28"  # 23:30 - 처음 도보 2분


def test_many_rides():
    """대중교통 구간이 3개 이상이면 계산하지 않고 '직접 확인'으로 표시해야 해요."""
    fresh_files(seed=False)
    route = {"segments": [subway("1호선", ["a", "b"], 5, 1), subway("2호선", ["b", "c"], 5, 2),
                          subway("3호선", ["c", "d"], 5, 3)]}
    with mock.patch("last_train.call_odsay", no_internet):
        assert plan_route(route, "weekday") == {"status": "many"}


def test_branch_line_unsure():
    """갈래 노선(1호선)에서 갈림역(구로)을 지나는데 종착역이 경로에 없으면 '확인 필요'여야 해요."""
    fresh_files(seed=False)
    stops = ["서울역", "남영", "용산", "노량진", "대방", "신길", "영등포", "신도림", "구로", "가산디지털단지", "수원"]
    put_subway_timetable(100, [("23:20", "천안", 0), ("23:40", "인천", 0)])
    route = {"segments": [subway("1호선", stops, 50, start_id=100)]}
    result = plan_route(route, "weekday", offline=True)
    assert result["status"] == "unsure"
    assert "인천행 열차가 수원역까지 가는지 확실하지 않아요" in result["reason"]

    # 종착역이 내릴 역과 같으면 확실해요
    put_subway_timetable(100, [("23:20", "천안", 0), ("23:40", "수원", 0)])
    assert clock_text(plan_route(route, "weekday", offline=True)["legs"][0]["depart"]) == "23:40"


def test_branch_line_without_junction():
    """1호선이라도 갈림역을 지나지 않으면(금정 → 수원), 종착역이 경로 너머여도 확실하게 판단해야 해요."""
    fresh_files(seed=False)
    put_subway_timetable(101, [("23:50", "천안", 0), ("24:10", "병점", 0)])
    route = {"segments": [subway("1호선", ["금정", "군포", "당정", "의왕", "성균관대", "화서", "수원"], 15, 101)]}
    result = plan_route(route, "weekday", offline=True)
    assert result["status"] == "ok"
    assert (clock_text(result["legs"][0]["depart"]), result["legs"][0]["terminus"]) == ("00:10", "병점")


def test_circle_line_seongsu():
    """2호선으로 성수를 지나가면, 성수행 열차는 성수에서 끝난다고 보고 그 앞 열차를 골라야 해요. (이른 쪽)"""
    fresh_files(seed=False)
    put_subway_timetable(200, [("23:30", "을지로입구", 0), ("23:50", "성수", 0)])
    route = {"segments": [subway("2호선", ["잠실", "잠실나루", "강변", "구의", "건대입구", "성수", "뚝섬", "왕십리"],
                                 14, start_id=200)]}
    result = plan_route(route, "weekday", offline=True)
    assert (clock_text(result["legs"][0]["depart"]), result["legs"][0]["terminus"]) == ("23:30", "을지로입구")


def test_express_only_for_express_route():
    """경로가 급행이면 급행 열차만, 일반이면 일반 열차만 골라야 해요."""
    fresh_files(seed=False)
    put_subway_timetable(300, [("23:30", "중앙보훈병원", 1), ("23:45", "중앙보훈병원", 0)])
    normal = {"segments": [subway("9호선", ["신논현", "고속터미널"], 5, start_id=300)]}
    express = {"segments": [subway("9호선(급행)", ["신논현", "고속터미널"], 3, start_id=300)]}
    assert clock_text(plan_route(normal, "weekday", offline=True)["legs"][0]["depart"]) == "23:45"
    assert clock_text(plan_route(express, "weekday", offline=True)["legs"][0]["depart"]) == "23:30"


def test_station_name_variants():
    """역 이름 모양이 조금 달라도("광교중앙(아주대)" vs "광교중앙") 같은 역으로 봐야 해요."""
    assert last_train.same_station("광교중앙(아주대)", "광교중앙")
    assert last_train.same_station("수원역", "수원")
    assert not last_train.same_station("수원", "수원시청")


def test_timetable_cache_30_days():
    """시간표 메모는 30일 동안 쓰고, 30일이 지나면 ODsay에 다시 물어봐야 해요. (showExpressTime=1 포함)"""
    fresh_files(seed=False)
    answer = load("subway_schedule_1530_jeongja_suinbundang.json")
    postman = mock.Mock(return_value=answer)
    with mock.patch("last_train.call_odsay", postman):
        last_train.get_timetable("subway", 1530)
        last_train.get_timetable("subway", 1530)  # 두 번째는 메모장에서
        assert postman.call_count == 1
        assert postman.call_args.args[1] == {"stationID": 1530, "showExpressTime": 1}

        # 저장 날짜를 31일 전으로 바꾸면 다시 물어봐요
        cache = transit.read_json(last_train.TIMETABLE_CACHE_PATH, {})
        cache["subway:1530"]["saved"] = "2026-09-20"
        transit.write_json(last_train.TIMETABLE_CACHE_PATH, cache)
        with mock.patch("last_train.today_kst", lambda: "2026-10-21"):
            assert not last_train.is_timetable_cached("subway", 1530)
            last_train.get_timetable("subway", 1530)
        assert postman.call_count == 2


def test_offline_timetable_missing():
    """테스트 모드에서 시간표가 메모장에 없으면, ODsay를 부르지 않고 '저장된 결과가 없어요'로 멈춰야 해요."""
    fresh_files(seed=False)
    with mock.patch("last_train.call_odsay", no_internet):
        try:
            last_train.get_timetable("subway", 1530, offline=True)
            assert False, "오류가 나야 하는데 안 났어요"
        except transit.OfflineMissError as error:
            assert "테스트 모드에서는 저장된 결과가 없어요" in str(error)


def test_plan_friend_and_count_calls():
    """귀갓길이 메모장에 있으면 필요한 호출 수를 정확히 세고, 없으면 '최대'로 세야 해요. 가까우면 0건."""
    fresh_files(seed=False)
    with mock.patch("last_train.call_odsay", no_internet), mock.patch("transit.call_odsay", no_internet):
        assert last_train.count_last_train_calls(JEONGJA, [SUWON]) == (3, False)  # 경로 1 + 시간표 최대 2
        assert last_train.count_last_train_calls(JEONGJA, [(37.367, 127.108)]) == (0, True)  # 100m → 걸어가요

        # 귀갓길(정자 → 수원)을 메모장에 넣으면: 시간표 1건만 필요
        cache = {transit.make_cache_key(JEONGJA, SUWON): real_route("path_jeongja_to_suwon.json")}
        transit.write_json(transit.CACHE_PATH, cache)
        assert last_train.count_last_train_calls(JEONGJA, [SUWON, SUWON]) == (1, True)  # 같은 역은 한 번만

        # 시간표까지 넣으면 0건 → 테스트 모드로 바로 계산
        last_train.save_timetable("subway", 1530, load("subway_schedule_1530_jeongja_suinbundang.json"))
        assert last_train.count_last_train_calls(JEONGJA, [SUWON]) == (0, True)
        results = last_train.plan_last_trains(JEONGJA, [SUWON, (37.367, 127.108)], "weekday", offline=True)
        assert results[0]["status"] == "ok" and clock_text(results[0]["leave_by"]) == "23:37"
        assert results[1]["status"] == "walk"


def test_budget_check():
    """막차 확인에 필요한 호출이 오늘 남은 횟수보다 많으면, 부르기 전에 안내해야 해요."""
    fresh_files(seed=False)
    transit.write_json(transit.USAGE_PATH, {"date": transit.today_kst(), "count": 28})  # 남은 횟수 2
    with mock.patch("last_train.call_odsay", no_internet), mock.patch("transit.call_odsay", no_internet):
        try:
            last_train.plan_last_trains(JEONGJA, [SUWON], "weekday")
            assert False, "오류가 나야 하는데 안 났어요"
        except ValueError as error:
            assert "막차 확인에 ODsay 최대 3건이 필요한데, 오늘 남은 횟수는 2건이에요." in str(error)


def test_meeting_end():
    """모임 종료 = 가장 이른 '나서야 하는 시각' - 여유 10분. 확인이 필요한 친구는 계산에서 빠져요."""
    results = [
        {"status": "ok", "leave_by": to_minutes("23:37")},
        {"status": "ok", "leave_by": to_minutes("23:10")},
        {"status": "unsure", "reason": "..."},
    ]
    end = last_train.meeting_end(results, ["수원역", "스타필드시티 위례", "강남역"])
    assert end == {"end": to_minutes("23:00"), "friend": "스타필드시티 위례", "index": 1}
    assert last_train.meeting_end([{"status": "many"}], ["수원역"]) is None


# 이 파일을 직접 실행하면 위의 테스트들을 차례로 실행합니다.
if __name__ == "__main__":
    tests = [
        test_time_helpers, test_real_jeongja_to_suwon, test_real_gangnam_line2_after_midnight,
        test_real_bus_740_turning_point, test_real_bus_740_start_label, test_real_bus_3217_single_value,
        test_old_bus_memo_is_refetched, test_bus_bound_minus_interval, test_backward_two_rides, test_many_rides,
        test_branch_line_unsure, test_branch_line_without_junction, test_circle_line_seongsu,
        test_express_only_for_express_route, test_station_name_variants, test_timetable_cache_30_days,
        test_offline_timetable_missing, test_plan_friend_and_count_calls, test_budget_check, test_meeting_end,
    ]
    usage_path = transit.USAGE_PATH  # 진짜 기록부 위치 (테스트가 끝나고 사용량이 그대로인지 확인)
    usage_before = transit.read_json(usage_path, {}).get("count")
    for test in tests:
        test()  # 실패하면 여기서 AssertionError가 나며 멈춰요
        print(f"✅ {test.__name__}: {test.__doc__.strip().splitlines()[0]}")
    assert transit.read_json(usage_path, {}).get("count") == usage_before, "ODsay 사용량이 바뀌었어요!"
    print(f"\n🎉 테스트 {len(tests)}개 모두 통과! (ODsay 실제 호출 0번)")
