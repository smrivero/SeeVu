import { useState } from 'react'
import { savePromptApi } from './api.js'
import { t } from './i18n.js'

export default function SavePromptModal({ lang, content, onClose, onSaved }) {
  const [name, setName]     = useState('')
  const [promptLang, setPromptLang] = useState('en')
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    if (!name.trim() || !content.trim()) return
    setSaving(true)
    try {
      const d = await savePromptApi(name.trim(), promptLang, content.trim())
      if (d.ok) onSaved(d.prompts)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay open" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal">
        <h3>{t(lang, 'modalTitle')}</h3>

        <div className="field">
          <label htmlFor="modal-name">{t(lang, 'modalName')}</label>
          <input
            id="modal-name"
            type="text"
            placeholder="e.g. Revo Construction"
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSave()}
            autoFocus
          />
        </div>

        <div className="field">
          <label htmlFor="modal-lang">{t(lang, 'modalLang')}</label>
          <select id="modal-lang" value={promptLang} onChange={e => setPromptLang(e.target.value)}>
            <option value="en">English</option>
            <option value="es">Español</option>
          </select>
        </div>

        <div className="modal-actions">
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            {t(lang, 'modalCancel')}
          </button>
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            {t(lang, 'modalSave')}
          </button>
        </div>
      </div>
    </div>
  )
}
