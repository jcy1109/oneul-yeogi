# geocode.py
# 역할: 장소 이름이나 주소(예: "강남역", "서울 중구 세종대로 110")를 좌표(위도, 경도)로 바꿔주는 파일입니다.
# 카카오 로컬 API의 두 가지 기능을 사용합니다.
#   1) 주소 검색: 도로명 주소, 지번 주소 → 좌표
#   2) 키워드 검색: 아파트·건물·가게·역 이름 → 좌표

import os  # 컴퓨터의 환경 변수(숨겨둔 설정값)를 읽기 위한 도구

import requests  # 인터넷으로 다른 서버에 요청을 보내는 도구
from dotenv import load_dotenv  # .env 파일에 적힌 값을 불러오는 도구

# .env 파일을 읽어서, 그 안의 값들을 환경 변수로 등록합니다.
load_dotenv()

# 등록된 환경 변수 중에서 카카오 API 키를 꺼내옵니다.
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")

# 카카오 "키워드로 장소 검색" API의 주소
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

# 카카오 "주소 검색" API의 주소
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

# 출발지 검색 결과를 몇 개까지 보여줄지 (사용자가 이 중에서 골라요)
MAX_RESULTS = 3


def kakao_search(url, params):
    """
    카카오 검색 API에 요청을 보내고, 검색 결과 목록(documents)을 돌려줍니다.
    (주소 검색과 키워드 검색이 똑같은 방식으로 요청하기 때문에 한 곳에 모아뒀어요)
    """
    # API 키가 없으면 더 진행할 수 없으므로, 알기 쉬운 에러를 냅니다.
    if not KAKAO_REST_API_KEY:
        raise ValueError(".env 파일에 KAKAO_REST_API_KEY가 없습니다. 키를 먼저 넣어주세요.")

    # 카카오 서버에 "나 키 있는 사람이야"라고 알려주는 신분증 같은 정보
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}

    # 카카오 서버에 요청을 보냅니다. 10초 안에 답이 없으면 포기합니다.
    response = requests.get(url, headers=headers, params=params, timeout=10)

    # 서버가 에러를 돌려줬다면(예: 키가 틀림) 여기서 에러를 냅니다.
    response.raise_for_status()

    # 서버의 답장(JSON 형식)을 파이썬 딕셔너리로 바꾼 뒤, 검색 결과 목록만 꺼냅니다.
    return response.json()["documents"]


def get_coordinates(place_name, category=None):
    """
    장소 이름을 받아서 (위도, 경도)를 돌려주는 함수입니다. (키워드 검색의 첫 번째 결과)
    검색 결과가 없으면 None을 돌려줍니다.
    지금은 후보역 좌표를 찾을 때(stations.py) 지하철역 필터와 함께 써요.

    category: 특정 종류의 장소에서만 찾고 싶을 때 쓰는 카카오 카테고리 코드
              (예: "SW8" = 지하철역). 비워두면 모든 장소에서 찾습니다.

    예) get_coordinates("강남역") → (37.49..., 127.02...)
        get_coordinates("강남역", category="SW8") → 지하철역 중에서만 검색
    """
    # 무엇을 검색할지 알려주는 정보 (query = 검색어)
    params = {"query": place_name}

    # 카테고리를 지정했다면, 그 종류의 장소에서만 찾도록 조건을 추가합니다.
    if category:
        params["category_group_code"] = category

    documents = kakao_search(KAKAO_KEYWORD_URL, params)

    # 검색 결과가 하나도 없으면 None을 돌려줍니다.
    if not documents:
        return None

    # 가장 첫 번째(가장 정확한) 검색 결과를 사용합니다.
    first = documents[0]

    # 카카오는 y = 위도, x = 경도로 주고, 글자(문자열) 형태라서 숫자(float)로 바꿉니다.
    return float(first["y"]), float(first["x"])


def from_address_result(doc):
    """
    주소 검색 결과 하나를 {"name", "address", "lat", "lng"} 모양으로 바꿉니다.
    건물 이름이 있으면 그걸 이름으로 쓰고, 없으면 주소 자체를 이름으로 써요.
    """
    road = doc.get("road_address") or {}  # 도로명 주소 정보 (없으면 빈 딕셔너리)
    lot = doc.get("address") or {}  # 지번 주소 정보 (없으면 빈 딕셔너리)

    # 보여줄 주소: 도로명 주소가 있으면 도로명, 없으면 지번
    address = road.get("address_name") or lot.get("address_name") or doc["address_name"]
    # 보여줄 이름: 건물 이름이 있으면 건물 이름, 없으면 검색된 주소
    name = road.get("building_name") or doc["address_name"]

    return {"name": name, "address": address, "lat": float(doc["y"]), "lng": float(doc["x"])}


def from_keyword_result(doc):
    """키워드 검색 결과 하나를 {"name", "address", "lat", "lng"} 모양으로 바꿉니다."""
    # 도로명 주소가 있으면 도로명, 없으면 지번 주소를 보여줘요.
    address = doc.get("road_address_name") or doc.get("address_name", "")
    return {"name": doc["place_name"], "address": address, "lat": float(doc["y"]), "lng": float(doc["x"])}


def search_places(query, limit=MAX_RESULTS):
    """
    출발지 검색어(주소, 아파트·건물 이름, 역 이름 등)로 장소를 찾아
    최대 limit개를 돌려줍니다. 하나도 못 찾으면 빈 리스트 []를 돌려줘요.

    1) 주소 검색을 먼저 해보고 → 2) 결과가 없으면 키워드 검색으로 찾아요.
       (지하철역 필터는 쓰지 않아요. 집, 학교, 회사 어디서든 출발할 수 있으니까요)

    돌려주는 값 예시:
        [{"name": "서울특별시청", "address": "서울 중구 세종대로 110", "lat": 37.56..., "lng": 126.97...}, ...]
    """
    # 1) 주소 검색 (도로명 주소, 지번 주소)
    documents = kakao_search(KAKAO_ADDRESS_URL, {"query": query, "size": limit})
    if documents:
        return [from_address_result(doc) for doc in documents[:limit]]

    # 2) 주소로 못 찾았으면 키워드 검색 (아파트, 건물, 역 이름 등)
    documents = kakao_search(KAKAO_KEYWORD_URL, {"query": query, "size": limit})
    return [from_keyword_result(doc) for doc in documents[:limit]]


def place_text(place):
    """
    장소를 "이름 (주소)" 글자로 바꿉니다. (여러 결과 중에서 고르는 버튼에 써요)
    이름과 주소가 같으면(주소로 검색한 경우) 한 번만 보여줘요.
    """
    if not place["address"] or place["name"] == place["address"]:
        return place["name"]
    return f"{place['name']} ({place['address']})"


def place_label(place):
    """장소를 "📍 이름 (주소)" 글자로 바꿉니다. 사용자가 맞는 곳인지 확인할 때 써요."""
    return f"📍 {place_text(place)}"


# 아래 코드는 이 파일을 "직접 실행"할 때만 동작합니다.
# (다른 파일에서 함수를 가져다 쓸 때는 실행되지 않아요.)
if __name__ == "__main__":
    for query in ["강남역", "서울 중구 세종대로 110"]:
        print(f"🔎 '{query}'")
        results = search_places(query)
        if not results:
            print("   검색 결과가 없습니다.")
        for place in results:
            print(f"   {place_label(place)} → 위도 {place['lat']}, 경도 {place['lng']}")
