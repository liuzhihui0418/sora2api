"""Token management module"""
import jwt
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from curl_cffi.requests import AsyncSession
from faker import Faker
from ..core.database import Database
from ..core.models import Token, TokenStats
from ..core.config import config
from .proxy_manager import ProxyManager
from ..core.logger import debug_logger

# ✅ 全局统一伪装：iPhone 15 Pro / iOS 17.4
FIXED_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"

class TokenManager:
    """Token lifecycle manager"""

    def __init__(self, db: Database):
        self.db = db
        self._lock = asyncio.Lock()
        self.proxy_manager = ProxyManager(db)
        self.fake = Faker()

    async def decode_jwt(self, token: str) -> dict:
        """Decode JWT token without verification"""
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            return decoded
        except Exception as e:
            raise ValueError(f"Invalid JWT token: {str(e)}")

    def _generate_random_username(self) -> str:
        """Generate a random username using faker"""
        first_name = self.fake.first_name()
        last_name = self.fake.last_name()
        first_name_clean = ''.join(c for c in first_name if c.isalpha())
        last_name_clean = ''.join(c for c in last_name if c.isalpha())
        random_digits = str(random.randint(1, 9999))

        format_choice = random.choice([
            f"{first_name_clean}{last_name_clean}{random_digits}",
            f"{first_name_clean}.{last_name_clean}{random_digits}",
            f"{first_name_clean}{random_digits}",
            f"{last_name_clean}{random_digits}",
            f"{first_name_clean[0]}{last_name_clean}{random_digits}",
            f"{first_name_clean}{last_name_clean[0]}{random_digits}"
        ])
        return format_choice.lower()

    async def get_user_info(self, access_token: str, token_id: Optional[int] = None, proxy_url: Optional[str] = None, user_agent: Optional[str] = None) -> dict:
        proxy_url = await self.proxy_manager.get_proxy_url(token_id, proxy_url)

        # ✅ 修正：优先使用传入的 UA，解决入库时的指纹冲突
        ua = user_agent or FIXED_USER_AGENT
        if not user_agent and token_id:
            token_data = await self.db.get_token(token_id)
            if token_data and token_data.user_agent:
                ua = token_data.user_agent

        async with AsyncSession(impersonate="safari15_5") as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": ua,  # <--- [关键修改：这里要用变量 ua，而不是 FIXED_USER_AGENT]
                "Origin": "https://sora.chatgpt.com",
                "Referer": "https://sora.chatgpt.com/"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30,
                # impersonate 已在 Session 初始化时设置
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            response = await session.get(
                f"{config.sora_base_url}/me",
                **kwargs
            )

            if response.status_code != 200:
                if response.status_code == 401:
                    try:
                        error_data = response.json()
                        error_code = error_data.get("error", {}).get("code", "")
                        if error_code == "token_invalidated":
                            raise ValueError(f"401 token_invalidated: Token has been invalidated")
                    except (ValueError, KeyError):
                        pass
                raise ValueError(f"Failed to get user info: {response.status_code}")

            return response.json()

    async def get_subscription_info(self, token: str, token_id: Optional[int] = None, proxy_url: Optional[str] = None, user_agent: Optional[str] = None) -> Dict[str, Any]:
        """Get subscription information from Sora API"""
        print(f"🔍 开始获取订阅信息...")
        proxy_url = await self.proxy_manager.get_proxy_url(token_id, proxy_url)

        # 获取专属 UA
        ua = FIXED_USER_AGENT
        if token_id:
            token_data = await self.db.get_token(token_id)
            if token_data and token_data.user_agent:
                ua = token_data.user_agent

        async with AsyncSession(impersonate="safari15_5") as session:
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": ua,  # <--- [修改这里]
                "Referer": "https://sora.chatgpt.com/"
            }

            url = "https://sora.chatgpt.com/backend/billing/subscriptions"
            print(f"📡 请求 URL: {url}")

            kwargs = {
                "headers": headers,
                "timeout": 30
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 使用代理: {proxy_url}")

            response = await session.get(url, **kwargs)
            print(f"📥 响应状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                # 提取第一个订阅信息
                if data.get("data") and len(data["data"]) > 0:
                    subscription = data["data"][0]
                    plan = subscription.get("plan", {})

                    result = {
                        "plan_type": plan.get("id", ""),
                        "plan_title": plan.get("title", ""),
                        "subscription_end": subscription.get("end_ts", "")
                    }
                    print(f"✅ 订阅信息提取成功: {result}")
                    return result

                print(f"⚠️  响应数据中没有订阅信息")
                return {
                    "plan_type": "",
                    "plan_title": "",
                    "subscription_end": ""
                }
            else:
                print(f"❌ Failed to get subscription info: {response.status_code}")
                # Check for token_expired error
                try:
                    error_data = response.json()
                    error_info = error_data.get("error", {})
                    if error_info.get("code") == "token_expired":
                        raise Exception(f"Token已过期: {error_info.get('message', 'Token expired')}")
                except ValueError:
                    pass

                raise Exception(f"Failed to get subscription info: {response.status_code}")

    async def get_sora2_invite_code(self, access_token: str, token_id: Optional[int] = None, proxy_url: Optional[str] = None, user_agent: Optional[str] = None) -> dict:
        """Get Sora2 invite code"""
        proxy_url = await self.proxy_manager.get_proxy_url(token_id, proxy_url)
        print(f"🔍 开始获取Sora2邀请码...")

        # ✅ 修正：使用 Safari 指纹
        async with AsyncSession(impersonate="safari15_5") as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": FIXED_USER_AGENT, # ✅ 强制 UA
                "Referer": "https://sora.chatgpt.com/"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            response = await session.get(
                "https://sora.chatgpt.com/backend/project_y/invite/mine",
                **kwargs
            )

            print(f"📥 响应状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Sora2邀请码获取成功: {data}")
                return {
                    "supported": True,
                    "invite_code": data.get("invite_code"),
                    "redeemed_count": data.get("redeemed_count", 0),
                    "total_count": data.get("total_count", 0)
                }
            else:
                print(f"❌ 获取Sora2邀请码失败: {response.status_code}")
                # Check for specific errors
                try:
                    error_data = response.json()
                    error_info = error_data.get("error", {})

                    if error_info.get("code") == "unsupported_country_code":
                        country = error_info.get("param", "未知")
                        raise Exception(f"Sora在您的国家/地区不可用 ({country}): {error_info.get('message', '')}")

                    if response.status_code == 401 and "Unauthorized" in error_info.get("message", ""):
                        print(f"⚠️  Token不支持Sora2，尝试激活...")
                        try:
                            # 激活也要用统一的指纹
                            activate_response = await session.get(
                                "https://sora.chatgpt.com/backend/m/bootstrap",
                                **kwargs
                            )

                            if activate_response.status_code == 200:
                                retry_response = await session.get(
                                    "https://sora.chatgpt.com/backend/project_y/invite/mine",
                                    **kwargs
                                )
                                if retry_response.status_code == 200:
                                    retry_data = retry_response.json()
                                    return {
                                        "supported": True,
                                        "invite_code": retry_data.get("invite_code"),
                                        "redeemed_count": retry_data.get("redeemed_count", 0),
                                        "total_count": retry_data.get("total_count", 0)
                                    }
                        except Exception as activate_e:
                            print(f"⚠️  Sora2激活过程出错: {activate_e}")

                except ValueError:
                    pass

                return {"supported": False, "invite_code": None}

    async def get_sora2_remaining_count(self, access_token: str, token_id: Optional[int] = None,
                                        proxy_url: Optional[str] = None, user_agent: Optional[str] = None) -> dict:
        """Get Sora2 remaining video count"""
        proxy_url = await self.proxy_manager.get_proxy_url(token_id, proxy_url)
        print(f"🔍 开始获取Sora2剩余次数...")

        # ✅ 修正：使用 Safari 指纹
        async with AsyncSession(impersonate="safari15_5") as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": FIXED_USER_AGENT # ✅ 强制 UA
            }

            kwargs = {
                "headers": headers,
                "timeout": 30
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            response = await session.get(
                "https://sora.chatgpt.com/backend/nf/check",
                **kwargs
            )

            if response.status_code == 200:
                data = response.json()
                rate_limit_info = data.get("rate_limit_and_credit_balance", {})
                return {
                    "success": True,
                    "remaining_count": rate_limit_info.get("estimated_num_videos_remaining", 0),
                    "rate_limit_reached": rate_limit_info.get("rate_limit_reached", False),
                    "access_resets_in_seconds": rate_limit_info.get("access_resets_in_seconds", 0)
                }
            else:
                return {
                    "success": False,
                    "remaining_count": 0,
                    "error": f"Failed to get remaining count: {response.status_code}"
                }

    async def check_username_available(self, access_token: str, username: str) -> bool:
        """Check if username is available"""
        proxy_url = await self.proxy_manager.get_proxy_url()

        # ✅ 修正：使用 Safari 指纹
        async with AsyncSession(impersonate="safari15_5") as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": FIXED_USER_AGENT
            }

            kwargs = {
                "headers": headers,
                "json": {"username": username},
                "timeout": 30
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            response = await session.post(
                "https://sora.chatgpt.com/backend/project_y/profile/username/check",
                **kwargs
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("available", False)
            else:
                return False

    async def set_username(self, access_token: str, username: str) -> dict:
        """Set username for the account"""
        proxy_url = await self.proxy_manager.get_proxy_url()

        # ✅ 修正：使用 Safari 指纹
        async with AsyncSession(impersonate="safari15_5") as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": FIXED_USER_AGENT
            }

            kwargs = {
                "headers": headers,
                "json": {"username": username},
                "timeout": 30
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            response = await session.post(
                "https://sora.chatgpt.com/backend/project_y/profile/username/set",
                **kwargs
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Failed to set username: {response.status_code}")

    async def activate_sora2_invite(self, access_token: str, invite_code: str) -> dict:
        """Activate Sora2 with invite code"""
        import uuid
        proxy_url = await self.proxy_manager.get_proxy_url()

        # ✅ 修正：使用 Safari 指纹
        async with AsyncSession(impersonate="safari15_5") as session:
            device_id = str(uuid.uuid4())
            headers = {
                "authorization": f"Bearer {access_token}",
                "cookie": f"oai-did={device_id}",
                "User-Agent": FIXED_USER_AGENT
            }

            kwargs = {
                "headers": headers,
                "json": {"invite_code": invite_code},
                "timeout": 30
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            response = await session.post(
                "https://sora.chatgpt.com/backend/project_y/invite/accept",
                **kwargs
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": data.get("success", False),
                    "already_accepted": data.get("already_accepted", False)
                }
            else:
                raise Exception(f"Failed to activate Sora2: {response.status_code}")

    async def st_to_at(self, session_token: str, proxy_url: Optional[str] = None,
                       user_agent: Optional[str] = None) -> dict:
        """Convert Session Token to Access Token"""
        debug_logger.log_info(f"[ST_TO_AT] 开始转换 Session Token 为 Access Token...")
        proxy_url = await self.proxy_manager.get_proxy_url(proxy_url=proxy_url)

        # ✅ 关键逻辑：优先使用传入的专属 UA，如果没有则用全局默认的
        current_ua = user_agent or FIXED_USER_AGENT

        async with AsyncSession(impersonate="safari15_5") as session:
            headers = {
                "Cookie": f"__Secure-next-auth.session-token={session_token}",
                "Accept": "application/json",
                "User-Agent": current_ua,  # <--- 这里改掉
                "Origin": "https://sora.chatgpt.com",
                "Referer": "https://sora.chatgpt.com/"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            url = "https://sora.chatgpt.com/api/auth/session"

            try:
                response = await session.get(url, **kwargs)
                if response.status_code != 200:
                    raise ValueError(f"Failed to convert ST to AT: {response.status_code}")

                data = response.json()
                access_token = data.get("accessToken")
                email = data.get("user", {}).get("email") if data.get("user") else None
                expires = data.get("expires")

                if not access_token:
                    raise ValueError("Missing accessToken in response")

                return {
                    "access_token": access_token,
                    "email": email,
                    "expires": expires
                }
            except Exception as e:
                debug_logger.log_info(f"[ST_TO_AT] 🔴 异常: {str(e)}")
                raise

    async def rt_to_at(self, refresh_token: str, client_id: Optional[str] = None, proxy_url: Optional[str] = None,
                       user_agent: Optional[str] = None) -> dict:
        """Convert Refresh Token to Access Token"""
        effective_client_id = client_id or "app_LlGpXReQgckcGGUo2JrYvtJK"
        proxy_url = await self.proxy_manager.get_proxy_url(proxy_url=proxy_url)

        # ✅ 关键逻辑：优先使用传入的专属 UA
        current_ua = user_agent or FIXED_USER_AGENT

        async with AsyncSession(impersonate="safari15_5") as session:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": current_ua  # <--- 这里改掉
            }

            kwargs = {
                "headers": headers,
                "json": {
                    "client_id": effective_client_id,
                    "grant_type": "refresh_token",
                    "redirect_uri": "com.openai.chat://auth0.openai.com/ios/com.openai.chat/callback",
                    "refresh_token": refresh_token
                },
                "timeout": 30
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            url = "https://auth.openai.com/oauth/token"

            try:
                response = await session.post(url, **kwargs)
                if response.status_code != 200:
                    raise ValueError(f"Failed to convert RT to AT: {response.status_code}")

                data = response.json()
                access_token = data.get("access_token")
                new_refresh_token = data.get("refresh_token")
                expires_in = data.get("expires_in")

                if not access_token:
                    raise ValueError("Missing access_token in response")

                return {
                    "access_token": access_token,
                    "refresh_token": new_refresh_token,
                    "expires_in": expires_in
                }
            except Exception as e:
                debug_logger.log_info(f"[RT_TO_AT] 🔴 异常: {str(e)}")
                raise

    async def add_token(self, token_value: str,
                       st: Optional[str] = None,
                       rt: Optional[str] = None,
                       user_agent: Optional[str] = None,  # <--- [新增参数]
                       client_id: Optional[str] = None,
                       proxy_url: Optional[str] = None,
                       remark: Optional[str] = None,
                       update_if_exists: bool = False,
                       image_enabled: bool = True,
                       video_enabled: bool = True,
                       image_concurrency: int = -1,
                       video_concurrency: int = -1,
                       skip_status_update: bool = False,
                       email: Optional[str] = None) -> Token:
        # Check if token already exists
        existing_token = await self.db.get_token_by_value(token_value)
        if existing_token:
            if not update_if_exists:
                raise ValueError(f"Token 已存在（邮箱: {existing_token.email}）。如需更新，请先删除旧 Token 或使用更新功能。")
            return await self.update_existing_token(existing_token.id, token_value, st, rt, remark)

        decoded = await self.decode_jwt(token_value)
        expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None

        jwt_email = None
        if "https://api.openai.com/profile" in decoded:
            jwt_email = decoded["https://api.openai.com/profile"].get("email")

        name = ""
        plan_type = None
        plan_title = None
        subscription_end = None
        sora2_supported = None
        sora2_invite_code = None
        sora2_redeemed_count = -1
        sora2_total_count = -1
        sora2_remaining_count = -1

        if skip_status_update:
            email = email or jwt_email or ""
            name = email.split("@")[0] if email else ""
        else:
            try:
                # ✅ 修正：传入 user_agent
                user_info = await self.get_user_info(token_value, proxy_url=proxy_url, user_agent=user_agent)
                email = user_info.get("email", jwt_email or "")
                name = user_info.get("name") or ""
            except Exception as e:
                email = jwt_email or ""
                name = email.split("@")[0] if email else ""

            try:
                sub_info = await self.get_subscription_info(token_value, proxy_url=proxy_url, user_agent=user_agent)
                plan_type = sub_info.get("plan_type")
                plan_title = sub_info.get("plan_title")
                if sub_info.get("subscription_end"):
                    from dateutil import parser
                    subscription_end = parser.parse(sub_info["subscription_end"])
            except Exception as e:
                error_msg = str(e)
                if "Token已过期" in error_msg:
                    raise
                print(f"Failed to get subscription info: {e}")

            sora2_redeemed_count = 0
            sora2_total_count = 0
            sora2_remaining_count = 0
            try:
                sora2_info = await self.get_sora2_invite_code(token_value, proxy_url=proxy_url)
                sora2_supported = sora2_info.get("supported", False)
                sora2_invite_code = sora2_info.get("invite_code")
                sora2_redeemed_count = sora2_info.get("redeemed_count", 0)
                sora2_total_count = sora2_info.get("total_count", 0)

                if sora2_supported:
                    try:
                        remaining_info = await self.get_sora2_remaining_count(token_value, proxy_url=proxy_url)
                        if remaining_info.get("success"):
                            sora2_remaining_count = remaining_info.get("remaining_count", 0)
                    except Exception as e:
                        print(f"Failed to get Sora2 remaining count: {e}")
            except Exception as e:
                error_msg = str(e)
                if "Sora在您的国家/地区不可用" in error_msg:
                    raise
                print(f"Failed to get Sora2 info: {e}")

            try:
                user_info = await self.get_user_info(token_value, proxy_url=proxy_url)
                username = user_info.get("username")

                if username is None:
                    max_attempts = 5
                    for attempt in range(max_attempts):
                        generated_username = self._generate_random_username()
                        if await self.check_username_available(token_value, generated_username):
                            try:
                                await self.set_username(token_value, generated_username)
                                break
                            except Exception:
                                pass
            except Exception as e:
                print(f"⚠️  用户名检查/设置过程中出错: {e}")

        token = Token(
            token=token_value,
            email=email,
            name=name,
            st=st,
            rt=rt,
            user_agent=user_agent,  # <--- [关键：存入对象]
            client_id=client_id,
            proxy_url=proxy_url,
            remark=remark,
            expiry_time=expiry_time,
            is_active=True,
            plan_type=plan_type,
            plan_title=plan_title,
            subscription_end=subscription_end,
            sora2_supported=sora2_supported,
            sora2_invite_code=sora2_invite_code,
            sora2_redeemed_count=sora2_redeemed_count,
            sora2_total_count=sora2_total_count,
            sora2_remaining_count=sora2_remaining_count,
            image_enabled=image_enabled,
            video_enabled=video_enabled,
            image_concurrency=image_concurrency,
            video_concurrency=video_concurrency
        )

        token_id = await self.db.add_token(token)
        token.id = token_id

        return token

    async def update_existing_token(self, token_id: int, token_value: str,
                                    st: Optional[str] = None,
                                    rt: Optional[str] = None,
                                    remark: Optional[str] = None) -> Token:
        decoded = await self.decode_jwt(token_value)
        expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None

        jwt_email = None
        if "https://api.openai.com/profile" in decoded:
            jwt_email = decoded["https://api.openai.com/profile"].get("email")

        try:
            user_info = await self.get_user_info(token_value)
            email = user_info.get("email", jwt_email or "")
            name = user_info.get("name", "")
        except Exception as e:
            email = jwt_email or ""
            name = email.split("@")[0] if email else ""

        plan_type = None
        plan_title = None
        subscription_end = None
        try:
            sub_info = await self.get_subscription_info(token_value)
            plan_type = sub_info.get("plan_type")
            plan_title = sub_info.get("plan_title")
            if sub_info.get("subscription_end"):
                from dateutil import parser
                subscription_end = parser.parse(sub_info["subscription_end"])
        except Exception as e:
            print(f"Failed to get subscription info: {e}")

        await self.db.update_token(
            token_id=token_id,
            token=token_value,
            st=st,
            rt=rt,
            remark=remark,
            expiry_time=expiry_time,
            plan_type=plan_type,
            plan_title=plan_title,
            subscription_end=subscription_end
        )

        updated_token = await self.db.get_token(token_id)
        return updated_token

    async def delete_token(self, token_id: int):
        await self.db.delete_token(token_id)

    async def update_token(self, token_id: int,
                          token: Optional[str] = None,
                          st: Optional[str] = None,
                          rt: Optional[str] = None,
                          user_agent: Optional[str] = None,  # <--- [新增参数]
                          client_id: Optional[str] = None,
                          proxy_url: Optional[str] = None,
                          remark: Optional[str] = None,
                          image_enabled: Optional[bool] = None,
                          video_enabled: Optional[bool] = None,
                          image_concurrency: Optional[int] = None,
                          video_concurrency: Optional[int] = None,
                          skip_status_update: bool = False):
        expiry_time = None
        if token:
            try:
                decoded = await self.decode_jwt(token)
                expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None
            except Exception:
                pass

        await self.db.update_token(token_id, token=token, st=st, rt=rt, user_agent=user_agent, client_id=client_id, proxy_url=proxy_url, remark=remark, expiry_time=expiry_time,
                                   image_enabled=image_enabled, video_enabled=video_enabled,
                                   image_concurrency=image_concurrency, video_concurrency=video_concurrency)

        if token and not skip_status_update:
            try:
                test_result = await self.test_token(token_id)
                if test_result.get("valid"):
                    await self.db.update_token_status(token_id, True)
                    await self.db.clear_token_expired(token_id)
            except Exception:
                pass

    async def get_active_tokens(self) -> List[Token]:
        return await self.db.get_active_tokens()

    async def get_all_tokens(self) -> List[Token]:
        return await self.db.get_all_tokens()

    async def update_token_status(self, token_id: int, is_active: bool):
        await self.db.update_token_status(token_id, is_active)

    async def enable_token(self, token_id: int):
        await self.db.update_token_status(token_id, True)
        await self.db.reset_error_count(token_id)
        await self.db.clear_token_expired(token_id)

    async def disable_token(self, token_id: int):
        await self.db.update_token_status(token_id, False)

    async def test_token(self, token_id: int) -> dict:
        token_data = await self.db.get_token(token_id)
        if not token_data:
            return {"valid": False, "message": "Token not found"}

        try:
            user_info = await self.get_user_info(token_data.token, token_id)

            plan_type = None
            plan_title = None
            subscription_end = None
            try:
                sub_info = await self.get_subscription_info(token_data.token, token_id)
                plan_type = sub_info.get("plan_type")
                plan_title = sub_info.get("plan_title")
                if sub_info.get("subscription_end"):
                    from dateutil import parser
                    subscription_end = parser.parse(sub_info["subscription_end"])
            except Exception as e:
                print(f"Failed to get subscription info: {e}")

            sora2_info = await self.get_sora2_invite_code(token_data.token, token_id)
            sora2_supported = sora2_info.get("supported", False)
            sora2_invite_code = sora2_info.get("invite_code")
            sora2_redeemed_count = sora2_info.get("redeemed_count", 0)
            sora2_total_count = sora2_info.get("total_count", 0)
            sora2_remaining_count = 0

            if sora2_supported:
                try:
                    remaining_info = await self.get_sora2_remaining_count(token_data.token, token_id)
                    if remaining_info.get("success"):
                        sora2_remaining_count = remaining_info.get("remaining_count", 0)
                except Exception as e:
                    print(f"Failed to get Sora2 remaining count: {e}")

            await self.db.update_token(
                token_id,
                plan_type=plan_type,
                plan_title=plan_title,
                subscription_end=subscription_end
            )

            await self.db.update_token_sora2(
                token_id,
                supported=sora2_supported,
                invite_code=sora2_invite_code,
                redeemed_count=sora2_redeemed_count,
                total_count=sora2_total_count,
                remaining_count=sora2_remaining_count
            )

            await self.db.clear_token_expired(token_id)

            return {
                "valid": True,
                "message": "Token is valid and account info updated",
                "email": user_info.get("email"),
                "username": user_info.get("username"),
                "plan_type": plan_type,
                "plan_title": plan_title,
                "subscription_end": subscription_end.isoformat() if subscription_end else None,
                "sora2_supported": sora2_supported,
                "sora2_invite_code": sora2_invite_code,
                "sora2_redeemed_count": sora2_redeemed_count,
                "sora2_total_count": sora2_total_count,
                "sora2_remaining_count": sora2_remaining_count
            }
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg and "token_invalidated" in error_msg.lower():
                await self.db.mark_token_expired(token_id)
                return {
                    "valid": False,
                    "message": "Token已过期（token_invalidated）"
                }
            return {
                "valid": False,
                "message": f"Token is invalid: {error_msg}"
            }

    async def record_usage(self, token_id: int, is_video: bool = False):
        await self.db.update_token_usage(token_id)
        if is_video:
            await self.db.increment_video_count(token_id)
        else:
            await self.db.increment_image_count(token_id)

    async def record_error(self, token_id: int, is_overload: bool = False):
        await self.db.increment_error_count(token_id, increment_consecutive=not is_overload)
        if not is_overload:
            stats = await self.db.get_token_stats(token_id)
            admin_config = await self.db.get_admin_config()
            if stats and stats.consecutive_error_count >= admin_config.error_ban_threshold:
                await self.db.update_token_status(token_id, False)

    async def record_success(self, token_id: int, is_video: bool = False):
        await self.db.reset_error_count(token_id)
        if is_video:
            try:
                token_data = await self.db.get_token(token_id)
                if token_data and token_data.sora2_supported:
                    remaining_info = await self.get_sora2_remaining_count(token_data.token, token_id)
                    if remaining_info.get("success"):
                        remaining_count = remaining_info.get("remaining_count", 0)
                        await self.db.update_token_sora2_remaining(token_id, remaining_count)

                        if remaining_count <= 1:
                            reset_seconds = remaining_info.get("access_resets_in_seconds", 0)
                            if reset_seconds > 0:
                                cooldown_until = datetime.now() + timedelta(seconds=reset_seconds)
                                await self.db.update_token_sora2_cooldown(token_id, cooldown_until)
                            await self.disable_token(token_id)
            except Exception as e:
                print(f"Failed to update Sora2 remaining count: {e}")

    async def refresh_sora2_remaining_if_cooldown_expired(self, token_id: int):
        try:
            token_data = await self.db.get_token(token_id)
            if not token_data or not token_data.sora2_supported:
                return

            if token_data.sora2_cooldown_until and token_data.sora2_cooldown_until <= datetime.now():
                try:
                    remaining_info = await self.get_sora2_remaining_count(token_data.token, token_id)
                    if remaining_info.get("success"):
                        remaining_count = remaining_info.get("remaining_count", 0)
                        await self.db.update_token_sora2_remaining(token_id, remaining_count)
                        await self.db.update_token_sora2_cooldown(token_id, None)
                except Exception as e:
                    print(f"Failed to refresh Sora2 remaining count: {e}")
        except Exception as e:
            print(f"Error in refresh_sora2_remaining_if_cooldown_expired: {e}")

    async def auto_refresh_expiring_token(self, token_id: int) -> bool:
        try:
            debug_logger.log_info(f"[AUTO_REFRESH] 开始检查Token {token_id}...")
            token_data = await self.db.get_token(token_id)

            if not token_data:
                return False

            if not token_data.expiry_time:
                return False

            time_until_expiry = token_data.expiry_time - datetime.now()
            hours_until_expiry = time_until_expiry.total_seconds() / 3600

            if hours_until_expiry > 24:
                return False

            new_at = None
            new_st = None
            new_rt = None

            if token_data.st:
                try:
                    # ✅ 核心改动：把数据库里的 user_agent 传过去
                    result = await self.st_to_at(token_data.st, proxy_url=token_data.proxy_url,
                                                 user_agent=token_data.user_agent)
                    new_at = result.get("access_token")
                    new_st = token_data.st
                except Exception:
                    new_at = None

            if not new_at and token_data.rt:
                try:
                    # ✅ 核心改动：把数据库里的 user_agent 传过去
                    result = await self.rt_to_at(token_data.rt, client_id=token_data.client_id,
                                                 proxy_url=token_data.proxy_url, user_agent=token_data.user_agent)
                    new_at = result.get("access_token")
                    new_rt = result.get("refresh_token", token_data.rt)
                except Exception:
                    new_at = None

            if new_at:
                await self.update_token(token_id, token=new_at, st=new_st, rt=new_rt)
                updated_token = await self.db.get_token(token_id)
                new_expiry_time = updated_token.expiry_time
                new_hours_until_expiry = ((new_expiry_time - datetime.now()).total_seconds() / 3600) if new_expiry_time else -1

                if new_hours_until_expiry < 0:
                    await self.db.mark_token_expired(token_id)
                    await self.db.update_token_status(token_id, False)
                    return False

                return True
            else:
                await self.db.mark_token_expired(token_id)
                await self.db.update_token_status(token_id, False)
                return False

        except Exception as e:
            debug_logger.log_info(f"[AUTO_REFRESH] 🔴 Token {token_id}: 自动刷新异常 - {str(e)}")
            return False

    async def batch_refresh_all_tokens(self) -> dict:
        debug_logger.log_info("[BATCH_REFRESH] 🔄 开始批量刷新所有Token...")
        all_tokens = await self.db.get_all_tokens()

        success_count = 0
        failed_count = 0
        skipped_count = 0

        for token in all_tokens:
            if not token.st and not token.rt:
                skipped_count += 1
                continue

            if not token.expiry_time:
                skipped_count += 1
                continue

            time_until_expiry = token.expiry_time - datetime.now()
            hours_until_expiry = time_until_expiry.total_seconds() / 3600

            if hours_until_expiry > 24:
                skipped_count += 1
                continue

            try:
                result = await self.auto_refresh_expiring_token(token.id)
                if result:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception:
                failed_count += 1

        return {
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "total": len(all_tokens)
        }