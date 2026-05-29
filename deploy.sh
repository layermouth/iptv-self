#!/bin/bash
# ============================================
# IPTV 自建直播源 - VPS 一键部署脚本
# 适用于 Ubuntu 22.04
# 用法: curl -sSL https://raw.githubusercontent.com/layermouth/iptv-self/main/deploy.sh | sudo bash
# ============================================
set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════╗"
echo "║   🛰️  IPTV 自建直播源 - VPS 部署    ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"

# ---- 1. 检测系统 ----
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "系统: $NAME $VERSION_ID"
else
    echo "⚠️ 无法检测系统版本，继续尝试..."
fi

# ---- 2. 安装 Docker ----
if ! command -v docker &> /dev/null; then
    echo ""
    echo -e "${YELLOW}[1/5] 安装 Docker...${NC}"
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker
    systemctl start docker
    echo -e "${GREEN}✓ Docker 安装完成${NC}"
else
    echo -e "${GREEN}✓ Docker 已安装${NC}"
fi

# ---- 3. 安装 Docker Compose ----
if ! docker compose version &> /dev/null 2>&1; then
    echo ""
    echo -e "${YELLOW}[2/5] 安装 Docker Compose...${NC}"
    apt-get update -qq && apt-get install -y -qq docker-compose-plugin 2>/dev/null || true
    echo -e "${GREEN}✓ Docker Compose 安装完成${NC}"
else
    echo -e "${GREEN}✓ Docker Compose 已安装${NC}"
fi

# ---- 4. 获取 VPS 公网 IP ----
echo ""
echo -e "${YELLOW}[3/5] 检测 VPS IP...${NC}"
PUBLIC_IP=$(curl -s -4 ifconfig.me 2>/dev/null || curl -s -4 ip.sb 2>/dev/null || curl -s -4 ipinfo.io/ip 2>/dev/null || hostname -I | awk '{print $1}')
echo -e "${GREEN}✓ VPS IP: ${PUBLIC_IP}${NC}"

# ---- 5. 构建并启动 ----
echo ""
echo -e "${YELLOW}[4/5] 构建镜像并启动服务...${NC}"
PUBLIC_IP=$PUBLIC_IP docker compose up -d --build 2>&1 | tail -5

# 等待服务启动
sleep 5

# ---- 6. 检查状态 ----
echo ""
echo -e "${YELLOW}[5/5] 检查服务状态...${NC}"
if docker ps | grep -q iptv-self; then
    echo -e "${GREEN}✓ 容器运行中${NC}"
else
    echo "⚠️ 容器未运行，查看日志: docker logs iptv-self"
fi

# ---- 完成 ----
echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗"
echo "║          ✅  部署完成!               ║"
echo "╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "📺 ${GREEN}港台频道:${NC} http://${PUBLIC_IP}/hk_tw.m3u"
echo -e "🎬 ${GREEN}电影频道:${NC} http://${PUBLIC_IP}/movies.m3u"
echo -e "🌏 ${GREEN}全频道:  ${NC} http://${PUBLIC_IP}/all.m3u"
echo ""
echo "把这 3 个链接导入 APTV 即可观看！"
echo ""
echo -e "${YELLOW}提示:${NC}"
echo "  - 查看日志: docker logs iptv-self"
echo "  - 手动更新: docker exec iptv-self python /app/main.py"
echo "  - 重启服务: docker compose restart"
echo "  - 停止服务: docker compose down"
echo ""
