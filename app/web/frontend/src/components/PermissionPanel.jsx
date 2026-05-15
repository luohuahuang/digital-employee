import { useState, useEffect } from 'react'
import { RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import { permissionApi } from '../api/client.js'

const LEVELS = ['L1', 'L2', 'L3']

const LEVEL_STYLE = {
  L1: 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200 border-green-300 dark:border-green-700',
  L2: 'bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-200 border-yellow-300 dark:border-yellow-700',
  L3: 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 border-red-300 dark:border-red-700',
}

const LEVEL_DESC = {
  L1: 'Auto-execute',
  L2: 'Requires approval',
  L3: 'Plan only (no execution)',
}

const RANKING_ORDER = ['Intern', 'Junior', 'Senior', 'Lead']

function LevelBadge({ level }) {
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${LEVEL_STYLE[level] || ''}`}>
      {level}
    </span>
  )
}

function LevelSelector({ value, onChange, disabled }) {
  return (
    <div className="flex gap-1">
      {LEVELS.map(l => (
        <button
          key={l}
          disabled={disabled}
          onClick={() => onChange(l)}
          className={`text-xs font-semibold px-2.5 py-1 rounded border transition-colors ${
            value === l
              ? LEVEL_STYLE[l] + ' ring-1 ring-offset-1 ring-current'
              : 'border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
          } disabled:opacity-40 disabled:cursor-not-allowed`}
        >
          {l}
        </button>
      ))}
    </div>
  )
}

export default function PermissionPanel() {
  const [tools,    setTools]    = useState([])
  const [rankings, setRankings] = useState([])
  const [loading,  setLoading]  = useState(true)
  const [saving,   setSaving]   = useState(null)   // tool_name or ranking key being saved
  const [confirmReset, setConfirmReset] = useState(false)

  useEffect(() => { load() }, [])

  async function load() {
    setLoading(true)
    try {
      const data = await permissionApi.get()
      setTools(data.tools || [])
      setRankings(data.rankings || [])
    } catch {
      toast.error('Failed to load permission config')
    } finally {
      setLoading(false)
    }
  }

  async function handleToolChange(toolName, newLevel) {
    setSaving(toolName)
    try {
      await permissionApi.updateTool(toolName, newLevel)
      setTools(prev => prev.map(t => t.tool_name === toolName ? { ...t, risk_level: newLevel } : t))
      toast.success(`${toolName} → ${newLevel}`)
    } catch {
      toast.error('Failed to update tool permission')
    } finally {
      setSaving(null)
    }
  }

  async function handleRankingChange(ranking, newCeiling) {
    setSaving(ranking)
    try {
      await permissionApi.updateRanking(ranking, newCeiling)
      setRankings(prev => prev.map(r => r.ranking === ranking ? { ...r, ceiling: newCeiling } : r))
      toast.success(`${ranking} ceiling → ${newCeiling}`)
    } catch {
      toast.error('Failed to update ranking ceiling')
    } finally {
      setSaving(null)
    }
  }

  async function handleReset() {
    setConfirmReset(false)
    try {
      await permissionApi.reset()
      toast.success('Permissions reset to defaults')
      load()
    } catch {
      toast.error('Failed to reset permissions')
    }
  }

  // Sort tools: L2/L3 first, then L1; within same level alphabetically
  const sortedTools = [...tools].sort((a, b) => {
    const la = a.risk_level, lb = b.risk_level
    if (la !== lb) return la > lb ? -1 : 1   // L3 > L2 > L1
    return a.display_name.localeCompare(b.display_name)
  })

  // Sort rankings in fixed order
  const sortedRankings = RANKING_ORDER
    .map(r => rankings.find(x => x.ranking === r))
    .filter(Boolean)

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 shrink-0 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900 dark:text-white">🔐 Permission Config</h1>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Configure tool risk levels and ranking ceilings. Changes take effect on the next chat turn.
          </p>
        </div>
        <div>
          {confirmReset ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 dark:text-gray-400">Reset all to defaults?</span>
              <button onClick={() => setConfirmReset(false)} className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800">Cancel</button>
              <button onClick={handleReset} className="text-xs px-2 py-1 rounded bg-red-500 hover:bg-red-400 text-white font-medium">Reset</button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmReset(true)}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:border-gray-500 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Reset to defaults
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="flex-1 overflow-y-auto p-6 space-y-8">

          {/* Legend */}
          <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
            {LEVELS.map(l => (
              <span key={l} className="flex items-center gap-1.5">
                <LevelBadge level={l} />
                {LEVEL_DESC[l]}
              </span>
            ))}
          </div>

          {/* Ranking Ceilings */}
          <section>
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Ranking Permission Ceilings
              <span className="ml-2 text-xs font-normal text-gray-400 dark:text-gray-500">
                — highest level a ranking tier can auto-execute
              </span>
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {sortedRankings.map(r => (
                <div key={r.ranking} className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">{r.ranking}</span>
                    <LevelBadge level={r.ceiling} />
                  </div>
                  <LevelSelector
                    value={r.ceiling}
                    disabled={saving === r.ranking}
                    onChange={v => handleRankingChange(r.ranking, v)}
                  />
                </div>
              ))}
            </div>
          </section>

          {/* Tool Risk Levels */}
          <section>
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Tool Risk Levels
              <span className="ml-2 text-xs font-normal text-gray-400 dark:text-gray-500">
                — determines whether a tool needs Mentor approval
              </span>
            </h2>
            <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-100 dark:bg-gray-800 text-left text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    <th className="px-4 py-2.5 font-semibold">Tool</th>
                    <th className="px-4 py-2.5 font-semibold">Internal Name</th>
                    <th className="px-4 py-2.5 font-semibold">Risk Level</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
                  {sortedTools.map(t => (
                    <tr key={t.tool_name} className="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors">
                      <td className="px-4 py-3 font-medium text-gray-800 dark:text-gray-200">{t.display_name}</td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-400 dark:text-gray-500">{t.tool_name}</td>
                      <td className="px-4 py-3">
                        <LevelSelector
                          value={t.risk_level}
                          disabled={saving === t.tool_name}
                          onChange={v => handleToolChange(t.tool_name, v)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

        </div>
      )}
    </div>
  )
}
