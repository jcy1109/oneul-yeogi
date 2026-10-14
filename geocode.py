# geocode.py
# 역할: 장소 이름(예: "강남역")을 좌표(위도, 경도)로 바꿔주는 파일입니다.
# 카카오 로컬 API의 "키워드로 장소 검색" 기능을 사용합니다.

import os  # 컴퓨터의 환경 변수(숨겨둔 설정값)를 읽기 위한 도구

import requests  # 인터넷으로 다른 서버에 요청을 보내는 도구
from dotenv import load_dotenv  # .env 파일에 적힌 값을 불러오는 도구

# .env 파일을 읽어서, 그 안의 값들을 환경 변수로 등록합니다.
load_dotenv()

# 등록된 환경 변수 중에서 카카오 API 키를 꺼내옵니다.
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")

# 카카오 "키워드로 장소 검색" API의 주소
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def get_coordinates(place_name):
    """
    장소 이름을 받아서 (위도, 경도)를 돌려주는 함수입니다.
    검색 결과가 없으면 None을 돌려줍니다.

    예) get_coordinates("강남역") → (37.49..., 127.02...)
    """
    # API 키가 없으면 더 진행할 수 없으므로, 알기 쉬운 에러를 냅니다.
    if not KAKAO_REST_API_KEY:
        raise ValueError(".env 파일에 KAKAO_REST_API_KEY가 없습니다. 키를 먼저 넣어주세요.")

    # 카카오 서버에 "나 키 있는 사람이야"라고 알려주는 신분증 같은 정보
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}

    # 무엇을 검색할지 알려주는 정보 (query = 검색어)
    params = {"query": place_name}

    # 카카오 서버에 요청을 보냅니다. 10초 안에 답이 없으면 포기합니다.
    response = requests.get(KAKAO_KEYWORD_URL, headers=headers, params=params, timeout=10)

    # 서버가 에러를 돌려줬다면(예: 키가 틀림) 여기서 에러를 냅니다.
    response.raise_for_status()

    # 서버의 답장(JSON 형식)을 파이썬 딕셔너리로 바꿉니다.
    data = response.json()

    # 검색 결과 목록을 꺼냅니다.
    documents = data["documents"]

    # 검색 결과가 하나도 없으면 None을 돌려줍니다.
    if not documents:
        return None

    # 가장 첫 번째(가장 정확한) 검색 결과를 사용합니다.
    first = documents[0]

    # 카카오는 y = 위도, x = 경도로 주고, 글자(문자열) 형태라서 숫자(float)로 바꿉니다.
    latitude = float(first["y"])
    longitude = float(first["x"])

    return latitude, longitude


# 아래 코드는 이 파일을 "직접 실행"할 때만 동작합니다.
# (다른 파일에서 get_coordinates를 가져다 쓸 때는 실행되지 않아요.)
if __name__ == "__main__":
    place = "강남역"
    result = get_coordinates(place)

    if result is None:
        print(f"'{place}'에 대한 검색 결과가 없습니다.")
    else:
        lat, lng = result  # 위도와 경도를 각각 꺼냅니다.
        print(f"'{place}'의 좌표 → 위도: {lat}, 경도: {lng}")
