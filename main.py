import os
import json
import requests
from datetime import datetime, timedelta, timezone

# 從環境變數讀取配置
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
CHANNEL_ID = os.getenv('CHANNEL_ID')
DISCORD_WEBHOOK_A = os.getenv('DISCORD_WEBHOOK_A')  # 一般影片 & Shorts
DISCORD_WEBHOOK_B = os.getenv('DISCORD_WEBHOOK_B')  # 直播中
DATA_FILE = 'last_notified.json'

def load_last_notified():
    """載入上次通知過的影片 ID 紀錄"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_last_notified(data):
    """更新影片 ID 紀錄檔案"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_discord_notification(webhook_url, video_data, status_text):
    """發送 Discord Webhook 通知"""
    video_id = video_data['id']['videoId']
    video_title = video_data['snippet']['title']
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    thumbnail = video_data['snippet']['thumbnails']['high']['url']

    payload = {
        "content": f"🔔 **{status_text}** 已經發布！",
        "embeds": [{
            "title": video_title,
            "url": video_url,
            "color": 16711680 if status_text == "直播中" else 3447003,
            "image": {"url": thumbnail},
            "footer": {"text": f"YouTube 自動監控系統 • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }]
    }
    
    response = requests.post(webhook_url, json=payload)
    if response.status_code == 204:
        print(f"成功發送通知: {video_title} ({status_text})")
    else:
        print(f"發送 Discord 通知失敗: {response.status_code}, {response.text}")

def check_youtube():
    """檢查 YouTube 頻道最新動態"""
    # 增加檢查最近一小時發布的影片，避免抓到過舊的存檔
    published_after = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    
    url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&channelId={CHANNEL_ID}&part=snippet,id&order=date&maxResults=10&publishedAfter={published_after}"
    
    response = requests.get(url)
    if response.status_code != 200:
        print(f"無法取得 YouTube 資料: {response.status_code}, {response.text}")
        return

    data = response.json()
    items = data.get('items', [])
    last_notified = load_last_notified()
    updated = False

    for item in items:
        if item['id'].get('kind') != 'youtube#video':
            continue

        video_id = item['id']['videoId']
        snippet = item['snippet']
        live_status = snippet.get('liveBroadcastContent')
        
        # 1. 忽略預告狀態
        if live_status == 'upcoming':
            continue 
        
        # 2. 防止重複通知 (核心邏輯：只要 ID 存在於紀錄中，不論狀態為何都不再發送)
        if video_id in last_notified:
            continue

        # 3. 判斷分流
        if live_status == 'live':
            # 正在直播中
            send_discord_notification(DISCORD_WEBHOOK_B, item, "直播中")
            last_notified[video_id] = {"status": "live", "time": str(datetime.now())}
            updated = True
        elif live_status == 'none':
            # 排除掉可能標題包含 "Streamed" 或已經結束的直播標記（這部分視 API 回傳狀況而定）
            # 最有效的方法是 check publishTime 是否太舊，我們已在 API 參數中加入 publishedAfter
            send_discord_notification(DISCORD_WEBHOOK_A, item, "新影片/Shorts")
            last_notified[video_id] = {"status": "none", "time": str(datetime.now())}
            updated = True

    if updated:
        save_last_notified(last_notified)
    else:
        print("沒有偵測到新的、符合條件的影片或直播。")

if __name__ == "__main__":
    check_youtube()
