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
    # 去掉分辨率后缀
    name = re.sub(r"\s+\d+p$", "", name)
    name = re.sub(r"\s+(HD|FHD|SD|UHD|4K|8K)$", "", name)
    return name.strip()


def match_keywords(name: str, keywords: list[str]) -> bool:
    """检查频道名是否匹配任一关键词（不区分大小写）"""
    name_lower = name.lower()
    for kw in keywords:
        if kw.lower() in name_lower:
            return True
    return False


def sort_key(name: str, is_movie: bool = False) -> int:
    """返回频道的排序权重，越小越靠前"""
    keywords = MOVIE_ORDER_KEYWORDS if is_movie else ORDER_KEYWORDS
    for i, kw in enumerate(keywords):
        if kw.lower() in name.lower():
            return i
    return len(keywords)


def proxy_url(original_url: str) -> str:
    """如果启用了 VPS 代理，将原始流地址替换为代理地址"""
    if not PROXY_ENABLED:
        return original_url
    from urllib.parse import quote
    encoded = quote(original_url, safe='')
    return f"http://{PROXY_HOST}:{PROXY_PORT}/proxy?url={encoded}"


# ===== 网络请求 =====
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})
session.timeout = 30


def fetch_source(source: dict) -> list[dict]:
    """抓取单个数据源"""
    try:
        resp = session.get(source["url"], timeout=30)
        resp.raise_for_status()
        # 处理可能的编码问题
        content = resp.text
        if resp.encoding and resp.encoding.lower() != "utf-8":
            try:
                content = resp.content.decode("utf-8")
            except:
                pass
        channels = parse_m3u(content)
        log.info(f"  ✓ {source['name']}: {len(channels)} 个频道")
        for ch in channels:
            ch["_source"] = source["name"]
            ch["_priority"] = source["priority"]
        return channels
    except Exception as e:
        log.warning(f"  ✗ {source['name']}: {e}")
        return []


def test_stream(url: str, timeout: int = SPEED_TEST_TIMEOUT) -> tuple[bool, float]:
    """测试流地址是否可用，返回 (可用, 响应时间秒)"""
    try:
        start = time.time()
        # 只请求前几个字节，不下载完整流
        resp = session.get(url, stream=True, timeout=timeout)
        if resp.status_code == 200:
            # 读取一点数据确认流活跃
            chunk = next(resp.iter_content(chunk_size=1024), None)
            resp.close()
            if chunk and len(chunk) > 100:
                elapsed = time.time() - start
                return True, elapsed
        resp.close()
    except:
        pass
    return False, 0


# ===== 去重 =====
def channel_key(ch: dict) -> str:
    """生成频道唯一标识（基于标准化名称）"""
    name = normalize_name(ch.get("name", ""))
    return hashlib.md5(name.lower().encode()).hexdigest()


# ===== 主流程 =====
def main():
    skip_test = "--skip-test" in sys.argv
    log.info("=" * 60)
    log.info("IPTV 自建直播源 - 开始更新")
    log.info(f"数据源数量: {len(SOURCE_URLS)}")
    log.info(f"跳过测速: {skip_test}")
    log.info("=" * 60)

    # ----- 1. 聚合所有源 -----
    log.info("[1/4] 抓取数据源...")
    all_channels = []
    for src in SOURCE_URLS:
        channels = fetch_source(src)
        all_channels.extend(channels)
    log.info(f"总计抓取: {len(all_channels)} 个频道条目")

    # ----- 2. 去重合并 -----
    log.info("[2/4] 去重合并...")
    merged = OrderedDict()  # key -> 最优 channel
    for ch in all_channels:
        key = channel_key(ch)
        if key in merged:
            existing = merged[key]
            # 保留优先级更高的源
            if ch.get("_priority", 99) < existing.get("_priority", 99):
                merged[key] = ch
        else:
            merged[key] = ch
    log.info(f"去重后: {len(merged)} 个唯一频道")

    # ----- 2.5 分类：港台 / 电影 / 其他 -----
    hk_tw_channels = {}
    movie_channels = {}
    other_channels = {}
    for key, ch in merged.items():
        name = normalize_name(ch.get("name", ""))
        ch["_name_norm"] = name
        if match_keywords(name, HK_TW_KEYWORDS):
            hk_tw_channels[key] = ch
        if match_keywords(name, MOVIE_KEYWORDS):
            movie_channels[key] = ch
        if not match_keywords(name, HK_TW_KEYWORDS) and not match_keywords(name, MOVIE_KEYWORDS):
            other_channels[key] = ch
    # 港台和电影有重叠是正常的
    log.info(f"港台频道: {len(hk_tw_channels)}, 电影频道: {len(movie_channels)}, 其他: {len(other_channels)}")

    # ----- 3. 测速（可选） -----
    tested_hk_tw = {}
    tested_movie = {}
    tested_other = {}

    if not skip_test:
        log.info(f"[3/4] 测速验证 (超时={SPEED_TEST_TIMEOUT}s, 并发={MAX_WORKERS})...")
        total = len(hk_tw_channels) + len(movie_channels) + len(other_channels)
        done = 0

        def test_one(item):
            key, ch = item
            ok, elapsed = test_stream(ch["url"])
            return key, ch, ok, elapsed

        all_to_test = list(hk_tw_channels.items()) + list(movie_channels.items()) + list(other_channels.items())
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(test_one, item): item for item in all_to_test}
            for future in as_completed(futures):
                key, ch, ok, elapsed = future.result()
                done += 1
                if ok:
                    ch["_speed"] = round(elapsed, 2)
                    if key in hk_tw_channels:
                        tested_hk_tw[key] = ch
                    if key in movie_channels:
                        tested_movie[key] = ch
                    if key in other_channels:
                        tested_other[key] = ch
                if done % 50 == 0:
                    log.info(f"  测速进度: {done}/{total}")
        log.info(f"  港台可用: {len(tested_hk_tw)}, 电影可用: {len(tested_movie)}, 其他可用: {len(tested_other)}")
    else:
        log.info("[3/4] 跳过测速 (--skip-test)")
        tested_hk_tw = hk_tw_channels
        tested_movie = movie_channels
        tested_other = other_channels

    # ----- 4. 排序 + 生成 m3u -----
    log.info("[4/4] 生成 m3u 文件...")

    def generate_m3u(channels: dict, output_path: str, title: str, is_movie: bool = False):
        """生成 m3u 文件"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        sorted_channels = sorted(
            channels.values(),
            key=lambda ch: (sort_key(normalize_name(ch.get("name", "")), is_movie),
                           normalize_name(ch.get("name", "")))
        )
        now_str = datetime.now(TZ_BEIJING).strftime("%Y-%m-%d %H:%M")
        lines = ['#EXTM3U x-tvg-url="{}"'.format(EPG_URL)]
        lines.append(f"# 更新时间: {now_str} (北京时间)")
        lines.append(f"# 频道数: {len(sorted_channels)}")
        lines.append(f"# {title}")
        if PROXY_ENABLED:
            lines.append(f"# 代理模式: 通过 http://{PROXY_HOST}:{PROXY_PORT} 中转")
        lines.append("")

        for ch in sorted_channels:
            name = normalize_name(ch.get("name", ""))
            logo = ch.get("tvg-logo", "")
            group = ch.get("group-title", "")
            url = proxy_url(ch["url"])
            speed = ch.get("_speed", "")
            source = ch.get("_source", "")

            extinf = f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo}" group-title="{group}"'
            if speed:
                extinf += f' speed="{speed}s"'
            if source:
                extinf += f' source="{source}"'
            extinf += f",{name}"
            lines.append(extinf)
            lines.append(url)
            lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        log.info(f"  已生成: {output_path} ({len(sorted_channels)} 频道)")

    # 生成港台专用
    generate_m3u(tested_hk_tw, HK_TW_OUTPUT, "港台频道 - 自建直播源")
    # 生成电影专用
    generate_m3u(tested_movie, MOVIE_OUTPUT, "电影频道 - 自建直播源", is_movie=True)
    # 生成全频道
    all_tested = {}
    all_tested.update(tested_hk_tw)
    all_tested.update(tested_movie)
    all_tested.update(tested_other)
    generate_m3u(all_tested, ALL_OUTPUT, "全频道 - 自建直播源")

    # ----- 汇总 -----
    log.info("=" * 60)
    log.info("✅ 更新完成!")
    log.info(f"  港台频道: {HK_TW_OUTPUT} ({len(tested_hk_tw)} 个)")
    log.info(f"  电影频道: {MOVIE_OUTPUT} ({len(tested_movie)} 个)")
    log.info(f"  全频道:   {ALL_OUTPUT} ({len(all_tested)} 个)")
    if PROXY_ENABLED:
        log.info(f"  代理模式: http://{PROXY_HOST}:{PROXY_PORT}")
    else:
        log.info(f"  GitHub:   {GITHUB_RAW_BASE}/")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
