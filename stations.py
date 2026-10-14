# stations.py
# 역할: 약속 장소 "후보역" 목록을 관리하는 파일입니다.
# 직접 실행하면 각 역의 좌표를 카카오에서 받아와 data/stations.json에 저장합니다.

import json  # 파이썬 데이터를 JSON 파일로 저장하기 위한 도구
import os  # 폴더를 만들거나 파일 경로를 다루기 위한 도구

from geocode import get_coordinates  # 우리가 만든 "이름 → 좌표" 함수

# 약속 장소 후보가 될 수도권 주요 역 30곳 (출석부 같은 목록)
STATION_NAMES = [
    "서울역", "시청", "종로3가", "동대문역사문화공원", "청량리",
    "왕십리", "성수", "건대입구", "잠실", "선릉",
    "강남", "교대", "고속터미널", "양재", "수서",
    "사당", "노량진", "신도림", "영등포", "여의도",
    "공덕", "홍대입구", "합정", "신촌", "용산",
    "판교", "수원", "금정", "부평", "대화",
]

# 좌표를 저장할 파일 위치
OUTPUT_PATH = os.path.join("data", "stations.json")

# 수도권의 대략적인 범위 (이 밖에 있으면 "이상한 좌표"로 판단)
LAT_MIN, LAT_MAX = 36.9, 38.3  # 위도 범위 (남쪽 끝 ~ 북쪽 끝)
LNG_MIN, LNG_MAX = 126.0, 127.9  # 경도 범위 (서쪽 끝 ~ 동쪽 끝)


def make_search_word(name):
    """
    검색할 단어를 만듭니다. 이름 뒤에 "역"을 붙이되,
    "서울역"처럼 이미 "역"으로 끝나면 그대로 둡니다. ("서울역역" 방지)
    """
    if name.endswith("역"):
        return name
    return name + "역"


def is_in_capital_area(lat, lng):
    """좌표가 수도권 범위 안에 있으면 True, 아니면 False를 돌려줍니다."""
    return LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX


def build_station_data():
    """
    모든 후보역의 좌표를 찾아서
    (찾은 역 목록, 못 찾은 역 이름 목록)을 돌려줍니다.
    """
    found = []  # 좌표를 찾은 역들을 담을 빈 리스트
    not_found = []  # 좌표를 못 찾은 역 이름을 담을 빈 리스트

    # 출석부를 위에서부터 한 명씩 부릅니다.
    for name in STATION_NAMES:
        search_word = make_search_word(name)

        # "SW8" = 카카오의 지하철역 카테고리 → 역 근처 가게가 아닌 진짜 역만 찾음
        result = get_coordinates(search_word, category="SW8")

        if result is None:
            not_found.append(name)
        else:
            lat, lng = result
            found.append({"name": name, "lat": lat, "lng": lng})

    return found, not_found


# 이 파일을 직접 실행할 때만 아래 코드가 동작합니다.
if __name__ == "__main__":
    stations, missing = build_station_data()

    # data 폴더가 없으면 만듭니다. (이미 있으면 그냥 넘어감)
    os.makedirs("data", exist_ok=True)

    # JSON 파일로 저장합니다. ensure_ascii=False → 한글이 깨지지 않게 저장
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(stations, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(stations)}개 역의 좌표를 {OUTPUT_PATH}에 저장했습니다.")

    # 못 찾은 역 알려주기
    if missing:
        print(f"❌ 좌표를 못 찾은 역 ({len(missing)}개): {', '.join(missing)}")
    else:
        print("🎉 모든 역의 좌표를 찾았습니다.")

    # 수도권 밖에 있는 이상한 좌표 검사
    strange = [s for s in stations if not is_in_capital_area(s["lat"], s["lng"])]
    if strange:
        print("⚠️ 수도권 밖 좌표가 있습니다:")
        for s in strange:
            print(f"   {s['name']}: 위도 {s['lat']}, 경도 {s['lng']}")
    else:
        print("👍 모든 좌표가 수도권 범위 안에 있습니다.")
