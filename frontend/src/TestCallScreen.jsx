import { useState, useEffect, useRef, useCallback } from 'react'
import { saveConfig, applyPromptApi, fetchLiveSession, fetchActivePrompt } from './api.js'
import { resolveActivePromptSelection } from './utils.js'
import VoiceCallPanel from './VoiceCallPanel.jsx'
import { t } from './i18n.js'

function syncPromptState(prompts, activeData, setPromptText, setSelectedPromptId) {
  const { content, promptId } = resolveActivePromptSelection(prompts, activeData)
  setPromptText(content)
  setSelectedPromptId(promptId)
  return { content, promptId }
}

export default function TestCallScreen({
  lang,
  isActive,
  providers,
  config,
  prompts,
  activePromptData,
  onConfigChange,
  onActivePromptChange,
  onOpenModal,
}) {
  const [provider, setProvider] = useState(config.provider)
  const [voice, setVoice] = useState(config.voice)
  const [promptText, setPromptText] = useState(activePromptData.content || '')
  const [selectedPromptId, setSelectedPromptId] = useState(activePromptData.promptId || '')
  const [configStatus, setConfigStatus] = useState(null)
  const [promptStatus, setPromptStatus] = useState(null)

  useEffect(() => { setProvider(config.provider); setVoice(config.voice) }, [config])

  useEffect(() => {
    syncPromptState(prompts, activePromptData, setPromptText, setSelectedPromptId)
  }, [activePromptData, prompts])

  useEffect(() => {
    if (!isActive) return
    fetchActivePrompt().then((data) => {
      const synced = syncPromptState(prompts, data, setPromptText, setSelectedPromptId)
      onActivePromptChange(synced)
    })
  }, [isActive, onActivePromptChange, prompts])

  const voices = providers[provider]?.voices || []

  function showSfb(setter, ok, msg) {
    setter({ ok, msg })
    setTimeout(() => setter(null), 2500)
  }

  async function applyConfig() {
    const d = await saveConfig(provider, voice)
    if (d.ok) onConfigChange({ provider, voice })
    showSfb(setConfigStatus, d.ok, d.ok ? t(lang, 'applied') : 'Error')
  }

  async function handleApplyPrompt() {
    if (!promptText.trim()) return
    const d = await applyPromptApi(promptText.trim(), selectedPromptId || null)
    if (d.ok) {
      onActivePromptChange({ content: promptText.trim(), promptId: selectedPromptId || d.prompt_id || '' })
    }
    showSfb(setPromptStatus, d.ok, d.ok ? t(lang, 'applied') : 'Error')
  }

  const ensurePromptApplied = useCallback(async () => {
    const content = promptText.trim()
    if (!content) {
      showSfb(setPromptStatus, false, t(lang, 'promptRequired'))
      return false
    }
    const unchanged =
      content === (activePromptData.content || '').trim() &&
      (selectedPromptId || '') === (activePromptData.promptId || '')
    if (unchanged) return true

    const d = await applyPromptApi(content, selectedPromptId || null)
    if (d.ok) {
      onActivePromptChange({ content, promptId: selectedPromptId || d.prompt_id || '' })
      return true
    }
    showSfb(setPromptStatus, false, 'Error')
    return false
  }, [activePromptData, lang, onActivePromptChange, promptText, selectedPromptId])

  return (
    <>
      <div className="pg-header">
        <div>
          <h1>{t(lang, 'pageTest')}</h1>
          <p>{t(lang, 'pageTestSub')}</p>
        </div>
      </div>

      <div className="testcall-body">
        <div className="tc-left">
          <div className="tc-section-hd">{t(lang, 'tcConn')}</div>
          <div className="tc-section-body">
            <div className="field">
              <label>{t(lang, 'lblProvider')}</label>
              <select value={provider} onChange={(e) => { setProvider(e.target.value); setVoice('') }}>
                {Object.entries(providers).map(([id, p]) => (
                  <option key={id} value={id}>{p.label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>{t(lang, 'lblVoice')}</label>
              <select value={voice} onChange={(e) => setVoice(e.target.value)}>
                {voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
              </select>
            </div>
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              <button className="btn btn-primary btn-sm" onClick={applyConfig}>
                {t(lang, 'btnApply')}
              </button>
              {configStatus && (
                <span className={`sfb ${configStatus.ok ? 'ok' : 'err'}`}>{configStatus.msg}</span>
              )}
            </div>
          </div>

          <div className="prompt-pane">
            <div className="tc-section-hd">{t(lang, 'tcPrompt')}</div>
            <div className="prompt-pane-body">
              <div className="field">
                <select
                  value={selectedPromptId}
                  onChange={(e) => {
                    const p = prompts.find((x) => x.id === e.target.value)
                    if (p) {
                      setSelectedPromptId(p.id)
                      setPromptText(p.content)
                    } else {
                      setSelectedPromptId('')
                    }
                  }}
                >
                  <option value="">{t(lang, 'promptPH')}</option>
                  {prompts.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} [{(p.lang || 'en').toUpperCase()}]
                    </option>
                  ))}
                </select>
              </div>
              <textarea
                className="prompt-ta"
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                spellCheck={false}
              />
              <div className="prompt-actions">
                <button
                  className="btn btn-secondary btn-sm"
                  style={{ flex: 1 }}
                  onClick={() => promptText.trim() && onOpenModal(promptText.trim())}
                >
                  {t(lang, 'btnSaveAs')}
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  style={{ flex: 1 }}
                  onClick={handleApplyPrompt}
                >
                  {t(lang, 'btnApplyPrompt')}
                </button>
              </div>
              {promptStatus && (
                <span className={`sfb ${promptStatus.ok ? 'ok' : 'err'}`}>{promptStatus.msg}</span>
              )}
            </div>
          </div>
        </div>

        <div className="tc-right">
          <div className="tc-voice-wrap">
            <VoiceCallPanel lang={lang} onBeforeConnect={ensurePromptApplied} />
          </div>
          <LivePanel lang={lang} />
        </div>
      </div>
    </>
  )
}

function LivePanel({ lang }) {
  const [session, setSession] = useState({ active: false, turns: [] })
  const [wasActive, setWasActive] = useState(false)
  const turnsRef = useRef(null)

  useEffect(() => {
    let isMounted = true
    async function poll() {
      try {
        const data = await fetchLiveSession()
        if (!isMounted) return
        setSession(data)
        if (wasActive && !data.active) {
          setTimeout(() => window.dispatchEvent(new Event('refresh-conversations')), 2500)
        }
        setWasActive(data.active)
      } catch { /* ignore */ }
    }
    poll()
    const id = setInterval(poll, 3000)
    return () => { isMounted = false; clearInterval(id) }
  }, [wasActive])

  useEffect(() => {
    if (turnsRef.current && session.turns?.length) {
      turnsRef.current.scrollTop = turnsRef.current.scrollHeight
    }
  }, [session.turns])

  function getAgentState() {
    if (!session.active) return { cls: 'idle', label: t(lang, 'stateIdle') }
    const turns = session.turns || []
    const last = turns[turns.length - 1]
    if (last?.role === 'assistant' && (last.content || '').endsWith('…'))
      return { cls: 'speaking', label: t(lang, 'stateSpeaking') }
    return { cls: 'listening', label: t(lang, 'stateListening') }
  }

  const state = getAgentState()
  const cfg = session.config || {}
  const turns = session.turns || []

  return (
    <div className="live-panel">
      <div className="live-hd">
        <div className={`live-status-dot${session.active ? ' on' : ''}`}></div>
        <h3>{t(lang, 'liveTitle')}</h3>
      </div>

      <div className="agent-state-bar">
        <div className={`astate-dot ${state.cls}`}></div>
        <span className="astate-label">{state.label}</span>
      </div>

      {session.active && (
        <div className="live-info">
          <strong>{t(lang, 'liveActive')}</strong> · {cfg.provider || ''} / {cfg.voice || ''}
          <br />{(session.started_at || '').slice(0, 19).replace('T', ' ')}
        </div>
      )}

      <div className="live-turns" ref={turnsRef}>
        {turns.length === 0 ? (
          <div className="live-empty">
            {session.active ? `${t(lang, 'stateListening')}…` : t(lang, 'liveEmpty')}
          </div>
        ) : turns.map((turn, i) => (
          <div key={i} className={`live-turn ${turn.role === 'user' ? 'user' : 'assistant'}`}>
            <span className="live-role">
              {turn.role === 'user' ? t(lang, 'user') : t(lang, 'assistant')}
            </span>
            <div className={`live-bubble${(turn.content || '').endsWith('…') ? ' live-pending' : ''}`}>
              {turn.content || ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
