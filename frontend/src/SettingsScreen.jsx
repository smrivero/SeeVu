import { useState, useEffect } from 'react'
import { saveConfig, applyPromptApi, fetchActivePrompt, fetchChatModels } from './api.js'
import { BOT_WS_URL_KEY, getBotWsUrl } from './hooks/useVoiceCall.js'
import { resolveActivePromptSelection } from './utils.js'
import { t } from './i18n.js'

export default function SettingsScreen({
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
  const [botWsUrl, setBotWsUrl] = useState(getBotWsUrl)
  const [promptText, setPromptText] = useState(activePromptData.content || '')
  const [selectedPromptId, setSelectedPromptId] = useState(activePromptData.promptId || '')
  const [configStatus, setConfigStatus] = useState(null)
  const [promptStatus, setPromptStatus] = useState(null)
  const [chatModel, setChatModel] = useState(config.chat_model || 'gpt-4o-mini')
  const [chatModels, setChatModels] = useState([])
  const [chatModelStatus, setChatModelStatus] = useState(null)

  useEffect(() => { setProvider(config.provider); setVoice(config.voice); setChatModel(config.chat_model || 'gpt-4o-mini') }, [config])

  useEffect(() => {
    fetchChatModels().then(d => setChatModels(d.models || []))
  }, [])

  useEffect(() => {
    const { content, promptId } = resolveActivePromptSelection(prompts, activePromptData)
    setPromptText(content)
    setSelectedPromptId(promptId)
  }, [activePromptData, prompts])

  useEffect(() => {
    if (!isActive) return
    fetchActivePrompt().then((data) => {
      const synced = resolveActivePromptSelection(prompts, data)
      setPromptText(synced.content)
      setSelectedPromptId(synced.promptId)
      onActivePromptChange(synced)
    })
  }, [isActive, onActivePromptChange, prompts])

  const voices = providers[provider]?.voices || []

  function showSfb(setter, ok, msg) {
    setter({ ok, msg })
    setTimeout(() => setter(null), 2500)
  }

  async function applyProviderConfig() {
    const d = await saveConfig(provider, voice)
    if (d.ok) onConfigChange({ ...config, provider, voice })
    showSfb(setConfigStatus, d.ok, d.ok ? t(lang,'applied') : 'Error')
  }

  async function applyChatModel() {
    const d = await saveConfig(config.provider, config.voice, config.log_level, chatModel)
    if (d.ok) onConfigChange({ ...config, chat_model: chatModel })
    showSfb(setChatModelStatus, d.ok, d.ok ? t(lang,'applied') : 'Error')
  }

  function applyBotWsUrl() {
    localStorage.setItem(BOT_WS_URL_KEY, botWsUrl.trim())
    showSfb(setConfigStatus, true, t(lang,'applied'))
  }

  async function handleApplyPrompt() {
    if (!promptText.trim()) return
    const d = await applyPromptApi(promptText.trim(), selectedPromptId || null)
    if (d.ok) {
      onActivePromptChange({ content: promptText.trim(), promptId: selectedPromptId || d.prompt_id || '' })
    }
    showSfb(setPromptStatus, d.ok, d.ok ? t(lang,'applied') : 'Error')
  }

  return (
    <>
      <div className="pg-header">
        <div>
          <h1>{t(lang,'pageSettings')}</h1>
          <p>{t(lang,'pageSettingsSub')}</p>
        </div>
      </div>

      <div className="settings-body">
        <div className="settings-grid">

          {/* Provider & Voice */}
          <div className="sc">
            <div className="sc-hd">{t(lang,'settingsProvider')}</div>
            <div className="sc-body">
              <div className="settings-notice">
                {lang === 'es'
                  ? '📞 Esta configuración aplica a las llamadas reales vía Twilio. Para hacer una prueba rápida usá la pantalla Test Call.'
                  : '📞 This configuration applies to real phone calls via Twilio. Use the Test Call screen for quick tests.'}
              </div>
              <div className="field">
                <label>{t(lang,'lblProvider')}</label>
                <select value={provider} onChange={e => { setProvider(e.target.value); setVoice('') }}>
                  {Object.entries(providers).map(([id, p]) => (
                    <option key={id} value={id}>{p.label}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>{t(lang,'lblVoice')}</label>
                <select value={voice} onChange={e => setVoice(e.target.value)}>
                  {voices.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
                </select>
              </div>
              <div style={{display:'flex',alignItems:'center',gap:'8px'}}>
                <button className="btn btn-primary btn-sm" onClick={applyProviderConfig}>
                  {t(lang,'btnApply')}
                </button>
                {configStatus && (
                  <span className={`sfb ${configStatus.ok ? 'ok' : 'err'}`}>{configStatus.msg}</span>
                )}
              </div>
            </div>
          </div>


          {/* Chat model */}
          <div className="sc">
            <div className="sc-hd">{t(lang,'settingsChat')}</div>
            <div className="sc-body">
              <div className="settings-notice">
                {lang === 'es'
                  ? '💬 Este modelo es el que usa la pantalla Chat por defecto para conversaciones nuevas.'
                  : '💬 This model is what the Chat screen defaults to for new conversations.'}
              </div>
              <div className="field">
                <label>{t(lang,'lblChatModel')}</label>
                <select value={chatModel} onChange={e => setChatModel(e.target.value)}>
                  {chatModels.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div style={{display:'flex',alignItems:'center',gap:'8px'}}>
                <button className="btn btn-primary btn-sm" onClick={applyChatModel}>
                  {t(lang,'btnApply')}
                </button>
                {chatModelStatus && (
                  <span className={`sfb ${chatModelStatus.ok ? 'ok' : 'err'}`}>{chatModelStatus.msg}</span>
                )}
              </div>
            </div>
          </div>

          {/* Bot WebSocket URL */}
          <div className="sc">
            <div className="sc-hd">{t(lang,'settingsBot')}</div>
            <div className="sc-body">
              <div className="field">
                <label>{t(lang,'lblBotUrl')}</label>
                <input type="text" value={botWsUrl} onChange={e => setBotWsUrl(e.target.value)} />
              </div>
              <button className="btn btn-secondary btn-sm" onClick={applyBotWsUrl}>
                {t(lang,'btnApply')}
              </button>
            </div>
          </div>

          {/* Prompts */}
          <div className="sc sc-full">
            <div className="sc-hd">{t(lang,'settingsPrompts')}</div>
            <div className="sc-body">
              <div className="field">
                <label>{t(lang,'lblSavedPrompts')}</label>
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
                  <option value="">{t(lang,'promptPH')}</option>
                  {prompts.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.name} [{(p.lang || 'en').toUpperCase()}]
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>{t(lang,'lblPromptContent')}</label>
                <textarea
                  className="settings-ta"
                  value={promptText}
                  onChange={e => setPromptText(e.target.value)}
                  spellCheck={false}
                />
              </div>
              <div style={{display:'flex',gap:'8px',alignItems:'center',flexWrap:'wrap'}}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => promptText.trim() && onOpenModal(promptText.trim())}
                >
                  {t(lang,'btnSaveAs')}
                </button>
                <button className="btn btn-primary btn-sm" onClick={handleApplyPrompt}>
                  {t(lang,'btnApplyPrompt')}
                </button>
                {promptStatus && (
                  <span className={`sfb ${promptStatus.ok ? 'ok' : 'err'}`}>{promptStatus.msg}</span>
                )}
              </div>
            </div>
          </div>

        </div>
      </div>
    </>
  )
}
