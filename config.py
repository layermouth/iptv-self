"""
IPTV 自建直播源 - 配置文件
"""
# 订阅源列表
SOURCE_URLS = [
    {"name": "YanG-1989",      "url": "https://tv.iill.top/m3u/Gather",                    "priority": 1},
    {"name": "fanmingming",    "url": "https://live.fanmingming.com/tv/m3u/ipv6.m3u",      "priority": 1},
    {"name": "Kimentanm",      "url": "https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u", "priority": 1},
    {"name": "yanghan-iptv",   "url": "https://raw.githubusercontent.com/yanghanhanyingshi/iptv/master/live.txt", "priority": 1, "format": "txt"},
    {"name": "yanghan-result", "url": "https://raw.githubusercontent.com/yanghanhanyingshi/iptv/master/result.txt", "priority": 1, "format": "txt"},
    {"name": "sammy0101-hk",   "url": "https://raw.githubusercontent.com/sammy0101/hk-iptv-auto/main/hk_live.m3u", "priority": 2},
    {"name": "xJEYDAin-hk",    "url": "https://raw.githubusercontent.com/xJEYDAin/iptv-scraper/master/output/hk_merged.m3u", "priority": 2},
    {"name": "Guovin-ipv4",    "url": "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u", "priority": 3},
    {"name": "YueChan",        "url": "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u", "priority": 3},
    {"name": "joevess",        "url": "https://raw.githubusercontent.com/joevess/IPTV/main/m3u/iptv.m3u", "priority": 3},
    {"name": "BurningC4",      "url": "https://raw.githubusercontent.com/BurningC4/Chinese-IPTV/master/TV-IPV4.m3u", "priority": 3},
    {"name": "suxuang-ipv4",   "url": "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u", "priority": 3},
    {"name": "iptv-org-tw",    "url": "https://iptv-org.github.io/iptv/countries/tw.m3u",  "priority": 3},
    {"name": "iptv-org-hk",    "url": "https://iptv-org.github.io/iptv/countries/hk.m3u",  "priority": 3},
    {"name": "vbskycn-ipv4",   "url": "https://live.zbds.org/tv/iptv4.m3u",                "priority": 3},
    {"name": "YueChan-GNTV",   "url": "https://raw.githubusercontent.com/YueChan/Live/main/GNTV.m3u", "priority": 3},
]

HK_TW_KEYWORDS = ["翡翠","Jade","明珠","Pearl","无线新闻","TVB新聞","無綫新聞",
    "J2","财经体育","財經體育","ViuTV","Viu","HOY","奇妙",
    "港台电视","港台電視","RTHK","Now","now","凤凰","鳳凰","Phoenix",
    "耀才","HK","香港","台视","TTV","中视","CTV","华视","華視","CTS",
    "民视","民視","FTV","公视","公視","PTS","中天","CTi","东森","東森","EBC",
    "三立","SET","TVBS","年代","ERA","壹电视","壹電視","八大","GTV",
    "纬来","緯來","卫视中文","衛視中文","龙华","龍華","大爱","大愛","DaAi",
    "原住民","Indigenous","GOOD TV","台湾","Taiwan","华丽","Jade"]

ORDER_KEYWORDS = ["翡翠","Jade","明珠","Pearl","无线新闻","無綫新聞",
    "凤凰中文","鳳凰中文","凤凰资讯","鳳凰資訊","HOY","ViuTV","RTHK",
    "港台电视","Now","台视","TTV","中视","CTV","华视","華視",
    "民视","民視","TVBS","中天","东森","東森","三立","八大","纬来","緯來"]

SPEED_TEST_TIMEOUT = 8
SPEED_TEST_LIMIT = 3
MAX_WORKERS = 15
OUTPUT_DIR = "output"
HK_TW_OUTPUT = "output/hk_tw.m3u"
MOVIE_OUTPUT = "output/movies.m3u"
ALL_OUTPUT = "output/all.m3u"
EPG_URL = "https://epg.112114.xyz/pp.xml"

MOVIE_KEYWORDS = ["天映","Celestial","美亚","CHC",
    "龙华电影","龍華电影","龙华洋片","龍華洋片","龙华经典","龍華經典",
    "龙华戏剧","龍華戲劇","龙华偶像","龍華偶像","龙华日韩","龍華日韓",
    "龙华卡通","龍華卡通","靖天","东森电影","東森電影","纬来电影","緯來電影",
    "凤凰电影","星空","CCTV-6","1905","峨眉电影","西部电影","湖南电影","淘电影",
    "刘德华","周星驰","成龙","漫威","韩国电影","功夫电影","战争电影","动作电影",
    "HBO","CINEMAX","FOX Movies","好莱坞","Movie","Disney","Cartoon","动画","卡通"]

MOVIE_ORDER_KEYWORDS = ["天映","Celestial","HBO","美亚","CHC",
    "龙华电影","龙华洋片","东森电影","纬来电影","凤凰电影","星空","靖天",
    "CCTV-6","1905","Disney","Cartoon"]

PROXY_ENABLED = False
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8888
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/layermouth/iptv-self/main"

# 虎牙/斗鱼 配置
HUYA_ROOMS = [{"id":"660000","name":"虎牙电影1"},{"id":"159999","name":"虎牙电影2"},
    {"id":"117055","name":"虎牙电影3"},{"id":"880168","name":"虎牙电影4"},
    {"id":"393141","name":"虎牙电影5"},{"id":"646666","name":"虎牙电影6"},
    {"id":"521521","name":"虎牙电影7"},{"id":"138855","name":"虎牙电影8"}]

DOUYU_ROOMS = [{"id":"4729165","name":"斗鱼电影1"},{"id":"673005","name":"斗鱼电影2"},
    {"id":"6897319","name":"斗鱼电影3"},{"id":"8464717","name":"斗鱼电影4"},
    {"id":"222721","name":"斗鱼电影5"},{"id":"288061","name":"斗鱼电影6"},
    {"id":"696034","name":"斗鱼电影7"}]

AUTO_DISCOVER_ENABLED = True
