# demo.py
# 역할: API 키가 없는 컴퓨터(예: 채점자)에서도 앱을 실행해볼 수 있게 해주는 "데모 모드" 파일입니다.
#
# 키가 없으면 카카오와 ODsay를 부를 수 없어요. 그래서 demo_data/ 폴더에
# 공공장소 예시 하나(스타필드시티 위례 + 수원역, 위례 친구 귀가 목표 복정역)에 필요한 기록만 넣어두고,
# 데모 모드에서는 data/ 메모장 대신 이 폴더를 읽어요. (시험 문제 하나 풀 분량만 담은 "요약 노트" 같은 것)
#   - places.json: 장소 이름 → 카카오 검색 결과 (공공장소 3곳만)
#   - transit_cache.json: 이동시간·귀갓길 메모장
#   - timetable_cache.json: 정자역 수인분당선 시간표, 3217번 버스 노선 정보

import os  # 파일 경로를 다루기 위한 도구

import geocode  # 카카오 API 키를 확인하기 위한 도구
import last_train  # 시간표 메모장 위치를 바꾸기 위한 도구
import transit  # ODsay API 키 확인, 메모장 위치를 바꾸기 위한 도구

DEMO_DIR = "demo_data"
PLACES_PATH = os.path.join(DEMO_DIR, "places.json")
DEMO_CACHE_PATH = os.path.join(DEMO_DIR, "transit_cache.json")
DEMO_TIMETABLE_PATH = os.path.join(DEMO_DIR, "timetable_cache.json")


def is_demo_mode():
    """카카오 키나 ODsay 키 중 하나라도 없으면 True (= 실제 검색·조회를 할 수 없어요)"""
    return not geocode.KAKAO_REST_API_KEY or not transit.ODSAY_API_KEY


def use_demo_data():
    """
    메모장 위치를 demo_data/로 바꿉니다.
    데모 데이터는 다시 받아올 수 없으니, 30일이 지나도 시간표 메모를 그대로 써요.
    (데모 모드는 항상 테스트 모드라서 이 폴더에 새로 적는 일은 없어요)
    """
    transit.CACHE_PATH = DEMO_CACHE_PATH
    last_train.TIMETABLE_CACHE_PATH = DEMO_TIMETABLE_PATH
    last_train.CHECK_EXPIRY = False


def search_places(query):
    """카카오 대신 demo_data/places.json에서 장소를 찾아요. 없으면 빈 리스트(못 찾음)"""
    return transit.read_json(PLACES_PATH, {}).get(query, [])


def place_names():
    """데모 모드에서 검색할 수 있는 장소 이름들 (안내 문구에 써요)"""
    return list(transit.read_json(PLACES_PATH, {}))
