import { useState, useEffect } from 'react'
import { saveConfig, applyPromptApi } from './api.js'
import { t } from './i18n.js'

export default function SettingsScreen({ lang, providers, config, prompts, onPromptsChange, onConfigChange, onOpenModal }) {
  const [provider, setProvider]   = useState(config.provider)
  const [voice, setVoice]         = useState(config.voice)
  const [clientUrl, setClientUrl] = useState(() => localStorage.getItem('clientUrl') || 'http://localhost:5173')
  const [promptText, setPromptText] = useState('')
  const [configStatus, setConfigStatus] = useState(null)
  const [promptStatus, setPromptStatus] = useState(null)

  useEffect(() => { setProvider(config.provider); setVoice(config.voice) }, [config])

  const voices = providers[provider]?.voices || []

  function showSfb(setter, ok, msg) {
    setter({ ok, msg })
    setTimeout(() => setter(null), 2500)
  }

  async function applyProviderConfig() {
    const d = await saveConfig(provider, voice)
    if (d.ok) onConfigChange({ provider, voice })
    showSfb(setConfigStatus, d.ok, d.ok ? t(lang,'applied') : 'Error')
  }

  function applyClientUrl() {
    localStorage.setItem('clientUrl', clientUrl)
    window.dispatchEvent(new CustomEvent('client-url-change', { detail: clientUrl }))
    showSfb(setConfigStatus, true, t(lang,'applied'))
  }

  async function handleApplyPrompt() {
    if (!promptText.trim()) return
    const d = await applyPromptApi(promptText.trim())
    showSfb(setPromptStatus, d.ok, d.ok ? t(lang,'applied') : 'Error')
  }

  const selectedPrompt = prompts.find(p => p.content === promptText)

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

          {/* Client URL */}
          <div className="sc">
            <div className="sc-hd">{t(lang,'settingsClient')}</div>
            <div className="sc-body">
              <div className="field">
                <label>{t(lang,'lblUrl')}</label>
                <input type="text" value={clientUrl} onChange={e => setClientUrl(e.target.value)} />
              </div>
              <button className="btn btn-secondary btn-sm" onClick={applyClientUrl}>
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
                  value={selectedPrompt?.id || ''}
                  onChange={e => {
                    const p = prompts.find(x => x.id === e.target.value)
                    if (p) setPromptText(p.content)
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
