import { useState, useEffect, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line,
} from 'recharts'
import { ChevronDown, ChevronUp, RefreshCw, Filter, GitBranch } from 'lucide-react'
import { auditApi } from '../api/client.js'

const TOOL_ICON = {
  search_knowledge_base: '📚',
  search_confluence:     '🔍',
  save_confluence_page:  '💾',
  read_requirement_doc:  '📄',
  write_output_file:     '📝',
  create_defect_mock:    '🐛',
  search_jira:           '🎫',
  get_jira_issue:        '🎫',
  get_gitlab_mr_diff:    '🔀',
  save_to_memory:        '🧠',
  llm_judge:             '⚖️',
}

const EVENT_COLORS = {
  tool_call:     '#3b82f6',
  l2_decision:   '#f59e0b',
  llm_call:      '#8b5cf6',
  quality_score: '#10b981',
  error:         '#ef4444',
}

// Health score → colour
function healthColor(score) {
  if (score >= 0.9) return 'text-green-400'
  if (score >= 0.7) return 'text-yellow-400'
  return 'text-red-400'
}

export default function AuditPanel({ agents }) {
  const [summary, setSummary] = useState(null)
  const [items, setItems]     = useState([])
  const [total, setTotal]     = useState(0)
  const [page, setPage]       = useState(1)
  const [loading, setLoading] = useState(false)

  // Filters
  const [agentId,    setAgentId]    = useState('')
  const [days,       setDays]       = useState(7)
  const [toolFilter, setToolFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  // Expanded row + trace modal
  const [expanded,    setExpanded]    = useState(null)
  const [traceModal,  setTraceModal]  = useState(null)   // trace_id or null
  const [traceData,   setTraceData]   = useState(null)

  const PER_PAGE = 50

  const loadSummary = useCallback(async () => {
    try {
      const data = await auditApi.summary({ agent_id: agentId || undefined, days })
      setSummary(data)
    } catch {}
  }, [agentId, days])

  const loadList = useCallback(async (p = 1) => {
    setLoading(true)
    try {
      const params = {
        page: p, per_page: PER_PAGE,
        ...(agentId    && { agent_id:   agentId }),
        ...(toolFilter && { tool:        toolFilter }),
        ...(typeFilter && { event_type:  typeFilter }),
      }
      const data = await auditApi.list(params)
      setItems(data.items)
      setTotal(data.total)
      setPage(p)
    } catch {}
    setLoading(false)
  }, [agentId, toolFilter, typeFilter])

  useEffect(() => {
    loadSummary()
    loadList(1)
  }, [loadSummary, loadList])

  function refresh() {
    loadSummary()
    loadList(1)
  }

  async function openTrace(traceId) {
    setTraceModal(traceId)
    setTraceData(null)
    try {
      const data = await fetch(`/api/audit/trace/${traceId}`).then(r => r.json())
      setTraceData(data)
    } catch {
      setTraceData({ error: 'Failed to load trace' })
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800 shrink-0">
        <h1 className="text-lg font-bold">📊 Audit Log</h1>
        <div className="flex items-center gap-3">
          <select
            value={agentId}
            onChange={e => setAgentId(e.target.value)}
            className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-sm rounded-lg px-3 py-1.5 outline-none"
          >
            <option value="">All Agents</option>
            {(agents || []).map(a => (
              <option key={a.id} value={a.id}>{a.avatar_emoji} {a.name}</option>
            ))}
          </select>
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-sm rounded-lg px-3 py-1.5 outline-none"
          >
            {[1, 7, 14, 30, 90].map(d => (
              <option key={d} value={d}>Last {d}d</option>
            ))}
          </select>
          <button onClick={refresh} className="p-1.5 rounded-lg hover:bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:text-white transition-colors">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {/* ── Summary Cards ──────────────────────────────────────────────── */}
        {summary && (
          <>
            {/* Row 1: core metrics */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <StatCard label="Tool Calls" value={summary.total_tool_calls} />
              <StatCard label="Success Rate" value={`${(summary.success_rate * 100).toFixed(1)}%`}
                color={summary.success_rate >= 0.95 ? 'text-green-400' : 'text-yellow-400'} />
              <StatCard label="Avg Duration" value={`${(summary.avg_duration_ms / 1000).toFixed(1)}s`} />
              <StatCard
                label="L2 Decisions"
                value={`${summary.l2_decisions.approved}✅ / ${summary.l2_decisions.rejected}❌`}
              />
            </div>

            {/* Row 2: token costs */}
            {summary.tokens && (summary.tokens.input > 0 || summary.tokens.output > 0) && (
              <div className="grid grid-cols-3 gap-3">
                <StatCard label="Input Tokens"  value={(summary.tokens.input).toLocaleString()} color="text-blue-400" />
                <StatCard label="Output Tokens" value={(summary.tokens.output).toLocaleString()} color="text-purple-400" />
                <StatCard label="Est. Cost (USD)" value={`$${summary.tokens.estimated_cost_usd.toFixed(4)}`} color="text-yellow-400" />
              </div>
            )}

            {/* Row 3: V2 observability — health + quality + KB */}
            {summary.health && (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <StatCard
                  label="Health Score"
                  value={`${(summary.health.score * 100).toFixed(0)}%`}
                  color={healthColor(summary.health.score)}
                  sub={`P95: ${(summary.health.p95_duration_ms / 1000).toFixed(1)}s · trend: ${summary.health.error_rate_trend >= 0 ? '+' : ''}${(summary.health.error_rate_trend * 100).toFixed(1)}%`}
                />
                {summary.quality && summary.quality.sample_count > 0 && (
                  <StatCard
                    label="Reply Quality"
                    value={`${(summary.quality.avg_score * 100).toFixed(0)}%`}
                    color={summary.quality.avg_score >= 0.8 ? 'text-green-400' : summary.quality.avg_score >= 0.6 ? 'text-yellow-400' : 'text-red-400'}
                    sub={`${summary.quality.sample_count} turns judged`}
                  />
                )}
                {summary.kb_stats && summary.kb_stats.total_searches > 0 && (
                  <>
                    <StatCard
                      label="KB Searches"
                      value={summary.kb_stats.total_searches}
                      sub={`avg top score: ${summary.kb_stats.avg_top_score ?? '—'}%`}
                    />
                    <StatCard
                      label="Low Relevance"
                      value={`${(summary.kb_stats.low_relevance_rate * 100).toFixed(0)}%`}
                      color={summary.kb_stats.low_relevance_rate > 0.3 ? 'text-yellow-400' : 'text-green-400'}
                      sub={`${summary.kb_stats.low_relevance_count} searches < 75%`}
                    />
                  </>
                )}
              </div>
            )}
          </>
        )}

        {/* ── Trend Charts ───────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Tool calls per day */}
          {summary && summary.calls_per_day.length > 0 && (
            <div className="bg-gray-800/50 rounded-xl p-4">
              <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-3">Tool Calls — Last {days} Days</h2>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={summary.calls_per_day} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 11 }} tickFormatter={d => d.slice(5)} />
                  <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                    labelStyle={{ color: '#9ca3af' }}
                    itemStyle={{ color: '#60a5fa' }}
                  />
                  <Bar dataKey="count" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Quality score trend */}
          {summary?.quality?.scores_per_day?.some(d => d.avg_score !== null) && (
            <div className="bg-gray-800/50 rounded-xl p-4">
              <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-3">Reply Quality — Last {days} Days</h2>
              <ResponsiveContainer width="100%" height={140}>
                <LineChart
                  data={summary.quality.scores_per_day.filter(d => d.avg_score !== null)}
                  margin={{ top: 0, right: 0, left: -20, bottom: 0 }}
                >
                  <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 11 }} tickFormatter={d => d.slice(5)} />
                  <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} domain={[0, 1]} />
                  <Tooltip
                    contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                    labelStyle={{ color: '#9ca3af' }}
                    formatter={v => [`${(v * 100).toFixed(0)}%`, 'quality']}
                  />
                  <Line type="monotone" dataKey="avg_score" stroke="#10b981" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* ── Top Tools ──────────────────────────────────────────────────── */}
        {summary && summary.top_tools.length > 0 && (
          <div className="bg-gray-800/50 rounded-xl p-4">
            <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-3">Top Tools</h2>
            <div className="space-y-2">
              {summary.top_tools.map(t => (
                <div key={t.name} className="flex items-center gap-3 text-sm">
                  <span className="w-5 text-center">{TOOL_ICON[t.name] || '🔧'}</span>
                  <span className="w-48 truncate text-gray-600 dark:text-gray-300">{t.name}</span>
                  <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full"
                      style={{ width: `${Math.min(100, (t.count / summary.total_tool_calls) * 100 * 3)}%` }}
                    />
                  </div>
                  <span className="text-gray-500 dark:text-gray-500 dark:text-gray-400 w-12 text-right">{t.count}x</span>
                  <span className="text-gray-500 dark:text-gray-500 w-16 text-right">{(t.avg_ms / 1000).toFixed(1)}s avg</span>
                  {t.error_count > 0 && (
                    <span className="text-red-400 text-xs">⚠️ {t.error_count} err</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Event Table ─────────────────────────────────────────────────── */}
        <div className="bg-gray-800/50 rounded-xl overflow-hidden">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-300 dark:border-gray-700">
            <Filter className="w-3.5 h-3.5 text-gray-500 dark:text-gray-500" />
            <input
              value={toolFilter}
              onChange={e => setToolFilter(e.target.value)}
              onBlur={() => loadList(1)}
              onKeyDown={e => e.key === 'Enter' && loadList(1)}
              placeholder="Filter by tool name…"
              className="bg-gray-700 text-xs rounded px-2 py-1 outline-none w-48"
            />
            <select
              value={typeFilter}
              onChange={e => { setTypeFilter(e.target.value); loadList(1) }}
              className="bg-gray-700 text-xs rounded px-2 py-1 outline-none"
            >
              <option value="">All types</option>
              <option value="tool_call">tool_call</option>
              <option value="l2_decision">l2_decision</option>
              <option value="llm_call">llm_call</option>
              <option value="quality_score">quality_score</option>
            </select>
            <span className="ml-auto text-xs text-gray-500 dark:text-gray-500">{total} records</span>
          </div>

          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 dark:text-gray-500 border-b border-gray-300 dark:border-gray-700">
                <th className="text-left px-4 py-2 font-medium">Time</th>
                <th className="text-left px-4 py-2 font-medium">Agent</th>
                <th className="text-left px-4 py-2 font-medium">Tool / Event</th>
                <th className="text-left px-4 py-2 font-medium">Type</th>
                <th className="text-left px-4 py-2 font-medium">Node</th>
                <th className="text-right px-4 py-2 font-medium">Duration</th>
                <th className="text-right px-4 py-2 font-medium">Cost</th>
                <th className="text-center px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={8} className="text-center py-8 text-gray-500 dark:text-gray-500">Loading…</td></tr>
              )}
              {!loading && items.length === 0 && (
                <tr><td colSpan={8} className="text-center py-8 text-gray-600">No audit records yet.</td></tr>
              )}
              {items.map(item => (
                <>
                  <tr
                    key={item.id}
                    onClick={() => setExpanded(expanded === item.id ? null : item.id)}
                    className="border-b border-gray-300 dark:border-gray-700/50 hover:bg-gray-300 dark:hover:bg-gray-700/30 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-2 text-gray-500 dark:text-gray-500 dark:text-gray-400 whitespace-nowrap">{formatTime(item.created_at)}</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-300 max-w-[120px] truncate">{item.agent_name}</td>
                    <td className="px-4 py-2 text-gray-200">
                      {TOOL_ICON[item.tool_name] || '🔧'} {item.tool_name || '—'}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className="px-1.5 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: (EVENT_COLORS[item.event_type] || '#6b7280') + '22',
                          color: EVENT_COLORS[item.event_type] || '#6b7280',
                        }}
                      >
                        {item.event_type}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-gray-500 dark:text-gray-500 text-xs">{item.node_name || '—'}</td>
                    <td className="px-4 py-2 text-right text-gray-500 dark:text-gray-500 dark:text-gray-400">
                      {item.duration_ms != null ? `${(item.duration_ms / 1000).toFixed(2)}s` : '—'}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {item.event_type === 'llm_call' && (item.input_tokens != null || item.output_tokens != null)
                        ? (() => {
                            const cost = ((item.input_tokens || 0) / 1e6 * 3) + ((item.output_tokens || 0) / 1e6 * 15)
                            return <span className="text-yellow-500">${cost < 0.0001 ? '<0.0001' : cost.toFixed(4)}</span>
                          })()
                        : <span className="text-gray-600">—</span>
                      }
                    </td>
                    <td className="px-4 py-2 text-center">
                      {item.event_type === 'l2_decision'
                        ? (item.l2_approved ? '✅ approved' : '❌ rejected')
                        : item.event_type === 'quality_score'
                          ? <span className="text-emerald-400">{item.result_preview}</span>
                          : (item.success ? '✅' : '❌')}
                    </td>
                  </tr>

                  {expanded === item.id && (
                    <tr key={item.id + '_detail'} className="bg-gray-900/60">
                      <td colSpan={8} className="px-6 py-3">
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <p className="text-gray-500 dark:text-gray-500 mb-1 text-xs">Arguments</p>
                            <pre className="text-gray-600 dark:text-gray-300 text-xs bg-gray-100 dark:bg-gray-800 rounded p-2 overflow-auto max-h-32 whitespace-pre-wrap">
                              {JSON.stringify(item.tool_args, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <p className="text-gray-500 dark:text-gray-500 mb-1 text-xs">
                              {item.success ? 'Result Preview' : 'Error'}
                            </p>
                            <pre className="text-gray-600 dark:text-gray-300 text-xs bg-gray-100 dark:bg-gray-800 rounded p-2 overflow-auto max-h-32 whitespace-pre-wrap">
                              {item.error_msg || item.result_preview || '—'}
                            </pre>
                            {(item.input_tokens != null || item.output_tokens != null) && (
                              <p className="text-xs text-gray-500 dark:text-gray-500 mt-2">
                                🔢 Tokens — in: <span className="text-blue-400">{(item.input_tokens || 0).toLocaleString()}</span>
                                {' / '}out: <span className="text-purple-400">{(item.output_tokens || 0).toLocaleString()}</span>
                              </p>
                            )}
                            {/* P3: KB retrieval stats */}
                            {item.event_type === 'tool_call' && item.tool_name === 'search_knowledge_base' && item.extra_data?.top_score != null && (
                              <p className="text-xs mt-2">
                                📚 KB — top score:&nbsp;
                                <span className={item.extra_data.low_relevance ? 'text-yellow-400' : 'text-green-400'}>
                                  {item.extra_data.top_score.toFixed(1)}%
                                </span>
                                &nbsp;·&nbsp;{item.extra_data.result_count} chunks
                                {item.extra_data.low_relevance && <span className="text-yellow-500 ml-1">⚠️ low relevance</span>}
                              </p>
                            )}
                            {/* P2: quality score details */}
                            {item.event_type === 'quality_score' && item.extra_data?.score != null && (
                              <p className="text-xs mt-2 text-gray-500 dark:text-gray-500 dark:text-gray-400">
                                ⚖️ {item.extra_data.verdict} — {item.extra_data.reasoning}
                              </p>
                            )}
                          </div>
                        </div>
                        {/* P0: trace link */}
                        {item.trace_id && (
                          <div className="flex items-center gap-2 mt-2">
                            <p className="text-gray-600 text-xs">Trace: {item.trace_id.slice(0, 8)}…</p>
                            <button
                              onClick={e => { e.stopPropagation(); openTrace(item.trace_id) }}
                              className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                            >
                              <GitBranch className="w-3 h-3" /> View trace waterfall
                            </button>
                          </div>
                        )}
                        {item.conversation_id && (
                          <p className="text-gray-600 text-xs mt-1">Conversation: {item.conversation_id}</p>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>

          {total > PER_PAGE && (
            <div className="flex items-center justify-center gap-2 px-4 py-3 border-t border-gray-300 dark:border-gray-700">
              <button
                disabled={page === 1}
                onClick={() => loadList(page - 1)}
                className="px-3 py-1 text-xs rounded bg-gray-700 disabled:opacity-40 hover:bg-gray-600 transition-colors"
              >Prev</button>
              <span className="text-xs text-gray-500 dark:text-gray-500">{page} / {Math.ceil(total / PER_PAGE)}</span>
              <button
                disabled={page >= Math.ceil(total / PER_PAGE)}
                onClick={() => loadList(page + 1)}
                className="px-3 py-1 text-xs rounded bg-gray-700 disabled:opacity-40 hover:bg-gray-600 transition-colors"
              >Next</button>
            </div>
          )}
        </div>
      </div>

      {/* ── P0: Trace Waterfall Modal ───────────────────────────────────── */}
      {traceModal && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
          onClick={() => setTraceModal(null)}
        >
          <div
            className="bg-gray-50 dark:bg-gray-900 rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-800">
              <div>
                <h2 className="font-semibold text-sm">🔗 Trace Waterfall</h2>
                {traceData && !traceData.error && (
                  <p className="text-xs text-gray-500 dark:text-gray-500 mt-0.5">
                    {traceData.event_count} events · {traceData.total_duration_ms}ms total ·{' '}
                    {traceData.total_input_tokens + traceData.total_output_tokens} tokens
                  </p>
                )}
              </div>
              <button
                onClick={() => setTraceModal(null)}
                className="text-gray-500 dark:text-gray-500 hover:text-gray-900 dark:text-white text-lg leading-none"
              >×</button>
            </div>
            <div className="flex-1 overflow-y-auto p-5">
              {!traceData && <p className="text-gray-500 dark:text-gray-500 text-sm text-center py-8">Loading…</p>}
              {traceData?.error && <p className="text-red-400 text-sm">{traceData.error}</p>}
              {traceData?.events && (
                <div className="space-y-2">
                  {traceData.events.map((ev, i) => (
                    <TraceEvent key={ev.id} ev={ev} index={i} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function TraceEvent({ ev, index }) {
  const [open, setOpen] = useState(false)
  const color = EVENT_COLORS[ev.event_type] || '#6b7280'
  return (
    <div className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-gray-200 dark:hover:bg-gray-800/50 text-left"
      >
        <span className="text-xs text-gray-600 w-4">{index + 1}</span>
        <span
          className="text-xs px-1.5 py-0.5 rounded font-medium shrink-0"
          style={{ background: color + '22', color }}
        >
          {ev.event_type}
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 shrink-0">{ev.node_name || '—'}</span>
        <span className="text-xs text-gray-200 truncate flex-1">
          {TOOL_ICON[ev.tool_name] || '🔧'} {ev.tool_name || '—'}
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-500 shrink-0">
          {ev.duration_ms != null ? `${ev.duration_ms}ms` : '—'}
        </span>
        <span className="text-xs shrink-0">{ev.success ? '✅' : '❌'}</span>
        {open ? <ChevronUp className="w-3 h-3 text-gray-500 dark:text-gray-500" /> : <ChevronDown className="w-3 h-3 text-gray-500 dark:text-gray-500" />}
      </button>
      {open && (
        <div className="px-4 pb-3 grid grid-cols-2 gap-3 bg-gray-900/60">
          {ev.event_type === 'llm_call' && (
            <p className="text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 col-span-2 pt-2">
              Tokens — in: <span className="text-blue-400">{(ev.input_tokens || 0).toLocaleString()}</span>
              {' / '}out: <span className="text-purple-400">{(ev.output_tokens || 0).toLocaleString()}</span>
            </p>
          )}
          {ev.result_preview && (
            <div className="col-span-2 pt-2">
              <p className="text-xs text-gray-500 dark:text-gray-500 mb-1">Result Preview</p>
              <pre className="text-xs bg-gray-100 dark:bg-gray-800 rounded p-2 overflow-auto max-h-24 whitespace-pre-wrap text-gray-600 dark:text-gray-300">
                {ev.result_preview}
              </pre>
            </div>
          )}
          {ev.extra_data && Object.keys(ev.extra_data).length > 0 && (
            <div className="col-span-2">
              <p className="text-xs text-gray-500 dark:text-gray-500 mb-1">Extra Data</p>
              <pre className="text-xs bg-gray-100 dark:bg-gray-800 rounded p-2 text-gray-600 dark:text-gray-300">
                {JSON.stringify(ev.extra_data, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, color = 'text-gray-900 dark:text-white', sub }) {
  return (
    <div className="bg-gray-800/50 rounded-xl px-4 py-3">
      <p className="text-xs text-gray-500 dark:text-gray-500 mb-1">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  })
}
