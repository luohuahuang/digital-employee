import { useState, useEffect } from 'react'
import { Save, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import { rolePromptApi } from '../api/client.js'

const ROLES = [
  { id: 'QA',  emoji: '🔍', label: 'QA',  color: 'text-purple-400', activeBorder: 'border-purple-500' },
  { id: 'Dev', emoji: '💻', label: 'Dev', color: 'text-blue-400',   activeBorder: 'border-blue-500'   },
  { id: 'PM',  emoji: '📋', label: 'PM',  color: 'text-orange-400', activeBorder: 'border-orange-500' },
  { id: 'SRE', emoji: '🔧', label: 'SRE', color: 'text-red-400',    activeBorder: 'border-red-500'    },
  { id: 'PJ',  emoji: '📅', label: 'PJ',  color: 'text-teal-400',   activeBorder: 'border-teal-500'   },
]

export default function RolePromptsPanel() {
  const [activeRole,   setActiveRole]   = useState('QA')
  const [templates,    setTemplates]    = useState({})   // { QA: {content, updated_at}, ... }
  const [editContent,  setEditContent]  = useState('')
  const [note,         setNote]         = useState('')
  const [loading,      setLoading]      = useState(true)
  const [saving,       setSaving]       = useState(false)
  const [resetting,    setResetting]    = useState(false)
  const [dirty,        setDirty]        = useState(false)

  useEffect(() => { load() }, [])

  useEffect(() => {
    const tpl = templates[activeRole]
    if (tpl) {
      setEditContent(tpl.content)
      setDirty(false)
      setNote('')
    }
  }, [activeRole, templates])

  async function load() {
    setLoading(true)
    try {
      const all = await rolePromptApi.list()
      const map = {}
      all.forEach(t => { map[t.role] = t })
      setTemplates(map)
    } catch {
      toast.error('Failed to load role templates')
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    try {
      const updated = await rolePromptApi.update(activeRole, editContent)
      setTemplates(prev => ({ ...prev, [activeRole]: updated }))
      setDirty(false)
      toast.success(`${activeRole} template saved`)
    } catch {
      toast.error('Failed to save template')
    } finally {
      setSaving(false)
    }
  }

  async function handleReset() {
    setResetting(true)
    try {
      const updated = await rolePromptApi.reset(activeRole)
      setTemplates(prev => ({ ...prev, [activeRole]: updated }))
      setEditContent(updated.content)
      setDirty(false)
      toast.success(`${activeRole} template reset to default`)
    } catch {
      toast.error('Failed to reset template')
    } finally {
      setResetting(false)
    }
  }

  const activeRoleMeta = ROLES.find(r => r.id === activeRole)
  const tpl = templates[activeRole]

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 shrink-0">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">📝 Role Prompt Templates</h1>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          Edit the base prompt that will be seeded for each newly onboarded employee. Existing agents are not affected.
        </p>
      </div>

      {/* Role tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-800 shrink-0 px-6">
        {ROLES.map(role => (
          <button
            key={role.id}
            onClick={() => {
              if (dirty && !window.confirm('You have unsaved changes. Switch anyway?')) return
              setActiveRole(role.id)
            }}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeRole === role.id
                ? `${role.activeBorder} ${role.color}`
                : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            }`}
          >
            <span>{role.emoji}</span>
            {role.label}
            {activeRole === role.id && dirty && <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 ml-1" />}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="flex flex-1 overflow-hidden">

          {/* Editor pane */}
          <div className="flex-1 flex flex-col p-5 gap-3 overflow-hidden">

            {/* Info bar */}
            <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
              <span>
                Base prompt for <span className={`font-semibold ${activeRoleMeta?.color}`}>{activeRole}</span> employees.
                Used when a new {activeRole} agent's Prompt Manager is first opened.
              </span>
              <span>{editContent.length} chars</span>
            </div>

            {/* Textarea */}
            <textarea
              value={editContent}
              onChange={e => { setEditContent(e.target.value); setDirty(true) }}
              className="flex-1 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-3 text-xs font-mono text-gray-900 dark:text-gray-100 outline-none focus:border-blue-500 resize-none leading-relaxed"
              spellCheck={false}
            />

            {/* Action bar */}
            <div className="flex items-center gap-3 shrink-0">
              <span className="text-xs text-gray-500 dark:text-gray-400 flex-1">
                {tpl?.updated_at
                  ? `Last saved: ${new Date(tpl.updated_at).toLocaleString()}`
                  : 'Never edited — using built-in default'}
              </span>
              <button
                onClick={handleReset}
                disabled={resetting || saving}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:border-gray-500 transition-colors disabled:opacity-50"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                {resetting ? 'Resetting…' : 'Reset to default'}
              </button>
              <button
                onClick={handleSave}
                disabled={saving || resetting || !dirty}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Save className="w-3.5 h-3.5" />
                {saving ? 'Saving…' : 'Save template'}
              </button>
            </div>
          </div>

          {/* Sidebar: usage note */}
          <div className="w-64 shrink-0 border-l border-gray-200 dark:border-gray-800 p-5 space-y-5 overflow-y-auto">
            <div>
              <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">How it works</p>
              <div className="space-y-3 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                <p>
                  When a new employee is onboarded with the <span className={`font-semibold ${activeRoleMeta?.color}`}>{activeRole}</span> role,
                  their Base Prompt is automatically seeded from this template.
                </p>
                <p>
                  Each agent can then further customize their own base prompt via <span className="font-mono bg-gray-100 dark:bg-gray-800 px-1 rounded">Prompt Manager</span> in their chat view.
                </p>
                <p>
                  Saving this template does <span className="font-semibold text-gray-700 dark:text-gray-200">not</span> affect existing agents — only newly onboarded ones.
                </p>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">Template variables</p>
              <div className="space-y-1.5 text-xs font-mono">
                {[
                  ['{agent_id}',            'Agent UUID'],
                  ['{agent_version}',       'Prompt version'],
                  ['{ranking_description}', 'Intern / Junior / Senior / Lead'],
                ].map(([v, desc]) => (
                  <div key={v} className="flex gap-2">
                    <span className="text-blue-400 shrink-0">{v}</span>
                    <span className="text-gray-600 dark:text-gray-500">{desc}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
