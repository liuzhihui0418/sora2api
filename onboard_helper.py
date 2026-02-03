import asyncio
import random
import aiosqlite
import os
from curl_cffi.requests import AsyncSession
from playwright.async_api import async_playwright

# --- 1. 配置区 ---
PASSWORD = "aini7758258@！！"
DB_PATH = r"E:\py\群主项目\sora2api\data\hancat.db"
PROXY_SERVER = "http://43.246.197.192:443"
PROXY_USER = "CYfFOZOYdhXd"
PROXY_PASS = "n7CSQQspGX"
PROXY_FULL = f"http://{PROXY_USER}:{PROXY_PASS}@43.246.197.192:443"


def get_random_ios_ua():
    ios_versions = [("17_4", "17.4"), ("17_6", "17.6"), ("18_0", "18.0"), ("18_1", "18.1")]
    ver = random.choice(ios_versions)
    dev = random.choice(["iPhone", "iPad"])
    webkit = f"605.1.{random.randint(10, 30)}"
    return f"Mozilla/5.0 ({dev}; CPU {dev} OS {ver[0]} like Mac OS X) AppleWebKit/{webkit} (KHTML, like Gecko) Version/{ver[1]} Mobile/15E148 Safari/604.1"


async def human_type(page, selector, text):
    try:
        await page.wait_for_selector(selector, timeout=15000)
        await page.click(selector)
        for char in text:
            await page.type(selector, char, delay=random.randint(50, 150))
        await asyncio.sleep(random.uniform(0.5, 1.0))
        return True
    except:
        return False


async def refresh_st_to_at(st, ua):
    url = "https://chatgpt.com/api/auth/session"
    headers = {"Cookie": f"__Secure-next-auth.session-token={st}", "User-Agent": ua, "Accept": "application/json"}
    async with AsyncSession(impersonate="safari15_5", proxies={"all": PROXY_FULL}) as session:
        try:
            resp = await session.get(url, headers=headers, timeout=15)
            if resp.status_code == 200: return resp.json().get("accessToken")
        except:
            return None


async def save_to_db(email, st, ua, real_at):
    async with aiosqlite.connect(DB_PATH) as db:
        token_value = real_at if real_at else f"st_only_{email}"
        cursor = await db.execute("SELECT id FROM tokens WHERE email = ?", (email,))
        if await cursor.fetchone():
            await db.execute("UPDATE tokens SET token=?, st=?, user_agent=?, is_active=1 WHERE email=?",
                             (token_value, st, ua, email))
        else:
            await db.execute(
                "INSERT INTO tokens (token, email, username, name, st, user_agent, is_active, created_at) VALUES (?, ?, '', ?, ?, ?, 1, CURRENT_TIMESTAMP)",
                (token_value, email, email.split('@')[0], st, ua))
        await db.commit()


async def check_and_save(email, context, ua):
    cookies = await context.cookies()
    st_cookie = next((c for c in cookies if c['name'] == '__Secure-next-auth.session-token'), None)
    if st_cookie:
        st_value = st_cookie['value']
        print(f"✅ 抓取成功！执行转换入库...")
        real_at = await refresh_st_to_at(st_value, ua)
        await save_to_db(email, st_value, ua, real_at)
        print(f"🎉 {email} 已同步完成！")
        return True
    return False


async def start_onboard(email):
    async with async_playwright() as p:
        selected_ua = get_random_ios_ua()
        browser = await p.chromium.launch(headless=False, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(user_agent=selected_ua, viewport={'width': 393, 'height': 852},
                                            proxy={"server": PROXY_SERVER, "username": PROXY_USER,
                                                   "password": PROXY_PASS})
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print(f"\n🚀 目标账号: {email}")
        try:
            # 进入首页
            await page.goto("https://chatgpt.com/auth/login", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # --- 核心改进 1: 暴力清理 Cookie 弹窗 ---
            print("🍪 正在尝试关闭 Cookie 弹窗...")
            cookie_btns = ['全部接受', 'Accept all', '全部接受', '全部允许']
            for btn_text in cookie_btns:
                try:
                    target = page.get_by_role("button", name=btn_text)
                    if await target.is_visible():
                        await target.click(timeout=3000)
                        print(f"✅ 已点掉 Cookie 弹窗 ({btn_text})")
                        await asyncio.sleep(1)
                        break
                except:
                    pass

            # --- 核心改进 2: 点击蓝色登录按钮 ---
            print("🖱️ 正在寻找登录起始按钮...")
            login_selectors = [
                'button:has-text("登录")',
                'button:has-text("Log in")',
                '[data-testid="login-button"]',
                'div[role="button"]:has-text("登录")'
            ]
            for sel in login_selectors:
                try:
                    target = await page.wait_for_selector(sel, timeout=3000)
                    if target:
                        await target.click()
                        print("✅ 已点击登录入口")
                        break
                except:
                    pass

            await asyncio.sleep(3)

            # --- 3. 输入邮箱 (增加对多种表单的兼容) ---
            print("📧 正在填写邮箱...")
            email_selectors = 'input[name="username"], input[type="email"], input[id="email-input"]'
            if await human_type(page, email_selectors, email):
                await page.keyboard.press("Enter")
                # 兼容手动点继续
                await asyncio.sleep(2)
                try:
                    await page.click('button:has-text("继续"), button:has-text("Continue")')
                except:
                    pass

            # --- 4. 密码阶段与状态监控 ---
            print("⏳ 监控跳转...")
            for _ in range(15):
                if await check_and_save(email, context, selected_ua): return
                # 检查密码框
                if await page.query_selector('input[name="password"]'): break
                # 检查人机验证
                if "Verify you are human" in await page.content() or await page.query_selector('iframe'):
                    print("⚠️  请在弹出的浏览器中手动通过人机验证...")
                await asyncio.sleep(2)

            print("🔑 填写密码...")
            if await human_type(page, 'input[name="password"]', PASSWORD):
                await page.keyboard.press("Enter")
                # 兼容手动点登录
                await asyncio.sleep(2)
                try:
                    await page.click('button:has-text("登录"), button:has-text("Log in")')
                except:
                    pass

            # --- 5. 循环等待直到抓到 ST ---
            print("⏳ 等待最后重定向...")
            for _ in range(25):
                if await check_and_save(email, context, selected_ua): return
                await asyncio.sleep(2)

        except Exception as e:
            print(f"❌ 运行失败: {e}")
        finally:
            await browser.close()


if __name__ == "__main__":
    email = input("请输入邮箱: ").strip()
    if email: asyncio.run(start_onboard(email))