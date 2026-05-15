import { useState, useEffect, useRef } from 'react'
import { Routes, Route, useNavigate, Navigate, Link, useLocation } from 'react-router-dom'
import { Sun, Moon, Pencil, Check, ClipboardList, TestTube2, BarChart2, FileText, ShieldCheck, UserX, BookOpen, Menu } from 'lucide-react'
import Sidebar from './components/Sidebar.jsx'
import ChatView from './components/ChatView.jsx'
import CreateAgentModal from './components/CreateAgentModal.jsx'
import AuditPanel from './components/AuditPanel.jsx'
import ExamPanel from './components/ExamPanel.jsx'
import TestSuitePanel from './components/TestSuitePanel.jsx'
import TestPlatform from './components/TestPlatform.jsx'
import OffboardPanel from './components/OffboardPanel.jsx'
import RolePromptsPanel from './components/RolePromptsPanel.jsx'
import PermissionPanel from './components/PermissionPanel.jsx'
import GroupChatView from './components/GroupChatView.jsx'
import CreateGroupModal from './components/CreateGroupModal.jsx'
import TestRunView from './components/TestRunView.jsx'
import BrowserSkillsPanel from './components/BrowserSkillsPanel.jsx'
import { agentApi, groupApi } from './api/client.js'
import toast from 'react-hot-toast'
import { LangProvider, useLang } from './i18n.jsx'
import { ThemeProvider, useTheme } from './ThemeContext.jsx'

const ALL_SHORTCUTS = [
  { id: 'exams',         label: 'Evaluation',    to: '/exams',         icon: ClipboardList },
  { id: 'test-platform', label: 'Test Platform',  to: '/test-platform', icon: TestTube2     },
  { id: 'audit',         label: 'Audit Log',      to: '/audit',         icon: BarChart2     },
  { id: 'role-prompts',  label: 'Role Prompts',   to: '/role-prompts',  icon: FileText      },
  { id: 'permissions',   label: 'Permissions',    to: '/permissions',   icon: ShieldCheck   },
  { id: 'offboard',      label: 'Offboard',       to: '/offboard',      icon: UserX         },
]

const DEFAULT_SHORTCUTS = ['exams', 'test-platform']

function BookmarkBar() {
  const location = useLocation()
  const [active, setActive] = useState(() => {
    try { const s = localStorage.getItem('nav_bookmarks'); return s ? JSON.parse(s) : DEFAULT_SHORTCUTS } catch { return DEFAULT_SHORTCUTS }
  })
  const [editing, setEditing] = useState(false)
  const popoverRef = useRef(null)

  useEffect(() => {
    try { localStorage.setItem('nav_bookmarks', JSON.stringify(active)) } catch {}
  }, [active])

  useEffect(() => {
    if (!editing) return
    function handler(e) {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) setEditing(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [editing])

  const toggle = id => setActive(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  const shortcuts = ALL_SHORTCUTS.filter(s => active.includes(s.id))

  return (
    <div className="flex items-center gap-0.5" ref={popoverRef}>
      {shortcuts.map(s => {
        const isActive = location.pathname === s.to || location.pathname.startsWith(s.to + '/')
        return (
          <Link
            key={s.id}
            to={s.to}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
              isActive
                ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white'
            }`}
          >
            <s.icon className="w-3.5 h-3.5 shrink-0" />
            <span>{s.label}</span>
          </Link>
        )
      })}

      {/* Edit button */}
      <div className="relative ml-0.5">
        <button
          onClick={() => setEditing(v => !v)}
          className={`p-1.5 rounded-lg transition-colors ${
            editing
              ? 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
              : 'text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
          }`}
          title="Edit shortcuts"
        >
          <Pencil className="w-3 h-3" />
        </button>

        {editing && (
          <div className="absolute top-full right-0 mt-1 w-44 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 py-1.5 z-50">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 px-3 pb-1.5">
              Shortcuts
            </p>
            {ALL_SHORTCUTS.map(s => (
              <button
                key={s.id}
                onClick={() => toggle(s.id)}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 transition-colors ${
                  active.includes(s.id)
                    ? 'bg-blue-500 border-blue-500'
                    : 'border-gray-300 dark:border-gray-600'
                }`}>
                  {active.includes(s.id) && <Check className="w-2.5 h-2.5 text-white" />}
                </div>
                <s.icon className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 shrink-0" />
                <span>{s.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function InnerApp() {
  const [agents,      setAgents]      = useState([])
  const [groups,      setGroups]      = useState([])
  const [showCreate,  setShowCreate]  = useState(false)
  const [showGroup,   setShowGroup]   = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const navigate  = useNavigate()
  const { dark, setDark } = useTheme()
  const { lang, setLang, t } = useLang()

  useEffect(() => { loadAgents(); loadGroups() }, [])

  async function loadAgents() {
    try { setAgents(await agentApi.list()) }
    catch { toast.error('Failed to load agents') }
  }

  async function loadGroups() {
    try { setGroups(await groupApi.list()) }
    catch {}
  }

  async function handleCreate(data) {
    try {
      const agent = await agentApi.create(data)
      setAgents(prev => [...prev, agent])
      setShowCreate(false)
      toast.success(`${agent.name} joined the team!`)
      navigate(`/agent/${agent.id}`)
    } catch { toast.error('Failed to create agent') }
  }

  async function handleCreateGroup(data) {
    try {
      const g = await groupApi.create(data)
      setGroups(prev => [g, ...prev])
      setShowGroup(false)
      navigate(`/group/${g.id}`)
      toast.success('Group chat created!')
    } catch { toast.error('Failed to create group chat') }
  }

  async function handleOffboard(agentId) {
    try {
      const agent = await agentApi.offboard(agentId)
      setAgents(prev => prev.filter(a => a.id !== agentId))
      navigate('/')
      toast.success(`${agent.name} has been offboarded`)
    } catch { toast.error('Failed to offboard agent') }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-gray-950 text-gray-900 dark:text-white">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/50 z-40 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}
      <Sidebar agents={agents} groups={groups} onNewAgent={() => setShowCreate(true)} onNewGroup={() => setShowGroup(true)} isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Top bar: bookmarks + controls */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shrink-0">
          {/* Hamburger (mobile only) */}
          <button
            className="md:hidden p-1.5 rounded-lg border border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors shrink-0"
            onClick={() => setSidebarOpen(v => !v)}
          >
            <Menu className="w-4 h-4" />
          </button>
          {/* Bookmark shortcuts (hidden on mobile) */}
          <div className="hidden md:flex items-center"><BookmarkBar /></div>

          <div className="flex-1" />

          {/* Docs link */}
          <a
            href="/docs/"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <BookOpen className="w-3.5 h-3.5" />
            Docs
          </a>

          {/* Lang + theme toggles */}
          <button
            onClick={() => setLang(lang === 'en' ? 'zh' : 'en')}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            {lang === 'en' ? '中文' : 'EN'}
          </button>
          <button
            onClick={() => setDark(!dark)}
            className="p-1.5 rounded-lg border border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<Welcome agents={agents} onNewAgent={() => setShowCreate(true)} />} />
            <Route path="/audit" element={<AuditPanel agents={agents} />} />
            <Route path="/exams" element={<ExamPanel agents={agents} onUpdate={loadAgents} />} />
            <Route path="/test-suites" element={<TestSuitePanel agents={agents} onUpdate={loadAgents} />} />
            <Route path="/test-platform" element={<TestPlatform agents={agents} onUpdate={loadAgents} />} />
            <Route path="/test-platform/:tab" element={<TestPlatform agents={agents} onUpdate={loadAgents} />} />
            <Route path="/offboard" element={<OffboardPanel />} />
            <Route path="/role-prompts" element={<RolePromptsPanel />} />
            <Route path="/permissions" element={<PermissionPanel />} />
            <Route path="/group/:groupId" element={<GroupChatView onGroupsChange={loadGroups} />} />
            <Route path="/agent/:agentId" element={<ChatView agents={agents} onOffboard={handleOffboard} onUpdate={loadAgents} />} />
            <Route path="/agent/:agentId/conv/:convId" element={<ChatView agents={agents} onOffboard={handleOffboard} onUpdate={loadAgents} />} />
            <Route path="/test-runs/:runId" element={<TestRunView />} />
            <Route path="/browser-skills" element={<Navigate to="/test-platform/skills" replace />} />
          </Routes>
        </main>
      </div>
      {showCreate && <CreateAgentModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />}
      {showGroup  && <CreateGroupModal agents={agents} onClose={() => setShowGroup(false)} onCreate={handleCreateGroup} />}
    </div>
  )
}

function Welcome({ agents = [], onNewAgent }) {
  const { t } = useLang()
  const hasAgents = agents.length > 0
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-8 bg-white dark:bg-gray-950">
      <div className="text-6xl mb-4">🤖</div>
      <h1 className="text-3xl font-bold mb-2 text-gray-900 dark:text-white">{t('welcome.title')}</h1>
      <p className="text-gray-500 dark:text-gray-400 mb-8 max-w-md">
        {hasAgents ? t('welcome.subtitle.has_agents') : t('welcome.subtitle')}
      </p>
      <button onClick={onNewAgent} className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-semibold transition-colors">
        {hasAgents ? t('welcome.cta.has_agents') : t('welcome.cta')}
      </button>
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <LangProvider>
        <InnerApp />
      </LangProvider>
    </ThemeProvider>
  )
}
