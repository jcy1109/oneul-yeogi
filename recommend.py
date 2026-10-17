# recommend.py
# 역할: 친구들의 출발지를 받아, "공정성 기준"에 따라 약속 장소 후보역의 순위를 매기는 파일입니다.
#
# 두 단계로 나뉘어 있어요.
#   [1단계] build_travel_table(): 친구 × 후보역마다 이동시간을 구해 "표"로 만들기 (ODsay 사용)
#   [2단계] rank_stations(): 표를 보고 기준에 따라 순서만 정하기 (ODsay 사용 안 함)
# 그래서 기준을 바꿔도 ODsay를 다시 부르지 않아요.

import math  # 올림(ceil) 계산을 위한 도구
from datetime import date, datetime, timedelta  # 출발 시각(약속 시각 - 이동시간)을 계산하기 위한 도구

from candidates import geocode_places, haversine, pick_nearest_stations
from transit import DAILY_LIMIT, NoRouteError, get_remaining_calls, get_transit_info, is_cached

# 공정성 기준: 코드에서 쓰는 이름 → 사용자에게 보여줄 이름
CRITERIA = {
    "fair": "공평하게",
    "fast": "빠르게",
}

# 기본 기준. 이 서비스는 "경기도 친구가 항상 멀리 오는 문제"를 해결하려고 만들었으므로 fair가 기본이에요.
DEFAULT_CRITERION = "fair"

# 출발지가 역에서 이 거리(km) 이내면 ODsay 대신 걸어가는 시간으로 계산해요.
# (ODsay도 700m 이내는 "너무 가깝다"며 경로를 주지 않아요)
WALK_LIMIT_KM = 0.7
WALK_SPEED_KMH = 4  # 보통 걷는 속도 (시속 4km)

# 약속 날짜 종류: 코드에서 쓰는 이름 → 사용자에게 보여줄 이름
# (다음 단계의 막차 시간표에서 날짜 종류마다 다른 시간표를 쓸 거예요)
DAY_TYPES = {
    "weekday": "평일",
    "saturday": "토요일",
    "holiday": "일요일·공휴일",
}
DEFAULT_DAY_TYPE = "weekday"

# 출발 시각을 계산할 때 더하는 여유 시간(분). 지하철을 한 대 놓쳐도 늦지 않게!
BUFFER_MIN = 5

# 한 번 검색할 때 ODsay를 최대 몇 번까지 부를지 (하루 30건 제한 때문)
MAX_CALLS_PER_SEARCH = 10
MAX_CANDIDATES = 5  # 후보역은 아무리 많아도 5곳까지


def candidate_count(friend_count):
    """
    친구 수에 따라 후보역 개수를 정합니다. (친구 수 × 후보 수 ≤ 10)
    2명 → 5곳 (10건), 3명 → 3곳 (9건)
    """
    return max(1, min(MAX_CANDIDATES, MAX_CALLS_PER_SEARCH // friend_count))


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


def estimate_calls(coords, top_n=None):
    """
    출발지 좌표만으로 "ODsay를 몇 번 부를지"와 "후보역 이름"을 미리 알려줍니다.
    (ODsay는 부르지 않아요)
    top_n을 비워두면 친구 수에 맞춰 후보 개수를 정해요.
    """
    if top_n is None:
        top_n = candidate_count(len(coords))
    stations = pick_nearest_stations(coords, top_n)
    return count_odsay_calls(coords, stations), [s["name"] for s in stations]


def build_travel_table(friends, coords, top_n=None):
    """
    [1단계] 친구 × 후보역마다 소요시간과 환승 횟수를 구해서 "이동시간 표"를 만듭니다.

    friends: 화면에 보여줄 친구별 출발지 이름 (예: ["스타필드시티 위례", "수원역"])
    coords: 친구별 출발 좌표 (위도, 경도) 리스트. friends와 순서가 같아야 해요.
            (화면에서 사용자가 직접 고른 위치의 좌표예요)

    돌려주는 값 예시:
        {
          "friends": ["강남역", "수원역"],
          "stations": [
            {"name": "금정", "routes": [
                {"time_min": 40, "transfers": 1, "fare": 1850, "segments": [...]},   ← 강남역에서
                {"error": "경로를 찾을 수 없어요."},                ← 수원역에서 (못 구함)
            ]},
            ...
          ]
        }
    routes의 순서는 friends의 순서와 같아요. (같은 출발지를 두 명이 입력해도 헷갈리지 않게)
    top_n을 비워두면 친구 수에 맞춰 후보 개수를 정해요. (2명 → 5곳, 3명 → 3곳)
    """
    if top_n is None:
        top_n = candidate_count(len(coords))
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

    table = {"friends": list(friends), "stations": []}

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

        # 역 좌표도 함께 적어둬요. (1위 역 주변의 맛집·놀거리를 찾을 때 써요)
        table["stations"].append({
            "name": station["name"], "lat": station["lat"], "lng": station["lng"], "routes": routes,
        })

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
            "lat": station.get("lat"),  # 역 좌표 (가짜 표처럼 좌표가 없으면 None)
            "lng": station.get("lng"),
            "routes": station["routes"],
            "max_time": max(times),  # 가장 오래 걸리는 친구의 시간
            "total_time": sum(times),  # 모든 친구 시간의 합계
            "gap": max(times) - min(times),  # 가장 오래 걸리는 친구와 가장 빨리 오는 친구의 차이
        })

    if criterion == "fair":
        # 가장 오래 걸리는 친구의 시간이 짧은 순 → 같으면 친구 간 시간 차이가 작은 순
        # (그래도 같으면 합계가 작은 순으로, 순서가 매번 똑같이 나오게 해요)
        ranked.sort(key=lambda s: (s["max_time"], s["gap"], s["total_time"]))
    else:  # "fast"
        # 모든 친구의 시간 합계가 작은 순
        # (같으면 가장 오래 걸리는 친구의 시간이 짧은 순으로, 순서가 매번 똑같이 나오게 해요)
        ranked.sort(key=lambda s: (s["total_time"], s["max_time"]))

    return ranked, excluded


def same_top_station(table):
    """
    두 기준(fair, fast)의 1위가 같은 역이면 그 역 이름을, 다르면 None을 돌려줍니다.
    (같으면 "모두에게 좋은 장소"라고 안내하는 데 써요)
    """
    winners = set()
    for criterion in CRITERIA:
        ranked, _ = rank_stations(table, criterion)
        if not ranked:  # 순위에 든 역이 하나도 없으면 비교할 수 없어요
            return None
        winners.add(ranked[0]["name"])
    return winners.pop() if len(winners) == 1 else None


# ─────────────────────────────────────────────
# 출발 시각 계산 (이미 구한 이동시간을 써요 → ODsay를 부르지 않아요)
# ─────────────────────────────────────────────

def departure_time(meeting_time, travel_min, buffer_min=BUFFER_MIN):
    """
    출발 시각 = 약속 시각 - 이동시간 - 여유 시간

    meeting_time: 약속 시각 (datetime.time, 예: 19:00)
    travel_min: 이동시간(분)
    돌려주는 값: (출발 시각(time), 전날 출발인지 True/False)

    예) departure_time(19:00, 39) → (18:16, False)
        departure_time(00:30, 50) → (23:35, True)  ← 자정을 넘으면 "전날"
    """
    # 시각(time)끼리는 바로 뺄 수 없어서, 아무 날짜(2000년 1월 2일)에 붙여서 "날짜+시각"으로 만든 뒤 빼요.
    meeting_day = date(2000, 1, 2)
    meeting = datetime.combine(meeting_day, meeting_time)
    leave = meeting - timedelta(minutes=travel_min + buffer_min)
    return leave.time(), leave.date() < meeting_day


def departure_text(meeting_time, route):
    """
    한 친구의 출발 시각을 "18:16 출발" 같은 글자로 바꿉니다. (자정을 넘으면 "전날 23:35 출발")
    경로를 못 구한 친구는 "경로 없음"이에요.
    """
    if "error" in route:
        return "경로 없음"
    leave, previous_day = departure_time(meeting_time, route["time_min"])
    text = f"{leave:%H:%M} 출발"
    return f"전날 {text}" if previous_day else text


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


def stop_name(segment, which):
    """
    구간의 타는 곳(which="start") 또는 내리는 곳(which="end") 이름을 돌려줍니다.
    지하철이면 "마천" → "마천역"처럼 "역"을 붙여요. ("서울역"처럼 이미 "역"으로 끝나면 그대로)
    버스 정류장 이름은 그대로 써요.
    """
    name = segment[which]
    if segment["type"] == "subway" and not name.endswith("역"):
        return name + "역"
    return name


def first_walk(route):
    """
    출발지(집)에서 첫 역(또는 정류장)까지 걷는 구간을 돌려줍니다. 없으면 None.
    ODsay는 경로의 맨 처음에 "출발지 → 첫 역" 도보 구간을 넣어줘요.
    """
    segments = route.get("segments", [])
    if segments and segments[0]["type"] == "walk":
        return segments[0]
    return None


def route_summary(route):
    """
    경로를 한 줄로 요약합니다. 노선 이름이 바뀌는 곳이 갈아타는 곳이에요.
    예) "🏠 → 도보 7분 → 마천역 [5호선] → 오금역 [3호선] → 교대역"
    """
    if "error" in route:
        return "경로 없음"
    if route.get("walk"):
        return f"🏠 → 걸어서 {route['time_min']}분"

    rides = [s for s in route.get("segments", []) if s["type"] != "walk"]  # 탈것 구간만
    if not rides:
        return "경로 정보 없음"

    # 1) 집에서 첫 역까지 걷는 구간 (0분이면 생략)
    text = "🏠 → "
    walk = first_walk(route)
    if walk and walk["minutes"] > 0:
        text += f"도보 {walk['minutes']}분 → "

    # 2) 타는 곳 [노선] → 타는 곳 [노선] → ... 순서로 이어 붙여요
    for i, ride in enumerate(rides):
        if i > 0:
            # 내린 곳과 다음에 타는 곳이 다르면 (예: 버스 정류장 → 지하철역) 내린 곳도 적어줘요
            got_off = stop_name(rides[i - 1], "end")
            if got_off != stop_name(ride, "start"):
                text += f"{got_off} → "
        text += f"{stop_name(ride, 'start')} [{ride['line']}] → "

    # 3) 마지막에 내리는 곳
    return text + stop_name(rides[-1], "end")


def route_details(route):
    """
    경로를 구간별 문장 리스트로 바꿉니다. (펼치기 화면에서 한 줄씩 보여줘요)
    예) ["🏠 출발지에서 마천역까지 도보 7분 (480m)", "🚇 5호선 마천역 → 오금역 (3개 역, 6분)", ...]
    """
    if "error" in route:
        return [route["error"]]
    if route.get("walk"):
        return [f"🏠 출발지에서 역까지 걸어서 {route['time_min']}분"]

    segments = route.get("segments", [])
    rides = [s for s in segments if s["type"] != "walk"]  # 탈것 구간만
    lines = []
    for i, seg in enumerate(segments):
        if seg["type"] == "walk":
            if seg["minutes"] == 0:  # 0분 도보(같은 역 안 환승 등)는 생략
                continue
            distance = f" ({seg['distance_m']}m)" if seg["distance_m"] else ""
            if i == 0 and rides:
                # 맨 처음 도보 = 집에서 첫 역(정류장)까지
                lines.append(f"🏠 출발지에서 {stop_name(rides[0], 'start')}까지 도보 {seg['minutes']}분{distance}")
            else:
                lines.append(f"🚶 도보 {seg['minutes']}분{distance}")
        else:
            icon = "🚇" if seg["type"] == "subway" else "🚌"
            unit = "개 역" if seg["type"] == "subway" else "개 정류장"
            lines.append(
                f"{icon} {seg['line']} {stop_name(seg, 'start')} → {stop_name(seg, 'end')} "
                f"({seg['stations']}{unit}, {seg['minutes']}분)"
            )
    return lines


def print_ranking(table, criterion=DEFAULT_CRITERION):
    """한 가지 기준의 순위를 보기 좋게 출력합니다."""
    ranked, excluded = rank_stations(table, criterion)

    print(f"\n🏆 [{CRITERIA[criterion]}] 기준 추천 순위")
    for rank, station in enumerate(ranked, start=1):
        print(f"  {rank}위  {station['name']}")
        for friend, route in zip(table["friends"], station["routes"]):
            print(f"        {friend} → {describe_route(route)}  |  {route_summary(route)}")
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
    # 공공장소만 써요. (실제 개인 주소는 코드에 적지 않기!)
    places = ["스타필드시티 위례", "수원역"]

    try:
        coords = geocode_places(places)  # 출발지 → 좌표 (검색 결과가 여러 개면 첫 번째)
        needed, station_names = estimate_calls(coords)
        print(f"👥 출발지: {places}")
        print(f"🚉 후보역: {station_names}")
        print(f"📞 ODsay 호출 예정: {needed}번 (오늘 남은 횟수: {get_remaining_calls()}번)")

        answer = input("진행할까요? (y/n): ")
        if answer.strip().lower() == "y":
            table = build_travel_table(places, coords)
            print_side_by_side(table)
            if same_top_station(table):
                print(f"\n👍 두 기준 모두 같은 역({same_top_station(table)})을 추천해요. 모두에게 좋은 장소예요!")
            print_ranking(table)  # 기본 기준(fair)으로 자세히
            print(f"\n📞 오늘 남은 ODsay 호출: {get_remaining_calls()}번")
        else:
            print("취소했어요. ODsay는 부르지 않았어요.")
    except ValueError as error:
        print(f"⚠️ {error}")
