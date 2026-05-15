import { useState } from 'react'
import { X } from 'lucide-react'
import { useLang } from '../i18n.jsx'

const ROLES = [
  { id: 'QA',  label: 'QA',  labelZh: 'QA 测试',  emoji: '🔍', desc: 'Test case design, bug triage, regression, quality metrics', descZh: '用例设计、缺陷分析、回归测试、质量指标' },
  { id: 'Dev', label: 'Dev', labelZh: '研发',      emoji: '💻', desc: 'Code review, architecture, debugging, PR analysis',          descZh: '代码审查、架构设计、缺陷修复、PR 分析' },
  { id: 'PM',  label: 'PM',  labelZh: '产品',      emoji: '📋', desc: 'PRD writing, metrics analysis, sprint planning, OKRs',      descZh: '产品需求文档、数据分析、迭代规划、OKR' },
  { id: 'SRE', label: 'SRE', labelZh: '运维',      emoji: '🔧', desc: 'Incident response, capacity planning, SLO/SLI, runbooks',  descZh: '故障响应、容量规划、SLO/SLI、运维手册' },
  { id: 'PJ',  label: 'PJ',  labelZh: '项目',      emoji: '📅', desc: 'Sprint planning, risk management, stakeholder alignment',   descZh: '项目计划、风险管理、跨组对齐' },
]

const PRESETS_BY_ROLE = {
  QA: [
    { line: 'promotion', emoji: '🎫', name: 'Promotion QA',  nameZh: '促销 QA',  desc: 'Vouchers, coupons, discount rules, campaign management', descZh: '优惠券、折扣规则、活动管理' },
    { line: 'checkout',  emoji: '🛒', name: 'Checkout QA',   nameZh: '结算 QA',  desc: 'Cart, order placement, payment flow, address validation', descZh: '购物车、下单、支付流程' },
    { line: 'payment',   emoji: '💳', name: 'Payment QA',    nameZh: '支付 QA',  desc: 'Payment gateway, refunds, transaction idempotency',       descZh: '支付网关、退款、事务幂等性' },
    { line: 'logistics', emoji: '📦', name: 'Logistics QA',  nameZh: '物流 QA',  desc: 'Shipping, tracking, delivery, warehouse',                 descZh: '物流、配送、仓储管理' },
  ],
  Dev: [
    { line: 'backend',   emoji: '⚙️', name: 'Backend Dev',  nameZh: '后端研发', desc: 'APIs, databases, microservices, performance',    descZh: 'API 设计、数据库、微服务' },
    { line: 'frontend',  emoji: '🖥️', name: 'Frontend Dev', nameZh: '前端研发', desc: 'React/Vue, component architecture, Core Web Vitals', descZh: '组件架构、性能优化' },
    { line: 'mobile',    emoji: '📱', name: 'Mobile Dev',   nameZh: '移动研发', desc: 'iOS / Android, React Native, app performance',   descZh: 'iOS/Android、跨端开发' },
    { line: 'data',      emoji: '📊', name: 'Data Dev',     nameZh: '数据研发', desc: 'Data pipelines, SQL optimisation, ETL workflows', descZh: '数据管道、SQL 优化、ETL' },
  ],
  PM: [
    { line: 'growth',    emoji: '📈', name: 'Growth PM',    nameZh: '增长产品', desc: 'User acquisition, retention, A/B testing, funnels', descZh: '用户增长、A/B 测试、转化漏斗' },
    { line: 'platform',  emoji: '🗂️', name: 'Platform PM',  nameZh: '平台产品', desc: 'Developer tools, internal platforms, APIs',         descZh: '开发者工具、内部平台、API' },
    { line: 'checkout',  emoji: '🛒', name: 'Checkout PM',  nameZh: '结算产品', desc: 'Checkout funnel, payment experience, conversion',   descZh: '结算漏斗、支付体验' },
  ],
  SRE: [
    { line: 'platform',  emoji: '🔧', name: 'Platform SRE', nameZh: '平台运维', desc: 'Kubernetes, capacity planning, chaos engineering',   descZh: 'K8s、容量规划、混沌工程' },
    { line: 'payment',   emoji: '🛡️', name: 'Payment SRE',  nameZh: '支付运维', desc: 'Payment gateway reliability, transaction pipelines', descZh: '支付可靠性、事务管道' },
    { line: 'data',      emoji: '📊', name: 'Data SRE',     nameZh: '数据运维', desc: 'Database reliability, query performance, backups',   descZh: '数据库可靠性、查询优化' },
  ],
  PJ: [
    { line: 'platform',  emoji: '📋', name: 'Project Lead', nameZh: '技术项目经理', desc: 'Cross-team delivery, risk management, milestones',  descZh: '跨组交付、风险管理、里程碑' },
    { line: 'growth',    emoji: '📅', name: 'Growth PM/PJ', nameZh: '增长项目经理', desc: 'Campaign coordination, stakeholder alignment',       descZh: '活动协调、干系人对齐' },
  ],
}

export default function CreateAgentModal({ onClose, onCreate }) {
  const { t, lang } = useLang()
  const [step,      setStep]  = useState(1)   // 1=role, 2=preset, 3=configure
  const [selRole,   setRole]  = useState(null)
  const [form, setForm] = useState({
    name: '', product_line: '', avatar_emoji: '🤖',
    description: '', specialization: '',
    default_jira_project: '', confluence_spaces: [],
    role: 'QA',
  })

  function pickRole(r) {
    setRole(r)
    setForm(f => ({ ...f, role: r.id, avatar_emoji: r.emoji }))
    setStep(2)
  }

  function pickPreset(p) {
    const name = lang === 'zh' ? p.nameZh : p.name
    const desc = lang === 'zh' ? p.descZh : p.desc
    setForm(f => ({ ...f, name, product_line: p.line, avatar_emoji: p.emoji, description: desc }))
    setStep(3)
  }

  function handleSpaces(val) {
    setForm(f => ({ ...f, confluence_spaces: val.split(',').map(s => s.trim()).filter(Boolean) }))
  }

  function submit() {
    if (!form.name || !form.product_line) return
    onCreate(form)
  }

  const inputCls = "w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500 text-gray-900 dark:text-white placeholder-gray-400"

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl w-full max-w-lg border border-gray-200 dark:border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-800">
          <h2 className="font-bold text-lg text-gray-900 dark:text-white">
            {step === 1 ? t('modal.choose_role') :
             step === 2 ? t('modal.choose_spec') :
             `${t('modal.configure')} — ${form.name || '...'}`}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Step 1: Choose role */}
        {step === 1 && (
          <div className="p-5 space-y-2">
            {ROLES.map(r => (
              <button
                key={r.id}
                onClick={() => pickRole(r)}
                className="w-full flex items-center gap-4 p-3 rounded-xl bg-gray-50 dark:bg-gray-800 hover:border-blue-500 border border-gray-200 dark:border-gray-700 text-left transition-colors"
              >
                <span className="text-2xl">{r.emoji}</span>
                <div>
                  <p className="font-semibold text-gray-900 dark:text-white">
                    {lang === 'zh' ? r.labelZh : r.label}
                  </p>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">
                    {lang === 'zh' ? r.descZh : r.desc}
                  </p>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Step 2: Choose specialization */}
        {step === 2 && (
          <div className="p-5 space-y-2">
            {(PRESETS_BY_ROLE[selRole?.id] || []).map(p => (
              <button
                key={p.line}
                onClick={() => pickPreset(p)}
                className="w-full flex items-center gap-4 p-3 rounded-xl bg-gray-50 dark:bg-gray-800 hover:border-blue-500 border border-gray-200 dark:border-gray-700 text-left transition-colors"
              >
                <span className="text-2xl">{p.emoji}</span>
                <div>
                  <p className="font-semibold text-gray-900 dark:text-white">{lang === 'zh' ? p.nameZh : p.name}</p>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">{lang === 'zh' ? p.descZh : p.desc}</p>
                </div>
              </button>
            ))}
            <button
              onClick={() => setStep(3)}
              className="w-full p-3 rounded-xl bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 border border-dashed border-gray-400 dark:border-gray-600 text-gray-500 dark:text-gray-400 text-sm transition-colors"
            >
              {t('modal.custom_spec')}
            </button>
            <button onClick={() => setStep(1)} className="w-full py-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
              ← {t('modal.back')}
            </button>
          </div>
        )}

        {/* Step 3: Configure */}
        {step === 3 && (
          <div className="p-5 space-y-4">
            <div className="flex gap-3">
              <div>
                <label className="text-xs text-gray-500 dark:text-gray-400 mb-1 block">{t('modal.label.emoji')}</label>
                <input
                  value={form.avatar_emoji}
                  onChange={e => setForm(f => ({...f, avatar_emoji: e.target.value}))}
                  className="w-16 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-2 py-2 text-center text-xl outline-none focus:border-blue-500"
                />
              </div>
              <div className="flex-1">
                <label className="text-xs text-gray-500 dark:text-gray-400 mb-1 block">{t('modal.label.name')}</label>
                <input value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))}
                  placeholder={lang === 'zh' ? '促销 QA' : 'Promotion QA'} className={inputCls} />
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-500 dark:text-gray-400 mb-1 block">{t('modal.label.product')}</label>
              <input value={form.product_line} onChange={e => setForm(f => ({...f, product_line: e.target.value}))}
                placeholder="promotion" className={inputCls} />
            </div>
            <div>
              <label className="text-xs text-gray-500 dark:text-gray-400 mb-1 block">{t('modal.label.desc')}</label>
              <input value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))}
                placeholder={lang === 'zh' ? '简短介绍该员工的职责' : 'Short description'} className={inputCls} />
            </div>
            <div>
              <label className="text-xs text-gray-500 dark:text-gray-400 mb-1 block">{t('modal.label.spec')}</label>
              <textarea value={form.specialization} onChange={e => setForm(f => ({...f, specialization: e.target.value}))}
                placeholder={lang === 'zh' ? '描述该员工的领域专长…' : 'Describe domain expertise…'}
                rows={3} className={`${inputCls} resize-none`} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-500 dark:text-gray-400 mb-1 block">{t('modal.label.jira')}</label>
                <input value={form.default_jira_project} onChange={e => setForm(f => ({...f, default_jira_project: e.target.value}))}
                  placeholder="SPPT" className={inputCls} />
              </div>
              <div>
                <label className="text-xs text-gray-500 dark:text-gray-400 mb-1 block">{t('modal.label.confluence')}</label>
                <input value={form.confluence_spaces.join(', ')} onChange={e => handleSpaces(e.target.value)}
                  placeholder="PROMO, QA" className={inputCls} />
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => setStep(2)} className="flex-1 py-2.5 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-xl text-sm transition-colors">
                {t('modal.back')}
              </button>
              <button
                onClick={submit}
                disabled={!form.name || !form.product_line}
                className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-xl text-sm font-semibold transition-colors"
              >
                {t('modal.submit')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
