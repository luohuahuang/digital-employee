#!/usr/bin/env bash
# =============================================================================
# deploy.sh — 首次部署 / 环境重置脚本
# 适用平台：Ubuntu / Debian / CentOS / RHEL / Alibaba Cloud Linux
#
# 用法（从 app/ 目录执行）：
#   chmod +x deploy.sh
#   ./deploy.sh
#
# 功能：
#   0. 检测 OS，安装 Python 3.11 和 Node.js（如尚未安装）
#   1. 创建虚拟环境并安装 Python 依赖
#   2. 构建前端
#   3. 初始化 / 迁移数据库
#   4. （可选）重建知识库向量索引
#   5. 启动服务器
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo " Digital Employee — Deploy"
echo "========================================="

# ── 0. 系统依赖检测与安装 ──────────────────────────────────────────────────────

# ---------- 检测 OS ----------
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    elif command -v uname &>/dev/null; then
        uname -s | tr '[:upper:]' '[:lower:]'
    else
        echo "unknown"
    fi
}
OS=$(detect_os)

# ---------- 安装 Python 3.11 ----------
echo ""
echo "[0/4] Checking Python 3.11..."

PYTHON311=""
for cmd in python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null)
        if python3 -c "v=$VER; exit(0 if v>=(3,9) else 1)" 2>/dev/null; then
            PYTHON311="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON311" ]; then
    echo "  Python 3.9+ not found. Installing Python 3.11..."
    case "$OS" in
        ubuntu|debian)
            apt-get update -y -q
            apt-get install -y -q software-properties-common
            add-apt-repository -y ppa:deadsnakes/ppa
            apt-get update -y -q
            apt-get install -y -q python3.11 python3.11-venv python3.11-dev
            ;;
        centos|rhel|almalinux|rocky|alinux|anolis)
            # Alibaba Cloud Linux / CentOS 8+ / RHEL 8+
            if command -v dnf &>/dev/null; then
                dnf install -y python3.11 python3.11-devel || {
                    # 尝试启用 EPEL
                    dnf install -y epel-release
                    dnf install -y python3.11 python3.11-devel
                }
            else
                # CentOS 7 — 使用 IUS 源
                yum install -y https://repo.ius.io/ius-release-el7.rpm || true
                yum install -y python311 python311-devel || {
                    echo ""
                    echo "  ✗ 无法自动安装 Python 3.11（CentOS 7 支持有限）"
                    echo "    请手动安装后重新运行 deploy.sh："
                    echo "      sudo yum install -y openssl-devel bzip2-devel libffi-devel"
                    echo "      wget https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz"
                    echo "      tar xf Python-3.11.9.tgz && cd Python-3.11.9"
                    echo "      ./configure --enable-optimizations && make altinstall"
                    exit 1
                }
            fi
            ;;
        *)
            echo "  ✗ 未识别的发行版: $OS。请手动安装 Python 3.11 后重新运行。"
            exit 1
            ;;
    esac
    PYTHON311="python3.11"
fi

PYTHON_VER=$("$PYTHON311" --version)
echo "  ✓ 使用 $PYTHON_VER ($PYTHON311)"

# ---------- 安装 Node.js ----------
echo ""
echo "  Checking Node.js..."
if ! command -v node &>/dev/null || ! node -e "process.exit(parseInt(process.versions.node)<18?1:0)" 2>/dev/null; then
    echo "  Node.js 18+ not found. Installing..."
    case "$OS" in
        ubuntu|debian)
            curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
            apt-get install -y -q nodejs
            ;;
        centos|rhel|almalinux|rocky|alinux|anolis)
            curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
            if command -v dnf &>/dev/null; then
                dnf install -y nodejs
            else
                yum install -y nodejs
            fi
            ;;
        *)
            echo "  ✗ 无法自动安装 Node.js。请手动安装 Node.js 20 后重新运行。"
            exit 1
            ;;
    esac
fi
echo "  ✓ Node.js $(node --version)"

# ── 检查 .env 文件 ──────────────────────────────────────────────────────────────
echo ""
if [ ! -f ".env" ]; then
    echo "  ⚠ 未找到 .env 文件，从 .env.example 复制..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  ✓ 已创建 .env（请编辑并填入 API Key 后重新运行）"
        echo ""
        echo "  必填项："
        echo "    ANTHROPIC_API_KEY=sk-ant-..."
        echo "    EMBEDDING_API_KEY=sk-...   (OpenAI key，用于知识库向量化)"
        echo ""
        echo "  编辑完成后运行：  ./deploy.sh"
        exit 0
    else
        echo "  ✗ .env.example 也不存在，请手动创建 .env"
        exit 1
    fi
fi

# ── 1. Python 虚拟环境 + 依赖 ──────────────────────────────────────────────────
echo ""
echo "[1/4] Setting up Python virtual environment..."

VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON311" -m venv "$VENV_DIR"
    echo "  ✓ Created venv at $VENV_DIR"
else
    echo "  venv already exists, skipping creation"
fi

# 激活 venv
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

# 升级 pip
pip install --upgrade pip --quiet

echo "  Installing requirements..."
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --quiet
echo "  ✓ Python dependencies installed"

# ── 2. 前端构建 ────────────────────────────────────────────────────────────────
echo ""
echo "[2/4] Building frontend..."
if [ -d "web/frontend/node_modules" ]; then
    echo "  node_modules found, skipping npm install"
else
    (cd web/frontend && npm install --registry https://registry.npmmirror.com)
fi

if [ -d "web/frontend/dist" ] && [ "$(ls -A web/frontend/dist 2>/dev/null)" ]; then
    echo "  dist/ already exists, skipping build (delete dist/ to force rebuild)"
else
    (cd web/frontend && npm run build)
fi
echo "  ✓ Frontend ready"

# ── 3. 数据库初始化 + 迁移 ────────────────────────────────────────────────────
echo ""
echo "[3/4] Initializing database..."
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
    print("  Empty database detected — running seed scripts...")
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
    print(f"  Found {count} active agent(s) — skipping seed (data already present).")
PYEOF

# ── 4. 知识库向量索引（可选）─────────────────────────────────────────────────
echo ""
echo "[4/4] Knowledge base..."
if [ -d "knowledge/.chroma" ] && [ "$(ls -A knowledge/.chroma 2>/dev/null)" ]; then
    echo "  .chroma index already exists, skipping setup_kb.py"
    echo "  (delete knowledge/.chroma/ to force a full rebuild)"
else
    EMBEDDING_KEY=$(grep -E "^EMBEDDING_API_KEY=" .env 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)
    OAI_KEY=$(grep -E "^OPENAI_API_KEY=" .env 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)
    if [ -n "$EMBEDDING_KEY" ] || [ -n "$OAI_KEY" ]; then
        echo "  Building vector index from knowledge/ files..."
        python knowledge/setup_kb.py
        echo "  ✓ Knowledge base ready."
    else
        echo "  ⚠ EMBEDDING_API_KEY not set — skipping knowledge base setup."
        echo "    Agents will still work; only the search_knowledge_base tool will be unavailable."
        echo "    To enable KB later: set EMBEDDING_API_KEY in .env, then run:"
        echo "      source venv/bin/activate && python knowledge/setup_kb.py"
    fi
fi

# ── 启动服务器（systemd 托管，后台永久运行）────────────────────────────────────
echo ""
echo "[5/5] Installing systemd service..."

SERVICE_NAME="digital-employee"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON_BIN="$VENV_DIR/bin/python"

# 读取 .env 中的环境变量，写入 systemd EnvironmentFile 格式
ENV_FILE="$SCRIPT_DIR/.env"

cat > /tmp/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Digital Employee Platform
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$SCRIPT_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON_BIN web/server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 安装 service 文件（需要 root）
if [ "$(id -u)" -eq 0 ]; then
    cp /tmp/${SERVICE_NAME}.service "$SERVICE_FILE"
else
    sudo cp /tmp/${SERVICE_NAME}.service "$SERVICE_FILE"
fi

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

sleep 2
STATUS=$(sudo systemctl is-active "$SERVICE_NAME")
echo ""
echo "========================================="
if [ "$STATUS" = "active" ]; then
    echo " ✓ 服务已启动并设为开机自启"
    echo " 访问地址：http://$(hostname -I | awk '{print $1}'):8000"
else
    echo " ✗ 服务启动失败，查看日志："
    sudo journalctl -u "$SERVICE_NAME" -n 30 --no-pager
fi
echo ""
echo " 常用命令："
echo "   查看状态：sudo systemctl status $SERVICE_NAME"
echo "   查看日志：sudo journalctl -u $SERVICE_NAME -f"
echo "   重启服务：sudo systemctl restart $SERVICE_NAME"
echo "   停止服务：sudo systemctl stop $SERVICE_NAME"
echo "========================================="
