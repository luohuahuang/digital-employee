#!/usr/bin/env bash
# =============================================================================
# deploy.sh — 部署 / 本地启动脚本
# 支持平台：macOS（开发模式）/ Ubuntu / Debian / CentOS / RHEL / Alibaba Cloud Linux
#
# 用法（从 app/ 目录执行）：
#
#   macOS（本地开发，前台运行）：
#     chmod +x deploy.sh
#     ./deploy.sh
#
#   Linux（生产部署，nginx + systemd）：
#     chmod +x deploy.sh
#     sudo ./deploy.sh
#
# macOS 模式：
#   - 通过 Homebrew 安装 Python / Node（如未安装）
#   - 创建 venv，安装依赖，构建前端和文档
#   - 直接在前台启动 FastAPI（Ctrl-C 停止）
#   - 访问：http://localhost:<WEB_PORT>/digital-employee/
#
# Linux 生产模式：
#   - 安装 Python / Node / nginx
#   - 创建 venv，安装依赖，构建前端和文档
#   - 配置 nginx（监听 PUBLIC_PORT，默认 80，代理到 FastAPI）
#   - 注册 systemd 服务（开机自启，后台运行）
#   - 访问：http://<host>:<PUBLIC_PORT>/digital-employee/
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo " Digital Employee — Deploy"
echo "========================================="

# ── 检测操作系统 ───────────────────────────────────────────────────────────────
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
        return
    fi
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    else
        echo "unknown"
    fi
}
OS=$(detect_os)

if [ "$OS" = "macos" ]; then
    echo " 模式：macOS 本地开发"
else
    echo " 模式：Linux 生产部署"
fi

# ── 0. 系统依赖安装 ────────────────────────────────────────────────────────────
echo ""
echo "[0/5] Checking system dependencies..."

# ---------- Python ----------
PYTHON311=""
for cmd in python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null)
        if "$cmd" -c "import sys; exit(0 if sys.version_info>=(3,9) else 1)" 2>/dev/null; then
            PYTHON311="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON311" ]; then
    echo "  Python 3.9+ not found. Installing..."
    case "$OS" in
        macos)
            if ! command -v brew &>/dev/null; then
                echo "  ✗ 未找到 Homebrew。请先安装：https://brew.sh"
                exit 1
            fi
            brew install python@3.11
            PYTHON311="$(brew --prefix python@3.11)/bin/python3.11"
            ;;
        ubuntu|debian)
            apt-get update -y -q
            apt-get install -y -q software-properties-common
            add-apt-repository -y ppa:deadsnakes/ppa
            apt-get update -y -q
            apt-get install -y -q python3.11 python3.11-venv python3.11-dev
            PYTHON311="python3.11"
            ;;
        centos|rhel|almalinux|rocky|alinux|anolis)
            if command -v dnf &>/dev/null; then
                dnf install -y python3.11 python3.11-devel || {
                    dnf install -y epel-release
                    dnf install -y python3.11 python3.11-devel
                }
            else
                yum install -y https://repo.ius.io/ius-release-el7.rpm || true
                yum install -y python311 python311-devel || {
                    echo "  ✗ 无法自动安装 Python 3.11（CentOS 7 支持有限）"
                    exit 1
                }
            fi
            PYTHON311="python3.11"
            ;;
        *)
            echo "  ✗ 未识别的发行版: $OS。请手动安装 Python 3.11 后重新运行。"
            exit 1
            ;;
    esac
fi
echo "  ✓ Python $("$PYTHON311" --version 2>&1 | grep -o '[0-9.]*')"

# ---------- Node.js ----------
if ! command -v node &>/dev/null || ! node -e "process.exit(parseInt(process.versions.node)<18?1:0)" 2>/dev/null; then
    echo "  Node.js 18+ not found. Installing..."
    case "$OS" in
        macos)
            if ! command -v brew &>/dev/null; then
                echo "  ✗ 未找到 Homebrew。请先安装：https://brew.sh"
                exit 1
            fi
            brew install node
            ;;
        ubuntu|debian)
            curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
            apt-get install -y -q nodejs
            ;;
        centos|rhel|almalinux|rocky|alinux|anolis)
            curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
            if command -v dnf &>/dev/null; then dnf install -y nodejs; else yum install -y nodejs; fi
            ;;
        *)
            echo "  ✗ 无法自动安装 Node.js，请手动安装 Node.js 20 后重新运行。"
            exit 1
            ;;
    esac
fi
echo "  ✓ Node.js $(node --version)"

# ---------- nginx（仅 Linux）----------
if [ "$OS" != "macos" ]; then
    if ! command -v nginx &>/dev/null; then
        echo "  Installing nginx..."
        case "$OS" in
            ubuntu|debian)
                apt-get update -y -q && apt-get install -y -q nginx
                ;;
            centos|rhel|almalinux|rocky|alinux|anolis)
                if command -v dnf &>/dev/null; then
                    dnf install -y nginx || { dnf install -y epel-release && dnf install -y nginx; }
                else
                    yum install -y epel-release && yum install -y nginx
                fi
                ;;
        esac
    fi
    echo "  ✓ nginx $(nginx -v 2>&1 | grep -o '[0-9.]*$')"
fi

# ── 检查 .env 文件 ─────────────────────────────────────────────────────────────
echo ""
if [ ! -f ".env" ]; then
    echo "  ⚠ 未找到 .env 文件，从 .env.example 复制..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  ✓ 已创建 .env，请编辑后重新运行："
        echo ""
        echo "    必填：ANTHROPIC_API_KEY / EMBEDDING_API_KEY"
        if [ "$OS" != "macos" ]; then
            echo "    可选：PUBLIC_PORT（默认 80）、WEB_BASE_PATH（默认 /digital-employee）"
        fi
        echo ""
        echo "  编辑后运行：$([ "$OS" = "macos" ] && echo './deploy.sh' || echo 'sudo ./deploy.sh')"
        exit 0
    else
        echo "  ✗ .env.example 不存在，请手动创建 .env"
        exit 1
    fi
fi

# 读取部署参数
WEB_PORT=$(grep -E "^WEB_PORT=" .env 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)
WEB_PORT=${WEB_PORT:-8000}

if [ "$OS" != "macos" ]; then
    PUBLIC_PORT=$(grep -E "^PUBLIC_PORT=" .env 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)
    PUBLIC_PORT=${PUBLIC_PORT:-80}

    WEB_BASE_PATH=$(grep -E "^WEB_BASE_PATH=" .env 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)
    WEB_BASE_PATH=${WEB_BASE_PATH:-/digital-employee}
    WEB_BASE_PATH="/${WEB_BASE_PATH#/}"   # 确保以 / 开头
    WEB_BASE_PATH="${WEB_BASE_PATH%/}"    # 去掉尾部 /

    echo ""
    echo "  部署参数："
    echo "    公开访问：http://<host>:${PUBLIC_PORT}${WEB_BASE_PATH}/"
    echo "    FastAPI 内部端口：${WEB_PORT}"
fi

# ── 1. Python 虚拟环境 + 依赖 ─────────────────────────────────────────────────
echo ""
echo "[1/5] Setting up Python virtual environment..."

VENV_DIR="$SCRIPT_DIR/venv"
NEED_NEW_VENV=1

if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
    if "$VENV_DIR/bin/python" -c "import sys; exit(0 if sys.version_info>=(3,9) else 1)" 2>/dev/null; then
        echo "  venv already exists ($("$VENV_DIR/bin/python" --version)), skipping creation"
        NEED_NEW_VENV=0
    else
        echo "  venv uses old Python, recreating..."
        rm -rf "$VENV_DIR"
    fi
fi

if [ "$NEED_NEW_VENV" -eq 1 ]; then
    "$PYTHON311" -m venv "$VENV_DIR"
    echo "  ✓ Created venv with $("$PYTHON311" --version)"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet

echo "  Installing requirements..."
if [ "$OS" = "macos" ]; then
    pip install -q -r requirements.txt
else
    pip install -r requirements.txt \
        -i https://pypi.tuna.tsinghua.edu.cn/simple/ \
        --extra-index-url https://pypi.org/simple/ \
        --trusted-host pypi.tuna.tsinghua.edu.cn \
        --quiet
fi
echo "  ✓ Python dependencies installed"

# ── 2. 构建文档 + 前端 ────────────────────────────────────────────────────────
echo ""
echo "[2/5] Building docs and frontend..."

# HTML 文档门户
python ../docs/build.py
echo "  ✓ HTML docs built"

# 前端
if [ -d "web/frontend/node_modules" ]; then
    echo "  node_modules found, skipping npm install"
else
    if [ "$OS" = "macos" ]; then
        (cd web/frontend && npm install --silent)
    else
        (cd web/frontend && npm install --registry https://registry.npmmirror.com)
    fi
fi

(cd web/frontend && npm run build)
echo "  ✓ Frontend ready"

# ── 3. 数据库初始化 + 迁移 ────────────────────────────────────────────────────
echo ""
echo "[3/5] Initializing database..."
python3 - <<'PYEOF'
import sys, os
sys.path.insert(0, '.')
from web.db.database import init_db
init_db()
print("  Database ready.")

import sqlite3
db = sqlite3.connect('web/de_team.db')
count = db.execute("SELECT COUNT(*) FROM agents WHERE is_active=1").fetchone()[0]
db.close()

if count == 0:
    print("  Empty database — running seed scripts...")
    import subprocess
    scripts = [
        ('seed_demo.py',         'Demo agents + conversations'),
        ('seed_observability.py','Observability / audit demo data'),
        ('seed_test_suites.py',  'Shopee SG mock test suites'),
    ]
    for script, desc in scripts:
        if os.path.exists(script):
            print(f"  → {desc}...")
            subprocess.run([sys.executable, script], check=True)
        else:
            print(f"  ⚠ {script} not found, skipped")
    print("  Seeding complete.")
else:
    print(f"  Found {count} active agent(s) — skipping seed.")
PYEOF

# ── 4. 知识库向量索引（可选）────────────────────────────────────────────────────
echo ""
echo "[4/5] Knowledge base..."
if [ -d "knowledge/.chroma" ] && [ "$(ls -A knowledge/.chroma 2>/dev/null)" ]; then
    echo "  .chroma index exists, skipping (delete knowledge/.chroma/ to force rebuild)"
else
    EMBEDDING_KEY=$(grep -E "^EMBEDDING_API_KEY=" .env 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)
    OAI_KEY=$(grep -E "^OPENAI_API_KEY=" .env 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)
    if [ -n "$EMBEDDING_KEY" ] || [ -n "$OAI_KEY" ]; then
        echo "  Building vector index..."
        python knowledge/setup_kb.py
        echo "  ✓ Knowledge base ready."
    else
        echo "  ⚠ EMBEDDING_API_KEY not set — skipping KB setup."
        echo "    To enable later: set EMBEDDING_API_KEY in .env, then:"
        echo "      source venv/bin/activate && python knowledge/setup_kb.py"
    fi
fi

# ── 5. 启动服务 ───────────────────────────────────────────────────────────────
echo ""
echo "[5/5] Starting server..."

if [ "$OS" = "macos" ]; then
    # ── macOS：前台直接运行 ──────────────────────────────────────────────────
    echo ""
    echo "========================================="
    echo " ✓ 启动中..."
    echo " 访问地址：http://localhost:${WEB_PORT}/digital-employee/"
    echo " API Docs： http://localhost:${WEB_PORT}/digital-employee/api-docs"
    echo " HTML Docs：http://localhost:${WEB_PORT}/digital-employee/docs/"
    echo ""
    echo " 按 Ctrl-C 停止服务"
    echo "========================================="
    echo ""
    python web/server.py

else
    # ── Linux：配置 nginx + systemd ──────────────────────────────────────────

    # --- nginx WebSocket map ---
    if ! grep -q "connection_upgrade" /etc/nginx/nginx.conf 2>/dev/null && \
       [ ! -f /etc/nginx/conf.d/ws-upgrade-map.conf ]; then
        cat > /etc/nginx/conf.d/ws-upgrade-map.conf <<'MAPEOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
MAPEOF
    fi

    # 删除可能冲突的默认 nginx 配置文件（如果存在）
    rm -f /etc/nginx/conf.d/default.conf

    # 获取本机内网 IP 和公网 IP 作为 server_name，避免使用 server_name _ + default_server。
    # 阿里云 nginx.conf 主文件内嵌了 default_server，用 _ 会冲突导致我们的配置被忽略。
    # 使用具体 IP/主机名则无需争抢 default_server，nginx 按 server_name 精确匹配。
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    SERVER_NAMES="$LOCAL_IP localhost"

    # --- nginx site config ---
    NGINX_CONF="/etc/nginx/conf.d/digital-employee.conf"
    cat > "$NGINX_CONF" <<NGINXEOF
server {
    listen ${PUBLIC_PORT};
    listen [::]:${PUBLIC_PORT};
    server_name ${SERVER_NAMES};

    location = / {
        return 301 ${WEB_BASE_PATH}/;
    }

    location ${WEB_BASE_PATH}/ {
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

    nginx -t
    systemctl enable nginx
    if systemctl is-active --quiet nginx; then
        systemctl reload nginx
    else
        systemctl start nginx
    fi

    # --- systemd service ---
    SERVICE_NAME="digital-employee"
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    PYTHON_BIN="$VENV_DIR/bin/python"

    cat > /tmp/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Digital Employee Platform (FastAPI)
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$SCRIPT_DIR
EnvironmentFile=$SCRIPT_DIR/.env
ExecStart=$PYTHON_BIN web/server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    cp /tmp/${SERVICE_NAME}.service "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl restart "$SERVICE_NAME"

    sleep 2
    STATUS=$(systemctl is-active "$SERVICE_NAME")
    echo ""
    echo "========================================="
    if [ "$STATUS" = "active" ]; then
        SERVER_IP=$(hostname -I | awk '{print $1}')
        echo " ✓ 服务已启动并设为开机自启"
        echo ""
        echo " 访问地址：http://${SERVER_IP}:${PUBLIC_PORT}${WEB_BASE_PATH}/"
        echo " API Docs： http://${SERVER_IP}:${PUBLIC_PORT}${WEB_BASE_PATH}/api-docs"
        echo " HTML Docs：http://${SERVER_IP}:${PUBLIC_PORT}${WEB_BASE_PATH}/docs/"
    else
        echo " ✗ FastAPI 启动失败，查看日志："
        journalctl -u "$SERVICE_NAME" -n 30 --no-pager
    fi
    echo ""
    echo " 常用命令："
    echo "   查看状态：sudo systemctl status $SERVICE_NAME"
    echo "   查看日志：sudo journalctl -u $SERVICE_NAME -f"
    echo "   重启服务：sudo systemctl restart $SERVICE_NAME"
    echo "   停止服务：sudo systemctl stop $SERVICE_NAME"
    echo "   nginx 日志：sudo tail -f /var/log/nginx/error.log"
    echo "========================================="
fi
