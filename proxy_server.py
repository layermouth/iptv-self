#!/usr/bin/env python3
"""
IPTV 流代理服务
接收 http://VPS:8888/proxy?url=原始流地址 的请求，
从源站拉流并实时转发给客户端（HLS/m3u8 或 TS 流）。

对于 HLS (.m3u8) 流：解析 playlist 中的相对路径并改写为代理地址
对于 TS 流：直接透传
"""

import asyncio
import logging
from urllib.parse import urlparse, urljoin, unquote
from aiohttp import web, ClientSession, ClientTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PROXY_HOST = "0.0.0.0"
PROXY_PORT = 8888

# 外部访问地址（从环境变量获取，用于改写 m3u8 内的相对 URL）
EXTERNAL_HOST = None  # 由 deploy.sh 注入


async def proxy_stream(request: web.Request) -> web.StreamResponse:
    """代理流请求：从源站拉流 → 透传给客户端"""
    target_url = request.query.get("url", "")
    if not target_url:
        return web.Response(text="Missing 'url' parameter", status=400)

    target_url = unquote(target_url)
    log.info(f"代理请求: {target_url[:100]}")

    timeout = ClientTimeout(total=600, connect=10)
    try:
        async with ClientSession(timeout=timeout) as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": urlparse(target_url).scheme + "://" + urlparse(target_url).netloc,
            }

            async with session.get(target_url, headers=headers) as upstream:
                if upstream.status != 200:
                    log.warning(f"上游返回 {upstream.status}: {target_url[:80]}")
                    return web.Response(status=upstream.status)

                content_type = upstream.headers.get("Content-Type", "")

                # HLS playlist (.m3u8): 需要改写内部 URL
                if "m3u8" in content_type or "vnd.apple.mpegurl" in content_type or target_url.endswith(".m3u8"):
                    body = await upstream.text()
                    rewritten = rewrite_m3u8(body, target_url, request)
                    resp = web.StreamResponse(
                        status=200,
                        headers={"Content-Type": "application/vnd.apple.mpegurl"},
                    )
                    await resp.prepare(request)
                    await resp.write(rewritten.encode("utf-8"))
                    await resp.write_eof()
                    return resp

                # 普通流（TS / MP4 / FLV 等）: 直接透传
                resp = web.StreamResponse(status=200, headers={"Content-Type": content_type})
                await resp.prepare(request)

                chunk_size = 64 * 1024  # 64KB
                while True:
                    chunk = await upstream.content.read(chunk_size)
                    if not chunk:
                        break
                    await resp.write(chunk)

                await resp.write_eof()
                return resp

    except asyncio.TimeoutError:
        log.warning(f"超时: {target_url[:80]}")
        return web.Response(text="Upstream timeout", status=504)
    except Exception as e:
        log.error(f"代理错误: {e} — {target_url[:80]}")
        return web.Response(text=f"Proxy error: {e}", status=502)


def rewrite_m3u8(body: str, base_url: str, request: web.Request) -> str:
    """改写 m3u8 playlist 中的 URL，将相对路径和绝对路径都改为代理地址"""
    proxy_base = EXTERNAL_HOST or f"http://{request.host}"
    proxy_base = proxy_base.rstrip("/")
    import urllib.parse

    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            # 这是一个资源 URL
            if stripped.startswith("http://") or stripped.startswith("https://"):
                # 绝对 URL：也走代理
                encoded = urllib.parse.quote(stripped, safe="")
                lines.append(f"{proxy_base}/proxy?url={encoded}")
            else:
                # 相对 URL
                full_url = urljoin(base_url, stripped)
                encoded = urllib.parse.quote(full_url, safe="")
                lines.append(f"{proxy_base}/proxy?url={encoded}")
        else:
            lines.append(line)
    return "\n".join(lines)


async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def start_proxy():
    app = web.Application()
    app.router.add_get("/proxy", proxy_stream)
    app.router.add_get("/health", health)
    app.router.add_get("/", health)

    log.info(f"流代理启动: http://{PROXY_HOST}:{PROXY_PORT}")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, PROXY_HOST, PROXY_PORT)
    await site.start()

    # 保持运行
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    import os
    EXTERNAL_HOST = os.environ.get("EXTERNAL_HOST", "")
    asyncio.run(start_proxy())
