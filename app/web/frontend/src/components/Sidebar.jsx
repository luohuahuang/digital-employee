import { useState, useRef, useEffect } from 'react'
import { Link, useParams, useLocation } from 'react-router-dom'
import { Plus, Bot, BarChart2, ClipboardList, UserX, Users, FileText, ShieldCheck, TestTube2, Settings, Cpu } from 'lucide-react'
import { useLang } from '../i18n.jsx'

const RANKING_STYLE = {
  Intern:  'bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200',
  Junior:  'bg-blue-100 dark:bg-blue-700 text-blue-700 dark:text-blue-100',
  Senior:  'bg-green-100 dark:bg-green-700 text-green-700 dark:text-green-100',
  Lead:    'bg-yellow-100 dark:bg-yellow-600 text-yellow-700 dark:text-yellow-100',
}

const ROLE_STYLE = {
  QA:  'bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-200',
  Dev: 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200',
  PM:  'bg-orange-100 dark:bg-orange-900 text-orange-700 dark:text-orange-200',
  SRE: 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200',
  PJ:  'bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-200',
}

function RankingBadge({ ranking }) {
  const cls = RANKING_STYLE[ranking] || RANKING_STYLE.Intern
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0 ${cls}`}>
      {ranking || 'Intern'}
    </span>
  )
}

function RoleBadge({ role }) {
  const { t } = useLang()
  const cls = ROLE_STYLE[role] || ROLE_STYLE.QA
  return (
    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 ${cls}`}>
      {t(`role.${role}`) || role}
    </span>
  )
}

const ROLE_ORDER = ['QA', 'Dev', 'PM', 'SRE', 'PJ']

export default function Sidebar({ agents, groups, onNewAgent, onNewGroup }) {
  const { agentId, groupId } = useParams()
  const location = useLocation()
  const { t } = useLang()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)

  const onAudit          = location.pathname === '/audit'
  const onExams          = location.pathname === '/exams'
  const onTestSuites     = location.pathname === '/test-suites'
  const onTestPlatform   = location.pathname.startsWith('/test-platform')
  const onOffboard       = location.pathname === '/offboard'
  const onRolePrompts    = location.pathname === '/role-prompts'
  const onPermissions    = location.pathname === '/permissions'
  const onBrowserSkills  = location.pathname === '/browser-skills'
  const anyActive        = onAudit || onExams || onTestSuites || onTestPlatform || onOffboard || onRolePrompts || onPermissions || onBrowserSkills

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return
    function handleClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [menuOpen])

  // Close menu on route change
  useEffect(() => { setMenuOpen(false) }, [location.pathname])

  const grouped = {}
  for (const a of agents) {
    const r = a.role || 'QA'
    if (!grouped[r]) grouped[r] = []
    grouped[r].push(a)
  }
  const hasRoles = Object.keys(grouped).length > 1

  const menuItems = [
    { to: '/exams',          label: t('sidebar.exams'),          icon: ClipboardList, active: onExams          },
    { to: '/test-platform',  label: 'Test Platform',             icon: TestTube2,     active: onTestPlatform   },
    { to: '/audit',          label: t('sidebar.audit'),          icon: BarChart2,     active: onAudit          },
    { to: '/role-prompts',   label: t('sidebar.role_prompts'),   icon: FileText,      active: onRolePrompts    },
    { to: '/permissions',    label: t('sidebar.permissions'),    icon: ShieldCheck,   active: onPermissions    },
    { to: '/offboard',       label: t('sidebar.offboard'),       icon: UserX,         active: onOffboard       },
  ]

  return (
    <aside className="w-64 flex flex-col bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 shrink-0">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-blue-500 dark:text-blue-400" />
          <span className="font-bold text-gray-900 dark:text-white text-sm">{t('app.title')}</span>
        </div>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {agents.length === 0 && (
          <p className="text-gray-400 dark:text-gray-500 text-sm text-center py-8 px-4 whitespace-pre-line">
            {t('sidebar.no_agents')}
          </p>
        )}

        {hasRoles
          ? ROLE_ORDER.filter(r => grouped[r]).map(role => (
              <div key={role} className="mb-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider px-2 pt-2 pb-1 text-gray-400 dark:text-gray-500 flex items-center gap-1.5">
                  <RoleBadge role={role} />
                </p>
                {grouped[role].map(agent => (
                  <AgentLink key={agent.id} agent={agent} active={agentId === agent.id} />
                ))}
              </div>
            ))
          : agents.map(agent => (
              <AgentLink key={agent.id} agent={agent} active={agentId === agent.id} />
            ))
        }
      </div>

      {/* Group chats */}
      <div className="mx-2 mb-2 rounded-xl bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-100 dark:border-indigo-900/60 overflow-hidden">
        <div className="flex items-center gap-1.5 px-3 pt-2.5 pb-1">
          <Users className="w-3 h-3 text-indigo-400 dark:text-indigo-500" />
          <p className="flex-1 text-[10px] font-semibold text-indigo-400 dark:text-indigo-500 uppercase tracking-wider">
            {t('sidebar.group_chats')}
          </p>
          <button
            onClick={onNewGroup}
            title={t('sidebar.new_group')}
            className="w-4 h-4 flex items-center justify-center rounded text-indigo-400 dark:text-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 transition-colors"
          >
            <Plus className="w-3 h-3" />
          </button>
        </div>
        {groups && groups.length > 0 && (
          <div className="px-1 pb-1.5 space-y-0.5">
            {groups.map(g => (
              <Link
                key={g.id}
                to={`/group/${g.id}`}
                className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg transition-colors text-xs ${
                  groupId === g.id
                    ? 'bg-indigo-500 text-white'
                    : 'hover:bg-indigo-100 dark:hover:bg-indigo-900/60 text-gray-600 dark:text-gray-400'
                }`}
              >
                <span className="truncate">{g.title}</span>
                <span className="ml-auto shrink-0 text-[10px] opacity-50">{g.members?.length}p</span>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Bottom bar — Settings button + quick actions */}
      <div className="p-3 border-t border-gray-200 dark:border-gray-800 flex items-center gap-2" ref={menuRef}>

        {/* Settings popover trigger */}
        <div className="relative flex-1">
          <button
            onClick={() => setMenuOpen(v => !v)}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm ${
              menuOpen || anyActive
                ? 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white'
                : 'text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white'
            }`}
          >
            <Settings className="w-4 h-4 shrink-0" />
            <span>{t('sidebar.settings') || 'Settings'}</span>
          </button>

          {/* Popover */}
          {menuOpen && (
            <div className="absolute bottom-full left-0 mb-2 w-56 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 py-1.5 z-50">
              {menuItems.map(item => (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                    item.active
                      ? 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30'
                      : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
                >
                  <item.icon className="w-4 h-4 shrink-0" />
                  {item.label}
                </Link>
              ))}

              {/* Divider */}
              <div className="my-1.5 border-t border-gray-100 dark:border-gray-700" />

              <button
                onClick={() => { onNewAgent?.(); setMenuOpen(false) }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                <Plus className="w-4 h-4 shrink-0" />
                {t('sidebar.onboard')}
              </button>
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}

function AgentLink({ agent, active }) {
  return (
    <Link
      to={`/agent/${agent.id}`}
      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
        active
          ? 'bg-blue-600 text-white'
          : 'hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
      }`}
    >
      <span className="text-xl shrink-0">{agent.avatar_emoji}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <p className="font-medium truncate text-sm">{agent.name}</p>
          <RankingBadge ranking={agent.ranking} />
        </div>
        <p className={`text-xs truncate ${active ? 'text-blue-200' : 'text-gray-400 dark:text-gray-500'}`}>
          {agent.product_line}
        </p>
      </div>
    </Link>
  )
}
