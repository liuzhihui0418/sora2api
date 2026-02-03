"""Sora API client module"""
import asyncio
import base64
import hashlib
import json
import io
import time
import random
import string
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from uuid import uuid4
from urllib.request import Request, urlopen, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
from curl_cffi.requests import AsyncSession
from curl_cffi import CurlMime
from curl_cffi.requests import AsyncSession
from curl_cffi import CurlMime

# ==================== 调试补丁开始 ====================
try:
    # 正常运行时使用相对导入
    from .proxy_manager import ProxyManager
    from ..core.config import config
    from ..core.logger import debug_logger
except ImportError:
    # 调试模式（直接运行时）模拟这些对象，防止报错
    class ProxyManager:
        pass


    class MockConfig:
        sora_base_url = "https://sora.chatgpt.com"
        sora_timeout = 30
        pow_proxy_enabled = False
        pow_proxy_url = None


    config = MockConfig()


    class MockLogger:
        def log_info(self, msg): print(f"[INFO] {msg}")

        def log_error(self, **kwargs): print(f"[ERROR] {kwargs}")

        def log_request(self, **kwargs): pass

        def log_response(self, **kwargs): pass


    debug_logger = MockLogger()
# ==================== 调试补丁结束 ====================
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Global browser instance for reuse (lightweight Playwright approach)
_browser = None
_playwright = None
_current_proxy = None

# Sentinel token cache
_cached_sentinel_token = None
_cached_device_id = None
_cached_user_agent = None  # <--- 新增这行
# ================= 必须把这行加在文件最上面 =================
# ✅ 强制改为 iPhone 15 Pro / iOS 17.4 的 UA
FIXED_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"

async def _get_browser(proxy_url: str = None):
    global _browser, _playwright, _current_proxy
    if _browser is not None and _current_proxy != proxy_url:
        await _browser.close()
        _browser = None
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        _current_proxy = proxy_url
    return _browser


async def _close_browser():
    """Close browser instance"""
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


async def _fetch_oai_did(proxy_url: str = None, max_retries: int = 3) -> str:
    """Fetch oai-did using curl_cffi (lightweight approach)"""
    debug_logger.log_info(f"[Sentinel] Fetching oai-did...")

    # 强制随机一个 iOS UA，防止默认请求头泄露
    current_ua = random.choice(MOBILE_USER_AGENTS)
    headers = {
        "User-Agent": current_ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }

    for attempt in range(max_retries):
        try:
            # ✅ 修正：全程统一使用 Safari 指纹
            async with AsyncSession(impersonate="safari15_5") as session:
                response = await session.get(
                    "https://chatgpt.com/",
                    headers=headers,  # 加上 Headers
                    proxy=proxy_url,
                    timeout=30,
                    allow_redirects=True
                )
                
                # Check for 403/429 errors - don't retry, just fail
                if response.status_code == 403:
                    raise Exception("403 Forbidden - Access denied when fetching oai-did")
                if response.status_code == 429:
                    raise Exception("429 Too Many Requests - Rate limited when fetching oai-did")
                
                oai_did = response.cookies.get("oai-did")
                if oai_did:
                    debug_logger.log_info(f"[Sentinel] oai-did: {oai_did}")
                    return oai_did
                
                set_cookie = response.headers.get("set-cookie", "")
                match = re.search(r'oai-did=([a-f0-9-]{36})', set_cookie)
                if match:
                    oai_did = match.group(1)
                    debug_logger.log_info(f"[Sentinel] oai-did: {oai_did}")
                    return oai_did
                    
        except Exception as e:
            error_str = str(e)
            # Re-raise 403/429 errors immediately
            if "403" in error_str or "429" in error_str:
                raise
            debug_logger.log_info(f"[Sentinel] oai-did fetch failed: {e}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(2)
    
    return None


async def _generate_sentinel_token_lightweight(proxy_url: str = None, device_id: str = None) -> str:
    """[域名模拟版] 借用 chatgpt.com 环境运行，彻底解决卡死和下载问题"""
    global _cached_device_id, _cached_user_agent
    if not _cached_user_agent: _cached_user_agent = random.choice(MOBILE_USER_AGENTS)
    ios_ua = _cached_user_agent

    if not device_id: device_id = await _fetch_oai_did(proxy_url)
    if not device_id: return None
    _cached_device_id = device_id

    # 1. 在 Python 层面先抓取脚本内容 (这步之前已证明能成)
    sdk_code = ""
    try:
        async with AsyncSession(impersonate="safari15_5") as session:
            res = await session.get("https://chatgpt.com/backend-api/sentinel/sdk.js", proxy=proxy_url, timeout=15)
            if res.status_code == 200: sdk_code = res.text
    except:
        pass
    if not sdk_code: return None

    # 2. 启动浏览器环境
    browser = await _get_browser(proxy_url)
    # 【关键】模拟 iPhone 13 特征
    context = await browser.new_context(
        viewport={'width': 390, 'height': 844},
        user_agent=ios_ua,
        is_mobile=True,
        has_touch=True
    )

    # 【补丁】注入隐藏自动化特征的代码
    await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    page = await context.new_page()

    # 3. 【核心创新】通过拦截器，在 chatgpt.com 域下伪造一个完美的运行环境
    target_url = "https://chatgpt.com/robots.txt"  # 借用 robots.txt 路径

    async def handle_route(route):
        if route.request.url == target_url:
            # 伪造一个包含 SDK 的完整 HTML
            content = f'<html><head><script>{sdk_code}</script></head><body><div id="root"></div></body></html>'
            await route.fulfill(status=200, content_type="text/html", body=content)
        else:
            await route.continue_()

    await page.route("**/*", handle_route)

    try:
        # 4. 访问伪造页面（瞬时加载）
        await page.goto(target_url, wait_until="commit", timeout=15000)

        debug_logger.log_info(f"[Sentinel] Environment Spoofed. Running SDK...")

        # 5. 【核心修正】加入 12 秒内部超时保护，防止 evaluate 永久卡死 Python
        token = await page.evaluate(f'''
            async () => {{
                return new Promise((resolve) => {{
                    // 设置 12 秒保险，超时强制返回 ERROR
                    const timer = setTimeout(() => resolve('ERROR_TIMEOUT'), 12000);

                    if (typeof SentinelSDK === 'undefined') {{
                        resolve('ERROR_NO_SDK');
                        return;
                    }}

                    // 执行计算
                    SentinelSDK.token('sora_2_create_task', '{device_id}')
                        .then(t => {{
                            clearTimeout(timer);
                            resolve(t);
                        }})
                        .catch(e => resolve('ERROR_' + e.message));
                }});
            }}
        ''')

        if token and not token.startswith('ERROR') and len(token) > 100:
            debug_logger.log_info(f"[Sentinel] Success! Short Token Extracted ({len(token)} bytes)")
            return token

        debug_logger.log_info(f"[Sentinel] SDK failed to compute: {token}")
        return None

    except Exception as e:
        debug_logger.log_info(f"[Sentinel] Playwright Engine Error: {e}")
        return None
    finally:
        await context.close()


async def _get_cached_sentinel_token(proxy_url: str = None, force_refresh: bool = False) -> str:
    """Get sentinel token with caching support
    
    Args:
        proxy_url: Optional proxy URL
        force_refresh: Force refresh token (e.g., after 400 error)
        
    Returns:
        Sentinel token string or None
        
    Raises:
        Exception: If 403/429 when fetching oai-did
    """
    global _cached_sentinel_token
    
    # Return cached token if available and not forcing refresh
    if _cached_sentinel_token and not force_refresh:
        debug_logger.log_info("[Sentinel] Using cached token")
        return _cached_sentinel_token
    
    # Generate new token
    debug_logger.log_info("[Sentinel] Generating new token...")
    token = await _generate_sentinel_token_lightweight(proxy_url)
    
    if token:
        _cached_sentinel_token = token
        debug_logger.log_info("[Sentinel] Token cached successfully")
    
    return token


def _invalidate_sentinel_cache():
    """Invalidate cached sentinel token (call after 400 error)"""
    global _cached_sentinel_token
    _cached_sentinel_token = None
    debug_logger.log_info("[Sentinel] Cache invalidated")


# PoW related constants
POW_MAX_ITERATION = 500000
POW_CORES = [4, 8, 12, 16, 24, 32]
# ==================== 补全缺失的常量 ====================

# 1. 缺失的脚本列表 (POW_SCRIPTS)
POW_SCRIPTS = [
    "https://sora-cdn.oaistatic.com/_next/static/chunks/polyfills-42372ed130431b0a.js",
    "https://sora-cdn.oaistatic.com/_next/static/chunks/6974-eaafbe7db9c73c96.js",
    "https://sora-cdn.oaistatic.com/_next/static/chunks/main-app-5f0c58611778fb36.js",
    "https://chatgpt.com/backend-api/sentinel/sdk.js",
]

# 2. 缺失的 Document Keys (POW_DOCUMENT_KEYS)
POW_DOCUMENT_KEYS = [
    "__reactContainer$3k0e9yog4o3",
    "__reactContainer$ft149nhgior",
    "__reactResources$9nnifsagitb",
    "_reactListeningou2wvttp2d9",
    "_reactListeningu9qurgpwsme",
    "_reactListeningo743lnnpvdg",
    "location",
    "body",
]

# 3. 缺失的 Desktop UA (因为代码后面 _nf_create_urllib 还在引用它)
# 这里我们直接把它指向 Mobile UA，或者定义一个通用的 iOS Mac UA 也可以
DESKTOP_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

# ==================== 补全结束 ====================
# ==================== 替换开始 ====================
# 1. 定义 iOS 屏幕 (逻辑分辨率)
POW_SCREEN_SIZES = [
    (390, 844),   # iPhone 12/13/14
    (428, 926),   # iPhone 12/13/14 Pro Max
    (393, 852),   # iPhone 15 Pro
    (430, 932),   # iPhone 15 Pro Max
    (375, 812),   # iPhone X/XS/11 Pro
    (414, 896),   # iPhone XR/11
]

# 2. 定义 iOS 浏览器环境特征 (Safari WebKit)
# iOS 核心特征：vendor是Apple，无webdriver，maxTouchPoints>0
POW_NAVIGATOR_KEYS = [
    "cookieEnabled−true",
    "onLine−true",
    "doNotTrack−null",      # Safari 特有
    "hardwareConcurrency−6", # iPhone A系列芯片通常显示为6核
    "language−en-US",
    "languages−en-US",
    "vendor−Apple Computer, Inc.", # 必须修改！原代码是 Google Inc
    "product−Gecko",
    "productSub−20030107",
    "maxTouchPoints−5",     # 移动端特征
    "pdfViewerEnabled−true"
]

# 3. 这里的 Key 保持通用即可，主要影响不大，但建议去掉 chrome 特有的
POW_WINDOW_KEYS = [
    "getSelection", "btoa", "__next_s", "crossOriginIsolated", "print",
    "window", "self", "document", "location", "navigator", "screen",
    "localStorage", "sessionStorage", "crypto", "performance"
]

# 4. 强制使用 iOS User-Agent
MOBILE_USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
]
# ==================== 替换结束 ====================

class SoraClient:
    """Sora API client with proxy support"""

    # 基础域名保持不变
    CHATGPT_BASE_URL = "https://chatgpt.com"
    # 确保 Flow 对齐
    SENTINEL_FLOW = "sora_2_create_task"

    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.base_url = config.sora_base_url
        self.timeout = config.sora_timeout

    @staticmethod
    def _get_pow_parse_time() -> str:
        """Generate time string for PoW (local timezone)"""
        now = datetime.now()
        
        # Get local timezone offset (seconds)
        if time.daylight and time.localtime().tm_isdst > 0:
            utc_offset_seconds = -time.altzone
        else:
            utc_offset_seconds = -time.timezone
        
        # Format as +0800 or -0500
        offset_hours = utc_offset_seconds // 3600
        offset_minutes = abs(utc_offset_seconds % 3600) // 60
        offset_sign = '+' if offset_hours >= 0 else '-'
        offset_str = f"{offset_sign}{abs(offset_hours):02d}{offset_minutes:02d}"
        
        # Get timezone name
        tz_name = time.tzname[1] if time.daylight and time.localtime().tm_isdst > 0 else time.tzname[0]
        
        return now.strftime("%a %b %d %Y %H:%M:%S") + f" GMT{offset_str} ({tz_name})"

    @staticmethod
    def _get_pow_config(user_agent: str) -> list:
        """iOS 专用 PoW 配置生成"""
        # 从 iOS 尺寸池中随机取一个
        screen_w, screen_h = random.choice(POW_SCREEN_SIZES)

        # 模拟性能时间
        perf_time = random.uniform(500, 5000)

        return [
            screen_w,  # [0] screen.width (使用 iOS 逻辑宽度)
            SoraClient._get_pow_parse_time(),  # [1] time
            None,  # [2] jsHeapSizeLimit (重点：Safari 没有这个值，必须为 None)
            0,  # [3] iteration
            user_agent,  # [4] UA
            random.choice(POW_SCRIPTS) if POW_SCRIPTS else "",  # [5] script
            None,  # [6] null
            "en-US",  # [7] language
            "en-US,en",  # [8] languages
            random.randint(2, 10),  # [9] init
            random.choice(POW_NAVIGATOR_KEYS),  # [10] navigator (使用上面定义的 Apple 版本)
            random.choice(POW_DOCUMENT_KEYS),  # [11] document
            random.choice(POW_WINDOW_KEYS),  # [12] window
            perf_time,  # [13] perf time
            str(uuid4()),  # [14] UUID
            "",  # [15] empty
            6,  # [16] cores (iOS 通常为 6)
            time.time() * 1000 - perf_time,  # [17] time origin
        ]

    @staticmethod
    def _solve_pow(seed: str, difficulty: str, config_list: list) -> Tuple[str, bool]:
        """Execute PoW calculation using SHA3-512 hash collision"""
        diff_len = len(difficulty) // 2
        seed_encoded = seed.encode()
        target_diff = bytes.fromhex(difficulty)

        static_part1 = (json.dumps(config_list[:3], separators=(',', ':'), ensure_ascii=False)[:-1] + ',').encode()
        static_part2 = (',' + json.dumps(config_list[4:9], separators=(',', ':'), ensure_ascii=False)[1:-1] + ',').encode()
        static_part3 = (',' + json.dumps(config_list[10:], separators=(',', ':'), ensure_ascii=False)[1:]).encode()
        initial_j = config_list[9]

        for i in range(POW_MAX_ITERATION):
            dynamic_i = str(i).encode()

            dynamic_j = str(initial_j + (i + 29) // 30).encode()

            final_json_compact = static_part1 + dynamic_i + static_part2 + dynamic_j + static_part3
            # 移除所有多余的空格，并尝试在生成时精简配置项（核心技巧）
            b64_encoded = base64.b64encode(final_json_compact)

            hash_value = hashlib.sha3_512(seed_encoded + b64_encoded).digest()

            if hash_value[:diff_len] <= target_diff:
                return b64_encoded.decode(), True

        error_token = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D" + base64.b64encode(f'"{seed}"'.encode()).decode()
        return error_token, False

    @staticmethod
    def _get_pow_token(user_agent: str) -> str:
        """Generate initial PoW token"""
        config_list = SoraClient._get_pow_config(user_agent)
        seed = format(random.random())
        difficulty = "0fffff"
        solution, _ = SoraClient._solve_pow(seed, difficulty, config_list)
        return "gAAAAAC" + solution

    @staticmethod
    def _build_sentinel_token(
        flow: str,
        req_id: str,
        pow_token: str,
        resp: Dict[str, Any],
        user_agent: str,
    ) -> str:
        """Build openai-sentinel-token from PoW response"""
        final_pow_token = pow_token

        # Check if PoW is required
        proofofwork = resp.get("proofofwork", {})
        if proofofwork.get("required"):
            seed = proofofwork.get("seed", "")
            difficulty = proofofwork.get("difficulty", "")
            if seed and difficulty:
                config_list = SoraClient._get_pow_config(user_agent)
                solution, success = SoraClient._solve_pow(seed, difficulty, config_list)
                final_pow_token = "gAAAAAB" + solution
                if not success:
                    debug_logger.log_info("[Warning] PoW calculation failed, using error token")

        if not final_pow_token.endswith("~S"):
            final_pow_token = final_pow_token + "~S"

        token_payload = {
            "p": final_pow_token,
            "t": resp.get("turnstile", {}).get("dx", ""),
            "c": resp.get("token", ""),
            "id": req_id,
            "flow": flow,
        }
        return json.dumps(token_payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _post_json_sync(url: str, headers: dict, payload: dict, timeout: int, proxy: Optional[str]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")

        try:
            if proxy:
                opener = build_opener(ProxyHandler({"http": proxy, "https": proxy}))
                resp = opener.open(req, timeout=timeout)
            else:
                resp = urlopen(req, timeout=timeout)

            resp_text = resp.read().decode("utf-8")
            if resp.status not in (200, 201):
                raise Exception(f"Request failed: {resp.status} {resp_text}")
            return json.loads(resp_text)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise Exception(f"HTTP Error: {exc.code} {body}") from exc
        except URLError as exc:
            raise Exception(f"URL Error: {exc}") from exc

    async def _get_sentinel_token_via_browser(self, proxy_url: Optional[str] = None) -> Optional[str]:
        if not PLAYWRIGHT_AVAILABLE:
            debug_logger.log_info("[Warning] Playwright not available, cannot use browser fallback")
            return None
        
        try:
            async with async_playwright() as p:
                launch_args = {
                    "headless": True,
                    "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                }
                
                if proxy_url:
                    launch_args["proxy"] = {"server": proxy_url}
                
                browser = await p.chromium.launch(**launch_args)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                )
                
                page = await context.new_page()
                
                debug_logger.log_info(f"[Browser] Navigating to sora.chatgpt.com...")
                await page.goto("https://sora.chatgpt.com", wait_until="domcontentloaded", timeout=90000)
                
                cookies = await context.cookies()
                device_id = None
                for cookie in cookies:
                    if cookie.get("name") == "oai-did":
                        device_id = cookie.get("value")
                        break
                
                if not device_id:
                    device_id = str(uuid4())
                    debug_logger.log_info(f"[Browser] No oai-did cookie, generated: {device_id}")
                else:
                    debug_logger.log_info(f"[Browser] Got oai-did from cookie: {device_id}")
                
                debug_logger.log_info(f"[Browser] Waiting for SentinelSDK...")
                for _ in range(120):
                    try:
                        sdk_ready = await page.evaluate("() => typeof window.SentinelSDK !== 'undefined'")
                        if sdk_ready:
                            break
                    except:
                        pass
                    await asyncio.sleep(0.5)
                else:
                    debug_logger.log_info("[Browser] SentinelSDK load timeout")
                    await browser.close()
                    return None
                
                debug_logger.log_info(f"[Browser] SentinelSDK ready, getting token...")
                
                # 尝试获取 token，最多重试 3 次
                for attempt in range(3):
                    debug_logger.log_info(f"[Browser] Getting token, attempt {attempt + 1}/3...")
                    
                    try:
                        token = await page.evaluate(
                            "(deviceId) => window.SentinelSDK.token('sora_2_create_task__auto', deviceId)",
                            device_id
                        )
                        
                        if token:
                            debug_logger.log_info(f"[Browser] Token obtained successfully")
                            await browser.close()
                            
                            if isinstance(token, str):
                                token_data = json.loads(token)
                            else:
                                token_data = token
                            
                            if "id" not in token_data or not token_data.get("id"):
                                token_data["id"] = device_id
                            
                            return json.dumps(token_data, ensure_ascii=False, separators=(",", ":"))
                        else:
                            debug_logger.log_info(f"[Browser] Token is empty")
                            
                    except Exception as e:
                        debug_logger.log_info(f"[Browser] Token exception: {str(e)}")
                    
                    if attempt < 2:
                        await asyncio.sleep(2)
                
                await browser.close()
                return None
                
        except Exception as e:
            debug_logger.log_error(
                error_message=f"Browser sentinel token failed: {str(e)}",
                status_code=0,
                response_text=str(e),
                source="Server"
            )
            return None

    async def _nf_create_urllib(self, token: str, payload: dict, sentinel_token: str,
                                proxy_url: Optional[str], token_id: Optional[int] = None,
                                user_agent: Optional[str] = None,
                                session_token: Optional[str] = None) -> Dict[str, Any]:
        """
        [身份统一版]
        1. 从传入的 Cookie 字符串中强行提取真实的 oai-did
        2. 确保 Header 中的 Device-Id 与 Cookie 一致，解决 400 错误
        """
        global _cached_user_agent
        import json as json_mod
        import re

        # --- 1. 核心修复：从 Cookie 中提取真实的 oai-did ---
        real_device_id = None
        if session_token and "oai-did=" in session_token:
            # 尝试正则提取
            match = re.search(r'oai-did=([a-f0-9\-]+)', session_token)
            if match:
                real_device_id = match.group(1)
                debug_logger.log_info(f"🔍 已从 Cookie 提取真实设备ID: {real_device_id}")

        # 如果没提取到，才使用 Sentinel 里的或者随机的
        if not real_device_id:
            if sentinel_token:
                try:
                    sentinel_data = json_mod.loads(sentinel_token)
                    real_device_id = sentinel_data.get("id")
                except:
                    pass

        # 兜底
        if not real_device_id:
            real_device_id = str(uuid4())

        final_ua = user_agent or _cached_user_agent or random.choice(MOBILE_USER_AGENTS)

        # --- 2. 注入 Cookie ---
        cookies = {"oai-did": real_device_id}  # 确保 Cookie 里的 ID 也是对的

        if session_token:
            # 如果传入的是完整的 Cookie 串（包含 key），直接塞入
            if "session-token=" in session_token:
                # 这里我们做一个特殊的处理：如果 session_token 本身就是一长串 cookie，我们不应该把它
                # 当作 __Secure-next-auth.session-token 的值，而是应该解析它
                # 但为了兼容你 test_sora.py 里的清洗逻辑，我们假设传进来的是纯值
                cookies["__Secure-next-auth.session-token"] = session_token
            else:
                cookies["__Secure-next-auth.session-token"] = session_token
        else:
            debug_logger.log_info("⚠️ [警告] 未提供 Session Token")

        # --- 3. 候选 API 地址 ---
        candidate_urls = [
            "https://sora.chatgpt.com/backend/nf/create"  # 正确地址

        ]

        async with AsyncSession(impersonate="safari15_5", cookies=cookies, http_version=1) as session:
            last_exception = None

            for url in candidate_urls:
                if "sora.chatgpt.com" in url:
                    current_domain = "https://sora.chatgpt.com"
                else:
                    current_domain = "https://chatgpt.com"

                headers = {
                    "Authorization": f"Bearer {token}",
                    "OAI-Device-Id": real_device_id,  # 【关键】这里必须用提取出来的真 ID
                    "Content-Type": "application/json",
                    "User-Agent": final_ua,
                    "Accept": "*/*",
                    "Origin": current_domain,
                    "Referer": f"{current_domain}/",
                    "X-Sora-Fingerprint": "undefined",
                    "Priority": "u=1, i",
                }

                if sentinel_token:
                    headers["OpenAI-Sentinel-Token"] = sentinel_token

                debug_logger.log_info(f"🚀 [尝试提交] 目标: {url}")

                # 随机延迟
                await asyncio.sleep(random.uniform(0.5, 1.0))

                try:
                    response = await session.post(
                        url,
                        json=payload,
                        headers=headers,
                        proxy=proxy_url,
                        timeout=60,
                        allow_redirects=False
                    )

                    if response.status_code == 404:
                        debug_logger.log_info(f"⚠️ 404 Not Found...")
                        continue

                    if response.status_code in [307, 308, 302]:
                        target = response.headers.get("Location", "")
                        raise Exception(f"Session 失效或被拦截 (307) -> {target}")

                    if response.status_code == 403:
                        raise Exception("403 Forbidden - IP 被盾拦截")

                    # 400 错误处理：打印详细信息
                    if response.status_code == 400:
                        debug_logger.log_info(f"❌ 400 Bad Request: {response.text}")
                        # 不抛出，让它尝试下一个域名（虽然通常 400 是参数问题而不是域名问题）
                        # 但这里我们抛出，因为 400 意味着服务器处理了但拒绝了
                        raise Exception(f"API 参数或身份校验错误 (400): {response.text}")

                    if response.status_code == 200:
                        try:
                            resp_json = response.json()
                            if "id" in resp_json:
                                debug_logger.log_info(f"✅✅✅ 提交成功！Task ID: {resp_json['id']}")
                                return resp_json
                        except:
                            pass
                    debug_logger.log_info(f"❌ 响应内容: {response.text[:200]}")
                    # 👇 把 response.text 加进去，这样前端就能看到详细原因了
                    raise Exception(f"API 错误 {response.status_code}: {response.text}")

                except Exception as e:
                    last_exception = e
                    debug_logger.log_info(f"❌ 请求异常: {str(e)}")

            raise last_exception or Exception("所有 API 路径尝试均失败")

    @staticmethod
    def _post_text_sync(url: str, headers: dict, body: str, timeout: int, proxy: Optional[str]) -> Dict[str, Any]:
        data = body.encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")

        try:
            if proxy:
                opener = build_opener(ProxyHandler({"http": proxy, "https": proxy}))
                resp = opener.open(req, timeout=timeout)
            else:
                resp = urlopen(req, timeout=timeout)

            resp_text = resp.read().decode("utf-8")
            if resp.status not in (200, 201):
                raise Exception(f"Request failed: {resp.status} {resp_text}")
            return json.loads(resp_text)
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="ignore")
            raise Exception(f"HTTP Error: {exc.code} {body_text}") from exc
        except URLError as exc:
            raise Exception(f"URL Error: {exc}") from exc

    async def _generate_sentinel_token(self, token: Optional[str] = None, user_agent: Optional[str] = None) -> Tuple[
        str, str]:
        req_id = str(uuid4())

        # 强制覆盖：如果没有指定 UA 或 UA 不是 iPhone，则强制使用 iOS UA
        if not user_agent or "iPhone" not in user_agent:
            user_agent = random.choice(MOBILE_USER_AGENTS)

        pow_token = self._get_pow_token(user_agent)

        init_payload = {
            "p": pow_token,
            "id": req_id,
            "flow": "sora_init"
        }
        ua_with_pow = f"{user_agent} {json.dumps(init_payload, separators=(',', ':'))}"

        proxy_url = await self.proxy_manager.get_proxy_url()

        # Request sentinel/req endpoint
        url = f"{self.CHATGPT_BASE_URL}/backend-api/sentinel/req"
        request_payload = {
            "p": pow_token,
            "id": req_id,
            "flow": "sora_init"
        }
        request_body = json.dumps(request_payload, separators=(',', ':'))

        # ==================== 重点修改 Headers ====================
        # iOS Safari 不支持 Client Hints (sec-ch-ua)，带了必死
        headers = {
            "Accept": "*/*",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/backend-api/sentinel/frame.html",
            "User-Agent": ua_with_pow,
            "Accept-Language": "en-US,en;q=0.9",
            # 千万不要在这里加任何 sec-ch-ua 开头的头，iOS 没这些
        }

        try:
            # ==================== 重点修改 Impersonate ====================
            # 将 chrome131 改为 safari15_5 或 safari16_0
            async with AsyncSession(impersonate="safari15_5") as session:
                response = await session.post(
                    url,
                    headers=headers,
                    data=request_body,
                    proxy=proxy_url,
                    timeout=30
                )
                if response.status_code != 200:
                    raise Exception(f"Sentinel request failed: {response.status_code} {response.text}")
                resp = response.json()

            debug_logger.log_info(f"Sentinel response: turnstile.dx={bool(resp.get('turnstile', {}).get('dx'))}, token={bool(resp.get('token'))}, pow_required={resp.get('proofofwork', {}).get('required')}")
        except Exception as e:
            debug_logger.log_error(
                error_message=f"Sentinel request failed: {str(e)}",
                status_code=0,
                response_text=str(e),
                source="Server"
            )
            raise

        # Build final sentinel token
        sentinel_token = self._build_sentinel_token(
            self.SENTINEL_FLOW, req_id, pow_token, resp, user_agent
        )

        # Log final token for debugging
        parsed = json.loads(sentinel_token)
        debug_logger.log_info(f"Final sentinel: p_prefix={parsed['p'][:10]}, p_suffix={parsed['p'][-5:]}, t_len={len(parsed['t'])}, c_len={len(parsed['c'])}, flow={parsed['flow']}")

        return sentinel_token, user_agent

    @staticmethod
    def is_storyboard_prompt(prompt: str) -> bool:
        """检测提示词是否为分镜模式格式

        格式: [time]prompt 或 [time]prompt\n[time]prompt
        例如: [5.0s]猫猫从飞机上跳伞 [5.0s]猫猫降落

        Args:
            prompt: 用户输入的提示词

        Returns:
            True if prompt matches storyboard format
        """
        if not prompt:
            return False
        # 匹配格式: [数字s] 或 [数字.数字s]
        pattern = r'\[\d+(?:\.\d+)?s\]'
        matches = re.findall(pattern, prompt)
        # 至少包含一个时间标记才认为是分镜模式
        return len(matches) >= 1

    @staticmethod
    def format_storyboard_prompt(prompt: str) -> str:
        """将分镜格式提示词转换为API所需格式

        输入: 猫猫的奇妙冒险\n[5.0s]猫猫从飞机上跳伞 [5.0s]猫猫降落
        输出: current timeline:\nShot 1:...\n\ninstructions:\n猫猫的奇妙冒险

        Args:
            prompt: 原始分镜格式提示词

        Returns:
            格式化后的API提示词
        """
        # 匹配 [时间]内容 的模式
        pattern = r'\[(\d+(?:\.\d+)?)s\]\s*([^\[]+)'
        matches = re.findall(pattern, prompt)

        if not matches:
            return prompt

        # 提取总述(第一个[时间]之前的内容)
        first_bracket_pos = prompt.find('[')
        instructions = ""
        if first_bracket_pos > 0:
            instructions = prompt[:first_bracket_pos].strip()

        # 格式化分镜
        formatted_shots = []
        for idx, (duration, scene) in enumerate(matches, 1):
            scene = scene.strip()
            shot = f"Shot {idx}:\nduration: {duration}sec\nScene: {scene}"
            formatted_shots.append(shot)

        timeline = "\n\n".join(formatted_shots)

        # 如果有总述,添加instructions部分
        if instructions:
            return f"current timeline:\n{timeline}\n\ninstructions:\n{instructions}"
        else:
            return timeline

    async def _make_request(self, method: str, endpoint: str, token: str,
                            json_data: Optional[Dict] = None,
                            multipart: Optional[Dict] = None,
                            add_sentinel_token: bool = False,
                            token_id: Optional[int] = None) -> Dict[str, Any]:
        """
        [调试增强版] 发送请求并处理 WAF 拦截诊断
        """
        proxy_url = await self.proxy_manager.get_proxy_url(token_id)

        global _cached_user_agent, _cached_device_id
        # 同步 Sentinel 缓存
        if add_sentinel_token:
            try:
                sentinel_token = await _get_cached_sentinel_token(proxy_url)
            except Exception as e:
                debug_logger.log_info(f"[Warning] 获取 Sentinel Token 失败: {e}")
                sentinel_token = None

        # ✅ [iOS修正] 确保 UA 一致性，强制使用全局 iPhone UA
        current_ua = FIXED_USER_AGENT
        device_id = _cached_device_id or str(uuid4())

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": current_ua,
            "OAI-Device-Id": device_id,
            "Accept": "application/json",
            # ✅ [iOS修正] 这里的 Headers 必须干净，没有 Chrome 的痕迹
        }

        if add_sentinel_token and '_cached_sentinel_token' in globals() and _cached_sentinel_token:
            headers["OpenAI-Sentinel-Token"] = _cached_sentinel_token

        cookies = {"oai-did": device_id}

        # ✅ [iOS修正] 关键：改为 safari15_5，去掉 http_version=1
        async with AsyncSession(impersonate="safari15_5", cookies=cookies) as session:
            # 统一使用 chatgpt.com 域名
            url = f"https://chatgpt.com{endpoint}"

            req_kwargs = {
                "headers": headers,
                "timeout": self.timeout,
                "proxy": proxy_url,
                "allow_redirects": False  # 禁止自动重定向，以便捕获 307
            }
            if json_data: req_kwargs["json"] = json_data
            if multipart: req_kwargs["multipart"] = multipart

            # Log request
            debug_logger.log_info(f"🚀 发送请求: {method} {url}")

            try:
                if method == "GET":
                    response = await session.get(url, **req_kwargs)
                else:
                    response = await session.post(url, **req_kwargs)
            except Exception as e:
                raise Exception(f"网络层连接失败 (代理挂了?): {str(e)}")

            # ================= [诊断核心区] =================
            if response.status_code != 200:
                debug_logger.log_info(f"⚠️ 状态码异常: {response.status_code}")

                preview_text = response.text[:500]
                debug_logger.log_info(f"⚠️ 响应内容预览: {preview_text}")

                if response.status_code == 403:
                    if "Just a moment" in preview_text or "Challenge" in preview_text:
                        raise Exception("⛔️ 403 Forbidden: 触发了 Cloudflare 盾 (身份指纹不匹配)")
                    else:
                        raise Exception("⛔️ 403 Forbidden: 访问被拒绝，IP 可能被拉黑。")

                if response.status_code in [302, 307, 308]:
                    location = response.headers.get('Location', 'Unknown')
                    raise Exception(f"🔄 请求被重定向到: {location}")

                raise Exception(f"API 请求失败 ({response.status_code})")

            try:
                return response.json()
            except json.JSONDecodeError:
                debug_logger.log_error(f"❌ JSON 解析失败! 虽然状态码是 200。")
                raise Exception("JSON 解析失败: 服务器返回了非 JSON 格式的数据")

    async def get_user_info(self, token: str, session_token: Optional[str] = None) -> Dict[str, Any]:
        # 👇👇👇 加入这行打印代码 👇👇👇
        print("\n\n🔥【调试】正在运行新代码！UA:", FIXED_USER_AGENT[:50], "\n\n")
        # 主域接口
        url = "https://chatgpt.com/backend-api/me"

        # ✅ [iOS修正] 强制使用全局统一的 iPhone UA
        current_ua = FIXED_USER_AGENT

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": current_ua,
            "Accept": "application/json",
            "Referer": "https://sora.chatgpt.com/",
            # ✅ [iOS修正] 绝对不要加 sec-ch-ua 等 Chrome 专用头，iOS Safari 没有这些
        }

        # 构造 Cookie
        cookies = {}
        if session_token:
            cookies["__Secure-next-auth.session-token"] = session_token

        # ✅ [iOS修正] 使用 safari15_5 指纹，且去掉 http_version=1 让其自动协商 H2/H3
        async with AsyncSession(impersonate="safari15_5", cookies=cookies) as session:
            proxy_url = await self.proxy_manager.get_proxy_url()

            debug_logger.log_info(f"🚀 获取用户信息: {url}")
            try:
                # 禁止自动重定向，以便捕获 307
                response = await session.get(url, headers=headers, proxy=proxy_url, timeout=15, allow_redirects=False)

                if response.status_code != 200:
                    debug_logger.log_info(f"⚠️ get_user_info 状态码异常: {response.status_code}")
                    # 如果是 307，尝试打印 Location
                    if response.status_code in [307, 302]:
                        debug_logger.log_info(f"⚠️ 重定向至: {response.headers.get('Location')}")
                    # 打印 HTML 预览以便诊断
                    debug_logger.log_info(f"⚠️ 响应内容: {response.text[:200]}")
                    raise Exception(f"用户信息获取失败 ({response.status_code})")

                return response.json()
            except Exception as e:
                debug_logger.log_info(f"❌ get_user_info 网络错误: {e}")
                raise
    
    async def upload_image(self, image_data: bytes, token: str, filename: str = "image.png") -> str:
        """Upload image and return media_id

        使用 CurlMime 对象上传文件（curl_cffi 的正确方式）
        参考：https://curl-cffi.readthedocs.io/en/latest/quick_start.html#uploads
        """
        # 检测图片类型
        mime_type = "image/png"
        if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
            mime_type = "image/jpeg"
        elif filename.lower().endswith('.webp'):
            mime_type = "image/webp"

        # 创建 CurlMime 对象
        mp = CurlMime()

        # 添加文件部分
        mp.addpart(
            name="file",
            content_type=mime_type,
            filename=filename,
            data=image_data
        )

        # 添加文件名字段
        mp.addpart(
            name="file_name",
            data=filename.encode('utf-8')
        )

        result = await self._make_request("POST", "/uploads", token, multipart=mp)
        return result["id"]
    
    async def generate_image(self, prompt: str, token: str, width: int = 360,
                            height: int = 360, media_id: Optional[str] = None, token_id: Optional[int] = None) -> str:
        """Generate image (text-to-image or image-to-image)"""
        operation = "remix" if media_id else "simple_compose"

        inpaint_items = []
        if media_id:
            inpaint_items = [{
                "type": "image",
                "frame_index": 0,
                "upload_media_id": media_id
            }]

        json_data = {
            "type": "image_gen",
            "operation": operation,
            "prompt": prompt,
            "width": width,
            "height": height,
            "n_variants": 1,
            "n_frames": 1,
            "inpaint_items": inpaint_items
        }

        # 生成请求需要添加 sentinel token
        result = await self._make_request("POST", "/video_gen", token, json_data=json_data, add_sentinel_token=True, token_id=token_id)
        return result["id"]

    async def generate_video(self, prompt: str, token: str, orientation: str = "landscape",
                             media_id: Optional[str] = None, n_frames: int = 300, style_id: Optional[str] = None,
                             model: str = "sy_8", size: str = "small", token_id: Optional[int] = None,
                             session_token: Optional[str] = None) -> str: # 👈 [新增] 接收 Session Token
        """
        提交视频生成任务
        Args:
            prompt: 提示词
            token: Access Token (Bearer)
            orientation: 方向
            media_id: 上传的媒体ID (图生视频用)
            n_frames: 帧数
            style_id: 风格ID
            model: 模型
            size: 尺寸
            token_id: 数据库ID
            session_token: [关键] 必须传入 __Secure-next-auth.session-token 否则会报 307
        """

        # 【核心适配】使用 kind: video 格式
        inpaint_items = [{"kind": "upload", "upload_id": media_id}] if media_id else []

        json_data = {
            "kind": "video",
            "prompt": prompt,
            "orientation": orientation,
            "size": "small",  # 强制使用 small 降低风险
            "n_frames": 300,  # 强制使用 300 提高通过率
            "model": "sy_8",  # 强制使用标准模型
            "inpaint_items": inpaint_items,
            "style_id": style_id
        }

        proxy_url = await self.proxy_manager.get_proxy_url(token_id)

        # 获取 Sentinel Token
        try:
            sentinel_token = await _get_cached_sentinel_token(proxy_url, force_refresh=False)
        except Exception as e:
            debug_logger.log_info(f"[Warning] Sentinel Token 获取失败: {e}")
            sentinel_token = None

        # 如果缓存没有，尝试重新生成
        if not sentinel_token:
            sentinel_token, _ = await self._generate_sentinel_token(token, user_agent=_cached_user_agent)

        # 提交请求至 Sora 官方域名 (透传 session_token)
        result = await self._nf_create_urllib(
            token,
            json_data,
            sentinel_token,
            proxy_url,
            token_id,
            _cached_user_agent,
            session_token=session_token # 👈 [新增] 传给底层发送函数
        )

        if isinstance(result, dict) and "id" in result:
            return result["id"]
        else:
            raise Exception(f"提交失败，OpenAI 反馈: {result}")
    
    async def get_image_tasks(self, token: str, limit: int = 20, token_id: Optional[int] = None) -> Dict[str, Any]:
        """Get recent image generation tasks"""
        return await self._make_request("GET", f"/backend-api/v2/recent_tasks?limit={limit}", token, token_id=token_id)

    async def get_video_drafts(self, token: str, limit: int = 15, token_id: Optional[int] = None) -> Dict[str, Any]:
        """Get recent video drafts"""
        return await self._make_request("GET", f"/backend-api/project_y/profile/drafts?limit={limit}", token, token_id=token_id)

    async def get_pending_tasks(self, token: str, token_id: Optional[int] = None) -> list:
        """Get pending video generation tasks
        [修复版] 强制对齐 iOS 指纹和 Referer，规避 403 盾
        """
        url = "https://sora.chatgpt.com/backend/nf/pending/v2"
        proxy_url = await self.proxy_manager.get_proxy_url(token_id)

        # 1. 必须使用全局一致的 UA 和 Device ID
        global _cached_device_id
        device_id = _cached_device_id or str(uuid4())

        # 2. 构造严格的 iOS/Safari Headers
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": FIXED_USER_AGENT,
            "Accept": "application/json",
            "Referer": "https://sora.chatgpt.com/",  # 必须带，证明你从官网看的进度
            "Origin": "https://sora.chatgpt.com",
            "OAI-Device-Id": device_id,
            "Alt-Used": "sora.chatgpt.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        # 3. 必须带上 oai-did Cookie，否则 CF 认为你是爬虫
        cookies = {"oai-did": device_id}

        try:
            # 4. 强制使用 safari15_5 指纹
            async with AsyncSession(impersonate="safari15_5", cookies=cookies) as session:
                debug_logger.log_info(f"🚀 [GET] {url}")

                # 增加一个 1-2 秒的随机延迟，模拟人眼刷新，避免被 WAF 标记高频
                await asyncio.sleep(random.uniform(1.0, 2.5))

                response = await session.get(
                    url,
                    headers=headers,
                    proxy=proxy_url,
                    timeout=30,
                    allow_redirects=False  # 拦截重定向以便调试
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 403:
                    # 如果还是 403，记录下关键信息
                    debug_logger.log_info(f"❌ 依然 403！可能是 IP 被拉黑或 Session 失效。")
                    return []
                elif response.status_code == 404:
                    return []
                else:
                    debug_logger.log_info(f"⚠️ 查询异常: {response.status_code}")
                    return []

        except Exception as e:
            debug_logger.log_info(f"❌ 查询请求崩溃: {e}")
            return []

    async def post_video_for_watermark_free(self, generation_id: str, prompt: str, token: str) -> str:
        """Post video to get watermark-free version

        Args:
            generation_id: The generation ID (e.g., gen_01k9btrqrnen792yvt703dp0tq)
            prompt: The original generation prompt
            token: Access token

        Returns:
            Post ID (e.g., s_690ce161c2488191a3476e9969911522)
        """
        json_data = {
            "attachments_to_create": [
                {
                    "generation_id": generation_id,
                    "kind": "sora"
                }
            ],
            "post_text": ""
        }

        # 发布请求需要添加 sentinel token
        result = await self._make_request("POST", "/project_y/post", token, json_data=json_data, add_sentinel_token=True)

        # 返回 post.id
        return result.get("post", {}).get("id", "")

    async def delete_post(self, post_id: str, token: str) -> bool:
        """Delete a published post

        Args:
            post_id: The post ID (e.g., s_690ce161c2488191a3476e9969911522)
            token: Access token

        Returns:
            True if deletion was successful
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        headers = {
            "Authorization": f"Bearer {token}"
        }

        async with AsyncSession() as session:
            url = f"{self.base_url}/project_y/post/{post_id}"

            kwargs = {
                "headers": headers,
                "timeout": self.timeout,
                "impersonate": "chrome"
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            # Log request
            debug_logger.log_request(
                method="DELETE",
                url=url,
                headers=headers,
                body=None,
                files=None,
                proxy=proxy_url
            )

            # Record start time
            start_time = time.time()

            # Make DELETE request
            response = await session.delete(url, **kwargs)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log response
            debug_logger.log_response(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.text if response.text else "No content",
                duration_ms=duration_ms,
                source="Server"
            )

            # Check status (DELETE typically returns 204 No Content or 200 OK)
            if response.status_code not in [200, 204]:
                error_msg = f"Delete post failed: {response.status_code} - {response.text}"
                debug_logger.log_error(
                    error_message=error_msg,
                    status_code=response.status_code,
                    response_text=response.text,
                    source="Server"
                )
                raise Exception(error_msg)

            return True

    async def get_watermark_free_url_custom(self, parse_url: str, parse_token: str, post_id: str) -> str:
        """Get watermark-free video URL from custom parse server

        Args:
            parse_url: Custom parse server URL (e.g., http://example.com)
            parse_token: Access token for custom parse server
            post_id: Post ID to parse (e.g., s_690c0f574c3881918c3bc5b682a7e9fd)

        Returns:
            Download link from custom parse server

        Raises:
            Exception: If parse fails or token is invalid
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        # Construct the share URL
        share_url = f"https://sora.chatgpt.com/p/{post_id}"

        # Prepare request
        json_data = {
            "url": share_url,
            "token": parse_token
        }

        kwargs = {
            "json": json_data,
            "timeout": 30,
            "impersonate": "chrome"
        }

        if proxy_url:
            kwargs["proxy"] = proxy_url

        try:
            async with AsyncSession() as session:
                # Record start time
                start_time = time.time()

                # Make POST request to custom parse server
                response = await session.post(f"{parse_url}/get-sora-link", **kwargs)

                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000

                # Log response
                debug_logger.log_response(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=response.text if response.text else "No content",
                    duration_ms=duration_ms,
                    source="Server"
                )

                # Check status
                if response.status_code != 200:
                    error_msg = f"Custom parse failed: {response.status_code} - {response.text}"
                    debug_logger.log_error(
                        error_message=error_msg,
                        status_code=response.status_code,
                        response_text=response.text,
                        source="Server"
                    )
                    raise Exception(error_msg)

                # Parse response
                result = response.json()

                # Check for error in response
                if "error" in result:
                    error_msg = f"Custom parse error: {result['error']}"
                    debug_logger.log_error(
                        error_message=error_msg,
                        status_code=401,
                        response_text=str(result),
                        source="Server"
                    )
                    raise Exception(error_msg)

                # Extract download link
                download_link = result.get("download_link")
                if not download_link:
                    raise Exception("No download_link in custom parse response")

                debug_logger.log_info(f"Custom parse successful: {download_link}")
                return download_link

        except Exception as e:
            debug_logger.log_error(
                error_message=f"Custom parse request failed: {str(e)}",
                status_code=500,
                response_text=str(e),
                source="Server"
            )
            raise

    # ==================== Character Creation Methods ====================

    async def upload_character_video(self, video_data: bytes, token: str) -> str:
        """Upload character video and return cameo_id

        Args:
            video_data: Video file bytes
            token: Access token

        Returns:
            cameo_id
        """
        mp = CurlMime()
        mp.addpart(
            name="file",
            content_type="video/mp4",
            filename="video.mp4",
            data=video_data
        )
        mp.addpart(
            name="timestamps",
            data=b"0,3"
        )

        result = await self._make_request("POST", "/characters/upload", token, multipart=mp)
        return result.get("id")

    async def get_cameo_status(self, cameo_id: str, token: str) -> Dict[str, Any]:
        """Get character (cameo) processing status

        Args:
            cameo_id: The cameo ID returned from upload_character_video
            token: Access token

        Returns:
            Dictionary with status, display_name_hint, username_hint, profile_asset_url, instruction_set_hint
        """
        return await self._make_request("GET", f"/project_y/cameos/in_progress/{cameo_id}", token)

    async def download_character_image(self, image_url: str) -> bytes:
        """Download character image from URL

        Args:
            image_url: The profile_asset_url from cameo status

        Returns:
            Image file bytes
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        kwargs = {
            "timeout": self.timeout,
            "impersonate": "chrome"
        }

        if proxy_url:
            kwargs["proxy"] = proxy_url

        async with AsyncSession() as session:
            response = await session.get(image_url, **kwargs)
            if response.status_code != 200:
                raise Exception(f"Failed to download image: {response.status_code}")
            return response.content

    async def finalize_character(self, cameo_id: str, username: str, display_name: str,
                                profile_asset_pointer: str, instruction_set, token: str) -> str:
        """Finalize character creation

        Args:
            cameo_id: The cameo ID
            username: Character username
            display_name: Character display name
            profile_asset_pointer: Asset pointer from upload_character_image
            instruction_set: Character instruction set (not used by API, always set to None)
            token: Access token

        Returns:
            character_id
        """
        # Note: API always expects instruction_set to be null
        # The instruction_set parameter is kept for backward compatibility but not used
        _ = instruction_set  # Suppress unused parameter warning
        json_data = {
            "cameo_id": cameo_id,
            "username": username,
            "display_name": display_name,
            "profile_asset_pointer": profile_asset_pointer,
            "instruction_set": None,
            "safety_instruction_set": None
        }

        result = await self._make_request("POST", "/characters/finalize", token, json_data=json_data)
        return result.get("character", {}).get("character_id")

    async def set_character_public(self, cameo_id: str, token: str) -> bool:
        """Set character as public

        Args:
            cameo_id: The cameo ID
            token: Access token

        Returns:
            True if successful
        """
        json_data = {"visibility": "public"}
        await self._make_request("POST", f"/project_y/cameos/by_id/{cameo_id}/update_v2", token, json_data=json_data)
        return True

    async def upload_character_image(self, image_data: bytes, token: str) -> str:
        """Upload character image and return asset_pointer

        Args:
            image_data: Image file bytes
            token: Access token

        Returns:
            asset_pointer
        """
        mp = CurlMime()
        mp.addpart(
            name="file",
            content_type="image/webp",
            filename="profile.webp",
            data=image_data
        )
        mp.addpart(
            name="use_case",
            data=b"profile"
        )

        result = await self._make_request("POST", "/project_y/file/upload", token, multipart=mp)
        return result.get("asset_pointer")

    async def delete_character(self, character_id: str, token: str) -> bool:
        """Delete a character

        Args:
            character_id: The character ID
            token: Access token

        Returns:
            True if successful
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        headers = {
            "Authorization": f"Bearer {token}"
        }

        async with AsyncSession() as session:
            url = f"{self.base_url}/project_y/characters/{character_id}"

            kwargs = {
                "headers": headers,
                "timeout": self.timeout,
                "impersonate": "chrome"
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            response = await session.delete(url, **kwargs)
            if response.status_code not in [200, 204]:
                raise Exception(f"Failed to delete character: {response.status_code}")
            return True

    async def remix_video(self, remix_target_id: str, prompt: str, token: str,
                         orientation: str = "portrait", n_frames: int = 450, style_id: Optional[str] = None) -> str:
        """Generate video using remix (based on existing video)

        Args:
            remix_target_id: The video ID from Sora share link (e.g., s_690d100857248191b679e6de12db840e)
            prompt: Generation prompt
            token: Access token
            orientation: Video orientation (portrait/landscape)
            n_frames: Number of frames
            style_id: Optional style ID

        Returns:
            task_id
        """
        json_data = {
            "kind": "video",
            "prompt": prompt,
            "inpaint_items": [],
            "remix_target_id": remix_target_id,
            "cameo_ids": [],
            "cameo_replacements": {},
            "model": "sy_8",
            "orientation": orientation,
            "n_frames": n_frames,
            "style_id": style_id
        }

        # Generate sentinel token and call /nf/create using urllib
        proxy_url = await self.proxy_manager.get_proxy_url()
        sentinel_token, user_agent = await self._generate_sentinel_token(token)
        result = await self._nf_create_urllib(token, json_data, sentinel_token, proxy_url, user_agent=user_agent)
        return result.get("id")

    async def generate_storyboard(self, prompt: str, token: str, orientation: str = "landscape",
                                 media_id: Optional[str] = None, n_frames: int = 450, style_id: Optional[str] = None) -> str:
        """Generate video using storyboard mode

        Args:
            prompt: Formatted storyboard prompt (Shot 1:\nduration: 5.0sec\nScene: ...)
            token: Access token
            orientation: Video orientation (portrait/landscape)
            media_id: Optional image media_id for image-to-video
            n_frames: Number of frames
            style_id: Optional style ID

        Returns:
            task_id
        """
        inpaint_items = []
        if media_id:
            inpaint_items = [{
                "kind": "upload",
                "upload_id": media_id
            }]

        json_data = {
            "kind": "video",
            "prompt": prompt,
            "title": "Draft your video",
            "orientation": orientation,
            "size": "small",
            "n_frames": n_frames,
            "storyboard_id": None,
            "inpaint_items": inpaint_items,
            "remix_target_id": None,
            "model": "sy_8",
            "metadata": None,
            "style_id": style_id,
            "cameo_ids": None,
            "cameo_replacements": None,
            "audio_caption": None,
            "audio_transcript": None,
            "video_caption": None
        }

        result = await self._make_request("POST", "/backend-api/nf/create/storyboard", token, json_data=json_data, add_sentinel_token=True)
        return result.get("id")

    async def enhance_prompt(self, prompt: str, token: str, expansion_level: str = "medium",
                             duration_s: int = 10, token_id: Optional[int] = None) -> str:
        json_data = {
            "prompt": prompt,
            "expansion_level": expansion_level,
            "duration_s": duration_s
        }
        # 尝试使用主域名的接口，主域名对 307 重定向更友好
        endpoint = "/backend-api/editor/enhance_prompt"

        # 手动构建请求，不走 _make_request 以便精细控制域名
        url = f"https://chatgpt.com{endpoint}"
        ua = random.choice(MOBILE_USER_AGENTS)
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": ua,
            "Content-Type": "application/json",
        }

        async with AsyncSession(impersonate="safari15_5") as session:
            proxy_url = await self.proxy_manager.get_proxy_url(token_id)
            response = await session.post(url, json=json_data, headers=headers, proxy=proxy_url)

            if response.status_code != 200:
                return prompt  # 失败则返回原句

            result = response.json()
            return result.get("enhanced_prompt", prompt)


# ==========================================
# 👇 将以下代码复制并粘贴到文件的最末尾 👇
# ==========================================

if __name__ == "__main__":
    import sys
    import logging

    # 1. 配置简易日志，方便看输出
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("DebugSora")


    # 2. Mock (模拟) 缺失的依赖类
    # 因为我们没有 .proxy_manager 和 ..core.config，这里做一个假的替代品
    class MockProxyManager:
        async def get_proxy_url(self, token_id=None):
            # 如果你有真实的代理 IP，填在这里，例如 "http://user:pass@ip:port"
            # 如果没有，留 None 尝试直连（可能会被 403）
            return None


    class MockConfig:
        sora_base_url = "https://sora.chatgpt.com"
        sora_timeout = 30
        pow_proxy_enabled = False
        pow_proxy_url = None


    # 3. 替换掉全局的 config 和 logger
    config = MockConfig()


    # 简单的 logger 包装
    class MockLogger:
        def log_info(self, msg): logger.info(msg)

        def log_error(self, **kwargs): logger.error(f"ERROR: {kwargs}")

        def log_request(self, **kwargs): logger.info(f"REQ: {kwargs.get('method')} {kwargs.get('url')}")

        def log_response(self, **kwargs): logger.info(
            f"RESP: {kwargs.get('status_code')} (Duration: {kwargs.get('duration_ms')}ms)")


    # 这里的 debug_logger 是模块全局变量，我们需要强制覆盖它以便调试
    import sys

    current_module = sys.modules[__name__]
    current_module.debug_logger = MockLogger()


    # 4. 核心测试函数
    async def test_main():
        logger.info("🚀 开始 iOS 模拟测试...")

        # 初始化 Client
        proxy_manager = MockProxyManager()
        client = SoraClient(proxy_manager)

        # 测试 1: 检查 PoW 配置是否为 iOS 特征
        logger.info("Checking PoW Config...")
        ua = random.choice(MOBILE_USER_AGENTS)
        pow_config = client._get_pow_config(ua)
        logger.info(f"📱 User-Agent: {ua[:50]}...")
        logger.info(f"📱 Screen Size: {pow_config[0]}")  # 应该是 390, 428 等
        logger.info(f"📱 Cores: {pow_config[16]}")  # 应该是 6
        logger.info(f"📱 Memory: {pow_config[2]}")  # 应该是 None

        if pow_config[16] != 6 or pow_config[2] is not None:
            logger.error("❌ PoW 配置错误！未检测到 iOS 特征！")
            return
        else:
            logger.info("✅ PoW 配置符合 iOS 标准")

        # 测试 2: 尝试获取 Sentinel Token (这是最难的一步)
        logger.info("\n🧪 尝试生成 Sentinel Token (模拟 iOS 网络请求)...")
        try:
            # 传入 None 让它自动生成 iOS UA
            token, used_ua = await client._generate_sentinel_token(token="fake_token")

            logger.info("🎉 Token 获取成功!")
            logger.info(f"Token preview: {token[:50]}...")

            # 解析 Token 看看 flow 是否正确
            token_data = json.loads(token)
            logger.info(f"Flow: {token_data.get('flow')}")

            if "iPhone" in used_ua:
                logger.info("✅ 请求使用的 User-Agent 确认为 iPhone")
            else:
                logger.error(f"❌ 请求使用了错误的 UA: {used_ua}")

        except Exception as e:
            logger.error(f"❌ Token 生成失败: {e}")
            logger.error("💡 提示: 如果是 403/429，请在 MockProxyManager 中填入有效的海外住宅代理 IP")

    # 运行测试
    if PLAYWRIGHT_AVAILABLE:
        asyncio.run(test_main())
    else:
        logger.error("需要安装 Playwright: pip install playwright && playwright install chromium")