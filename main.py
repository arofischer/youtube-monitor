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
            except (json.JSONDecodeError, ValueError):
                return {}
    return {}

def save_last_notified(data):
    """更新影片 ID 紀錄檔案"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def is_actually_a_live_archive(video_id):
    """二次檢查：確認該影片是否為直播存檔"""
    url = f"https://www.googleapis.com/youtube/v3/videos?key={YOUTUBE_API_KEY}&id={video_id}&part=liveStreamingDetails"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            items = response.json().get('items', [])
            return len(items) > 0 and 'liveStreamingDetails' in items[0]
        return False
    except:
        return False

def send_discord_notification(webhook_url, video_data, status_text):
    """發送 Discord Webhook 通知"""
    snippet = video_data['snippet']
    video_id = video_data['id']['videoId']
    video_title = snippet['title']
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    thumbnail = snippet['thumbnails']['high']['url']

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
    
    response = requests.post(webhook_url, json=payload, timeout=15)
    return response.status_code == 204

def check_youtube():
    """檢查 YouTube 頻道最新動態"""
    # 修正重點：使用 strftime 確保產生符合 YouTube API 規範的 RFC 3339 格式 (結尾為 Z)
    published_after = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # 建議加上 type=video 確保只搜尋影片，排除頻道或播放清單
    url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&channelId={CHANNEL_ID}&part=snippet,id&order=date&maxResults=10&type=video&publishedAfter={published_after}"
    
    print(f"🔍 正在檢查頻道 {CHANNEL_ID} (過去 24 小時)...")
    
    response = requests.get(url, timeout=15)
    if response.status_code != 200:
        print(f"無法取得 YouTube 資料: {response.status_code}, {response.text}")
        return

    items = response.json().get('items', [])
    last_notified = load_last_notified()
    updated = False

    if not items:
        print("📭 過去 24 小時內沒有偵測到任何影片。")
        return

    for item in items:
        video_id = item['id']['videoId']
        snippet = item['snippet']
        live_status = snippet.get('liveBroadcastContent')
        
        # 1. 忽略預告
        if live_status == 'upcoming': continue 
        
        # 2. 防止重複通知
        if video_id in last_notified:
            print(f"📌 已通知過，跳過: {snippet.get('title')}")
            continue

        # 3. 判斷分流與直播存檔過濾
        if live_status == 'live':
            if send_discord_notification(DISCORD_WEBHOOK_B, item, "直播中"):
                last_notified[video_id] = {"status": "live", "time": str(datetime.now())}
                updated = True
        elif live_status == 'none':
            # 檢查是否為直播存檔
            if is_actually_a_live_archive(video_id):
                print(f"⏭️ 偵測到直播存檔，不重複通知: {snippet.get('title')}")
                last_notified[video_id] = {"status": "archived", "time": str(datetime.now())}
                updated = True
                continue
            
            if send_discord_notification(DISCORD_WEBHOOK_A, item, "新影片/Shorts"):
                last_notified[video_id] = {"status": "none", "time": str(datetime.now())}
                updated = True

    if updated:
        save_last_notified(last_notified)
        print("💾 紀錄已更新。")
    else:
        print("✨ 掃描完成，無新內容發布。")

if __name__ == "__main__":
    check_youtube()
