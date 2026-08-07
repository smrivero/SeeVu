import { useState, useEffect, useRef } from 'react'
import { sendChatMessage, fetchActivePrompt, fetchChatModels } from './api.js'
import { t } from './i18n.js'
import ConfirmModal from './ConfirmModal.jsx'
import PromptViewModal from './PromptViewModal.jsx'

export default function ChatScreen({ lang, isActive, config, activePromptData, onActivePromptChange, onNavigate }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [model, setModel] = useState(config.chat_model || 'gpt-4o-mini')
  const [models, setModels] = useState([])
  const [pendingModel, setPendingModel] = useState(null)
  const [showPromptModal, setShowPromptModal] = useState(false)
  const scrollRef = useRef(null)
  const messagesRef = useRef(messages)
  messagesRef.current = messages

  useEffect(() => {
    fetchChatModels().then(d => setModels(d.models || []))
  }, [])

  // Adopt the Settings default only when Settings itself changes, and only
  // if no conversation is in flight at that moment. Deliberately NOT keyed
  // on messages.length -- our own resets (new conversation, confirmed model
  // change) also drop messages to 0, and re-running this then would stomp
  // the model the user just picked. The model is frozen for an in-progress
  // session anyway (server enforces this independently).
  useEffect(() => {
    if (messagesRef.current.length === 0) setModel(config.chat_model || 'gpt-4o-mini')
  }, [config.chat_model])

  useEffect(() => {
    if (!isActive) return
    fetchActivePrompt().then(onActivePromptChange)
  }, [isActive, onActivePromptChange])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, loading])

  const hasPrompt = !!(activePromptData?.content || '').trim()

  async function handleSend() {
    const text = input.trim()
    if (!text || loading || !hasPrompt) return

    const nextMessages = [...messages, { role: 'user', content: text }]
    setMessages(nextMessages)
    setInput('')
    setError(null)
    setLoading(true)
    try {
      const d = await sendChatMessage(nextMessages, sessionId, model)
      if (d.ok) {
        setMessages(prev => [...prev, { role: 'assistant', content: d.message }])
        if (d.session_id) setSessionId(d.session_id)
        if (d.model) setModel(d.model)
      } else if (d.error === 'no_prompt') {
        setError(t(lang, 'chatNoPrompt'))
      } else {
        setError(t(lang, 'chatError'))
      }
    } catch {
      setError(t(lang, 'chatError'))
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleNewConversation() {
    setMessages([])
    setError(null)
    setSessionId(null)
  }

  function handleModelSelect(value) {
    if (value === model) return
    if (messages.length === 0) {
      setModel(value)
    } else {
      setPendingModel(value)
    }
  }

  function confirmModelChange() {
    setModel(pendingModel)
    setPendingModel(null)
    setMessages([])
    setError(null)
    setSessionId(null)
  }

  function handleReloadPrompt() {
    fetchActivePrompt().then(onActivePromptChange)
  }

  return (
    <>
      <div className="pg-header">
        <div>
          <h1>{t(lang, 'pageChat')}</h1>
          <p>{t(lang, 'pageChatSub')}</p>
        </div>
        <div className="pg-header-r">
          <select
            className="chat-model-select"
            value={model}
            onChange={e => handleModelSelect(e.target.value)}
          >
            {models.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <button className="btn btn-secondary btn-sm" onClick={handleNewConversation}>
            {t(lang, 'chatNewConversation')}
          </button>
        </div>
      </div>

      <div className="chat-content">
        <div className="chat-meta-row">
          <span className="chat-meta-badge">{t(lang, 'chatModelLabel')}: {model}</span>
          <span className="chat-meta-badge">{t(lang, 'chatPromptFromSettings')}</span>
          <button className="chat-meta-link" onClick={() => setShowPromptModal(true)}>
            {t(lang, 'chatViewPrompt')}
          </button>
          <button className="chat-meta-link" onClick={handleReloadPrompt}>
            {t(lang, 'chatReloadConfig')}
          </button>
        </div>

        {!hasPrompt && (
          <div className="chat-banner">
            <span>{t(lang, 'chatNoPrompt')}</span>
            <button className="btn btn-primary btn-sm" onClick={() => onNavigate('settings')}>
              {t(lang, 'chatGoToSettings')}
            </button>
          </div>
        )}

        <div className="chat-turns" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="live-empty">{t(lang, 'chatEmpty')}</div>
          ) : messages.map((m, i) => (
            <div key={i} className={`live-turn ${m.role === 'user' ? 'user' : 'assistant'}`}>
              <span className="live-role">{m.role === 'user' ? t(lang, 'user') : t(lang, 'assistant')}</span>
              <div className="live-bubble">{m.content}</div>
            </div>
          ))}
          {loading && (
            <div className="live-turn assistant">
              <span className="live-role">{t(lang, 'assistant')}</span>
              <div className="live-bubble live-pending">{t(lang, 'chatThinking')}</div>
            </div>
          )}
        </div>

        {error && <div className="chat-error">{error}</div>}

        <div className="chat-input-row">
          <textarea
            className="chat-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t(lang, 'chatPlaceholder')}
            disabled={loading || !hasPrompt}
            rows={2}
          />
          <button
            className="btn btn-primary"
            onClick={handleSend}
            disabled={loading || !hasPrompt || !input.trim()}
          >
            {t(lang, 'chatSend')}
          </button>
        </div>
      </div>

      {pendingModel && (
        <ConfirmModal
          message={t(lang, 'chatModelChangeConfirm')}
          confirmLabel={t(lang, 'modalContinue')}
          cancelLabel={t(lang, 'modalCancel')}
          danger={false}
          onConfirm={confirmModelChange}
          onCancel={() => setPendingModel(null)}
        />
      )}

      {showPromptModal && (
        <PromptViewModal
          lang={lang}
          content={activePromptData?.content}
          updatedAt={activePromptData?.updated_at}
          onClose={() => setShowPromptModal(false)}
          onNavigate={onNavigate}
        />
      )}
    </>
  )
}
