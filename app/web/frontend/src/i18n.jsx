/**
 * Minimal i18n for Digital Employee.
 * Usage: const { t, lang, setLang } = useLang()
 */

export const TRANSLATIONS = {
  en: {
    // Sidebar
    'app.title':              'Digital Employee',
    'sidebar.no_agents':      'No digital employees yet.\nClick + to onboard one.',
    'sidebar.group_chats':    'Group Chats',
    'sidebar.exams':          'Evaluation Platform',
    'sidebar.audit':          'Audit Log',
    'sidebar.offboard':       'Offboard Records',
    'sidebar.role_prompts':   'Role Prompts',
    'sidebar.permissions':    'Permissions',
    'sidebar.new_group':      'New Group Chat',
    'sidebar.onboard':        'Onboard Employee',
    'sidebar.settings':       'Settings',
    // Role labels
    'role.QA':  'QA',
    'role.Dev': 'Dev',
    'role.PM':  'PM',
    'role.SRE': 'SRE',
    'role.PJ':  'PJ',
    // Welcome screen
    'welcome.title':             'Digital Employee Platform',
    'welcome.subtitle':          'AI-powered digital employees for QA, Dev, PM, SRE, and PJ. Each employee is specialized for a domain and learns from every interaction.',
    'welcome.cta':               '+ Onboard your first employee',
    'welcome.subtitle.has_agents': 'Select an employee from the sidebar to start chatting, or onboard a new one.',
    'welcome.cta.has_agents':    '+ Onboard new employee',
    // CreateAgentModal
    'modal.onboard.title':    'Onboard Digital Employee',
    'modal.choose_role':      'Choose Role',
    'modal.choose_spec':      'Choose Specialization',
    'modal.configure':        'Configure',
    'modal.back':             'Back',
    'modal.submit':           'Onboard Employee',
    'modal.label.emoji':      'Emoji',
    'modal.label.name':       'Name *',
    'modal.label.product':    'Product Line *',
    'modal.label.desc':       'Description',
    'modal.label.spec':       'Domain Specialization',
    'modal.label.jira':       'Default Jira Project',
    'modal.label.confluence': 'Confluence Spaces',
    'modal.custom_spec':      '+ Custom specialization',
    // ChatView
    'chat.new_conv':          'New Conversation',
    'chat.conversations':     'Conversations',
    'chat.placeholder':       'Ask your digital employee…',
    'chat.send':              'Send',
    'chat.offboard':          'Offboard',
    'chat.promote':           'Promote',
    'chat.thinking':          'Thinking…',
    'chat.l2_approval':       'Approve L2 Tool Call?',
    'chat.approve':           'Approve',
    'chat.reject':            'Reject',
    // AuditPanel
    'audit.title':            'Audit Log',
    'audit.health':           'Health Score',
    'audit.p95':              'P95 Latency',
    'audit.error_trend':      'Error Trend',
    'audit.quality':          'Avg Quality',
    'audit.filters':          'Filters',
    'audit.all_agents':       'All agents',
    'audit.all_tools':        'All tools',
    'audit.all_events':       'All events',
    'audit.trace_view':       'Trace View',
    'audit.close':            'Close',
    // ExamPanel
    'exam.title':             'Evaluation Platform',
    'exam.run':               'Run Evaluation',
    'exam.history':           'History',
    'exam.score':             'Score',
    'exam.passed':            'Passed',
    'exam.failed':            'Failed',
    // OffboardPanel
    'offboard.title':         'Offboard Records',
    'offboard.empty':         'No offboarded employees.',
    // Common
    'common.loading':         'Loading…',
    'common.error':           'Error',
    'common.save':            'Save',
    'common.cancel':          'Cancel',
    'common.confirm':         'Confirm',
    'common.search':          'Search',
    'common.filter':          'Filter',
    'common.refresh':         'Refresh',
  },

  zh: {
    // Sidebar
    'app.title':              '数字员工平台',
    'sidebar.no_agents':      '暂无数字员工。\n点击 + 来入职一名。',
    'sidebar.group_chats':    '群聊',
    'sidebar.exams':          '评测平台',
    'sidebar.audit':          '审计日志',
    'sidebar.offboard':       '离职记录',
    'sidebar.role_prompts':   'Role Prompts',
    'sidebar.permissions':    '权限管理',
    'sidebar.new_group':      '新建群聊',
    'sidebar.onboard':        '入职员工',
    'sidebar.settings':       '设置',
    // Role labels
    'role.QA':  'QA 测试',
    'role.Dev': '研发',
    'role.PM':  '产品',
    'role.SRE': '运维',
    'role.PJ':  '项目',
    // Welcome screen
    'welcome.title':             '数字员工平台',
    'welcome.subtitle':          'AI 驱动的数字员工，覆盖 QA、研发、产品、运维和项目管理。每位员工专注于特定领域，并从每次交互中持续学习。',
    'welcome.cta':               '+ 入职第一位数字员工',
    'welcome.subtitle.has_agents': '从侧边栏选择一位员工开始对话，或入职新员工。',
    'welcome.cta.has_agents':    '+ 入职新员工',
    // CreateAgentModal
    'modal.onboard.title':    '入职数字员工',
    'modal.choose_role':      '选择角色',
    'modal.choose_spec':      '选择专业方向',
    'modal.configure':        '配置信息',
    'modal.back':             '返回',
    'modal.submit':           '确认入职',
    'modal.label.emoji':      '图标',
    'modal.label.name':       '姓名 *',
    'modal.label.product':    '业务线 *',
    'modal.label.desc':       '简介',
    'modal.label.spec':       '领域专长',
    'modal.label.jira':       '默认 Jira 项目',
    'modal.label.confluence': 'Confluence 空间',
    'modal.custom_spec':      '+ 自定义专长',
    // ChatView
    'chat.new_conv':          '新建对话',
    'chat.conversations':     '对话记录',
    'chat.placeholder':       '向数字员工提问…',
    'chat.send':              '发送',
    'chat.offboard':          '离职',
    'chat.promote':           '晋升',
    'chat.thinking':          '思考中…',
    'chat.l2_approval':       '审批 L2 工具调用？',
    'chat.approve':           '批准',
    'chat.reject':            '拒绝',
    // AuditPanel
    'audit.title':            '审计日志',
    'audit.health':           '健康评分',
    'audit.p95':              'P95 延迟',
    'audit.error_trend':      '错误趋势',
    'audit.quality':          '平均质量',
    'audit.filters':          '筛选',
    'audit.all_agents':       '全部员工',
    'audit.all_tools':        '全部工具',
    'audit.all_events':       '全部事件',
    'audit.trace_view':       '链路视图',
    'audit.close':            '关闭',
    // ExamPanel
    'exam.title':             '评测平台',
    'exam.run':               '发起评测',
    'exam.history':           '历史记录',
    'exam.score':             '分数',
    'exam.passed':            '通过',
    'exam.failed':            '未通过',
    // OffboardPanel
    'offboard.title':         '离职记录',
    'offboard.empty':         '暂无离职记录。',
    // Common
    'common.loading':         '加载中…',
    'common.error':           '错误',
    'common.save':            '保存',
    'common.cancel':          '取消',
    'common.confirm':         '确认',
    'common.search':          '搜索',
    'common.filter':          '筛选',
    'common.refresh':         '刷新',
  },
}

import { createContext, useContext, useState } from 'react'

const LangContext = createContext(null)

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(() => {
    try { return localStorage.getItem('de_lang') || 'en' } catch { return 'en' }
  })

  function setLang(l) {
    setLangState(l)
    try { localStorage.setItem('de_lang', l) } catch {}
  }

  function t(key) {
    return TRANSLATIONS[lang]?.[key] ?? TRANSLATIONS['en']?.[key] ?? key
  }

  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>
}

export function useLang() {
  return useContext(LangContext)
}
