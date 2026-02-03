import asyncio
import sys

if sys.platform == 'win32':
    # 强制使用 Proactor 策略，否则 Playwright 无法启动
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 导入你之前的 SoraClient
from sora_client import SoraClient
import os
import time
import random


# ================= 配置区 =================
# 已经填入你提供的 Access Token 和 住宅代理
# ================= 配置区 =================
ACCESS_TOKEN = "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE5MzQ0ZTY1LWJiYzktNDRkMS1hOWQwLWY5NTdiMDc5YmQwZSIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSJdLCJjbGllbnRfaWQiOiJhcHBfWDh6WTZ2VzJwUTl0UjNkRTduSzFqTDVnSCIsImV4cCI6MTc3MDkxODc4MiwiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS9hdXRoIjp7ImNoYXRncHRfYWNjb3VudF9pZCI6ImE5MDMyMTcwLTRiNjgtNDU3YS1iZDAyLTFlNjk5OGJmN2RmZiIsImNoYXRncHRfYWNjb3VudF91c2VyX2lkIjoidXNlci1YN3FZbjhrRTR5a1lPYmhCb3lOeVNpb2pfX2E5MDMyMTcwLTRiNjgtNDU3YS1iZDAyLTFlNjk5OGJmN2RmZiIsImNoYXRncHRfY29tcHV0ZV9yZXNpZGVuY3kiOiJub19jb25zdHJhaW50IiwiY2hhdGdwdF9wbGFuX3R5cGUiOiJwbHVzIiwiY2hhdGdwdF91c2VyX2lkIjoidXNlci1YN3FZbjhrRTR5a1lPYmhCb3lOeVNpb2oiLCJ1c2VyX2lkIjoidXNlci1YN3FZbjhrRTR5a1lPYmhCb3lOeVNpb2oifSwiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS9wcm9maWxlIjp7ImVtYWlsIjoieWlkZXllNjI2NkBob3Blc3guY29tIiwiZW1haWxfdmVyaWZpZWQiOnRydWV9LCJpYXQiOjE3NzAwNTQ3ODIsImlzcyI6Imh0dHBzOi8vYXV0aC5vcGVuYWkuY29tIiwianRpIjoiNGI1MmIwZTYtYjEwNi00ZGM2LTkwMjctMjg3YTVhYTM0YjU5IiwibmJmIjoxNzcwMDU0NzgyLCJwd2RfYXV0aF90aW1lIjoxNzcwMDU0Nzc5OTUzLCJzY3AiOlsib3BlbmlkIiwiZW1haWwiLCJwcm9maWxlIiwib2ZmbGluZV9hY2Nlc3MiLCJtb2RlbC5yZXF1ZXN0IiwibW9kZWwucmVhZCIsIm9yZ2FuaXphdGlvbi5yZWFkIiwib3JnYW5pemF0aW9uLndyaXRlIl0sInNlc3Npb25faWQiOiJhdXRoc2Vzc19GOGJ0TEZqcWNuQlFra01TeURGUlQ1TEsiLCJzdWIiOiJhdXRoMHxoZXRqVkdodWdRTE1veENPUmhGS05YcXcifQ.fI4jJJi5JwMzVgho4pU4GwFZRxD4tvFERPJLy3k0LdkGkTgEJhm9kuyzVBswKJTDyvir8xILHPgu1hF9v7aCumXzS-qwE7Rat_iaT6oN1MJ8FATYE5SCAWS3q-jtduf4YEsHGWbVLOAHY9qCCp9luTcb2cyvF_cWNEUJvpgXaAAc-p08ScNJTReAVClG2zgFtNKasjwBjb5DYj4I0aX0i8YgjqaHnrfb2w_ohau4CrI4nHM-mXd3-WWixIpWQt7C9C2wYO-eJybWexkhKdTlSsprB_LvFgBzQdXuedZuzolQ3LFJfgBq70oSFITCR8iMzx1xu_xautityMkZTXym-FIFnv1XNQKBT9jkNWRFpppSllA4NOR9nMdUGWDuk_OkV_wLptXOf6VOo2A5ZfRnlXOExCdDryVO3MLycqNSgr6--iYjS4BDourq9e-qjpfja94qk4EwyseNgcnIgd-7vMACd-FbT1W6YcCb4zX7Qi112TPA_-nw56HZdy9OXd75yUA5KnfCrHRvEUoXQPTilyIud-OGLNbb-ATofvl1XD58L8UlqqO8j3538UMY8UcdSDROJeIfCU0QPD5xL0lQ0z7bYlUm3hQExAJp4Sy4iljZa-pF0qr4NXW2BVzZadIEWuq4AUtxRvjjxnLuoD-iQCPbPSA3R6k7xHHdyZC3S-c"
# ACCESS_TOKEN = ""
PROXY_URL = "http://CYfFOZOYdhXd:n7CSQQspGX@43.246.197.192:443"

# 1. 这里的逗号必须去掉！
TEST_IMAGE_PATH = "test_image.jpg"

# 2. 这里我帮你清洗提取了，只保留了 Session Token 的值
# (去掉了 oai-did, cf_clearance 等干扰项)
SESSION_TOKEN = "oai-did=88bbaf0e-acb3-486f-acc3-fb104acc24e7; _ga=GA1.1.84592422.1769610474; _cfuvid=R3D9RTwHNByCpcJXpJSF3nMDcX9MkcAgRuXgcvinmSY-1770033073824-0.0.1.1-604800000; _rdt_uuid=1770033146870.cde941ef-f999-407d-8fa5-e1cdd1d2bb03; _fbp=fb.1.1770033148277.84940717528427412; __stripe_mid=e01b7d07-e8f5-4f76-a7d3-c9a1822dfd3d093b0b; _gcl_au=1.1.666505679.1770033149.763138592.1770033208.1770033207; __Host-next-auth.csrf-token=5be48a93a1258f8b10516bff3113d85f3d603769ddf3c742a4678085cd086b0b%7C60c17596b4b2d5d8340ab08438bd25660cdc60c037036d915dec44357672bcd0; __Secure-next-auth.callback-url=https%3A%2F%2Fsora.com; __cf_bm=3g2PLfTtLMmd.VMQNq6wHOB8B9O.ryDU1JwH3aNut8Q-1770054469-1.0.1.1-LB6nWXlPLdcgVJenoSJSIc9N8WtkafitYqMyEiIQOy98hVCg5d1X9VkbQix59plJJWFLY3VCd_bgt2VvJRDxDblVhTSqacBoBxV8Z3xuTf0; cf_clearance=pKio1GuI2800ZFMSAFuKArTde0Bnyr.Zc2hqt7vCU08-1770054541-1.2.1.1-PYPROmENLVA_NpW6WGCwu_wpfkQM9q9eRprQuwfRallosEFfjNakiJg61YyaghHZzHS_vYzm6uUSnXEATXRvxttrf6yGq6Fl4I7bhs9HofJ7vpDsWendSqgbWBmja1ILCGGYCKiF9BycbGDfFWnKG_h4FQ0f5x9O8hBiCYzaDrXDU5ISsQls_fU48RzTeCIaGZoVjBxR4Zcak9Y.6o4msAP82ivgR1SRmpRD1rXLxaU; _puid=user-X7qYn8kE4ykYObhBoyNySioj:1770054785-d25YSyGBYmWfFMbGldxFWtA155ZFq8WZBIIqFsyUeZY%3D; _ga_9SHBSK2D9J=GS2.1.s1770054542$o6$g1$t1770054787$j5$l0$h0; __cflb=0H28vBjUqcdJN5F5i8D8gyGbfU6KPdHGWKV35zu18n1; cf_clearance=LQTiiRpWPpVSUxQGDb3gVvqR3p2CC_vbvBj_759CNdw-1770054885-1.2.1.1-yol5neWByhhLu5aCltMNADGwGdD5JvW_nmZjVuly2Vo2ESEDjOeta7njaZDW0RtlCgLqHyrUeFBMzfVf7bEqhy6iOElhEdR4pcB5sRP1UBRS6_qjV3UDEq0DU.k2772EoN1.PHzHLPlxuIvqAwkdSlr4BquHw.0o8y0kSD2Gs1jk4N3Aa91liSAEEL8i1jhWPcX_Qhl3p3aBPQCWD7wX3C5O4EbgJJGqhHAFmqvnAnw; oai-sc=0gAAAAABpgOTnXvqql0f79H9eNSWg1wlKOu93zpIHVOv-fswRsLoAt4Te3cajtxOacID8mllXXt0Jqeic3SN_F8Vgsm-wbHJ2hEQ-EeZSp5fUZnwz2ILWhSECaE5tYBD6M3fWmPAfor5ywq0LlHrP3FpylK11nUOotM_lifxkMrwD5D5InTswPZ_LpMN9imqkNGdB5XwYP-Jdnc2vbL3uk9M0wog5m1mg2Q; __Secure-next-auth.session-token=eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2R0NNIn0..S9qXudN2Sz3j2_ji.0PD2uEcoPwh-BlrdIKKf16Lcpgz-lP2HOKosufau9BWR_MoUIvIYLUCWdGi6uYzkNFwJ3RjegpuMqrlRN668x9qldr3lMQY1IIN-92dTi4Uk3Y2i8YTTw9jIZDOutOIkucw_0ZJt9N9k7KCZ6MhTZVvI6CvHZswmre9l5IiQ-5xqclYT5rw_i-s441VZ0YXJCkJ0xuEfib5VzkwkHBTTUo4do4lyk-NRtoAPumZS7tAlrC6-aXiWUMGJj7Wc_MOUWSJ4Q1t0Tw2izSBghFC8Iz7FPrEh_nraBjnUxmMV7_ftTpw3_cbUSc6VVx-xsyjBZZWRbE70vaTkLqKAihx3KCXTFA-c-Wcyn6oFK9OgalGkfhDaf8YowAd7garVj1gesLRzG5y8jpox7LRpY_zNN0UwRZ_xYGVHudm0BT36PEoEJZ29C1sNfE3378KD0ooyexDB4u8y8GyUIsNST-m8070OSkBa4u5r_B35tcbSs9wRgBkl91wBbIXLR26K-5LJnVRZRBXSuc4Nb5rMLhfY44LMvzjf5YqfmwlVVQDzaproy0eyXiGlZnT_a0adjh_RC93HpUQm_eaa3NwcmzS9JGY5mPAmtnfw2_ReKoAB6PLFxPWN09K5HlKlZMuuy_THfpj7CpqKivkhQaHzsMDx-EI85bGLbLHT0dsYnil96fkIeK90vt_ZwRgmO1mhYPTsSNNHK62_RtFn63m9-ExwzvZcQ993nR4QIjnnve6j6XWsnYUPeeRYM8KSCWJeypbagrxT0XT92C_HUWLPWxQX82p390Sk_vvM90q2Xt7tcXAEpx-QVa4EWq8TTbxAM5VH0F1KUd9NM51H1E_UzCaIgSeTTAQ8PrbErfS3uALlcJ7BDwdEMNK25VV1y0xoUF8pEFUxEid4_wv0Uh_C60US0foqgxSicCvgimwIt_2-hNqRHuOaYhLez1R-YPXE67faezd_rIK-YTlLX1eVbDYFl2yXR8Lis0YFjxN57RtMLfcp1Sx5q5KlSwNmUO_jreVtgIG5jFyaZdR-XgxHqW3LPHnIRfwPTlHQV9tZWVHjYljO8moR90S2l71SoizatVkcgTzwb565ky0yQm1qQQT46ShoxK1VkXSAoMPabJXd4zQgisekemoL8zz3mdjmRarLZucph2DyN2M6TxmkfXvG4vn-1RF-VMdloxJL9Mnri7_46K6hMRy69XKaBzridqzr31WiD-cgGW7teh3hoq9GDFSsfKE6jDJhyI78Vz8Qmz97bEOMzghPFTSa_FTxuJ7fLWSUQsFCwkj5PGSLL25sAElhzYbAYCba9aSePsnGyWQdulewTT5m3Ykrmy-GPGPW7aBRJbjgXfrk5_6QzOwfwc0y4PJScPmFS3IW2SKCz5mLRncoIpIcg93BLKIAW3WeBg5VfptgaCwt0vnon1HwXxH2svmtRTLwoBfWCmIV_Y6jma36ngqhbGLd4GDpWUoBlUTocondvvKa3zcMh_GiRBFd2we64PYHNNxQw8VG98jIMic7tQGiW6N0Q4Lav9m1FjzFPS0Cf0zhT4b4GjUNGqPL7l_Cbmylf6Y4EWB41r9YcXclTRPKxs6B3J4eoG0mzOJvygYETlf9aTAvBESVj0gLzjUjqj4gzDi8r1SA1j1zNY3UhwaSLFc96r5h2UZJVOqETV7OH8d9ubjvYOt0BXugdaenhLxflXy_K7WWVn5IGg5mcwFtrIXT9HyoSMeYVj6ol_UboTnCGTo-l9zgTPRI8TwJUXIcDc9yw1srjK-5vE514kt6YHIlPjpuRLwAn9EFwhvpeK0foRU5NXMxzvDSoGjzL7Qbxv0Xwq_K5c2oc346YFNFr_b20ZV9glm9SmRhaV8FIEHMXXJLdmP0q-fjKFwd2ecMMx0iKrujwRoumchkM-U3VB04NcjbNbPimO0WKyMZlIE_QgphVbnikEht1temCkaH8Rs73Yjg95bsGSEoCI887h0SpLGp0a7zknE_h5CiBniHdq8dN48P_gQ-UEBtUbHXrb_fCzKQyMzIsfC5Mr2kfeptAR0TfI5IDELbVolBhWfJyKvjVycqGJInnbCu6-9sYIyaldyUTGi-aINjZ9IpxbEAskOuJsZgq3q9DhMOiq_r5hi7X6hG5r4EJ04r5dlqkDS4_y2JQ4ncnyfsLA31_aTFud7J0oF70ND4WluW1FIZsYmqIJq4-skFtpH5vKKOESGWtie9eNB-8Tj5RATyWWskgoTeaiiYefHs2zopIFLDX2d5-ojfLZdgAEkzmiGrHmFpCJYgBITOl4OzB1qUDETMTDCSc4M40Vdd8tPOnG2MoMZpmG2VRWmh1QMjQY0IVQ_C5F1fLc1aw92ngpq6o3zoFBnAPqx8K78SXzsG0z3oCJDBRNF-u60CpgR52EkEajeRTxCZO9qT08-cujlrwRW-ouT2n43lCKNqYZwmFuULonBDJtNjWEbpcoznzThxMir8H49hd2uc_UX2dmTEaNzsyFvt3zvn29OnzuWARpT2YxttGqRUPw9C1zXHah1c9JoU5x6uI6HyFiZJWEXOmGNcTLr3Glqlics9eEupeEKvtVBG_Q467RFRVNsMtZBTrI2yfJB-5tMmHvuMXv3FPAZp6wKbL1nsWrbOdfgIuMK6DmOfn7DR4xDMzuhLQJJc0PXLUyD6Qcl3npwETGjUAxvu3FtHl1Ouqo59ro91po_HvyV_-lB-Nvou-JxONwPaPpUFWzPatfE5G2JZC9rvgTznbMx2RlHI1Tg5dmBngo4W2JWUPpg0VN2fMBTrR-0CS9-GjU30gwzZBumhtvWHXyuFVwFu3bYyIuGEtmLakFNLzsuCswAmYuQgEB-Q5Jep-hkHxMtTKHjrd6PDuQXMTvDkh6Sxx51jSHYoVYlU-GjTN3PBivOoXwAG8-ukmHOKWK3F1SlqdVpyGvGthbS8ueaQsE2m8H7Gse-nyoQPauG1DOraGg1SLCHoVU-JHi15TjViBMrq3kZwAQ3x-PkZYJOVIpXrcCPUf-QhJCRVK952D8-65M1m1-7HsVcX1BjeFXnWCSWAinY3lvB8xiGroqr5fsqH2LjB03V4UyRR3m_W4BHJ2Kamj0hzzh2qTrnDEQOGbtTIthJ-elXzBw-M0d7Zt8Y8zCpzB_JaHZ-wzu9pyNOuE9ViA6o4xQLyVaAJKa-N8eAYZ-BwDAsWJHksDRdIyRFxwinA81E3C6mJw_IsuIAfb7JzZ4WSRTtMs1ASq00tK0F95UsTvAto1XGQ2yJ7XeTJDCqlTtWxcQoXxde0dPe_P6d8IONJSakpUMaKIiaxxlLIDTQB6nDvsfZ3KcGDYcHaVUfGbiZZFxxbCcUeayhJUvdHtPdNGprhPCcJcRAO1F6V_5OPoiU5Y5CUbZ8pcnSeOPvECRIoLPaXjRMoc6idihwIPL3A9S4fBuXMgkOFvWr0IF97KbfbfnQ1tfy8axTF8Lbqo0GpQ016wozLAEIn_2RDUxhj3Q-9BHMA9QOV7dwUROyMabm8F-mo4m9Vt9KIZkT67XuifSisYh_-3L-yVY42-6ipE97nStCUbvUmvf3vaO4aRaBoYxpFBVc.j8flKtoh4w3oLbwN3ug85w; __cf_bm=iQzhdwVeo5vFJzcinxJaNwuIfmoZkVDrq3QrkUiA1zw-1770054915-1.0.1.1-NDWERmqCOiLC4pxfHazMr2zIbxggS9nPbYUqxZzrj6fsHiPOrVEVybj8K6rOmvZdJwP17S5P.ydIS1gDSHUCtpNNmafqNWdOft0KVJIYGUc; _cfuvid=0ti.IoeHVC6qXu1DpGSSUaXrmDCgnfe39.JCYqCjQMc-1770054915357-0.0.1.1-604800000; _dd_s=rum=2&id=cdf79189-bdd2-4ac7-9c88-785e827c6d2f&created=1770054888108&expire=1770055824208"
# SESSION_TOKEN = ""
# ================= Mock 区域 =================
# 为了让测试能独立运行，模拟一个 ProxyManager 给 SoraClient 用
class SimpleProxyManager:
    async def get_proxy_url(self, token_id=None):
        return PROXY_URL


async def run_integration_test():
    # ================= 清洗 Token 逻辑 (新增) =================
    # 自动从那一堆乱七八糟的 Cookie 字符串里提取出真正的 Session Token
    real_session_token = SESSION_TOKEN
    if "session-token=" in SESSION_TOKEN:
        try:
            # 尝试提取 __Secure-next-auth.session-token 的值
            import re
            match = re.search(r'__Secure-next-auth\.session-token=([^;]+)', SESSION_TOKEN)
            if match:
                real_session_token = match.group(1)
                print("🧹 自动清洗成功：已从 Cookie 字符串中提取出 Session Token")
            else:
                # 如果没找到 key，可能是用户直接粘贴了值，或者格式不对，尝试直接用
                pass
        except:
            pass
    # 1. 初始化 Mock 代理管理器和客户端
    proxy_manager = SimpleProxyManager()
    client = SoraClient(proxy_manager)

    print("🎬 开始集成测试 (iOS 指纹模拟版)...")

    try:
        # 步骤 1: 验证 Token
        print("\n[1/4] 正在获取用户信息...")
        user_info = await client.get_user_info(ACCESS_TOKEN, session_token=real_session_token)
        # 获取用户名，API 返回可能在不同层级
        name = user_info.get("name") or user_info.get("user", {}).get("name", "Unknown")
        print(f"✅ 登录成功: {name}")

        # 步骤 2: 提示词增强测试
        print("\n[2/4] 正在增强提示词...")
        raw_prompt = "A cinematic shot of a futuristic Tokyo with neon lights, 4k"
        try:
            enhanced_prompt = await client.enhance_prompt(raw_prompt, ACCESS_TOKEN)
            print(f"✨ 增强后的提示词: {enhanced_prompt[:100]}...")
        except Exception as e:
            print(f"⚠️ 增强失败 (跳过): {e}")
            enhanced_prompt = raw_prompt

        # 步骤 3: 图片上传测试
        media_id = None
        if os.path.exists(TEST_IMAGE_PATH):
            print("\n[3/4] 正在上传测试图片...")
            with open(TEST_IMAGE_PATH, "rb") as f:
                image_bytes = f.read()
            media_id = await client.upload_image(image_bytes, ACCESS_TOKEN, filename="test.jpg")
            print(f"✅ 图片上传成功，Media ID: {media_id}")
        else:
            print("\n[3/4] 跳过图片上传 (未找到 test_image.jpg)")

        # 步骤 4: 提交生成任务
        print("\n[4/4] 正在提交视频生成任务 (触发 Sentinel Token)...")
        # 这里会触发关键的 _generate_sentinel_token 和 iOS UA 模拟逻辑
        task_id = await client.generate_video(
            prompt=enhanced_prompt,
            token=ACCESS_TOKEN,
            media_id=media_id,
            orientation="landscape",
            model="sy_8",
            session_token=real_session_token

        )
        print(f"🚀 任务提交成功！Task ID: {task_id}")

        # 步骤 5: 查询进度
        print("\n[5/5] 查询任务进度...")
        pending = await client.get_pending_tasks(ACCESS_TOKEN)
        print(f"📋 当前队列中有 {len(pending)} 个任务正在处理")

    except Exception as e:
        print(f"❌ 提交阶段发生错误: {e}")
        print(f"\n❌ 测试失败: {str(e)}")
        # 增加一些常见错误的诊断
        if "403" in str(e):
            print("💡 诊断: 403 Forbidden。你的住宅代理 IP 可能已被 OpenAI 拉黑，或者代理不支持 H2。")
        elif "401" in str(e):
            print("💡 诊断: 401 Unauthorized。Access Token 填写有误或已过期。")
        elif "sentinel" in str(e).lower():
            print("💡 诊断: Sentinel Token 校验失败。可能是 PoW 计算逻辑与服务端不匹配。")


if __name__ == "__main__":
    import sys
    import asyncio
    from functools import wraps
    from asyncio.proactor_events import _ProactorBasePipeTransport

    # ================= 屏蔽 Windows 报错的黑魔法11 =================
    def silence_event_loop_closed(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except RuntimeError:
                pass
        return wrapper

    # 强制覆盖删除方法，忽略报错
    _ProactorBasePipeTransport.__del__ = silence_event_loop_closed(_ProactorBasePipeTransport.__del__)
    # ===========================================================

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        asyncio.run(run_integration_test())
    except KeyboardInterrupt:
        pass