import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Plus, Settings, Trash2, Database, Send, ChevronRight, Pencil, UserX, FileText } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import toast from 'react-hot-toast'
import { agentApi, convApi, examApi, createWebSocket } from '../api/client.js'
import KnowledgePanel from './KnowledgePanel.jsx'
import EditAgentModal from './EditAgentModal.jsx'
import PromptPanel from './PromptPanel.jsx'

export default function ChatView({ agents, onOffboard, onUpdate }) {
  const { agentId, convId } = useParams()
  const navigate = useNavigate()

  const agent = agents.find(a => a.id === agentId)
  const [conversations, setConversations] = useState([])
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showKb, setShowKb] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [showPrompt, setShowPrompt] = useState(false)
  const [pendingApproval, setPendingApproval] = useState(null)
  const [renamingId, setRenamingId] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleteModal, setDeleteModal] = useState(null)   // { id, title } | null
  const [confirmOffboard, setConfirmOffboard] = useState(false)
  const [savingKb, setSavingKb] = useState(false)
  const wsRef = useRef(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (agentId) loadConversations()
  }, [agentId])

  useEffect(() => {
    if (convId) loadMessages()
  }, [convId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function loadConversations() {
    try {
      const data = await agentApi.listConversations(agentId)
      setConversations(data)
    } catch {}
  }

  async function loadMessages() {
    try {
      const data = await convApi.get(convId)
      setMessages(data.messages || [])
    } catch {}
  }

  async function newConversation() {
    try {
      const conv = await agentApi.createConversation(agentId)
      await loadConversations()
      navigate(`/agent/${agentId}/conv/${conv.id}`)
      setMessages([])
    } catch {
      toast.error('Failed to create conversation')
    }
  }

  const connectWs = useCallback(() => {
    if (!convId) return
    if (wsRef.current) wsRef.current.close()

    const ws = createWebSocket(convId)
    wsRef.current = ws

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)

      // Helper: append a step to the current thinking bubble
      const addStep = (step) => setMessages(prev => prev.map(m =>
        m.role === 'thinking' ? { ...m, steps: [...(m.steps || []), step] } : m
      ))

      if (data.type === 'thinking') {
        setMessages(prev => {
          if (prev.some(m => m.role === 'thinking')) return prev
          return [...prev, { id: 'thinking', role: 'thinking', steps: [] }]
        })
      } else if (data.type === 'thinking_text') {
        addStep({ type: 'text', content: data.content })
      } else if (data.type === 'tool_call') {
        addStep({ type: 'tool', name: data.tool, preview: data.preview })
      } else if (data.type === 'tool_result') {
        addStep({ type: 'result', content: data.content })
      } else if (data.type === 'message_start') {
        // Server is about to stream tokens — create an empty assistant bubble
        setMessages(prev => [
          ...prev.filter(m => m.role !== 'thinking'),
          { id: 'streaming', role: 'assistant', content: '' }
        ])
      } else if (data.type === 'token') {
        // Append token to the streaming bubble
        setMessages(prev => prev.map(m =>
          m.id === 'streaming' ? { ...m, content: m.content + data.content } : m
        ))
      } else if (data.type === 'message') {
        setMessages(prev => [
          ...prev.filter(m => m.role !== 'thinking'),
          { id: Date.now(), role: 'assistant', content: data.content }
        ])
      } else if (data.type === 'approval_required') {
        setMessages(prev => prev.filter(m => m.role !== 'thinking'))
        setPendingApproval(data)
        setLoading(false)
      } else if (data.type === 'done') {
        // Finalise any streaming bubble
        setMessages(prev => prev.map(m =>
          m.id === 'streaming' ? { ...m, id: Date.now() } : m
        ))
        setLoading(false)
        loadConversations()  // refresh title
      } else if (data.type === 'error') {
        toast.error(data.content)
        setMessages(prev => prev.filter(m => m.role !== 'thinking'))
        setLoading(false)
      }
    }

    ws.onclose = () => {
      // Always unlock the input when the connection drops,
      // so the user isn't left with a permanently disabled input box.
      setLoading(false)
    }
  }, [convId])

  useEffect(() => {
    connectWs()
    return () => wsRef.current?.close()
  }, [connectWs])

  function sendMessage() {
    if (!input.trim() || loading || !wsRef.current) return
    const content = input.trim()
    setInput('')
    setLoading(true)
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', content }])
    wsRef.current.send(JSON.stringify({ type: 'message', content }))
  }

  function startRename(conv, e) {
    e.preventDefault()
    e.stopPropagation()
    setRenamingId(conv.id)
    setRenameValue(conv.title)
  }

  async function submitRename(id) {
    const title = renameValue.trim()
    if (!title) { setRenamingId(null); return }
    try {
      await convApi.rename(id, title)
      setConversations(prev => prev.map(c => c.id === id ? { ...c, title } : c))
    } catch {
      toast.error('Rename failed')
    }
    setRenamingId(null)
  }

  function deleteConversation(id, e) {
    e.preventDefault()
    e.stopPropagation()
    const conv = conversations.find(c => c.id === id)
    setDeleteModal({ id, title: conv?.title || 'this conversation' })
  }

  async function confirmDelete(saveKb) {
    const { id } = deleteModal
    setDeleteModal(null)
    try {
      if (saveKb) {
        setSavingKb(true)
        try {
          const result = await convApi.saveToKb(id)
          toast.success(`Saved to KB: "${result.title}" (${result.chunks} chunks)`)
        } catch {
          toast.error('Failed to save to knowledge base')
          setSavingKb(false)
          return
        }
        setSavingKb(false)
      }
      await convApi.delete(id)
      setConversations(prev => prev.filter(c => c.id !== id))
      if (convId === id) navigate(`/agent/${agentId}`)
    } catch {
      toast.error('Failed to delete conversation')
    }
  }

  function handleApproval(approved) {
    wsRef.current?.send(JSON.stringify({ type: 'approval', approved }))
    setPendingApproval(null)
    if (approved) setLoading(true)
  }

  if (!agent) return <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-500">Agent not found</div>

  return (
    <div className="flex h-full">
      {/* Conversation history sidebar */}
      <div className="w-56 flex flex-col bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 shrink-0">
        <div className="p-3 border-b border-gray-200 dark:border-gray-800">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xl">{agent.avatar_emoji}</span>
            <span className="font-semibold text-sm truncate">{agent.name}</span>
          </div>
          <button
            onClick={newConversation}
            className="w-full flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-lg bg-blue-600 hover:bg-blue-500 transition-colors"
          >
            <Plus className="w-3 h-3" /> New Chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.map(c => (
            <div key={c.id} className="group relative">
              {renamingId === c.id ? (
                <input
                  autoFocus
                  value={renameValue}
                  onChange={e => setRenameValue(e.target.value)}
                  onBlur={() => submitRename(c.id)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') submitRename(c.id)
                    if (e.key === 'Escape') setRenamingId(null)
                  }}
                  className="w-full px-2 py-1 text-xs rounded bg-gray-600 text-gray-900 dark:text-white outline-none border border-blue-500"
                />
              ) : (
                <Link
                  to={`/agent/${agentId}/conv/${c.id}`}
                  className={`flex items-center justify-between px-2 py-1.5 rounded text-xs transition-colors ${
                    c.id === convId ? 'bg-gray-700 text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-800'
                  }`}
                >
                  <span className="truncate flex-1">{c.title}</span>
                  <div className="shrink-0 ml-1 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={e => startRename(c, e)}
                      className="text-gray-500 dark:text-gray-500 hover:text-gray-200 p-0.5"
                      title="Rename"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                    <button
                      onClick={e => deleteConversation(c.id, e)}
                      className="text-gray-500 dark:text-gray-500 hover:text-red-400 p-0.5"
                      title="Delete"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </Link>
              )}
            </div>
          ))}
        </div>
        {/* Agent actions */}
        <div className="p-2 border-t border-gray-200 dark:border-gray-800 space-y-1">
          <button onClick={() => setShowPrompt(true)} className="w-full flex items-center gap-2 px-2 py-1.5 text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:bg-gray-800 rounded">
            <FileText className="w-3 h-3" /> Prompt
          </button>
          <button onClick={() => setShowKb(true)} className="w-full flex items-center gap-2 px-2 py-1.5 text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:bg-gray-800 rounded">
            <Database className="w-3 h-3" /> Knowledge Base
          </button>
          <button onClick={() => setShowEdit(true)} className="w-full flex items-center gap-2 px-2 py-1.5 text-xs text-gray-500 dark:text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:bg-gray-800 rounded">
            <Settings className="w-3 h-3" /> Settings
          </button>
          {confirmOffboard ? (
            <div className="space-y-1.5 pt-1">
              <p className="text-[11px] text-gray-500 dark:text-gray-400 text-center">Offboard this employee?</p>
              <div className="flex gap-1.5">
                <button
                  onClick={() => setConfirmOffboard(false)}
                  className="flex-1 px-2 py-1.5 text-xs text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => { setConfirmOffboard(false); onOffboard(agentId) }}
                  className="flex-1 px-2 py-1.5 text-xs text-white bg-orange-500 hover:bg-orange-600 rounded-lg transition-colors"
                >
                  Offboard
                </button>
              </div>
            </div>
          ) : (
            <button onClick={() => setConfirmOffboard(true)} className="w-full flex items-center gap-2 px-2 py-1.5 text-xs text-orange-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded">
              <UserX className="w-3 h-3" /> Offboard Employee
            </button>
          )}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!convId ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-8">
            <span className="text-5xl mb-4">{agent.avatar_emoji}</span>
            <h2 className="text-xl font-bold mb-2">{agent.name}</h2>
            <p className="text-gray-500 dark:text-gray-500 dark:text-gray-400 text-sm mb-2">{agent.product_line} specialist</p>
            {agent.description && <p className="text-gray-500 dark:text-gray-500 text-sm mb-6 max-w-sm">{agent.description}</p>}
            <button onClick={newConversation} className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl font-medium transition-colors">
              Start a conversation
            </button>
          </div>
        ) : (
          <>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
              {messages.length === 0 && (
                <div className="text-center text-gray-600 text-sm pt-8">
                  Say something to {agent.name}...
                </div>
              )}
              {messages.map((msg, idx) => (
                <MessageBubble key={msg.id || idx} message={msg} agent={agent} />
              ))}
              {pendingApproval && (
                <ApprovalCard approval={pendingApproval} onApprove={handleApproval} />
              )}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="p-4 border-t border-gray-200 dark:border-gray-800">
              <div className="flex gap-2">
                <input
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), sendMessage())}
                  placeholder={`Message ${agent.name}...`}
                  disabled={loading}
                  className="flex-1 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-blue-500 disabled:opacity-50 transition-colors"
                />
                <button
                  onClick={sendMessage}
                  disabled={loading || !input.trim()}
                  className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-xl transition-colors"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {showKb && <KnowledgePanel agentId={agentId} onClose={() => setShowKb(false)} />}
      {showPrompt && (
        <PromptPanel
          agentId={agentId}
          agentName={agent?.name || ''}
          onClose={() => setShowPrompt(false)}
        />
      )}
      {showEdit && (
        <EditAgentModal
          agent={agent}
          onClose={() => setShowEdit(false)}
          onUpdate={() => { setShowEdit(false); onUpdate() }}
        />
      )}

      {/* Delete confirmation modal */}
      {deleteModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-80 space-y-4">
            <h3 className="font-semibold text-gray-800">Delete conversation</h3>
            <p className="text-sm text-gray-600">
              Save <span className="font-medium">"{deleteModal.title}"</span> to {agent?.name}'s knowledge base before deleting?
            </p>
            <div className="flex flex-col gap-2 pt-1">
              <button
                onClick={() => confirmDelete(true)}
                className="w-full py-2 rounded-lg bg-blue-600 text-gray-900 dark:text-white text-sm font-medium hover:bg-blue-700"
              >
                Save to KB &amp; delete
              </button>
              <button
                onClick={() => confirmDelete(false)}
                className="w-full py-2 rounded-lg bg-red-50 text-red-600 text-sm font-medium hover:bg-red-100"
              >
                Delete without saving
              </button>
              <button
                onClick={() => setDeleteModal(null)}
                className="w-full py-2 rounded-lg text-gray-500 dark:text-gray-500 text-sm hover:bg-gray-100"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Saving overlay */}
      {savingKb && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl px-8 py-6 text-sm text-gray-700 flex items-center gap-3">
            <svg className="animate-spin h-5 w-5 text-blue-600" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
            </svg>
            Generating summary and saving to knowledge base…
          </div>
        </div>
      )}
    </div>
  )
}

const TOOL_ICON = {
  search_knowledge_base: '📚',
  search_confluence:     '🔍',
  save_confluence_page:  '💾',
  read_requirement_doc:  '📄',
  write_output_file:     '💾',
  create_defect_mock:    '🐛',
  search_jira:           '🎫',
  get_jira_issue:        '🎫',
  get_gitlab_mr_diff:    '🔀',
  save_to_memory:        '🧠',
}

function MessageBubble({ message, agent }) {
  if (message.role === 'thinking') {
    const steps = message.steps || []
    return (
      <div className="flex gap-3">
        <span className="text-xl shrink-0 mt-0.5">{agent.avatar_emoji}</span>
        <div className="flex-1 max-w-[80%]">
          <div className="bg-gray-800/60 border border-gray-300 dark:border-gray-700/50 rounded-xl px-3 py-2.5 space-y-1.5">
            {steps.length === 0 && (
              <span className="text-gray-500 dark:text-gray-500 text-xs italic">Thinking…</span>
            )}
            {steps.map((step, i) => {
              if (step.type === 'text') return (
                <p key={i} className="text-gray-500 dark:text-gray-500 dark:text-gray-400 text-xs italic leading-relaxed line-clamp-3">
                  💭 {step.content}
                </p>
              )
              if (step.type === 'tool') return (
                <div key={i} className="flex items-start gap-1.5 text-xs text-cyan-400">
                  <span className="shrink-0 mt-px">{TOOL_ICON[step.name] || '🔧'}</span>
                  <span className="font-medium">{step.name}</span>
                  {step.preview && (
                    <span className="text-gray-500 dark:text-gray-500 truncate">— {step.preview}</span>
                  )}
                </div>
              )
              if (step.type === 'result') return (
                <div key={i} className="text-xs text-gray-600 pl-4 border-l border-gray-300 dark:border-gray-700 line-clamp-2">
                  ↳ {step.content}
                </div>
              )
              return null
            })}
            {/* Animated dots: always visible while this bubble exists */}
            <div className="flex gap-1 pt-0.5">
              <span className="w-1.5 h-1.5 bg-gray-600 rounded-full animate-bounce" style={{animationDelay:'0ms'}} />
              <span className="w-1.5 h-1.5 bg-gray-600 rounded-full animate-bounce" style={{animationDelay:'150ms'}} />
              <span className="w-1.5 h-1.5 bg-gray-600 rounded-full animate-bounce" style={{animationDelay:'300ms'}} />
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%] bg-blue-600 rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm">
          {message.content}
        </div>
      </div>
    )
  }

  // Detect exam draft marker
  const hasDraftMarker = message.content && message.content.includes('DRAFT_ID:')
  const draftIdMatch = message.content?.match(/DRAFT_ID:([^\s\n]+)/)
  const draftId = draftIdMatch ? draftIdMatch[1] : null

  return (
    <div className="flex gap-3 flex-col">
      <div className="flex gap-3">
        <span className="text-xl shrink-0 mt-0.5">{agent.avatar_emoji}</span>
        <div className="max-w-[80%] bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-tl-sm px-4 py-3 text-sm">
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
          {message.tool_calls?.length > 0 && (
            <div className="mt-2 pt-2 border-t border-gray-300 dark:border-gray-700 space-y-1">
              {message.tool_calls.map((tc, i) => (
                <div key={i} className="text-xs text-gray-500 dark:text-gray-500 flex items-center gap-1">
                  <ChevronRight className="w-3 h-3" />
                  🔧 {tc.name}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {hasDraftMarker && draftId && (
        <ExamDraftCard draftId={draftId} />
      )}
    </div>
  )
}

function ExamDraftCard({ draftId }) {
  const [publishing, setPublishing] = useState(false)
  const [hidden, setHidden] = useState(false)

  async function handlePublish() {
    setPublishing(true)
    try {
      await examApi.examDrafts.publish(draftId)
      toast.success('✅ Added to exam library!')
      setHidden(true)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to publish exam')
    } finally {
      setPublishing(false)
    }
  }

  async function handleDiscard() {
    try {
      await examApi.examDrafts.discard(draftId)
      toast.success('Draft discarded')
      setHidden(true)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to discard draft')
    }
  }

  if (hidden) return null

  return (
    <div className="mx-auto max-w-md bg-amber-900/30 border border-amber-700/50 rounded-xl p-4 mt-2">
      <p className="text-amber-400 font-semibold text-sm mb-2">📋 Exam Case Draft: {draftId}</p>
      <p className="text-gray-600 dark:text-gray-300 text-xs mb-3">
        Review the draft above, then add it to the exam library for future use.
      </p>
      <div className="flex gap-2">
        <button
          onClick={handlePublish}
          disabled={publishing}
          className="flex-1 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          {publishing ? 'Adding...' : 'Add to Exam Library'}
        </button>
        <button
          onClick={handleDiscard}
          disabled={publishing}
          className="flex-1 py-1.5 bg-red-900 hover:bg-red-800 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          Discard
        </button>
      </div>
    </div>
  )
}

function ApprovalCard({ approval, onApprove }) {
  return (
    <div className="mx-auto max-w-md bg-yellow-900/30 border border-yellow-700/50 rounded-xl p-4">
      <p className="text-yellow-400 font-semibold text-sm mb-1">⚠️ Mentor Approval Required</p>
      <p className="text-gray-600 dark:text-gray-300 text-sm mb-3">
        Agent wants to run <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{approval.tool}</code>
      </p>
      <pre className="text-xs bg-gray-50 dark:bg-gray-900 rounded p-2 mb-3 overflow-auto max-h-24 text-gray-500 dark:text-gray-500 dark:text-gray-400">
        {JSON.stringify(approval.args, null, 2)}
      </pre>
      <div className="flex gap-2">
        <button onClick={() => onApprove(true)} className="flex-1 py-1.5 bg-green-700 hover:bg-green-600 rounded-lg text-sm font-medium transition-colors">
          ✅ Approve
        </button>
        <button onClick={() => onApprove(false)} className="flex-1 py-1.5 bg-red-900 hover:bg-red-800 rounded-lg text-sm font-medium transition-colors">
          ❌ Reject
        </button>
      </div>
    </div>
  )
}
