import asyncio
from src.core.database import Database
from src.services.token_manager import TokenManager


async def main():
    db = Database()
    tm = TokenManager(db)

    # 这里定义你要批量加的账号列表
    # 格式：(邮箱, ST, 专属UA)
    accounts_to_import = [
        ("user1@gmail.com", "eyJhbG...st1", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4...)"),
        ("user2@gmail.com", "eyJhbG...st2", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5...)"),
        ("user3@gmail.com", "eyJhbG...st3", "Mozilla/5.0 (iPad; CPU OS 17_6...)"),
        # ... 这里可以放几百个 ...
    ]

    for email, st, ua in accounts_to_import:
        try:
            print(f"正在导入: {email}...")
            # token_value 传占位符，因为 st_to_at 会自动更新它
            await tm.add_token(
                token_value=f"temp_{email}",
                email=email,
                st=st,
                user_agent=ua,
                is_active=True
            )
            print(f"✅ {email} 导入成功")
        except Exception as e:
            print(f"❌ {email} 导入失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())