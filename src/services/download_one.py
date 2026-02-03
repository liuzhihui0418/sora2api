import asyncio
import os
import time
import sys

# 引用你之前调试好的配置（必须确保 sora_client.py 就在旁边）
from sora_client import FIXED_USER_AGENT, _cached_device_id
from curl_cffi.requests import AsyncSession

# ================= 配置区 =================
# 1. 填入你的 Token (确保有效)
ACCESS_TOKEN = "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE5MzQ0ZTY1LWJiYzktNDRkMS1hOWQwLWY5NTdiMDc5YmQwZSIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSJdLCJjbGllbnRfaWQiOiJhcHBfWDh6WTZ2VzJwUTl0UjNkRTduSzFqTDVnSCIsImV4cCI6MTc3MDkwMDI2NiwiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS9hdXRoIjp7ImNoYXRncHRfYWNjb3VudF9pZCI6IjhkZGNhODRlLTZhOGQtNGFkYS04MTAwLTY3MzAwM2I3NjA5YiIsImNoYXRncHRfYWNjb3VudF91c2VyX2lkIjoidXNlci1SQVNHZ3NpY0NCU0ZrZ2p0OExDa0ZNYndfXzhkZGNhODRlLTZhOGQtNGFkYS04MTAwLTY3MzAwM2I3NjA5YiIsImNoYXRncHRfY29tcHV0ZV9yZXNpZGVuY3kiOiJub19jb25zdHJhaW50IiwiY2hhdGdwdF9wbGFuX3R5cGUiOiJwbHVzIiwiY2hhdGdwdF91c2VyX2lkIjoidXNlci1SQVNHZ3NpY0NCU0ZrZ2p0OExDa0ZNYnciLCJ1c2VyX2lkIjoidXNlci1SQVNHZ3NpY0NCU0ZrZ2p0OExDa0ZNYncifSwiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS9wcm9maWxlIjp7ImVtYWlsIjoieW93b2g3MTcyNkBpY3ViaWsuY29tIiwiZW1haWxfdmVyaWZpZWQiOnRydWV9LCJpYXQiOjE3NzAwMzYyNjUsImlzcyI6Imh0dHBzOi8vYXV0aC5vcGVuYWkuY29tIiwianRpIjoiNDliZDcyMmItNDk3Yy00ZjdlLThhYTAtMDQ5ZmRhOGY0M2RlIiwibmJmIjoxNzcwMDM2MjY1LCJwd2RfYXV0aF90aW1lIjoxNzcwMDM2MjYzOTQ0LCJzY3AiOlsib3BlbmlkIiwiZW1haWwiLCJwcm9maWxlIiwib2ZmbGluZV9hY2Nlc3MiLCJtb2RlbC5yZXF1ZXN0IiwibW9kZWwucmVhZCIsIm9yZ2FuaXphdGlvbi5yZWFkIiwib3JnYW5pemF0aW9uLndyaXRlIl0sInNlc3Npb25faWQiOiJhdXRoc2Vzc19naFVCd0NlRU1KUzZlV3hGQzZ2SEtzV2IiLCJzdWIiOiJhdXRoMHxrVXVYOWsxQk1zV2ozd1k2RXVqT0w2bDEifQ.IxuUvGPl5olXn6Zccb1WIWIyHuTaYBjlHg55oGkEjcIDTWANBIyRNLcqRgYB21IGG0u0rkZ02Rp-1NikXk29YHRo-_EZLiSwTj5I1-K-FeVd1MNr_YE9XGJAD9G0diL-pAKz-r8JsURCboikpiqY3Q22izyYQCZn23nta3SxV1uPLYlLggirRxRBGXIflwxa_9SwCOXxQOINt4f0yiG3R8zDOSofyzAKcFAlsRt1ZUAJPiJ5u59QA5oKWllSPDLQlcfPGpcJWAPy3aaT2p1WSqzbe_p8rIsCKIoUn3MMHnuACKS0nCH63XJSsQBMENUXhwDjyFXKNaz7rm_Vol9UZ4gmXOixu9kOpGuM9kDdZlCkmfrijoP6nIQDOvrjmFzonQ-mWBh8inyGWw9Vjvf7Gb8H-WltI8RBvoUc4cXx9m5tieYBw8Eu_eBE2pj4WghqUHbDukZBCgH0pt3bbLMJrz610SjyUAKgky-bDpRlICrnE8d9JBmsMrLwmsLtzfngHVB_D68lkaDwKpayox0J9qcBrQo3HuYSzDVhAWGR-PFq3QtUjPl0jT4QV4k0K1oiGe8vVewmaQERHnY4TDku8955mIG4_AkkSKMJ2XaRQ64LRXJwtmR3Qbo20LHllG8erPhJtgtqKIjWRC-00KPl6-ozmNIkdewWYrnufFy--Tw"

# 2. 填入你要死盯着的 Task ID
TARGET_TASK_ID = "task_01kgf6mhv5e5abna98t8j08yav"

# 3. 填入你的日本 HTTP 代理
PROXY_URL = "http://zVfa9RasFz6-zone-custom-region-JP-st-Saitama-city-Saitama:f70a812a26a1@global.lycheeip.com:10000"


# =========================================

async def poll_and_download():
    print(f"🎯 开始轮询任务: {TARGET_TASK_ID}")
    print("⏳ 等待生成中，请不要关闭窗口...")

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "User-Agent": FIXED_USER_AGENT,
        "Accept": "application/json",
        "Referer": "https://sora.chatgpt.com/",
        "Origin": "https://sora.chatgpt.com"
    }
    cookies = {"oai-did": _cached_device_id or "uuid-placeholder"}

    # 循环轮询
    while True:
        try:
            async with AsyncSession(impersonate="chrome124", cookies=cookies) as session:
                # --- 阶段 1: 检查是否还在进行中 (Pending) ---
                pending_url = "https://sora.chatgpt.com/backend/nf/pending/v2"
                resp = await session.get(pending_url, headers=headers, proxy=PROXY_URL, timeout=30)

                is_still_pending = False
                if resp.status_code == 200:
                    tasks = resp.json()
                    for t in tasks:
                        if t.get('id') == TARGET_TASK_ID:
                            progress = t.get('progress', 0)
                            print(f"🔄 [{time.strftime('%H:%M:%S')}] 生成中... 进度: {progress}%")
                            is_still_pending = True
                            break

                if is_still_pending:
                    # 如果还在生成，休息 10 秒再看
                    await asyncio.sleep(10)
                    continue

                # --- 阶段 2: 既然不在 Pending 了，去历史记录 (History) 找结果 ---
                print(f"⚡ [{time.strftime('%H:%M:%S')}] 任务已从队列消失，正在去历史记录寻找下载链接...")
                history_url = "https://sora.chatgpt.com/backend/nf/history?limit=20"
                resp_hist = await session.get(history_url, headers=headers, proxy=PROXY_URL, timeout=30)

                found_task = None
                if resp_hist.status_code == 200:
                    history_data = resp_hist.json()
                    # 兼容不同的返回结构 (list 或 dict)
                    items = history_data if isinstance(history_data, list) else history_data.get('data', [])

                    for item in items:
                        if item.get('id') == TARGET_TASK_ID:
                            found_task = item
                            break

                if not found_task:
                    print("⚠️ 奇怪，任务既不在队列也不在历史记录里，可能刚完成有延迟，5秒后重试...")
                    await asyncio.sleep(5)
                    continue

                # --- 阶段 3: 检查状态并下载 ---
                status = found_task.get('status')
                if status == 'failed':
                    print("❌ 悲报：任务生成失败！")
                    return

                # 提取链接
                video_url = found_task.get('video_url')
                # 暴力提取兜底
                if not video_url:
                    import re
                    content = str(found_task)
                    match = re.search(r"src='(https://[^']+)'", content)
                    if match:
                        video_url = match.group(1)

                if video_url:
                    print(f"✅ 成功获取链接！准备下载...")
                    print(f"🔗 Link: {video_url[:60]}...")

                    # 下载文件
                    file_name = f"{TARGET_TASK_ID}.mp4"
                    dl_resp = await session.get(video_url, headers=headers, proxy=PROXY_URL, stream=True)
                    if dl_resp.status_code == 200:
                        content = await dl_resp.content.read()
                        with open(file_name, "wb") as f:
                            f.write(content)
                        print(f"\n🎉🎉🎉 下载完成！视频已保存为: {os.path.abspath(file_name)}")
                        break  # 退出循环
                    else:
                        print(f"❌ 下载请求被拒绝 (HTTP {dl_resp.status_code})")
                        break
                else:
                    print("⚠️ 任务显示完成，但没找到视频链接，可能被风控拦截。")
                    break

        except Exception as e:
            print(f"⚠️ 网络波动 ({e})，3秒后重试...")
            await asyncio.sleep(3)


if __name__ == "__main__":
    # Windows Proactor 修复
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        asyncio.run(poll_and_download())
    except KeyboardInterrupt:
        pass