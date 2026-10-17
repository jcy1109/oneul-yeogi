# places.py
# 역할: 약속 장소(역) 주변의 맛집과 놀거리를 카카오 로컬 API로 찾아주는 파일입니다.
#
# 종류는 4가지예요.
#   🍜 음식점: "○○역 맛집" 키워드 검색 + 정확도순 (카카오가 관련 있다고 판단한 곳이 먼저)
#   ☕ 카페 / 🎬 문화시설 / 🎡 관광명소: 카테고리 검색 + 거리순 (역에서 가까운 곳이 먼저)
# 카카오는 별점과 리뷰를 주지 않아서, 순서는 "검색 정확도" 또는 "거리" 기준이에요.

from geocode import KAKAO_KEYWORD_URL, from_keyword_result, kakao_search
from stations import make_search_word  # "사당" → "사당역" ("서울역"은 그대로)

# 카카오 "카테고리로 장소 검색" API의 주소
KAKAO_CATEGORY_URL = "https://dapi.kakao.com/v2/local/search/category.json"

# 역에서 몇 m 안에서 찾을지 (500m ≈ 걸어서 7~8분)
RADIUS_M = 500

# 종류별로 최대 몇 곳까지 보여줄지
MAX_PLACES = 5

# 종류 이름 → 카카오 카테고리 코드와 화면에 보여줄 이름
KINDS = {
    "food": {"code": "FD6", "label": "🍜 음식점"},
    "cafe": {"code": "CE7", "label": "☕ 카페"},
    "culture": {"code": "CT1", "label": "🎬 문화시설"},
    "attraction": {"code": "AT4", "label": "🎡 관광명소"},
}


def short_category(category_name):
    """
    카카오의 카테고리 글자에서 맨 앞의 큰 분류를 빼고 세부 카테고리만 남깁니다.
    예) "음식점 > 한식 > 국밥" → "한식 > 국밥"
        "카페" → "카페" (나눌 게 없으면 그대로)
    """
    parts = category_name.split(" > ")
    if len(parts) > 1:
        parts = parts[1:]
    return " > ".join(parts)


def from_place_result(doc):
    """카카오 검색 결과 하나를 화면에 보여주기 좋은 모양으로 바꿉니다."""
    return {
        "name": doc["place_name"],  # 장소 이름
        "category": short_category(doc.get("category_name", "")),  # 세부 카테고리 (예: 한식 > 국밥)
        "distance_m": int(doc.get("distance") or 0),  # 역에서 거리(m). 카카오가 글자로 줘서 숫자로 바꿔요
        "url": doc.get("place_url", ""),  # 카카오맵 장소 페이지 링크
    }


def get_nearby_places(station_coord, kind, station_name=""):
    """
    역 주변(반경 500m)의 장소를 종류별로 최대 5곳 찾아서 돌려줍니다. 못 찾으면 빈 리스트 []예요.

    station_coord: 역의 (위도, 경도)
    kind: "food", "cafe", "culture", "attraction" 중 하나 (KINDS 참고)
    station_name: 역 이름 (예: "사당"). 음식점을 "사당역 맛집"으로 검색할 때만 써요.

    돌려주는 값 예시:
        [{"name": "○○국밥", "category": "한식 > 국밥", "distance_m": 230,
          "url": "http://place.map.kakao.com/12345"}, ...]
    """
    if kind not in KINDS:
        raise ValueError(f"알 수 없는 종류예요: '{kind}'. ({', '.join(KINDS)} 중에서 골라주세요)")

    lat, lng = station_coord
    # 공통 조건: 역 좌표(카카오는 x = 경도, y = 위도), 반경, 개수
    params = {
        "x": lng,
        "y": lat,
        "radius": RADIUS_M,
        "size": MAX_PLACES,
        "category_group_code": KINDS[kind]["code"],
    }

    if kind == "food":
        # 음식점: "사당역 맛집"처럼 키워드로 찾고, 정확도순으로 정렬해요.
        # (카테고리 코드도 함께 넣어서, 음식점이 아닌 곳은 섞이지 않게 해요)
        if not station_name:
            raise ValueError("음식점을 찾으려면 역 이름이 필요해요.")
        params["query"] = f"{make_search_word(station_name)} 맛집"
        params["sort"] = "accuracy"
        documents = kakao_search(KAKAO_KEYWORD_URL, params)
    else:
        # 카페·문화시설·관광명소: 카테고리로 찾고, 가까운 순으로 정렬해요.
        params["sort"] = "distance"
        documents = kakao_search(KAKAO_CATEGORY_URL, params)

    return [from_place_result(doc) for doc in documents[:MAX_PLACES]]


def find_station(name):
    """
    역 이름으로 지하철역을 찾아 {"name", "address", "lat", "lng"}를 돌려줍니다. 못 찾으면 None.
    ("이미 장소를 정했어요" 화면에서 써요. 후보역 목록에 없는 역도 찾을 수 있어요)
    """
    documents = kakao_search(KAKAO_KEYWORD_URL, {
        "query": make_search_word(name),  # "사당" → "사당역"
        "category_group_code": "SW8",  # 지하철역만
        "size": 1,
    })
    if not documents:
        return None
    return from_keyword_result(documents[0])


# 이 파일을 직접 실행하면 사당역 주변 장소를 찾아서 보여줍니다. (카카오만 쓰고 ODsay는 안 써요)
if __name__ == "__main__":
    station = find_station("사당")
    print(f"🚉 {station['name']} ({station['address']})")
    for kind, info in KINDS.items():
        print(f"\n{info['label']}")
        found = get_nearby_places((station["lat"], station["lng"]), kind, "사당")
        if not found:
            print("   주변에 찾은 곳이 없어요")
        for p in found:
            print(f"   {p['name']} · {p['category']} · {p['distance_m']}m · {p['url']}")
