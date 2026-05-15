import { useState, useEffect } from 'react'
import { X, GitMerge, Upload, RefreshCw } from 'lucide-react'
import { agentApi } from '../api/client.js'
import toast from 'react-hot-toast'

export default function KnowledgePanel({ agentId, onClose }) {
  const [kbStatus, setKbStatus] = useState(null)
  const [selectedSources, setSelectedSources] = useState(new Set())
  const [merging, setMerging] = useState(false)

  useEffect(() => { loadKbStatus() }, [agentId])

  async function loadKbStatus() {
    try {
      const data = await agentApi.getKbStatus(agentId)
      setKbStatus(data)
    } catch { toast.error('Failed to load KB status') }
  }

  async function handleMerge() {
    if (selectedSources.size === 0) return
    setMerging(true)
    try {
      const result = await agentApi.mergeToMain(agentId, [...selectedSources])
      toast.success(`Merged ${result.merged.length} source(s) to Main KB`)
      setSelectedSources(new Set())
      loadKbStatus()
    } catch { toast.error('Merge failed') }
    setMerging(false)
  }

  function toggleSource(src) {
    setSelectedSources(prev => {
      const next = new Set(prev)
      next.has(src) ? next.delete(src) : next.add(src)
      return next
    })
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-50 dark:bg-gray-900 rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col border border-gray-300 dark:border-gray-700">
        <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-800">
          <h2 className="font-bold text-lg">Knowledge Base</h2>
          <button onClick={onClose} className="text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Main KB */}
          <section>
            <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-2">
              🌐 Main KB (shared)
              <span className="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded-full">
                {kbStatus?.main?.total_chunks ?? '…'} chunks
              </span>
            </h3>
            {kbStatus?.main?.sources && Object.keys(kbStatus.main.sources).length > 0 ? (
              <div className="space-y-1">
                {Object.entries(kbStatus.main.sources).map(([src, count]) => (
                  <div key={src} className="flex items-center justify-between text-sm bg-gray-100 dark:bg-gray-800 rounded-lg px-3 py-2">
                    <span className="text-gray-600 dark:text-gray-300 truncate">{src}</span>
                    <span className="text-gray-500 dark:text-gray-500 text-xs ml-2 shrink-0">{count} chunks</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-600 text-sm">No sources in Main KB yet.</p>
            )}
          </section>

          {/* Branch KB */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-500 dark:text-gray-400 flex items-center gap-2">
                🌿 Branch KB (this agent)
                <span className="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded-full">
                  {kbStatus?.branch?.total_chunks ?? '…'} chunks
                </span>
              </h3>
              {selectedSources.size > 0 && (
                <button
                  onClick={handleMerge}
                  disabled={merging}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-green-700 hover:bg-green-600 disabled:opacity-50 rounded-lg text-xs font-medium transition-colors"
                >
                  <GitMerge className="w-3 h-3" />
                  {merging ? 'Merging…' : `Merge ${selectedSources.size} to Main`}
                </button>
              )}
            </div>
            {kbStatus?.branch?.sources && Object.keys(kbStatus.branch.sources).length > 0 ? (
              <div className="space-y-1">
                {Object.entries(kbStatus.branch.sources).map(([src, count]) => (
                  <div
                    key={src}
                    onClick={() => toggleSource(src)}
                    className={`flex items-center justify-between text-sm rounded-lg px-3 py-2 cursor-pointer transition-colors ${
                      selectedSources.has(src)
                        ? 'bg-green-900/40 border border-green-700'
                        : 'bg-gray-100 dark:bg-gray-800 hover:bg-gray-750 border border-transparent'
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <input
                        type="checkbox"
                        checked={selectedSources.has(src)}
                        onChange={() => toggleSource(src)}
                        onClick={e => e.stopPropagation()}
                        className="accent-green-500 shrink-0"
                      />
                      <span className="text-gray-600 dark:text-gray-300 truncate">{src}</span>
                    </div>
                    <span className="text-gray-500 dark:text-gray-500 text-xs ml-2 shrink-0">{count} chunks</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-600 text-sm">No branch-specific knowledge yet. Use <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">save_confluence_page</code> during chat to add content.</p>
            )}
          </section>
        </div>

        <div className="p-4 border-t border-gray-200 dark:border-gray-800 flex justify-end">
          <button
            onClick={loadKbStatus}
            className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:text-white transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
        </div>
      </div>
    </div>
  )
}
