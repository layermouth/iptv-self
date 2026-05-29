FROM python:3.12-slim

# 安装依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    curl \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir aiohttp

# 复制代码
COPY config.py /app/config.py
COPY main.py /app/main.py
COPY proxy_server.py /app/proxy_server.py
COPY nginx.conf /etc/nginx/sites-available/default
COPY deploy.sh /app/deploy.sh

# 修改 config.py 启用代理模式
RUN sed -i 's/PROXY_ENABLED = False/PROXY_ENABLED = True/' /app/config.py && \
    sed -i 's/PROXY_HOST = "127.0.0.1"/PROXY_HOST = "127.0.0.1"/' /app/config.py && \
    sed -i 's/PROXY_PORT = 8888/PROXY_PORT = 8888/' /app/config.py

# 创建输出目录
RUN mkdir -p /app/output /var/www/html

# 复制启动脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /app
EXPOSE 80 8888

ENTRYPOINT ["/entrypoint.sh"]
