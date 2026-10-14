# candidates.py
# 역할: 친구들의 출발지를 받아서, 모두의 "중심"에서 가까운 후보역을 골라주는 파일입니다.

import json  # JSON 파일을 읽기 위한 도구
import math  # 삼각함수(sin, cos 등)와 제곱근 같은 수학 계산 도구
import os  # 파일 경로를 다루기 위한 도구

from geocode import get_coordinates  # 우리가 만든 "이름 → 좌표" 함수

# 후보역 좌표가 저장된 파일 위치
STATIONS_PATH = os.path.join("data", "stations.json")

# 지구의 반지름 (단위: km)
EARTH_RADIUS_KM = 6371


def haversine(lat1, lng1, lat2, lng2):
    """
    하버사인 공식: 두 지점(위도, 경도) 사이의 실제 거리를 km 단위로 계산합니다.
    지구가 둥글다는 것을 고려해서, 지구 표면을 따라 잰 거리를 구해요.
    """
    # 삼각함수는 "도(°)"가 아니라 "라디안" 단위를 쓰기 때문에 단위를 바꿔줍니다.
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])

    # 두 지점의 위도 차이, 경도 차이
    d_lat = lat2 - lat1
    d_lng = lng2 - lng1

    # 하버사인 공식의 핵심 계산 (지구 위에서 두 점이 벌어진 정도를 구함)
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2

    # 벌어진 각도를 구한 뒤, 지구 반지름을 곱해서 실제 거리(km)로 바꿉니다.
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_KM * c


def load_stations():
    """data/stations.json 파일에서 후보역 목록을 읽어옵니다."""
    with open(STATIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_candidates(start_places, top_n=5):
    """
    출발지 이름 리스트를 받아서, 중심점에서 가까운 후보역 top_n개를 돌려줍니다.

    돌려주는 값 예시:
        [{"name": "사당", "distance_km": 3.2}, {"name": "양재", "distance_km": 4.1}, ...]

    출발지를 찾을 수 없으면 친절한 메시지를 담은 ValueError를 일으킵니다.
    """
    # 출발지가 하나도 없으면 계산할 수 없으므로 알려줍니다.
    if not start_places:
        raise ValueError("출발지를 한 곳 이상 입력해주세요.")

    # 1단계: 출발지 이름 → 좌표
    coords = []  # 찾은 좌표를 담을 리스트
    not_found = []  # 못 찾은 출발지 이름을 담을 리스트

    for place in start_places:
        result = get_coordinates(place)
        if result is None:
            not_found.append(place)
        else:
            coords.append(result)

    # 2단계: 못 찾은 곳이 있으면, 전부 모아서 한 번에 친절하게 알려줍니다.
    if not_found:
        names = ", ".join(f"'{p}'" for p in not_found)
        raise ValueError(f"{names}을(를) 찾을 수 없어요. 이름을 다시 확인해주세요.")

    # 3단계: 중심점 = 모든 위도의 평균, 모든 경도의 평균
    center_lat = sum(lat for lat, lng in coords) / len(coords)
    center_lng = sum(lng for lat, lng in coords) / len(coords)

    # 4단계: 각 후보역과 중심점 사이의 거리를 계산합니다.
    results = []
    for station in load_stations():
        distance = haversine(center_lat, center_lng, station["lat"], station["lng"])
        results.append({"name": station["name"], "distance_km": round(distance, 2)})

    # 거리가 가까운 순서로 정렬한 뒤, 앞에서부터 top_n개만 잘라서 돌려줍니다.
    results.sort(key=lambda r: r["distance_km"])
    return results[:top_n]


# 이 파일을 직접 실행할 때만 아래 테스트가 동작합니다.
if __name__ == "__main__":
    test_cases = [
        ["강남역", "수원역"],  # 정상
        ["홍대입구역", "잠실역", "부평역"],  # 정상
        ["강남역", "ㅁㄴㅇㄹ존재하지않는곳"],  # 오류: 없는 장소
    ]

    for places in test_cases:
        print(f"\n📍 출발지: {places}")
        try:
            candidates = get_candidates(places)
            for i, c in enumerate(candidates, start=1):
                print(f"   {i}. {c['name']} ({c['distance_km']}km)")
        except ValueError as error:
            # 오류가 나도 프로그램을 멈추지 않고, 메시지만 보여준 뒤 다음 테스트로 넘어갑니다.
            print(f"   ⚠️ {error}")
