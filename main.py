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
import base64
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
    """严格测速 - 智能识别 HLS 和直连流"""
    try:
        t0 = time.time()
        r = session.get(url, stream=True, timeout=SPEED_TEST_TIMEOUT)
        if r.status_code != 200:
            r.close(); return False, 0
        ct = r.headers.get("Content-Type", "")
        # 拒绝错误页面
        if "text/html" in ct or "application/json" in ct:
            r.close(); return False, 0
        # 判断是否 HLS 流 (m3u8)
        is_hls = "m3u8" in ct or "m3u8" in url.lower() or "hls" in url.lower()
        c = b""
        for x in r.iter_content(4096):
            c += x
            if len(c) >= 16384: break
        r.close()
        if not c or len(c) < 64: return False, 0
        # HLS 流: 验证播放列表有效性
        if is_hls:
            try:
                text = c.decode('utf-8', errors='ignore')
                if text.startswith('#EXTM3U') and ('#EXTINF' in text or '#EXT-X-STREAM-INF' in text):
                    return True, time.time() - t0
                # 有些虎牙流返回的 m3u8 没有标准头部但包含 TS 引用
                if '.ts' in text or 'm3u8' in text.lower():
                    return True, time.time() - t0
                return False, 0
            except: return False, 0
        # 直连流: 验证包含二进制视频数据
        if len(c) < 512: return False, 0
        # 检查是否 HTML 错误页 (即使 Content-Type 正确也可能返回 HTML)
        if c[:64].strip().startswith(b'<!') or c[:64].strip().startswith(b'<html'):
            return False, 0
        np = sum(1 for b in c if b < 32 and b not in (9,10,13))
        # 放宽二进制比例要求(考虑视频流可能以文本头开始)
        if np < max(len(c) * 0.03, 15): return False, 0
        return True, time.time() - t0
    except: return False, 0


def huya_stream(rid):
    """提取虎牙直播流"""
    try:
        r = session.get("https://m.huya.com/" + str(rid),
            headers={"User-Agent":"Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"}, timeout=10)
        if r.status_code != 200: return None
        text = r.text
        # Method 1: liveLineUrl (base64 encoded)
        m = re.search(r'"liveLineUrl":"([^"]+)"', text)
        if m:
            try: url = base64.b64decode(m.group(1)).decode()
            except:
                url = m.group(1)
            if url.startswith("http"):
                return url
            if url.startswith("//"):
                return "https:" + url
        # Method 2: direct m3u8 field
        m = re.search(r'"m3u8":"([^"]+)"', text)
        if m:
            url = m.group(1).replace('\\u002F', '/')
            if url.startswith("//"): url = "https:" + url
            if "m3u8" in url: return url
        # Method 3: stream base64
        m = re.search(r'"stream":\s*"([^"]*)"', text)
        if m:
            try: url = base64.b64decode(m.group(1)).decode()
            except: url = m.group(1)
            if url.startswith("//"): url = "https:" + url
            if "huya" in url.lower(): return url
        return None
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
    """并发收集虎牙/斗鱼直播流"""
    chs = []
    HUYA_TIMEOUT = 12  # 比 session timeout 稍长
    # 并发提取虎牙流
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {}
        for rm in HUYA_ROOMS:
            futures[ex.submit(huya_stream, rm["id"])] = rm
        for f in as_completed(futures):
            rm = futures[f]
            try:
                u = f.result(timeout=HUYA_TIMEOUT)
                if u:
                    chs.append({"name":rm["name"],"url":u,"_source":"Huya","_priority":1})
            except: pass
    # 并发提取斗鱼流
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {}
        for rm in DOUYU_ROOMS:
            futures[ex.submit(douyu_stream, rm["id"])] = rm
        for f in as_completed(futures):
            rm = futures[f]
            try:
                u = f.result(timeout=HUYA_TIMEOUT)
                if u:
                    chs.append({"name":rm["name"],"url":u,"_source":"Douyu","_priority":1})
            except: pass
    log.info("虎牙/斗鱼: %d 个在线" % len(chs))
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

    # ----- 2. 去重合并 + 过滤地方台 -----
    log.info("[2/4] 去重合并 + 过滤地方台...")
    # 地方频道黑名单关键词
    LOCAL_BLACKLIST = [
        "县台","区台","市台","乡镇","街道","村",
        "文旅","旅游","风光","景点",
        "党建","政务","政法","纪委","普法",
        "教科","教育","教学","课堂","校园",
        "卫生健康","医院","医疗","疾控",
        "气象","天气","环境监测",
    ]
    def is_local(name):
        nl = name.lower()
        # 跳过央视/卫视/港台/电影
        if match_kw(name, HK_TW_KEYWORDS): return False
        if match_kw(name, MOVIE_KEYWORDS): return False
        # 央视和卫视关键词
        if any(k in name for k in ["CCTV","央视","卫视","凤凰","星空","好莱坞","HBO","Disney","Cartoon"]):
            return False
        # 检查地方台关键词
        for kw in LOCAL_BLACKLIST:
            if kw in name:
                return True
        # XX综合/XX都市/XX新闻等(长度<6且含地方特征)
        if len(name) <= 8:
            local_suffixes = ["综合","都市","公共","新闻","生活","经济","影视","教育","农业","少儿","文体"]
            for sfx in local_suffixes:
                if name.endswith(sfx) and "卫视" not in name and "CCTV" not in name:
                    return True
        return False

    merged = OrderedDict()
    local_count = 0
    for ch in all_channels:
        name = ch.get("name","")
        if name and is_local(name):
            local_count += 1
            continue
        key = ch_key(ch)
        if key not in merged:
            merged[key] = []
        eurls = {ukey(x.get("url","")) for x in merged[key]}
        if ukey(ch.get("url","")) not in eurls:
            merged[key].append(ch)
    log.info("过滤地方台: %d 条" % local_count)
    for k in merged:
        merged[k].sort(key=lambda x: x.get("_priority",99))
    total_urls = sum(len(v) for v in merged.values())
    log.info("去重后: %d 频道, %d 线路" % (len(merged), total_urls))

    # ----- 3. 测速 -----
    if not skip:
        log.info("[3/4] 严格测速 (%d 频道, %d 候选线路)..." % (len(merged), total_urls))
        okd = OrderedDict()

        # 展开所有候选 URL (每频道最多 SPEED_TEST_LIMIT 条)
        all_tasks = []  # [(channel_key, url, channel_obj)]
        for k, cl in merged.items():
            for c in cl[:SPEED_TEST_LIMIT]:
                all_tasks.append((k, c["url"], c))

        log.info("  共 %d 条 URL 待测..." % len(all_tasks))
        results = {}  # key -> [passed_channels]
        tested = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {}
            for task in all_tasks:
                k, url, ch = task
                futures[ex.submit(test_url, url)] = (k, ch)

            for f in as_completed(futures):
                k, ch = futures[f]
                tested += 1
                try:
                    ok, sp = f.result(timeout=SPEED_TEST_TIMEOUT + 2)
                    if ok:
                        ch["speed"] = sp
                        if k not in results:
                            results[k] = []
                        results[k].append(ch)
                except Exception:
                    pass

                if tested % 500 == 0:
                    log.info("  测速: %d/%d (存活 %d 频道)" % (tested, len(all_tasks), len(results)))

        # 排序并限制每频道线路数
        for k in results:
            results[k].sort(key=lambda x: x.get("speed", 999))
            okd[k] = results[k][:SPEED_TEST_LIMIT]

        merged = okd
        ta = sum(len(v) for v in merged.values())
        log.info("测速完成: %d 频道, %d 线路 (淘汰 %d)" % (len(merged), ta, len(all_tasks) - ta))
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
    for k, cl in merged.items():
        nm = norm_name(cl[0].get("name", ""))
        hm = match_kw(nm, HK_TW_KEYWORDS)
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
