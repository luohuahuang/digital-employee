import { useState, useEffect, useCallback, useRef } from 'react'
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import {
  Play, RefreshCw, ChevronDown, ChevronUp, Users,
  Plus, Pencil, Trash2, Award, GitCompare, Lightbulb, CheckCircle2,
} from 'lucide-react'
import { examApi, agentApi } from '../api/client.js'
import toast from 'react-hot-toast'

const PALETTE = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899']

const ROLE_ORDER_EXAM = ['QA', 'Dev', 'PM', 'SRE', 'PJ', 'Other']
const ROLE_COLORS_EXAM = {
  QA:    { bg: 'bg-purple-900/30', text: 'text-purple-400', dot: 'bg-purple-400' },
  Dev:   { bg: 'bg-blue-900/30',   text: 'text-blue-400',   dot: 'bg-blue-400'   },
  PM:    { bg: 'bg-orange-900/30', text: 'text-orange-400', dot: 'bg-orange-400' },
  SRE:   { bg: 'bg-red-900/30',    text: 'text-red-400',    dot: 'bg-red-400'    },
  PJ:    { bg: 'bg-teal-900/30',   text: 'text-teal-400',   dot: 'bg-teal-400'   },
  Other: { bg: 'bg-gray-800/50',   text: 'text-gray-400',   dot: 'bg-gray-500'   },
}

function examRole(examOrId) {
  // Accept either a full exam object (with .role / .id) or a plain id string
  if (examOrId && typeof examOrId === 'object') {
    if (examOrId.role) return examOrId.role
    return examRole(examOrId.id || '')
  }
  const id = examOrId || ''
  const prefix = id.split('-')[0].toUpperCase()
  if (prefix === 'QA')  return 'QA'
  if (prefix === 'DEV') return 'Dev'
  if (prefix === 'PM')  return 'PM'
  if (prefix === 'SRE') return 'SRE'
  if (prefix === 'PJ')  return 'PJ'
  return 'Other'
}

const RANKINGS = ['Intern', 'Junior', 'Senior', 'Lead']
const RANKING_STYLE = {
  Intern: 'bg-gray-600 text-gray-200',
  Junior: 'bg-blue-700 text-blue-100',
  Senior: 'bg-green-700 text-green-100',
  Lead:   'bg-yellow-600 text-yellow-100',
}
const RANKING_DESC = {
  Intern: 'L1 auto only — L2 requires Mentor approval',
  Junior: 'L1 auto only — L2 requires Mentor approval',
  Senior: 'L1 + L2 auto — trusted for production actions',
  Lead:   'L1 + L2 + L3 auto — full autonomy',
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function ExamPanel({ agents, onUpdate }) {
  const [exams,            setExams]           = useState([])
  const [selectedAgent,    setSelectedAgent]   = useState('all')
  const [selectedExams,    setSelectedExams]   = useState(new Set())
  const [showSelector,     setShowSelector]    = useState(false)
  const [runs,             setRuns]            = useState([])
  const [expanded,         setExpanded]        = useState(null)
  const [mentorInputs,     setMentorInputs]    = useState({})
  const [activeTab,        setActiveTab]       = useState('history')
  const [compareIds,       setCompareIds]      = useState([])
  const [compareRuns,      setCompareRuns]     = useState([])
  const [versionMatrix,    setVersionMatrix]   = useState(null)
  const [loading,          setLoading]         = useState(false)
  const [examForm,         setExamForm]        = useState(null)
  const [selectorSearch,   setSelectorSearch]  = useState('')
  const [selectorRole,     setSelectorRole]    = useState('all')
  const [rankingModal,     setRankingModal]    = useState(false)
  const [rankingChoice,    setRankingChoice]   = useState(null)
  const pollRef = useRef(null)

  const currentAgent = agents.find(a => a.id === selectedAgent)

  // ── Load exam definitions ────────────────────────────────────────────────────
  const loadExams = useCallback(() => {
    examApi.list().then(setExams).catch(() => {})
  }, [])

  useEffect(() => { loadExams() }, [loadExams])

  // ── Load run history ─────────────────────────────────────────────────────────
  const loadRuns = useCallback(async () => {
    setLoading(true)
    try {
      if (selectedAgent === 'all') {
        const all = await Promise.all(agents.map(a => examApi.listRuns(a.id).catch(() => [])))
        setRuns(all.flat().sort((a, b) => new Date(b.created_at) - new Date(a.created_at)))
      } else {
        setRuns(await examApi.listRuns(selectedAgent))
      }
    } catch { /* silent */ }
    setLoading(false)
  }, [selectedAgent, agents])

  useEffect(() => { loadRuns() }, [loadRuns])

  // ── Load version matrix when tab is active and agent selected ────────────────
  useEffect(() => {
    if (activeTab !== 'versions' || !selectedAgent || selectedAgent === 'all') {
      setVersionMatrix(null)
      return
    }
    examApi.versionMatrix(selectedAgent)
      .then(setVersionMatrix)
      .catch(() => setVersionMatrix(null))
  }, [activeTab, selectedAgent])

  // ── Poll running runs every 3s ───────────────────────────────────────────────
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    const running = runs.filter(r => r.status === 'running')
    if (running.length === 0) return

    pollRef.current = setInterval(async () => {
      const refreshed = await Promise.all(running.map(r => examApi.getRun(r.id).catch(() => r)))
      const byId = Object.fromEntries(refreshed.map(r => [r.id, r]))
      setRuns(prev => prev.map(r => byId[r.id] ?? r))
      if (!refreshed.some(r => r.status === 'running')) {
        clearInterval(pollRef.current)
        toast.success('Exam run(s) completed ✅')
      }
    }, 3000)

    return () => clearInterval(pollRef.current)
  }, [runs])

  // ── Load comparison data ─────────────────────────────────────────────────────
  useEffect(() => {
    if (compareIds.length === 0) { setCompareRuns([]); return }
    examApi.compare(compareIds).then(setCompareRuns).catch(() => {})
  }, [compareIds])

  // ── Trigger run ──────────────────────────────────────────────────────────────
  async function handleRun() {
    if (selectedAgent === 'all') {
      toast.error('Select a specific agent to run exams')
      return
    }
    const targets = selectedExams.size === 0 ? ['all'] : [...selectedExams]
    let total = 0
    for (const f of targets) {
      try {
        const res = await examApi.startRun(selectedAgent, f)
        total += res.count
      } catch {
        toast.error(`Failed to start: ${f}`)
      }
    }
    if (total > 0) {
      toast.success(`Started ${total} exam run${total > 1 ? 's' : ''}`)
      await loadRuns()
    }
  }

  // ── Mentor scores ────────────────────────────────────────────────────────────
  async function handleMentorSubmit(runId) {
    const scores = mentorInputs[runId] || {}
    const run = runs.find(r => r.id === runId)
    if (!run) return
    if (run.mentor_criteria.filter(c => scores[c] == null).length > 0) {
      toast.error('Please score all criteria before submitting')
      return
    }
    try {
      const updated = await examApi.submitMentorScore(runId, scores)
      setRuns(prev => prev.map(r => r.id === runId ? updated : r))
      toast.success('Mentor scores saved')
    } catch {
      toast.error('Failed to save scores')
    }
  }

  // ── Exam CRUD ────────────────────────────────────────────────────────────────
  async function handleExamSave(filename, formData) {
    const payload = {
      id: formData.id,
      role: formData.role || '',
      skill: formData.skill,
      difficulty: formData.difficulty,
      scenario: formData.scenario,
      input_message: formData.input_message,
      expected_keywords: formData.expected_keywords,
      mentor_criteria: formData.mentor_criteria,
      auto_score_weight: parseFloat(formData.auto_score_weight),
      mentor_score_weight: parseFloat(formData.mentor_score_weight),
      pass_threshold: parseInt(formData.pass_threshold),
    }
    try {
      if (filename) {
        await examApi.update(filename, payload)
        toast.success('Exam updated')
      } else {
        await examApi.create(payload)
        toast.success('Exam created')
      }
      loadExams()
      setExamForm(null)
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to save exam')
    }
  }

  async function handleExamDelete(filename) {
    try {
      await examApi.delete(filename)
      toast.success('Exam deleted')
      loadExams()
      setSelectedExams(prev => { const s = new Set(prev); s.delete(filename); return s })
    } catch {
      toast.error('Failed to delete exam')
    }
  }

  async function handleEditExam(exam) {
    try {
      const full = await examApi.get(exam.file)
      setExamForm({ mode: 'edit', filename: exam.file, data: full })
    } catch {
      toast.error('Failed to load exam')
    }
  }

  // ── Assign ranking ───────────────────────────────────────────────────────────
  async function handleAssignRanking() {
    if (!rankingChoice || !currentAgent) return
    try {
      await agentApi.updateRanking(currentAgent.id, rankingChoice)
      toast.success(`${currentAgent.name} → ${rankingChoice}`)
      setRankingModal(false)
      if (onUpdate) onUpdate()
    } catch {
      toast.error('Failed to update ranking')
    }
  }

  // ── Drill into a run from the version matrix ──────────────────────────────────
  async function handleMatrixDrill(runId) {
    if (!runId) return
    try {
      const run = await examApi.getRun(runId)
      // Switch to history tab and expand that row
      // First, ensure the run is in the list
      setRuns(prev => prev.find(r => r.id === runId) ? prev : [run, ...prev])
      setActiveTab('history')
      setExpanded(runId)
    } catch {
      toast.error('Could not load run details')
    }
  }

  // ── Derived ──────────────────────────────────────────────────────────────────
  const filteredSelectorExams = exams.filter(exam => {
    const role = examRole(exam)
    const matchRole   = selectorRole === 'all' || role === selectorRole
    const matchSearch = !selectorSearch || exam.id.toLowerCase().includes(selectorSearch.toLowerCase()) || (exam.skill || '').toLowerCase().includes(selectorSearch.toLowerCase())
    return matchRole && matchSearch
  })

  const runningRuns = runs.filter(r => r.status === 'running')
  const doneRuns    = runs.filter(r => r.status === 'done')
  const trendData   = buildTrendData(doneRuns)
  const examLines   = [...new Set(doneRuns.map(r => r.exam_id).filter(Boolean))]
  const compareData = buildCompareData(compareRuns, compareIds, agents)
  const compareExams = [...new Set(compareRuns.map(r => r.exam_id).filter(Boolean))]
  const selCount    = selectedExams.size
  const runLabel    = selectedAgent === 'all' ? 'Run'
    : selCount === 0 ? 'Run All'
    : `Run (${selCount})`

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Header ── */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200 dark:border-gray-800 shrink-0 flex-wrap">
        <h1 className="text-lg font-bold shrink-0">📝 Exams</h1>

        <select
          value={selectedAgent}
          onChange={e => setSelectedAgent(e.target.value)}
          className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-sm rounded-lg px-3 py-1.5 outline-none"
        >
          <option value="all">All Agents</option>
          {agents.map(a => (
            <option key={a.id} value={a.id}>{a.avatar_emoji} {a.name}</option>
          ))}
        </select>

        <button
          onClick={() => setShowSelector(v => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700
                     text-sm rounded-lg hover:border-gray-500 transition-colors"
        >
          {selCount === 0 ? 'Select Questions' : `${selCount} selected`}
          {showSelector ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>

        <button
          onClick={handleRun}
          disabled={selectedAgent === 'all'}
          className="flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 hover:bg-blue-500
                     disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium
                     rounded-lg transition-colors"
        >
          <Play className="w-3.5 h-3.5" /> {runLabel}
        </button>

        {currentAgent && (
          <button
            onClick={() => { setRankingChoice(currentAgent.ranking || 'Intern'); setRankingModal(true) }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700
                       text-sm rounded-lg hover:border-gray-500 transition-colors"
          >
            <Award className="w-3.5 h-3.5 text-yellow-400" />
            <RankingBadge ranking={currentAgent.ranking} />
          </button>
        )}

        <button
          onClick={loadRuns}
          className="p-1.5 text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:text-white hover:bg-gray-100 dark:bg-gray-800 rounded-lg transition-colors ml-auto"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* ── Question selector (collapsible) ── */}
      {showSelector && (
        <div className="px-6 py-3 bg-gray-900/80 border-b border-gray-200 dark:border-gray-800 shrink-0 space-y-2">
          {/* Row 1: select all/none + search */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-semibold text-gray-400">Select questions to run:</span>
            <button onClick={() => setSelectedExams(new Set(filteredSelectorExams.map(e => e.file)))} className="text-xs text-blue-400 hover:text-blue-300">All</button>
            <button onClick={() => setSelectedExams(new Set())} className="text-xs text-gray-500 hover:text-gray-300">None</button>
            <input
              value={selectorSearch}
              onChange={e => setSelectorSearch(e.target.value)}
              placeholder="Search questions…"
              className="ml-auto bg-gray-800 border border-gray-700 rounded-lg px-3 py-1 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 w-48"
            />
          </div>
          {/* Row 2: role filter pills */}
          <div className="flex gap-1.5 flex-wrap">
            {['all', 'QA', 'Dev', 'PM', 'SRE', 'PJ'].map(r => (
              <button
                key={r}
                onClick={() => setSelectorRole(r)}
                className={`px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors ${
                  selectorRole === r ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {r === 'all' ? 'All' : r}
              </button>
            ))}
          </div>
          {/* Row 3: question chips */}
          <div className="flex flex-wrap gap-2 max-h-44 overflow-y-auto">
            {filteredSelectorExams.map(exam => (
              <label key={exam.file} className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 rounded-lg cursor-pointer hover:bg-gray-700 transition-colors select-none text-xs">
                <input
                  type="checkbox"
                  checked={selectedExams.has(exam.file)}
                  onChange={e => {
                    setSelectedExams(prev => {
                      const s = new Set(prev)
                      if (e.target.checked) s.add(exam.file); else s.delete(exam.file)
                      return s
                    })
                  }}
                  className="accent-blue-500"
                />
                <ExamRoleDot role={examRole(exam)} />
                <span className="font-mono text-gray-200">{exam.id}</span>
                {exam.skill && <span className="text-gray-500">· {exam.skill}</span>}
                {exam.difficulty && <DiffBadge diff={exam.difficulty} />}
              </label>
            ))}
            {filteredSelectorExams.length === 0 && <span className="text-xs text-gray-600">No questions match.</span>}
          </div>
        </div>
      )}

      {/* ── Running strip ── */}
      {runningRuns.length > 0 && (
        <div className="px-6 py-2 bg-yellow-900/20 border-b border-yellow-800/30 flex items-center gap-4 flex-wrap shrink-0">
          <span className="text-xs text-yellow-500 font-medium shrink-0">Running:</span>
          {runningRuns.map(r => (
            <span key={r.id} className="flex items-center gap-1.5 text-xs text-yellow-300">
              <span className="w-3 h-3 border border-yellow-400 border-t-transparent rounded-full animate-spin inline-block" />
              {r.agent_name} · <span className="font-mono">{r.exam_id}</span>
            </span>
          ))}
        </div>
      )}

      {/* ── Tabs ── */}
      <div className="flex border-b border-gray-200 dark:border-gray-800 shrink-0 px-6">
        {[
          { id: 'history',  label: '📈 History' },
          { id: 'versions', label: '🔀 Version Compare' },
          { id: 'compare',  label: '⚖️ Agent Compare' },
          { id: 'manage',   label: '🗂 Manage' },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-gray-500 dark:text-gray-500 hover:text-gray-600 dark:text-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Body ── */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">

        {/* ════════ HISTORY TAB ════════ */}
        {activeTab === 'history' && <>
          {trendData.length >= 2 && examLines.length > 0 && (
            <div className="bg-gray-800/50 rounded-xl p-4">
              <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-3">Score Trend</h2>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={trendData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 11 }} tickFormatter={d => d.slice(5)} />
                  <YAxis domain={[0, 100]} tick={{ fill: '#6b7280', fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} labelStyle={{ color: '#9ca3af' }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {examLines.map((id, i) => (
                    <Line key={id} type="monotone" dataKey={id} name={id} stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} dot={{ r: 4 }} connectNulls />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {doneRuns.length > 0 && (
            <div className="grid grid-cols-3 gap-3">
              <StatCard label="Total Runs" value={doneRuns.length} />
              <StatCard
                label="Pass Rate"
                value={`${Math.round(doneRuns.filter(r => r.passed === true).length / doneRuns.length * 100)}%`}
                color={doneRuns.filter(r => r.passed === true).length / doneRuns.length >= 0.8 ? 'text-green-400' : 'text-yellow-400'}
              />
              <StatCard
                label="Avg Score"
                value={`${Math.round(doneRuns.reduce((s, r) => s + (r.total_score || 0), 0) / doneRuns.length)}`}
              />
            </div>
          )}

          <RunTable
            runs={runs}
            expanded={expanded}
            setExpanded={setExpanded}
            mentorInputs={mentorInputs}
            setMentorInputs={setMentorInputs}
            onMentorSubmit={handleMentorSubmit}
          />
        </>}

        {/* ════════ VERSION COMPARE TAB ════════ */}
        {activeTab === 'versions' && (
          <VersionCompareTab
            selectedAgent={selectedAgent}
            agents={agents}
            versionMatrix={versionMatrix}
            onDrill={handleMatrixDrill}
          />
        )}

        {/* ════════ AGENT COMPARE TAB ════════ */}
        {activeTab === 'compare' && (
          <CompareTab
            agents={agents}
            compareIds={compareIds}
            setCompareIds={setCompareIds}
            compareData={compareData}
            compareExams={compareExams}
          />
        )}

        {/* ════════ MANAGE EXAMS TAB ════════ */}
        {activeTab === 'manage' && (
          <ManageExamsTab
            exams={exams}
            examForm={examForm}
            setExamForm={setExamForm}
            onSave={handleExamSave}
            onEdit={handleEditExam}
            onDelete={handleExamDelete}
          />
        )}
      </div>

      {/* ── Ranking Modal ── */}
      {rankingModal && currentAgent && (
        <RankingModal
          agent={currentAgent}
          current={rankingChoice}
          onChange={setRankingChoice}
          onConfirm={handleAssignRanking}
          onClose={() => setRankingModal(false)}
        />
      )}
    </div>
  )
}


// ── Version Compare Tab ────────────────────────────────────────────────────────
function VersionCompareTab({ selectedAgent, agents, versionMatrix, onDrill }) {
  if (selectedAgent === 'all') {
    return (
      <div className="bg-gray-800/50 rounded-xl p-10 text-center text-gray-500 dark:text-gray-500">
        <GitCompare className="w-8 h-8 mx-auto mb-3 opacity-40" />
        <p className="font-medium mb-1">Select an agent to compare prompt versions</p>
        <p className="text-xs text-gray-600">This view shows how each exam score changed across prompt v1, v2, v3…</p>
      </div>
    )
  }

  if (!versionMatrix) {
    return <div className="text-center text-gray-600 py-10 text-sm">Loading version data…</div>
  }

  const { versions, exams } = versionMatrix

  if (!exams || exams.length === 0) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-10 text-center text-gray-600">
        No completed runs with prompt versions yet for this agent.
      </div>
    )
  }

  const agent = agents.find(a => a.id === selectedAgent)

  // Summary row: pass counts per version
  const passCounts = {}
  versions.forEach(v => {
    passCounts[v] = exams.filter(e => e.scores[v]?.passed === true).length
  })

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="bg-gray-800/50 rounded-xl p-4">
        <div className="flex items-center gap-3 mb-3">
          <span className="text-sm font-semibold text-gray-600 dark:text-gray-300">
            {agent?.avatar_emoji} {agent?.name} — Prompt Version Progress
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-500">{exams.length} exams · {versions.length} versions</span>
        </div>
        <div className="flex gap-4">
          {versions.map(v => (
            <div key={v} className="flex-1 bg-gray-900/60 rounded-lg px-4 py-3 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-500 mb-1">Prompt v{v}</p>
              <p className={`text-2xl font-bold ${passCounts[v] / exams.length >= 0.8 ? 'text-green-400' : passCounts[v] / exams.length >= 0.5 ? 'text-yellow-400' : 'text-red-400'}`}>
                {passCounts[v]}/{exams.length}
              </p>
              <p className="text-xs text-gray-600">passed</p>
            </div>
          ))}
          {versions.length >= 2 && (() => {
            const first = passCounts[versions[0]]
            const last  = passCounts[versions[versions.length - 1]]
            const delta = last - first
            return (
              <div className="flex-1 bg-gray-900/60 rounded-lg px-4 py-3 text-center border border-dashed border-gray-300 dark:border-gray-700">
                <p className="text-xs text-gray-500 dark:text-gray-500 mb-1">Improvement</p>
                <p className={`text-2xl font-bold ${delta > 0 ? 'text-green-400' : delta < 0 ? 'text-red-400' : 'text-gray-500 dark:text-gray-500'}`}>
                  {delta > 0 ? '+' : ''}{delta}
                </p>
                <p className="text-xs text-gray-600">v{versions[0]} → v{versions[versions.length - 1]}</p>
              </div>
            )
          })()}
        </div>
      </div>

      {/* Matrix table */}
      <div className="bg-gray-800/50 rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 dark:text-gray-500 border-b border-gray-300 dark:border-gray-700">
              <th className="text-left px-4 py-2.5 font-medium">Exam</th>
              <th className="text-left px-4 py-2.5 font-medium">Skill</th>
              {versions.map(v => (
                <th key={v} className="text-center px-4 py-2.5 font-medium text-blue-400">v{v}</th>
              ))}
              {versions.length >= 2 && (
                <th className="text-center px-4 py-2.5 font-medium text-gray-500 dark:text-gray-500 dark:text-gray-400">Δ</th>
              )}
            </tr>
          </thead>
          <tbody>
            {exams.map(exam => {
              const firstScore = exam.scores[versions[0]]?.total
              const lastScore  = exam.scores[versions[versions.length - 1]]?.total
              const delta      = firstScore != null && lastScore != null ? Math.round((lastScore - firstScore) * 10) / 10 : null

              return (
                <tr key={exam.exam_id} className="border-b border-gray-300 dark:border-gray-700/50 hover:bg-gray-300 dark:hover:bg-gray-700/20">
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-gray-200 text-xs">{exam.exam_id}</span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-500 dark:text-gray-500">{exam.skill || '—'}</td>
                  {versions.map(v => {
                    const s = exam.scores[v]
                    if (!s) return <td key={v} className="px-4 py-2.5 text-center text-gray-700">—</td>
                    return (
                      <td key={v} className="px-4 py-2.5 text-center">
                        <button
                          onClick={() => onDrill(s.run_id)}
                          className="group flex flex-col items-center gap-0.5 mx-auto hover:opacity-80 transition-opacity"
                          title="Click to see details"
                        >
                          <span className={`font-bold text-sm ${scoreColor(s.total, 75)}`}>
                            {s.total ?? '—'}
                          </span>
                          <span className="text-[10px]">{s.passed === true ? '✅' : s.passed === false ? '❌' : '⏳'}</span>
                        </button>
                      </td>
                    )
                  })}
                  {versions.length >= 2 && (
                    <td className="px-4 py-2.5 text-center">
                      {delta != null ? (
                        <span className={`font-semibold text-xs ${delta > 0 ? 'text-green-400' : delta < 0 ? 'text-red-400' : 'text-gray-500 dark:text-gray-500'}`}>
                          {delta > 0 ? '+' : ''}{delta}
                        </span>
                      ) : <span className="text-gray-700">—</span>}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-600 text-center">Click any score cell to see the full run detail in History tab</p>
    </div>
  )
}


// ── Ranking Badge ──────────────────────────────────────────────────────────────
function RankingBadge({ ranking }) {
  const cls = RANKING_STYLE[ranking] || RANKING_STYLE.Intern
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${cls}`}>
      {ranking || 'Intern'}
    </span>
  )
}


// ── Ranking Modal ──────────────────────────────────────────────────────────────
function RankingModal({ agent, current, onChange, onConfirm, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-2xl p-6 w-[420px] shadow-2xl">
        <h2 className="text-lg font-bold mb-1">Assign Ranking</h2>
        <p className="text-gray-500 dark:text-gray-500 dark:text-gray-400 text-sm mb-5">{agent.avatar_emoji} {agent.name}</p>

        <div className="space-y-2 mb-6">
          {RANKINGS.map(r => (
            <button
              key={r}
              onClick={() => onChange(r)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl border transition-colors text-left ${
                current === r ? 'border-blue-500 bg-blue-600/10' : 'border-gray-300 dark:border-gray-700 hover:border-gray-500'
              }`}
            >
              <RankingBadge ranking={r} />
              <span className="text-sm text-gray-600 dark:text-gray-300">{RANKING_DESC[r]}</span>
            </button>
          ))}
        </div>

        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-300 dark:border-gray-700 text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:border-gray-500 text-sm">Cancel</button>
          <button onClick={onConfirm} className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium transition-colors">Confirm</button>
        </div>
      </div>
    </div>
  )
}


// ── Exam role / diff helpers ───────────────────────────────────────────────────
function ExamRoleDot({ role }) {
  const dot = (ROLE_COLORS_EXAM[role] || ROLE_COLORS_EXAM.Other).dot
  return <span className={`w-1.5 h-1.5 rounded-full shrink-0 inline-block ${dot}`} />
}

function DiffBadge({ diff }) {
  const colors = {
    L1: 'text-green-400 bg-green-900/30',
    L2: 'text-yellow-400 bg-yellow-900/30',
    L3: 'text-red-400 bg-red-900/30',
  }
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${colors[diff] || 'text-gray-400 bg-gray-700'}`}>
      {diff}
    </span>
  )
}


// ── Manage Exams Tab ───────────────────────────────────────────────────────────
const EMPTY_FORM = {
  id: '', role: '', skill: '', difficulty: 'L1', scenario: '',
  input_message: '', expected_keywords: [], mentor_criteria: [],
  auto_score_weight: 0.6, mentor_score_weight: 0.4, pass_threshold: 75,
}

function ManageExamsTab({ exams, examForm, setExamForm, onSave, onEdit, onDelete }) {
  const [search,         setSearch]         = useState('')
  const [confirmDelete,  setConfirmDelete]  = useState(null)  // filename | null

  const filtered = exams.filter(e =>
    !search ||
    e.id.toLowerCase().includes(search.toLowerCase()) ||
    (e.skill || '').toLowerCase().includes(search.toLowerCase())
  )

  // Group by role
  const grouped = {}
  ROLE_ORDER_EXAM.forEach(r => { grouped[r] = [] })
  filtered.forEach(exam => {
    const r = examRole(exam)
    ;(grouped[r] || (grouped[r] = [])).push(exam)
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold text-gray-600 dark:text-gray-300 shrink-0">
          {exams.length} question{exams.length !== 1 ? 's' : ''}
        </span>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search questions…"
          className="flex-1 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-900 dark:text-gray-200 placeholder-gray-500 outline-none focus:border-blue-500"
        />
        <button
          onClick={() => setExamForm({ mode: 'create', filename: null, data: { ...EMPTY_FORM } })}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors shrink-0"
        >
          <Plus className="w-3.5 h-3.5" /> New Question
        </button>
      </div>

      {ROLE_ORDER_EXAM.map(role => {
        const items = grouped[role]
        if (!items || items.length === 0) return null
        const rc = ROLE_COLORS_EXAM[role]
        return (
          <div key={role}>
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg mb-2 ${rc.bg}`}>
              <span className={`text-xs font-bold ${rc.text}`}>{role}</span>
              <span className={`text-xs ${rc.text} opacity-60`}>{items.length} question{items.length !== 1 ? 's' : ''}</span>
            </div>
            <div className="space-y-2">
              {items.map(exam => (
                <div key={exam.file} className="bg-gray-800/50 rounded-xl px-4 py-3 flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                      <span className="font-mono text-sm text-gray-900 dark:text-white">{exam.id}</span>
                      {exam.difficulty && <DiffBadge diff={exam.difficulty} />}
                      {exam.skill && <span className="text-xs text-gray-500 dark:text-gray-500">{exam.skill}</span>}
                    </div>
                    {exam.scenario && <p className="text-xs text-gray-500 dark:text-gray-500 truncate">{exam.scenario}</p>}
                    <p className="text-xs text-gray-600 mt-0.5 font-mono">{exam.file}</p>
                  </div>
                  {confirmDelete === exam.file ? (
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="text-xs text-gray-400">Delete?</span>
                      <button
                        onClick={() => setConfirmDelete(null)}
                        className="px-2 py-1 text-xs text-gray-400 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
                      >Cancel</button>
                      <button
                        onClick={() => { onDelete(exam.file); setConfirmDelete(null) }}
                        className="px-2 py-1 text-xs text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors"
                      >Delete</button>
                    </div>
                  ) : (
                    <div className="flex gap-1.5 shrink-0">
                      <button onClick={() => onEdit(exam)} className="p-1.5 text-gray-500 dark:text-gray-500 hover:text-blue-400 hover:bg-gray-300 dark:hover:bg-gray-700 rounded-lg transition-colors" title="Edit">
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => setConfirmDelete(exam.file)} className="p-1.5 text-gray-500 dark:text-gray-500 hover:text-red-400 hover:bg-gray-300 dark:hover:bg-gray-700 rounded-lg transition-colors" title="Delete">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}

      {filtered.length === 0 && (
        <div className="text-center text-gray-600 py-10">
          {search ? 'No questions match your search.' : 'No question files found. Click New Question to get started.'}
        </div>
      )}

      {examForm && (
        <ExamFormModal
          mode={examForm.mode}
          filename={examForm.filename}
          initial={examForm.data}
          onSave={onSave}
          onClose={() => setExamForm(null)}
        />
      )}
    </div>
  )
}


// ── Exam Form Modal ────────────────────────────────────────────────────────────
function ExamFormModal({ mode, filename, initial, onSave, onClose }) {
  const [form, setForm] = useState({ ...initial })

  function set(field, val) { setForm(prev => ({ ...prev, [field]: val })) }
  function parseLines(str) { return str.split('\n').map(s => s.trim()).filter(Boolean) }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-2xl p-6 w-full max-w-xl shadow-2xl overflow-y-auto max-h-[90vh]">
        <h2 className="text-lg font-bold mb-5">{mode === 'create' ? '+ New Question' : `✏️ Edit ${filename}`}</h2>

        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <Field label="Question ID *">
              <input value={form.id} onChange={e => set('id', e.target.value)} placeholder="qa-tc-001"
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-1.5 text-sm outline-none focus:border-blue-500" />
            </Field>
            <Field label="Role">
              <select value={form.role} onChange={e => set('role', e.target.value)}
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-1.5 text-sm outline-none">
                <option value="">— infer from ID —</option>
                {['QA', 'Dev', 'PM', 'SRE', 'PJ'].map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
            <Field label="Difficulty">
              <select value={form.difficulty} onChange={e => set('difficulty', e.target.value)}
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-1.5 text-sm outline-none">
                {['L1', 'L2', 'L3'].map(d => <option key={d}>{d}</option>)}
              </select>
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Skill">
              <input value={form.skill} onChange={e => set('skill', e.target.value)} placeholder="security_boundary"
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-1.5 text-sm outline-none focus:border-blue-500" />
            </Field>
            <Field label="Pass Threshold (0–100)">
              <input type="number" min="0" max="100" value={form.pass_threshold} onChange={e => set('pass_threshold', e.target.value)}
                className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-1.5 text-sm outline-none focus:border-blue-500" />
            </Field>
          </div>

          <Field label="Scenario Description">
            <input value={form.scenario} onChange={e => set('scenario', e.target.value)} placeholder="Brief description"
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-1.5 text-sm outline-none focus:border-blue-500" />
          </Field>

          <Field label="Input Message *">
            <textarea value={form.input_message} onChange={e => set('input_message', e.target.value)} rows={3}
              placeholder="The prompt sent to the agent during the exam"
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500 resize-y" />
          </Field>

          <Field label="Expected Keywords (one per line)">
            <textarea value={(form.expected_keywords || []).join('\n')} onChange={e => set('expected_keywords', parseLines(e.target.value))}
              rows={3} placeholder={'refuse\ndecline\nunauthorized'}
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500 resize-y font-mono" />
          </Field>

          <Field label="Mentor Criteria (one per line)">
            <textarea value={(form.mentor_criteria || []).join('\n')} onChange={e => set('mentor_criteria', parseLines(e.target.value))}
              rows={3} placeholder={'Explicitly refuses\nExplains reason\nOffers alternative'}
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500 resize-y" />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label={`Auto Score Weight (${Math.round(form.auto_score_weight * 100)}%)`}>
              <input type="range" min="0" max="1" step="0.1" value={form.auto_score_weight}
                onChange={e => { const v = parseFloat(e.target.value); set('auto_score_weight', v); set('mentor_score_weight', Math.round((1 - v) * 10) / 10) }}
                className="w-full accent-blue-500 mt-2" />
            </Field>
            <Field label={`Mentor Score Weight (${Math.round(form.mentor_score_weight * 100)}%)`}>
              <input type="range" min="0" max="1" step="0.1" value={form.mentor_score_weight}
                onChange={e => { const v = parseFloat(e.target.value); set('mentor_score_weight', v); set('auto_score_weight', Math.round((1 - v) * 10) / 10) }}
                className="w-full accent-blue-500 mt-2" />
            </Field>
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-300 dark:border-gray-700 text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:border-gray-500 text-sm">Cancel</button>
          <button onClick={() => onSave(filename, form)} disabled={!form.id || !form.input_message}
            className="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium transition-colors">
            {mode === 'create' ? 'Create' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 mb-1">{label}</label>
      {children}
    </div>
  )
}


// ── Run table ──────────────────────────────────────────────────────────────────
function RunTable({ runs, expanded, setExpanded, mentorInputs, setMentorInputs, onMentorSubmit }) {
  if (runs.length === 0) {
    return (
      <div className="bg-gray-800/50 rounded-xl p-10 text-center text-gray-600">
        No exam runs yet — select an agent above and click Run.
      </div>
    )
  }

  return (
    <div className="bg-gray-800/50 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-300 dark:border-gray-700">
        <span className="text-sm font-semibold text-gray-600 dark:text-gray-300">Run History</span>
        <span className="text-xs text-gray-500 dark:text-gray-500">{runs.length} entries</span>
      </div>

      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 dark:text-gray-500 border-b border-gray-300 dark:border-gray-700">
            <th className="text-left px-4 py-2 font-medium">Time</th>
            <th className="text-left px-4 py-2 font-medium">Agent</th>
            <th className="text-left px-4 py-2 font-medium">Exam</th>
            <th className="text-center px-3 py-2 font-medium">Prompt</th>
            <th className="text-right px-4 py-2 font-medium">Auto</th>
            <th className="text-right px-4 py-2 font-medium">Total</th>
            <th className="text-center px-4 py-2 font-medium">Result</th>
            <th className="px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          {runs.map(run => (
            <RunRow
              key={run.id}
              run={run}
              isExpanded={expanded === run.id}
              onToggle={() => setExpanded(expanded === run.id ? null : run.id)}
              mentorInput={mentorInputs[run.id] || {}}
              onMentorChange={(criterion, val) =>
                setMentorInputs(prev => ({ ...prev, [run.id]: { ...(prev[run.id] || {}), [criterion]: val } }))
              }
              onMentorSubmit={() => onMentorSubmit(run.id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}


// ── Run row + expandable detail ────────────────────────────────────────────────
function RunRow({ run, isExpanded, onToggle, mentorInput, onMentorChange, onMentorSubmit }) {
  return (
    <>
      <tr onClick={onToggle} className="border-b border-gray-300 dark:border-gray-700/50 hover:bg-gray-300 dark:hover:bg-gray-700/30 cursor-pointer transition-colors">
        <td className="px-4 py-2.5 text-gray-500 dark:text-gray-500 dark:text-gray-400 whitespace-nowrap">{fmtDate(run.created_at)}</td>
        <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300 max-w-[100px] truncate">{run.agent_name}</td>
        <td className="px-4 py-2.5">
          <span className="font-mono text-gray-200">{run.exam_id || run.exam_file}</span>
          {run.skill && <span className="text-gray-500 dark:text-gray-500 ml-1.5 hidden sm:inline">{run.skill}</span>}
        </td>
        <td className="px-3 py-2.5 text-center">
          {run.prompt_version_num != null
            ? <span className="px-1.5 py-0.5 bg-blue-900/40 text-blue-300 rounded text-[10px] font-mono">v{run.prompt_version_num}</span>
            : <span className="text-gray-600">—</span>
          }
        </td>
        <td className="px-4 py-2.5 text-right text-gray-600 dark:text-gray-300">{run.auto_score != null ? run.auto_score : '—'}</td>
        <td className="px-4 py-2.5 text-right font-semibold"><ScoreCell run={run} /></td>
        <td className="px-4 py-2.5 text-center"><StatusBadge run={run} /></td>
        <td className="px-2 py-2.5 text-gray-600">
          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </td>
      </tr>

      {isExpanded && (
        <tr className="bg-gray-900/60">
          <td colSpan={8} className="px-5 py-4">
            <RunDetail
              run={run}
              mentorInput={mentorInput}
              onMentorChange={onMentorChange}
              onMentorSubmit={onMentorSubmit}
            />
          </td>
        </tr>
      )}
    </>
  )
}


// ── Expanded detail panel ──────────────────────────────────────────────────────
function RunDetail({ run, mentorInput, onMentorChange, onMentorSubmit }) {
  if (run.status === 'running') return <p className="text-yellow-400 text-sm">⏳ Exam is still running…</p>
  if (run.status === 'error') return (
    <div className="text-red-400 text-sm">
      <p className="font-semibold mb-1">Error</p>
      <pre className="bg-gray-100 dark:bg-gray-800 rounded p-2 text-xs whitespace-pre-wrap">{run.error_msg}</pre>
    </div>
  )

  const needsMentor = run.mentor_criteria.length > 0 && run.mentor_score == null
  const hasJudge    = run.judge_results && Object.keys(run.judge_results).length > 0
  const hasRules    = run.rules_result  && run.rules_result.length > 0

  return (
    <div className="space-y-4">
      {/* Score summary row */}
      <div className="flex gap-6 text-sm flex-wrap">
        <div>
          <span className="text-gray-500 dark:text-gray-500 text-xs">Auto score</span>
          <p className="font-bold text-gray-900 dark:text-white">{run.auto_score ?? '—'} / 100</p>
          <p className="text-gray-600 text-xs">{Math.round((run.auto_weight ?? 0.6) * 100)}% weight</p>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-500 text-xs">Judge / Mentor score</span>
          <p className={`font-bold ${run.mentor_score != null ? 'text-gray-900 dark:text-white' : 'text-gray-600'}`}>
            {run.mentor_score != null ? `${run.mentor_score} / 100` : 'Pending'}
          </p>
          <p className="text-gray-600 text-xs">{Math.round((run.mentor_weight ?? 0.4) * 100)}% weight</p>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-500 text-xs">Total {needsMentor ? '(auto only so far)' : ''}</span>
          <p className={`font-bold text-lg ${scoreColor(run.total_score, run.threshold)}`}>
            {run.total_score ?? '—'} / 100
          </p>
          <p className="text-gray-600 text-xs">threshold {run.threshold}</p>
        </div>
        {run.prompt_version_num != null && (
          <div>
            <span className="text-gray-500 dark:text-gray-500 text-xs">Prompt version</span>
            <p className="font-bold text-blue-300">v{run.prompt_version_num}</p>
          </div>
        )}
      </div>

      {/* Rules check */}
      {hasRules && (
        <div>
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-500 dark:text-gray-400 mb-1.5">Rule Checks</p>
          <div className="space-y-1">
            {run.rules_result.map((r, i) => (
              <div key={i} className={`flex items-start gap-2 px-3 py-2 rounded-lg text-xs ${r.passed ? 'bg-green-900/20' : 'bg-red-900/20'}`}>
                <span className="shrink-0 mt-0.5">{r.passed ? '✅' : '❌'}</span>
                <div>
                  <span className="text-gray-600 dark:text-gray-300 font-mono">{r.rule}</span>
                  {r.message && <span className="text-gray-500 dark:text-gray-500 ml-2">— {r.message}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Keyword check (legacy) */}
      {!hasRules && run.missed_keywords != null && (
        <div>
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-500 dark:text-gray-400 mb-1.5">Keyword Check</p>
          <div className="flex flex-wrap gap-1.5">
            {run.missed_keywords.length === 0
              ? <span className="text-green-400 text-xs">✅ All expected keywords present</span>
              : run.missed_keywords.map(kw => (
                  <span key={kw} className="px-2 py-0.5 bg-red-900/40 text-red-300 rounded text-xs">❌ {kw}</span>
                ))
            }
          </div>
        </div>
      )}

      {/* Judge criterion breakdown */}
      {hasJudge && (
        <div className="border border-gray-300 dark:border-gray-700 rounded-xl p-4">
          <p className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-3">🤖 Judge Scoring (per criterion)</p>
          <div className="space-y-3">
            {Object.entries(run.judge_results).map(([criterion, result]) => (
              <JudgeCriterionRow key={criterion} criterion={criterion} result={result} />
            ))}
          </div>
        </div>
      )}

      {/* Human override / mentor scoring */}
      {run.mentor_criteria.length > 0 && (
        <div className="border border-gray-300 dark:border-gray-700 rounded-xl p-4">
          <p className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-1">
            {run.mentor_score != null ? '✅ Human Review (submitted)' : '👤 Human Review / Override'}
          </p>
          {run.mentor_score == null && (
            <p className="text-xs text-gray-500 dark:text-gray-500 mb-3">Override the judge scores below if you disagree with the assessment</p>
          )}
          <div className="space-y-3">
            {run.mentor_criteria.map((criterion, i) => {
              const submitted = run.mentor_scores?.[criterion]
              const current   = submitted ?? mentorInput[criterion] ?? 0.5
              return (
                <div key={i}>
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-xs text-gray-600 dark:text-gray-300 flex-1 pr-4">{criterion}</p>
                    <span className={`text-xs font-bold w-8 text-right ${
                      (submitted ?? mentorInput[criterion]) == null ? 'text-gray-600'
                        : current >= 0.8 ? 'text-green-400' : current >= 0.5 ? 'text-yellow-400' : 'text-red-400'
                    }`}>
                      {(submitted ?? mentorInput[criterion]) != null ? `${Math.round(current * 10) / 10}` : '?'}
                    </span>
                  </div>
                  <input type="range" min="0" max="1" step="0.1" value={current}
                    disabled={run.mentor_score != null}
                    onChange={e => onMentorChange(criterion, parseFloat(e.target.value))}
                    className="w-full h-1.5 accent-blue-500 disabled:opacity-50" />
                  <div className="flex justify-between text-gray-600 text-xs mt-0.5">
                    <span>0 — Poor</span><span>1 — Perfect</span>
                  </div>
                </div>
              )
            })}
          </div>
          {run.mentor_score == null && (
            <button onClick={onMentorSubmit} className="mt-4 w-full py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors">
              Submit Review
            </button>
          )}
        </div>
      )}

      {/* Prompt Improvement Suggestion — shown for completed non-perfect runs */}
      {run.status === 'done' && run.passed === false && (
        <SuggestionPanel run={run} />
      )}

      {/* Agent output */}
      {run.output && (
        <div>
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-500 dark:text-gray-400 mb-1.5">Agent Output</p>
          <pre className="bg-gray-100 dark:bg-gray-800 rounded-lg p-3 text-xs text-gray-600 dark:text-gray-300 overflow-auto max-h-60 whitespace-pre-wrap">
            {run.output}
          </pre>
        </div>
      )}
    </div>
  )
}


// ── Prompt improvement suggestion panel ───────────────────────────────────────
function SuggestionPanel({ run }) {
  const [state,       setState]       = useState('idle')   // idle | loading | done | error
  const [suggestion,  setSuggestion]  = useState(null)
  const [applying,    setApplying]    = useState(false)
  const [openPatch,   setOpenPatch]   = useState({})

  async function handleSuggest() {
    setState('loading')
    try {
      const data = await examApi.suggest(run.id)
      setSuggestion(data)
      setState('done')
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to generate suggestion')
      setState('error')
    }
  }

  async function handleApply() {
    if (!suggestion) return
    setApplying(true)
    try {
      const result = await examApi.applysuggestion(run.id)
      setSuggestion(s => ({ ...s, applied: true }))
      toast.success(`Applied as Prompt v${result.version_num}`)
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to apply suggestion')
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="border border-yellow-600/40 bg-yellow-900/10 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-semibold text-yellow-400 flex items-center gap-2">
          <Lightbulb className="w-4 h-4" /> Prompt Improvement Suggestions
        </p>
        {state === 'idle' && (
          <button
            onClick={handleSuggest}
            className="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg text-xs font-medium transition-colors"
          >
            Suggest
          </button>
        )}
        {state === 'loading' && (
          <span className="text-xs text-yellow-400 animate-pulse">Analysing failure…</span>
        )}
      </div>

      {state === 'idle' && (
        <p className="text-xs text-gray-500">
          Let an independent LLM analyse this failure and draft targeted prompt improvements.
        </p>
      )}

      {state === 'done' && suggestion && (
        <div className="space-y-3">
          {/* Diagnosis */}
          <div className="bg-gray-800/50 rounded-lg px-3 py-2">
            <p className="text-xs text-gray-400 font-semibold mb-0.5">Root Cause</p>
            <p className="text-xs text-gray-300">{suggestion.diagnosis}</p>
          </div>

          {/* Suggestion cards */}
          {suggestion.suggestions.map((s, i) => (
            <div key={s.id || i} className="border border-gray-700 rounded-lg overflow-hidden">
              <button
                onClick={() => setOpenPatch(prev => ({ ...prev, [i]: !prev[i] }))}
                className="w-full flex items-start gap-2 px-3 py-2.5 text-left hover:bg-gray-800/40 transition-colors"
              >
                <span className="text-yellow-400 font-bold text-xs mt-0.5 shrink-0">{s.id}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-gray-200">{s.point}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{s.rationale}</p>
                </div>
                {openPatch[i] ? <ChevronUp className="w-3.5 h-3.5 text-gray-500 shrink-0 mt-0.5" />
                              : <ChevronDown className="w-3.5 h-3.5 text-gray-500 shrink-0 mt-0.5" />}
              </button>
              {openPatch[i] && (
                <div className="px-3 pb-3 bg-gray-900/40">
                  <p className="text-xs text-gray-500 font-semibold mb-1">Suggested patch</p>
                  <pre className="text-xs text-green-300 bg-gray-950/60 rounded p-2 whitespace-pre-wrap overflow-auto max-h-40">
                    {s.patch}
                  </pre>
                </div>
              )}
            </div>
          ))}

          {/* Apply button */}
          {!suggestion.applied ? (
            <button
              onClick={handleApply}
              disabled={applying}
              className="w-full py-2 bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 text-white rounded-lg text-xs font-semibold transition-colors"
            >
              {applying ? 'Applying…' : '✨ Apply to New Prompt Version'}
            </button>
          ) : (
            <div className="flex items-center gap-2 text-green-400 text-xs">
              <CheckCircle2 className="w-4 h-4" />
              Applied as a new prompt version — check Prompt Manager to activate.
            </div>
          )}
        </div>
      )}
    </div>
  )
}


// ── Judge criterion row ────────────────────────────────────────────────────────
function JudgeCriterionRow({ criterion, result }) {
  const [open, setOpen] = useState(false)
  const score = result.score ?? 0
  const maxScore = 3

  const dotColors = ['bg-red-500', 'bg-orange-400', 'bg-yellow-400', 'bg-green-400']
  const dotColor  = dotColors[Math.min(score, 3)]

  return (
    <div className="border border-gray-300 dark:border-gray-700/50 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-gray-200 dark:hover:bg-gray-800/40 transition-colors text-left"
      >
        {/* Score dots */}
        <div className="flex gap-1 shrink-0">
          {Array.from({ length: maxScore + 1 }, (_, i) => (
            <span key={i} className={`w-2 h-2 rounded-full ${i <= score ? dotColor : 'bg-gray-700'}`} />
          ))}
        </div>
        <span className="text-xs font-mono text-gray-500 dark:text-gray-500 dark:text-gray-400 w-6 shrink-0">{score}/{maxScore}</span>
        <span className="text-xs text-gray-600 dark:text-gray-300 flex-1 truncate">{criterion}</span>
        {open ? <ChevronUp className="w-3 h-3 text-gray-500 dark:text-gray-500 shrink-0" /> : <ChevronDown className="w-3 h-3 text-gray-500 dark:text-gray-500 shrink-0" />}
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2 bg-gray-900/40">
          {result.evidence && (
            <div>
              <p className="text-[10px] text-gray-500 dark:text-gray-500 uppercase tracking-wide mb-0.5">Evidence</p>
              <p className="text-xs text-gray-600 dark:text-gray-300 italic">"{result.evidence}"</p>
            </div>
          )}
          {result.reasoning && (
            <div>
              <p className="text-[10px] text-gray-500 dark:text-gray-500 uppercase tracking-wide mb-0.5">Reasoning</p>
              <p className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400">{result.reasoning}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}


// ── Compare tab (agent vs agent) ───────────────────────────────────────────────
function CompareTab({ agents, compareIds, setCompareIds, compareData, compareExams }) {
  function toggleAgent(id) {
    setCompareIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }
  const selectedAgents = agents.filter(a => compareIds.includes(a.id))

  return (
    <div className="space-y-5">
      <div className="bg-gray-800/50 rounded-xl p-4">
        <p className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-3 flex items-center gap-2">
          <Users className="w-4 h-4" /> Select agents to compare
        </p>
        <div className="flex flex-wrap gap-2">
          {agents.map((a, i) => (
            <button key={a.id} onClick={() => toggleAgent(a.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-colors border ${
                compareIds.includes(a.id) ? 'border-blue-500 bg-blue-600/20 text-blue-300' : 'border-gray-300 dark:border-gray-700 text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:border-gray-500'
              }`}
            >
              <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: PALETTE[i % PALETTE.length] }} />
              {a.avatar_emoji} {a.name}
            </button>
          ))}
        </div>
      </div>

      {compareIds.length === 0 && <p className="text-center text-gray-600 py-8">Select at least one agent to see comparison.</p>}
      {compareIds.length > 0 && compareData.length === 0 && <p className="text-center text-gray-600 py-8">No completed runs for the selected agents yet.</p>}

      {compareData.length > 0 && <>
        <div className="bg-gray-800/50 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-3">Score Comparison (latest run per exam)</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={compareData} margin={{ top: 5, right: 10, left: -20, bottom: 20 }}>
              <XAxis dataKey="exam" tick={{ fill: '#6b7280', fontSize: 10 }} angle={-20} textAnchor="end" interval={0} />
              <YAxis domain={[0, 100]} tick={{ fill: '#6b7280', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} labelStyle={{ color: '#9ca3af' }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {selectedAgents.map((a, i) => (
                <Bar key={a.id} dataKey={a.name} fill={PALETTE[i % PALETTE.length]} radius={[3, 3, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-gray-800/50 rounded-xl overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 dark:text-gray-500 border-b border-gray-300 dark:border-gray-700">
                <th className="text-left px-4 py-2 font-medium">Exam</th>
                <th className="text-left px-4 py-2 font-medium">Skill</th>
                {selectedAgents.map((a, i) => (
                  <th key={a.id} className="text-right px-4 py-2 font-medium" style={{ color: PALETTE[i % PALETTE.length] }}>
                    {a.avatar_emoji} {a.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {compareExams.map(examId => {
                const examMeta = compareData.find(d => d.exam === examId)
                return (
                  <tr key={examId} className="border-b border-gray-300 dark:border-gray-700/50">
                    <td className="px-4 py-2 font-mono text-gray-200">{examId}</td>
                    <td className="px-4 py-2 text-gray-500 dark:text-gray-500">{examMeta?.skill || '—'}</td>
                    {selectedAgents.map(a => {
                      const score = examMeta?.[a.name]
                      return (
                        <td key={a.id} className={`px-4 py-2 text-right font-semibold ${
                          score == null ? 'text-gray-600' : scoreColor(score, examMeta?.threshold ?? 75)
                        }`}>
                          {score != null ? score : '—'}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </>}
    </div>
  )
}


// ── Small helpers ──────────────────────────────────────────────────────────────
function StatCard({ label, value, color = 'text-gray-900 dark:text-white' }) {
  return (
    <div className="bg-gray-800/50 rounded-xl px-4 py-3">
      <p className="text-xs text-gray-500 dark:text-gray-500 mb-1">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
    </div>
  )
}

function StatusBadge({ run }) {
  if (run.status === 'running') return (
    <span className="flex items-center justify-center gap-1 text-yellow-400">
      <span className="w-2.5 h-2.5 border border-yellow-400 border-t-transparent rounded-full animate-spin inline-block" />
      running
    </span>
  )
  if (run.status === 'error')  return <span className="text-red-400">❌ error</span>
  if (run.passed === true)     return <span className="text-green-400">✅ passed</span>
  if (run.passed === false)    return <span className="text-red-400">❌ failed</span>
  if (run.passed === null)     return <span className="text-gray-500 dark:text-gray-500">⏳ scoring</span>
  return <span className="text-gray-500 dark:text-gray-500">—</span>
}

function ScoreCell({ run }) {
  if (run.status === 'running') return <span className="text-gray-600">—</span>
  if (run.status === 'error')   return <span className="text-red-500">err</span>
  if (run.total_score == null)  return <span className="text-gray-600">—</span>
  return (
    <span className={`font-bold ${scoreColor(run.total_score, run.threshold)}`}>
      {run.total_score}
      {run.passed === null && <span className="text-gray-600 font-normal text-xs ml-0.5">*</span>}
    </span>
  )
}

function scoreColor(score, threshold = 75) {
  if (score == null) return 'text-gray-600'
  if (score >= threshold) return 'text-green-400'
  if (score >= threshold * 0.8) return 'text-yellow-400'
  return 'text-red-400'
}

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-US', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}


// ── Data transformation helpers ────────────────────────────────────────────────
function buildTrendData(doneRuns) {
  const byDate = {}
  const sorted = [...doneRuns].sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
  sorted.forEach(r => {
    const date = r.created_at.slice(0, 10)
    if (!byDate[date]) byDate[date] = { date }
    const score = r.total_score ?? r.auto_score
    if (score != null && r.exam_id) byDate[date][r.exam_id] = score
  })
  return Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date))
}

function buildCompareData(compareRuns, agentIds, agents) {
  const latest = {}
  compareRuns.forEach(r => {
    const key = `${r.agent_id}||${r.exam_id}`
    latest[key] = r
  })
  const examMap = {}
  Object.values(latest).forEach(r => {
    if (!examMap[r.exam_id]) examMap[r.exam_id] = { exam: r.exam_id, skill: r.skill, threshold: r.threshold }
    const agent = agents.find(a => a.id === r.agent_id)
    if (agent) examMap[r.exam_id][agent.name] = r.total_score ?? r.auto_score
  })
  return Object.values(examMap)
}
