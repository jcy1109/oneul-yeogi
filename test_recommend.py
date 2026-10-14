# test_recommend.py
# 역할: recommend.py의 "순위 매기기"를 가짜 이동시간 표로 테스트합니다.
#
# ⚠️ 순위 함수는 ODsay를 부르지 않아요. 여기서는 가짜 표만 쓰기 때문에 호출 0번이에요.

from recommend import rank_stations


def make_table(stations):
    """
    가짜 이동시간 표를 간단히 만들어주는 도우미입니다.
    stations 예: {"A역": [90, 90], "B역": [40, 48]}  ← 친구별 소요시간(분)
    시간 대신 "X"를 넣으면 그 친구는 "경로 없음"이 됩니다.
    """
    table = {"friends": ["친구1", "친구2"], "stations": []}
    for name, times in stations.items():
        routes = []
        for t in times:
            if t == "X":
                routes.append({"error": "두 지점 사이의 대중교통 경로를 찾을 수 없어요."})
            else:
                routes.append({"time_min": t, "transfers": 1})
        table["stations"].append({"name": name, "routes": routes})
    return table


def names(table, criterion):
    """순위 결과에서 역 이름만 순서대로 뽑아줍니다."""
    ranked, _ = rank_stations(table, criterion)
    return [s["name"] for s in ranked]


# ─────────────────────────────────────────────
# 테스트들
# ─────────────────────────────────────────────

def test_equal_not_both_90():
    """[중요] 둘 다 90분(차이 0분)인 역이 equal에서 1위가 되면 안 돼요."""
    table = make_table({
        "모두90분역": [90, 90],  # 차이 0분, 최대 90분 → 공평하지만 둘 다 고생
        "적당역": [40, 48],  # 차이 8분, 최대 48분 → 거의 공평하고 훨씬 빠름
        "치우친역": [20, 70],  # 차이 50분
    })
    result = names(table, "equal")
    assert result[0] != "모두90분역", result
    assert result == ["적당역", "모두90분역", "치우친역"], result


def test_equal_gap_order():
    """equal: 차이가 10분보다 많이 나면, 차이가 작은 역이 위로 가야 해요."""
    table = make_table({
        "차이30역": [30, 60],  # 최대 60분이지만 차이 30분
        "차이5역": [55, 60],  # 최대 60분, 차이 5분
    })
    assert names(table, "equal") == ["차이5역", "차이30역"]


def test_equal_no_rock_paper_scissors():
    """equal: 두 개씩 비교하면 꼬이는 경우(가위바위보)에도 순서가 하나로 정해져야 해요."""
    table = make_table({
        "A역": [90, 90],  # 차이 0, 최대 90
        "B역": [42, 50],  # 차이 8, 최대 50  (A와 10분 이내 → 같은 그룹)
        "C역": [25, 40],  # 차이 15, 최대 40 (A와 10분 넘게 차이 → 다음 그룹)
    })
    # 첫 그룹(A, B)에서 최대 시간이 짧은 B → A, 그다음 그룹 C
    assert names(table, "equal") == ["B역", "A역", "C역"]


def test_care():
    """care: 가장 오래 걸리는 친구의 시간이 짧은 순. 같으면 합계가 작은 순."""
    table = make_table({
        "최대60_합100": [40, 60],
        "최대60_합80": [20, 60],
        "최대50_합95": [45, 50],
    })
    assert names(table, "care") == ["최대50_합95", "최대60_합80", "최대60_합100"]


def test_fast():
    """fast: 모든 친구의 시간 합계가 작은 순."""
    table = make_table({
        "합80": [10, 70],  # 한 명만 많이 고생하지만 합계는 작음
        "합95": [45, 50],
    })
    assert names(table, "fast") == ["합80", "합95"]
    assert names(table, "care") == ["합95", "합80"]  # 같은 표라도 care는 반대!


def test_default_is_care():
    """기준을 안 고르면 care로 정렬돼야 해요."""
    table = make_table({"합80": [10, 70], "합95": [45, 50]})
    ranked, _ = rank_stations(table)
    assert [s["name"] for s in ranked] == names(table, "care")


def test_excluded_station():
    """한 친구라도 경로를 못 구한 역은 순위에서 빠지고, 누구 때문인지 이유가 나와야 해요."""
    table = make_table({
        "정상역": [40, 50],
        "못가는역": [30, "X"],
    })
    for criterion in ["care", "fast", "equal"]:
        ranked, excluded = rank_stations(table, criterion)
        assert [s["name"] for s in ranked] == ["정상역"]
        assert excluded[0]["name"] == "못가는역"
        assert "친구2" in excluded[0]["reason"]  # 누구 경로가 문제인지 알려줌


def test_unknown_criterion():
    """없는 기준을 넣으면 친절한 안내가 나와야 해요."""
    table = make_table({"정상역": [40, 50]})
    try:
        rank_stations(table, "cheap")
        assert False, "오류가 나야 하는데 안 났어요"
    except ValueError as error:
        assert "알 수 없는 기준" in str(error)


# 이 파일을 직접 실행하면 위의 테스트들을 차례로 실행합니다.
if __name__ == "__main__":
    tests = [
        test_equal_not_both_90, test_equal_gap_order, test_equal_no_rock_paper_scissors,
        test_care, test_fast, test_default_is_care, test_excluded_station, test_unknown_criterion,
    ]
    for test in tests:
        test()  # 실패하면 여기서 AssertionError가 나며 멈춰요
        print(f"✅ {test.__name__}: {test.__doc__.strip().splitlines()[0]}")
    print(f"\n🎉 테스트 {len(tests)}개 모두 통과! (ODsay 실제 호출 0번)")
