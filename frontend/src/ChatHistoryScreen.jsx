import { useState, useEffect, Fragment } from 'react'
import { fetchChatConversations, deleteChatConversationApi, analyzeChatApi } from './api.js'
import { t } from './i18n.js'
import { relTime } from './utils.js'
import ConfirmModal from './ConfirmModal.jsx'

export default function ChatHistoryScreen({ lang, isActive }) {
  const [convs, setConvs] = useState([])
  const [online, setOnline] = useState(true)
  const [openRows, setOpenRows] = useState(new Set())
  const [lastUpd, setLastUpd] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [confirmSid, setConfirmSid] = useState(null)

  async function load() {
    try {
      const data = await fetchChatConversations()
      setOnline(true)
      setConvs(data)
      setLastUpd(new Date())
    } catch {
      setOnline(false)
    }
  }

  useEffect(() => {
    if (!isActive) return
    load()
  }, [isActive])

  function toggle(sid) {
    setOpenRows(prev => {
      const next = new Set(prev)
      if (next.has(sid)) next.delete(sid); else next.add(sid)
      return next
    })
  }

  async function deleteConv(sid) {
    setDeleting(sid)
    await deleteChatConversationApi(sid)
    setConvs(prev => prev.filter(c => c.session_id !== sid))
    setOpenRows(prev => { const n = new Set(prev); n.delete(sid); return n })
    setDeleting(null)
    setConfirmSid(null)
  }

  return (
    <>
      <div className="pg-header">
        <div>
          <h1>{t(lang, 'pageChatHistory')}</h1>
          <p>{t(lang, 'pageChatHistorySub')}</p>
        </div>
        <div className="pg-header-r">
          {lastUpd && (
            <span className="last-upd">
              {t(lang, 'lastUpd')} {lastUpd.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}
            </span>
          )}
          <button className="btn btn-secondary btn-sm" onClick={load}>
            <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="2">
              <path d="M1 8A7 7 0 1 0 8 1M1 1v4h4" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            {t(lang, 'btnRefresh')}
          </button>
          <span className={`badge ${online ? 'badge-green' : 'badge-red'}`}>
            <span className="badge-dot"></span>
            {t(lang, online ? 'badgeOnline' : 'badgeOffline')}
          </span>
        </div>
      </div>

      <div className="table-area">
        <div className="table-toolbar">
          <div className="table-title">
            <div className="live-dot-sm"></div>
            {t(lang, 'chatHistoryTitle')}
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t(lang,'colDate')}</th>
                <th>{t(lang,'chatColMessages')}</th>
                <th>{t(lang,'chatColPreview')}</th>
                <th>User</th>
                <th style={{width:'36px'}}></th>
              </tr>
            </thead>
            <tbody>
              {convs.length === 0 ? (
                <tr>
                  <td colSpan="5" style={{padding:0}}>
                    <div className="empty-state">
                      <div className="empty-state-icon">
                        <svg fill="none" viewBox="0 0 22 22" stroke="currentColor" strokeWidth="1.5">
                          <path d="M2 4h18v11H8.5L4 19.5V15H2z" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      </div>
                      <h3>{t(lang,'noChatHistory')}</h3>
                      <p>{t(lang,'noChatHistorySub')}</p>
                    </div>
                  </td>
                </tr>
              ) : convs.map(c => (
                <ChatRow
                  key={c.session_id}
                  conv={c}
                  lang={lang}
                  open={openRows.has(c.session_id)}
                  deleting={deleting === c.session_id}
                  onToggle={() => toggle(c.session_id)}
                  onDelete={() => setConfirmSid(c.session_id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {confirmSid && (
        <ConfirmModal
          message={t(lang, 'chatDeleteConfirm')}
          onConfirm={() => deleteConv(confirmSid)}
          onCancel={() => setConfirmSid(null)}
        />
      )}
    </>
  )
}

function ChatRow({ conv: c, lang, open, deleting, onToggle, onDelete }) {
  const sid = c.session_id || ''
  const iso = c.started_at || ''
  const msgs = c.messages || []
  const createdBy = c.created_by_email || null
  const firstUserMsg = msgs.find(m => m.role === 'user')?.content || ''
  const preview = firstUserMsg.length > 80 ? firstUserMsg.slice(0, 80) + '…' : firstUserMsg
  const [analysis, setAnalysis] = useState(c.analysis || null)

  const userTurns = msgs.filter(m => m.role === 'user').length
  const assistantTurns = msgs.filter(m => m.role === 'assistant').length
  const wordCount = msgs.reduce((sum, m) => sum + (m.content || '').trim().split(/\s+/).filter(Boolean).length, 0)
  const durationSec = (c.started_at && c.updated_at)
    ? Math.max(0, Math.round((new Date(c.updated_at) - new Date(c.started_at)) / 1000))
    : null
  const durationLabel = durationSec == null ? '—'
    : durationSec < 60 ? `${durationSec}s`
    : `${Math.floor(durationSec / 60)}m ${durationSec % 60}s`

  return (
    <Fragment>
      <tr className="conv-row" onClick={onToggle}>
        <td className="td-2">
          <svg
            style={{width:'10px',height:'10px',marginRight:'5px',verticalAlign:'middle',transition:'transform .15s',transform: open ? 'rotate(90deg)' : 'rotate(0deg)',color:'var(--text-3)'}}
            fill="none" viewBox="0 0 10 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          >
            <path d="M3 2l4 3-4 3"/>
          </svg>
          <span title={iso.slice(0,19).replace('T',' ')}>{relTime(iso)}</span>
        </td>
        <td className="td-mono">{msgs.length}</td>
        <td style={{color:'var(--text-2)'}}>{preview || '—'}</td>
        <td className="td-user">
          {createdBy
            ? <span className="user-badge" title={createdBy}>{createdBy.split('@')[0]}</span>
            : <span style={{color:'var(--text-3)'}}>—</span>}
        </td>
        <td>
          <button
            className="del-btn"
            disabled={deleting}
            onClick={e => { e.stopPropagation(); onDelete() }}
            title="Delete"
          >
            {deleting ? '…' : '×'}
          </button>
        </td>
      </tr>

      {open && (
        <tr className="detail">
          <td colSpan="5">
            <div className="det-body">
              <div className="det-tokens">
                <div className="tok-cards">
                  <div className="tok-card">
                    <span className="tok-card-label">{t(lang,'chatColMessages')}</span>
                    <span className="tok-card-val">{msgs.length}</span>
                  </div>
                  <div className="tok-card">
                    <span className="tok-card-label">{t(lang,'user')}</span>
                    <span className="tok-card-val">{userTurns}</span>
                  </div>
                  <div className="tok-card">
                    <span className="tok-card-label">{t(lang,'assistant')}</span>
                    <span className="tok-card-val">{assistantTurns}</span>
                  </div>
                  <div className="tok-card">
                    <span className="tok-card-label">{t(lang,'chatWords')}</span>
                    <span className="tok-card-val">{wordCount}</span>
                  </div>
                  <div className="tok-card">
                    <span className="tok-card-label">{t(lang,'chatDuration')}</span>
                    <span className="tok-card-val">{durationLabel}</span>
                  </div>
                </div>
                <ChatAnalysis sessionId={sid} analysis={analysis} lang={lang} onAnalyzed={setAnalysis} />
              </div>

              <div className="det-transcript" style={{flex:1}}>
                <div className="tx-title">{t(lang,'transcript')}</div>
                {msgs.length === 0 ? (
                  <div style={{color:'var(--text-3)',fontSize:'12px',padding:'24px 0',textAlign:'center'}}>
                    {t(lang,'noTranscript')}
                  </div>
                ) : msgs.map((m, i) => (
                  <div key={i} className={`turn ${m.role === 'user' ? 'user' : 'assistant'}`}>
                    <span className="turn-label">
                      {m.role === 'user' ? t(lang,'user') : t(lang,'assistant')}
                    </span>
                    <div className="turn-bubble">
                      {(m.content || '').replace(/</g,'&lt;')}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  )
}

function ChatAnalysis({ sessionId, analysis, lang, onAnalyzed }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(false)

  if (analysis) {
    const s = analysis.sentiment || 'neutral'
    const sKey = { positive:'sSentPos', neutral:'sSentNeu', negative:'sSentNeg' }[s] || 'sSentNeu'
    const hl = analysis.highlights || []
    return (
      <div className="analysis-box">
        <div className="analysis-title">{t(lang,'analysisTitle')}</div>
        <div style={{marginBottom:'7px'}}>
          <span className={`s-badge s-${s.slice(0,3)}`}>{t(lang,sKey)}</span>
          <span style={{fontSize:'11px',color:'var(--text-2)'}}>
            {analysis.productive ? t(lang,'sProductive') : t(lang,'sNotProductive')}
          </span>
        </div>
        <p className="analysis-summary">{analysis.summary || ''}</p>
        {hl.length > 0 && (
          <ul className="analysis-hl">
            {hl.map((h, i) => <li key={i}>{h}</li>)}
          </ul>
        )}
      </div>
    )
  }

  return (
    <>
      <button
        className="analysis-trigger"
        disabled={pending}
        onClick={async () => {
          setPending(true)
          setError(false)
          try {
            const result = await analyzeChatApi(sessionId)
            onAnalyzed(result)
          } catch {
            setError(true)
          }
          setPending(false)
        }}
      >
        <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.8" style={{width:'14px',height:'14px',flexShrink:0}}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 2L6.5 7H11L7 14M3 4l1 1M13 4l-1 1M3 12l1-1M13 12l-1-1"/>
        </svg>
        {pending ? t(lang,'analyzing') : t(lang,'analyzeChatBtn')}
      </button>
      {error && <div className="chat-error" style={{marginTop:'6px'}}>{t(lang,'analyzeError')}</div>}
    </>
  )
}
