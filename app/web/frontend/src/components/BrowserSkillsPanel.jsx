import { useState, useEffect } from 'react'
import { Plus, Trash2, Save, Globe, Zap } from 'lucide-react'
import { api } from '../api/client.js'
import toast from 'react-hot-toast'

const skillsApi = {
  list:   (type)     => api.get('/browser-skills', { params: type ? { type } : {} }).then(r => r.data),
  create: (payload)  => api.post('/browser-skills', payload).then(r => r.data),
  update: (id, payload) => api.put(`/browser-skills/${id}`, payload).then(r => r.data),
  delete: (id)       => api.delete(`/browser-skills/${id}`),
}

const TABS = [
  { key: 'environment', label: 'Environment Skills', icon: Globe,
    hint: 'One skill per environment. Defines base_url, credentials, and test data. Select exactly one when starting a run.' },
  { key: 'extra',       label: 'Extra Skills',       icon: Zap,
    hint: 'Reusable execution hints. Multi-select when starting a run. Examples: login flow, popup handling, checkout patterns.' },
]

const EMPTY_SKILL = { name: '', skill_type: 'environment', content: '' }

const ENV_PLACEHOLDER = `# Environment: My Staging

base_url: https://staging.example.com

credentials:
  username: testuser@example.com
  password: Test1234

test_data:
  product_id: '12345'
  voucher_code: 'SAVE10'

notes:
  - CAPTCHA is disabled in staging
  - Payment gateway is mocked
`

const EXTRA_PLACEHOLDER = `# Skill: Login Flow

When a test step requires logging in:
1. Navigate to /login if not already there
2. Enter credentials from the environment skill
3. Click the login/submit button
4. Wait for the redirect to complete before proceeding
5. If a 'Stay signed in' dialog appears, dismiss it
`

export default function BrowserSkillsPanel() {
  const [activeTab, setActiveTab] = useState('environment')
  const [skills, setSkills] = useState([])
  const [selected, setSelected] = useState(null)   // currently edited skill
  const [draft, setDraft] = useState(EMPTY_SKILL)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    loadSkills()
  }, [activeTab])

  async function loadSkills() {
    try {
      const data = await skillsApi.list(activeTab)
      setSkills(data)
      setSelected(null)
      setDraft({ ...EMPTY_SKILL, skill_type: activeTab })
      setDirty(false)
    } catch {
      toast.error('Failed to load skills')
    }
  }

  function selectSkill(skill) {
    setSelected(skill)
    setDraft({ name: skill.name, skill_type: skill.skill_type, content: skill.content })
    setDirty(false)
    setConfirmDelete(false)
  }

  function newSkill() {
    setSelected(null)
    setDraft({ name: '', skill_type: activeTab, content: '' })
    setDirty(false)
    setConfirmDelete(false)
  }

  function handleChange(field, value) {
    setDraft(d => ({ ...d, [field]: value }))
    setDirty(true)
  }

  async function handleSave() {
    if (!draft.name.trim()) { toast.error('Name is required'); return }
    if (!draft.content.trim()) { toast.error('Content is required'); return }
    setSaving(true)
    try {
      if (selected) {
        await skillsApi.update(selected.id, draft)
        toast.success('Skill saved')
      } else {
        const { id } = await skillsApi.create(draft)
        toast.success('Skill created')
      }
      await loadSkills()
    } catch {
      toast.error('Failed to save skill')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!selected) return
    try {
      await skillsApi.delete(selected.id)
      toast.success('Skill deleted')
      await loadSkills()
      setConfirmDelete(false)
    } catch {
      toast.error('Failed to delete skill')
    }
  }

  const tab = TABS.find(t => t.key === activeTab)
  const placeholder = activeTab === 'environment' ? ENV_PLACEHOLDER : EXTRA_PLACEHOLDER

  return (
    <div className="flex flex-col h-full overflow-hidden bg-white dark:bg-gray-950">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <h1 className="font-semibold text-gray-900 dark:text-white text-base">Browser Skills</h1>
        <p className="text-xs text-gray-400 mt-0.5">
          Skills provide context to the test execution engine — credentials, environment config, and execution hints.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-800 px-6">
        {TABS.map(t => {
          const Icon = t.icon
          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === t.key
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </button>
          )
        })}
      </div>

      {/* Hint */}
      <div className="px-6 py-2 bg-gray-50 dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800">
        <p className="text-xs text-gray-400">{tab.hint}</p>
      </div>

      {/* Body: list + editor */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left: skill list */}
        <div className="w-64 shrink-0 border-r border-gray-200 dark:border-gray-800 flex flex-col">
          <div className="p-3 border-b border-gray-100 dark:border-gray-800">
            <button
              onClick={newSkill}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium rounded-lg transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> New Skill
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {skills.length === 0 && (
              <p className="text-xs text-gray-400 text-center py-8 px-4">
                No {activeTab} skills yet.<br />Click "New Skill" to create one.
              </p>
            )}
            {skills.map(s => (
              <button
                key={s.id}
                onClick={() => selectSkill(s)}
                className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors text-sm truncate ${
                  selected?.id === s.id
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                {s.name}
              </button>
            ))}
          </div>
        </div>

        {/* Right: editor */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Editor header */}
          <div className="px-6 py-3 border-b border-gray-100 dark:border-gray-800 flex items-center gap-3">
            <input
              value={draft.name}
              onChange={e => handleChange('name', e.target.value)}
              placeholder="Skill name…"
              className="flex-1 text-sm font-medium bg-transparent border-0 border-b border-transparent focus:border-blue-500 focus:outline-none text-gray-900 dark:text-white placeholder-gray-300 dark:placeholder-gray-600 py-0.5 transition-colors"
            />
            {dirty && (
              <span className="text-xs text-amber-500 shrink-0">Unsaved changes</span>
            )}
            <button
              onClick={handleSave}
              disabled={saving || !dirty}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-xs font-medium rounded-lg transition-colors shrink-0"
            >
              <Save className="w-3.5 h-3.5" />
              {saving ? 'Saving…' : 'Save'}
            </button>
            {selected && (
              confirmDelete ? (
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-red-500">Delete?</span>
                  <button onClick={handleDelete} className="text-xs text-red-500 hover:text-red-400 font-medium">Yes</button>
                  <button onClick={() => setConfirmDelete(false)} className="text-xs text-gray-400 hover:text-gray-600">No</button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmDelete(true)}
                  className="p-1.5 text-gray-400 hover:text-red-500 transition-colors shrink-0"
                  title="Delete skill"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )
            )}
          </div>

          {/* Textarea */}
          <textarea
            value={draft.content}
            onChange={e => handleChange('content', e.target.value)}
            placeholder={placeholder}
            spellCheck={false}
            className="flex-1 p-6 text-sm font-mono bg-white dark:bg-gray-950 text-gray-800 dark:text-gray-200 resize-none focus:outline-none placeholder-gray-200 dark:placeholder-gray-700 leading-relaxed"
          />
        </div>
      </div>
    </div>
  )
}
