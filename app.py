# app.py
# 역할: "오늘은여기서"의 웹 화면입니다. (실행: streamlit run app.py)
#
# Streamlit은 버튼을 누르거나 선택을 바꿀 때마다 이 파일을 "처음부터 다시" 실행해요.
# 그래서 다시 실행돼도 남아 있어야 하는 값(이동시간 표 등)은 st.session_state(사물함)에 넣어둡니다.

import html  # 사용자가 입력한 글자를 HTML에 안전하게 넣기 위한 도구

import streamlit as st  # 파이썬 코드를 웹 화면으로 바꿔주는 도구

from recommend import (
    CRITERIA, DEFAULT_CRITERION, build_travel_table,
    rank_stations, route_details, route_summary, same_top_station,
)
from transit import DAILY_LIMIT, get_today_usage

# 친구는 최소 2명, 최대 3명까지 (ODsay 하루 30건 제한 때문)
MAX_FRIENDS = 3
MIN_FRIENDS = 2

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
    st.session_state.table_places = []  # 그 표를 만들 때 쓴 출발지들


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


def show_station_card(rank, station, friends, scale_max):
    """후보역 하나를 카드(테두리 상자) 모양으로 보여줍니다."""
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

        # 펼치면 구간별 자세한 경로가 보여요
        with st.expander("자세한 경로 보기"):
            for friend, route in zip(friends, station["routes"]):
                st.markdown(f"**{friend}에서 출발**")
                st.markdown("\n".join(f"- {line}" for line in route_details(route)))


# ─────────────────────────────────────────────
# 1. 제목과 소개
# ─────────────────────────────────────────────
st.markdown(BAR_STYLE, unsafe_allow_html=True)  # 막대 그래프 모양 넣기
st.title("🚇 오늘은여기서")
st.write("친구들 모두에게 공정한 약속 장소 찾기")

# ─────────────────────────────────────────────
# 2. 친구 출발지 입력칸 (✕ 버튼은 3명일 때만 보여요)
# ─────────────────────────────────────────────
st.subheader("👥 친구들의 출발지")

can_remove = len(st.session_state.friend_ids) > MIN_FRIENDS
places = []  # 입력된 출발지들을 모을 리스트

for position, friend_id in enumerate(st.session_state.friend_ids):
    label = f"친구 {position + 1} 출발지"
    key = f"place_{friend_id}"  # 번호표로 만든 입력칸 이름

    if can_remove:
        # 입력칸(넓게)과 ✕ 버튼(좁게)을 한 줄에 나란히 놓아요
        input_col, button_col = st.columns([6, 1], vertical_alignment="bottom")
        with input_col:
            text = st.text_input(label, key=key, placeholder="예: 강남역, 홍익대학교")
        with button_col:
            st.button("✕", key=f"remove_{friend_id}", on_click=remove_friend, args=(friend_id,),
                      help="이 친구 삭제")
    else:
        text = st.text_input(label, key=key, placeholder="예: 강남역, 홍익대학교")

    places.append(text.strip())  # 앞뒤 공백은 지워요

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
# 4. 추천 버튼
# ─────────────────────────────────────────────
problem_shown = False  # 이번에 안내(경고/오류)를 보여줬는지

if st.button("약속 장소 추천받기", type="primary"):
    if any(place == "" for place in places):
        # 빈 칸이 있을 때
        st.warning("비어 있는 출발지 칸이 있어요. 모든 친구의 출발지를 입력해주세요.")
        problem_shown = True
    else:
        try:
            # ODsay를 부를 수 있는 곳은 여기 한 군데뿐이에요. (버튼을 눌렀을 때만)
            # 후보역 개수는 친구 수에 맞춰 자동으로 정해져요. (2명 → 5곳, 3명 → 3곳)
            with st.spinner("이동시간 계산 중..."):
                table = build_travel_table(places)
            st.session_state.table = table  # 사물함에 이동시간 표 저장
            st.session_state.table_places = places  # 어떤 출발지로 만든 표인지도 저장
        except ValueError as error:
            # 없는 장소, 오늘 한도 초과, 키 오류 등 → 멈추지 않고 안내만
            st.error(str(error))
            st.session_state.table = None
            problem_shown = True

# ─────────────────────────────────────────────
# 5. 결과 (사물함의 표로 순위만 계산 → 기준을 바꿔도 ODsay를 다시 부르지 않아요)
# ─────────────────────────────────────────────
table = st.session_state.table

if table is not None:
    if st.session_state.table_places != places:
        # 추천받은 뒤 출발지를 고쳤다면(친구 추가·삭제 포함), 옛날 결과는 숨기고 안내합니다.
        if not problem_shown:
            st.info("출발지가 바뀌었어요. '약속 장소 추천받기'를 다시 눌러주세요.")
    else:
        ranked, excluded = rank_stations(table, criterion)

        # 막대 길이의 기준 = 순위에 든 모든 역 중 가장 오래 걸리는 시간 (모든 카드가 같은 기준)
        scale_max = max((s["max_time"] for s in ranked), default=0)

        st.subheader(f"📍 추천 결과 · {CRITERION_EMOJI[criterion]} {CRITERIA[criterion]}")

        # 두 기준의 1위가 같으면 알려줘요
        if same_top_station(table):
            st.success("두 기준 모두 같은 역을 추천해요. 모두에게 좋은 장소예요! 👍")

        for rank, station in enumerate(ranked[:CARD_COUNT], start=1):
            show_station_card(rank, station, table["friends"], scale_max)

        # 4위 이하는 스위치를 켜야 보여요.
        # (카드 안에 이미 펼치기(expander)가 있어서, 펼치기 안에 또 펼치기를 넣을 수 없기 때문에 스위치를 써요)
        others = ranked[CARD_COUNT:]
        if others and st.toggle(f"다른 후보 보기 ({len(others)}곳)", key="show_others"):
            for rank, station in enumerate(others, start=CARD_COUNT + 1):
                show_station_card(rank, station, table["friends"], scale_max)

        # 경로를 못 구해서 순위에서 빠진 역
        for station in excluded:
            st.warning(f"{station['name']}역은 순위에서 뺐어요. ({station['reason']})")

        if not ranked:
            st.error("모든 후보역의 경로를 구하지 못했어요. 다른 출발지로 시도해주세요.")

# ─────────────────────────────────────────────
# 6. 오늘 ODsay 사용량 (항상 맨 아래에)
# ─────────────────────────────────────────────
st.divider()
st.caption(f"오늘 ODsay 사용량: {get_today_usage()}/{DAILY_LIMIT}건")
