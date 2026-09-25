import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# === Renderのポート検知をクリアするためのダミーサーバー ===
def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), lambda *args: BaseHTTPRequestHandler(*args))
    server.serve_forever()

threading.Thread(target=start_dummy_server, daemon=True).start()

# === 設定の読み込み ===
ICAO_CODE = os.environ.get("ICAO_CODE", "acfc26")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
FLIGHTAWARE_API_KEY = os.environ.get("FLIGHTAWARE_API_KEY")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))

JAPAN_AIRPORT_PREFIXES = ("RJ", "RO")

if not DISCORD_WEBHOOK_URL:
    raise ValueError("エラー: DISCORD_WEBHOOK_URL が設定されていません。")

is_in_air_last = None

def is_destination_japan_airport(destination_str):
    if not destination_str or destination_str in ["不明", "N/A"]:
        return False
    dest_clean = destination_str.strip().upper()
    return dest_clean.startswith(JAPAN_AIRPORT_PREFIXES)

def get_flight_route(flight_number):
    if not FLIGHTAWARE_API_KEY or not flight_number or flight_number == "N/A":
        return "不明", "不明"
    url = f"https://aeroapi.flightaware.com/aeroapi/flights/{flight_number.strip()}"
    headers = {"x-apikey": FLIGHTAWARE_API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            flights = data.get("flights", [])
            if flights:
                latest = flights[0]
                origin = (latest.get("origin") or {}).get("code") or "不明"
                destination = (latest.get("destination") or {}).get("code") or "不明"
                return origin, destination
    except Exception as e:
        print(f"目的地取得エラー: {e}")
    return "不明", "不明"

def send_discord_notification(flight, alt, origin, destination):
    flight_str = flight if flight else "不明"
    is_japan_airport = is_destination_japan_airport(destination)
    
    if is_japan_airport:
        content_text = f"🚨 **【重要】N936CAの目的地が「日本の空港 ({destination})」に設定されました！** @everyone"
        embed_color = 15158332
    else:
        content_text = "✈️ **N936CA 離陸検知**"
        embed_color = 3066993

    payload = {
        "content": content_text,
        "embeds": [
            {
                "title": "✈️ 離陸ステータス詳細",
                "color": embed_color,
                "fields": [
                    {"name": "機体 (ICAO)", "value": ICAO_CODE.upper(), "inline": True},
                    {"name": "フライト番号", "value": flight_str, "inline": True},
                    {"name": "高度", "value": f"{alt} ft", "inline": True},
                    {"name": "🛫 出発地", "value": origin, "inline": True},
                    {"name": "🛬 目的地", "value": destination, "inline": True},
                ],
                "footer": {"text": "ADSB Tracker"}
            }
        ]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print("Discordへ送信成功")
    except Exception as e:
        print(f"送信エラー: {e}")

def check_takeoff():
    global is_in_air_last
    url = f"https://api.adsb.lol/v2/icao/{ICAO_CODE}"
    try:
        res = requests.get(url, timeout=10).json()
        ac_list = res.get("ac", [])
        if not ac_list:
            return

        ac = ac_list[0]
        alt = ac.get("alt_baro")
        flight = ac.get("flight", "N/A").strip()

        is_ground = (alt == "ground") or (isinstance(alt, (int, float)) and alt < 100)
        is_in_air_current = not is_ground

        if is_in_air_last is False and is_in_air_current is True:
            origin, destination = get_flight_route(flight)
            send_discord_notification(flight, alt, origin, destination)

        is_in_air_last = is_in_air_current
    except Exception as e:
        print(f"エラー: {e}")

if __name__ == "__main__":
    print("N936CAの常時監視を開始しました...")
    while True:
        check_takeoff()
        time.sleep(CHECK_INTERVAL)
