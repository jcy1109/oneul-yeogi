# transit.py
# 역할: 두 지점 사이의 "실제 대중교통 이동시간"을 ODsay API로 알아내는 파일입니다.
#
# ODsay는 하루에 30번까지만 부를 수 있어서, 두 가지 장치를 두었어요.
#   1) 캐시(메모장): 한 번 물어본 구간은 data/transit_cache.json에 적어두고 다시 묻지 않기
#   2) 호출 기록부: 오늘 몇 번 불렀는지 data/odsay_usage.json에 세어서 30번이 되면 멈추기

import json  # 메모장/기록부를 JSON 파일로 읽고 쓰기 위한 도구
import os  # 환경 변수와 파일 경로를 다루기 위한 도구
import re  # 문장 안에서 특정 단어를 찾기 위한 도구
from datetime import datetime, timedelta, timezone  # 오늘 날짜(한국 시간)를 알기 위한 도구

import requests  # 인터넷으로 다른 서버에 요청을 보내는 도구
from dotenv import load_dotenv  # .env 파일에 적힌 값을 불러오는 도구

# .env 파일을 읽어서 ODsay API 키를 꺼내옵니다.
load_dotenv()
ODSAY_API_KEY = os.getenv("ODSAY_API_KEY")

# ODsay "대중교통 길찾기" API의 주소
ODSAY_PATH_URL = "https://api.odsay.com/v1/api/searchPubTransPathT"

# 하루 최대 호출 횟수
DAILY_LIMIT = 30

# 메모장(캐시)과 호출 기록부 파일 위치
CACHE_PATH = os.path.join("data", "transit_cache.json")
CACHE_BACKUP_PATH = os.path.join("data", "transit_cache.backup.json")  # 메모장 제목을 바꾸기 전 원본
USAGE_PATH = os.path.join("data", "odsay_usage.json")

# 한국 시간(UTC+9). ODsay의 "하루"는 한국 시간 기준이라서 이걸로 날짜를 셉니다.
KST = timezone(timedelta(hours=9))


# 테스트 모드에서 메모장에 없는 구간을 만났을 때 보여줄 안내
OFFLINE_MISS_MESSAGE = "테스트 모드에서는 저장된 결과가 없어요."


class OfflineMissError(ValueError):
    """
    테스트 모드(ODsay 호출 안 함)인데 메모장에 기록이 없을 때 생기는 오류입니다.
    (ValueError의 한 종류라서, 화면에서는 다른 오류처럼 안내만 하고 멈추지 않아요.)
    """


class NoRouteError(ValueError):
    """
    "경로 없음" 또는 "너무 가까움"처럼, 다시 물어봐도 결과가 똑같은 오류입니다.
    이런 오류는 메모장에 적어두고 다음엔 ODsay를 부르지 않아요.
    (ValueError의 한 종류라서, except ValueError로도 똑같이 잡을 수 있어요.)
    """


# ─────────────────────────────────────────────
# JSON 파일 읽기/쓰기 도우미
# ─────────────────────────────────────────────

def read_json(path, default):
    """JSON 파일을 읽습니다. 파일이 없으면 default 값을 돌려줍니다."""
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    """데이터를 JSON 파일로 저장합니다. 폴더가 없으면 만듭니다."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# 호출 기록부 (오늘 몇 번 불렀는지)
# ─────────────────────────────────────────────

def today_kst():
    """오늘 날짜를 "2026-10-14" 같은 글자로 돌려줍니다. (한국 시간 기준)"""
    return datetime.now(KST).strftime("%Y-%m-%d")


def get_today_usage():
    """오늘 ODsay를 몇 번 불렀는지 돌려줍니다. 날짜가 바뀌었으면 0이에요."""
    usage = read_json(USAGE_PATH, {"date": today_kst(), "count": 0})

    # 기록부의 날짜가 오늘이 아니면 = 새로운 날 → 0부터 다시 셉니다.
    if usage["date"] != today_kst():
        return 0
    return usage["count"]


def add_one_usage():
    """ODsay를 1번 불렀다고 기록부에 적습니다."""
    write_json(USAGE_PATH, {"date": today_kst(), "count": get_today_usage() + 1})


def get_remaining_calls():
    """오늘 ODsay를 몇 번 더 부를 수 있는지 돌려줍니다."""
    return max(DAILY_LIMIT - get_today_usage(), 0)


# ─────────────────────────────────────────────
# 메모장(캐시)
# ─────────────────────────────────────────────

def make_cache_key(start, end):
    """
    출발-도착 좌표로 메모장의 "제목"을 만듭니다.

    출발지와 도착지 모두 소수점 3자리(약 100m)로 반올림해요.
    → 귀갓길(추천역 → 집)처럼 도착지가 집이어도 정확한 집 위치가 메모장에 남지 않아요.
      ("○○아파트 101동"이 아니라 "○○동 근처"까지만 적는 셈이에요)
    → 같은 동네(약 100m 안)끼리는 기록을 함께 써요.
    예) "37.498,127.028->37.372,126.943"
    """
    return f"{start[0]:.3f},{start[1]:.3f}->{end[0]:.3f},{end[1]:.3f}"


def migrate_cache_keys():
    """
    예전 모양의 메모장 제목(도착지 소수점 5자리)을 새 모양(출발지·도착지 모두 3자리)으로 옮깁니다.
    옮기기 전에 원본을 data/transit_cache.backup.json에 그대로 복사해둬요. (백업이 이미 있으면 덮어쓰지 않아요)
    여러 기록이 같은 새 제목이 되면(100m 안의 두 장소) 처음 것만 남겨요.

    돌려주는 값: (바뀐 제목 수, 겹쳐서 버린 기록 수). 이미 새 모양이면 (0, 0)이고 아무 파일도 건드리지 않아요.
    """
    cache = read_json(CACHE_PATH, {})
    migrated = {}
    changed = 0
    dropped = 0
    for key, value in cache.items():
        # "37.498,127.028->37.37247,126.94347" → 숫자 4개를 꺼내서 다시 반올림
        start_text, end_text = key.split("->")
        start = [float(x) for x in start_text.split(",")]
        end = [float(x) for x in end_text.split(",")]
        new_key = make_cache_key(start, end)
        if new_key != key:
            changed += 1
        if new_key in migrated:
            dropped += 1  # 같은 동네의 두 기록 → 처음 것만 남겨요
            continue
        migrated[new_key] = value

    if changed == 0:
        return 0, 0  # 이미 새 모양이라 할 일이 없어요

    if not os.path.exists(CACHE_BACKUP_PATH):
        write_json(CACHE_BACKUP_PATH, cache)  # 원본 그대로 백업
    write_json(CACHE_PATH, migrated)
    return changed, dropped


def is_usable_cache(saved, detailed=False):
    """
    메모장의 기록을 그대로 써도 되는지 확인합니다.
    - "경로 없음" 기록 → 써도 돼요
    - 경로 정보(segments)가 있는 기록 → 써도 돼요
    - 예전에 저장해서 경로 정보가 없는 기록 → 다시 물어봐야 해요
    detailed=True면 (막차 계산용) 탈것 구간마다 "타는 곳 코드(start_id)"까지 있어야 써요.
    """
    if "error" in saved:
        return True
    if "segments" not in saved:
        return False
    if detailed:
        return all("start_id" in seg for seg in saved["segments"] if seg["type"] != "walk")
    return True


def is_cached(start, end, detailed=False):
    """이 구간을 메모장에서 꺼내 쓸 수 있으면 True (= ODsay를 부르지 않아도 됨)"""
    saved = read_json(CACHE_PATH, {}).get(make_cache_key(start, end))
    return saved is not None and is_usable_cache(saved, detailed)


# ─────────────────────────────────────────────
# ODsay 부르기 (길찾기, 시간표, 버스 노선 모두 여기를 거쳐요 → 하루 한도를 함께 세요)
# ─────────────────────────────────────────────

def call_odsay(url, params):
    """
    ODsay에 요청을 1번 보내고 답장(딕셔너리)을 돌려줍니다.
    보내기 전에 오늘 한도와 API 키를 확인하고, 호출 기록부에 1번 적어요.
    문제가 생기면 한국어 설명이 담긴 ValueError를 일으킵니다.
    """
    # 오늘 한도를 다 썼으면 ODsay를 부르지 않고 안내합니다.
    if get_today_usage() >= DAILY_LIMIT:
        raise ValueError(f"오늘 대중교통 조회 한도를 다 썼어요. ({DAILY_LIMIT}건) 내일 다시 시도해주세요.")

    # API 키가 없으면 더 진행할 수 없으므로 알려줍니다.
    if not ODSAY_API_KEY:
        raise ValueError(".env 파일에 ODSAY_API_KEY가 없습니다. 키를 먼저 넣어주세요.")

    # 보내기 직전에 기록부에 1번 적습니다.
    # (보낸 뒤 오류가 나더라도 ODsay 쪽에서는 횟수가 줄었을 수 있으니, 넉넉하게 셉니다.)
    add_one_usage()

    # ODsay 서버에 요청을 보냅니다. 인터넷 문제가 생기면 친절한 메시지로 바꿔줍니다.
    try:
        response = requests.get(url, params={**params, "apiKey": ODSAY_API_KEY}, timeout=10)
        return response.json()  # 답장(JSON)을 파이썬 딕셔너리로 바꾸기
    except requests.RequestException:
        raise ValueError("ODsay 서버에 연결하지 못했어요. 인터넷 연결을 확인해주세요.")
    except ValueError:
        # 답장이 JSON 형식이 아닐 때 (서버 점검 등)
        raise ValueError("ODsay 서버가 이상한 답장을 보냈어요. 잠시 후 다시 시도해주세요.")


# ─────────────────────────────────────────────
# 핵심 함수
# ─────────────────────────────────────────────

def get_transit_info(start, end, offline=False, detailed=False):
    """
    출발 좌표와 도착 좌표를 받아서, 가장 빠른 대중교통 경로의 정보를 돌려줍니다.

    start, end: (위도, 경도) 형태의 좌표. get_coordinates()가 돌려주는 모양과 같아요.
    offline: True면 "테스트 모드"예요. 메모장만 보고, 없으면 ODsay를 부르지 않고 OfflineMissError를 일으켜요.
    detailed: True면 (막차 계산용) 타는 곳 코드까지 저장된 기록만 써요. 예전 기록이면 다시 물어봐요.

    돌려주는 값 예시:
        {"time_min": 40, "transfers": 1, "fare": 1850,
         "segments": [ {"type": "walk", "minutes": 1, "distance_m": 37},
                       {"type": "subway", "line": "2호선", "start": "강남", "end": "사당",
                        "minutes": 9, "stations": 4}, ... ]}

    문제가 생기면 한국어 설명이 담긴 ValueError를 일으킵니다.
    """
    key = make_cache_key(start, end)
    cache = read_json(CACHE_PATH, {})

    # 1) 메모장에 쓸 수 있는 기록이 있으면 ODsay를 부르지 않고 바로 돌려줍니다.
    #    (경로 정보가 없는 예전 기록이면 아래로 내려가서 다시 물어봐요)
    if key in cache and is_usable_cache(cache[key], detailed):
        saved = cache[key]
        if "error" in saved:  # "경로 없음"이 적혀 있던 구간
            raise NoRouteError(saved["error"])
        return saved

    # 테스트 모드에서는 메모장에 없으면 여기서 멈춰요. (ODsay를 절대 부르지 않아요)
    if offline:
        raise OfflineMissError(OFFLINE_MISS_MESSAGE)

    start_lat, start_lng = start  # 출발지 위도, 경도 꺼내기
    end_lat, end_lng = end  # 도착지 위도, 경도 꺼내기

    # ODsay에는 반올림하지 않은 정확한 좌표를 보내요. (그래야 집에서 역까지 걷는 시간이 정확해요)
    # 메모장에 적을 때만 위의 make_cache_key가 대략적인 위치로 바꿔줘요.
    # ODsay는 X = 경도, Y = 위도로 받습니다. (순서 주의!)
    params = {"SX": start_lng, "SY": start_lat, "EX": end_lng, "EY": end_lat}

    # 2) ODsay에 물어봅니다. (한도·키 확인과 호출 기록은 call_odsay가 해줘요)
    data = call_odsay(ODSAY_PATH_URL, params)

    # 3) 결과를 메모장에 적어둡니다. ("경로 없음"도 적어둬요. 키 오류 등은 적지 않아요.)
    try:
        result = parse_transit_response(data)
    except NoRouteError as error:
        cache[key] = {"error": str(error)}
        write_json(CACHE_PATH, cache)
        raise

    cache[key] = result
    write_json(CACHE_PATH, cache)
    return result


def parse_transit_response(data):
    """
    ODsay가 보낸 답장(딕셔너리)에서 필요한 정보만 꺼냅니다.
    (서버 요청과 분리해두면, API 호출 없이도 이 부분만 따로 테스트할 수 있어요.)
    """
    # 답장에 "error"가 있으면 무슨 문제인지 한국어로 알려줍니다.
    # (ODsay는 오류가 나도 HTTP 상태 코드가 200이라서, 답장 안의 "error"를 직접 확인해야 해요.)
    if "error" in data:
        message, is_no_route = explain_odsay_error(data["error"])
        if is_no_route:
            raise NoRouteError(message)
        raise ValueError(message)

    paths = data.get("result", {}).get("path", [])

    # 경로가 하나도 없으면 알려줍니다.
    if not paths:
        raise NoRouteError("대중교통 경로를 찾을 수 없어요.")

    # 각 경로를 우리가 쓰기 쉬운 모양으로 정리합니다.
    options = []
    for path in paths:
        info = path["info"]  # 경로의 요약 정보

        # busTransitCount, subwayTransitCount는 "탄 횟수"라서,
        # 전부 더한 뒤 1을 빼야 "갈아탄 횟수(환승)"가 됩니다.
        rides = info["busTransitCount"] + info["subwayTransitCount"]
        transfers = max(rides - 1, 0)  # 혹시 음수가 되지 않도록 0 아래로는 안 내려가게

        options.append({
            "time_min": info["totalTime"],  # 총 소요시간(분)
            "transfers": transfers,  # 환승 횟수
            "fare": info["payment"],  # 요금(원)
            "segments": parse_segments(path.get("subPath", [])),  # 구간별 경로 안내
        })

    # 가장 좋은 경로 = 시간이 가장 짧은 경로 (시간이 같으면 환승이 적은 쪽)
    best = min(options, key=lambda o: (o["time_min"], o["transfers"]))
    return best


def parse_segments(sub_paths):
    """
    ODsay의 구간 목록(subPath)을 우리가 쓰기 쉬운 모양으로 바꿉니다.
    trafficType: 1 = 지하철, 2 = 버스, 3 = 도보
    """
    segments = []
    for sub in sub_paths:
        kind = sub.get("trafficType")
        minutes = sub.get("sectionTime", 0)  # 이 구간에 걸리는 시간(분)

        if kind == 3:  # 도보
            segments.append({"type": "walk", "minutes": minutes, "distance_m": sub.get("distance", 0)})
            continue

        lanes = sub.get("lane", [])  # 이 구간을 다니는 노선 목록
        if kind == 1:  # 지하철: "수도권 2호선" → "2호선"
            line = lanes[0]["name"].replace("수도권 ", "") if lanes else "지하철"
            seg_type = "subway"
        else:  # 버스: 같은 정류장 사이를 다니는 버스가 여러 대일 수 있어서 3개까지 함께 보여줘요
            line = "/".join(lane["busNo"] for lane in lanes[:3]) + "번" if lanes else "버스"
            seg_type = "bus"

        segment = {
            "type": seg_type,
            "line": line,  # 호선 또는 버스 번호
            "start": sub.get("startName", ""),  # 타는 역(정류장)
            "end": sub.get("endName", ""),  # 내리는 역(정류장)
            "minutes": minutes,
            "stations": sub.get("stationCount", 0),  # 몇 정거장 가는지
            # ↓ 막차 계산에 쓰는 값들 (ODsay 시간표·버스 노선 API에 그대로 넣어요)
            "start_id": sub.get("startID"),  # 타는 역(정류장) 코드
            "end_id": sub.get("endID"),  # 내리는 역(정류장) 코드
        }
        if kind == 1:
            segment["way_code"] = sub.get("wayCode")  # 방향: 1 = 상행, 2 = 하행
            # 지나가는 역 이름들 (타는 역 ~ 내리는 역). 막차의 종착역이 내릴 역까지 가는지 확인할 때 써요.
            stops = sub.get("passStopList", {}).get("stations", [])
            segment["stops"] = [stop["stationName"] for stop in stops]
        else:
            segment["bus_ids"] = [lane.get("busID") for lane in lanes]  # 버스 노선 코드들
        segments.append(segment)
    return segments


def explain_odsay_error(error):
    """
    ODsay의 오류 정보를 보고, 무슨 문제인지 한국어 문장으로 바꿔줍니다.
    (안내 문장, "경로 없음" 종류인지 여부)를 함께 돌려줍니다.
    """
    # ODsay의 오류는 리스트 [ {...} ] 또는 딕셔너리 {...} 두 가지 모양으로 올 수 있어요.
    if isinstance(error, list):
        error = error[0] if error else {}

    code = str(error.get("code", ""))  # 오류 번호
    message = error.get("message") or error.get("msg") or ""  # 오류 원문 메시지

    # 출발지와 도착지가 너무 가까울 때 (700m 이내) → 경로 없음 종류
    if code == "-98":
        return "출발지와 도착지가 너무 가까워요(700m 이내). 걸어서 갈 수 있는 거리예요!", True

    # 대중교통 경로가 아예 없을 때 → 경로 없음 종류
    if code == "-99":
        return "두 지점 사이의 대중교통 경로를 찾을 수 없어요.", True

    # IP가 ODsay에 등록되지 않았을 때 ("IP"라는 단어가 따로 들어 있는지 확인)
    if re.search(r"\bip\b", message, re.IGNORECASE):
        return "이 컴퓨터의 IP 주소가 ODsay에 등록되지 않았어요. ODsay 홈페이지에서 IP를 등록해주세요.", False

    # API 키 인증 실패 (실제 응답: "[ApiKeyAuthFailed] ApiKey authentication failed.")
    # ODsay는 IP 미등록일 때도 이 오류를 보내는 경우가 있어서 두 가지를 함께 안내해요.
    if "ApiKeyAuthFailed" in message:
        return (
            "ODsay API 키 인증에 실패했어요. "
            ".env의 ODSAY_API_KEY가 맞는지, 그리고 ODsay에 이 컴퓨터의 IP가 등록되어 있는지 확인해주세요."
        ), False

    # 그 밖의 모르는 오류는 원문을 함께 보여줍니다.
    return f"ODsay 오류가 발생했어요. (코드: {code}, 내용: {message})", False


# 이 파일을 직접 실행할 때만 아래 코드가 동작합니다.
# 강남역 → 금정역은 이미 메모장에 있으면 ODsay를 부르지 않아요.
# (오류 처리 등 나머지 테스트는 test_transit.py에서 가짜 답장으로 합니다.)
if __name__ == "__main__":
    gangnam = (37.49808633653005, 127.02800140627488)
    geumjeong = (37.37247, 126.94347)

    print("🚇 강남역 → 금정역")
    try:
        info = get_transit_info(gangnam, geumjeong)
        print(f"   소요시간 {info['time_min']}분, 환승 {info['transfers']}번, 요금 {info['fare']}원")
    except ValueError as error:
        print(f"   ⚠️ {error}")

    print(f"📊 오늘 ODsay 호출: {get_today_usage()} / {DAILY_LIMIT}건")
