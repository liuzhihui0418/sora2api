import random


def generate_ua_list(count=1000):
    ios_versions = [
        ("17_4", "17.4"), ("17_5", "17.5"), ("17_6", "17.6"),
        ("17_7", "17.7"), ("18_0", "18.0"), ("18_1", "18.1"),
        ("16_6", "16.6"), ("17_5_1", "17.5.1")
    ]
    devices = ["iPhone", "iPad"]

    ua_list = []
    for i in range(count):
        ver = random.choice(ios_versions)
        dev = random.choice(devices)
        # 随机微调 Webkit 版本号，让 1000 个 UA 各不相同
        webkit = f"605.1.{random.randint(10, 20)}"

        ua = f"Mozilla/5.0 ({dev}; CPU {dev} OS {ver[0]} like Mac OS X) AppleWebKit/{webkit} (KHTML, like Gecko) Version/{ver[1]} Mobile/15E148 Safari/604.1"
        ua_list.append(ua)
    return ua_list


# 打印出前 500 个供复制
for ua in generate_ua_list(500):
    print(ua)