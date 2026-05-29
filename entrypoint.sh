#!/bin/bash
# IPTV 容器启动脚本
set -e

# 注入外部地址
if [ -n "$PUBLIC_IP" ]; then
    export EXTERNAL_HOST="http://$PUBLIC_IP:8888"
    sed -i "s/PROXY_HOST = \"127.0.0.1\"/PROXY_HOST = \"$PUBLIC_IP\"/" /app/config.py
    echo "代理地址: http://$PUBLIC_IP:8888"
fi

# 启动 nginx
nginx

# 启动流代理（后台）
cd /app
python proxy_server.py &
PROXY_PID=$!
echo "流代理 PID: $PROXY_PID"

# 先跑一次爬虫
echo "首次抓取..."
python main.py --skip-test || python main.py

# 链接 m3u 到 nginx 目录
ln -sf /app/output/*.m3u /var/www/html/

# 设置定时任务：每 6 小时更新
echo "0 */6 * * * cd /app && python main.py --skip-test && ln -sf /app/output/*.m3u /var/www/html/" > /tmp/crontab
crontab /tmp/crontab
service cron start

echo ""
echo "============================================"
echo "✅ IPTV 服务已启动!"
echo ""
if [ -n "$PUBLIC_IP" ]; then
    echo "📺 港台频道: http://$PUBLIC_IP/hk_tw.m3u"
    echo "🎬 电影频道: http://$PUBLIC_IP/movies.m3u"
    echo "🌏 全频道:   http://$PUBLIC_IP/all.m3u"
else
    echo "📺 港台频道: http://\$(hostname -I | awk '{print \$1}')/hk_tw.m3u"
fi
echo "============================================"

# 等待后台进程
wait
