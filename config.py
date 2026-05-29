"""
IPTV 自建直播源 - 配置文件
修改此文件来自定义数据源、频道过滤和排序规则
"""

# ===== 订阅源列表 =====
# 格式：{ "name": "源名称", "url": "m3u地址", "priority": 优先级(1最高) }
SOURCE_URLS = [
    # 优先级1 - 大陆优化、更新最勤
    {"name": "YanG-1989",      "url": "https://tv.iill.top/m3u/Gather",                    "priority": 1},
    {"name": "fanmingming",    "url": "https://live.fanmingming.com/tv/m3u/ipv6.m3u",      "priority": 1},
    {"name": "Kimentanm",      "url": "https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u", "priority": 1},

    # 优先级2 - 港台专用
    {"name": "sammy0101-hk",   "url": "https://raw.githubusercontent.com/sammy0101/hk-iptv-auto/refs/heads/main/hk_live.m3u", "priority": 2},
    {"name": "xJEYDAin-hk",    "url": "https://raw.githubusercontent.com/xJEYDAin/iptv-scraper/master/output/hk_merged.m3u", "priority": 2},

    # 优先级3 - 综合源
    {"name": "Guovin-ipv4",    "url": "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u", "priority": 3},
    {"name": "YueChan",        "url": "https://raw.githubusercontent.com/YueChan/Live/refs/heads/main/IPTV.m3u", "priority": 3},
    {"name": "joevess",        "url": "https://raw.githubusercontent.com/joevess/IPTV/main/m3u/iptv.m3u", "priority": 3},
    {"name": "BurningC4",      "url": "https://raw.githubusercontent.com/BurningC4/Chinese-IPTV/master/TV-IPV4.m3u", "priority": 3},
    {"name": "suxuang-ipv4",   "url": "https://raw.githubusercontent.com/suxuang/myIPTV/refs/heads/main/ipv4.m3u", "priority": 3},
    {"name": "iptv-org-tw",    "url": "https://iptv-org.github.io/iptv/countries/tw.m3u",  "priority": 3},
    {"name": "iptv-org-hk",    "url": "https://iptv-org.github.io/iptv/countries/hk.m3u",  "priority": 3},
    {"name": "vbskycn-ipv4",   "url": "https://live.zbds.org/tv/iptv4.m3u",                "priority": 3},
]

# ===== 港台频道白名单关键词 =====
# 频道名包含以下任一关键词则保留
HK_TW_KEYWORDS = [
    # 香港 TVB 系列
    "翡翠", "Jade", "明珠", "Pearl", "无线新闻", "TVB新聞", "無綫新聞", "News",
    "J2", "财经体育", "財經體育",

    # 香港 ViuTV
    "ViuTV", "Viu",

    # 香港 HOY TV / 奇妙电视
    "HOY", "奇妙",

    # 香港 RTHK 港台电视
    "港台电视", "港台電視", "RTHK",

    # 香港 Now TV
    "Now", "now",

    # 香港 凤凰卫视
    "凤凰", "鳳凰", "Phoenix",

    # 香港 其他
    "耀才", "HK", "香港",

    # 台湾 无线/有线
    "台视", "TTV",
    "中视", "CTV",
    "华视", "華視", "CTS",
    "民视", "民視", "FTV",
    "公视", "公視", "PTS",

    # 台湾 新闻台
    "中天", "CTi",
    "东森", "東森", "EBC",
    "三立", "SET",
    "TVBS",
    "年代", "ERA",
    "壹电视", "壹電視",

    # 台湾 综合/娱乐
    "八大", "GTV",
    "纬来", "緯來",
    "卫视中文", "衛視中文",
    "龙华", "龍華",

    # 台湾 其他
    "大爱", "大愛", "DaAi",
    "原住民", "Indigenous",
    "GOOD TV",
    "台湾", "Taiwan",
]

# ===== 频道排序规则 =====
# 排前面的关键词优先级高
ORDER_KEYWORDS = [
    "翡翠", "Jade",
    "明珠", "Pearl",
    "无线新闻", "無綫新聞",
    "凤凰中文", "鳳凰中文",
    "凤凰资讯", "鳳凰資訊",
    "HOY",
    "ViuTV",
    "RTHK", "港台电视",
    "Now",
    "台视", "TTV",
    "中视", "CTV",
    "华视", "華視",
    "民视", "民視",
    "TVBS",
    "中天",
    "东森", "東森",
    "三立",
    "八大",
    "纬来", "緯來",
]

# ===== 测速配置 =====
SPEED_TEST_TIMEOUT = 8      # 单个频道测速超时(秒)
SPEED_TEST_LIMIT = 3        # 每个频道最多保留几个可用源
MAX_WORKERS = 10            # 并发测速线程数

# ===== 输出配置 =====
OUTPUT_DIR = "output"
HK_TW_OUTPUT = "output/hk_tw.m3u"
MOVIE_OUTPUT = "output/movies.m3u"
ALL_OUTPUT = "output/all.m3u"

# ===== EPG 节目单 =====
EPG_URL = "https://epg.112114.xyz/pp.xml"

# ===== 电影频道白名单关键词 =====
MOVIE_KEYWORDS = [
    # 天映
    "天映", "Celestial",

    # 美亚
    "美亚",

    # CHC 系列
    "CHC",

    # 龙华系列
    "龙华电影", "龍華电影", "龙华洋片", "龍華洋片",
    "龙华经典", "龍華經典", "龙华戏剧", "龍華戲劇",
    "龙华偶像", "龍華偶像", "龙华日韩", "龍華日韓",
    "龙华卡通", "龍華卡通",

    # 香港电影
    "靖天",

    # 台湾电影
    "东森电影", "東森電影",
    "纬来电影", "緯來電影",

    # 凤凰电影 / 星空
    "凤凰电影", "星空",

    # 大陆电影
    "CCTV-6", "1905", "峨眉电影", "西部电影",
    "湖南电影", "淘电影",

    # 专题电影
    "刘德华", "周星驰", "成龙", "漫威",
    "韩国电影", "功夫电影", "战争电影", "动作电影",

    # 好莱坞
    "HBO", "CINEMAX", "FOX Movies", "好莱坞", "Movie",

    # Disney / 动画
    "Disney", "Cartoon", "动画", "卡通",
]

# ===== 电影频道排序 =====
MOVIE_ORDER_KEYWORDS = [
    "天映", "Celestial",
    "HBO",
    "美亚",
    "CHC",
    "龙华电影", "龙华洋片",
    "东森电影", "纬来电影",
    "凤凰电影", "星空",
    "靖天",
    "CCTV-6", "1905",
    "Disney", "Cartoon",
]

# ===== VPS 代理配置 =====
# 部署到 VPS 后，流地址会替换为 http://VPS_IP:8888/proxy?url=原始地址
# 如果不用 VPS 代理（本地/GitHub Pages 模式），设 PROXY_ENABLED = False
PROXY_ENABLED = False
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8888

# ===== GitHub Raw 前缀 =====
# 部署后请修改为你的用户名
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/layermouth/iptv-self/main"
