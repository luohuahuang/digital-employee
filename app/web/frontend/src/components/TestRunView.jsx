import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { CheckCircle, XCircle, Clock, ChevronDown, ChevronUp, ArrowLeft, RefreshCw, StopCircle } from 'lucide-react'
import { testRunApi } from '../api/client.js'
import toast from 'react-hot-toast'

// ── Status helpers ──────────────────────────────────────────────────────────

const STATUS_STYLE = {
  pass:       { icon: CheckCircle, color: 'text-green-500',  bg: 'bg-green-50 dark:bg-green-900/20',    label: 'Pass'       },
  fail:       { icon: XCircle,     color: 'text-red-500',    bg: 'bg-red-50 dark:bg-red-900/20',        label: 'Fail'       },
  error:      { icon: XCircle,     color: 'text-orange-500', bg: 'bg-orange-50 dark:bg-orange-900/20',  label: 'Error'      },
  pending:    { icon: Clock,       color: 'text-gray-400',   bg: 'bg-gray-50 dark:bg-gray-800',         label: 'Pending'    },
  running:    { icon: Clock,       color: 'text-blue-400',   bg: 'bg-blue-50 dark:bg-blue-900/20',      label: 'Running'    },
  terminated: { icon: StopCircle,  color: 'text-yellow-500', bg: 'bg-yellow-50 dark:bg-yellow-900/20',  label: 'Terminated' },
  completed:  { icon: CheckCircle, color: 'text-green-500',  bg: 'bg-green-50 dark:bg-green-900/20',    label: 'Completed'  },
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

// ── Step detail row ─────────────────────────────────────────────────────────

function StepRow({ step, index }) {
  const [open, setOpen] = useState(false)
  const passed = step.passed

  return (
    <div className={`border rounded-lg overflow-hidden ${passed ? 'border-green-200 dark:border-green-800' : 'border-red-200 dark:border-red-800'}`}>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        <span className={`text-xs font-mono font-bold w-6 shrink-0 ${passed ? 'text-green-500' : 'text-red-500'}`}>
          {String(index + 1).padStart(2, '0')}
        </span>
        <span className="flex-1 text-sm text-gray-700 dark:text-gray-300 truncate">{step.description}</span>
        <StatusBadge status={passed ? 'pass' : 'fail'} small />
        {open ? <ChevronUp className="w-4 h-4 text-gray-400 shrink-0" /> : <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 bg-gray-50 dark:bg-gray-900 space-y-3 border-t border-gray-100 dark:border-gray-800">
          {/* Expected vs reason */}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="text-gray-400 uppercase tracking-wider mb-1">Expected</p>
              <p className="text-gray-700 dark:text-gray-300">{step.expected || '—'}</p>
            </div>
            <div>
              <p className={`uppercase tracking-wider mb-1 ${passed ? 'text-green-500' : 'text-red-500'}`}>
                {passed ? 'Result' : 'Failure reason'}
              </p>
              <p className="text-gray-700 dark:text-gray-300">{step.reason || step.error || '—'}</p>
            </div>
          </div>

          {/* Actions taken */}
          {step.actions_taken?.length > 0 && (
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Actions</p>
              <div className="flex flex-wrap gap-1.5">
                {step.actions_taken.map((a, i) => (
                  <span key={i} className="text-[11px] bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded font-mono">
                    {a.type}{a.x !== undefined ? ` (${a.x}, ${a.y})` : ''}{a.text ? ` "${a.text}"` : ''}{a.key ? ` ${a.key}` : ''}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Screenshots */}
          <ScreenshotPair before={step.screenshot_before} after={step.screenshot_after} />
        </div>
      )}
    </div>
  )
}

function ScreenshotPair({ before, after }) {
  if (!before && !after) return null
  // Convert absolute disk paths to API URLs
  const toUrl = (path) => {
    if (!path) return null
    const parts = path.replace(/\\/g, '/').split('/')
    const runId = parts[parts.indexOf('test_runs') + 1]
    const filename = parts[parts.length - 1]
    return `/api/test-runs/screenshots/${runId}/${filename}`
  }
  const beforeUrl = toUrl(before)
  const afterUrl = toUrl(after)
  return (
    <div className="grid grid-cols-2 gap-3">
      {beforeUrl && <ScreenshotThumb url={beforeUrl} label="Before" />}
      {afterUrl  && <ScreenshotThumb url={afterUrl}  label="After"  />}
    </div>
  )
}

function ScreenshotThumb({ url, label }) {
  const [enlarged, setEnlarged] = useState(false)
  return (
    <>
      <div>
        <p className="text-[11px] text-gray-400 mb-1">{label}</p>
        <img
          src={url}
          alt={label}
          className="w-full rounded border border-gray-200 dark:border-gray-700 cursor-zoom-in hover:opacity-90 transition-opacity"
          onClick={() => setEnlarged(true)}
        />
      </div>
      {enlarged && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setEnlarged(false)}
        >
          <img src={url} alt={label} className="max-w-full max-h-full rounded shadow-2xl" />
        </div>
      )}
    </>
  )
}

// ── Case row ────────────────────────────────────────────────────────────────

function CaseRow({ c }) {
  const [open, setOpen] = useState(false)
  const steps = Array.isArray(c.steps_json) ? c.steps_json : []
  const isPending = c.status === 'pending' || c.status === 'running'

  return (
    <div className={`border rounded-xl overflow-hidden ${
      c.status === 'pass'  ? 'border-green-200 dark:border-green-800' :
      c.status === 'fail'  ? 'border-red-200 dark:border-red-800' :
      c.status === 'error' ? 'border-orange-200 dark:border-orange-800' :
      'border-gray-200 dark:border-gray-700'
    }`}>
      <button
        onClick={() => !isPending && setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
        disabled={isPending}
      >
        <StatusBadge status={c.status} small />
        <span className="flex-1 font-medium text-sm text-gray-800 dark:text-gray-200 truncate">{c.case_title}</span>
        {c.failure_step && (
          <span className="text-xs text-red-400 shrink-0">Failed at step {c.failure_step}</span>
        )}
        {!isPending && (
          open
            ? <ChevronUp className="w-4 h-4 text-gray-400 shrink-0" />
            : <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 bg-white dark:bg-gray-900 border-t border-gray-100 dark:border-gray-800 space-y-2">
          {c.actual_result && (
            <p className="text-xs text-gray-500 dark:text-gray-400 italic mb-2">{c.actual_result}</p>
          )}
          {steps.length > 0
            ? steps.map((step, i) => <StepRow key={i} step={step} index={i} />)
            : <p className="text-xs text-gray-400 dark:text-gray-600 py-3 text-center">No step details recorded for this run.</p>
          }
        </div>
      )}
    </div>
  )
}

// ── Main view ───────────────────────────────────────────────────────────────

export default function TestRunView() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const [run, setRun] = useState(null)
  const [loading, setLoading] = useState(true)
  const [terminating, setTerminating] = useState(false)
  const [showTerminateConfirm, setShowTerminateConfirm] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await testRunApi.get(runId)
      setRun(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => { load() }, [load])

  // Poll while running / pending
  useEffect(() => {
    if (!run) return
    if (run.status !== 'running' && run.status !== 'pending') return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [run, load])

  const isActive = run?.status === 'running' || run?.status === 'pending'

  async function handleTerminate() {
    setTerminating(true)
    try {
      await testRunApi.terminate(runId)
      toast.success('Run terminated')
      load()
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to terminate run')
    } finally {
      setTerminating(false)
      setShowTerminateConfirm(false)
    }
  }

  if (loading) return (
    <div className="flex-1 flex items-center justify-center text-gray-400">Loading…</div>
  )
  if (!run) return (
    <div className="flex-1 flex items-center justify-center text-gray-400">Run not found.</div>
  )

  const cases = run.cases || []
  const passRate = run.total_cases > 0
    ? Math.round((run.passed / run.total_cases) * 100)
    : 0

  return (
    <div className="h-full flex flex-col overflow-hidden bg-white dark:bg-gray-950">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center gap-4">
        <button
          onClick={() => navigate('/test-platform/runs')}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="font-semibold text-gray-900 dark:text-white truncate">{run.name}</h1>
            {run.platform && run.platform !== 'web' && (
              <span className="shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded bg-green-900/40 text-green-400 border border-green-800/60">
                {run.platform === 'android' ? '🤖 Android' : run.platform}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-0.5">{run.base_url}</p>
        </div>
        <StatusBadge status={run.status} />
        {isActive && (
          <button
            onClick={() => setShowTerminateConfirm(true)}
            disabled={terminating}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600/10 border border-red-600/30 text-red-400 hover:bg-red-600/20 text-xs font-medium transition-colors disabled:opacity-40"
            title="Terminate run"
          >
            <StopCircle className="w-3.5 h-3.5" />
            {terminating ? 'Stopping…' : 'Terminate'}
          </button>
        )}
        <button
          onClick={load}
          className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 transition-colors"
          title="Refresh"
        >
          <RefreshCw className={`w-4 h-4 ${isActive ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Progress bar + stats */}
      <div className="px-6 py-3 border-b border-gray-100 dark:border-gray-800 flex items-center gap-6">
        <div className="flex-1">
          <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 transition-all duration-500"
              style={{ width: `${passRate}%` }}
            />
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm shrink-0">
          <span className="text-green-500 font-medium">{run.passed} passed</span>
          <span className="text-red-500 font-medium">{run.failed} failed</span>
          <span className="text-gray-400">{run.total_cases} total</span>
          <span className="font-bold text-gray-700 dark:text-gray-300">{passRate}%</span>
        </div>
      </div>

      {/* Case list */}
      <div className="flex-1 min-h-0 overflow-y-auto p-6 space-y-3">
        {cases.length === 0 && (
          <p className="text-center text-gray-400 py-12">No cases found.</p>
        )}
        {cases.map(c => <CaseRow key={c.id} c={c} />)}
      </div>

      {/* Terminate confirm modal */}
      {showTerminateConfirm && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-sm p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center shrink-0">
                <StopCircle className="w-5 h-5 text-red-500" />
              </div>
              <div>
                <h2 className="font-semibold text-gray-900 dark:text-white">Terminate run?</h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  The current case will finish, then execution stops.
                </p>
              </div>
            </div>
            <div className="flex gap-3 pt-1">
              <button
                onClick={() => setShowTerminateConfirm(false)}
                className="flex-1 px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleTerminate}
                disabled={terminating}
                className="flex-1 px-4 py-2 text-sm rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-medium transition-colors"
              >
                {terminating ? 'Stopping…' : 'Terminate'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
