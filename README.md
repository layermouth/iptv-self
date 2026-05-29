# 🛰️ IPTV 自建直播源

每日自动从 14 个公开源聚合港台 + 电影频道，通过 VPS 流代理突破地域限制。

## 🚀 VPS 部署（推荐 — 所有频道可播）

### 一行命令

用 FinalShell / Xshell / Termius 连上你的 Ubuntu 22.04 VPS，粘贴：

```bash
curl -sSL https://raw.githubusercontent.com/layermouth/iptv-self/main/deploy.sh | sudo bash
```

等 2 分钟，脚本会自动：
1. 装 Docker
2. 构建镜像（爬虫 + nginx + 流代理）
3. 启动服务
4. 跑第一次频道抓取
5. 输出 m3u 订阅地址

### 拿到订阅链接

部署完成后输出类似：

```
📺 港台频道: http://123.45.67.89/hk_tw.m3u
🎬 电影频道: http://123.45.67.89/movies.m3u
🌏 全频道:   http://123.45.67.89/all.m3u
```

把链接导入 APTV，所有频道通过 VPS 中转，**不受大陆 IP 限制**。

### 管理命令

```bash
docker logs iptv-self          # 查看日志
docker exec iptv-self python /app/main.py   # 手动更新频道
docker compose restart         # 重启
docker compose down            # 停止
```

---

## 📺 收录频道

### 🇭🇰 香港
- TVB：翡翠台、明珠台、无线新闻台、J2
- ViuTV：ViuTV (99台)、ViuTVsix (96台)
- HOY TV：HOY TV (77台)、HOY 资讯台 (78台)
- RTHK：港台电视 31/32/33
- Now TV：Now 新闻台、Now 直播台
- 凤凰卫视：凤凰中文台、凤凰资讯台

### 🇹🇼 台湾
- 无线台：台视、中视、华视、民视、公视
- 新闻台：中天、东森、三立、TVBS、年代
- 综合台：八大、纬来、龙华

### 🎬 电影
- 天映经典、美亚电影、CHC 家庭影院
- 龙华电影/洋片/经典/戏剧/偶像/日韩
- HBO、CINEMAX、FOX Movies
- CCTV-6、1905 电影网
- 韩国电影、漫威电影、周星驰/成龙专题

### 🎨 动画
- Disney Channel、Disney XD、Disney Jr.
- Cartoon Classics、龙华卡通

---

## 🔧 GitHub Actions 模式（无需 VPS，但不带流代理）

如果想只用 GitHub 自动更新：

1. Fork 仓库 → 启用 Actions
2. 订阅链接：`https://raw.githubusercontent.com/layermouth/iptv-self/main/output/hk_tw.m3u`
3. 频道直接从大陆直连，受地域限制（翡翠台/ViuTV/HBO 等播不了）

---

## ⚙️ 配置说明

编辑 `config.py`：

| 配置项 | 说明 |
| :--- | :--- |
| `SOURCE_URLS` | 数据源列表（增删改） |
| `HK_TW_KEYWORDS` | 港台频道白名单关键词 |
| `MOVIE_KEYWORDS` | 电影频道白名单关键词 |
| `PROXY_ENABLED` | VPS 代理开关（部署时自动设为 True） |

---

## ⚠️ 免责声明

- 本项目仅是一个技术工具，不存储任何视频流文件
- 所有直播源链接均来自互联网公开渠道
- 频道版权归相关电视台所有
- 仅供学习交流使用，请勿用于商业用途
