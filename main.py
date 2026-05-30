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
    """严格测速"""
    try:
        t0 = time.time()
        r = session.get(url, stream=True, timeout=SPEED_TEST_TIMEOUT)
        if r.status_code != 200:
            r.close(); return False, 0
        ct = r.headers.get("Content-Type", "")
        if "text/html" in ct or "application/json" in ct or "text/plain" in ct:
            r.close(); return False, 0
        c = b""
        for x in r.iter_content(4096):
            c += x
            if len(c) >= 8192: break
        r.close()
        if not c or len(c) < 512: return False, 0
        np = sum(1 for b in c if b < 32 and b not in (9,10,13))
        if np < len(c) * 0.05: return False, 0
        return True, time.time() - t0
    except: return False, 0


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
                ff = {ex.submit(test_url, c["url"]): c for c in cl[:SPEED_TEST_LIMIT]}
                for f in as_completed(ff):
                    c = ff[f]
                    ok, sp = f.result()
                    if ok:
                        c["speed"] = sp
                        alive.append(c)
            alive.sort(key=lambda x: x.get("speed", 999))
            if alive:
                okd[k] = alive[:SPEED_TEST_LIMIT]
            done += 1
            if done % 100 == 0 or done == total:
                log.info("  测速进度: %d/%d" % (done, total))
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
