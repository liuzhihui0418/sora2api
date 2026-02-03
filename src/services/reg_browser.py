import asyncio
import random
import os
from playwright.async_api import async_playwright

# --- 配置区 ---
PROXY_SERVER = "http://43.246.197.192:443"
PROXY_USER = "CYfFOZOYdhXd"
PROXY_PASS = "n7CSQQspGX"
OPENAI_URL = "https://chatgpt.com/"


def get_random_desktop_ua():
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ]
    return random.choice(uas)


async def launch_stable_reg():
    async with async_playwright() as p:
        print(f"🚀 正在准备极速注册环境...")

        # 1. 启动浏览器 - 移除了导致闪退的 --single-process 和 --no-zygote
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-extensions',
                '--start-maximized'  # 默认最大化
            ]
        )

        # 2. 创建上下文
        context = await browser.new_context(
            user_agent=get_random_desktop_ua(),
            viewport={'width': 1280, 'height': 800},
            proxy={
                "server": PROXY_SERVER,
                "username": PROXY_USER,
                "password": PROXY_PASS
            }
        )

        page = await context.new_page()
        # 3. 抹除自动化特征
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("\n" + "=" * 50)
        print("✅ 浏览器已启动！")
        print("🚩 流程：\n1. 在网页完成注册/登录\n2. 提取 Session Token 存入你的 Excel\n3. 在控制台按回车重置环境")
        print("=" * 50)

        while True:
            try:
                print("\n🏠 载入 ChatGPT 页面...")
                # wait_until="commit" 只要拿到响应就显示，不等待沉重的后台脚本
                await page.goto(OPENAI_URL, wait_until="commit", timeout=60000)

                # 阻塞点：等待用户手动操作
                print("⌨️  请在浏览器操作。完成后，在此处按回车 [Enter] 清理环境并注册下一个...")

                # 使用 loop.run_in_executor 让 input 不卡死异步循环
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, input, "")

                # --- 核心清理动作 ---
                print("🧹 正在深度清理本地缓存（不登出）...")
                await context.clear_cookies()
                await page.evaluate("window.localStorage.clear();")
                await page.evaluate("window.sessionStorage.clear();")

                print("✅ 环境已重置，正在准备下一个账号...")

            except Exception as e:
                print(f"⚠️ 发生错误: {e}")
                print("正在尝试重新载入...")
                await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(launch_stable_reg())
    except KeyboardInterrupt:
        print("\n已退出脚本")
    except Exception as e:
        print(f"\n❌ 程序崩溃: {e}")
        input("按回车关闭...")