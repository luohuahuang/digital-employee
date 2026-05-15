import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Download, Trash2, ChevronDown, ChevronUp, X, GitBranch, Search, Play, Pencil } from 'lucide-react'
import { testSuiteApi, testRunApi, api } from '../api/client.js'
import toast from 'react-hot-toast'

const PRIORITY_COLORS = {
  P0: 'bg-red-900/30 text-red-400',
  P1: 'bg-orange-900/30 text-orange-400',
  P2: 'bg-yellow-900/30 text-yellow-400',
  P3: 'bg-gray-900/30 text-gray-400',
}

const PRIORITY_HEX = { P0: '#ef4444', P1: '#f97316', P2: '#eab308', P3: '#6b7280' }

const SOURCE_LABELS = { all: 'All', jira: 'Jira', mr: 'MR', manual: 'Manual' }

// ── Mind Map Modal ─────────────────────────────────────────────────────────────
function MindMapModal({ suite, onClose }) {
  const casesByCategory = suite.cases.reduce((acc, c) => {
    const cat = c.category || 'General'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(c)
    return acc
  }, {})

  const categories = Object.entries(casesByCategory)

  const ROW_H = 28
  const PAD_TOP = 40
  const ROOT_X = 20
  const ROOT_W = 130
  const CAT_X = 190
  const CAT_W = 90
  const CASE_X = 320
  const CASE_W = 200
  const PRI_X = 526

  // Calculate y positions
  let y = PAD_TOP
  const catRows = categories.map(([catName, cases]) => {
    const startY = y
    const caseRows = cases.map(tc => {
      const cy = y + ROW_H / 2
      y += ROW_H
      return { ...tc, cy }
    })
    const endY = y - ROW_H / 2
    return { catName, cases: caseRows, catY: (startY + endY) / 2 }
  })

  const svgH = Math.max(y + PAD_TOP, 200)
  const rootY = svgH / 2
  const svgW = 560

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-gray-950 rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800 shrink-0">
          <div>
            <h2 className="font-bold text-white text-sm">{suite.name}</h2>
            <p className="text-gray-400 text-xs mt-0.5">{suite.cases.length} test cases · {categories.length} categories</p>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-3 px-5 py-2 border-b border-gray-800 text-xs text-gray-400 shrink-0">
          <span>Priority:</span>
          {Object.entries(PRIORITY_HEX).map(([p, color]) => (
            <span key={p} className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: color }} />
              {p}
            </span>
          ))}
        </div>

        {/* SVG mind map */}
        <div className="flex-1 overflow-auto p-4">
          <svg width={svgW} height={svgH} style={{ minWidth: svgW }}>
            {/* Root → Category edges */}
            {catRows.map((cat, i) => (
              <path
                key={`re-${i}`}
                d={`M ${ROOT_X + ROOT_W} ${rootY} C ${CAT_X - 30} ${rootY}, ${CAT_X - 30} ${cat.catY}, ${CAT_X} ${cat.catY}`}
                fill="none" stroke="#4b5563" strokeWidth="1.5"
              />
            ))}

            {/* Category → Case edges */}
            {catRows.map((cat, ci) =>
              cat.cases.map((tc, ti) => (
                <path
                  key={`ce-${ci}-${ti}`}
                  d={`M ${CAT_X + CAT_W} ${cat.catY} C ${CASE_X - 20} ${cat.catY}, ${CASE_X - 20} ${tc.cy}, ${CASE_X} ${tc.cy}`}
                  fill="none"
                  stroke={PRIORITY_HEX[tc.priority] || '#6b7280'}
                  strokeWidth="1"
                  opacity="0.5"
                />
              ))
            )}

            {/* Root node */}
            <rect x={ROOT_X} y={rootY - 22} width={ROOT_W} height={44} rx={8} fill="#1d4ed8" />
            <text x={ROOT_X + ROOT_W / 2} y={rootY - 4} textAnchor="middle" fill="white" fontSize="10" fontWeight="700">
              {suite.name.length > 16 ? suite.name.slice(0, 16) + '…' : suite.name}
            </text>
            <text x={ROOT_X + ROOT_W / 2} y={rootY + 11} textAnchor="middle" fill="#93c5fd" fontSize="9">
              {suite.cases.length} cases
            </text>

            {/* Category nodes */}
            {catRows.map((cat, i) => (
              <g key={`cat-${i}`}>
                <rect x={CAT_X} y={cat.catY - 14} width={CAT_W} height={28} rx={6} fill="#1e3a5f" />
                <text x={CAT_X + CAT_W / 2} y={cat.catY + 5} textAnchor="middle" fill="#93c5fd" fontSize="9" fontWeight="600">
                  {cat.catName.length > 11 ? cat.catName.slice(0, 11) + '…' : cat.catName}
                </text>
              </g>
            ))}

            {/* Test case leaf nodes */}
            {catRows.map((cat) =>
              cat.cases.map((tc, i) => {
                const color = PRIORITY_HEX[tc.priority] || '#6b7280'
                return (
                  <g key={`tc-${tc.id}`}>
                    <rect x={CASE_X} y={tc.cy - 10} width={CASE_W} height={20} rx={3} fill={color} opacity="0.08" />
                    <rect x={CASE_X} y={tc.cy - 10} width={3} height={20} rx={1} fill={color} />
                    <text x={CASE_X + 8} y={tc.cy + 4} fill="#d1d5db" fontSize="9">
                      {tc.title.length > 30 ? tc.title.slice(0, 30) + '…' : tc.title}
                    </text>
                    <text x={PRI_X} y={tc.cy + 4} fill={color} fontSize="8" fontWeight="700">
                      {tc.priority}
                    </text>
                  </g>
                )
              })
            )}
          </svg>
        </div>
      </div>
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function TestSuitePanel({ agents, onUpdate }) {
  const navigate = useNavigate()
  const [suites, setSuites] = useState([])
  const [components, setComponents] = useState([])
  const [selectedComponent, setSelectedComponent] = useState('')  // '' = All
  const [sourceFilter, setSourceFilter] = useState('all')
  const [searchText, setSearchText] = useState('')
  const [priorityFilter, setPriorityFilter] = useState('all')  // for cases within suite

  const [selectedSuite, setSelectedSuite] = useState(null)
  const [suiteDetail, setSuiteDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [expandedCategory, setExpandedCategory] = useState({})
  const [newCaseMode, setNewCaseMode] = useState(false)
  const [newCaseData, setNewCaseData] = useState({
    title: '', category: '', preconditions: '', steps: [''], expected: '', priority: 'P1',
  })
  const [editingCaseId, setEditingCaseId] = useState(null)
  const [editForm, setEditForm] = useState(null)
  const [showMindMap, setShowMindMap] = useState(false)
  const [showRunModal, setShowRunModal] = useState(false)
  const [runForm, setRunForm] = useState({ name: '', env_skill_id: '', extra_skill_ids: [], platform: 'web' })
  const [envSkills, setEnvSkills] = useState([])
  const [extraSkills, setExtraSkills] = useState([])
  const [starting, setStarting] = useState(false)

  // Load components for dropdown
  useEffect(() => {
    testSuiteApi.listComponents()
      .then(data => setComponents(data || []))
      .catch(() => {})
  }, [])

  // Load suites when component filter changes
  const loadSuites = useCallback(async () => {
    setLoading(true)
    try {
      const filters = {}
      if (selectedComponent) filters.component = selectedComponent
      const data = await testSuiteApi.listAll(filters)
      setSuites(data || [])
      setSelectedSuite(null)
      setSuiteDetail(null)
    } catch {
      toast.error('Failed to load test suites')
    }
    setLoading(false)
  }, [selectedComponent])

  useEffect(() => { loadSuites() }, [loadSuites])

  // Load suite detail
  useEffect(() => {
    if (!selectedSuite) { setSuiteDetail(null); return }
    testSuiteApi.get(selectedSuite)
      .then(setSuiteDetail)
      .catch(() => toast.error('Failed to load suite details'))
  }, [selectedSuite])

  // Client-side filtered suite list
  const filteredSuites = suites.filter(s => {
    if (sourceFilter !== 'all' && s.source_type !== sourceFilter) return false
    if (searchText && !s.name.toLowerCase().includes(searchText.toLowerCase())) return false
    return true
  })

  // Group cases by category (with optional priority filter)
  const casesByCategory = suiteDetail
    ? suiteDetail.cases
        .filter(c => priorityFilter === 'all' || c.priority === priorityFilter)
        .reduce((acc, c) => {
          const cat = c.category || 'General'
          if (!acc[cat]) acc[cat] = []
          acc[cat].push(c)
          return acc
        }, {})
    : {}

  async function handleDeleteSuite() {
    if (!selectedSuite) return
    if (!confirm('Delete this test suite? This cannot be undone.')) return
    try {
      await testSuiteApi.delete(selectedSuite)
      toast.success('Suite deleted')
      loadSuites()
    } catch { toast.error('Failed to delete suite') }
  }

  async function handleDeleteCase(caseId) {
    if (!selectedSuite) return
    try {
      await testSuiteApi.deleteCase(selectedSuite, caseId)
      toast.success('Case deleted')
      setSuiteDetail(await testSuiteApi.get(selectedSuite))
    } catch { toast.error('Failed to delete case') }
  }

  function startEditCase(tc) {
    setEditingCaseId(tc.id)
    setEditForm({
      title: tc.title || '',
      category: tc.category || '',
      preconditions: tc.preconditions || '',
      steps: (tc.steps && tc.steps.length > 0) ? [...tc.steps] : [''],
      expected: tc.expected || '',
      priority: tc.priority || 'P1',
    })
  }

  async function handleUpdateCase() {
    if (!selectedSuite || !editingCaseId) return
    if (!editForm.title || !editForm.expected) {
      toast.error('Fill in title and expected result')
      return
    }
    try {
      await testSuiteApi.updateCase(selectedSuite, editingCaseId, {
        ...editForm,
        steps: editForm.steps.filter(s => s.trim()),
      })
      toast.success('Case updated')
      setSuiteDetail(await testSuiteApi.get(selectedSuite))
      setEditingCaseId(null)
      setEditForm(null)
    } catch { toast.error('Failed to update case') }
  }

  async function handleAddCase() {
    if (!selectedSuite || !newCaseData.title || !newCaseData.expected) {
      toast.error('Fill in title and expected result')
      return
    }
    try {
      await testSuiteApi.addCase(selectedSuite, {
        ...newCaseData,
        steps: newCaseData.steps.filter(s => s.trim()),
      })
      toast.success('Case added')
      setSuiteDetail(await testSuiteApi.get(selectedSuite))
      setNewCaseData({ title: '', category: '', preconditions: '', steps: [''], expected: '', priority: 'P1' })
      setNewCaseMode(false)
    } catch { toast.error('Failed to add case') }
  }

  async function handleExportMarkdown() {
    if (!selectedSuite) return
    try {
      const text = await testSuiteApi.exportMarkdown(selectedSuite)
      const a = document.createElement('a')
      a.href = 'data:text/markdown;charset=utf-8,' + encodeURIComponent(text)
      a.download = `${suiteDetail.name.replace(/\s+/g, '_')}.md`
      a.click()
      toast.success('Markdown exported')
    } catch { toast.error('Failed to export markdown') }
  }

  async function handleExportXMind() {
    if (!selectedSuite) return
    try {
      const blob = await testSuiteApi.exportXMind(selectedSuite)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${suiteDetail.name.replace(/\s+/g, '_')}.xmind`
      a.click()
      window.URL.revokeObjectURL(url)
      toast.success('XMind exported')
    } catch { toast.error('Failed to export XMind') }
  }

  async function handleOpenRunModal() {
    setRunForm({ name: `${suiteDetail.name} — Run`, env_skill_id: '', extra_skill_ids: [], platform: 'web' })
    try {
      const [envData, extraData] = await Promise.all([
        api.get('/browser-skills', { params: { type: 'environment' } }).then(r => r.data),
        api.get('/browser-skills', { params: { type: 'extra' } }).then(r => r.data),
      ])
      setEnvSkills(envData)
      setExtraSkills(extraData)
      // Pre-select first env skill if only one exists
      if (envData.length === 1) setRunForm(f => ({ ...f, env_skill_id: envData[0].id }))
    } catch { /* skills optional */ }
    setShowRunModal(true)
  }

  async function handleStartRun() {
    if (!selectedSuite || !runForm.name.trim()) return
    setStarting(true)
    try {
      const { run_id } = await testRunApi.start({
        suite_id:        selectedSuite,
        name:            runForm.name.trim(),
        env_skill_id:    runForm.env_skill_id || null,
        extra_skill_ids: runForm.extra_skill_ids,
        platform:        runForm.platform,
      })
      setShowRunModal(false)
      toast.success('Test run started')
      navigate(`/test-runs/${run_id}`)
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to start run')
    } finally {
      setStarting(false)
    }
  }

  function toggleExtraSkill(id) {
    setRunForm(f => ({
      ...f,
      extra_skill_ids: f.extra_skill_ids.includes(id)
        ? f.extra_skill_ids.filter(x => x !== id)
        : [...f.extra_skill_ids, id],
    }))
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Header bar ── */}
      <div className="px-6 py-3 border-b border-gray-200 dark:border-gray-800 shrink-0 space-y-2">
        {/* Row 1: title + action buttons */}
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-lg font-bold shrink-0">📋 Test Suites</h1>

          <button
            onClick={loadSuites}
            disabled={loading}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-xs font-medium text-white rounded-lg transition-colors"
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>

          {selectedSuite && suiteDetail && (
            <div className="flex items-center gap-2 ml-auto flex-wrap">
              <button
                onClick={handleOpenRunModal}
                className="px-3 py-1.5 bg-green-600/20 border border-green-600/40 text-green-400 text-xs rounded-lg hover:bg-green-600/30 flex items-center gap-1.5"
              >
                <Play className="w-3.5 h-3.5" /> Run
              </button>
              <button
                onClick={() => setShowMindMap(true)}
                className="px-3 py-1.5 bg-indigo-600/20 border border-indigo-600/40 text-indigo-400 text-xs rounded-lg hover:bg-indigo-600/30 flex items-center gap-1.5"
              >
                <GitBranch className="w-3.5 h-3.5" /> Mind Map
              </button>
              <button
                onClick={handleExportMarkdown}
                className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-xs rounded-lg hover:border-gray-500 flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" /> Markdown
              </button>
              <button
                onClick={handleExportXMind}
                className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-xs rounded-lg hover:border-gray-500 flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" /> XMind
              </button>
              <button
                onClick={handleDeleteSuite}
                className="px-3 py-1.5 bg-red-600/20 border border-red-600/30 text-red-400 text-xs rounded-lg hover:bg-red-600/30 flex items-center gap-1.5"
              >
                <Trash2 className="w-3.5 h-3.5" /> Delete
              </button>
            </div>
          )}
        </div>

        {/* Row 2: filters */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Product Line dropdown */}
          <select
            value={selectedComponent}
            onChange={e => setSelectedComponent(e.target.value)}
            className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-xs rounded-lg px-2.5 py-1.5 outline-none"
          >
            <option value="">All product lines</option>
            {components.map(c => <option key={c} value={c}>{c}</option>)}
          </select>

          {/* Source type pills */}
          <div className="flex items-center gap-1">
            {Object.entries(SOURCE_LABELS).map(([val, label]) => (
              <button
                key={val}
                onClick={() => setSourceFilter(val)}
                className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                  sourceFilter === val
                    ? 'bg-blue-600 border-blue-600 text-white'
                    : 'border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-gray-500'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Search box */}
          <div className="relative flex-1 min-w-32 max-w-56">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
            <input
              type="text"
              placeholder="Search suites…"
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-xs rounded-lg pl-7 pr-2.5 py-1.5 outline-none placeholder-gray-400"
            />
          </div>
        </div>
      </div>

      {/* ── Body: list + detail ── */}
      <div className="flex flex-1 overflow-hidden gap-4 px-6 py-4">
        {/* Left: suite list */}
        <div className="w-60 flex flex-col border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900/50 shrink-0 overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {filteredSuites.length} suite{filteredSuites.length !== 1 ? 's' : ''}
              {filteredSuites.length !== suites.length && ` (of ${suites.length})`}
            </span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-1 p-1.5">
            {filteredSuites.map(suite => (
              <button
                key={suite.id}
                onClick={() => setSelectedSuite(suite.id)}
                className={`w-full text-left p-2.5 rounded-lg text-xs transition-colors ${
                  selectedSuite === suite.id
                    ? 'bg-blue-600 text-white'
                    : 'hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-900 dark:text-gray-300'
                }`}
              >
                <div className="font-medium truncate">{suite.name}</div>
                <div className={`flex items-center gap-1.5 mt-0.5 ${selectedSuite === suite.id ? 'text-blue-200' : 'text-gray-500'}`}>
                  <span className="text-[10px]">{suite.case_count} case{suite.case_count !== 1 ? 's' : ''}</span>
                  <span className="text-[10px]">·</span>
                  <span className="text-[10px] uppercase">{suite.source_type}</span>
                  {suite.component && (
                    <>
                      <span className="text-[10px]">·</span>
                      <span className="text-[10px]">{suite.component}</span>
                    </>
                  )}
                </div>
              </button>
            ))}
            {filteredSuites.length === 0 && (
              <div className="text-center text-gray-500 dark:text-gray-500 py-8 text-xs">
                {suites.length === 0 ? 'No test suites yet' : 'No matching suites'}
              </div>
            )}
          </div>
        </div>

        {/* Right: suite detail */}
        <div className="flex-1 flex flex-col overflow-hidden border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900/50">
          {suiteDetail ? (
            <>
              {/* Suite header + priority filter */}
              <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 shrink-0">
                <h2 className="font-bold text-gray-900 dark:text-white text-sm mb-0.5">{suiteDetail.name}</h2>
                {suiteDetail.description && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{suiteDetail.description}</p>
                )}
                {/* Priority filter pills */}
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-gray-500 dark:text-gray-400 mr-1">Priority:</span>
                  {['all', 'P0', 'P1', 'P2', 'P3'].map(p => (
                    <button
                      key={p}
                      onClick={() => setPriorityFilter(p)}
                      className={`px-2 py-0.5 text-[10px] rounded-full border transition-colors ${
                        priorityFilter === p
                          ? p === 'all'
                            ? 'bg-gray-600 border-gray-600 text-white'
                            : `border-transparent text-white`
                          : 'border-gray-300 dark:border-gray-700 text-gray-500 hover:border-gray-400'
                      }`}
                      style={priorityFilter === p && p !== 'all' ? { background: PRIORITY_HEX[p] } : {}}
                    >
                      {p === 'all' ? 'All' : p}
                    </button>
                  ))}
                  <span className="text-[10px] text-gray-400 ml-1">
                    {Object.values(casesByCategory).flat().length} shown
                  </span>
                </div>
              </div>

              {/* Cases list */}
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {Object.keys(casesByCategory).length === 0 ? (
                  <div className="text-center text-gray-500 py-8 text-xs">No test cases</div>
                ) : (
                  Object.entries(casesByCategory).map(([category, cases]) => (
                    <div key={category} className="border border-gray-300 dark:border-gray-700 rounded-lg overflow-hidden">
                      <button
                        onClick={() => setExpandedCategory(prev => ({ ...prev, [category]: !prev[category] }))}
                        className="w-full flex items-center justify-between px-3 py-2 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-gray-900 dark:text-white">{category}</span>
                          <span className="text-xs bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-300 px-2 py-0.5 rounded">
                            {cases.length}
                          </span>
                        </div>
                        {expandedCategory[category] ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>

                      {expandedCategory[category] && (
                        <div className="space-y-2 p-2 bg-white dark:bg-gray-900">
                          {cases.map(tc => (
                            <div key={tc.id} className="border border-gray-300 dark:border-gray-700 rounded-lg p-2">
                              {editingCaseId === tc.id && editForm ? (
                                /* ── Inline edit form ── */
                                <div className="space-y-1.5">
                                  <input
                                    type="text" placeholder="Title"
                                    value={editForm.title}
                                    onChange={e => setEditForm({ ...editForm, title: e.target.value })}
                                    className="w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none"
                                  />
                                  <div className="flex gap-1.5">
                                    <input
                                      type="text" placeholder="Category"
                                      value={editForm.category}
                                      onChange={e => setEditForm({ ...editForm, category: e.target.value })}
                                      className="flex-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none"
                                    />
                                    <select
                                      value={editForm.priority}
                                      onChange={e => setEditForm({ ...editForm, priority: e.target.value })}
                                      className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none"
                                    >
                                      <option>P0</option><option>P1</option><option>P2</option><option>P3</option>
                                    </select>
                                  </div>
                                  <textarea
                                    placeholder="Preconditions (optional)"
                                    value={editForm.preconditions}
                                    onChange={e => setEditForm({ ...editForm, preconditions: e.target.value })}
                                    rows={2}
                                    className="w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none resize-y"
                                  />
                                  <div>
                                    <label className="text-[10px] font-semibold text-gray-500 dark:text-gray-400 mb-0.5 block">Steps</label>
                                    {editForm.steps.map((step, i) => (
                                      <input
                                        key={i} type="text" value={step}
                                        onChange={e => {
                                          const s = [...editForm.steps]; s[i] = e.target.value
                                          setEditForm({ ...editForm, steps: s })
                                        }}
                                        placeholder={`Step ${i + 1}`}
                                        className="w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none mb-1"
                                      />
                                    ))}
                                    <button
                                      onClick={() => setEditForm({ ...editForm, steps: [...editForm.steps, ''] })}
                                      className="text-xs text-blue-600 hover:text-blue-500"
                                    >+ Add step</button>
                                  </div>
                                  <textarea
                                    placeholder="Expected result"
                                    value={editForm.expected}
                                    onChange={e => setEditForm({ ...editForm, expected: e.target.value })}
                                    rows={2}
                                    className="w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none resize-y"
                                  />
                                  <div className="flex gap-1.5 pt-0.5">
                                    <button
                                      onClick={handleUpdateCase}
                                      className="flex-1 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium rounded transition-colors"
                                    >Save</button>
                                    <button
                                      onClick={() => { setEditingCaseId(null); setEditForm(null) }}
                                      className="flex-1 py-1 bg-gray-300 dark:bg-gray-700 text-gray-900 dark:text-white text-xs font-medium rounded transition-colors"
                                    >Cancel</button>
                                  </div>
                                </div>
                              ) : (
                                /* ── Read-only view ── */
                                <>
                                  <div className="flex items-start justify-between mb-1">
                                    <div className="flex-1 min-w-0">
                                      <p className="font-semibold text-xs text-gray-900 dark:text-white">{tc.title}</p>
                                      <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded mt-0.5 ${PRIORITY_COLORS[tc.priority]}`}>
                                        {tc.priority}
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-0.5 shrink-0">
                                      <button
                                        onClick={() => startEditCase(tc)}
                                        className="p-0.5 text-gray-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                                        title="Edit"
                                      >
                                        <Pencil className="w-3.5 h-3.5" />
                                      </button>
                                      <button
                                        onClick={() => handleDeleteCase(tc.id)}
                                        className="p-0.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                                        title="Delete"
                                      >
                                        <X className="w-3.5 h-3.5" />
                                      </button>
                                    </div>
                                  </div>

                                  {tc.preconditions && (
                                    <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                                      <strong>Pre:</strong> {tc.preconditions}
                                    </div>
                                  )}

                                  {tc.steps && tc.steps.length > 0 && (
                                    <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                                      <strong>Steps:</strong>
                                      <ol className="ml-4 list-decimal text-gray-600 dark:text-gray-400">
                                        {tc.steps.map((s, i) => <li key={i}>{s}</li>)}
                                      </ol>
                                    </div>
                                  )}

                                  <div className="text-xs text-gray-600 dark:text-gray-400">
                                    <strong>Expected:</strong> {tc.expected}
                                  </div>
                                </>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}

                {/* Add case form */}
                {newCaseMode ? (
                  <div className="border border-blue-300 dark:border-blue-700 rounded-lg p-3 bg-blue-50 dark:bg-blue-900/20 space-y-2">
                    <h3 className="font-semibold text-sm text-gray-900 dark:text-white">Add Test Case</h3>
                    <input
                      type="text" placeholder="Title"
                      value={newCaseData.title}
                      onChange={e => setNewCaseData({ ...newCaseData, title: e.target.value })}
                      className="w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none"
                    />
                    <input
                      type="text" placeholder="Category (optional)"
                      value={newCaseData.category}
                      onChange={e => setNewCaseData({ ...newCaseData, category: e.target.value })}
                      className="w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none"
                    />
                    <textarea
                      placeholder="Preconditions (optional)"
                      value={newCaseData.preconditions}
                      onChange={e => setNewCaseData({ ...newCaseData, preconditions: e.target.value })}
                      rows={2}
                      className="w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none resize-y"
                    />
                    <div>
                      <label className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1 block">Steps</label>
                      {newCaseData.steps.map((step, i) => (
                        <input
                          key={i} type="text" value={step}
                          onChange={e => {
                            const s = [...newCaseData.steps]
                            s[i] = e.target.value
                            setNewCaseData({ ...newCaseData, steps: s })
                          }}
                          placeholder={`Step ${i + 1}`}
                          className="w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none mb-1"
                        />
                      ))}
                      <button
                        onClick={() => setNewCaseData({ ...newCaseData, steps: [...newCaseData.steps, ''] })}
                        className="text-xs text-blue-600 hover:text-blue-500"
                      >
                        + Add step
                      </button>
                    </div>
                    <textarea
                      placeholder="Expected result"
                      value={newCaseData.expected}
                      onChange={e => setNewCaseData({ ...newCaseData, expected: e.target.value })}
                      rows={2}
                      className="w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none resize-y"
                    />
                    <select
                      value={newCaseData.priority}
                      onChange={e => setNewCaseData({ ...newCaseData, priority: e.target.value })}
                      className="w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs outline-none"
                    >
                      <option>P0</option><option>P1</option><option>P2</option><option>P3</option>
                    </select>
                    <div className="flex gap-2">
                      <button
                        onClick={handleAddCase}
                        className="flex-1 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium rounded transition-colors"
                      >
                        Save Case
                      </button>
                      <button
                        onClick={() => setNewCaseMode(false)}
                        className="flex-1 py-1 bg-gray-300 dark:bg-gray-700 text-gray-900 dark:text-white text-xs font-medium rounded transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => setNewCaseMode(true)}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-gray-200 dark:bg-gray-800 hover:bg-gray-300 dark:hover:bg-gray-700 rounded-lg text-sm font-medium transition-colors text-gray-900 dark:text-white"
                  >
                    <Plus className="w-3.5 h-3.5" /> Add Case
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-center text-gray-500 dark:text-gray-400">
              <div>
                <p className="font-medium">Select a test suite to view details</p>
                <p className="text-sm mt-1">Or create a new one using the agent chat</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Mind map modal */}
      {showMindMap && suiteDetail && (
        <MindMapModal suite={suiteDetail} onClose={() => setShowMindMap(false)} />
      )}

      {/* Start Run modal */}
      {showRunModal && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-gray-900 dark:text-white">Start Test Run</h2>
              <button onClick={() => setShowRunModal(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Suite: <span className="font-medium text-gray-700 dark:text-gray-300">{suiteDetail?.name}</span>
            </p>
            <div className="space-y-4">
              {/* Platform selector */}
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Platform</label>
                <div className="flex gap-2">
                  {[
                    { value: 'web',     label: '🌐 Web' },
                    { value: 'android', label: '🤖 Android' },
                  ].map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setRunForm(f => ({ ...f, platform: opt.value }))}
                      className={`flex-1 py-1.5 text-sm rounded-lg border transition-colors ${
                        runForm.platform === opt.value
                          ? 'bg-green-600 border-green-600 text-white'
                          : 'border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-green-500'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Run name */}
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Run name</label>
                <input
                  value={runForm.name}
                  onChange={e => setRunForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-green-500"
                  placeholder="e.g. Sprint 16 regression"
                />
              </div>

              {/* Environment skill */}
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Environment{' '}
                  <span className="text-gray-400 font-normal">
                    {runForm.platform === 'android'
                      ? '(provides app_package + device + credentials)'
                      : '(provides base URL + credentials)'}
                  </span>
                </label>
                {envSkills.length === 0 ? (
                  <p className="text-xs text-amber-500 py-1">
                    No environment skills yet —{' '}
                    <a href="/browser-skills" className="underline">create one</a> first.
                  </p>
                ) : (
                  <select
                    value={runForm.env_skill_id}
                    onChange={e => setRunForm(f => ({ ...f, env_skill_id: e.target.value }))}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-green-500"
                  >
                    <option value="">— Select environment —</option>
                    {envSkills.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                )}
              </div>

              {/* Extra skills */}
              {extraSkills.length > 0 && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                    Extra Skills <span className="text-gray-400 font-normal">(optional, multi-select)</span>
                  </label>
                  <div className="space-y-1.5 max-h-36 overflow-y-auto">
                    {extraSkills.map(s => (
                      <label key={s.id} className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={runForm.extra_skill_ids.includes(s.id)}
                          onChange={() => toggleExtraSkill(s.id)}
                          className="w-3.5 h-3.5 accent-green-500"
                        />
                        <span className="text-sm text-gray-700 dark:text-gray-300">{s.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setShowRunModal(false)}
                className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleStartRun}
                disabled={starting || !runForm.name.trim() || !runForm.env_skill_id}
                className="px-4 py-2 text-sm bg-green-600 hover:bg-green-500 disabled:opacity-40 text-white rounded-lg flex items-center gap-2 transition-colors"
              >
                <Play className="w-3.5 h-3.5" />
                {starting ? 'Starting…' : 'Start Run'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
