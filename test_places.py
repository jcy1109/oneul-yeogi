# test_places.py
# 역할: places.py의 "역 주변 맛집·놀거리 찾기"를 "가짜 답장"으로 테스트합니다.
#
# ⚠️ 이 테스트는 카카오를 실제로 부르지 않아요! (ODsay도 당연히 안 불러요)
#    requests.get(진짜 우체부)을 가짜 우체부로 바꿔치기해서, 정해둔 가짜 답장만 돌려받습니다.

from unittest import mock  # 진짜 함수를 가짜로 바꿔치기하는 도구

import geocode
import places  # 테스트할 파일

SADANG = (37.47656, 126.98156)  # 테스트용 사당역 좌표


def place_doc(name, category, distance, place_id):
    """가짜 카카오 장소 검색 결과 하나를 만들어줍니다."""
    return {"place_name": name, "category_name": category, "distance": str(distance),
            "place_url": f"http://place.map.kakao.com/{place_id}", "x": "126.98", "y": "37.47",
            "road_address_name": "", "address_name": ""}


# 가짜 음식점 6곳 (최대 5곳만 남아야 해요)
FAKE_FOOD = [place_doc(f"가짜식당{i}", "음식점 > 한식 > 국밥", 100 * i, i) for i in range(1, 7)]


def fake_kakao(documents):
    """누가 요청하든 documents를 답장으로 주는 가짜 카카오 우체부 (size만큼만 잘라서 줘요)"""
    def postman(url, headers=None, params=None, timeout=None):
        response = mock.Mock()
        response.json.return_value = {"documents": documents[:params.get("size", 15)]}
        return response
    return mock.Mock(side_effect=postman)


def nearby(postman, kind, station_name="사당"):
    """가짜 우체부로 get_nearby_places를 부릅니다."""
    with mock.patch("geocode.requests.get", postman), mock.patch("geocode.KAKAO_REST_API_KEY", "FAKE_KEY"):
        return places.get_nearby_places(SADANG, kind, station_name)


# ─────────────────────────────────────────────
# 테스트들
# ─────────────────────────────────────────────

def test_food_keyword_accuracy():
    """음식점: "사당역 맛집" 키워드 검색 + 정확도순 + 음식점 카테고리 + 반경 500m로 찾아야 해요."""
    postman = fake_kakao(FAKE_FOOD)
    nearby(postman, "food")

    url = postman.call_args.args[0]
    params = postman.call_args.kwargs["params"]
    assert url == geocode.KAKAO_KEYWORD_URL
    assert params["query"] == "사당역 맛집"  # "사당" → "사당역 맛집"
    assert params["sort"] == "accuracy"
    assert params["category_group_code"] == "FD6"
    assert params["radius"] == 500 and params["size"] == 5
    assert (params["y"], params["x"]) == SADANG  # 카카오는 x = 경도, y = 위도


def test_food_query_no_double_station():
    """역 이름이 이미 "역"으로 끝나면 "서울역역 맛집"이 되지 않아야 해요."""
    postman = fake_kakao(FAKE_FOOD)
    nearby(postman, "food", station_name="서울역")
    assert postman.call_args.kwargs["params"]["query"] == "서울역 맛집"


def test_other_kinds_category_distance():
    """카페·문화시설·관광명소: 카테고리 검색 + 거리순 (키워드는 쓰지 않아요)"""
    for kind, code in [("cafe", "CE7"), ("culture", "CT1"), ("attraction", "AT4")]:
        postman = fake_kakao([])
        nearby(postman, kind)
        params = postman.call_args.kwargs["params"]
        assert postman.call_args.args[0] == places.KAKAO_CATEGORY_URL, kind
        assert params["category_group_code"] == code, kind
        assert params["sort"] == "distance", kind
        assert params["radius"] == 500, kind
        assert "query" not in params, kind


def test_place_fields():
    """각 장소는 이름, 세부 카테고리, 역에서 거리(숫자), 카카오맵 링크를 가져야 하고, 최대 5곳이에요."""
    found = nearby(fake_kakao(FAKE_FOOD), "food")
    assert len(found) == 5
    assert found[0] == {"name": "가짜식당1", "category": "한식 > 국밥", "distance_m": 100,
                        "url": "http://place.map.kakao.com/1"}


def test_short_category():
    """세부 카테고리: 맨 앞의 큰 분류만 빼요."""
    assert places.short_category("음식점 > 한식 > 국밥") == "한식 > 국밥"
    assert places.short_category("문화,예술 > 영화,영화관 > CGV") == "영화,영화관 > CGV"
    assert places.short_category("카페") == "카페"  # 나눌 게 없으면 그대로


def test_nothing_found():
    """주변에 아무것도 없으면 빈 리스트를 돌려줘야 해요. (화면에서 "주변에 찾은 곳이 없어요" 안내)"""
    assert nearby(fake_kakao([]), "attraction") == []


def test_unknown_kind():
    """없는 종류를 넣으면 친절한 안내가 나와야 해요."""
    try:
        places.get_nearby_places(SADANG, "bar", "사당")
        assert False, "오류가 나야 하는데 안 났어요"
    except ValueError as error:
        assert "알 수 없는 종류" in str(error)


def test_find_station():
    """역 이름으로 찾을 때는 "역"을 붙여서 지하철역(SW8)에서만 찾아야 해요."""
    station = place_doc("사당역 2호선", "교통,수송 > 지하철,전철 > 수도권2호선", 0, 99)
    station["road_address_name"] = "서울 동작구 남부순환로 지하2089"
    postman = fake_kakao([station])
    with mock.patch("geocode.requests.get", postman), mock.patch("geocode.KAKAO_REST_API_KEY", "FAKE_KEY"):
        found = places.find_station("사당")
        missing_postman = fake_kakao([])
    with mock.patch("geocode.requests.get", missing_postman), mock.patch("geocode.KAKAO_REST_API_KEY", "FAKE_KEY"):
        missing = places.find_station("없는역이름")

    params = postman.call_args.kwargs["params"]
    assert params["query"] == "사당역" and params["category_group_code"] == "SW8"
    assert found == {"name": "사당역 2호선", "address": "서울 동작구 남부순환로 지하2089", "lat": 37.47, "lng": 126.98}
    assert missing is None


# 이 파일을 직접 실행하면 위의 테스트들을 차례로 실행합니다.
if __name__ == "__main__":
    tests = [
        test_food_keyword_accuracy, test_food_query_no_double_station, test_other_kinds_category_distance,
        test_place_fields, test_short_category, test_nothing_found, test_unknown_kind, test_find_station,
    ]
    for test in tests:
        test()  # 실패하면 여기서 AssertionError가 나며 멈춰요
        print(f"✅ {test.__name__}: {test.__doc__.strip().splitlines()[0]}")
    print(f"\n🎉 테스트 {len(tests)}개 모두 통과! (카카오·ODsay 실제 호출 0번)")
