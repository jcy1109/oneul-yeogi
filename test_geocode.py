# test_geocode.py
# 역할: geocode.py의 출발지 검색(주소 검색 → 키워드 검색)을 "가짜 답장"으로 테스트합니다.
#
# ⚠️ 이 테스트는 카카오를 실제로 부르지 않아요!
#    requests.get(진짜 우체부)을 가짜 우체부로 바꿔치기해서, 정해둔 가짜 답장만 돌려받습니다.
#    가짜 답장에는 공공장소만 써요. (실제 개인 주소는 절대 적지 않기!)

from unittest import mock  # 진짜 함수를 가짜로 바꿔치기하는 도구

import geocode  # 테스트할 파일

# ── 가짜 답장들 ──
# 주소 검색 결과: 도로명 주소 + 건물 이름이 있는 경우 (서울시청)
CITY_HALL_ADDRESS = {
    "address_name": "서울 중구 세종대로 110", "x": "126.978", "y": "37.5665",
    "road_address": {"address_name": "서울 중구 세종대로 110", "building_name": "서울특별시청"},
    "address": {"address_name": "서울 중구 태평로1가 31"},
}
# 주소 검색 결과: 건물 이름도, 도로명 주소도 없는 경우 (동 이름만 검색)
DONG_ADDRESS = {
    "address_name": "서울 중구 태평로1가", "x": "126.977", "y": "37.567",
    "road_address": None,
    "address": {"address_name": "서울 중구 태평로1가"},
}


def keyword_doc(name, address, lat, lng):
    """가짜 키워드 검색 결과 하나를 만들어줍니다."""
    return {"place_name": name, "road_address_name": address, "address_name": "", "y": str(lat), "x": str(lng)}


# 키워드 검색 결과 4개 (상위 3개만 남아야 해요)
LOTTE_WORLD = [
    keyword_doc("롯데월드 어드벤처", "서울 송파구 올림픽로 240", 37.511, 127.098),
    keyword_doc("롯데월드몰", "서울 송파구 올림픽로 300", 37.513, 127.104),
    keyword_doc("롯데월드 민속박물관", "서울 송파구 올림픽로 240", 37.511, 127.097),
    keyword_doc("롯데월드 아이스링크", "서울 송파구 올림픽로 240", 37.511, 127.099),
]


def fake_kakao(address_docs, keyword_docs):
    """
    가짜 카카오 우체부를 만듭니다.
    주소 검색 주소로 오면 address_docs를, 키워드 검색 주소로 오면 keyword_docs를 답장으로 줘요.
    """
    def postman(url, headers=None, params=None, timeout=None):
        response = mock.Mock()
        docs = address_docs if url == geocode.KAKAO_ADDRESS_URL else keyword_docs
        response.json.return_value = {"documents": docs[:params.get("size", 15)]}
        return response
    return mock.Mock(side_effect=postman)


def search(postman, query):
    """가짜 우체부로 search_places를 부릅니다."""
    with mock.patch("geocode.requests.get", postman), mock.patch("geocode.KAKAO_REST_API_KEY", "FAKE_KEY"):
        return geocode.search_places(query)


def called_urls(postman):
    """가짜 우체부가 어느 주소로 불려갔는지 순서대로 알려줍니다."""
    return [call.args[0] for call in postman.call_args_list]


# ─────────────────────────────────────────────
# 테스트들
# ─────────────────────────────────────────────

def test_address_found():
    """주소로 찾으면 키워드 검색은 하지 않고, 건물 이름과 도로명 주소를 돌려줘야 해요."""
    postman = fake_kakao([CITY_HALL_ADDRESS], LOTTE_WORLD)
    results = search(postman, "서울 중구 세종대로 110")

    assert results == [{"name": "서울특별시청", "address": "서울 중구 세종대로 110", "lat": 37.5665, "lng": 126.978}]
    assert called_urls(postman) == [geocode.KAKAO_ADDRESS_URL]  # 주소 검색 1번만


def test_address_without_building():
    """건물 이름이 없으면 주소를 이름으로 쓰고, 화면에는 한 번만 보여줘요."""
    results = search(fake_kakao([DONG_ADDRESS], []), "태평로1가")
    assert results[0]["name"] == "서울 중구 태평로1가"
    assert geocode.place_label(results[0]) == "📍 서울 중구 태평로1가"


def test_keyword_fallback():
    """주소로 못 찾으면 키워드 검색으로 넘어가고, 지하철역 필터(SW8)는 쓰지 않아야 해요."""
    postman = fake_kakao([], LOTTE_WORLD)
    results = search(postman, "롯데월드")

    assert called_urls(postman) == [geocode.KAKAO_ADDRESS_URL, geocode.KAKAO_KEYWORD_URL]
    keyword_params = postman.call_args_list[1].kwargs["params"]
    assert "category_group_code" not in keyword_params  # 아무 장소나 찾기
    assert results[0] == {"name": "롯데월드 어드벤처", "address": "서울 송파구 올림픽로 240",
                          "lat": 37.511, "lng": 127.098}


def test_top_3_only():
    """결과가 많아도 상위 3개만 돌려줘야 해요. (카카오에도 3개만 달라고 해요)"""
    postman = fake_kakao([], LOTTE_WORLD)
    results = search(postman, "롯데월드")

    assert [r["name"] for r in results] == ["롯데월드 어드벤처", "롯데월드몰", "롯데월드 민속박물관"]
    assert all(call.kwargs["params"]["size"] == 3 for call in postman.call_args_list)


def test_not_found():
    """주소로도 키워드로도 못 찾으면 빈 리스트를 돌려줘야 해요."""
    assert search(fake_kakao([], []), "ㅁㄴㅇㄹ존재하지않는곳") == []


def test_place_label():
    """확인 문구는 "📍 이름 (주소)" 모양이어야 해요."""
    place = {"name": "롯데월드몰", "address": "서울 송파구 올림픽로 300", "lat": 0, "lng": 0}
    assert geocode.place_label(place) == "📍 롯데월드몰 (서울 송파구 올림픽로 300)"
    assert geocode.place_text(place) == "롯데월드몰 (서울 송파구 올림픽로 300)"


def test_station_search_keeps_sw8():
    """후보역 좌표 검색(get_coordinates)은 지금처럼 지하철역 필터(SW8)를 그대로 써야 해요."""
    postman = fake_kakao([], [keyword_doc("강남역 2호선", "서울 강남구 강남대로 396", 37.498, 127.028)])
    with mock.patch("geocode.requests.get", postman), mock.patch("geocode.KAKAO_REST_API_KEY", "FAKE_KEY"):
        assert geocode.get_coordinates("강남역", category="SW8") == (37.498, 127.028)

    assert called_urls(postman) == [geocode.KAKAO_KEYWORD_URL]  # 역은 키워드 검색만
    assert postman.call_args.kwargs["params"]["category_group_code"] == "SW8"


# 이 파일을 직접 실행하면 위의 테스트들을 차례로 실행합니다.
if __name__ == "__main__":
    tests = [
        test_address_found, test_address_without_building, test_keyword_fallback,
        test_top_3_only, test_not_found, test_place_label, test_station_search_keeps_sw8,
    ]
    for test in tests:
        test()  # 실패하면 여기서 AssertionError가 나며 멈춰요
        print(f"✅ {test.__name__}: {test.__doc__.strip().splitlines()[0]}")
    print(f"\n🎉 테스트 {len(tests)}개 모두 통과! (카카오 실제 호출 0번)")
