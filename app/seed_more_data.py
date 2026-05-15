"""
seed_more_data.py — Rich demo data supplement.

Adds to ALL features that are currently thin:
  - Conversations: multi-turn for agents with 0 or sparse history
  - Test Suites: 4 new Shopee product lines
  - Group Chats: 2 new chats + richer messages
  - Prompt Suggestions: 4 new suggestions
  - Exam Runs: more runs for agents with few entries
  - Fix: set component='Promotion' on the orphan SPPT-97814 suite

Run from app/ directory: python3 seed_more_data.py
"""
import sqlite3, json, uuid
from datetime import datetime, timedelta
import random

DB_PATH = "web/de_team.db"

def ts(offset_days=0, offset_hours=0, offset_minutes=0):
    t = datetime.utcnow() - timedelta(
        days=offset_days, hours=offset_hours, minutes=offset_minutes)
    return t.strftime("%Y-%m-%d %H:%M:%S")

def uid(): return str(uuid.uuid4())

db = sqlite3.connect(DB_PATH)
db.execute("PRAGMA foreign_keys = ON")

# ── Fetch agent IDs ────────────────────────────────────────────────────────────
agents = {row[1]: {"id": row[0], "name": row[1], "pl": row[2], "role": row[3]}
          for row in db.execute(
              "SELECT id, name, product_line, role FROM agents WHERE is_active=1")}

def aid(name): return agents[name]["id"]

ALICE  = aid("Alice · Promo QA")
BOB    = aid("Bob · Checkout QA")
CAROL  = aid("Carol · Payment QA")
DAVID  = aid("David · Backend Dev")
EVA    = aid("Eva · Frontend Dev")
FRANK  = aid("Frank · Growth PM")
GRACE  = aid("Grace · Checkout PM")
HANK   = aid("Hank · Platform SRE")
IRIS   = aid("Iris · Payment SRE")
JACK   = aid("Jack · Project Lead")

# ══════════════════════════════════════════════════════════════════════════════
# 1. CONVERSATIONS
# ══════════════════════════════════════════════════════════════════════════════

def add_conv(agent_id, title, messages, offset_days=0):
    """Insert a conversation with a list of (role, content, tool_calls_json) tuples."""
    cid = uid()
    db.execute(
        "INSERT INTO conversations (id, agent_id, title, created_at) VALUES (?,?,?,?)",
        (cid, agent_id, title, ts(offset_days))
    )
    for i, (role, content, tools) in enumerate(messages):
        db.execute(
            """INSERT INTO messages
               (id, conversation_id, role, content, tool_calls_json, created_at)
               VALUES (?,?,?,?,?,?)""",
            (uid(), cid, role, content,
             json.dumps(tools, ensure_ascii=False) if tools else "[]",
             ts(offset_days, offset_minutes=-(len(messages)-i)*3))
        )

EXISTING_TITLES = {r[0] for r in db.execute("SELECT title FROM conversations").fetchall()}

CONVS = [

  # ── BOB · Checkout QA ───────────────────────────────────────────────────────
  ("Bob · Checkout QA", "分析 SPCT-5523 购物车并发超售风险", 3, [
    ("user", "SPCT-5523 — 11.11 大促期间购物车 add-to-cart 并发测试，帮我分析一下风险点", None),
    ("assistant",
     """已完成分析，以下是风险摘要：

---

## SPCT-5523 — 并发超售风险分析

**核心风险：Redis 库存锁与 MySQL 落库之间的竞态条件**

### 高优先级风险
| # | 风险 | 触发条件 | 建议 |
|---|------|----------|------|
| R1 | 超售 (oversell) | 高并发下乐观锁失效 | 改用 Lua script 原子扣减 |
| R2 | 重复扣库存 | 网络重试导致幂等失效 | 增加 idempotency_key 校验 |
| R3 | 缓存击穿 | 热门商品缓存过期瞬间 | 本地缓存 + mutex lock |

### 建议测试用例
1. 100 并发同时 add-to-cart 同一 SKU（库存=1）
2. 网络超时后客户端自动重试场景
3. Redis 主从切换期间的 add-to-cart

已将风险点保存至输出文件。需要我帮你设计完整的并发测试套件吗？""",
     [{"name": "get_jira_issue", "args": {"issue_key": "SPCT-5523"},
       "result": "Issue: SPCT-5523 | Add-to-cart concurrency oversell fix for 11.11 | Priority: P0 | Status: In Progress"}]
    ),
    ("user", "帮我生成一套并发测试的 test suite，保存到 DB", None),
    ("assistant",
     """测试套件已生成并保存！

**Suite ID**: checkout-concurrency-001
**Test Cases**: 8 条用例，涵盖 Happy Path、边界值、并发场景

主要用例：
- ✅ 单并发正常加购
- ✅ 10 并发抢购库存=1 的商品（期望只有 1 笔成功）
- ✅ 100 并发压测（期望无超售、无死锁）
- ✅ Redis 故障转移期间加购（期望降级到 DB 直读）
- ✅ 重试幂等性校验""",
     [{"name": "save_test_suite",
       "args": {"name": "Checkout — 并发加购压测 (SPCT-5523)", "component": "Checkout",
                "source_type": "jira", "jira_key": "SPCT-5523"},
       "result": "Test suite 'Checkout — 并发加购压测 (SPCT-5523)' saved with 8 test cases"}]
    ),
  ]),

  ("Bob · Checkout QA", "地址切换对运费的影响测试", 5, [
    ("user", "用户在 checkout 中途切换收货地址，运费计算会有问题吗？应该怎么测？", None),
    ("assistant",
     """这是一个经典的**状态同步**问题，值得重点测试。

## 核心风险点

**1. 运费未刷新**
地址切换后前端缓存旧运费，用户实际支付金额与显示不符。

**2. 分区运费错误**
从新加坡本地 → 国际地址切换时，运费区间判断可能走缓存路径。

**3. 免运费门槛重算**
原地址满足免运费条件 → 新地址不满足，但免运费 badge 仍显示。

## 建议测试覆盖

```
1. 本地 → 本地（同区） — 运费不变 ✓
2. 本地 → 本地（跨区，如 East → West） — 运费更新 ✓
3. 本地 → 国际 — 运费大幅变化，配送方式重置 ✓
4. 有免运费券 → 切换地址后券是否仍有效 ✓
5. 多 seller 下各 seller 运费独立刷新 ✓
```

需要我把这些整理成正式测试套件吗？""", None),
    ("user", "好的，另外 COD（货到付款）在切换地址后会有问题吗？", None),
    ("assistant",
     """好问题。COD 在地址切换场景下有几个特殊风险：

**COD 可用性判断依赖地址**
Shopee 的 COD 按配送区域支持，部分偏远地区不支持。
切换地址后，系统需要重新查询该地址是否支持 COD。

**已知风险**：
- 旧地址支持 COD → 切换到不支持 COD 的新地址后，COD 选项可能仍显示（已选中）
- 最终下单时后端拦截，但用户体验差（报错而非提前提示）

**补充测试用例**：
```
TC-COD-01: 支持 COD 地址 → 不支持 COD 地址，验证 COD 选项自动禁用
TC-COD-02: 已选 COD → 切换地址 → 验证支付方式重置为默认值
TC-COD-03: 不支持 COD 地址 → 支持 COD 地址，验证 COD 选项重新出现
```""", None),
  ]),

  ("Bob · Checkout QA", "券应用顺序与折扣叠加逻辑验证", 8, [
    ("user", "我需要验证：平台券 + seller券 + coins 同时使用时，折扣计算顺序是否正确。你有相关的知识库资料吗？", None),
    ("assistant",
     """找到相关规则，以下是汇总：

## 折扣叠加计算顺序

根据知识库文档，Shopee 的折扣计算顺序为：

```
原价
  → Seller 折扣（百分比 / 固定金额）
  → Seller 券（在 seller 小计上减扣）
  → 平台券（在 order 总价上减扣，设有 cap）
  → Coins 抵扣（上限为 order 总价的 10%）
  → 最终实付金额
```

**关键规则**：
- Coins 抵扣基于**平台券后的金额**，而非原价
- 平台券的 cap 以**平台券后金额**为基准
- Seller 券不影响平台券的 min spend 门槛（门槛以 seller 小计前计算）

## 测试边界场景

| 场景 | 期望 |
|------|------|
| Seller 券使 seller 小计低于免运费门槛 | 运费不再免除 |
| Coins 抵扣后实付 < SGD 0.01 | 自动置为 SGD 0.01（最小支付单位） |
| 平台券 cap = SGD 5，但计算得 SGD 4.8 | 实际减扣 SGD 4.8，不补齐到 cap |""",
     [{"name": "search_knowledge_base",
       "args": {"query": "voucher stacking rules discount calculation order"},
       "result": "Found 3 relevant chunks: promo_rules.txt — Voucher stacking policy, discount priority order, coins redemption cap"}]
    ),
    ("user", "如果我用 SPPT-97814 这个 jira，能找到相关的 test case 设计参考吗？", None),
    ("assistant",
     """已查询，SPPT-97814 主要是 mtime/ctime 修复的票，和折扣叠加逻辑关系不大。

不过我搜到了更相关的票：

**SPPT-89124 — Voucher stacking edge case regression**
- Priority: P1
- 描述：多 seller 场景下 platform 券 cap 计算有 off-by-one bug
- 已有回归用例 12 条

建议参考 SPPT-89124 的测试范围来补充你的叠加测试。需要我基于这个设计正式用例并保存到 DB 吗？""",
     [{"name": "search_jira",
       "args": {"jql": "project=SPPT AND text~'voucher stacking' ORDER BY updated DESC"},
       "result": "SPPT-89124: Voucher stacking edge case regression | P1 | 12 test cases documented"}]
    ),
  ]),

  # ── CAROL · Payment QA (extend existing) ────────────────────────────────────
  ("Carol · Payment QA", "PayNow 集成测试风险评估", 4, [
    ("user", "PayNow 和 ShopeePay 的集成测试，从支付 QA 角度最需要关注哪些风险？", None),
    ("assistant",
     """PayNow × ShopeePay 集成的核心测试风险如下：

## P0 风险（必测）

**1. 幂等性**
PayNow 是推送型支付，Shopee 端需通过 transaction_ref 做去重。
风险：网络超时后 MAS 侧已扣款，Shopee 侧因超时认为失败 → 重试 → 双扣。

**2. 金额一致性**
PayNow 结算精度为 SGD 到分（2位小数），
如果 Shopee 内部用浮点计算，可能出现 SGD 10.001 → 截断 → SGD 10.00 → 差额。

**3. 通知延迟**
MAS 规定 PayNow 到账通知最长 30 秒，
Shopee 订单状态需在收到 callback 前保持 `pending_payment`（不能超时取消）。

## P1 风险

| 风险 | 测试方法 |
|------|----------|
| 用户关闭银行 app 后的状态同步 | Mock callback 延迟 60s |
| PayNow 金额 cap（单笔 SGD 200k） | 边界值：SGD 199,999.99 / SGD 200,000.01 |
| 手机号 vs NRIC 不同绑定方式 | 分别测试两种 PayNow proxy type |

需要我把这些整理为完整测试套件保存到 DB 吗？""", None),
    ("user", "好的，另外 3DS v2 和 v1 的测试有什么区别？我们现在支持哪个版本？", None),
    ("assistant",
     """根据知识库，Shopee SG 目前**同时支持 3DS v1 和 v2**，由 card bin 和 issuing bank 决定走哪个版本。

## 3DS v1 vs v2 测试差异

| 维度 | 3DS v1 | 3DS v2 |
|------|--------|--------|
| 认证方式 | 重定向到 bank OTP 页面 | 内嵌 SDK，无跳转（friction-less flow） |
| Challenge flow | 总是有 OTP | 低风险交易可跳过（frictionless） |
| 超时处理 | 5 min，超时 → 用户手动重试 | 15 min session，SDK 内部处理 |
| 测试复杂度 | 简单，Mock redirect URL 即可 | 复杂，需模拟 ACS challenge / frictionless 两条路径 |

## 3DS v2 特有测试用例
1. **Frictionless flow**：低风险卡 → 跳过 OTP → 直接授权
2. **Challenge flow**：高风险交易 → 内嵌 OTP 弹窗 → 完成认证
3. **Decoupled authentication**：用户在另一设备完成认证
4. **3DS v2 降级到 v1**：当 issuing bank 不支持 v2 时的 fallback

建议优先覆盖 frictionless + challenge 两条主路径。""",
     [{"name": "search_knowledge_base",
       "args": {"query": "3DS authentication version payment"},
       "result": "Found: qa_standards.txt — 3DS v2 frictionless flow, challenge authentication, SG card issuer compatibility list"}]
    ),
  ]),

  ("Carol · Payment QA", "ShopeePay 退款幂等性测试", 6, [
    ("user", "我在看一个 P0 bug：refund API 被重复调用，导致用户被退了两次款。帮我分析测试覆盖缺口。", None),
    ("assistant",
     """这是一个经典的**幂等性漏洞**。以下是测试覆盖缺口分析：

## 根因分析

退款 API 重复调用一般有两种来源：
1. **客户端重试**：网络超时后自动重试，幂等 key 未正确传递
2. **平台重试机制**：后台任务发现退款状态为 pending → 重新触发

## 当前测试可能缺失的场景

| 场景 | 风险等级 |
|------|----------|
| 相同 refund_request_id 发送两次 | P0 |
| 第一次成功但 response 丢失 → 客户端重试 | P0 |
| 退款处理中（pending）时再次触发 | P0 |
| 退款已完成后再次调用 | P1 |
| 不同 request_id 对同一 order_id 退款 | P1 |

## 立即建议

**修复前**：在 refund API 层增加 `refund_request_id` 唯一性校验（DB 级 unique constraint）
**修复后**：重复调用相同 ID 应返回 `200 Already processed`，而非重新执行""", None),
    ("user", "这个 bug 应该提交 Jira，帮我起草一下", None),
    ("assistant",
     """已起草 Jira issue（待你确认后提交，需要 Mentor 审批）：

---

**Summary**: [P0] ShopeePay refund API lacks idempotency — duplicate refunds triggered on retry

**Priority**: P0 / Blocker

**Description**:
Refund API does not enforce idempotency on `refund_request_id`. When the client retries after a network timeout, a second refund transaction is created for the same order, resulting in double-refund to the user's ShopeePay balance.

**Steps to Reproduce**:
1. Initiate refund for order #ORDER-12345 (SGD 25.00)
2. Simulate network timeout (drop response before client receives 200)
3. Client auto-retries with same `refund_request_id`
4. Observe: two refund transactions created, user balance credited SGD 50.00

**Expected**: Second call returns `200 {"status": "already_processed", "refund_id": "..."}`
**Actual**: New refund transaction created; user double-refunded

**Fix Suggestion**: Add unique constraint on `refund_request_id` in `refund_transactions` table; return early if exists.

---

确认后我帮你提交到 Jira。""", None),
    ("user", "好的，帮我提交", None),
    ("assistant",
     """需要 Mentor 审批（L2 操作）。已发起审批请求：

**Issue Key**: SPB-78901（待审批后创建）
**Project**: SPB — ShopeePay Backend
**Assignee**: 待 Mentor 确认后自动分配给 Payment 后端 on-call

⏳ 等待 Mentor 批准中……""",
     [{"name": "create_jira_issue",
       "args": {"project": "SPB", "summary": "[P0] ShopeePay refund API lacks idempotency — duplicate refunds on retry",
                "priority": "Blocker", "description": "Duplicate refund on network retry..."},
       "result": "L2 approval required. Pending mentor review."}]
    ),
  ]),

  # ── EVA · Frontend Dev ───────────────────────────────────────────────────────
  ("Eva · Frontend Dev", "商品详情页 LCP 性能测试", 4, [
    ("user", "产品详情页（PDP）的 LCP 最近在 P95 超过了 3.5s，帮我分析一下前端测试策略", None),
    ("assistant",
     """PDP LCP 超标是常见的前端性能问题。以下是测试策略建议：

## LCP 超标根因排查优先级

**最可能的原因（按影响排序）**：
1. **主图懒加载配置错误** — 首屏主图应使用 `loading="eager"`，错用 `lazy` 会直接导致 LCP 延迟
2. **图片格式未优化** — 仍用 JPEG/PNG 而非 WebP/AVIF；P95 设备网络较差时影响显著
3. **Hero 区域 CSS 阻塞** — 首屏样式未内联，需等待外部 CSS 文件加载
4. **Server-side rendering 缺失** — PDP 依赖客户端 fetch 数据，首屏 HTML 空白

## 测试工具链建议

| 工具 | 用途 |
|------|------|
| Lighthouse CI | PR 门禁，LCP 超阈值自动 fail |
| WebPageTest | 真实网络模拟（3G/4G Slow） |
| Chrome DevTools Performance | 逐帧分析 LCP element |
| `PerformanceObserver` | RUM 数据采集，按设备/网络分组 |

## 快速定位

```javascript
// 在 DevTools Console 运行，找出 LCP element
new PerformanceObserver((list) => {
  list.getEntries().forEach(e => console.log('LCP element:', e.element, 'time:', e.startTime));
}).observe({type: 'largest-contentful-paint', buffered: true});
```

需要我帮你设计完整的前端性能测试用例清单吗？""", None),
    ("user", "好的。另外我想了解 React 18 并发渲染对测试有什么影响", None),
    ("assistant",
     """React 18 并发特性对测试有几个重要影响，需要更新你的测试策略：

## 主要变化

**1. `act()` 行为变化**
并发模式下，`act()` 需要 `await`，否则会漏掉异步状态更新。
```javascript
// ❌ React 17 写法（在 React 18 可能漏更新）
act(() => { fireEvent.click(button) });

// ✅ React 18 正确写法
await act(async () => { fireEvent.click(button) });
```

**2. `useTransition` 和 `useDeferredValue` 需要独立测试**
这两个 hook 会让某些更新"延迟渲染"，普通 snapshot 测试可能在过渡状态被截图。

**3. Suspense 边界测试**
并发模式下 Suspense fallback 的显示时机不固定，需要用 `waitFor` 而非固定延迟：
```javascript
// 等待 loading 消失
await waitFor(() => expect(screen.queryByText('Loading...')).not.toBeInTheDocument());
```

**4. StrictMode 双重渲染**
React 18 StrictMode 会故意渲染组件两次（开发模式），`useEffect` 也会执行两次。
如果测试依赖 useEffect 副作用次数，需要调整断言。

建议升级 `@testing-library/react` 到 v14+ 来获得原生 React 18 支持。""", None),
  ]),

  ("Eva · Frontend Dev", "A/B 测试组件接入评审", 7, [
    ("user", "我们在做新版购物车 UI 的 A/B 测试，实验组和对照组的 feature flag 由 GrowthBook 控制。帮我 review 一下测试方案", None),
    ("assistant",
     """A/B 测试接入需要关注以下几个维度：

## 1. 功能正确性

**A/B 分流逻辑**
- 确认 GrowthBook SDK 初始化时机（需在首屏渲染前完成，避免 flicker）
- 验证同一用户（user_id 固定）每次加载都分到相同实验组

**组件隔离**
- 实验组 UI 变化不应影响全局样式（CSS 命名空间隔离）
- 对照组和实验组共享的业务逻辑（加购、运费计算）不应有差异

## 2. 数据埋点验证

```javascript
// 确认实验曝光事件正确上报
expect(analytics.track).toHaveBeenCalledWith('experiment_viewed', {
  experiment_id: 'cart_ui_v2',
  variant: 'treatment',  // 或 'control'
  user_id: mockUserId
});
```

## 3. 边界场景

| 场景 | 风险 |
|------|------|
| GrowthBook SDK 加载失败 | 应降级到对照组（control），不能白屏 |
| 用户中途从实验组被剔除 | 购物车状态不应丢失 |
| SSR + CSR 水合时分组不一致 | 会导致 hydration mismatch 和 UI flicker |

## 4. 性能基准

A/B 两组都需要单独跑 Lighthouse，确保实验组 LCP 不劣化超过 200ms（否则可能影响实验结论）。

需要我帮你写具体的 Jest 测试用例吗？""", None),
    ("user", "帮我写一个测试：验证 GrowthBook 加载失败时，购物车默认显示对照组 UI", None),
    ("assistant",
     """以下是完整的测试用例：

```javascript
// cart.ab-fallback.test.jsx
import { render, screen } from '@testing-library/react';
import { GrowthBookProvider } from '@growthbook/growthbook-react';
import CartPage from './CartPage';

describe('A/B fallback when GrowthBook fails', () => {
  it('renders control variant when GrowthBook SDK fails to initialize', async () => {
    // Mock GrowthBook SDK failure
    jest.spyOn(console, 'error').mockImplementation(() => {});
    const failingGrowthBook = {
      ready: false,
      getFeatureValue: () => { throw new Error('SDK not initialized'); },
      isOn: () => false,  // fallback to off = control
    };

    const { container } = render(
      <GrowthBookProvider growthbook={failingGrowthBook}>
        <CartPage />
      </GrowthBookProvider>
    );

    // Control UI should be visible
    expect(screen.getByTestId('cart-v1-layout')).toBeInTheDocument();
    expect(screen.queryByTestId('cart-v2-layout')).not.toBeInTheDocument();

    // No error boundary triggered
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument();
  });

  it('does not lose cart items when switching from treatment to control', async () => {
    const mockCartItems = [
      { id: 'sku-001', name: 'Wireless Earbuds', qty: 1, price: 29.90 }
    ];

    // Start in treatment
    const { rerender } = render(
      <CartPage variant="treatment" cartItems={mockCartItems} />
    );
    expect(screen.getByText('Wireless Earbuds')).toBeInTheDocument();

    // Switch to control (simulates mid-session SDK failure)
    rerender(<CartPage variant="control" cartItems={mockCartItems} />);

    // Cart items should persist
    expect(screen.getByText('Wireless Earbuds')).toBeInTheDocument();
    expect(screen.getByText('SGD 29.90')).toBeInTheDocument();
  });
});
```

这两个用例覆盖了最关键的降级场景。需要我补充 SSR hydration mismatch 的测试吗？""", None),
  ]),

  # ── GRACE · Checkout PM ──────────────────────────────────────────────────────
  ("Grace · Checkout PM", "一键购功能的验收标准制定", 5, [
    ("user", "我们要推出一键购（Buy Now）功能，你帮我梳理一下验收标准应该包括哪些？", None),
    ("assistant",
     """一键购的验收标准（AC）需要从三个层次覆盖：

## 功能性 AC（P0）

```
AC-1: 用户点击「立即购买」后，应在 ≤ 2 秒内跳转到 checkout 页面
      — 地址已预填（默认地址）
      — 数量默认为 1
      — 商品为当前 PDP 已选的 variant

AC-2: 默认地址不存在时，弹出「添加地址」引导，不直接进入 checkout

AC-3: 商品库存 = 0 时，「立即购买」按钮置灰，不可点击

AC-4: 一键购跳过购物车，不写入 cart；
      验证：购物车商品数量不因此增加
```

## 支付兼容性 AC（P1）

```
AC-5: 支持全部已上线支付方式（ShopeePay / PayNow / 信用卡 / BNPL）
AC-6: 含优惠券/Coins 的订单可通过一键购完成（折扣正确叠加）
AC-7: Flash Sale 商品的一键购：优先使用 flash sale 价格
```

## 边缘 AC（P1）

```
AC-8: 同一商品同时打开两个 tab 各点一键购，不重复下单
AC-9: 会员专属商品：非会员用户点击一键购，显示会员购买引导，不进入 checkout
AC-10: 下单失败（库存竞争）：显示清晰错误，返回 PDP，不停留在空的 checkout
```

需要我帮你把这些整理成正式的 PRD AC 格式或 Jira 子任务吗？""", None),
    ("user", "目前 QA 的测试覆盖是否足够？我应该跟 Bob 对齐哪些测试重点？", None),
    ("assistant",
     """根据 Bob 现有的测试套件（Checkout — Order Placement 和 Cart Management），一键购场景目前还有以下覆盖缺口：

## 未覆盖的关键场景

| 场景 | AC # | 建议 |
|------|------|------|
| 一键购跳过购物车（Cart 不增加） | AC-4 | Bob 需要新增负向验证用例 |
| Flash Sale 商品的一键购价格 | AC-7 | 需要联合 Promo QA (Alice) 共同覆盖 |
| 并发一键购防重复下单 | AC-8 | Bob 现有并发套件（SPCT-5523）可延伸 |
| 非会员访问会员专属 | AC-9 | 目前无覆盖，需新增 |

## 建议对齐事项（跟 Bob）

1. **确认 AC-4 的测试方法**：需要 mock「绕过购物车」逻辑，直接验证 cart_items 表无新增
2. **与 Alice 联动**：Flash Sale 一键购涉及促销逻辑，建议 Bob + Alice 共同设计用例
3. **性能指标**：AC-1 要求 ≤ 2s 跳转，需要在 staging 环境跑基准测试确认

要我帮你起草跟 Bob 的对齐清单（可直接发群聊）吗？""", None),
  ]),

  ("Grace · Checkout PM", "Q4 大促 checkout 功能冻结评审", 6, [
    ("user", "我们下周要做 Q4 大促的 code freeze，checkout 相关的功能都测好了吗？帮我做个评估", None),
    ("assistant",
     """基于现有测试套件和对话记录，以下是 Checkout 功能的测试就绪度评估：

## ✅ 已充分覆盖

| 功能 | 覆盖情况 |
|------|----------|
| 标准下单流程 | ✅ 5 个 Happy Path 用例（含多 seller） |
| 购物车管理 | ✅ 6 个用例（库存上限、持久化、批量删除） |
| Voucher 叠加 | ✅ 6 个用例，含边界场景 |
| 并发加购 | ✅ 8 个并发测试用例（SPCT-5523） |

## ⚠️ 部分覆盖（需确认）

| 功能 | 缺口 |
|------|------|
| 一键购 | AC-4/8/9 未在测试套件中 |
| COD 地址切换 | 已在对话中设计，未保存为正式套件 |
| 地址切换运费重算 | 有设计，未入库 |

## ❌ 未覆盖

| 功能 | 优先级 | 建议 |
|------|--------|------|
| ShopeePay 支付路径 (checkout → pay) | P0 | 应在 code freeze 前完成 |
| 退款后重新下单 (order cancel → re-order) | P1 | 可推至 P1 修复期 |

**建议**：code freeze 前需要 Bob 补充 ShopeePay 路径覆盖，一键购缺口 AC-4/8/9 至少在 staging 验证完成。""", None),
    ("user", "ShopeePay 那部分是 Carol 负责的，我需要确认她的测试套件状态", None),
    ("assistant",
     """Carol 目前的测试套件状况：

**已有套件**（来自 Test Suites 页面）：
- **Payment — ShopeePay Wallet**：6 个用例，覆盖 top-up、PIN 验证、账户冻结
- **Payment — Credit Card & 3DS**：4 个用例

**Checkout ↔ ShopeePay 集成的覆盖缺口**：

Carol 的套件主要覆盖 ShopeePay 本身的操作，但 **Checkout → ShopeePay 支付这条路径**（即完整的 e2e 流程）还没有专门的套件。

建议 Grace 在和 Carol 的对齐会议中确认：

1. **`checkout_to_payment_handoff`** 是否在测试范围内
   > 即：checkout 页面发起支付请求 → ShopeePay 扣款 → 订单状态同步
2. **超时场景**：ShopeePay 响应超时 5s，checkout 是否正确显示「支付处理中」而非报错
3. **并发下单 + 同步扣款**：11.11 高并发下 ShopeePay 的限流是否已测

需要我帮你起草一个 Carol 对齐的 checklist 吗？""", None),
  ]),

  # ── IRIS · Payment SRE ───────────────────────────────────────────────────────
  ("Iris · Payment SRE", "ShopeePay 支付网关故障演练", 5, [
    ("user", "我们下周要做一次 ShopeePay 支付网关的 chaos engineering 演练，你帮我规划一下测试场景", None),
    ("assistant",
     """以下是 ShopeePay 支付网关 Chaos Engineering 演练规划：

## 演练目标

验证以下系统行为在支付网关异常时的表现：
1. 订单状态一致性（不出现永久 pending）
2. 用户体验降级（不白屏、不无响应）
3. 自动恢复（故障消除后流量自动切回）

## 推荐演练场景（按风险排序）

### Scenario 1: 网关响应超时（P0 必演）
```yaml
场景: ShopeePay API p99 延迟注入到 8000ms（正常 < 800ms）
持续: 5 分钟
预期:
  - 超过 3s 的请求触发 circuit breaker（半开状态）
  - 用户看到「支付处理中，请稍候」而非报错
  - 订单保持 pending_payment 状态，不自动取消
恢复验证:
  - 延迟恢复后 circuit breaker 在 30s 内重新闭合
  - 积压的 pending 订单通过后台任务自动完成
```

### Scenario 2: 完全不可用（P0 必演）
```yaml
场景: ShopeePay API 返回 503（模拟网关宕机）
持续: 2 分钟
预期:
  - 自动切换到备用支付方式提示（PayNow / 信用卡）
  - 不产生孤儿订单
  - 告警在 30s 内触发（PagerDuty alert）
```

### Scenario 3: 回调通知丢失（P1）
```yaml
场景: 支付成功但 callback 被丢弃（Kafka 消息丢失模拟）
预期:
  - Reconciliation job 在 5 分钟内发现差异
  - 订单状态从 pending → paid 自动修正
  - 不重复退款
```

## 演练前 Checklist
- [ ] 确认 staging 环境已隔离（不影响生产）
- [ ] PagerDuty 告警路由已配置
- [ ] 准备回滚 runbook（停止演练按钮）
- [ ] 联系 Carol 提供测试支付账号（有余额）

需要我帮你生成完整的 runbook 文档吗？""", None),
    ("user", "Scenario 1 的 circuit breaker 如何验证它在 30s 内恢复？", None),
    ("assistant",
     """以下是 circuit breaker 恢复时间的验证方法：

## 测量方法

**实时监控**（推荐）：
```bash
# 在演练期间持续采样 circuit breaker 状态
watch -n 5 'curl -s http://shopeepay-service:8080/actuator/health | jq .components.circuitBreaker'

# 输出示例
{
  "status": "OPEN",        # 故障期间
  "details": { "failureRate": "78.5%" }
}
# 恢复后变为
{
  "status": "CLOSED",
  "details": { "failureRate": "2.1%" }
}
```

**Prometheus 指标**：
```promql
# 查询 circuit breaker 状态变化时间线
resilience4j_circuitbreaker_state{name="shopeepay-gateway"}
```

## 30s 恢复的验证步骤

1. **T=0**：注入故障，记录 circuit breaker 进入 OPEN 状态的时间戳
2. **T=故障消除**：停止延迟注入，记录时间戳
3. **T=故障消除 + Xs**：观察 circuit breaker 进入 HALF_OPEN 状态
4. **T=故障消除 + Ys**：第一个探测请求成功后进入 CLOSED

**配置检查**（Spring Resilience4j 示例）：
```yaml
resilience4j.circuitbreaker:
  instances:
    shopeepay-gateway:
      waitDurationInOpenState: 10s      # OPEN → HALF_OPEN 等待时间
      permittedNumberOfCallsInHalfOpenState: 3  # 探测请求数
      slowCallDurationThreshold: 3000ms
```

如果 `waitDurationInOpenState: 10s`，加上探测完成时间，恢复时间应在 **15–20s** 之间，满足你的 30s 要求。

需要我把这个验证方法整理成一页演练 runbook 吗？""", None),
  ]),

  ("Iris · Payment SRE", "11.11 支付系统容量规划", 7, [
    ("user", "11.11 大促预计 GMV 是平日的 8 倍，支付系统容量怎么规划？", None),
    ("assistant",
     """以下是支付系统 11.11 容量规划框架：

## 1. 流量估算

**基准数据**（假设）：
- 平日峰值 TPS：1,200 TPS（支付请求）
- 11.11 倍数：GMV 8x → 支付 TPS 约 8,000–10,000 TPS（含抢购毛刺）
- 峰值时间：00:00–00:05（零点前 3 分钟开始排队）

**毛刺系数**：零点前 30s 内 TPS 可能达到 **2–3x 平均峰值**，即 ~20,000–25,000 TPS

## 2. 各层容量需求

| 层级 | 平日容量 | 11.11 需求 | 扩容方式 |
|------|----------|------------|----------|
| ShopeePay API servers | 12 pods | 80 pods | HPA + 提前手动预扩 |
| Payment DB（主） | 500 QPS | 4,000 QPS | 读写分离 + ProxySQL |
| Redis（余额缓存） | 20k ops/s | 160k ops/s | Redis Cluster 扩分片 |
| Kafka（支付回调） | 5k msg/s | 40k msg/s | 增加 partition 数 |

## 3. 限流策略

```
用户级：每秒最多 1 次支付请求（防刷单）
全局级：ShopeePay 总入口 QPS 上限 = 12,000（超出排队，不拒绝）
第三方网关：与 Stripe/PayNow 协商临时提升 rate limit 到 5,000 TPS
```

## 4. 大促前验收标准

- [ ] 压测：用 k6 跑 15,000 TPS 持续 5 分钟，p99 < 1s，错误率 < 0.1%
- [ ] Redis 内存水位：大促前 < 60%（预留 burst 空间）
- [ ] DB 连接池：最大连接数已调整为平日的 3x
- [ ] Circuit breaker 阈值：大促期间调高到 30%（避免误触发）

需要我帮你生成 k6 压测脚本吗？""", None),
    ("user", "支付成功率的 SLO 定义是什么？大促时应该怎么设？", None),
    ("assistant",
     """支付成功率 SLO 定义和大促调整建议：

## 标准 SLO 定义

```
指标: Payment Success Rate (PSR)
定义: (成功完成支付的请求数) / (所有发起支付的请求数) × 100%
  — 不包括用户主动取消
  — 包括网关超时、3DS 失败、余额不足导致的失败

平日 SLO: ≥ 98.5%（月度滚动窗口）
告警阈值: < 97%（触发 P2 告警）
重大事故线: < 95%（触发 P0 Incident）
```

## 大促期间调整建议

大促期间由于用户行为异常（重复点击、余额不足试错增加），**真实可控失败率更高**，建议：

| 指标 | 平日 SLO | 11.11 00:00–00:30 | 11.11 其余时段 |
|------|----------|-------------------|----------------|
| PSR | ≥ 98.5% | ≥ 95.0% | ≥ 97.0% |
| p99 响应时间 | ≤ 800ms | ≤ 2,000ms | ≤ 1,200ms |
| 错误率（5xx） | ≤ 0.1% | ≤ 0.5% | ≤ 0.2% |

## 需要区分的失败类型

```
可控失败（不计入 SLO 违约）:
  - 余额不足 (insufficient_balance)
  - 用户主动取消
  - 3DS OTP 超时（用户未操作）

不可控失败（计入 SLO）:
  - 网关 5xx 错误
  - 支付服务内部错误
  - 数据库连接失败
```

建议在 Grafana 大盘上把两类失败分开展示，避免大促时用户侧高试错率污染 SLO 数据。""", None),
  ]),
]

print("Adding conversations...")
added_conv = 0
for (agent_name, title, offset, messages) in CONVS:
    if title in EXISTING_TITLES:
        print(f"  SKIP (exists): {title[:50]}")
        continue
    add_conv(aid(agent_name), title, messages, offset_days=offset)
    print(f"  ✓ [{agent_name.split('·')[1].strip():<18}] {title[:55]}")
    added_conv += 1
db.commit()
print(f"  → {added_conv} conversations added\n")


# ══════════════════════════════════════════════════════════════════════════════
# 2. FIX: set component on the orphan SPPT-97814 suite
# ══════════════════════════════════════════════════════════════════════════════
db.execute(
    "UPDATE test_suites SET component='Promotion' WHERE name LIKE '%SPPT-97814%' AND (component='' OR component IS NULL)"
)
db.commit()
print("Fixed: SPPT-97814 suite component set to 'Promotion'\n")


# ══════════════════════════════════════════════════════════════════════════════
# 3. MORE TEST SUITES
# ══════════════════════════════════════════════════════════════════════════════

EXISTING_SUITE_NAMES = {r[0] for r in db.execute("SELECT name FROM test_suites")}

NEW_SUITES = [
  {
    "name": "Shopee Live — Stream Commerce",
    "description": "Test cases for Shopee Live streaming commerce: viewer experience, product showcase, in-stream purchasing, and streamer controls.",
    "component": "Shopee Live",
    "source_type": "jira",
    "jira_key": "SPLV-1088",
    "agent": (ALICE, "Alice · Promo QA"),
    "offset": 9,
    "cases": [
      {"title": "Viewer joins live stream and sees product showcase", "category": "Happy Path", "priority": "P0",
       "preconditions": "Streamer is live with at least 1 product pinned",
       "steps": ["Open Shopee app → Live tab", "Tap on an active stream", "Verify product showcase panel appears at bottom"],
       "expected": "Product name, price, and thumbnail visible in stream overlay; 'Buy Now' button active."},
      {"title": "In-stream purchase — tap Buy Now and complete checkout", "category": "Happy Path", "priority": "P0",
       "preconditions": "Viewer is watching live; product is in stock; user logged in",
       "steps": ["Tap product in showcase panel", "Tap 'Buy Now'", "Confirm default address and ShopeePay", "Place order"],
       "expected": "Order created at live-stream price; viewer remains in stream while checkout completes; order confirmation toast shown."},
      {"title": "Flash price in-stream lower than regular PDP price", "category": "Happy Path", "priority": "P1",
       "preconditions": "Streamer has set a live-exclusive price for the product",
       "steps": ["Note product price in live overlay", "Open same product in another tab (PDP)", "Compare prices"],
       "expected": "Live price ≤ PDP price; live price badge shows 'Live Exclusive'; live price applies at checkout."},
      {"title": "Concurrent viewers — limited stock purchase race", "category": "Boundary", "priority": "P0",
       "preconditions": "Product stock = 5; 50+ concurrent viewers attempt purchase simultaneously",
       "steps": ["Simulate 50 concurrent 'Buy Now' taps on the same product"],
       "expected": "Exactly 5 orders succeed; remaining viewers see 'Sold Out'; no oversell; no duplicate orders."},
      {"title": "Stream ends mid-checkout — order completion handling", "category": "Edge Case", "priority": "P1",
       "preconditions": "User has tapped Buy Now and is on checkout page",
       "steps": ["Streamer ends the stream while user is on checkout page"],
       "expected": "Checkout page remains functional; order can still be placed; in-stream price is honoured (not reverted to PDP price)."},
      {"title": "Product sold out notification during live", "category": "Edge Case", "priority": "P1",
       "preconditions": "Product becomes sold out while stream is active",
       "steps": ["Watch the product showcase panel when last unit is purchased by another viewer"],
       "expected": "'Sold Out' badge appears on product card within 3 seconds; Buy Now button disabled for remaining viewers."},
      {"title": "Streamer adds new product to showcase mid-stream", "category": "Regression", "priority": "P2",
       "preconditions": "Stream is live with 2 products already showcased",
       "steps": ["Streamer adds a 3rd product via seller app", "Viewer's showcase panel refreshes"],
       "expected": "New product appears in viewer's showcase within 5 seconds without page reload; existing products unaffected."},
    ]
  },
  {
    "name": "Shopee Coins — Earn, Redeem & Expiry",
    "description": "Test cases for Shopee Coins lifecycle: earning on purchases, redemption cap rules, expiry behaviour, and cashback conversions.",
    "component": "Promotion",
    "source_type": "manual",
    "agent": (ALICE, "Alice · Promo QA"),
    "offset": 11,
    "cases": [
      {"title": "Coins earned after order auto-completes", "category": "Happy Path", "priority": "P1",
       "preconditions": "Order status changes to 'Completed'; order is coins-eligible",
       "steps": ["Wait for order to auto-complete (7 days after delivery)",
                 "Navigate to Me → Shopee Coins → Transaction History"],
       "expected": "Coins credited within 24 hours of order completion; amount matches promotion rate (e.g., 1 coin per SGD 1 spent)."},
      {"title": "Coins redemption capped at 10% of order value", "category": "Boundary", "priority": "P0",
       "preconditions": "User has 5000 Coins (worth SGD 5); order total = SGD 20",
       "steps": ["At checkout, toggle 'Use Shopee Coins'"],
       "expected": "Maximum deduction shown as SGD 2.00 (10% of SGD 20), not SGD 5.00; total after coins = SGD 18.00."},
      {"title": "Coins cannot be used on non-eligible items", "category": "Edge Case", "priority": "P1",
       "preconditions": "Cart contains a coins-ineligible item (e.g., top-up voucher)",
       "steps": ["Toggle 'Use Shopee Coins' at checkout"],
       "expected": "Coins toggle shows as unavailable or greyed out with tooltip 'Coins not applicable for this item'."},
      {"title": "Expiring coins shown with countdown in wallet", "category": "Regression", "priority": "P2",
       "preconditions": "User has coins expiring within 7 days",
       "steps": ["Navigate to Me → Shopee Coins"],
       "expected": "Expiry warning banner shown; coins amount and exact expiry date/time displayed; banner dismissible."},
      {"title": "Expired coins deducted from balance automatically", "category": "Regression", "priority": "P1",
       "preconditions": "Coins with past expiry date exist in account",
       "steps": ["Log in the day after coins expiry", "Check Shopee Coins balance"],
       "expected": "Expired coins no longer in balance; transaction history shows 'Coins expired — SGD X.XX' entry with date."},
      {"title": "Cashback coins from promotion credited with correct delay", "category": "Happy Path", "priority": "P2",
       "preconditions": "User completed a purchase under a '5% Coins Cashback' campaign",
       "steps": ["Complete eligible order", "Wait for campaign-stated cashback window (typically 3–5 days)"],
       "expected": "Cashback coins credited within the stated window; amount = 5% of eligible spend × coins rate; entry visible in Coins history."},
    ]
  },
  {
    "name": "ShopeePay Later — BNPL Flow",
    "description": "Buy Now Pay Later feature: eligibility check, instalment plan selection, repayment, and overdue handling.",
    "component": "Payment",
    "source_type": "jira",
    "jira_key": "SPPL-2044",
    "agent": (CAROL, "Carol · Payment QA"),
    "offset": 6,
    "cases": [
      {"title": "Eligible user activates ShopeePay Later", "category": "Happy Path", "priority": "P0",
       "preconditions": "User meets eligibility criteria (age ≥ 21, SG resident, no outstanding overdue)",
       "steps": ["Navigate to ShopeePay → ShopeePay Later", "Tap 'Activate'",
                 "Complete identity verification (MyInfo / manual)", "Accept T&C"],
       "expected": "Account activated with initial credit limit shown; user redirected to ShopeePay Later dashboard."},
      {"title": "Select 3-month instalment plan at checkout", "category": "Happy Path", "priority": "P0",
       "preconditions": "ShopeePay Later activated; order total = SGD 150; within credit limit",
       "steps": ["Select ShopeePay Later at checkout", "Choose '3 months, 0% interest' plan",
                 "Review instalment schedule (SGD 50/month)", "Confirm order"],
       "expected": "Order placed; instalment plan created; first payment of SGD 50 due next month; confirmation email with schedule sent."},
      {"title": "Credit limit insufficient — user informed clearly", "category": "Edge Case", "priority": "P1",
       "preconditions": "Available credit limit = SGD 80; order total = SGD 200",
       "steps": ["Select ShopeePay Later at checkout"],
       "expected": "Error: 'Insufficient credit limit. Available: SGD 80.00'; option to use partial credit limit not available; user prompted to switch payment method."},
      {"title": "Overdue repayment blocks new ShopeePay Later purchases", "category": "Security", "priority": "P0",
       "preconditions": "User has an overdue instalment (past due date by 3+ days)",
       "steps": ["Attempt to use ShopeePay Later for a new purchase"],
       "expected": "ShopeePay Later option disabled at checkout; tooltip: 'Clear your overdue balance to continue using ShopeePay Later'."},
      {"title": "Repayment made — credit limit restored immediately", "category": "Happy Path", "priority": "P1",
       "preconditions": "User has used SGD 100 of credit limit",
       "steps": ["Navigate to ShopeePay Later → Make Payment", "Pay SGD 100 outstanding balance",
                 "Check available credit limit"],
       "expected": "Credit limit restored within 1 minute of payment confirmation; SGD 100 available again."},
      {"title": "Early full repayment — no penalty", "category": "Happy Path", "priority": "P2",
       "preconditions": "User on 6-month plan, pays full amount in month 2",
       "steps": ["Navigate to instalment plan", "Tap 'Pay in Full'", "Confirm full repayment"],
       "expected": "All remaining instalments cleared; no early repayment fee charged; plan status = 'Completed'; credit limit restored."},
      {"title": "Instalment payment reminder notification sent on due date", "category": "Integration", "priority": "P2",
       "preconditions": "User has an active instalment plan",
       "steps": ["Wait for push notification on instalment due date (D-3 and D-day)"],
       "expected": "Push notification received: 'Your ShopeePay Later payment of SGD X is due on [date]'; tap opens repayment screen."},
    ]
  },
  {
    "name": "Shopee Mall — Brand Store Compliance",
    "description": "Shopee Mall brand store validation: authenticity guarantees, SLA compliance, mall badge display, and return policy enforcement.",
    "component": "Product & Search",
    "source_type": "manual",
    "agent": (BOB, "Bob · Checkout QA"),
    "offset": 15,
    "cases": [
      {"title": "Shopee Mall badge visible on eligible seller products", "category": "Happy Path", "priority": "P1",
       "preconditions": "Seller is an approved Shopee Mall brand",
       "steps": ["Search for a product from a Mall brand", "View search results and PDP"],
       "expected": "Orange Shopee Mall badge displayed on product card and PDP; 'Official Store' label on seller profile."},
      {"title": "Mall product includes 15-day return guarantee", "category": "Happy Path", "priority": "P1",
       "preconditions": "Product is from Shopee Mall; order is within 15 days of delivery",
       "steps": ["View order details", "Initiate return request"],
       "expected": "Return option available for 15 days (vs 7 days for non-mall); banner: 'Shopee Mall 15-Day Returns'."},
      {"title": "Counterfeit claim triggers Mall authenticity review", "category": "Edge Case", "priority": "P0",
       "preconditions": "User believes received item is counterfeit",
       "steps": ["Navigate to order → 'Report Item'", "Select 'Item not authentic'",
                 "Upload proof photos (min 2)", "Submit report"],
       "expected": "Report submitted; user receives Shopee Mall guarantee confirmation; case escalated to Mall team within 24h; refund initiated if verified counterfeit."},
      {"title": "Mall seller SLA: ships within 2 business days", "category": "Regression", "priority": "P1",
       "preconditions": "Order placed with Shopee Mall seller on a weekday",
       "steps": ["Check order tracking after 2 business days"],
       "expected": "Order status shows 'Shipped' within 2 business days; if not, auto-compensation triggered (Shopee Coins or extended delivery SLA)."},
      {"title": "Non-Mall seller cannot display Mall badge", "category": "Security", "priority": "P0",
       "preconditions": "Seller is NOT enrolled in Shopee Mall program",
       "steps": ["Attempt to list product with Mall-related keywords in title",
                 "Check product listing after approval"],
       "expected": "Mall badge NOT shown on product; any misleading 'official' claims flagged and removed during moderation."},
    ]
  },
]

print("Adding test suites...")
added_suites = 0
for s in NEW_SUITES:
    if s["name"] in EXISTING_SUITE_NAMES:
        print(f"  SKIP (exists): {s['name'][:50]}")
        continue
    sid = uid()
    agent_id, agent_name = s["agent"]
    db.execute(
        """INSERT INTO test_suites
           (id, agent_id, agent_name, name, description, component,
            source_type, source_ref, jira_key, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, agent_id, agent_name, s["name"], s["description"],
         s["component"], s["source_type"], s.get("source_ref",""),
         s.get("jira_key",""), ts(s["offset"]), ts(s["offset"]))
    )
    for i, c in enumerate(s["cases"]):
        db.execute(
            """INSERT INTO test_cases
               (id,suite_id,title,category,preconditions,steps,expected,priority,order_index,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (uid(), sid, c["title"], c["category"], c["preconditions"],
             json.dumps(c["steps"], ensure_ascii=False),
             c["expected"], c["priority"], i, ts(s["offset"]), ts(s["offset"]))
        )
    print(f"  ✓ [{s['component']:<16}] {s['name']:<55} ({len(s['cases'])} cases)")
    added_suites += 1
db.commit()
print(f"  → {added_suites} test suites added\n")


# ══════════════════════════════════════════════════════════════════════════════
# 4. MORE GROUP CHATS
# ══════════════════════════════════════════════════════════════════════════════

EXISTING_GROUPS = {r[0] for r in db.execute("SELECT title FROM group_chats")}

def add_group(title, members, messages, offset_days=0):
    """members: list of (agent_id, name, emoji). messages: list of (speaker_type, speaker_id, name, emoji, content)."""
    gid = uid()
    db.execute("INSERT INTO group_chats (id, title, created_at) VALUES (?,?,?)",
               (gid, title, ts(offset_days)))
    for (aid_m, name_m, emoji_m) in members:
        db.execute("INSERT INTO group_memberships (id,group_id,agent_id,joined_at) VALUES (?,?,?,?)",
                   (uid(), gid, aid_m, ts(offset_days)))
    for i, (stype, sid_m, sname, semoji, content) in enumerate(messages):
        db.execute(
            """INSERT INTO group_messages
               (id,group_id,speaker_type,speaker_id,speaker_name,speaker_emoji,content,is_pass,created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (uid(), gid, stype, sid_m, sname, semoji, content, False,
             ts(offset_days, offset_minutes=-(len(messages)-i)*4))
        )

U = ("user", None, "Mentor", "👤")

GROUPS = [
  ("ShopeePay v3 — Architecture Review", 2, [
    (CAROL, "Carol · Payment QA", "🔍"), (IRIS, "Iris · Payment SRE", "🛡️"),
    (DAVID, "David · Backend Dev", "💻"), (JACK, "Jack · Project Lead", "🎯"),
  ], [
    U + ("ShopeePay v3 架构评审开始。Carol，请先给大家介绍 v3 的主要变化。",),
    ("agent",CAROL,"Carol · Payment QA","🔍",
     "ShopeePay v3 的核心变化有三点：\n\n**1. 支付核心分拆为微服务**\n原来的 monolith payment service 拆成：`balance-service`、`transaction-service`、`notification-service`，各自独立扩容。\n\n**2. 引入 Event Sourcing**\n所有余额变更通过 Kafka event 驱动，不再直接写 DB，便于审计和回放。\n\n**3. gRPC 替换 REST**\n内部服务间通信改为 gRPC（Protobuf），预计延迟降低 40%。\n\n从 QA 角度，最大的挑战是 event sourcing 的测试：需要验证事件顺序和幂等性。"),
    ("agent",DAVID,"David · Backend Dev","💻",
     "Event sourcing 引入后，测试复杂度会显著增加。我有几个技术问题：\n\n1. Kafka consumer group 的 offset 管理如何处理重复消费？\n2. `balance-service` 的 read model 重建（replay）有没有做过压测？大量历史事件回放可能很慢。\n3. gRPC 的 schema 版本管理（Protobuf breaking changes）如何 handle？"),
    ("agent",IRIS,"Iris · Payment SRE","🛡️",
     "从 SRE 角度，我关注以下运维风险：\n\n**Kafka lag 监控**：event sourcing 架构下，consumer lag 是核心 SLI。需要在 Grafana 上配置 lag > 5000 messages → P2 alert。\n\n**服务间 gRPC 超时**：建议每个服务的 gRPC call 设置不同的超时阈值：\n- balance-service → 500ms\n- transaction-service → 1000ms\n- notification-service → 2000ms（允许较慢）\n\n**Graceful shutdown**：微服务拆分后，rolling deploy 期间需要确保 in-flight 事务不丢失。"),
    U + ("David，对于 Kafka 重复消费的问题，你们方案是什么？",),
    ("agent",DAVID,"David · Backend Dev","💻",
     "我们计划用 **idempotency key** 方案：\n\n每个 Kafka message 携带 `event_id`（UUID），consumer 在处理前先查 Redis：\n```\nif redis.exists(f'processed:{event_id}'):\n    return  # 已处理，跳过\nprocess_event(event)\nredis.setex(f'processed:{event_id}', ttl=7*86400, value=1)\n```\n\nTTL 设为 7 天，覆盖 Kafka retention period。测试需要验证：同一 `event_id` 发送两次，余额只变化一次。"),
    ("agent",CAROL,"Carol · Payment QA","🔍",
     "这个方案可行，但我需要补充几个测试用例：\n\n1. Redis 宕机期间的 idempotency 降级策略（此时 Redis 查不到，是否直接处理？）\n2. `event_id` 碰撞测试（UUID4 碰撞概率极低，但需要明确处理策略）\n3. Kafka message 顺序保证：同一用户的事件必须顺序消费（partition key = user_id）\n\n已将这些测试场景记录到 ShopeePay v3 测试计划文档中。"),
    ("agent",JACK,"Jack · Project Lead","🎯",
     "很好的讨论。总结行动项：\n\n| Action | Owner | Due |\n|--------|-------|-----|\n| Kafka lag 监控配置 | Iris | Sprint 12 |\n| idempotency 测试用例入库 | Carol | Sprint 12 |\n| Protobuf breaking change 规范 | David | Sprint 11 |\n| v3 压测报告（replay 场景） | David + Iris | Sprint 13 |\n\n下次评审在 Sprint 13 开始前，届时应有压测初步结论。"),
  ]),

  ("Post-Mortem: 9.9 大促支付超时事故", 2, [
    (IRIS, "Iris · Payment SRE", "🛡️"), (CAROL, "Carol · Payment QA", "🔍"),
    (DAVID, "David · Backend Dev", "💻"), (HANK, "Hank · Platform SRE", "🔧"),
  ], [
    U + ("9.9 大促期间 00:12–00:28 出现支付超时，影响约 8,400 笔订单。Post-mortem 开始，请各方陈述。",),
    ("agent",IRIS,"Iris · Payment SRE","🛡️",
     "**事故时间线（UTC+8）**\n\n```\n00:00 — 大促正式开始，TPS 从 1,200 升至 7,800\n00:09 — payment-service p99 延迟开始升高（800ms → 2,100ms）\n00:12 — circuit breaker 触发，ShopeePay 支付开始返回 503\n00:14 — PagerDuty 告警触发（on-call: Iris）\n00:19 — 定位根因：payment DB 连接池耗尽（max_connections=200，实际需求 340+）\n00:23 — 紧急扩容 DB 连接池 → 400\n00:28 — 服务恢复，p99 回落到 650ms\n```\n\n**影响**：8,400 笔支付失败，估算损失 GMV ~SGD 420k。"),
    ("agent",DAVID,"David · Backend Dev","💻",
     "根因分析：**DB 连接池配置未随压测结论更新**\n\n压测（T-7天）时用的是 10,000 TPS 场景，连接池需求峰值是 280。我们按 1.5x 余量配置了 200（计算错误，应该是 280 × 1.5 = 420）。\n\n直接原因：配置计算公式用了错误的基数（用了平时 TPS 而非大促压测 TPS）。\n\n**已修复**：连接池调整为 500，并在 Terraform 中添加了注释说明计算依据，防止下次被错误修改。"),
    ("agent",CAROL,"Carol · Payment QA","🔍",
     "从 QA 角度的反思：\n\n**测试侧缺口**：\n1. 我们的负载测试验证了 API 响应，但没有专门监控 DB 连接池饱和点\n2. 压测 teardown 后没有检查 staging 配置与 prod 配置的一致性\n\n**改进建议**：\n- 大促前增加「配置一致性」检查项（staging prod diff）\n- 压测报告中显式列出「资源限制边界」（连接池、文件句柄、内存）\n- 增加 DB 连接池使用率的 pre-alert（> 70% → P3 预警）"),
    ("agent",HANK,"Hank · Platform SRE","🔧",
     "平台侧补充：这次事故暴露了我们的**大促前 checklist 不完整**。\n\n我已更新大促 runbook，新增以下检查项：\n```\n□ DB 连接池 max = 压测峰值连接数 × 2.0（而非 1.5）\n□ Redis 最大连接数 = TPS × 0.05（每笔支付约 0.05 次 Redis 操作）\n□ Kafka partition 数 ≥ consumer 数 × 3\n□ 大促前 1 小时运行 smoke test 确认连接池水位 < 40%\n```\n\n下次大促前我会 review 所有服务的连接池配置。"),
    U + ("很好。最后，这次事故的 MTTR 是 16 分钟，目标是 < 10 分钟。如何改善？",),
    ("agent",IRIS,"Iris · Payment SRE","🛡️",
     "MTTR 拆解：\n- 告警触发：5 min（00:09 开始异常，00:14 告警）— **改进：将 p99 > 1500ms 触发时间从 5min 改为 2min**\n- 根因定位：5 min（00:14–00:19）— 已在 Runbook 中加入「连接池饱和」排查步骤，预计缩短到 2min\n- 修复执行：4 min（00:19–00:23）— 已创建 Terraform 快速扩容脚本，预计缩短到 2min\n- 验证恢复：5 min（00:23–00:28）— 保持不变\n\n**改进后预计 MTTR：~7 min**，满足 < 10 min 目标。"),
  ]),
]

print("Adding group chats...")
added_groups = 0
for (title, offset, members, messages) in GROUPS:
    if title in EXISTING_GROUPS:
        print(f"  SKIP (exists): {title}")
        continue
    msgs_with_speaker = []
    for m in messages:
        if m[0] == "user":
            msgs_with_speaker.append(("user", None, "Mentor", "👤", m[-1]))
        else:
            msgs_with_speaker.append(m)
    add_group(title, members, msgs_with_speaker, offset_days=offset)
    print(f"  ✓ '{title}' ({len(messages)} messages)")
    added_groups += 1
db.commit()
print(f"  → {added_groups} group chats added\n")


# ══════════════════════════════════════════════════════════════════════════════
# 5. MORE PROMPT SUGGESTIONS
# ══════════════════════════════════════════════════════════════════════════════

# Find some exam run IDs to attach suggestions to
runs = {r[0]: r[1] for r in db.execute(
    "SELECT id, agent_id FROM exam_runs WHERE passed=0 ORDER BY created_at DESC LIMIT 20")}

def get_version_id(agent_id):
    r = db.execute(
        "SELECT id FROM prompt_versions WHERE agent_id=? AND is_active=1 LIMIT 1", (agent_id,)
    ).fetchone()
    return r[0] if r else None

# Only add if < 5 suggestions exist
existing_suggestions = db.execute("SELECT COUNT(*) FROM prompt_suggestions").fetchone()[0]
if existing_suggestions < 5:
    SUGGESTIONS = [
      {
        "agent_id": BOB,
        "diagnosis": "Agent fails to ask clarifying questions when test scope is ambiguous. In the flash_sale_concurrency exam, the agent jumped directly to test case design without confirming whether the requirement covers backend API testing, frontend UI testing, or both. This leads to incomplete coverage and wasted effort on out-of-scope cases.",
        "suggestions": [
          {"id": "s1", "point": "Add explicit scope confirmation step",
           "rationale": "Agent should always confirm test scope (API/UI/E2E) before designing cases for ambiguous requirements.",
           "patch": "Before designing test cases for any feature, explicitly ask: 1) Is the scope API-level, UI-level, or E2E? 2) Is this for regression or new functionality? 3) Are there existing test cases to extend?"},
          {"id": "s2", "point": "Reference known system boundaries in concurrency scenarios",
           "rationale": "Checkout concurrency involves Redis + DB + API layers; agent should explicitly call out each layer's test strategy.",
           "patch": "For concurrency-related features, structure the response as: Layer Analysis (Redis / DB / API) → Risk Assessment → Test Strategy per layer."},
        ],
        "patched_prompt": "You are a digital QA engineer specialising in Checkout. When designing test cases: 1) Always confirm scope before starting. 2) For concurrency scenarios, analyse Redis, DB, and API layers separately.",
      },
      {
        "agent_id": EVA,
        "diagnosis": "Agent does not distinguish between unit tests and integration tests when discussing testing strategies. In the dev_code_review exam, recommendations mixed unit test assertions with E2E browser testing steps, causing confusion about what tooling and test environment is needed.",
        "suggestions": [
          {"id": "s1", "point": "Explicitly label test level (unit/integration/E2E) for each recommendation",
           "rationale": "Mixing test levels in a single recommendation confuses the developer about what to implement first and what infrastructure is needed.",
           "patch": "Structure all testing recommendations with clear level labels: **Unit** (Jest/Vitest, no network), **Integration** (MSW or real API calls), **E2E** (Playwright/Cypress). Each section should list tools, expected runtime, and CI stage."},
        ],
        "patched_prompt": "You are a digital Frontend Dev. When reviewing code or suggesting tests, always classify recommendations by test level: Unit (isolated, fast, no network), Integration (mocked or real API), E2E (browser automation).",
      },
      {
        "agent_id": CAROL,
        "diagnosis": "Agent overlooks idempotency testing in payment scenarios. Multiple exam runs show the agent designing test cases for happy paths and basic error handling, but consistently missing the idempotency dimension (duplicate requests, network retries, callback replay).",
        "suggestions": [
          {"id": "s1", "point": "Add idempotency as a mandatory test dimension for all payment flows",
           "rationale": "Payment systems must handle network retries safely. Missing idempotency tests in exam cases suggests this is a systematic blind spot.",
           "patch": "For every payment flow test suite, include a mandatory 'Idempotency' category with at least: (1) duplicate request with same idempotency key, (2) retry after network timeout, (3) callback/webhook replay."},
          {"id": "s2", "point": "Include PCI-DSS scope in risk analysis",
           "rationale": "Payment QA should always note which test data is in-scope for PCI-DSS and how to handle card data in test environments.",
           "patch": "When designing payment test cases, add a 'PCI-DSS Note' section: identify which fields are sensitive (PAN, CVV), confirm test uses tokenised test cards only, flag any logging that might capture card data."},
        ],
        "patched_prompt": "You are a digital Payment QA engineer. For every payment flow: 1) Include an Idempotency test category. 2) Note PCI-DSS sensitive fields and use tokenised test data. 3) Cover network retry and callback replay scenarios.",
      },
      {
        "agent_id": ALICE,
        "diagnosis": "Agent's voucher test cases focus on single-seller scenarios but miss multi-seller edge cases. Promotion logic in multi-seller carts (where platform voucher applies to the order total but seller vouchers apply per-seller group) is consistently untested.",
        "suggestions": [
          {"id": "s1", "point": "Always include multi-seller cart in voucher test suites",
           "rationale": "Multi-seller carts are the most common source of voucher calculation bugs because discount scoping rules differ between platform and seller levels.",
           "patch": "Every voucher test suite must include at least one multi-seller scenario: (1) platform voucher on cart with 2+ sellers, (2) seller A voucher not applied to seller B items, (3) free-shipping voucher applied per-seller vs per-order."},
          {"id": "s2", "point": "Test voucher calculation order explicitly",
           "rationale": "The order of discount application (seller discount → seller voucher → platform voucher → coins) affects the final price, especially for percentage-based vouchers.",
           "patch": "For each voucher test case, include an explicit 'calculation trace' in the expected result: e.g., 'Original: SGD 30.00 → Seller 10%: SGD 27.00 → Platform voucher: SGD 22.00 → Final: SGD 22.00'."},
        ],
        "patched_prompt": "You are a digital Promotion QA engineer. Every voucher/promotion test suite must: 1) Include multi-seller cart scenarios. 2) Show explicit calculation traces in expected results. 3) Cover coins-on-top-of-voucher edge cases.",
      },
    ]

    run_ids = list(runs.keys())
    for i, sug in enumerate(SUGGESTIONS):
        run_id = run_ids[i] if i < len(run_ids) else run_ids[0]
        version_id = get_version_id(sug["agent_id"])
        db.execute(
            """INSERT INTO prompt_suggestions
               (id, run_id, agent_id, prompt_version_id, diagnosis, suggestions_json,
                patched_prompt, applied, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (uid(), run_id, sug["agent_id"], version_id,
             sug["diagnosis"],
             json.dumps(sug["suggestions"], ensure_ascii=False),
             sug["patched_prompt"], False, ts(i * 3 + 1))
        )
    db.commit()
    print(f"Added {len(SUGGESTIONS)} prompt suggestions\n")
else:
    print(f"Prompt suggestions already at {existing_suggestions}, skipping\n")


# ══════════════════════════════════════════════════════════════════════════════
# Final summary
# ══════════════════════════════════════════════════════════════════════════════
db.close()
db = sqlite3.connect(DB_PATH)
print("=" * 55)
print("Final row counts:")
for t in ["conversations","messages","test_suites","test_cases",
          "group_chats","group_messages","prompt_suggestions","exam_runs"]:
    n = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t:<30} {n:>5}")
db.close()
print("=" * 55)
print("Done.")
