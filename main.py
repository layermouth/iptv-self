#!/usr/bin/env python3
"""
IPTV 自建直播源 - 核心爬虫脚本
功能：多源聚合 → 频道过滤 → 并发测速 → 去重排序 → 生成 m3u

用法：
    python main.py              # 完整流程（含测速）
    python main.py --skip-test  # 跳过测速（快速模式）
"""

import re
import os
import sys
import time
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

import requests
from config import *

# ===== 日志 =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# 北京时间
TZ_BEIJING = timezone(timedelta(hours=8))


# ===== M3U 解析 =====
def parse_m3u(content: str) -> list[dict]:
    """解析 m3u 内容，返回频道列表 [{name, url, logo, group, ...}]"""
    channels = []
    lines = content.split("\n")
    current = {}
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF:"):
            current = {}
            # 提取属性
            for key in ["tvg-name", "tvg-logo", "group-title", "tvg-id"]:
                m = re.search(rf'{key}="([^"]*)"', line)
                if m:
                    current[key] = m.group(1)
            # 提取频道名（逗号后部分）
            if "," in line:
                current["name"] = line.rsplit(",", 1)[-1].strip()
            else:
                current["name"] = ""
        elif line and not line.startswith("#") and current:
            current["url"] = line
            if current.get("name"):
                channels.append(current.copy())
            current = {}
    return channels


def normalize_name(name: str) -> str:
    """频道名标准化：去空格、去括号备注、统一繁简"""
    name = name.strip()
    # 去掉括号及内容（如 "(576p)"、"[Geo-blocked]"）
    name = re.sub(r"\s*[\(\[（].*?[\)\]）]\s*", "", name)
    name = re.sub(r"\s+\d+p$", "", name)
    name = re.sub(r"\s+(HD|FHD|SD|UHD|4K|8K)$", "", name)
    return name.strip()


def parse_txt(content):
    """解析 TXT 格式"""
    chs = []
    for line in content.split(chr(10)):
        line = line.strip()
        if not line or "#genre#" in line:
            continue
        parts = line.split(",", 1)
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        url = parts[1].strip().split("$")[0].strip()
        if name and url.startswith("http"):
            chs.append({"name": name, "url": url})
    return chs


def match_kw(name, kws):
    nl = name.lower()
    for kw in kws:
        if kw.lower() in nl:
            return True
    return False


def sort_key(name, mv=False):
    kws = MOVIE_ORDER_KEYWORDS if mv else ORDER_KEYWORDS
    for i, kw in enumerate(kws):
        if kw.lower() in name.lower():
            return i
    return len(kws)


def norm_name(name):
    name = name.strip()
    name = re.sub(r"\s*[\(\[（].*?[\)\]）]\s*", "", name)
    name = re.sub(r"\s+\d+p$", "", name)
    name = re.sub(r"\s+(HD|FHD|SD|UHD|4K|8K)$", "", name)
    return name.strip()


def ch_key(ch):
    return hashlib.md5(norm_name(ch.get("name", "")).lower().encode()).hexdigest()


def ukey(url):
    return hashlib.md5(url.encode()).hexdigest()


# ===== 网络请求 =====
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})
session.timeout = 30


def fetch_source(source: dict) -> list[dict]:
    """抓取单个数据源（支持 m3u 和 txt 格式）"""
    try:
        fmt = source.get("format", "m3u")
        resp = session.get(source["url"], timeout=30)
        resp.raise_for_status()
        text = resp.text
        if fmt == "txt":
            channels = parse_txt(text)
        else:
            channels = parse_m3u(text)
        log.info(f"  {source['name']}: {len(channels)} ch ({fmt})")
        for ch in channels:
            ch["_source"] = source["name"]
            ch["_priority"] = source["priority"]
        return channels
    except Exception as e:
        log.warning(f"  X {source['name']}: {e}")
        return []


def test_url(url):
    """严格测速 - 使用curl子进程,永不挂死"""
    import subprocess as _sub
    try:
        t0 = time.time()
        r = _sub.run(
            ['curl', '-s', '-o', os.devnull, '-w', '%{http_code}|%{size_download}|%{content_type}',
             '--connect-timeout', '4', '--max-time', str(SPEED_TEST_TIMEOUT - 1),
             '-L', '-k', '--user-agent', 'Mozilla/5.0',
             url],
            capture_output=True, text=True, timeout=SPEED_TEST_TIMEOUT
        )
        parts = r.stdout.strip().split('|')
        code = parts[0] if parts else '000'
        size = abs(int(parts[1])) if len(parts) > 1 and parts[1].lstrip('-').isdigit() else 0
        ct = (parts[2] if len(parts) > 2 else '').lower()
        if code not in ('200', '302', '301', '206', '304'): return False, 0
        if 'text/html' in ct and size < 1000: return False, 0
        if 'application/json' in ct: return False, 0
        if size < 100: return False, 0
        if 'm3u8' in url or 'mpegurl' in ct:
            return True, time.time() - t0
        if size < 2048: return False, 0
        return True, time.time() - t0
    except _sub.TimeoutExpired:
        return False, 0
    except:
        return False, 0


def huya_stream(rid):
    """提取虎牙直播流"""
    try:
        r = session.get("https://m.huya.com/" + str(rid),
            headers={"User-Agent":"Mozilla/5.0 (Linux; Android 10)"}, timeout=10)
        if r.status_code != 200: return None
        m = re.search(r'"liveLineUrl":"([^"]+)"', r.text)
        if not m: return None
        try: return base64.b64decode(m.group(1)).decode()
        except:
            u = m.group(1)
            return u if u.startswith("http") else None
    except: return None


def douyu_stream(rid):
    """提取斗鱼直播流"""
    try:
        r = session.get("https://m.douyu.com/" + str(rid), timeout=10)
        if r.status_code != 200: return None
        m = re.search(r'rid":(\d{1,8})', r.text)
        if not m: return None
        rid2 = m.group(1)
        t13 = str(int(time.time()*1000))
        auth = hashlib.md5((rid2+t13).encode()).hexdigest()
        r2 = session.post("https://playweb.douyucdn.cn/lapi/live/hlsH5Preview/" + rid2,
            headers={"rid":rid2,"time":t13,"auth":auth},
            data={"rid":rid2,"did":"10000000000000000000000000001501"}, timeout=10)
        if r2.status_code != 200: return None
        d = r2.json()
        if d.get("error") != 0: return None
        dd = d.get("data",{})
        ru = dd.get("rtmp_url",""); rl = dd.get("rtmp_live","")
        return ru + "/" + rl if ru and rl else None
    except: return None


# ===== 主流程 =====

def collect_live():
    """收集虎牙/斗鱼直播流"""
    chs = []
    for rm in HUYA_ROOMS:
        u = huya_stream(rm["id"])
        if u:
            chs.append({"name":rm["name"],"url":u,"_src":"Huya","_pri":1})
        log.info("  Huya %s: %s" % (rm["name"], "OK" if u else "offline"))
    for rm in DOUYU_ROOMS:
        u = douyu_stream(rm["id"])
        if u:
            chs.append({"name":rm["name"],"url":u,"_src":"Douyu","_pri":1})
        log.info("  Douyu %s: %s" % (rm["name"], "OK" if u else "offline"))
    return chs

def main():
    skip = "--skip-test" in sys.argv
    log.info("=" * 60)
    log.info("IPTV 自建直播源 - 开始更新 (%d 个源)" % len(SOURCE_URLS))
    log.info("跳过测速: %s" % skip)
    log.info("=" * 60)

    # ----- 1. 聚合所有源 -----
    log.info("[1/4] 抓取数据源...")
    all_channels = []
    for src in SOURCE_URLS:
        channels = fetch_source(src)
        all_channels.extend(channels)
    log.info("收集虎牙/斗鱼直播流...")
    all_channels.extend(collect_live())
    log.info("总计: %d 条" % len(all_channels))

    # ----- 2. 去重合并 (保留多线路) -----
    log.info("[2/4] 去重合并...")
    merged = OrderedDict()
    for ch in all_channels:
        key = ch_key(ch)
        if key not in merged:
            merged[key] = []
        eurls = {ukey(x.get("url","")) for x in merged[key]}
        if ukey(ch.get("url","")) not in eurls:
            merged[key].append(ch)
    for k in merged:
        merged[k].sort(key=lambda x: x.get("_priority",99))
    total_urls = sum(len(v) for v in merged.values())
    log.info("去重后: %d 频道, %d 线路" % (len(merged), total_urls))

    # ----- 3. 测速 -----
    if not skip:
        log.info("[3/4] 严格测速...")
        okd = OrderedDict()
        total = len(merged)
        done = 0
        for k, cl in merged.items():
            alive = []
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                futs = {ex.submit(test_url, c["url"]): c for c in cl[:SPEED_TEST_LIMIT]}
                for f in list(futs.keys()):
                    try:
                        ok, sp = f.result(timeout=SPEED_TEST_TIMEOUT + 3)
                        if ok:
                            futs[f]["speed"] = sp
                            alive.append(futs[f])
                    except:
                        pass
            alive.sort(key=lambda x: x.get("speed", 999))
            if alive:
                okd[k] = alive[:SPEED_TEST_LIMIT]
            done += 1
            if done % 50 == 0 or done == total:
                alive_total = sum(len(v) for v in okd.values())
                log.info("  测速进度: %d/%d (存活 %d 频道)" % (done, total, alive_total))
        merged = okd
        ta = sum(len(v) for v in merged.values())
        log.info("测速完成: %d 频道, %d 线路" % (len(merged), ta))
    else:
        dd = OrderedDict()
        for k, cl in merged.items():
            if cl:
                dd[k] = [cl[0]]
        merged = dd
        log.info("跳过测速: %d 频道" % len(merged))

    # ----- 4. 分类 -----
    log.info("[4/4] 分类生成 m3u...")
    hk = OrderedDict()
    mv = OrderedDict()
    ot = OrderedDict()
    HK_TW_BLACKLIST = ["CCTV","CGTN","福建","漳州","泉州","厦门","福州","龙岩",
        "三明","南平","宁德","莆田","广东","深圳","广州","东莞","佛山",
        "珠海","中山","惠州","汕头","江门","湛江","茂名","肇庆","清远",
        "揭阳","梅州","潮州","河源","汕尾","阳江","韶关","云浮","广西",
        "南宁","柳州","桂林","玉林","贵港","北海","钦州","防城港","梧州",
        "贺州","百色","河池","来宾","崇左","云南","昆明","曲靖","贵州",
        "贵阳","遵义","安顺","六盘水","铜仁","毕节","四川","成都","绵阳",
        "湖北","武汉","宜昌","襄阳","荆州","黄石","十堰","黄冈","孝感",
        "荆门","鄂州","随州","咸宁","恩施","仙桃","天门","潜江","神农架",
        "湖南","长沙","株洲","湘潭","衡阳","邵阳","岳阳","常德","张家界",
        "益阳","郴州","永州","怀化","娄底","湘西","河南","郑州","开封",
        "洛阳","平顶山","安阳","鹤壁","新乡","焦作","濮阳","许昌","漯河",
        "三门峡","南阳","商丘","信阳","周口","驻马店","济源","河北","石家庄",
        "唐山","秦皇岛","邯郸","邢台","保定","张家口","承德","沧州","廊坊",
        "衡水","山东","济南","青岛","淄博","枣庄","东营","烟台","潍坊",
        "济宁","泰安","威海","日照","临沂","德州","聊城","滨州","菏泽",
        "山西","太原","大同","阳泉","长治","晋城","朔州","晋中","运城",
        "忻州","临汾","吕梁","陕西","西安","铜川","宝鸡","咸阳","渭南",
        "延安","汉中","榆林","安康","商洛","辽宁","沈阳","大连","鞍山",
        "抚顺","本溪","丹东","锦州","营口","阜新","辽阳","盘锦","铁岭",
        "朝阳","葫芦岛","吉林","长春","四平","辽源","通化","白山","松原",
        "白城","延边","黑龙江","哈尔滨","齐齐哈尔","牡丹江","佳木斯","大庆",
        "鸡西","双鸭山","伊春","七台河","鹤岗","黑河","绥化","大兴安岭",
        "内蒙古","呼和浩特","赤峰","通辽","鄂尔多斯","呼伦贝尔","巴彦淖尔",
        "乌兰察布","兴安","锡林郭勒","阿拉善","宁夏","银川","石嘴山","吴忠",
        "固原","中卫","甘肃","兰州","嘉峪关","金昌","白银","天水","武威",
        "张掖","平凉","酒泉","庆阳","定西","陇南","临夏","甘南","青海",
        "西宁","海东","海北","黄南","果洛","玉树","海西","西藏","拉萨",
        "日喀则","昌都","林芝","山南","那曲","阿里","新疆","乌鲁木齐",
        "克拉玛依","吐鲁番","哈密","阿克苏","喀什","和田","塔城","阿勒泰",
        "博州","昌吉","克州","伊犁","巴州","浙江","嘉兴","湖州","绍兴",
        "金华","衢州","舟山","台州","丽水","义乌","宁波","温州","杭州",
        "萧山","余杭","富阳","临安","桐庐","淳安","建德","钱江","西湖",
        "江苏","南京","无锡","徐州","常州","苏州","南通","连云港","淮安",
        "盐城","扬州","镇江","泰州","宿迁","安徽","合肥","芜湖","蚌埠",
        "淮南","马鞍山","淮北","铜陵","安庆","黄山","滁州","阜阳","宿州",
        "六安","亳州","池州","宣城","江西","南昌","景德镇","萍乡","九江",
        "新余","鹰潭","赣州","吉安","宜春","抚州","上饶","海南","海口",
        "三亚","三沙","儋州","五指山","文昌","琼海","万宁","东方","定安",
        "屯昌","澄迈","临高","白沙","昌江","乐东","陵水","保亭","琼中",
        "上海","北京","天津","重庆","CETV","中国教育","CHC","Discovery",
        "Anthony Bourdain","Parts Unknown","MTV","NBC News","Fox Live","AXS TV"]
    
    def _is_hk_tw(nm):
        if not match_kw(nm, HK_TW_KEYWORDS):
            return False
        # Whitelist: certain HK/TW channels that might match blacklist
        for wl in ["卫视中文台","卫视卡式台","卫视国际电影","卫视电影台",
            "卫视体育台","卫视西片台","卫视合家欢","卫视音乐台","卫视电影",
            "凤凰卫视","香港卫视","台湾卫视","澳门卫视","澳门莲花",
            "莲花卫视","澳亚卫视","大爱一台","大爱二台"]:
            if wl in nm:
                return True
        for bl in HK_TW_BLACKLIST:
            if bl.lower() in nm.lower():
                return False
        return True
    
    for k, cl in merged.items():
        nm = norm_name(cl[0].get("name", ""))
        hm = _is_hk_tw(nm)
        mm = match_kw(nm, MOVIE_KEYWORDS)
        if hm:
            hk[k] = cl
        if mm:
            mv[k] = cl
        if not hm and not mm:
            ot[k] = cl
    log.info("港台: %d, 电影: %d, 其他: %d" % (len(hk), len(mv), len(ot)))
    def gen_m3u(cd, op, title):
        lns = ["#EXTM3U"]
        is_mv = "Movie" in title
        sk = sorted(cd.keys(), key=lambda k: sort_key(cd[k][0].get("name",""), is_mv))
        tc = 0; tl = 0
        for k in sk:
            nm = cd[k][0].get("name","?")
            tc += 1
            for c in cd[k]:
                lns.append('#EXTINF:-1 tvg-name="%s" group-title="%s",%s' % (nm, title, nm))
                lns.append(c["url"]); tl += 1
        c = chr(10).join(lns)
        os.makedirs(os.path.dirname(op), exist_ok=True)
        with open(op, "w", encoding="utf-8") as f: f.write(c)
        log.info("  %s: %d ch, %d lines" % (op, tc, tl))

    gen_m3u(merged, ALL_OUTPUT, "All")
    gen_m3u(hk, HK_TW_OUTPUT, "HK_TW")
    gen_m3u(mv, MOVIE_OUTPUT, "Movies")
if __name__ == "__main__":
    main()
