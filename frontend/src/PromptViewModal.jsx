import { useState } from 'react'
import { t } from './i18n.js'

function copyText(text) {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text)
  }
  // Fallback for browsers/contexts without the async Clipboard API.
  return new Promise((resolve, reject) => {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    try {
      document.execCommand('copy') ? resolve() : reject(new Error('execCommand failed'))
    } catch (err) {
      reject(err)
    } finally {
      document.body.removeChild(ta)
    }
  })
}

export default function PromptViewModal({ lang, content, updatedAt, onClose, onNavigate }) {
  const [copied, setCopied] = useState(false)
  const [copyFailed, setCopyFailed] = useState(false)
  const hasContent = !!(content || '').trim()

  function handleCopy() {
    setCopyFailed(false)
    copyText(content || '')
      .then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      })
      .catch(() => setCopyFailed(true))
  }

  return (
    <div className="modal-overlay open" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal modal-lg">
        <h3>{t(lang, 'promptModalTitle')}</h3>

        {hasContent ? (
          <>
            <div className="prompt-modal-body">
              <pre>{content}</pre>
            </div>
            {updatedAt && (
              <div className="prompt-modal-meta">
                {t(lang, 'promptModalLastUpdated')}: {new Date(updatedAt).toLocaleString()}
              </div>
            )}
          </>
        ) : (
          <div className="chat-banner">
            <span>{t(lang, 'promptModalEmpty')}</span>
            <button className="btn btn-primary btn-sm" onClick={() => { onClose(); onNavigate('settings') }}>
              {t(lang, 'chatGoToSettings')}
            </button>
          </div>
        )}

        <div className="modal-actions">
          {hasContent && (
            <button className="btn btn-secondary btn-sm" onClick={handleCopy}>
              {copied ? t(lang,'promptModalCopied') : copyFailed ? t(lang,'promptModalCopyFailed') : t(lang,'promptModalCopy')}
            </button>
          )}
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            {t(lang, 'promptModalClose')}
          </button>
        </div>
      </div>
    </div>
  )
}
