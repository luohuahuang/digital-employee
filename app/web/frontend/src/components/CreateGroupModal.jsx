import { useState } from 'react'
import { X, Users } from 'lucide-react'

export default function CreateGroupModal({ agents, onCreate, onClose }) {
  const [title, setTitle]       = useState('')
  const [selected, setSelected] = useState(new Set())
  const [loading, setLoading]   = useState(false)

  function toggle(id) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (selected.size < 2) return
    setLoading(true)
    try {
      await onCreate({
        title: title.trim() || 'New Group Chat',
        agent_ids: [...selected],
      })
    } finally {
      setLoading(false)
    }
  }

  const RANKING_STYLE = {
    Intern: 'bg-gray-600 text-gray-200',
    Junior: 'bg-blue-700 text-blue-100',
    Senior: 'bg-green-700 text-green-100',
    Lead:   'bg-yellow-600 text-yellow-100',
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-blue-400" />
            <span className="font-bold text-white">Create Group Chat</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {/* Title */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Group name (optional)</label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="e.g. SPB-57352 Regression Review"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Agent picker */}
          <div>
            <label className="block text-xs text-gray-400 mb-2">
              Select agents <span className="text-gray-500">(minimum 2)</span>
            </label>
            <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              {agents.map(agent => (
                <label
                  key={agent.id}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                    selected.has(agent.id)
                      ? 'bg-blue-600/20 border border-blue-500/50'
                      : 'bg-gray-800 border border-transparent hover:bg-gray-700'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(agent.id)}
                    onChange={() => toggle(agent.id)}
                    className="accent-blue-500"
                  />
                  <span className="text-xl">{agent.avatar_emoji}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-white truncate">{agent.name}</span>
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0 ${RANKING_STYLE[agent.ranking] || RANKING_STYLE.Intern}`}>
                        {agent.ranking || 'Intern'}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 truncate">{agent.product_line}</p>
                  </div>
                </label>
              ))}
              {agents.length === 0 && (
                <p className="text-gray-500 text-sm text-center py-4">No active agents available</p>
              )}
            </div>
          </div>

          {selected.size > 0 && selected.size < 2 && (
            <p className="text-xs text-orange-400">Select at least 2 agents to start a group chat</p>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={selected.size < 2 || loading}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-semibold transition-colors"
            >
              {loading ? 'Creating…' : `Create with ${selected.size} agent${selected.size !== 1 ? 's' : ''}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
