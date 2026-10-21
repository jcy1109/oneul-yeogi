# test_recommend.py
# 역할: recommend.py의 "순위 매기기"를 가짜 이동시간 표로 테스트합니다.
#
# ⚠️ 순위 함수는 ODsay를 부르지 않아요. 여기서는 가짜 표만 쓰기 때문에 호출 0번이에요.

from datetime import time  # 약속 시각(예: 19:00)을 만들기 위한 도구
from unittest import mock  # 진짜 함수를 가짜로 바꿔치기하는 도구

import recommend

from recommend import (
    candidate_count, departure_text, departure_time, find_saved_example, rank_stations, route_details, route_summary, same_top_station,
)

# 가짜 경로: 강남 → [2호선] → 사당 → [4호선] → 금정 (같은 역에서 환승)
SUBWAY_ROUTE = {"time_min": 40, "transfers": 1, "segments": [
    {"type": "walk", "minutes": 1, "distance_m": 37},
    {"type": "subway", "line": "2호선", "start": "강남", "end": "사당", "minutes": 9, "stations": 4},
    {"type": "walk", "minutes": 0, "distance_m": 0},
    {"type": "subway", "line": "4호선", "start": "사당", "end": "금정", "minutes": 23, "stations": 10},
]}

# 가짜 경로: 집에서 7분 걸어서 마천역 → 5호선 → 오금역 → 3호선 → 교대역
HOME_ROUTE = {"time_min": 45, "transfers": 1, "segments": [
    {"type": "walk", "minutes": 7, "distance_m": 480},
    {"type": "subway", "line": "5호선", "start": "마천", "end": "오금", "minutes": 6, "stations": 3},
    {"type": "walk", "minutes": 2, "distance_m": 0},
    {"type": "subway", "line": "3호선", "start": "오금", "end": "교대", "minutes": 25, "stations": 12},
]}

# 가짜 경로: 버스에서 내린 곳(사당역 정류장)과 지하철 타는 곳(이수)이 다른 경우
BUS_ROUTE = {"time_min": 48, "transfers": 1, "segments": [
    {"type": "bus", "line": "040/N64번", "start": "강남역9번출구", "end": "사당역", "minutes": 16, "stations": 8},
    {"type": "walk", "minutes": 4, "distance_m": 250},
    {"type": "subway", "line": "4호선", "start": "이수", "end": "금정", "minutes": 25, "stations": 11},
]}


def make_table(stations):
    """
    가짜 이동시간 표를 간단히 만들어주는 도우미입니다.
    stations 예: {"A역": [90, 90], "B역": [40, 48]}  ← 친구별 소요시간(분)
    시간 대신 "X"를 넣으면 그 친구는 "경로 없음"이 됩니다.
    """
    table = {"friends": ["친구1", "친구2"], "stations": []}
    for name, times in stations.items():
        routes = []
        for t in times:
            if t == "X":
                routes.append({"error": "두 지점 사이의 대중교통 경로를 찾을 수 없어요."})
            else:
                routes.append({"time_min": t, "transfers": 1})
        table["stations"].append({"name": name, "routes": routes})
    return table


def names(table, criterion):
    """순위 결과에서 역 이름만 순서대로 뽑아줍니다."""
    ranked, _ = rank_stations(table, criterion)
    return [s["name"] for s in ranked]


# ─────────────────────────────────────────────
# 테스트들
# ─────────────────────────────────────────────

def test_fair_longest_first():
    """fair: 가장 오래 걸리는 친구의 시간이 짧은 역이 위로 가요."""
    table = make_table({
        "최대60역": [55, 60],
        "최대50역": [45, 50],
        "최대70역": [10, 70],
    })
    assert names(table, "fair") == ["최대50역", "최대60역", "최대70역"]


def test_fair_tie_smaller_gap():
    """fair: 가장 오래 걸리는 시간이 같으면, 친구 간 차이가 작은 역이 위로 가요. (합계는 더 커도요)"""
    table = make_table({
        "최대60_차40": [20, 60],  # 합계 80
        "최대60_차20": [40, 60],  # 합계 100 → 합계는 크지만 더 공평해서 위로
    })
    assert names(table, "fair") == ["최대60_차20", "최대60_차40"]


def test_fair_not_both_90():
    """fair: 둘 다 90분(차이 0분)인 역보다, 조금 차이 나도 훨씬 빠른 역이 위로 가야 해요."""
    table = make_table({
        "모두90분역": [90, 90],
        "적당역": [40, 48],
    })
    assert names(table, "fair")[0] == "적당역"


def test_fast():
    """fast: 모든 친구의 시간 합계가 작은 순."""
    table = make_table({
        "합80": [10, 70],  # 한 명만 많이 고생하지만 합계는 작음
        "합95": [45, 50],
    })
    assert names(table, "fast") == ["합80", "합95"]
    assert names(table, "fair") == ["합95", "합80"]  # 같은 표라도 fair는 반대!


def test_default_is_fair():
    """기준을 안 고르면 fair로 정렬돼야 해요."""
    table = make_table({"합80": [10, 70], "합95": [45, 50]})
    ranked, _ = rank_stations(table)
    assert [s["name"] for s in ranked] == names(table, "fair")


def test_same_top_station():
    """두 기준의 1위가 같으면 그 역 이름을, 다르면 None을 돌려줘요."""
    same = make_table({"좋은역": [30, 31], "나쁜역": [40, 50]})  # 둘 다 좋은역이 1위
    assert same_top_station(same) == "좋은역"

    different = make_table({"합80": [10, 70], "합95": [45, 50]})  # fair는 합95, fast는 합80
    assert same_top_station(different) is None

    nothing = make_table({"못가는역": [30, "X"]})  # 순위에 든 역이 없으면 비교할 수 없음
    assert same_top_station(nothing) is None


def test_excluded_station():
    """한 친구라도 경로를 못 구한 역은 순위에서 빠지고, 누구 때문인지 이유가 나와야 해요."""
    table = make_table({
        "정상역": [40, 50],
        "못가는역": [30, "X"],
    })
    for criterion in ["fair", "fast"]:
        ranked, excluded = rank_stations(table, criterion)
        assert [s["name"] for s in ranked] == ["정상역"]
        assert excluded[0]["name"] == "못가는역"
        assert "친구2" in excluded[0]["reason"]  # 누구 경로가 문제인지 알려줌


def test_candidate_count():
    """후보 개수: 친구 2명 → 5곳, 3명 → 3곳. 한 번 검색에 ODsay 호출이 10건을 넘으면 안 돼요."""
    assert candidate_count(2) == 5
    assert candidate_count(3) == 3
    for friends in [2, 3]:
        assert friends * candidate_count(friends) <= 10


def test_route_summary_home_walk():
    """경로 요약: 집에서 첫 역까지 걷는 구간부터 보여주고, 지하철역에는 '역'을 붙여요."""
    assert route_summary(HOME_ROUTE) == "🏠 → 도보 7분 → 마천역 [5호선] → 오금역 [3호선] → 교대역"


def test_route_summary_subway():
    """경로 요약: 같은 역에서 갈아타면 그 역을 한 번만 보여줘요."""
    assert route_summary(SUBWAY_ROUTE) == "🏠 → 도보 1분 → 강남역 [2호선] → 사당역 [4호선] → 금정역"


def test_route_summary_bus_to_subway():
    """경로 요약: 걷는 구간이 없으면 바로 타는 곳부터, 내린 곳과 타는 곳이 다르면 내린 곳도 보여줘요."""
    assert route_summary(BUS_ROUTE) == "🏠 → 강남역9번출구 [040/N64번] → 사당역 → 이수역 [4호선] → 금정역"


def test_route_details():
    """자세한 경로: 첫 도보는 '출발지에서 ○○역까지', 0분 도보는 생략해요."""
    assert route_details(HOME_ROUTE) == [
        "🏠 출발지에서 마천역까지 도보 7분 (480m)",
        "🚇 5호선 마천역 → 오금역 (3개 역, 6분)",
        "🚶 도보 2분",
        "🚇 3호선 오금역 → 교대역 (12개 역, 25분)",
    ]
    assert route_details(SUBWAY_ROUTE)[0] == "🏠 출발지에서 강남역까지 도보 1분 (37m)"
    assert route_details(BUS_ROUTE)[0] == "🚌 040/N64번 강남역9번출구 → 사당역 (8개 정류장, 16분)"


def test_route_walk_and_error():
    """걸어가는 경로와 못 구한 경로도 멈추지 않고 문구로 보여줘요."""
    walk = {"time_min": 7, "transfers": 0, "walk": True}
    assert route_summary(walk) == "🏠 → 걸어서 7분"
    assert route_details(walk) == ["🏠 출발지에서 역까지 걸어서 7분"]
    assert route_summary({"error": "경로를 찾을 수 없어요."}) == "경로 없음"


def test_departure_time():
    """출발 시각 = 약속 시각 - 이동시간 - 여유 5분"""
    assert departure_time(time(19, 0), 39) == (time(18, 16), False)  # 19:00 - 39분 - 5분
    assert departure_time(time(19, 0), 0) == (time(18, 55), False)  # 이동시간 0분이어도 여유 5분
    assert departure_time(time(19, 0), 39, buffer_min=0) == (time(18, 21), False)  # 여유 시간 바꾸기


def test_departure_text():
    """출발 시각 글자: 지하철·도보 경로 모두 "18:16 출발", 경로가 없으면 "경로 없음"이에요."""
    assert departure_text(time(19, 0), HOME_ROUTE) == "18:10 출발"  # 45분 + 5분
    assert departure_text(time(19, 0), {"time_min": 7, "transfers": 0, "walk": True}) == "18:48 출발"
    assert departure_text(time(19, 0), {"error": "경로를 찾을 수 없어요."}) == "경로 없음"


def test_departure_previous_day():
    """자정을 넘으면 "전날"이라고 알려줘야 해요."""
    assert departure_time(time(0, 30), 50) == (time(23, 35), True)
    assert departure_text(time(0, 30), {"time_min": 50, "transfers": 0}) == "전날 23:35 출발"
    assert departure_text(time(0, 30), {"time_min": 25, "transfers": 0}) == "00:00 출발"  # 딱 자정은 같은 날


def test_unknown_criterion():
    """없는 기준을 넣으면 친절한 안내가 나와야 해요."""
    table = make_table({"정상역": [40, 50]})
    try:
        rank_stations(table, "care")  # 예전에 있던 기준이지만 이제는 없어요
        assert False, "오류가 나야 하는데 안 났어요"
    except ValueError as error:
        assert "알 수 없는 기준" in str(error)


def test_find_saved_example():
    """예시 조합 중 '모든 구간이 메모장에 있는' 첫 조합을 골라야 해요. 못 찾는 장소가 있는 조합은 건너뛰어요."""
    fake_places = {"A역": [{"lat": 37.1, "lng": 127.1}], "B역": [{"lat": 37.2, "lng": 127.2}],
                   "C역": [{"lat": 37.3, "lng": 127.3}]}
    search = lambda name: fake_places.get(name, [])  # 가짜 장소 검색 (없는 이름이면 빈 목록)
    groups = [["없는곳", "A역"], ["A역", "B역"], ["A역", "C역"]]

    def fake_estimate(coords):
        # A역 + C역만 모두 저장되어 있다고 쳐요 (A역 + B역은 2구간이 저장 안 됨)
        return (0 if coords == [(37.1, 127.1), (37.3, 127.3)] else 2), []

    with mock.patch("recommend.estimate_calls", fake_estimate):
        assert find_saved_example(search, groups) == ["A역", "C역"]
        assert find_saved_example(search, groups[:2]) is None  # 저장된 조합이 없으면 None


def test_offline_build_needs_cache():
    """테스트 모드로 이동시간 표를 만들 때 저장 안 된 구간이 있으면, ODsay 없이 바로 안내해야 해요."""
    with mock.patch("recommend.count_odsay_calls", lambda coords, stations: 4), \
            mock.patch("recommend.get_transit_info", side_effect=AssertionError("부르면 안 돼요")):
        try:
            recommend.build_travel_table(["친구1", "친구2"], [(37.5, 127.0), (37.3, 127.0)], offline=True)
            assert False, "오류가 나야 하는데 안 났어요"
        except ValueError as error:
            assert "테스트 모드에서는 저장된 결과가 없어요. (저장되지 않은 구간 4개)" in str(error), error


# 이 파일을 직접 실행하면 위의 테스트들을 차례로 실행합니다.
if __name__ == "__main__":
    tests = [
        test_fair_longest_first, test_fair_tie_smaller_gap, test_fair_not_both_90,
        test_fast, test_default_is_fair, test_same_top_station, test_excluded_station,
        test_candidate_count, test_route_summary_home_walk, test_route_summary_subway, test_route_summary_bus_to_subway,
        test_route_details, test_route_walk_and_error, test_departure_time, test_departure_text,
        test_departure_previous_day, test_unknown_criterion, test_find_saved_example, test_offline_build_needs_cache,
    ]
    for test in tests:
        test()  # 실패하면 여기서 AssertionError가 나며 멈춰요
        print(f"✅ {test.__name__}: {test.__doc__.strip().splitlines()[0]}")
    print(f"\n🎉 테스트 {len(tests)}개 모두 통과! (ODsay 실제 호출 0번)")
