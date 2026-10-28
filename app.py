# app.py
# 역할: "오늘은여기서"의 웹 화면입니다. (실행: streamlit run app.py)
#
# Streamlit은 버튼을 누르거나 선택을 바꿀 때마다 이 파일을 "처음부터 다시" 실행해요.
# 그래서 다시 실행돼도 남아 있어야 하는 값(이동시간 표 등)은 st.session_state(사물함)에 넣어둡니다.

import html  # 사용자가 입력한 글자를 HTML에 안전하게 넣기 위한 도구
from datetime import time  # 약속 시각(예: 19:00)을 다루기 위한 도구
from urllib.parse import quote  # 링크 주소에 한글을 안전하게 넣기 위한 도구

import requests  # 카카오 서버 연결 오류를 알아보기 위한 도구
import streamlit as st  # 파이썬 코드를 웹 화면으로 바꿔주는 도구

import demo  # API 키가 없을 때 demo_data/만 쓰는 데모 모드 도구
import geocode  # 출발지 검색(주소 → 키워드 순서) 도구
from last_train import (
    MANY_RIDES_MESSAGE, clock_text, count_last_train_calls, has_bus, leg_text, meeting_end, plan_last_trains,
)
from recommend import (
    CRITERIA, DAY_TYPES, DEFAULT_CRITERION, DEFAULT_DAY_TYPE, build_travel_table,
    departure_text, find_saved_example, rank_stations, route_details, route_summary, same_top_station,
)
from stations import make_search_word  # "사당" → "사당역"
from transit import DAILY_LIMIT, get_remaining_calls, get_today_usage

# 친구는 최소 2명, 최대 3명까지 (ODsay 하루 30건 제한 때문)
MAX_FRIENDS = 3
MIN_FRIENDS = 2

# 출발지 입력칸 안내 문구
PLACE_HINT = "주소, 아파트 이름, 역 이름 모두 가능해요"

# 친구별 "귀가 목표 지점" 입력칸 (비워두면 출발지까지로 계산해요)
GOAL_LABEL = "🌙 막차로 꼭 도착해야 하는 곳 (선택)"
GOAL_HINT = "예: 수원역까지만 가면 택시 탈 수 있어요 · 비워두면 출발지까지"
GOAL_TIP = "지하철역으로 정하면 더 정확해요. 버스 막차는 노선 정보로 추정해서 실제와 다를 수 있거든요."
GOAL_SUBWAY_HINT = "💡 '막차로 꼭 도착해야 하는 곳'을 지하철역으로 정하면 더 정확해요."

# 모임 종료의 기준이 된 친구가 버스를 탈 때 보여줄 경고
BUS_WARNING = "버스 막차는 실제와 다를 수 있어요. 버스 시간표를 꼭 확인하세요."

# 막차 결과 아래에 작게 보여줄 안내
LAST_TRAIN_NOTE = (
    "경로는 평소 기준이라 밤늦게는 다를 수 있어요. "
    "버스는 노선 막차와 거리로 추정한 시각이에요(날짜 구분 없음)."
)

# 사이드바의 테스트 모드 스위치 이름
TEST_MODE_LABEL = "🧪 테스트 모드 (ODsay 호출 안 함)"

# API 키가 없으면 데모 모드: 메모장을 demo_data/로 바꾸고, 테스트 모드를 끌 수 없게 해요.
DEMO_MODE = demo.is_demo_mode()
if DEMO_MODE:
    demo.use_demo_data()
DEMO_GUIDE = (
    "API 키가 없어서 데모 모드로 실행 중이에요. '저장된 예시 불러오기'를 누르면 "
    "스타필드시티 위례 + 수원역 예시가 채워져요. 위례 친구의 '막차로 꼭 도착해야 하는 곳'에 "
    "복정역을 넣어볼 수도 있어요."
)

# 약속 시각 입력칸의 처음 값 (저녁 7시)
DEFAULT_MEETING_TIME = time(19, 0)

# 출발 시각 아래에 작게 보여줄 안내
TRAVEL_TIME_NOTE = "이동시간은 평균 기준이라 실제와 몇 분 다를 수 있어요"

# 결과 카드로 크게 보여줄 순위 개수 (나머지는 "다른 후보 보기"에 접어둬요)
CARD_COUNT = 3

# 기준별 이모지와 한 줄 설명 (화면에 보여줄 글자)
CRITERION_EMOJI = {"fair": "⚖️", "fast": "⚡"}
CRITERION_HELP = {
    "fair": "누구 한 명만 오래 걸리지 않게",
    "fast": "다 같이 이동하는 시간의 합이 가장 짧게",
}

# 이동시간 막대의 색 (밝은 화면과 어두운 화면 모두에서 잘 보이는 파랑)
BAR_COLOR = "#2a78d6"

# 막대 그래프의 모양 (한 번만 넣어두면 모든 카드의 막대에 적용돼요)
BAR_STYLE = """
<style>
.travel-bars { display: grid; grid-template-columns: minmax(4.5em, 28%) 1fr; gap: 6px 10px;
               align-items: center; margin: 4px 0 8px; }
.travel-bars .who { font-size: 0.9rem; overflow-wrap: anywhere; }
.travel-bars .track { display: flex; align-items: center; gap: 8px; min-width: 0; }
.travel-bars .bar { height: 14px; border-radius: 0 4px 4px 0; flex: none; }
.travel-bars .value { font-size: 0.85rem; white-space: nowrap; opacity: 0.8; }
</style>
"""

# 기본 기준(fair)이 라디오 버튼의 첫 번째가 되도록 순서를 정합니다.
CRITERION_ORDER = [DEFAULT_CRITERION] + [c for c in CRITERIA if c != DEFAULT_CRITERION]

# ─────────────────────────────────────────────
# 사물함(session_state) 준비: 처음 열었을 때 한 번만 기본값을 넣어요.
# ─────────────────────────────────────────────
if "friend_ids" not in st.session_state:
    # 친구마다 "번호표"를 줘요. 입력칸 이름(place_번호표)이 자리 순서와 상관없이 고정되어서,
    # 가운데 친구를 지워도 다른 친구의 입력값이 밀리거나 섞이지 않아요.
    st.session_state.friend_ids = list(range(MIN_FRIENDS))  # 처음엔 [0, 1] → 입력칸 2개
    st.session_state.next_friend_id = MIN_FRIENDS  # 다음에 추가될 친구의 번호표
if "table" not in st.session_state:
    st.session_state.table = None  # 이동시간 표 (아직 추천 전이라 비어 있음)
    st.session_state.table_places = []  # 그 표를 만들 때 쓴 출발지들 (이름, 위도, 경도)


def load_saved_example():
    """
    '저장된 예시 불러오기' 버튼을 누르면, 메모장(캐시)에 모든 구간이 있는 출발지 조합을
    입력칸에 채워줍니다. (버튼의 on_click으로 실행돼서, 입력칸이 그려지기 전에 값을 넣을 수 있어요)
    결과 안내는 사물함의 example_message에 넣어두고, 사이드바에서 보여줘요.
    """
    try:
        group = find_saved_example(find_places)
    except (requests.RequestException, ValueError) as error:
        st.session_state.example_message = ("error", f"예시를 찾는 중 문제가 생겼어요: {error}")
        return

    if group is None:
        st.session_state.example_message = (
            "warning", "저장된 예시가 없어요. 테스트 모드를 끄고 한 번 추천받으면 저장돼요.",
        )
        return

    # 기존 입력칸은 지우고, 새 번호표로 예시 수만큼 입력칸을 만들어 채워요.
    for friend_id in st.session_state.friend_ids:
        st.session_state.pop(f"place_{friend_id}", None)
        st.session_state.pop(f"goal_{friend_id}", None)
    start = st.session_state.next_friend_id
    st.session_state.friend_ids = list(range(start, start + len(group)))
    st.session_state.next_friend_id = start + len(group)
    for friend_id, name in zip(st.session_state.friend_ids, group):
        st.session_state[f"place_{friend_id}"] = name
    st.session_state.example_message = ("success", f"예시를 불러왔어요: {' + '.join(group)}")


def add_friend():
    """'+ 친구 추가' 버튼을 누르면 새 번호표를 가진 입력칸을 하나 늘립니다. (최대 3칸)"""
    if len(st.session_state.friend_ids) < MAX_FRIENDS:
        st.session_state.friend_ids.append(st.session_state.next_friend_id)
        st.session_state.next_friend_id += 1


def remove_friend(friend_id):
    """'✕' 버튼을 누르면 그 번호표의 입력칸을 지웁니다. (최소 2칸은 남겨요)"""
    if len(st.session_state.friend_ids) > MIN_FRIENDS:
        st.session_state.friend_ids.remove(friend_id)
        st.session_state.pop(f"place_{friend_id}", None)  # 지운 칸에 적혀 있던 글자도 정리
        st.session_state.pop(f"goal_{friend_id}", None)


@st.cache_data(show_spinner=False, max_entries=100)
def search_places(query):
    """
    카카오에서 출발지를 검색합니다. (geocode.search_places를 부르는 얇은 포장지)
    Streamlit은 화면을 자주 다시 그려서, 같은 검색어를 매번 카카오에 묻지 않도록
    결과를 "메모리"에만 잠깐 기억해둬요. (파일에는 저장하지 않아서 집 주소가 남지 않아요)
    """
    return geocode.search_places(query)


def find_places(query):
    """장소를 찾습니다. 데모 모드면 demo_data/의 예시 장소에서, 아니면 카카오에서 찾아요."""
    if DEMO_MODE:
        return demo.search_places(query)
    return search_places(query)


def choose_place(text, pick_key):
    """
    입력한 장소를 검색해서 사용자가 위치를 확인(또는 선택)하게 하고,
    고른 장소 {"name", "address", "lat", "lng"}를 돌려줍니다.
    빈칸이거나 찾지 못했으면 None을 돌려줘요.
    pick_key: 선택 버튼 이름에 쓰는 글자 (출발지는 친구 번호표, 귀가 목표 지점은 "goal_번호표")
    """
    if text == "":
        return None

    try:
        results = find_places(text)
    except (requests.RequestException, ValueError) as error:
        # 인터넷 문제, 카카오 키 문제 등 → 멈추지 않고 안내만
        st.error(f"'{text}' 검색 중 문제가 생겼어요: {error}")
        return None

    if not results:
        if DEMO_MODE:
            # 데모 모드에서는 예시 장소만 찾을 수 있다고 알려줘요
            names = ", ".join(demo.place_names())
            st.warning(f"'{text}'을(를) 찾을 수 없어요. 데모 모드에서는 이 장소만 쓸 수 있어요: {names}")
        else:
            st.warning(f"'{text}'을(를) 찾을 수 없어요. 주소나 이름을 다시 확인해주세요.")
        return None

    if len(results) == 1:
        chosen = results[0]
    else:
        # 결과가 여러 개면 상위 3개 중에서 고르게 해요.
        # 입력칸 이름에 검색어도 넣어서, 검색어를 바꾸면 선택이 처음(1번)으로 돌아가요.
        index = st.radio(
            "어느 곳인가요?",
            options=range(len(results)),
            format_func=lambda i: geocode.place_text(results[i]),  # 예: "롯데월드 (서울 송파구 ...)"
            key=f"pick_{pick_key}_{text}",
        )
        chosen = results[index]

    # 고른 위치를 "📍 이름 (주소)"로 보여줘서 맞는 곳인지 확인할 수 있게 해요.
    st.markdown(geocode.place_label(chosen))
    return chosen


def travel_bars_html(friends, routes, scale_max):
    """
    친구별 이동시간을 가로 막대 HTML로 만듭니다.
    scale_max: 막대 길이의 기준(분). 모든 카드가 같은 기준을 써야 카드끼리 비교가 공정해요.
    """
    rows = []
    for friend, route in zip(friends, routes):
        name = html.escape(friend)  # 사용자가 입력한 글자는 반드시 안전하게 바꿔서 넣어요
        detail = "도보" if route.get("walk") else f"환승 {route['transfers']}"
        label = f"{route['time_min']}분 · {detail}"  # 예: "28분 · 환승 1", "7분 · 도보"
        # 막대는 칸의 최대 80%까지만 → 오른쪽에 "28분 · 환승 1" 글자가 들어갈 자리를 남겨요
        width = 80 * route["time_min"] / scale_max if scale_max else 0
        rows.append(
            f'<div class="who">{name}</div>'
            f'<div class="track" title="{name} → {label}">'
            f'<div class="bar" style="width:{width:.1f}%; background:{BAR_COLOR}"></div>'
            f'<span class="value">{label}</span></div>'
        )
    return f'<div class="travel-bars">{"".join(rows)}</div>'


def kakao_map_url(station_name):
    """
    카카오맵에서 역을 검색한 화면의 링크를 만듭니다. (카카오 API를 부르지 않고 주소만 만들어요)
    예) "사당" → "https://map.kakao.com/?q=%EC%82%AC%EB%8B%B9%EC%97%AD" (한글은 %로 바꿔서 넣어요)
    """
    return f"https://map.kakao.com/?q={quote(make_search_word(station_name))}"


def show_station_card(rank, station, friends, scale_max, meeting_time):
    """
    후보역 하나를 카드(테두리 상자) 모양으로 보여줍니다.
    meeting_time: 약속 시각. 친구별 출발 시각을 계산할 때 써요.
    """
    with st.container(border=True):
        if rank == 1:
            st.markdown(f"### 🏆 1위 · {station['name']}역")
        else:
            st.markdown(f"#### {rank}위 · {station['name']}역")

        # 친구별 이동시간 가로 막대 (차이가 한눈에 보이게)
        st.markdown(travel_bars_html(friends, station["routes"], scale_max), unsafe_allow_html=True)

        # 친구별 경로 요약 한 줄
        for friend, route in zip(friends, station["routes"]):
            st.markdown(f"**{friend}** · {route_summary(route)}")

        st.caption(
            f"가장 오래 걸리는 친구 {station['max_time']}분 · "
            f"합계 {station['total_time']}분 · 차이 {station['gap']}분"
        )

        # 친구별 출발 시각 (이미 구한 이동시간으로 계산 → ODsay를 부르지 않아요)
        st.markdown("\n".join(
            f"- 🏠 {friend} 친구: **{departure_text(meeting_time, route)}**"
            for friend, route in zip(friends, station["routes"])
        ))
        st.caption(TRAVEL_TIME_NOTE)

        # 카카오맵에서 역 주변을 직접 둘러볼 수 있는 링크
        st.markdown(f"[🗺️ 카카오맵에서 주변 둘러보기]({kakao_map_url(station['name'])})")

        # 펼치면 구간별 자세한 경로가 보여요
        with st.expander("자세한 경로 보기"):
            for friend, route in zip(friends, station["routes"]):
                st.markdown(f"**{friend}에서 출발**")
                st.markdown("\n".join(f"- {line}" for line in route_details(route)))


def bus_map_url(bus_no):
    """
    카카오맵에서 버스 노선을 검색한 화면의 링크를 만듭니다. (카카오 API를 부르지 않고 주소만 만들어요)
    예) "3217" → "https://map.kakao.com/?q=3217%EB%B2%88%20%EB%B2%84%EC%8A%A4" ("3217번 버스"를 검색)
    """
    return f"https://map.kakao.com/?q={quote(f'{bus_no}번 버스')}"


def last_train_lines(friend, goal_name, result, station_name):
    """친구 한 명의 막차 결과를 화면용 목록 줄들로 바꿉니다. (구간별 줄은 한 칸 들여써요)"""
    head = f"- 🏠 **{friend}** 친구 → {goal_name}"
    status = result["status"]
    if status == "ok":
        lines = [f"{head}: 늦어도 **{clock_text(result['leave_by'])}**에 {station_name}역에서 출발 "
                 f"(타는 곳까지 도보 {result['walk_min']}분)"]
        lines += [f"    - {leg_text(leg)}" for leg in result["legs"]]
        return lines
    if status == "walk":
        return [f"{head}: 걸어서 {result['minutes']}분 거리라 막차 걱정이 없어요"]
    if status == "many":
        return [f"{head}: {MANY_RIDES_MESSAGE}"]
    if status == "unsure":
        return [f"{head}: ⚠️ 확인 필요 · {result['reason']}"]
    return [f"{head}: 귀갓길을 찾지 못했어요 ({result['reason']})"]  # status == "error"


def show_last_trains(top, friends, places, goal_texts, goal_places, day_type, meeting_time, test_mode):
    """
    1위 역에서 친구마다 귀가 목표 지점까지의 막차를 확인하는 부분입니다.
    '🌙 막차 확인하기' 버튼을 눌렀을 때만 ODsay를 부르고(테스트 모드면 안 불러요),
    그 뒤로는 날짜 종류를 바꿔도 메모장(캐시)의 시간표로 다시 계산해요.
    """
    st.subheader(f"🌙 귀갓길 막차 · {top['name']}역에서")

    if top.get("lat") is None:
        st.caption("이 역은 좌표가 없어서 막차를 확인할 수 없어요.")
        return
    if any(text and place is None for text, place in zip(goal_texts, goal_places)):
        st.warning("찾지 못한 '막차로 꼭 도착해야 하는 곳'이 있어요. 입력칸 아래 안내를 확인해주세요.")
        return

    station_coord = (top["lat"], top["lng"])
    # 목표 지점을 비워둔 친구는 출발지(집)까지로 계산해요
    goals = [(goal["lat"], goal["lng"]) if goal else (lat, lng)
             for goal, (name, lat, lng) in zip(goal_places, places)]
    goal_names = [goal["name"] if goal else "출발지" for goal in goal_places]
    # 어떤 조건으로 계산한 결과인지 (역·출발지·목표 지점이 바뀌면 옛 결과를 숨겨요)
    condition = (top["name"], tuple(places), tuple(goals))

    # 누르기 전에 필요한 ODsay 호출 수를 알려줘요
    needed, exact = count_last_train_calls(station_coord, goals)
    if test_mode:
        st.caption("🧪 테스트 모드: 저장된 경로와 시간표만 써요. (ODsay 0건)")
    elif needed == 0:
        st.caption("저장된 경로와 시간표로 바로 확인할 수 있어요. (ODsay 0건)")
    else:
        amount = f"{needed}건" if exact else f"최대 {needed}건"
        st.caption(f"ODsay {amount}이 필요해요 (오늘 남은 횟수 {get_remaining_calls()}건)")

    if st.button("🌙 막차 확인하기"):
        try:
            with st.spinner("막차 확인 중..."):
                plan_last_trains(station_coord, goals, day_type, offline=test_mode)
            st.session_state.last_train_for = condition
        except ValueError as error:
            # 한도 부족, 테스트 모드에서 저장된 결과 없음, 키 오류 등 → 멈추지 않고 안내만
            st.error(str(error))
            st.session_state.last_train_for = None
            return

    if st.session_state.get("last_train_for") != condition:
        if st.session_state.get("last_train_for") is not None:
            st.info("장소나 귀가 목표 지점이 바뀌었어요. '🌙 막차 확인하기'를 다시 눌러주세요.")
        return

    # 버튼으로 받아둔 메모장만 써서 다시 계산해요 (날짜 종류를 바꿔도 ODsay 0건)
    try:
        results = plan_last_trains(station_coord, goals, day_type, offline=True)
    except ValueError:
        st.info("저장된 시간표가 부족해요. '🌙 막차 확인하기'를 다시 눌러주세요.")
        return

    st.caption(f"📅 {DAY_TYPES[day_type]} 시간표 기준")
    end = meeting_end(results, friends)
    if end:
        st.success(f"이 모임은 {clock_text(end['end'])}까지 놀 수 있어요 ({end['friend']} 친구 기준)", icon="🌙")
        meeting_minutes = meeting_time.hour * 60 + meeting_time.minute
        if end["end"] <= meeting_minutes:
            st.warning(f"막차 때문에 약속 시각({meeting_time:%H:%M})보다 일찍 헤어져야 해요. 다른 장소도 고려해보세요.")

        # 기준이 된 친구가 버스를 타면: 버스 막차는 ODsay 노선 정보로 추정해서 틀릴 수 있어요
        # (3217번은 ODsay 23:45, 실제 22:45였어요) → 경고와 실제 시간표를 볼 수 있는 링크
        limiting = results[end["index"]]
        if has_bus(limiting):
            st.warning(BUS_WARNING, icon="⚠️")
            bus_numbers = [leg["bus_no"] for leg in limiting["legs"] if leg["type"] == "bus" and leg.get("bus_no")]
            if bus_numbers:
                st.markdown(" · ".join(f"[🚌 카카오맵에서 {no}번 버스 시간표 보기]({bus_map_url(no)})"
                                       for no in bus_numbers))

    lines = []
    for friend, goal_name, result in zip(friends, goal_names, results):
        lines += last_train_lines(friend, goal_name, result, top["name"])
    st.markdown("\n".join(lines))

    # 막차를 확실하게 계산하지 못한 친구는 모임 종료 시각에서 빠졌다고 알려줘요
    left_out = [f for f, r in zip(friends, results) if r["status"] in ("unsure", "many", "error")]
    if end and left_out:
        st.warning(f"{', '.join(left_out)} 친구는 확인이 필요해서 모임 종료 시각 계산에서 빠졌어요.", icon="⚠️")
    st.caption(LAST_TRAIN_NOTE)
    st.caption(GOAL_SUBWAY_HINT)


# ─────────────────────────────────────────────
# 0. 사이드바: 테스트 모드 (영상 녹화·연습용)
# ─────────────────────────────────────────────
with st.sidebar:
    # 켜져 있으면 ODsay를 절대 부르지 않고, 메모장(캐시)에 저장된 결과만 써요. 처음엔 켜져 있어요.
    # 데모 모드(API 키 없음)에서는 끌 수 없게 막아두고, 항상 테스트 모드로 동작해요.
    test_mode = st.toggle(TEST_MODE_LABEL, value=True, key="test_mode", disabled=DEMO_MODE) or DEMO_MODE
    if DEMO_MODE:
        st.caption(DEMO_GUIDE)
    else:
        st.caption("켜져 있으면 저장된 결과만 쓰고 ODsay 사용량이 늘지 않아요.")
    st.button("저장된 예시 불러오기", on_click=load_saved_example)

    # 예시 불러오기 결과 안내 (한 번 보여주면 사물함에서 꺼내서 지워요)
    message = st.session_state.pop("example_message", None)
    if message:
        kind, text = message
        {"success": st.success, "warning": st.warning, "error": st.error}[kind](text)

# ─────────────────────────────────────────────
# 1. 제목과 소개
# ─────────────────────────────────────────────
st.markdown(BAR_STYLE, unsafe_allow_html=True)  # 막대 그래프 모양 넣기
st.title("🚇 오늘은여기서")
st.write("친구들 모두에게 공정한 약속 장소 찾기")
if DEMO_MODE:
    st.info("데모 모드 · API 키 없이 저장된 예시(demo_data)만 써요. 사이드바의 '저장된 예시 불러오기'를 눌러보세요.", icon="🧪")
elif test_mode:
    # 녹화 화면에서도 테스트 모드인 걸 알 수 있게 위쪽에 표시해요
    st.info("테스트 모드 · ODsay를 부르지 않고 저장된 결과만 써요", icon="🧪")

# ─────────────────────────────────────────────
# 2. 친구 출발지 입력칸 (✕ 버튼은 3명일 때만 보여요)
# ─────────────────────────────────────────────
st.subheader("👥 친구들의 출발지")

can_remove = len(st.session_state.friend_ids) > MIN_FRIENDS
texts = []  # 입력칸에 적은 글자들
chosen_places = []  # 검색해서 고른 장소들 (못 찾았으면 None)
goal_texts = []  # 귀가 목표 지점 칸에 적은 글자들 (빈칸 = 출발지까지)
goal_places = []  # 검색해서 고른 귀가 목표 지점들 (빈칸이거나 못 찾았으면 None)

for position, friend_id in enumerate(st.session_state.friend_ids):
    label = f"친구 {position + 1} 출발지"
    key = f"place_{friend_id}"  # 번호표로 만든 입력칸 이름

    if can_remove:
        # 입력칸(넓게)과 ✕ 버튼(좁게)을 한 줄에 나란히 놓아요
        input_col, button_col = st.columns([6, 1], vertical_alignment="bottom")
        with input_col:
            text = st.text_input(label, key=key, placeholder=PLACE_HINT)
        with button_col:
            st.button("✕", key=f"remove_{friend_id}", on_click=remove_friend, args=(friend_id,),
                      help="이 친구 삭제")
    else:
        text = st.text_input(label, key=key, placeholder=PLACE_HINT)

    text = text.strip()  # 앞뒤 공백은 지워요
    texts.append(text)
    chosen_places.append(choose_place(text, friend_id))

    # 귀가 목표 지점 (선택). 비워두면 None → 출발지까지로 계산해요.
    goal_text = st.text_input(GOAL_LABEL, key=f"goal_{friend_id}", placeholder=GOAL_HINT, help=GOAL_TIP).strip()
    goal_texts.append(goal_text)
    goal_places.append(choose_place(goal_text, f"goal_{friend_id}") if goal_text else None)

# 결과 화면에 보여줄 친구별 출발지 이름과, 이동시간 계산에 쓸 좌표
# (출발지가 바뀌었는지 확인할 때도 이 목록을 비교해요. 빈칸·못 찾은 칸은 None으로 남겨서
#  친구를 추가해 빈칸이 생겨도 "바뀌었다"고 알아챌 수 있게 해요)
places = [(p["name"], p["lat"], p["lng"]) if p else None for p in chosen_places]

st.button(
    "+ 친구 추가",
    on_click=add_friend,
    disabled=len(st.session_state.friend_ids) >= MAX_FRIENDS,  # 3명이면 더 못 누르게
)
if len(st.session_state.friend_ids) >= MAX_FRIENDS:
    st.caption(f"대중교통 조회 한도(하루 {DAILY_LIMIT}건) 때문에 최대 {MAX_FRIENDS}명까지 입력할 수 있어요.")

# ─────────────────────────────────────────────
# 3. 추천 기준 선택
# ─────────────────────────────────────────────
st.subheader("⚖️ 추천 기준")
criterion = st.radio(
    "어떤 약속 장소가 좋을까요?",
    options=CRITERION_ORDER,
    format_func=lambda c: f"{CRITERION_EMOJI[c]} {CRITERIA[c]}",  # 화면에 보일 이름
    captions=[CRITERION_HELP[c] for c in CRITERION_ORDER],  # 각 기준 아래 작은 설명
    key="criterion",
)

# ─────────────────────────────────────────────
# 3-1. 약속 시각 (날짜 종류는 귀갓길 막차 시간표에서도 써요)
# ─────────────────────────────────────────────
st.subheader("🕖 약속 시각")
day_type = st.radio(
    "약속 날짜",
    options=list(DAY_TYPES),
    format_func=lambda d: DAY_TYPES[d],  # 화면에 보일 이름 (평일 / 토요일 / 일요일·공휴일)
    index=list(DAY_TYPES).index(DEFAULT_DAY_TYPE),
    horizontal=True,  # 가로로 한 줄에 나란히
    key="day_type",
)
meeting_time = st.time_input(
    "약속 시각", value=DEFAULT_MEETING_TIME,
    step=300,  # 5분(300초) 단위로 고르기
    key="meeting_time",
)

# ─────────────────────────────────────────────
# 4. 추천 버튼
# ─────────────────────────────────────────────
problem_shown = False  # 이번에 안내(경고/오류)를 보여줬는지

if st.button("약속 장소 추천받기", type="primary"):
    if any(text == "" for text in texts):
        # 빈 칸이 있을 때
        st.warning("비어 있는 출발지 칸이 있어요. 모든 친구의 출발지를 입력해주세요.")
        problem_shown = True
    elif any(place is None for place in chosen_places):
        # 찾지 못한 출발지가 있을 때 (입력칸 아래에 이미 어떤 칸인지 안내했어요)
        st.warning("찾지 못한 출발지가 있어요. 입력칸 아래 안내를 확인해주세요.")
        problem_shown = True
    else:
        try:
            # ODsay를 부를 수 있는 곳은 여기 한 군데뿐이에요. (버튼을 눌렀을 때만)
            # 후보역 개수는 친구 수에 맞춰 자동으로 정해져요. (2명 → 5곳, 3명 → 3곳)
            # 테스트 모드면 메모장(캐시)만 쓰고, 없으면 ODsay 대신 안내만 해요.
            with st.spinner("이동시간 계산 중..."):
                names = [name for name, lat, lng in places]
                coords = [(lat, lng) for name, lat, lng in places]
                table = build_travel_table(names, coords, offline=test_mode)
            st.session_state.table = table  # 사물함에 이동시간 표 저장
            st.session_state.table_places = places  # 어떤 출발지로 만든 표인지도 저장
        except ValueError as error:
            # 없는 장소, 오늘 한도 초과, 키 오류, 테스트 모드에서 저장된 결과 없음 등 → 멈추지 않고 안내만
            st.error(str(error))
            st.session_state.table = None
            problem_shown = True

# ─────────────────────────────────────────────
# 5. 결과 (사물함의 표로 순위만 계산 → 기준을 바꿔도 ODsay를 다시 부르지 않아요)
# ─────────────────────────────────────────────
table = st.session_state.table

if table is not None:
    if st.session_state.table_places != places:
        # 추천받은 뒤 출발지를 고쳤다면(친구 추가·삭제, 다른 위치 선택 포함), 옛날 결과는 숨기고 안내합니다.
        if not problem_shown:
            st.info("출발지가 바뀌었어요. '약속 장소 추천받기'를 다시 눌러주세요.")
    else:
        ranked, excluded = rank_stations(table, criterion)

        # 막대 길이의 기준 = 순위에 든 모든 역 중 가장 오래 걸리는 시간 (모든 카드가 같은 기준)
        scale_max = max((s["max_time"] for s in ranked), default=0)

        st.subheader(f"📍 추천 결과 · {CRITERION_EMOJI[criterion]} {CRITERIA[criterion]}")
        # 약속 시각을 바꿔도 사물함의 이동시간 표로 출발 시각만 다시 계산해요. (ODsay 호출 없음)
        st.caption(f"⏰ {DAY_TYPES[day_type]} {meeting_time:%H:%M} 약속 기준")

        # 두 기준의 1위가 같으면 알려줘요
        if same_top_station(table):
            st.success("두 기준 모두 같은 역을 추천해요. 모두에게 좋은 장소예요! 👍")

        for rank, station in enumerate(ranked[:CARD_COUNT], start=1):
            show_station_card(rank, station, table["friends"], scale_max, meeting_time)

        # 4위 이하는 스위치를 켜야 보여요.
        # (카드 안에 이미 펼치기(expander)가 있어서, 펼치기 안에 또 펼치기를 넣을 수 없기 때문에 스위치를 써요)
        others = ranked[CARD_COUNT:]
        if others and st.toggle(f"다른 후보 보기 ({len(others)}곳)", key="show_others"):
            for rank, station in enumerate(others, start=CARD_COUNT + 1):
                show_station_card(rank, station, table["friends"], scale_max, meeting_time)

        # 경로를 못 구해서 순위에서 빠진 역
        for station in excluded:
            st.warning(f"{station['name']}역은 순위에서 뺐어요. ({station['reason']})")

        if not ranked:
            st.error("모든 후보역의 경로를 구하지 못했어요. 다른 출발지로 시도해주세요.")
        else:
            # 1위 역에서 친구들이 집(또는 귀가 목표 지점)으로 가는 막차
            show_last_trains(ranked[0], table["friends"], places, goal_texts, goal_places,
                             day_type, meeting_time, test_mode)

# ─────────────────────────────────────────────
# 6. 오늘 ODsay 사용량 (항상 맨 아래에)
# ─────────────────────────────────────────────
st.divider()
st.caption(f"오늘 ODsay 사용량: {get_today_usage()}/{DAILY_LIMIT}건")
