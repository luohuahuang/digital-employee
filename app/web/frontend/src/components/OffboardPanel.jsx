import { useState, useEffect } from 'react'
import { Trash2, UserX } from 'lucide-react'
import { agentApi } from '../api/client.js'
import toast from 'react-hot-toast'

const RANKING_STYLE = {
  Intern: 'bg-gray-600 text-gray-200',
  Junior: 'bg-blue-700 text-blue-100',
  Senior: 'bg-green-700 text-green-100',
  Lead:   'bg-yellow-600 text-yellow-100',
}

function RankingBadge({ ranking }) {
  const cls = RANKING_STYLE[ranking] || RANKING_STYLE.Intern
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${cls}`}>
      {ranking || 'Intern'}
    </span>
  )
}

export default function OffboardPanel() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [confirmId, setConfirmId] = useState(null)

  useEffect(() => { load() }, [])

  async function load() {
    try {
      setLoading(true)
      const data = await agentApi.listOffboarded()
      setAgents(data)
    } catch {
      toast.error('Failed to load offboard records')
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(agentId) {
    try {
      await agentApi.delete(agentId)
      setAgents(prev => prev.filter(a => a.id !== agentId))
      setConfirmId(null)
      toast.success('Agent permanently deleted')
    } catch {
      toast.error('Failed to delete agent')
    }
  }

  function formatDate(iso) {
    if (!iso) return '—'
    return new Date(iso).toLocaleString()
  }

  return (
    <div className="h-full flex flex-col p-6 overflow-y-auto">
      <div className="flex items-center gap-3 mb-6">
        <UserX className="w-6 h-6 text-orange-400" />
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Offboard Records</h1>
      </div>

      {loading ? (
        <p className="text-gray-500 dark:text-gray-500 text-sm">Loading...</p>
      ) : agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center flex-1 text-center">
          <UserX className="w-12 h-12 text-gray-700 mb-3" />
          <p className="text-gray-500 dark:text-gray-500">No offboarded agents yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {agents.map(agent => (
            <div
              key={agent.id}
              className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl px-5 py-4 flex items-center gap-4"
            >
              <span className="text-3xl shrink-0">{agent.avatar_emoji}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-semibold text-gray-900 dark:text-white text-sm">{agent.name}</span>
                  <RankingBadge ranking={agent.ranking} />
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400">{agent.product_line}</p>
                <p className="text-xs text-gray-600 mt-1">
                  Offboarded: {formatDate(agent.offboarded_at)}
                </p>
              </div>

              {confirmId === agent.id ? (
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-red-400">Permanently delete?</span>
                  <button
                    onClick={() => handleDelete(agent.id)}
                    className="px-3 py-1 bg-red-700 hover:bg-red-600 text-gray-900 dark:text-white text-xs rounded-lg transition-colors"
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => setConfirmId(null)}
                    className="px-3 py-1 bg-gray-700 hover:bg-gray-600 text-gray-900 dark:text-white text-xs rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmId(agent.id)}
                  className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:bg-gray-100 dark:bg-gray-800 rounded-lg transition-colors"
                  title="Permanently delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Delete
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
