import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Send, Trash2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import toast from 'react-hot-toast'
import { groupApi, createGroupWebSocket } from '../api/client.js'

// One colour palette entry per agent position (up to 6 agents)
const AGENT_PALETTES = [
  { bubble: 'bg-blue-900/40 border-blue-700/40',   name: 'text-blue-400',   dot: 'bg-blue-400' },
  { bubble: 'bg-green-900/40 border-green-700/40', name: 'text-green-400',  dot: 'bg-green-400' },
  { bubble: 'bg-purple-900/40 border-purple-700/40', name: 'text-purple-400', dot: 'bg-purple-400' },
  { bubble: 'bg-orange-900/40 border-orange-700/40', name: 'text-orange-400', dot: 'bg-orange-400' },
  { bubble: 'bg-pink-900/40 border-pink-700/40',   name: 'text-pink-400',   dot: 'bg-pink-400' },
  { bubble: 'bg-teal-900/40 border-teal-700/40',   name: 'text-teal-400',   dot: 'bg-teal-400' },
]

function usePalette(members) {
  const map = {}
  ;(members || []).forEach((m, i) => {
    map[m.agent_id] = AGENT_PALETTES[i % AGENT_PALETTES.length]
  })
  return map
}

// ── Message bubble ─────────────────────────────────────────────────────────────

function MessageBubble({ msg, palette }) {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-blue-600 rounded-2xl rounded-br-sm px-4 py-2.5 text-sm text-gray-900 dark:text-white">
          {msg.content}
        </div>
      </div>
    )
  }

  if (msg.is_pass) {
    return (
      <div className="flex items-center gap-2 py-0.5">
        <span className="text-base opacity-50">{msg.emoji}</span>
        <span className="text-xs text-gray-600 italic">{msg.speaker} had nothing to add from their domain</span>
      </div>
    )
  }

  const pal = palette[msg.agent_id] || AGENT_PALETTES[0]
  return (
    <div className="flex gap-3 items-start">
      <span className="text-2xl shrink-0 mt-0.5">{msg.emoji}</span>
      <div className="flex-1 min-w-0">
        <p className={`text-xs font-semibold mb-1 ${pal.name}`}>{msg.speaker}</p>
        <div className={`rounded-2xl rounded-tl-sm border px-4 py-2.5 text-sm text-gray-800 dark:text-gray-100 ${pal.bubble}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
        </div>
      </div>
    </div>
  )
}

// ── Thinking indicator ─────────────────────────────────────────────────────────

function ThinkingBubble({ emoji, name, palette }) {
  const pal = palette || AGENT_PALETTES[0]
  return (
    <div className="flex gap-3 items-start">
      <span className="text-2xl shrink-0 mt-0.5">{emoji}</span>
      <div className="flex-1 min-w-0">
        <p className={`text-xs font-semibold mb-1 ${pal.name}`}>{name}</p>
        <div className={`inline-flex items-center gap-1.5 rounded-2xl rounded-tl-sm border px-4 py-2.5 ${pal.bubble}`}>
          <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.3s]" />
          <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.15s]" />
          <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" />
        </div>
      </div>
    </div>
  )
}

// ── Main view ──────────────────────────────────────────────────────────────────

export default function GroupChatView({ onGroupsChange }) {
  const { groupId } = useParams()
  const navigate    = useNavigate()

  const [group,    setGroup]    = useState(null)
  const [messages, setMessages] = useState([])
  const [thinking, setThinking] = useState(null)   // {agent_id, agent_name, agent_emoji}
  const [input,    setInput]    = useState('')
  const [loading,  setLoading]  = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const wsRef     = useRef(null)
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  // Load group data
  useEffect(() => {
    if (!groupId) return
    groupApi.get(groupId)
      .then(data => {
        setGroup(data)
        setMessages(data.messages || [])
      })
      .catch(() => toast.error('Failed to load group chat'))
  }, [groupId])

  // WebSocket
  const connectWs = useCallback(() => {
    if (!groupId) return
    if (wsRef.current) wsRef.current.close()

    const ws = createGroupWebSocket(groupId)
    wsRef.current = ws

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)

      if (data.type === 'agent_thinking') {
        setThinking({ agent_id: data.agent_id, agent_name: data.agent_name, agent_emoji: data.agent_emoji })

      } else if (data.type === 'agent_message') {
        setThinking(null)
        setMessages(prev => [...prev, {
          id:       Date.now() + Math.random(),
          role:     'agent',
          agent_id: data.agent_id,
          speaker:  data.agent_name,
          emoji:    data.agent_emoji,
          content:  data.content,
          is_pass:  false,
        }])

      } else if (data.type === 'agent_pass') {
        setThinking(null)
        setMessages(prev => [...prev, {
          id:       Date.now() + Math.random(),
          role:     'agent',
          agent_id: data.agent_id,
          speaker:  data.agent_name,
          emoji:    data.agent_emoji,
          content:  '',
          is_pass:  true,
        }])

      } else if (data.type === 'done') {
        setThinking(null)
        setLoading(false)

      } else if (data.type === 'error') {
        toast.error(data.content)
        setThinking(null)
        setLoading(false)
      }
    }

    ws.onerror = () => toast.error('WebSocket error')
  }, [groupId])

  useEffect(() => { connectWs() }, [connectWs])
  useEffect(() => { return () => wsRef.current?.close() }, [])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, thinking])

  function sendMessage() {
    if (!input.trim() || loading || !wsRef.current) return
    const content = input.trim()
    setInput('')
    setLoading(true)
    setMessages(prev => [...prev, {
      id: Date.now(), role: 'user', speaker: 'You', emoji: '👤', content, is_pass: false,
    }])
    wsRef.current.send(JSON.stringify({ type: 'message', content }))
  }

  async function handleDelete() {
    try {
      await groupApi.delete(groupId)
      onGroupsChange?.()
      navigate('/')
      toast.success('Group chat deleted')
    } catch {
      toast.error('Failed to delete group chat')
    }
  }

  const palette = usePalette(group?.members)

  if (!group) {
    return <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-500">Loading…</div>
  }

  return (
    <div className="flex h-full">
      {/* Left panel — group info */}
      <div className="w-52 shrink-0 flex flex-col bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800">
        <div className="p-3 border-b border-gray-200 dark:border-gray-800">
          <p className="text-xs text-gray-500 dark:text-gray-500 mb-1">Group Chat</p>
          <p className="font-semibold text-sm text-gray-900 dark:text-white truncate" title={group.title}>{group.title}</p>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <p className="text-xs text-gray-500 dark:text-gray-500 mb-2 uppercase tracking-wide">Members</p>
          <div className="space-y-2">
            {group.members.map((m, i) => {
              const pal = AGENT_PALETTES[i % AGENT_PALETTES.length]
              return (
                <div key={m.agent_id} className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${pal.dot}`} />
                  <span className="text-lg">{m.avatar_emoji}</span>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-gray-900 dark:text-white truncate">{m.name}</p>
                    <p className="text-[10px] text-gray-500 dark:text-gray-500 truncate">{m.product_line}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
        <div className="p-3 border-t border-gray-200 dark:border-gray-800">
          {confirmDelete ? (
            <div className="space-y-1.5">
              <p className="text-[11px] text-gray-500 dark:text-gray-400 text-center">Delete this group?</p>
              <div className="flex gap-1.5">
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="flex-1 px-2 py-1.5 text-xs text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  className="flex-1 px-2 py-1.5 text-xs text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors"
                >
                  Delete
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="w-full flex items-center gap-2 px-2 py-1.5 text-xs text-red-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
            >
              <Trash2 className="w-3 h-3" /> Delete Group
            </button>
          )}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center text-gray-600">
              <p className="text-4xl mb-3">💬</p>
              <p className="text-sm">Ask a question to start the group discussion.</p>
              <p className="text-xs mt-1">Agents will respond from their respective domains.</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <MessageBubble key={msg.id || i} msg={msg} palette={palette} />
          ))}
          {thinking && (
            <ThinkingBubble
              emoji={thinking.agent_emoji}
              name={thinking.agent_name}
              palette={palette[thinking.agent_id]}
            />
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
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
              disabled={loading}
              placeholder={loading ? 'Agents are discussing…' : 'Ask a question to the group…'}
              className="flex-1 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-900 dark:text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 disabled:opacity-50"
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || loading}
              className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
