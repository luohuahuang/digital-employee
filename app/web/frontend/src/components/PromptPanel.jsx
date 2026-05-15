import { useState, useEffect } from 'react'
import { X, Save, RotateCcw, CheckCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { promptApi } from '../api/client.js'

const TABS = [
  {
    key: 'base',
    label: 'Base Prompt',
    hint: 'Identity, permissions, behavioral rules. ranking / specialization / memory auto-appended at runtime.',
  },
  {
    key: 'specialization',
    label: 'Specialization',
    hint: 'Domain-specific rules, business logic, and known risk areas for this agent\'s product line.',
  },
]

export default function PromptPanel({ agentId, agentName, onClose }) {
  const [tab, setTab]           = useState('base')
  const [content, setContent]   = useState('')
  const [note, setNote]         = useState('')
  const [versions, setVersions] = useState([])
  const [loading, setLoading]   = useState(true)
  const [saving, setSaving]     = useState(false)
  const [activating, setActivating] = useState(null)

  useEffect(() => { loadTab(tab) }, [agentId, tab])

  async function loadTab(t) {
    setLoading(true)
    try {
      const [active, list] = await Promise.all([
        promptApi.getActive(agentId, t),
        promptApi.list(agentId, t),
      ])
      setContent(active.content)
      setVersions(list)
    } catch {
      toast.error('Failed to load prompts')
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    if (!content.trim() && tab === 'base') return
    setSaving(true)
    try {
      await promptApi.save(agentId, { content: content.trim(), note: note.trim(), type: tab })
      toast.success('New version saved and activated')
      setNote('')
      await loadTab(tab)
    } catch {
      toast.error('Failed to save version')
    } finally {
      setSaving(false)
    }
  }

  async function handleActivate(versionId) {
    setActivating(versionId)
    try {
      const v = await promptApi.activate(agentId, versionId)
      toast.success(`Rolled back to v${v.version}`)
      await loadTab(tab)
    } catch {
      toast.error('Failed to activate version')
    } finally {
      setActivating(null)
    }
  }

  const currentTab = TABS.find(t => t.key === tab)

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-xl w-full max-w-5xl h-[85vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-300 dark:border-gray-700 shrink-0">
          <div>
            <h2 className="font-semibold text-gray-900 dark:text-white">Prompt Manager</h2>
            <p className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 mt-0.5">{agentName}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-300 dark:border-gray-700 px-6 shrink-0">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => { setTab(t.key); setNote('') }}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t.key
                  ? 'border-blue-500 text-gray-900 dark:text-white'
                  : 'border-transparent text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:text-gray-200'
              }`}
            >
              {t.label}
              {t.key === 'base' && <span className="ml-1.5 text-xs text-gray-500 dark:text-gray-500">(versioned)</span>}
              {t.key === 'specialization' && <span className="ml-1.5 text-xs text-gray-500 dark:text-gray-500">(versioned)</span>}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-500 text-sm">Loading…</div>
        ) : (
          <div className="flex flex-1 overflow-hidden">

            {/* Editor pane */}
            <div className="flex-1 flex flex-col p-4 gap-3 border-r border-gray-300 dark:border-gray-700 overflow-hidden">
              <div className="flex items-start justify-between gap-4">
                <p className="text-xs text-gray-500 dark:text-gray-500 leading-relaxed">{currentTab?.hint}</p>
                <span className="shrink-0 text-xs text-gray-600">{content.length} chars</span>
              </div>

              <textarea
                value={content}
                onChange={e => setContent(e.target.value)}
                className="flex-1 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-xs font-mono text-gray-200 outline-none focus:border-blue-500 resize-none leading-relaxed"
                spellCheck={false}
                placeholder={tab === 'specialization' ? 'Leave empty if no domain-specific rules are needed.' : ''}
              />

              <div className="flex gap-2 items-center">
                <input
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  placeholder="Change note (optional)…"
                  className="flex-1 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-xs outline-none focus:border-blue-500"
                />
                <button
                  onClick={handleSave}
                  disabled={saving || (tab === 'base' && !content.trim())}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 text-gray-900 dark:text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-50 shrink-0"
                >
                  <Save className="w-3.5 h-3.5" />
                  {saving ? 'Saving…' : 'Save new version'}
                </button>
              </div>
            </div>

            {/* Version history pane */}
            <div className="w-72 flex flex-col overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-300 dark:border-gray-700">
                <span className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 font-medium uppercase tracking-wide">Version History</span>
              </div>
              <div className="flex-1 overflow-y-auto">
                {versions.length === 0 && (
                  <p className="px-4 py-6 text-xs text-gray-600 text-center">No versions yet.</p>
                )}
                {versions.map(v => (
                  <div
                    key={v.id}
                    className={`px-4 py-3 border-b border-gray-300 dark:border-gray-700/50 transition-colors ${v.is_active ? 'bg-blue-900/20' : 'hover:bg-gray-200 dark:hover:bg-gray-800/50'}`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-gray-900 dark:text-white">v{v.version}</span>
                        {v.is_active && (
                          <span className="flex items-center gap-1 text-xs text-blue-400">
                            <CheckCircle className="w-3 h-3" /> active
                          </span>
                        )}
                      </div>
                      {!v.is_active && (
                        <button
                          onClick={() => handleActivate(v.id)}
                          disabled={activating === v.id}
                          className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:text-yellow-400 transition-colors"
                          title="Roll back to this version"
                        >
                          <RotateCcw className="w-3 h-3" />
                          {activating === v.id ? '…' : 'Activate'}
                        </button>
                      )}
                    </div>

                    <p className="text-xs text-gray-500 dark:text-gray-500 mb-1.5">
                      {v.created_at ? new Date(v.created_at).toLocaleString() : '—'}
                    </p>

                    {v.note && (
                      <p className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 italic mb-1.5">"{v.note}"</p>
                    )}

                    {/* Exam stats — only meaningful for base prompt versions */}
                    {tab === 'base' && (
                      v.exam_runs > 0 ? (
                        <div className="flex items-center gap-2 text-xs">
                          <span className="text-gray-500 dark:text-gray-500">{v.exam_runs} exam{v.exam_runs > 1 ? 's' : ''}</span>
                          {v.pass_rate != null && (
                            <span className={v.pass_rate >= 0.8 ? 'text-green-400' : v.pass_rate >= 0.5 ? 'text-yellow-400' : 'text-red-400'}>
                              {(v.pass_rate * 100).toFixed(0)}% pass
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-gray-600">No exams run yet</span>
                      )
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
