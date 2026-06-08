import json
import os
import psutil
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="LifeOps Core System",
    description="Home server Smart Display Hub",
    version="1.0.0"
)

# iPadや外部クライアントからのリクエストを許可するCORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 定義ファイル名（お手元のファイル名に合わせて大文字・小文字を調整して自動判定します）
SCHEDULE_FILE = "train_schedule.json"
CALENDER_FILE = "calendar_events.json" if os.path.exists("calendar_events.json") else "calender_events.json"

def get_system_stats():
    """psutilを使用したシステム統計の取得"""
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    ram_percent = ram.percent
    
    # CPU温度の取得（Rasberry PiやUbuntu Serverに対応、失敗時は42.0°Cをデフォルトとする）
    temp = 42.0
    if hasattr(psutil, "sensors_temperatures"):
        try:
            temps = psutil.sensors_temperatures()
            if "coretemp" in temps:
                core_temps = [entry.current for entry in temps["coretemp"]]
                if core_temps:
                    temp = sum(core_temps) / len(core_temps)
            elif "cpu_thermal" in temps:
                temp = temps["cpu_thermal"][0].current
        except Exception:
            pass
            
    return {
        "cpu": cpu_percent,
        "ram": ram_percent,
        "temp": round(temp, 1)
    }

def get_next_trains():
    """
    新しい train_schedule.json（階層化された時刻表）を読み込み、
    現在時刻から『先発』と『次発』の2つの電車を抽出して返します。
    """
    station_name = "天王台"
    next_trains = []
    
    if not os.path.exists(SCHEDULE_FILE):
        return {"station": station_name, "next_trains": []}
        
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            station_name = data.get("station", station_name)
            timetable = data.get("timetable", [])
            
            # 1. 階層化された timetable をフラットなリスト（時間順）に変換
            schedule = []
            for item in timetable:
                hour = item.get("hour", 0)
                h_str = f"{hour:02d}"
                for train in item.get("trains", []):
                    min_val = train.get("min", 0)
                    m_str = f"{min_val:02d}"
                    schedule.append({
                        "time": f"{h_str}:{m_str}",
                        "dest": train.get("destination", "上野"),
                        "type": train.get("type", "快速")
                    })
            
            # 2. 現在の時刻を「HH:MM」文字列として取得
            now_str = datetime.now().strftime("%H:%M")
            
            # 3. 時刻表を時間順にソートします
            schedule_sorted = sorted(schedule, key=lambda x: x["time"])
            
            # 4. 現在時刻以降の電車をフィルタリング
            upcoming = [t for t in schedule_sorted if t["time"] >= now_str]
            
            # 今日はもう終電が終わっている場合は、明日の始発サイクルのために全リストに戻す
            if not upcoming:
                upcoming = schedule_sorted
                
            # 5. 上位の2件を抽出
            for t in upcoming[:2]:
                next_trains.append({
                    "time": t["time"],
                    "dest": t["dest"],
                    "type": t["type"]
                })
    except Exception as e:
        print(f"Error reading schedule: {e}")
        
    return {
        "station": station_name,
        "next_trains": next_trains
    }

def get_calendar_events():
    """ローカルのJSONカレンダー予定を取得"""
    fallback_events = [{"time": "19:00", "title": "コンピュータークラブミーティング"}]
    if os.path.exists(CALENDER_FILE):
        try:
            with open(CALENDER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return fallback_events

@app.get("/api/status")
async def get_status():
    """ダッシュボードが必要とするシステム・交通・カレンダーの一元化API"""
    now = datetime.now()
    return {
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "system": get_system_stats(),
        "calendar": get_calendar_events(),
        "transit": get_next_trains(),
        "weather": {
            "condition": "Cloudy",
            "temp": 22
        }
    }

# ==================== 静的ファイル表示機能を追加 ====================

@app.get("/")
async def read_index():
    """
    ブラウザで http://localhost:3000/ にアクセスした時に、
    同じディレクトリにある index.html を表示します
    """
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"detail": "index.html がカレントディレクトリに見つかりません。"}

# カレントディレクトリ以下に配置されているその他の静的ファイル(JSONなど)も
# 配信できるようにFastAPIにマウントします
try:
    app.mount("/", StaticFiles(directory="."), name="static")
except Exception as e:
    print(f"StaticFiles mounting error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)