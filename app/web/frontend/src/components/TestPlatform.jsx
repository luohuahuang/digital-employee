import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Plus, Trash2, Play, X, Search, ChevronDown, ChevronUp,
  BarChart2, ClipboardList, ListChecks, FlaskConical,
  CheckCircle, XCircle, Clock, RefreshCw, ExternalLink,
  Download, GitBranch, Cpu, StopCircle,
} from 'lucide-react'
import { testSuiteApi, testRunApi, testPlanApi, api } from '../api/client.js'
import TestSuitePanel from './TestSuitePanel.jsx'
import BrowserSkillsPanel from './BrowserSkillsPanel.jsx'
import toast from 'react-hot-toast'

// ── Shared helpers ─────────────────────────────────────────────────────────────

const STATUS_STYLE = {
  pass:       { icon: CheckCircle, color: 'text-green-500',  bg: 'bg-green-50 dark:bg-green-900/20',    label: 'Pass'       },
  fail:       { icon: XCircle,     color: 'text-red-500',    bg: 'bg-red-50 dark:bg-red-900/20',        label: 'Fail'       },
  error:      { icon: XCircle,     color: 'text-orange-500', bg: 'bg-orange-50 dark:bg-orange-900/20',  label: 'Error'      },
  pending:    { icon: Clock,       color: 'text-gray-400',   bg: 'bg-gray-50 dark:bg-gray-800',         label: 'Pending'    },
  running:    { icon: Clock,       color: 'text-blue-400',   bg: 'bg-blue-50 dark:bg-blue-900/20',      label: 'Running'    },
  completed:  { icon: CheckCircle, color: 'text-green-500',  bg: 'bg-green-50 dark:bg-green-900/20',    label: 'Completed'  },
  terminated: { icon: StopCircle,  color: 'text-yellow-500', bg: 'bg-yellow-50 dark:bg-yellow-900/20',  label: 'Terminated' },
}

function StatusBadge({ status, small }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.pending
  const Icon = s.icon
  return (
    <span className={`inline-flex items-center gap-1 font-medium ${small ? 'text-xs' : 'text-sm'} ${s.color}`}>
      <Icon className={small ? 'w-3 h-3' : 'w-4 h-4'} />
      {s.label}
    </span>
  )
}

function PassRateBar({ rate, width = 'w-full' }) {
  const color = rate >= 80 ? 'bg-green-500' : rate >= 60 ? 'bg-yellow-400' : 'bg-red-500'
  return (
    <div className={`h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden ${width}`}>
      <div className={`h-full ${color} transition-all duration-500`} style={{ width: `${rate}%` }} />
    </div>
  )
}

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('en-SG', { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-SG', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// ── TAB: Plans ─────────────────────────────────────────────────────────────────

function PlansTab({ suites }) {
  const navigate = useNavigate()
  const [plans, setPlans]       = useState([])
  const [selected, setSelected] = useState(null)  // plan id
  const [editing, setEditing]   = useState(false)  // true = edit mode
  const [creating, setCreating] = useState(false)
  const [form, setForm]         = useState({ name: '', description: '', suite_ids: [], platform: 'web', env_skill_id: '' })
  const [envSkills, setEnvSkills]   = useState([])
  const [showExec, setShowExec]     = useState(false)
  const [execForm, setExecForm]     = useState({ batch_name: '', env_skill_id: '', platform: '' })
  const [executing, setExecuting]   = useState(false)
  const [saving, setSaving]         = useState(false)

  const loadPlans = useCallback(async () => {
    try { setPlans(await testPlanApi.list()) } catch { toast.error('Failed to load plans') }
  }, [])

  useEffect(() => { loadPlans() }, [loadPlans])

  useEffect(() => {
    api.get('/browser-skills', { params: { type: 'environment' } })
      .then(r => setEnvSkills(r.data))
      .catch(() => {})
  }, [])

  const selectedPlan = plans.find(p => p.id === selected)

  function startCreate() {
    setCreating(true)
    setEditing(false)
    setSelected(null)
    setForm({ name: '', description: '', suite_ids: [], platform: 'web', env_skill_id: '' })
  }

  function startEdit() {
    if (!selectedPlan) return
    setForm({
      name:        selectedPlan.name,
      description: selectedPlan.description || '',
      suite_ids:   selectedPlan.suite_ids || [],
      platform:    selectedPlan.platform || 'web',
      env_skill_id: selectedPlan.env_skill_id || '',
    })
    setEditing(true)
    setCreating(false)
  }

  async function handleSave() {
    if (!form.name.trim()) { toast.error('Plan name required'); return }
    setSaving(true)
    try {
      if (creating) {
        const p = await testPlanApi.create(form)
        setPlans(prev => [p, ...prev])
        setSelected(p.id)
        setCreating(false)
        toast.success('Plan created')
      } else {
        const p = await testPlanApi.update(selected, form)
        setPlans(prev => prev.map(x => x.id === p.id ? p : x))
        setEditing(false)
        toast.success('Plan saved')
      }
    } catch { toast.error('Failed to save plan') }
    setSaving(false)
  }

  async function handleDelete() {
    if (!selected || !confirm('Delete this test plan?')) return
    try {
      await testPlanApi.delete(selected)
      setPlans(prev => prev.filter(p => p.id !== selected))
      setSelected(null)
      toast.success('Plan deleted')
    } catch { toast.error('Failed to delete') }
  }

  function openExec() {
    if (!selectedPlan) return
    setExecForm({
      batch_name:   `${selectedPlan.name} — ${new Date().toLocaleDateString('en-SG', { month: 'short', day: 'numeric' })}`,
      env_skill_id: selectedPlan.env_skill_id || (envSkills[0]?.id || ''),
      platform:     selectedPlan.platform || 'web',
    })
    setShowExec(true)
  }

  async function handleExecute() {
    if (!execForm.batch_name.trim()) return
    setExecuting(true)
    try {
      const result = await testPlanApi.execute(selected, execForm)
      setShowExec(false)
      toast.success(`${result.runs.length} run${result.runs.length !== 1 ? 's' : ''} started`)
      if (result.runs.length === 1) {
        navigate(`/test-runs/${result.runs[0].run_id}`)
      } else {
        navigate('/test-platform/runs')
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to execute plan')
    }
    setExecuting(false)
  }

  function toggleSuite(suiteId) {
    setForm(f => ({
      ...f,
      suite_ids: f.suite_ids.includes(suiteId)
        ? f.suite_ids.filter(id => id !== suiteId)
        : [...f.suite_ids, suiteId],
    }))
  }

  const isFormMode = creating || editing

  return (
    <div className="flex flex-1 overflow-hidden gap-4 p-6">
      {/* Left: plan list */}
      <div className="w-60 flex flex-col border border-gray-200 dark:border-gray-700 rounded-xl bg-gray-50 dark:bg-gray-900/50 shrink-0 overflow-hidden">
        <div className="px-3 py-2.5 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">{plans.length} plan{plans.length !== 1 ? 's' : ''}</span>
          <button
            onClick={startCreate}
            className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-500 dark:text-gray-400 hover:text-blue-500"
            title="New plan"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-1.5 space-y-1">
          {creating && (
            <div className="w-full text-left p-2.5 rounded-lg text-xs bg-blue-600 text-white">
              <div className="font-medium truncate">{form.name || 'New Plan…'}</div>
              <div className="text-blue-200 text-[10px] mt-0.5">draft</div>
            </div>
          )}
          {plans.map(p => (
            <button
              key={p.id}
              onClick={() => { setSelected(p.id); setCreating(false); setEditing(false) }}
              className={`w-full text-left p-2.5 rounded-lg text-xs transition-colors ${
                selected === p.id && !creating
                  ? 'bg-blue-600 text-white'
                  : 'hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-900 dark:text-gray-300'
              }`}
            >
              <div className="font-medium truncate">{p.name}</div>
              <div className={`text-[10px] mt-0.5 ${selected === p.id && !creating ? 'text-blue-200' : 'text-gray-500'}`}>
                {(p.suite_ids || []).length} suite{(p.suite_ids || []).length !== 1 ? 's' : ''} · {p.platform}
              </div>
            </button>
          ))}
          {plans.length === 0 && !creating && (
            <p className="text-center text-gray-500 py-8 text-xs">No plans yet</p>
          )}
        </div>
      </div>

      {/* Right: plan detail / form */}
      <div className="flex-1 flex flex-col border border-gray-200 dark:border-gray-700 rounded-xl bg-gray-50 dark:bg-gray-900/50 overflow-hidden">
        {isFormMode ? (
          /* ── Edit / Create form ── */
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            <h2 className="font-bold text-gray-900 dark:text-white text-sm">
              {creating ? 'New Test Plan' : 'Edit Plan'}
            </h2>

            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Plan name *</label>
              <input
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Sprint 34 Regression"
                className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Description</label>
              <textarea
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                rows={2}
                placeholder="Optional description"
                className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 focus:outline-none resize-none"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                Platform
              </label>
              <div className="flex gap-2">
                {[{ value: 'web', label: '🌐 Web' }, { value: 'android', label: '🤖 Android' }].map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => setForm(f => ({ ...f, platform: opt.value }))}
                    className={`flex-1 py-1.5 text-sm rounded-lg border transition-colors ${
                      form.platform === opt.value
                        ? 'bg-blue-600 border-blue-600 text-white'
                        : 'border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                Default Environment
              </label>
              <select
                value={form.env_skill_id}
                onChange={e => setForm(f => ({ ...f, env_skill_id: e.target.value }))}
                className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 focus:outline-none"
              >
                <option value="">— None —</option>
                {envSkills.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                Test Suites ({form.suite_ids.length} selected)
              </label>
              <div className="border border-gray-300 dark:border-gray-700 rounded-lg overflow-hidden max-h-64 overflow-y-auto bg-white dark:bg-gray-800">
                {suites.length === 0 ? (
                  <p className="text-xs text-gray-400 p-3 text-center">No test suites available</p>
                ) : (
                  suites.map(s => (
                    <label key={s.id} className="flex items-center gap-3 px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer border-b border-gray-100 dark:border-gray-700 last:border-0">
                      <input
                        type="checkbox"
                        checked={form.suite_ids.includes(s.id)}
                        onChange={() => toggleSuite(s.id)}
                        className="w-3.5 h-3.5 accent-blue-500"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate">{s.name}</div>
                        <div className="text-[10px] text-gray-500">{s.case_count} cases · {s.component || 'General'}</div>
                      </div>
                    </label>
                  ))
                )}
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-medium rounded-lg transition-colors"
              >
                {saving ? 'Saving…' : 'Save Plan'}
              </button>
              <button
                onClick={() => { setCreating(false); setEditing(false) }}
                className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : selectedPlan ? (
          /* ── Plan detail view ── */
          <div className="flex-1 overflow-y-auto">
            {/* Plan header */}
            <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700 flex items-start justify-between">
              <div>
                <h2 className="font-bold text-gray-900 dark:text-white text-base">{selectedPlan.name}</h2>
                {selectedPlan.description && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{selectedPlan.description}</p>
                )}
                <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                  <span>{selectedPlan.platform === 'android' ? '🤖 Android' : '🌐 Web'}</span>
                  <span>·</span>
                  <span>{(selectedPlan.suite_ids || []).length} suite{(selectedPlan.suite_ids || []).length !== 1 ? 's' : ''}</span>
                  <span>·</span>
                  <span>Created {fmtDate(selectedPlan.created_at)}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={openExec}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white text-xs font-medium rounded-lg transition-colors"
                >
                  <Play className="w-3.5 h-3.5" /> Execute
                </button>
                <button
                  onClick={startEdit}
                  className="px-3 py-1.5 text-xs text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                >
                  Edit
                </button>
                <button
                  onClick={handleDelete}
                  className="p-1.5 text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Suites in plan */}
            <div className="p-5">
              <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
                Test Suites in this Plan
              </h3>
              {(selectedPlan.suite_ids || []).length === 0 ? (
                <p className="text-xs text-gray-400 py-4 text-center">No suites selected — click Edit to add some</p>
              ) : (
                <div className="space-y-2">
                  {(selectedPlan.suite_ids || []).map(sid => {
                    const s = suites.find(x => x.id === sid)
                    return (
                      <div key={sid} className="flex items-center gap-3 px-4 py-2.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
                        <FlaskConical className="w-4 h-4 text-blue-400 shrink-0" />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                            {s?.name || 'Unknown suite'}
                          </div>
                          <div className="text-xs text-gray-500">{s?.case_count ?? '?'} cases · {s?.component || 'General'}</div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
            <div className="text-center">
              <ClipboardList className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm font-medium">Select a plan or create a new one</p>
              <button onClick={startCreate} className="mt-3 text-xs text-blue-500 hover:text-blue-400">
                + New test plan
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Execute modal */}
      {showExec && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-gray-900 dark:text-white">Execute Plan</h2>
              <button onClick={() => setShowExec(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              This will create <strong className="text-gray-700 dark:text-gray-200">{(selectedPlan?.suite_ids || []).length}</strong> test run{(selectedPlan?.suite_ids || []).length !== 1 ? 's' : ''}, one per suite.
            </p>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Batch name *</label>
                <input
                  value={execForm.batch_name}
                  onChange={e => setExecForm(f => ({ ...f, batch_name: e.target.value }))}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Platform</label>
                <div className="flex gap-2">
                  {[{ value: 'web', label: '🌐 Web' }, { value: 'android', label: '🤖 Android' }].map(opt => (
                    <button
                      key={opt.value}
                      onClick={() => setExecForm(f => ({ ...f, platform: opt.value }))}
                      className={`flex-1 py-1.5 text-sm rounded-lg border transition-colors ${
                        execForm.platform === opt.value
                          ? 'bg-green-600 border-green-600 text-white'
                          : 'border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
              {envSkills.length > 0 && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Environment</label>
                  <select
                    value={execForm.env_skill_id}
                    onChange={e => setExecForm(f => ({ ...f, env_skill_id: e.target.value }))}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 focus:outline-none"
                  >
                    <option value="">— Select —</option>
                    {envSkills.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </div>
              )}
            </div>
            <div className="flex justify-end gap-3 pt-1">
              <button onClick={() => setShowExec(false)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">Cancel</button>
              <button
                onClick={handleExecute}
                disabled={executing || !execForm.batch_name.trim()}
                className="px-4 py-2 text-sm bg-green-600 hover:bg-green-500 disabled:opacity-40 text-white rounded-lg flex items-center gap-2"
              >
                <Play className="w-3.5 h-3.5" />
                {executing ? 'Starting…' : 'Execute'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── TAB: Runs ──────────────────────────────────────────────────────────────────

function RunsTab() {
  const navigate = useNavigate()
  const [runs, setRuns]           = useState([])
  const [loading, setLoading]     = useState(false)
  const [suites, setSuites]       = useState([])
  const [filterSuite, setFilterSuite]     = useState('')
  const [filterStatus, setFilterStatus]   = useState('')
  const [filterPlatform, setFilterPlatform] = useState('')
  const [search, setSearch]               = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const filters = {}
      if (filterSuite)    filters.suite_id = filterSuite
      if (filterStatus)   filters.status   = filterStatus
      if (filterPlatform) filters.platform = filterPlatform
      filters.limit = 200
      setRuns(await testRunApi.list(filters))
    } catch { toast.error('Failed to load runs') }
    setLoading(false)
  }, [filterSuite, filterStatus, filterPlatform])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 5s while any run is active
  useEffect(() => {
    const hasActive = runs.some(r => r.status === 'running' || r.status === 'pending')
    if (!hasActive) return
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [runs, load])

  useEffect(() => {
    testSuiteApi.listAll().then(setSuites).catch(() => {})
  }, [])

  const filtered = runs.filter(r =>
    !search || r.name?.toLowerCase().includes(search.toLowerCase()) || (r.suite_name || '').toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="px-6 py-3 border-b border-gray-200 dark:border-gray-800 flex items-center gap-3 flex-wrap shrink-0">
        <div className="relative flex-1 min-w-40 max-w-64">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search runs…"
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg outline-none"
          />
        </div>
        <select
          value={filterSuite}
          onChange={e => setFilterSuite(e.target.value)}
          className="text-xs bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-2.5 py-1.5 outline-none"
        >
          <option value="">All suites</option>
          {suites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          className="text-xs bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-2.5 py-1.5 outline-none"
        >
          <option value="">All statuses</option>
          <option value="completed">Completed</option>
          <option value="running">Running</option>
          <option value="pending">Pending</option>
          <option value="terminated">Terminated</option>
          <option value="error">Error</option>
        </select>
        <select
          value={filterPlatform}
          onChange={e => setFilterPlatform(e.target.value)}
          className="text-xs bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-2.5 py-1.5 outline-none"
        >
          <option value="">All platforms</option>
          <option value="web">Web</option>
          <option value="android">Android</option>
        </select>
        <button
          onClick={load}
          className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
        <span className="text-xs text-gray-400 ml-auto">{filtered.length} runs</span>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <ListChecks className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">{loading ? 'Loading…' : 'No runs found'}</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
              <tr>
                <th className="text-left px-6 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Run</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Suite</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Platform</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider w-40">Pass Rate</th>
                <th className="text-right px-6 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {filtered.map(run => {
                const total = run.total_cases || 0
                const passed = run.passed || 0
                const rate = total > 0 ? Math.round(passed / total * 100) : 0
                return (
                  <tr
                    key={run.id}
                    onClick={() => navigate(`/test-runs/${run.id}`)}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer transition-colors"
                  >
                    <td className="px-6 py-3">
                      <div className="font-medium text-gray-900 dark:text-white text-sm truncate max-w-56">{run.name}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-40 block">{run.suite_name || '—'}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-gray-500 dark:text-gray-400">{run.platform === 'android' ? '🤖 Android' : '🌐 Web'}</span>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={run.status} small />
                    </td>
                    <td className="px-4 py-3">
                      {total > 0 ? (
                        <div className="space-y-1">
                          <PassRateBar rate={rate} />
                          <div className="text-[10px] text-gray-500 dark:text-gray-400">{passed}/{total} · {rate}%</div>
                        </div>
                      ) : (
                        <span className="text-xs text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <span className="text-xs text-gray-500 dark:text-gray-400">{fmtDateTime(run.created_at)}</span>
                        <ExternalLink className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ── TAB: Analytics ─────────────────────────────────────────────────────────────

function AnalyticsTab() {
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    testRunApi.analytics()
      .then(setData)
      .catch(() => toast.error('Failed to load analytics'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex-1 flex items-center justify-center text-gray-400">
      <RefreshCw className="w-5 h-5 animate-spin mr-2" /> Loading analytics…
    </div>
  )

  if (!data) return (
    <div className="flex-1 flex items-center justify-center text-gray-400">Failed to load data.</div>
  )

  const trend = data.daily_trend || []
  const suiteStats = data.suite_stats || []
  const failures = data.top_failures || []

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* ── Summary cards ── */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="Total Runs"
          value={data.total_runs}
          sub={`${data.status_breakdown?.completed ?? 0} completed`}
          color="blue"
        />
        <StatCard
          label="Cases Executed"
          value={data.total_cases_executed.toLocaleString()}
          sub={`${data.total_passed} passed · ${data.total_failed} failed`}
          color="indigo"
        />
        <StatCard
          label="Overall Pass Rate"
          value={`${data.overall_pass_rate}%`}
          sub={data.overall_pass_rate >= 80 ? '✅ On target' : data.overall_pass_rate >= 60 ? '⚠️ Below target' : '🔴 Needs attention'}
          color={data.overall_pass_rate >= 80 ? 'green' : data.overall_pass_rate >= 60 ? 'yellow' : 'red'}
        />
        <StatCard
          label="Suites Tested"
          value={suiteStats.length}
          sub={`${data.status_breakdown?.running ?? 0} currently running`}
          color="purple"
        />
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* ── Pass rate by suite ── */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <h3 className="font-semibold text-sm text-gray-700 dark:text-gray-300 mb-4">Pass Rate by Suite</h3>
          {suiteStats.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-6">No completed runs yet</p>
          ) : (
            <div className="space-y-3">
              {suiteStats.map(s => {
                const color = s.pass_rate >= 80 ? '#22c55e' : s.pass_rate >= 60 ? '#eab308' : '#ef4444'
                return (
                  <div key={s.suite_id}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-gray-700 dark:text-gray-300 truncate max-w-48">{s.suite_name}</span>
                      <span className="font-bold ml-2 shrink-0" style={{ color }}>{s.pass_rate}%</span>
                    </div>
                    <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${s.pass_rate}%`, background: color }}
                      />
                    </div>
                    <div className="text-[10px] text-gray-400 mt-0.5">{s.run_count} run{s.run_count !== 1 ? 's' : ''} · {s.passed}/{s.total_cases} cases</div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ── Run trend (SVG line chart) ── */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <h3 className="font-semibold text-sm text-gray-700 dark:text-gray-300 mb-4">Pass Rate Trend (last 60 days)</h3>
          {trend.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-6">No data yet</p>
          ) : (
            <TrendChart data={trend} />
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* ── Top failures ── */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <h3 className="font-semibold text-sm text-gray-700 dark:text-gray-300 mb-4">Top Failing Test Cases</h3>
          {failures.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-6">No failures recorded yet 🎉</p>
          ) : (
            <div className="space-y-2">
              {failures.map((f, i) => (
                <div key={i} className="flex items-center gap-3 py-1.5">
                  <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
                    i === 0 ? 'bg-red-100 dark:bg-red-900/30 text-red-500' :
                    i === 1 ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-500' :
                    'bg-gray-100 dark:bg-gray-800 text-gray-500'
                  }`}>{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-gray-700 dark:text-gray-300 truncate">{f.case_title}</div>
                  </div>
                  <span className="text-xs font-semibold text-red-500 shrink-0">{f.fail_count}×</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Platform breakdown ── */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <h3 className="font-semibold text-sm text-gray-700 dark:text-gray-300 mb-4">Suite Performance Overview</h3>
          {suiteStats.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-6">No data yet</p>
          ) : (
            <SuiteDonutSvg stats={suiteStats} />
          )}
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, sub, color }) {
  const colors = {
    blue:   'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800/50',
    indigo: 'bg-indigo-50 dark:bg-indigo-900/20 border-indigo-200 dark:border-indigo-800/50',
    green:  'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800/50',
    yellow: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800/50',
    red:    'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800/50',
    purple: 'bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800/50',
  }
  const valColors = {
    blue: 'text-blue-600 dark:text-blue-400', indigo: 'text-indigo-600 dark:text-indigo-400',
    green: 'text-green-600 dark:text-green-400', yellow: 'text-yellow-600 dark:text-yellow-400',
    red: 'text-red-600 dark:text-red-400', purple: 'text-purple-600 dark:text-purple-400',
  }
  return (
    <div className={`rounded-xl border p-4 ${colors[color] || colors.blue}`}>
      <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${valColors[color] || valColors.blue}`}>{value}</div>
      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{sub}</div>
    </div>
  )
}

function TrendChart({ data }) {
  const W = 380, H = 120, PAD = { t: 10, r: 10, b: 30, l: 36 }
  const innerW = W - PAD.l - PAD.r
  const innerH = H - PAD.t - PAD.b

  const rates = data.map(d => d.pass_rate)
  const minY = Math.max(0, Math.min(...rates) - 5)
  const maxY = Math.min(100, Math.max(...rates) + 5)

  const xScale = i => PAD.l + (i / Math.max(data.length - 1, 1)) * innerW
  const yScale = v => PAD.t + innerH - ((v - minY) / Math.max(maxY - minY, 1)) * innerH

  const points = data.map((d, i) => [xScale(i), yScale(d.pass_rate)])
  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ')
  const areaPath = linePath + ` L ${points[points.length - 1][0].toFixed(1)} ${(PAD.t + innerH).toFixed(1)} L ${points[0][0].toFixed(1)} ${(PAD.t + innerH).toFixed(1)} Z`

  const yTicks = [minY, (minY + maxY) / 2, maxY].map(v => Math.round(v))

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }}>
      {/* Grid lines */}
      {yTicks.map(v => (
        <g key={v}>
          <line x1={PAD.l} y1={yScale(v)} x2={PAD.l + innerW} y2={yScale(v)} stroke="currentColor" strokeOpacity="0.1" strokeWidth="1" />
          <text x={PAD.l - 4} y={yScale(v) + 4} textAnchor="end" fontSize="9" fill="currentColor" opacity="0.5">{v}%</text>
        </g>
      ))}

      {/* Area */}
      <path d={areaPath} fill="#3b82f6" fillOpacity="0.1" />

      {/* Line */}
      <path d={linePath} fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinejoin="round" />

      {/* Dots */}
      {points.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="3" fill="#3b82f6" />
      ))}

      {/* X axis labels (show every Nth label) */}
      {data.map((d, i) => {
        const step = Math.max(1, Math.floor(data.length / 5))
        if (i % step !== 0 && i !== data.length - 1) return null
        return (
          <text key={i} x={xScale(i)} y={H - 6} textAnchor="middle" fontSize="8" fill="currentColor" opacity="0.5">
            {d.day?.slice(5)}
          </text>
        )
      })}
    </svg>
  )
}

function SuiteDonutSvg({ stats }) {
  // Simple horizontal stacked overview: pass rate distribution
  const buckets = [
    { label: '≥90%', count: stats.filter(s => s.pass_rate >= 90).length, color: '#22c55e' },
    { label: '80–89%', count: stats.filter(s => s.pass_rate >= 80 && s.pass_rate < 90).length, color: '#86efac' },
    { label: '60–79%', count: stats.filter(s => s.pass_rate >= 60 && s.pass_rate < 80).length, color: '#eab308' },
    { label: '<60%', count: stats.filter(s => s.pass_rate < 60).length, color: '#ef4444' },
  ].filter(b => b.count > 0)

  const total = stats.length

  return (
    <div className="space-y-3">
      {buckets.map(b => (
        <div key={b.label} className="flex items-center gap-3">
          <span className="w-16 text-xs text-gray-600 dark:text-gray-400 shrink-0">{b.label}</span>
          <div className="flex-1 h-5 bg-gray-100 dark:bg-gray-800 rounded overflow-hidden">
            <div
              className="h-full rounded flex items-center justify-center text-[10px] font-bold text-white transition-all duration-700"
              style={{ width: `${b.count / total * 100}%`, background: b.color, minWidth: b.count > 0 ? 24 : 0 }}
            >
              {b.count > 0 ? b.count : ''}
            </div>
          </div>
          <span className="text-xs text-gray-400 shrink-0">{b.count} suite{b.count !== 1 ? 's' : ''}</span>
        </div>
      ))}
      <p className="text-[10px] text-gray-400 pt-1">Based on {total} suite{total !== 1 ? 's' : ''} with completed runs</p>
    </div>
  )
}

// ── Main TestPlatform component ────────────────────────────────────────────────

const TABS = [
  { id: 'suites',    label: 'Suites',      icon: FlaskConical  },
  { id: 'plans',     label: 'Plans',       icon: ClipboardList },
  { id: 'runs',      label: 'Runs',        icon: ListChecks    },
  { id: 'analytics', label: 'Analytics',   icon: BarChart2     },
  { id: 'skills',    label: 'Test Skills', icon: Cpu           },
]

export default function TestPlatform({ agents, onUpdate }) {
  const { tab: tabParam } = useParams()
  const navigate = useNavigate()
  const [tab, setTab] = useState(tabParam || 'suites')
  const [suites, setSuites] = useState([])

  useEffect(() => {
    if (tabParam && tabParam !== tab) setTab(tabParam)
  }, [tabParam])

  useEffect(() => {
    testSuiteApi.listAll().then(setSuites).catch(() => {})
  }, [])

  function switchTab(t) {
    setTab(t)
    navigate(`/test-platform/${t}`, { replace: true })
  }

  return (
    <div className="flex flex-col h-full overflow-hidden bg-white dark:bg-gray-950">
      {/* Tab bar */}
      <div className="shrink-0 border-b border-gray-200 dark:border-gray-800 px-6 flex items-center gap-1 bg-white dark:bg-gray-950">
        <span className="text-sm font-bold text-gray-900 dark:text-white mr-4 py-3">🧪 Test Platform</span>
        {TABS.map(t => {
          const Icon = t.icon
          const active = tab === t.id
          return (
            <button
              key={t.id}
              onClick={() => switchTab(t.id)}
              className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                active
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {tab === 'suites'    && <TestSuitePanel agents={agents} onUpdate={onUpdate} />}
        {tab === 'plans'     && <PlansTab suites={suites} />}
        {tab === 'runs'      && <RunsTab />}
        {tab === 'analytics' && <AnalyticsTab />}
        {tab === 'skills'    && <BrowserSkillsPanel />}
      </div>
    </div>
  )
}
