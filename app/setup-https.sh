#!/usr/bin/env bash
# =============================================================================
# setup-https.sh — 为 Digital Employee 配置 Let's Encrypt HTTPS
#
# 前提条件（运行本脚本前必须完成）：
#   1. 已成功运行 sudo ./deploy.sh（nginx + 服务已在 HTTP 模式运行）
#   2. 域名 DNS A 记录已指向本服务器公网 IP（需等待 DNS 生效，一般 5-30 分钟）
#   3. 阿里云安全组已开放 80 和 443 端口
#
# 用法：
#   sudo ./setup-https.sh <域名> <邮箱>
#   sudo ./setup-https.sh luohua.tech admin@luohua.tech
#
# 可选：同时支持 www 子域名：
#   sudo ./setup-https.sh luohua.tech admin@luohua.tech --www
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 参数解析 ──────────────────────────────────────────────────────────────────
DOMAIN="${1:-}"
EMAIL="${2:-}"
WITH_WWW=0
for arg in "$@"; do [ "$arg" = "--www" ] && WITH_WWW=1; done

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "用法: sudo ./setup-https.sh <域名> <邮箱> [--www]"
    echo "示例: sudo ./setup-https.sh luohua.tech admin@luohua.tech"
    exit 1
fi

echo "========================================="
echo " Digital Employee — HTTPS Setup"
echo " 域名: $DOMAIN"
echo " 邮箱: $EMAIL"
echo "========================================="

# ── 读取部署参数 ──────────────────────────────────────────────────────────────
WEB_BASE_PATH=$(grep -E "^WEB_BASE_PATH=" .env 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)
WEB_BASE_PATH=${WEB_BASE_PATH:-/digital-employee}
BASE="/${WEB_BASE_PATH#/}"
BASE="${BASE%/}"

WEB_PORT=$(grep -E "^WEB_PORT=" .env 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)
WEB_PORT=${WEB_PORT:-8000}

# ── 检测 OS ────────────────────────────────────────────────────────────────────
detect_os() {
    if [ -f /etc/os-release ]; then . /etc/os-release; echo "$ID"; else echo "unknown"; fi
}
OS=$(detect_os)

# ── 1. 安装 certbot ────────────────────────────────────────────────────────────
echo ""
echo "[1/4] Installing certbot..."

if command -v certbot &>/dev/null; then
    echo "  certbot already installed: $(certbot --version 2>&1)"
else
    case "$OS" in
        ubuntu|debian)
            apt-get update -y -q
            apt-get install -y -q certbot python3-certbot-nginx
            ;;
        centos|rhel|almalinux|rocky|alinux|anolis)
            if command -v dnf &>/dev/null; then
                dnf install -y epel-release
                dnf install -y certbot python3-certbot-nginx
            else
                yum install -y epel-release
                yum install -y certbot python3-certbot-nginx
            fi
            ;;
        *)
            echo "  ✗ 未识别的发行版 $OS，请手动安装 certbot"
            echo "    参考：https://certbot.eff.org/instructions"
            exit 1
            ;;
    esac
    echo "  ✓ certbot installed"
fi

# ── 2. 验证 DNS 解析 ───────────────────────────────────────────────────────────
echo ""
echo "[2/4] Verifying DNS resolution..."

RESOLVED_IP=$(dig +short "$DOMAIN" A 2>/dev/null | tail -1 || \
              nslookup "$DOMAIN" 2>/dev/null | awk '/^Address: / { print $2 }' | tail -1 || \
              true)

if [ -z "$RESOLVED_IP" ]; then
    echo "  ⚠ 无法解析 $DOMAIN，可能 DNS 尚未生效"
    echo "    请检查域名 A 记录是否已指向本服务器，然后重新运行本脚本"
    read -rp "  是否仍要继续？(y/N) " CONT
    [[ "$CONT" =~ ^[Yy]$ ]] || exit 1
else
    echo "  $DOMAIN → $RESOLVED_IP"
fi

# ── 3. 申请证书（certbot --nginx 自动完成 ACME 验证并更新 nginx 配置）────────
echo ""
echo "[3/4] Obtaining Let's Encrypt certificate..."

# 构建域名参数
DOMAIN_ARGS="-d $DOMAIN"
[ "$WITH_WWW" -eq 1 ] && DOMAIN_ARGS="$DOMAIN_ARGS -d www.$DOMAIN"

# 先确保 nginx 在运行（certbot --nginx 需要 nginx 提供 ACME challenge 服务）
systemctl is-active --quiet nginx || systemctl start nginx

certbot certonly \
    --nginx \
    $DOMAIN_ARGS \
    --email "$EMAIL" \
    --agree-tos \
    --non-interactive \
    --keep-until-expiring

CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
echo "  ✓ Certificate obtained: $CERT_DIR"

# ── 4. 写入完整的 HTTPS nginx 配置 ────────────────────────────────────────────
echo ""
echo "[4/4] Writing HTTPS nginx config..."

# WebSocket upgrade map（如已存在则跳过）
if ! grep -q "connection_upgrade" /etc/nginx/nginx.conf 2>/dev/null && \
   [ ! -f /etc/nginx/conf.d/ws-upgrade-map.conf ]; then
    cat > /etc/nginx/conf.d/ws-upgrade-map.conf <<'MAPEOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
MAPEOF
fi

# 构建 server_name（主域名 + 可选 www）
SERVER_NAME="$DOMAIN"
[ "$WITH_WWW" -eq 1 ] && SERVER_NAME="$DOMAIN www.$DOMAIN"

cat > /etc/nginx/conf.d/digital-employee.conf <<NGINXEOF
# HTTP → HTTPS 重定向
server {
    listen 80;
    listen [::]:80;
    server_name $SERVER_NAME;
    return 301 https://\$host\$request_uri;
}

# HTTPS 主配置
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $SERVER_NAME;

    ssl_certificate     $CERT_DIR/fullchain.pem;
    ssl_certificate_key $CERT_DIR/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    # 访问根路径时跳转到应用
    location = / {
        return 301 https://\$host${BASE}/;
    }

    # 应用主入口（代理到 FastAPI，nginx 负责剥掉 ${BASE} 前缀）
    location ${BASE}/ {
        proxy_pass http://127.0.0.1:${WEB_PORT}/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
NGINXEOF

echo "  ✓ nginx config written"

# 测试 + 重载
nginx -t
systemctl reload nginx

echo ""
echo "========================================="
echo " ✓ HTTPS 配置完成！"
echo ""
echo " 访问地址：https://${DOMAIN}${BASE}/"
echo " API Docs： https://${DOMAIN}${BASE}/api-docs"
echo " HTML Docs：https://${DOMAIN}${BASE}/docs/"
echo ""
echo " 证书自动续期：certbot 已注册 systemd 定时任务，每天自动检查并续期"
echo " 手动测试续期：sudo certbot renew --dry-run"
echo "========================================="
