# last_train.py
# 역할: 1위 추천역에서 친구마다 "귀가 목표 지점"까지 가는 막차를 확인하고,
#       "이 모임은 몇 시까지 놀 수 있는지"를 계산하는 파일입니다.
#
# 계산 방법: 집에 가는 길을 "뒤에서부터 거꾸로" 따져요.
#   예) 마지막 구간(버스) 막차가 23:50 → 그 버스를 타려면 앞 구간(지하철)은
#       23:50 - 지하철 이동시간 - 갈아타러 걷는 시간 이전에 출발해야 해요.
#       → 그 시각 이전에 출발하는 열차 중 가장 늦은 것이 앞 구간의 "마지막 출발 시각"이에요.
#
# ODsay 호출을 아끼는 장치
#   - 귀갓길 경로: transit.py의 메모장(transit_cache.json)을 함께 써요.
#   - 지하철 시간표·버스 노선 정보: data/timetable_cache.json에 30일 동안 적어둬요.
#     (지하철 시간표는 한 번 받으면 평일·토요일·휴일이 모두 들어 있어서, 날짜 종류를 바꿔도 다시 안 불러요)

import math  # 내림(floor) 계산을 위한 도구
import os  # 파일 경로를 다루기 위한 도구
import re  # 글자 속에서 숫자를 찾기 위한 도구
from datetime import date  # 메모의 저장 날짜가 30일이 지났는지 계산하기 위한 도구

from candidates import haversine  # 두 좌표 사이의 직선거리(km)
from recommend import WALK_LIMIT_KM, walking_minutes  # 걸어갈 수 있는 거리 기준, 도보 시간 계산
from transit import (
    OFFLINE_MISS_MESSAGE, NoRouteError, OfflineMissError, call_odsay, explain_odsay_error,
    get_remaining_calls, get_transit_info, is_cached, read_json, today_kst, write_json,
)

# ODsay "지하철역 전체 시간표"와 "버스노선 상세정보" API의 주소
SUBWAY_SCHEDULE_URL = "https://api.odsay.com/v1/api/searchSubwaySchedule"
BUS_LANE_URL = "https://api.odsay.com/v1/api/busLaneDetail"

# 시간표 메모장 파일 위치와 보관 기간(일)
TIMETABLE_CACHE_PATH = os.path.join("data", "timetable_cache.json")
CACHE_DAYS = 30

# 밤에는 버스가 빨리 달린다고 가정하는 속도(시속 km).
# 빠르게 가정할수록 정류장 도착 추정이 "실제보다 이르게" 나와서, 틀려도 안전한 쪽이에요.
BUS_NIGHT_SPEED_KMH = 40

# 모임 종료 시각을 계산할 때 빼는 여유 시간(분)
SAFETY_MIN = 10

# 대중교통 구간이 이보다 많으면(= 3개 이상) 계산하지 않고 "직접 확인"을 안내해요.
MAX_RIDES = 2

# 날짜 종류(recommend.DAY_TYPES의 이름) → 지하철 시간표 묶음 이름 / 버스 배차간격 이름
SCHEDULE_KEYS = {"weekday": "weekdaySchedule", "saturday": "saturdaySchedule", "holiday": "holidaySchedule"}
BUS_INTERVAL_KEYS = {"weekday": "bus_Interval_Week", "saturday": "bus_Interval_Sat", "holiday": "bus_Interval_Sun"}

# 갈래가 있는 노선과 그 갈림역
# 갈림역을 지나가는 경로에서 "종착역이 지나가는 역 목록에 없는" 열차는, 내 갈래로 가는지 알 수 없어요.
# 예) 1호선 서울역 → 수원: 구로에서 인천행과 천안행이 갈라져요. 인천행은 수원에 안 가요.
# (수인분당선은 갈래가 없어서 넣지 않았어요. 정자역 시간표의 종착역이 모두 한 줄 위에 있었어요)
BRANCH_JUNCTIONS = {
    "1호선": ["구로", "금천구청", "병점"],
    "5호선": ["강동"],
    "경의중앙선": ["가좌"],
}

# 화면에 보여줄 안내 문구
MANY_RIDES_MESSAGE = "⚠️ 환승이 많아 직접 확인이 필요해요"


class UnsureError(Exception):
    """막차를 확실하게 판단할 수 없을 때 생기는 오류예요. (틀린 시각 대신 "⚠️ 확인 필요"로 보여줘요)"""


# ─────────────────────────────────────────────
# 시각 도우미 ("23:38" ↔ 분)
# ─────────────────────────────────────────────

def to_minutes(text):
    """
    "23:38" 같은 시각을 "0시부터 몇 분"인지로 바꿉니다.
    ODsay 시간표는 자정이 넘으면 "24:38"처럼 24 이상으로 적어줘요. → 1478분 (계산이 편해요)
    혹시 "00:30"처럼 오면 새벽 4시 전은 "다음 날"로 보고 24시간을 더해요. (막차 계산에서 새벽 0~3시는 늘 밤의 연장)
    """
    hour, minute = (int(part) for part in text.split(":")[:2])
    if hour < 4:
        hour += 24
    return hour * 60 + minute


def clock_text(minutes):
    """분을 "23:38" 같은 시각 글자로 바꿉니다. 24시가 넘으면 "00:21"처럼 다시 0시부터 적어요."""
    minutes = int(minutes)
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


# ─────────────────────────────────────────────
# 역 이름·노선 이름 도우미
# ─────────────────────────────────────────────

def station_key(name):
    """
    역 이름을 비교하기 좋게 다듬습니다.
    "광교중앙(아주대)" → "광교중앙", "수원역" → "수원" (같은 역인데 이름 모양이 조금 달라도 같다고 보려고)
    """
    name = re.sub(r"\(.*?\)", "", name).strip()
    if name.endswith("역") and len(name) > 2:
        name = name[:-1]
    return name


def same_station(a, b):
    """두 역 이름이 같은 역이면 True"""
    return station_key(a) == station_key(b)


def line_key(line):
    """노선 이름을 비교하기 좋게 다듬습니다. "9호선(급행)" → "9호선", "경의.중앙선" → "경의중앙선" """
    return line.split("(")[0].replace(".", "").strip()


def reaches(terminus, stops, line):
    """
    종착역이 terminus인 열차가 내릴 역(stops의 마지막)까지 가는지 판단합니다.
    stops: 타는 역부터 내리는 역까지 지나가는 역 이름 목록

    돌려주는 값: True(간다) / False(못 간다) / None(확실하지 않다)
      - 종착역 = 내릴 역 → 간다
      - 종착역이 내릴 역보다 앞(지나가는 역 목록 안) → 못 간다 (예: 정자 → 수원인데 죽전행)
      - 종착역이 목록에 없음 → 내릴 역 너머까지 가는 열차예요.
        단, 갈래 노선에서 갈림역을 지나가면 다른 갈래로 갈 수도 있어서 → 확실하지 않다
    (2호선 순환선도 이 규칙으로 돼요. 성수행 열차는 성수에서 끝난다고 보니까, 틀려도 이르게 나와요)
    """
    if same_station(terminus, stops[-1]):
        return True
    if any(same_station(terminus, stop) for stop in stops[:-1]):
        return False
    junctions = BRANCH_JUNCTIONS.get(line_key(line), [])
    if any(same_station(junction, stop) for junction in junctions for stop in stops[:-1]):
        return None
    return True


def parse_interval(text):
    """
    버스 배차간격 글자에서 분을 꺼냅니다. 예: "12" → 12, "8~15" → 15 (가장 긴 쪽 = 안전한 쪽)
    "1회"처럼 운행 횟수로 적혀 있거나 숫자가 없으면 None이에요.
    """
    if not text or "회" in str(text):
        return None
    numbers = [int(n) for n in re.findall(r"\d+", str(text))]
    return max(numbers) if numbers else None


# ─────────────────────────────────────────────
# 시간표 메모장 (30일 보관)
# ─────────────────────────────────────────────

def timetable_key(kind, code):
    """메모장 제목. 예) 지하철 강남역 2호선 → "subway:222", 740번 버스 → "bus:1273" """
    return f"{kind}:{code}"


def is_fresh(saved_date):
    """저장한 날짜("2026-10-21")로부터 30일이 안 지났으면 True"""
    age = date.fromisoformat(today_kst()) - date.fromisoformat(saved_date)
    return 0 <= age.days < CACHE_DAYS


def load_timetable(kind, code):
    """메모장에서 시간표(또는 버스 노선 정보)를 꺼냅니다. 없거나 30일이 지났으면 None"""
    saved = read_json(TIMETABLE_CACHE_PATH, {}).get(timetable_key(kind, code))
    if saved and is_fresh(saved["saved"]):
        return saved["data"]
    return None


def is_timetable_cached(kind, code):
    """메모장에서 바로 꺼내 쓸 수 있으면 True (= ODsay를 부르지 않아도 됨)"""
    return load_timetable(kind, code) is not None


def trim_subway(data):
    """
    ODsay 지하철 시간표 답장에서 필요한 것만 남깁니다.
    결과 예: {"name": "정자", "line": "수도권 수인.분당선",
             "schedules": {"weekday": {"up": [["23:35", "왕십리", 0], ...], "down": [...]}, ...}}
    열차마다 [출발시각, 종착역, 열차종류(0 일반·1 급행·2 특급)]만 적어요.
    """
    result = data["result"]
    schedules = {}
    for day_type, day_key in SCHEDULE_KEYS.items():
        day = result.get(day_key) or {}
        schedules[day_type] = {
            way: [[t["departureTime"], t["endStationName"], t.get("subwayClass", 0)] for t in day.get(way, [])]
            for way in ("up", "down")
        }
    return {"name": result.get("stationName"), "line": result.get("laneName"), "schedules": schedules}


def trim_bus(data):
    """
    ODsay 버스노선 상세정보 답장에서 필요한 것만 남깁니다.
    결과 예: {"bus_no": "740", "last": "22:40", "ep_last": "24:00", "turning": 46,
             "interval": "12", "intervals": {"weekday": "12", ...},
             "stations": [[정류장 코드, 기점부터 누적거리(m)], ...]}
    """
    result = data["result"]
    return {
        "bus_no": result.get("busNo"),
        "last": result.get("busLastTime"),  # 기점(출발 차고지) 기준 막차
        "ep_last": result.get("bus_Ep_LastTime"),  # 회차점(종점) 기준 막차
        "turning": result.get("turningPointIdx"),  # 회차점이 몇 번째 정류장인지
        "interval": result.get("busInterval"),
        "intervals": {day_type: result.get(key) for day_type, key in BUS_INTERVAL_KEYS.items()},
        "stations": [[s["stationID"], s["stationDistance"]] for s in result.get("station", [])],
    }


def save_timetable(kind, code, data):
    """ODsay 답장을 다듬어서 오늘 날짜와 함께 메모장에 적고, 다듬은 값을 돌려줍니다."""
    if "error" in data:
        # 오류 답장은 적지 않고 안내만 해요. (다음에 다시 물어볼 수 있게)
        message, _ = explain_odsay_error(data["error"])
        raise ValueError(message)
    trimmed = trim_subway(data) if kind == "subway" else trim_bus(data)
    cache = read_json(TIMETABLE_CACHE_PATH, {})
    cache[timetable_key(kind, code)] = {"saved": today_kst(), "data": trimmed}
    write_json(TIMETABLE_CACHE_PATH, cache)
    return trimmed


def get_timetable(kind, code, offline=False):
    """
    지하철 시간표(kind="subway", code=역 코드) 또는 버스 노선 정보(kind="bus", code=노선 코드)를 돌려줍니다.
    메모장에 있으면 꺼내 쓰고, 없으면 ODsay에 물어봐요. (테스트 모드면 묻지 않고 OfflineMissError)
    """
    saved = load_timetable(kind, code)
    if saved is not None:
        return saved
    if offline:
        raise OfflineMissError(OFFLINE_MISS_MESSAGE)

    if kind == "subway":
        # showExpressTime=1: 급행 열차도 함께 받기 (기본값으로는 빠질 수 있어요)
        data = call_odsay(SUBWAY_SCHEDULE_URL, {"stationID": code, "showExpressTime": 1})
    else:
        data = call_odsay(BUS_LANE_URL, {"busID": code})
    return save_timetable(kind, code, data)


def ride_timetable(ride):
    """탈것 구간 하나에 필요한 메모장 (종류, 코드). 버스는 첫 번째 노선만 봐요(호출 아끼기, 틀려도 이른 쪽)."""
    if ride["type"] == "subway":
        return "subway", ride.get("start_id")
    bus_ids = ride.get("bus_ids") or [None]
    return "bus", bus_ids[0]


# ─────────────────────────────────────────────
# 구간별 "마지막 출발 시각"
# ─────────────────────────────────────────────

def subway_departure(ride, bound, day_type, offline=False):
    """
    지하철 구간에서 bound(분) 이전에 출발하고, 내릴 역까지 가는 열차 중 가장 늦은 열차를 찾습니다.
    돌려주는 값: (출발 시각(분), 종착역 이름)
    확실하지 않으면 UnsureError를 일으켜요.

    ⚠️ ODsay의 "막차 표시"는 종착역마다 따로 붙어서 쓰지 않아요.
       (정자역 하행: 24:22 죽전행에도 막차 표시가 있지만, 죽전행은 수원까지 안 가요)
    """
    way = ride.get("way_code")
    if way not in (1, 2):
        raise UnsureError(f"{ride['line']} 방향(상행/하행)을 알 수 없어요")
    stops = ride.get("stops") or []
    if len(stops) < 2:
        raise UnsureError(f"{ride['line']} 지나가는 역 정보가 없어요")

    table = get_timetable("subway", ride["start_id"], offline)
    trains = table["schedules"][day_type]["up" if way == 1 else "down"]
    express = "급행" in ride["line"]  # 경로가 급행이면 급행 열차만, 아니면 일반 열차만 봐요

    # 늦은 열차부터 하나씩 확인해요
    for departure_text, terminus, train_class in sorted(trains, key=lambda t: to_minutes(t[0]), reverse=True):
        departure = to_minutes(departure_text)
        if departure > bound:
            continue  # 다음 구간에 못 맞추는 열차
        if (train_class == 1) != express or train_class == 2:
            continue  # 종류가 다른 열차 (특급은 서는 역이 적어서 빼요)
        reach = reaches(terminus, stops, ride["line"])
        if reach is None:
            raise UnsureError(f"{terminus}행 열차가 {station_key(stops[-1])}역까지 가는지 확실하지 않아요")
        if reach:
            return departure, terminus
    raise UnsureError(f"{ride['line']} {station_key(stops[0])}역에서 탈 수 있는 열차를 시간표에서 찾지 못했어요")


def bus_departure(ride, bound, day_type, offline=False):
    """
    버스 구간에서 탈 정류장의 "마지막으로 탈 수 있는 시각"을 추정합니다. (분)

    정류장 막차 ≈ 막차의 출발 시각 + 그 정류장까지 거리 ÷ 밤 속도(시속 40km)
      - 탈 정류장이 회차점 앞이면: 기점 막차(busLastTime) + 기점부터 거리
      - 회차점 뒤(돌아오는 길)이면: 회차점 막차(bus_Ep_LastTime) + 회차점부터 거리
    다음 구간 때문에 bound가 정류장 막차보다 이르면, 그 직전 버스가 언제 올지 몰라서
    bound에서 배차간격만큼 더 빼요. (최악의 경우를 가정 → 틀려도 이른 쪽)
    """
    kind, bus_id = ride_timetable(ride)
    if bus_id is None:
        raise UnsureError(f"{ride['line']} 노선 정보가 없어요")
    lane = get_timetable(kind, bus_id, offline)

    distances = [distance for station_id, distance in lane["stations"]]
    ids = [station_id for station_id, distance in lane["stations"]]
    if ride.get("start_id") not in ids:
        raise UnsureError(f"{ride['line']} 노선에서 {ride['start']} 정류장을 찾지 못했어요")
    position = ids.index(ride["start_id"])

    turning = lane.get("turning")
    if turning is not None and position >= turning:
        base_text, distance = lane.get("ep_last"), distances[position] - distances[turning]
    else:
        base_text, distance = lane.get("last"), distances[position]
    if not base_text:
        raise UnsureError(f"{ride['line']} 막차 시각 정보가 없어요")

    # 내림(floor)으로 계산해서 도착 추정이 조금이라도 이르게 나오게 해요
    arrive = to_minutes(base_text) + math.floor(distance / 1000 / BUS_NIGHT_SPEED_KMH * 60)
    if arrive <= bound:
        return arrive

    interval = parse_interval(lane["intervals"].get(day_type) or lane.get("interval"))
    if interval is None:
        raise UnsureError(f"{ride['line']} 배차간격을 알 수 없어요")
    return bound - interval


# ─────────────────────────────────────────────
# 친구 한 명의 귀갓길 계산
# ─────────────────────────────────────────────

def rides_of(route):
    """경로에서 탈것(지하철·버스) 구간만, (경로 안 위치, 구간) 목록으로 돌려줍니다."""
    return [(i, seg) for i, seg in enumerate(route.get("segments", [])) if seg["type"] != "walk"]


def walk_minutes_between(segments, start, end):
    """segments[start:end] 안의 도보 시간 합계(분)"""
    return sum(seg["minutes"] for seg in segments[start:end] if seg["type"] == "walk")


def plan_route(route, day_type, offline=False):
    """
    귀갓길 경로 하나로 "1위 역에서 늦어도 몇 시에 출발해야 하는지"를 계산합니다.

    돌려주는 값 예시 (status로 종류를 구분해요)
      {"status": "ok", "leave_by": 1393, "walk_min": 1,
       "legs": [{"type": "subway", "line": "수인.분당선", "start": "정자", "depart": 1418,
                 "estimated": False, "terminus": "고색"}, ...]}
      {"status": "many"}                         ← 구간 3개 이상
      {"status": "unsure", "reason": "..."}      ← 확실하게 판단할 수 없음
    """
    segments = route.get("segments", [])
    rides = rides_of(route)
    if not rides:
        return {"status": "walk", "minutes": route.get("time_min", 0)}
    if len(rides) > MAX_RIDES:
        return {"status": "many"}

    legs = []
    next_departure = None  # 바로 뒤 구간의 마지막 출발 시각
    # 마지막 구간부터 거꾸로
    for k in reversed(range(len(rides))):
        position, ride = rides[k]
        if next_departure is None:
            bound = math.inf  # 마지막 구간은 제한 없음 → 그냥 내릴 곳까지 가는 마지막 차
        else:
            # 다음 구간을 타려면: 다음 구간 출발 - 이 구간 이동시간 - 갈아타러 걷는 시간 이전에 출발
            transfer_walk = walk_minutes_between(segments, position + 1, rides[k + 1][0])
            bound = next_departure - ride["minutes"] - transfer_walk

        try:
            if ride["type"] == "subway":
                departure, terminus = subway_departure(ride, bound, day_type, offline)
                estimated = False
            else:
                departure, terminus = bus_departure(ride, bound, day_type, offline), None
                estimated = True  # 버스는 노선 막차로 추정한 값
        except UnsureError as error:
            return {"status": "unsure", "reason": str(error)}

        legs.insert(0, {
            "type": ride["type"], "line": ride["line"], "start": ride["start"],
            "depart": departure, "estimated": estimated, "terminus": terminus,
        })
        next_departure = departure

    walk_min = walk_minutes_between(segments, 0, rides[0][0])  # 1위 역에서 첫 타는 곳까지 걷는 시간
    return {"status": "ok", "leave_by": legs[0]["depart"] - walk_min, "walk_min": walk_min, "legs": legs}


def prefetch_timetables(route, offline=False):
    """
    경로의 모든 탈것 구간 시간표를 미리 받아둡니다. (구간 3개 이상이면 계산하지 않으니 안 받아요)
    계산 도중 "확인 필요"로 멈춰도 나머지 시간표가 메모장에 있어야, 날짜 종류를 바꿨을 때 다시 안 불러요.
    """
    rides = rides_of(route)
    if len(rides) > MAX_RIDES:
        return
    for _, ride in rides:
        kind, code = ride_timetable(ride)
        if code is not None:
            get_timetable(kind, code, offline)


def plan_friend(station_coord, goal_coord, day_type, offline=False):
    """
    친구 한 명: 1위 역 좌표 → 귀가 목표 지점 좌표의 귀갓길을 검색하고 막차를 계산합니다.
    걸어갈 수 있을 만큼 가까우면 {"status": "walk"}, 경로가 없으면 {"status": "error"}예요.
    """
    distance = haversine(station_coord[0], station_coord[1], goal_coord[0], goal_coord[1])
    if distance <= WALK_LIMIT_KM:
        return {"status": "walk", "minutes": walking_minutes(distance)}

    try:
        route = get_transit_info(station_coord, goal_coord, offline=offline, detailed=True)
    except NoRouteError as error:
        return {"status": "error", "reason": str(error)}

    prefetch_timetables(route, offline)
    return plan_route(route, day_type, offline)


def count_last_train_calls(station_coord, goal_coords):
    """
    막차 확인에 ODsay가 몇 번 필요한지 미리 셉니다. (ODsay는 부르지 않아요)
    돌려주는 값: (호출 수, 정확한지 여부)
      - 귀갓길이 메모장에 있으면 → 필요한 시간표 수를 정확히 셀 수 있어요
      - 없으면 → 경로 1건 + 시간표 최대 2건으로 넉넉하게 세요 (정확하지 않음 → 화면에 "최대"로 표시)
    """
    total = 0
    exact = True
    needed_timetables = set()  # 친구 둘이 같은 역 시간표를 쓰면 한 번만 세요
    for goal in goal_coords:
        if haversine(station_coord[0], station_coord[1], goal[0], goal[1]) <= WALK_LIMIT_KM:
            continue
        if not is_cached(station_coord, goal, detailed=True):
            total += 1 + MAX_RIDES
            exact = False
            continue
        try:
            route = get_transit_info(station_coord, goal, offline=True, detailed=True)
        except NoRouteError:
            continue
        rides = rides_of(route)
        if len(rides) > MAX_RIDES:
            continue
        for _, ride in rides:
            kind, code = ride_timetable(ride)
            if code is not None and not is_timetable_cached(kind, code):
                needed_timetables.add((kind, code))
    return total + len(needed_timetables), exact


def plan_last_trains(station_coord, goal_coords, day_type, offline=False):
    """
    모든 친구의 막차를 계산합니다. 친구 순서대로 plan_friend의 결과 목록을 돌려줘요.
    시작하기 전에 오늘 남은 ODsay 횟수로 충분한지 확인해요. (테스트 모드면 확인하지 않아요)
    """
    if not offline:
        needed, exact = count_last_train_calls(station_coord, goal_coords)
        remaining = get_remaining_calls()
        if needed > remaining:
            amount = f"{needed}건" if exact else f"최대 {needed}건"
            raise ValueError(f"막차 확인에 ODsay {amount}이 필요한데, 오늘 남은 횟수는 {remaining}건이에요.")
    return [plan_friend(station_coord, goal, day_type, offline) for goal in goal_coords]


def meeting_end(results, friends):
    """
    모임 종료 시각 = 친구들 중 가장 이른 "1위 역에서 늦어도 나서야 하는 시각" - 여유 10분
    ("나서야 하는 시각"에는 이미 1위 역에서 타는 곳까지 걷는 시간이 빠져 있어요)
    돌려주는 값: {"end": 분, "friend": 기준이 된 친구 이름}, 계산할 수 있는 친구가 없으면 None
    """
    candidates = [(result["leave_by"], friend) for result, friend in zip(results, friends) if result["status"] == "ok"]
    if not candidates:
        return None
    leave_by, friend = min(candidates, key=lambda c: c[0])
    return {"end": leave_by - SAFETY_MIN, "friend": friend}


def leg_text(leg):
    """
    구간 하나를 화면용 글자로 바꿉니다.
    예) "🚇 수인.분당선 정자역 **23:38** 열차 (고색행)", "🚌 38번 복정역환승센터 **약 23:40 (추정)**"
    """
    if leg["type"] == "subway":
        start = leg["start"] if leg["start"].endswith("역") else leg["start"] + "역"
        return f"🚇 {leg['line']} {start} **{clock_text(leg['depart'])}** 열차 ({leg['terminus']}행)"
    return f"🚌 {leg['line']} {leg['start']} **약 {clock_text(leg['depart'])} (추정)**"
