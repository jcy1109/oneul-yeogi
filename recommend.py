# recommend.py
# 역할: 친구들의 출발지를 받아, "공정성 기준"에 따라 약속 장소 후보역의 순위를 매기는 파일입니다.
#
# 두 단계로 나뉘어 있어요.
#   [1단계] build_travel_table(): 친구 × 후보역마다 이동시간을 구해 "표"로 만들기 (ODsay 사용)
#   [2단계] rank_stations(): 표를 보고 기준에 따라 순서만 정하기 (ODsay 사용 안 함)
# 그래서 기준을 바꿔도 ODsay를 다시 부르지 않아요.

import math  # 올림(ceil) 계산을 위한 도구

from candidates import geocode_places, haversine, pick_nearest_stations
from transit import DAILY_LIMIT, NoRouteError, get_remaining_calls, get_transit_info, is_cached

# 공정성 기준: 코드에서 쓰는 이름 → 사용자에게 보여줄 이름
CRITERIA = {
    "care": "멀리 오는 친구 배려",
    "fast": "다 같이 빨리",
    "equal": "똑같이 나누기",
}

# 기본 기준. 이 서비스는 "경기도 친구가 항상 멀리 오는 문제"를 해결하려고 만들었으므로 care가 기본이에요.
DEFAULT_CRITERION = "care"

# equal 기준에서 "시간 차이가 비슷하다"고 보는 범위 (분)
EQUAL_SIMILAR_MIN = 10

# 출발지가 역에서 이 거리(km) 이내면 ODsay 대신 걸어가는 시간으로 계산해요.
# (ODsay도 700m 이내는 "너무 가깝다"며 경로를 주지 않아요)
WALK_LIMIT_KM = 0.7
WALK_SPEED_KMH = 4  # 보통 걷는 속도 (시속 4km)


# ─────────────────────────────────────────────
# [1단계] 이동시간 표 만들기
# ─────────────────────────────────────────────

def walking_minutes(distance_km):
    """걸어서 몇 분 걸리는지 계산합니다. (직선거리 ÷ 걷는 속도, 분 단위로 올림)"""
    return math.ceil(distance_km / WALK_SPEED_KMH * 60)


def is_walkable(start, station):
    """출발 좌표와 역 사이가 걸어갈 수 있을 만큼 가까우면 True"""
    distance = haversine(start[0], start[1], station["lat"], station["lng"])
    return distance <= WALK_LIMIT_KM


def count_odsay_calls(coords, stations):
    """
    실제로 ODsay를 몇 번 부르게 될지 미리 세어봅니다.
    (걸어갈 수 있는 구간, 메모장에 이미 있는 구간은 빼고 셉니다)
    """
    count = 0
    for station in stations:
        station_coord = (station["lat"], station["lng"])
        for start in coords:
            if not is_walkable(start, station) and not is_cached(start, station_coord):
                count += 1
    return count


def estimate_calls(start_places, top_n=3):
    """
    출발지 이름만으로 "ODsay를 몇 번 부를지"와 "후보역 이름"을 미리 알려줍니다.
    (카카오만 쓰고 ODsay는 부르지 않아요)
    """
    coords = geocode_places(start_places)
    stations = pick_nearest_stations(coords, top_n)
    return count_odsay_calls(coords, stations), [s["name"] for s in stations]


def build_travel_table(start_places, top_n=3):
    """
    [1단계] 친구 × 후보역마다 소요시간과 환승 횟수를 구해서 "이동시간 표"를 만듭니다.

    돌려주는 값 예시:
        {
          "friends": ["강남역", "수원역"],
          "stations": [
            {"name": "금정", "routes": [
                {"time_min": 40, "transfers": 1, "fare": 1850},   ← 강남역에서
                {"error": "경로를 찾을 수 없어요."},                ← 수원역에서 (못 구함)
            ]},
            ...
          ]
        }
    routes의 순서는 friends의 순서와 같아요. (같은 출발지를 두 명이 입력해도 헷갈리지 않게)
    """
    coords = geocode_places(start_places)  # 친구 출발지 → 좌표
    stations = pick_nearest_stations(coords, top_n)  # 후보역 고르기

    # 시작하기 전에, 오늘 남은 호출 횟수로 충분한지 확인합니다.
    # (중간에 한도가 끝나서 호출만 날리고 결과를 못 얻는 일을 막기 위해서예요)
    needed = count_odsay_calls(coords, stations)
    remaining = get_remaining_calls()
    if needed > 0 and remaining == 0:
        raise ValueError(f"오늘 대중교통 조회 한도를 다 썼어요. ({DAILY_LIMIT}건) 내일 다시 시도해주세요.")
    if needed > remaining:
        raise ValueError(
            f"이번 추천에는 대중교통 조회가 {needed}번 필요한데, 오늘 남은 횟수는 {remaining}번이에요. "
            "내일 다시 시도하거나 친구 수를 줄여주세요."
        )

    table = {"friends": list(start_places), "stations": []}

    for station in stations:
        station_coord = (station["lat"], station["lng"])
        routes = []

        for start in coords:
            # 걸어갈 수 있을 만큼 가까우면 ODsay를 부르지 않고 도보 시간으로 계산합니다.
            if is_walkable(start, station):
                distance = haversine(start[0], start[1], station["lat"], station["lng"])
                routes.append({"time_min": walking_minutes(distance), "transfers": 0, "walk": True})
                continue

            try:
                routes.append(get_transit_info(start, station_coord))
            except NoRouteError as error:
                # "경로 없음"은 이 역만의 문제 → 기록해두고 나중에 순위에서 뺍니다.
                routes.append({"error": str(error)})
            # 키 오류, 한도 초과 같은 다른 ValueError는 역의 문제가 아니므로 그대로 위로 전달해서 멈춥니다.

        table["stations"].append({"name": station["name"], "routes": routes})

    return table


# ─────────────────────────────────────────────
# [2단계] 순위 매기기 (ODsay를 부르지 않아요)
# ─────────────────────────────────────────────

def rank_stations(table, criterion=DEFAULT_CRITERION):
    """
    [2단계] 이동시간 표를 보고, 공정성 기준에 따라 역의 순위를 정합니다.

    돌려주는 값: (순위 목록, 제외된 역 목록)
        순위 목록 예: [{"name": "사당", "routes": [...], "max_time": 40, "total_time": 75, "gap": 5}, ...]
        제외 목록 예: [{"name": "금정", "reason": "수원역: 경로를 찾을 수 없어요."}]
    """
    if criterion not in CRITERIA:
        raise ValueError(f"알 수 없는 기준이에요: '{criterion}'. ({', '.join(CRITERIA)} 중에서 골라주세요)")

    ranked = []  # 순위에 들어갈 역
    excluded = []  # 경로를 못 구해서 빠지는 역

    for station in table["stations"]:
        # 한 명이라도 경로를 못 구했으면, 그 역은 순위에서 뺍니다.
        problems = [
            f"{friend}: {route['error']}"
            for friend, route in zip(table["friends"], station["routes"])
            if "error" in route
        ]
        if problems:
            excluded.append({"name": station["name"], "reason": " / ".join(problems)})
            continue

        times = [route["time_min"] for route in station["routes"]]
        ranked.append({
            "name": station["name"],
            "routes": station["routes"],
            "max_time": max(times),  # 가장 오래 걸리는 친구의 시간
            "total_time": sum(times),  # 모든 친구 시간의 합계
            "gap": max(times) - min(times),  # 가장 오래 걸리는 친구와 가장 빨리 오는 친구의 차이
        })

    if criterion == "care":
        # 가장 오래 걸리는 친구의 시간이 짧은 순 → 같으면 합계가 작은 순
        ranked.sort(key=lambda s: (s["max_time"], s["total_time"]))
    elif criterion == "fast":
        # 합계가 작은 순 → 같으면 가장 오래 걸리는 친구의 시간이 짧은 순
        ranked.sort(key=lambda s: (s["total_time"], s["max_time"]))
    else:  # "equal"
        ranked = sort_equal(ranked)

    return ranked, excluded


def sort_equal(stations):
    """
    "똑같이 나누기" 기준으로 정렬합니다.

    그냥 "차이 작은 순"으로만 정렬하면, 둘 다 90분 걸리는 역(차이 0분)이 1위가 되어버려요.
    그래서 차이가 비슷한(10분 이내) 역들은 한 그룹으로 묶고,
    그룹 안에서는 "가장 오래 걸리는 친구의 시간"이 짧은 역을 위로 올립니다.

    방법:
      1) 남은 역 중 차이가 가장 작은 역을 찾고,
      2) 그 역과 차이 간격이 10분 이내인 역들을 한 그룹으로 묶어서,
      3) 그룹 안을 (최대 시간 → 합계) 순으로 정렬해 결과에 붙이고,
      4) 남은 역으로 1)부터 반복합니다.
    (역 두 개씩 따로 비교하면 가위바위보처럼 순서가 꼬일 수 있어서, 이렇게 그룹으로 정해요)
    """
    remaining = sorted(stations, key=lambda s: s["gap"])  # 차이 작은 순으로 줄 세우기
    result = []

    while remaining:
        smallest_gap = remaining[0]["gap"]
        group = [s for s in remaining if s["gap"] <= smallest_gap + EQUAL_SIMILAR_MIN]
        remaining = [s for s in remaining if s["gap"] > smallest_gap + EQUAL_SIMILAR_MIN]

        group.sort(key=lambda s: (s["max_time"], s["total_time"]))
        result.extend(group)

    return result


# ─────────────────────────────────────────────
# 결과 출력
# ─────────────────────────────────────────────

def describe_route(route):
    """한 친구의 이동 정보를 "40분(환승 1)" 같은 글자로 바꿉니다."""
    if "error" in route:
        return "경로 없음"
    if route.get("walk"):
        return f"{route['time_min']}분(도보)"
    return f"{route['time_min']}분(환승 {route['transfers']})"


def print_ranking(table, criterion=DEFAULT_CRITERION):
    """한 가지 기준의 순위를 보기 좋게 출력합니다."""
    ranked, excluded = rank_stations(table, criterion)

    print(f"\n🏆 [{CRITERIA[criterion]}] 기준 추천 순위")
    for rank, station in enumerate(ranked, start=1):
        print(f"  {rank}위  {station['name']}")
        for friend, route in zip(table["friends"], station["routes"]):
            print(f"        {friend} → {describe_route(route)}")
        print(f"        (최대 {station['max_time']}분 · 합계 {station['total_time']}분 · 차이 {station['gap']}분)")

    for station in excluded:
        print(f"  ❌ {station['name']}: 순위에서 제외 — {station['reason']}")


def print_side_by_side(table):
    """세 가지 기준의 순위를 나란히 비교해서 출력합니다."""
    # 1) 역마다 친구별 이동시간 표
    print("\n📋 후보역별 이동시간")
    for station in table["stations"]:
        details = " · ".join(
            f"{friend} {describe_route(route)}"
            for friend, route in zip(table["friends"], station["routes"])
        )
        print(f"  {station['name']}: {details}")

    # 2) 기준별 순위를 나란히
    results = {c: rank_stations(table, c) for c in CRITERIA}
    print("\n📊 기준별 순위 비교")
    print("  순위 | " + " | ".join(f"{CRITERIA[c]}({c})" for c in CRITERIA))
    rows = max(len(ranked) for ranked, _ in results.values())
    for i in range(rows):
        cells = []
        for c in CRITERIA:
            ranked, _ = results[c]
            if i < len(ranked):
                s = ranked[i]
                cells.append(f"{s['name']} (최대 {s['max_time']}·합 {s['total_time']}·차 {s['gap']})")
            else:
                cells.append("-")
        print(f"  {i + 1}위  | " + " | ".join(cells))

    # 3) 제외된 역 (기준과 상관없이 똑같아요)
    _, excluded = results[DEFAULT_CRITERION]
    for station in excluded:
        print(f"  ❌ {station['name']}: 순위에서 제외 — {station['reason']}")


# 이 파일을 직접 실행하면, ODsay 호출 횟수를 먼저 알려주고 허락을 받은 뒤 추천합니다.
if __name__ == "__main__":
    places = ["강남역", "수원역"]

    try:
        needed, station_names = estimate_calls(places)
        print(f"👥 출발지: {places}")
        print(f"🚉 후보역: {station_names}")
        print(f"📞 ODsay 호출 예정: {needed}번 (오늘 남은 횟수: {get_remaining_calls()}번)")

        answer = input("진행할까요? (y/n): ")
        if answer.strip().lower() == "y":
            table = build_travel_table(places)
            print_side_by_side(table)
            print_ranking(table)  # 기본 기준(care)으로 자세히
            print(f"\n📞 오늘 남은 ODsay 호출: {get_remaining_calls()}번")
        else:
            print("취소했어요. ODsay는 부르지 않았어요.")
    except ValueError as error:
        print(f"⚠️ {error}")
