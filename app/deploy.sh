#!/usr/bin/env bash
# =============================================================================
# deploy.sh — 首次部署 / 环境重置脚本
# 适用场景：AWS EC2、本地重置、全新环境搭建
#
# 用法（从 app/ 目录执行）：
#   chmod +x deploy.sh
#   ./deploy.sh
#
# 功能：
#   1. 安装 Python 依赖
#   2. 构建前端
#   3. 初始化 / 迁移数据库（如果 de_team.db 已在 git 中，此步骤跳过重建）
#   4. （可选）重建知识库向量索引 —— 需要 EMBEDDING_MODEL API Key
#   5. 启动服务器
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo " Digital Employee — Deploy"
echo "========================================="

# ── 1. Python 依赖 ─────────────────────────────────────────────────────────────
echo ""
echo "[1/4] Installing Python dependencies..."
pip install -r requirements.txt --quiet

# ── 2. 前端构建 ────────────────────────────────────────────────────────────────
echo ""
echo "[2/4] Building frontend..."
if [ -d "web/frontend/node_modules" ]; then
    echo "  node_modules found, skipping npm install"
else
    (cd web/frontend && npm install)
fi

if [ -d "web/frontend/dist" ] && [ "$(ls -A web/frontend/dist)" ]; then
    echo "  dist/ already exists, skipping build (delete dist/ to force rebuild)"
else
    (cd web/frontend && npm run build)
fi

# ── 3. 数据库初始化 + 迁移 ────────────────────────────────────────────────────
echo ""
echo "[3/4] Initializing database..."
python3 - <<'PYEOF'
import sys, os
sys.path.insert(0, '.')
from web.db.database import init_db
init_db()
print("  Database ready.")

# If db was freshly created (no agents yet), run all seed scripts
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
if [ -d "knowledge/.chroma" ] && [ "$(ls -A knowledge/.chroma)" ]; then
    echo "  .chroma index already exists, skipping setup_kb.py"
    echo "  (delete knowledge/.chroma/ to force a full rebuild)"
else
    # KB embedding requires OpenAI API specifically (text-embedding-3-small)
    if [ -z "$OPENAI_API_KEY" ]; then
        echo "  ⚠ OPENAI_API_KEY not set — skipping knowledge base setup."
        echo "    Agents will still work; only the search_knowledge_base tool will be unavailable."
        echo "    To enable KB later: set OPENAI_API_KEY in .env, then run:"
        echo "      python knowledge/setup_kb.py"
    else
        echo "  Building vector index from knowledge/ files..."
        python knowledge/setup_kb.py
        echo "  Knowledge base ready."
    fi
fi

# ── 启动服务器 ─────────────────────────────────────────────────────────────────
echo ""
echo "========================================="
echo " Starting server..."
echo "========================================="
python web/server.py
