import { useState } from 'react'
import { X } from 'lucide-react'
import { agentApi } from '../api/client.js'
import toast from 'react-hot-toast'

export default function EditAgentModal({ agent, onClose, onUpdate }) {
  const [form, setForm] = useState({
    name: agent.name,
    product_line: agent.product_line,
    avatar_emoji: agent.avatar_emoji,
    description: agent.description || '',
    default_jira_project: agent.default_jira_project || '',
    confluence_spaces: (agent.confluence_spaces || []).join(', '),
  })
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    try {
      await agentApi.update(agent.id, {
        ...form,
        confluence_spaces: form.confluence_spaces.split(',').map(s => s.trim()).filter(Boolean),
      })
      toast.success('Agent updated')
      onUpdate()
    } catch { toast.error('Update failed') }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-50 dark:bg-gray-900 rounded-2xl w-full max-w-lg border border-gray-300 dark:border-gray-700">
        <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-800">
          <h2 className="font-bold text-lg">Edit {agent.name}</h2>
          <button onClick={onClose} className="text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:text-white"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-4">
          <div className="flex gap-3">
            <div>
              <label className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 mb-1 block">Emoji</label>
              <input value={form.avatar_emoji} onChange={e => setForm(f => ({...f, avatar_emoji: e.target.value}))}
                className="w-16 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-2 py-2 text-center text-xl outline-none focus:border-blue-500" />
            </div>
            <div className="flex-1">
              <label className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 mb-1 block">Name</label>
              <input value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))}
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 mb-1 block">Default Jira Project</label>
              <input value={form.default_jira_project} onChange={e => setForm(f => ({...f, default_jira_project: e.target.value}))}
                placeholder="SPPT" className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 mb-1 block">Confluence Spaces</label>
              <input value={form.confluence_spaces} onChange={e => setForm(f => ({...f, confluence_spaces: e.target.value}))}
                placeholder="PROMO, QA" className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={onClose} className="flex-1 py-2.5 bg-gray-100 dark:bg-gray-800 hover:bg-gray-300 dark:hover:bg-gray-700 rounded-xl text-sm transition-colors">Cancel</button>
            <button onClick={save} disabled={saving} className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-xl text-sm font-semibold transition-colors">
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
