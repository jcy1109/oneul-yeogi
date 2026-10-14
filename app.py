# app.py
# 역할: "오늘은여기서"의 웹 화면입니다. (실행: streamlit run app.py)
#
# Streamlit은 버튼을 누르거나 선택을 바꿀 때마다 이 파일을 "처음부터 다시" 실행해요.
# 그래서 다시 실행돼도 남아 있어야 하는 값(이동시간 표 등)은 st.session_state(사물함)에 넣어둡니다.

import streamlit as st  # 파이썬 코드를 웹 화면으로 바꿔주는 도구

from recommend import CRITERIA, DEFAULT_CRITERION, build_travel_table, describe_route, rank_stations
from transit import DAILY_LIMIT, get_today_usage

# 친구는 최대 3명까지 (ODsay 하루 30건 제한 때문)
MAX_FRIENDS = 3
MIN_FRIENDS = 2

# 기준별 이모지와 한 줄 설명 (화면에 보여줄 글자)
CRITERION_EMOJI = {"care": "🧡", "fast": "⚡", "equal": "⚖️"}
CRITERION_HELP = {
    "care": "가장 오래 걸리는 친구의 이동시간을 가장 짧게 만들어요",
    "fast": "모든 친구의 이동시간을 더한 값이 가장 작은 곳을 골라요",
    "equal": "친구들끼리 걸리는 시간이 최대한 비슷한 곳을 골라요",
}

# 기본 기준(care)이 라디오 버튼의 첫 번째가 되도록 순서를 정합니다.
CRITERION_ORDER = [DEFAULT_CRITERION] + [c for c in CRITERIA if c != DEFAULT_CRITERION]

# ─────────────────────────────────────────────
# 사물함(session_state) 준비: 처음 열었을 때 한 번만 기본값을 넣어요.
# ─────────────────────────────────────────────
if "friend_count" not in st.session_state:
    st.session_state.friend_count = MIN_FRIENDS  # 처음엔 입력칸 2개
if "table" not in st.session_state:
    st.session_state.table = None  # 이동시간 표 (아직 추천 전이라 비어 있음)
    st.session_state.table_places = []  # 그 표를 만들 때 쓴 출발지들


def add_friend():
    """'+ 친구 추가' 버튼을 누르면 입력칸을 하나 늘립니다. (최대 3칸)"""
    if st.session_state.friend_count < MAX_FRIENDS:
        st.session_state.friend_count += 1


def show_station_card(rank, station, friends):
    """후보역 하나를 카드(테두리 상자) 모양으로 보여줍니다."""
    with st.container(border=True):
        if rank == 1:
            st.markdown(f"### 🏆 1위 · {station['name']}역")
        else:
            st.markdown(f"#### {rank}위 · {station['name']}역")

        # 친구별 소요시간과 환승 횟수
        for friend, route in zip(friends, station["routes"]):
            st.markdown(f"- **{friend}** → {describe_route(route)}")

        st.caption(
            f"가장 오래 걸리는 친구 {station['max_time']}분 · "
            f"합계 {station['total_time']}분 · 차이 {station['gap']}분"
        )


# ─────────────────────────────────────────────
# 1. 제목과 소개
# ─────────────────────────────────────────────
st.title("🚇 오늘은여기서")
st.write("친구들 모두에게 공정한 약속 장소 찾기")

# ─────────────────────────────────────────────
# 2. 친구 출발지 입력칸
# ─────────────────────────────────────────────
st.subheader("👥 친구들의 출발지")

places = []  # 입력된 출발지들을 모을 리스트
for i in range(st.session_state.friend_count):
    text = st.text_input(f"친구 {i + 1} 출발지", key=f"place_{i}", placeholder="예: 강남역, 홍익대학교")
    places.append(text.strip())  # 앞뒤 공백은 지워요

st.button(
    "+ 친구 추가",
    on_click=add_friend,
    disabled=st.session_state.friend_count >= MAX_FRIENDS,  # 3명이면 더 못 누르게
)
if st.session_state.friend_count >= MAX_FRIENDS:
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
        # 추천받은 뒤 출발지를 고쳤다면, 옛날 결과는 숨기고 안내합니다.
        if not problem_shown:
            st.info("출발지가 바뀌었어요. '약속 장소 추천받기'를 다시 눌러주세요.")
    else:
        ranked, excluded = rank_stations(table, criterion)

        st.subheader(f"📍 추천 결과 · {CRITERION_EMOJI[criterion]} {CRITERIA[criterion]}")
        for rank, station in enumerate(ranked, start=1):
            show_station_card(rank, station, table["friends"])

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
