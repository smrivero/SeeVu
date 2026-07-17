import { useVoiceCall } from './hooks/useVoiceCall.js'
import { t } from './i18n.js'

export default function VoiceCallPanel({ lang, onBeforeConnect }) {
  const { status, connect, disconnect, audioRef, isConnected, isConnecting } = useVoiceCall(onBeforeConnect)

  const statusLabel = {
    disconnected: t(lang, 'vcDisconnected'),
    connecting: t(lang, 'vcConnecting'),
    connected: t(lang, 'vcConnected'),
    error: t(lang, 'vcError'),
  }[status] || status

  return (
    <div className="voice-call-panel">
      <audio ref={audioRef} autoPlay playsInline />

      <div className="voice-call-status">
        <div className={`voice-call-dot${isConnected ? ' on' : ''}`} />
        <span>{statusLabel}</span>
      </div>

      <div className="voice-call-actions">
        <button
          className="btn btn-primary btn-sm"
          onClick={connect}
          disabled={isConnected || isConnecting}
        >
          {t(lang, 'btnConnect')}
        </button>
        <button
          className="btn btn-secondary btn-sm"
          onClick={disconnect}
          disabled={!isConnected && !isConnecting}
        >
          {t(lang, 'btnDisconnect')}
        </button>
      </div>

      <p className="voice-call-hint">{t(lang, 'vcHint')}</p>
    </div>
  )
}
