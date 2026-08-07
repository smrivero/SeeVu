import { useState, useEffect, Fragment } from 'react'
import { fetchConversations, analyzeCallApi, deleteConversationApi } from './api.js'
import { t } from './i18n.js'
import { fmtDur, relTime } from './utils.js'
import ConfirmModal from './ConfirmModal.jsx'

export default function CallsScreen({ lang, onOnlineChange }) {
  const [convs, setConvs]       = useState([])
  const [online, setOnline]     = useState(true)
  const [openRows, setOpenRows] = useState(new Set())
  const [lastUpd, setLastUpd]   = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [confirmSid, setConfirmSid] = useState(null)

  function setOnlineState(val) {
    setOnline(val)
    onOnlineChange(val)
  }

  async function load(force = false) {
    try {
      const data = await fetchConversations()
      setOnlineState(true)
      if (force || data.length !== convs.length) setConvs(data)
      setLastUpd(new Date())
    } catch {
      setOnlineState(false)
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [])

  function toggle(sid) {
    setOpenRows(prev => {
      const next = new Set(prev)
      if (next.has(sid)) { next.delete(sid) } else { next.add(sid) }
      return next
    })
  }

  async function deleteConv(sid) {
    setDeleting(sid)
    await deleteConversationApi(sid)
    setConvs(prev => prev.filter(c => c.session_id !== sid))
    setOpenRows(prev => { const n = new Set(prev); n.delete(sid); return n })
    setDeleting(null)
    setConfirmSid(null)
  }

  function playAudio(sid, track) {
    setOpenRows(prev => { const n = new Set(prev); n.add(sid); return n })
    setTimeout(() => document.getElementById(`audio-${track}-${sid}`)?.play(), 50)
  }

  const totToks = convs.reduce((s, c) => s + (((c.usage || {}).llm || {}).total_tokens || 0), 0)
  const totTts  = convs.reduce((s, c) => s + ((c.usage || {}).tts_characters || 0), 0)
  const avgDur  = convs.length
    ? Math.round(convs.reduce((s, c) => s + (c.duration_seconds || 0), 0) / convs.length) : 0

  return (
    <>
      <div className="pg-header">
        <div>
          <h1>{t(lang, 'pageCalls')}</h1>
          <p>{t(lang, 'pageCallsSub')}</p>
        </div>
        <div className="pg-header-r">
          {lastUpd && (
            <span className="last-upd">
              {t(lang, 'lastUpd')} {lastUpd.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}
            </span>
          )}
          <button className="btn btn-secondary btn-sm" onClick={() => load(true)}>
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

      <div className="metrics-row">
        {[
          { label:'mcCalls',  val: convs.length,        sub:'mcCallsSub',  icon:<rect x="1.5" y="3.5" width="13" height="10" rx="1.5"/>, icon2:<path d="M1.5 6.5h13"/> },
          { label:'mcDur',    val: fmtDur(avgDur),      sub:'mcDurSub' },
          { label:'mcTokens', val: totToks.toLocaleString(), sub:'mcTokensSub' },
          { label:'mcTts',    val: totTts.toLocaleString(),  sub:'mcTtsSub' },
        ].map((m, i) => (
          <div className="mc" key={i}>
            <div className="mc-head">
              <span className="mc-label">{t(lang, m.label)}</span>
              <div className="mc-icon">
                {i === 0 && <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.8"><rect x="1.5" y="3.5" width="13" height="10" rx="1.5"/><path d="M1.5 6.5h13"/></svg>}
                {i === 1 && <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.8"><circle cx="8" cy="8" r="6.5"/><path d="M8 4.5V8l2.5 2.5" strokeLinecap="round"/></svg>}
                {i === 2 && <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.8"><path d="M3 4h10M3 8h10M3 12h6" strokeLinecap="round"/></svg>}
                {i === 3 && <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.8"><path d="M9 3 6 6H3v4h3l3 3V3zM12 5a4 4 0 0 1 0 6" strokeLinecap="round" strokeLinejoin="round"/></svg>}
              </div>
            </div>
            <div className="mc-val">{m.val}</div>
            <div className="mc-sub">{t(lang, m.sub)}</div>
          </div>
        ))}
      </div>

      <div className="table-area">
        <div className="table-toolbar">
          <div className="table-title">
            <div className="live-dot-sm"></div>
            {t(lang, 'tableTitle')}
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t(lang,'colDate')}</th>
                <th>{t(lang,'colOrigin')}</th>
                <th>{t(lang,'colDuration')}</th>
                <th>{t(lang,'colVoice')}</th>
                <th>{t(lang,'colTokens')}</th>
                <th>{t(lang,'colAudio')}</th>
                <th>User</th>
                <th style={{width:'36px'}}></th>
              </tr>
            </thead>
            <tbody>
              {convs.length === 0 ? (
                <tr>
                  <td colSpan="8" style={{padding:0}}>
                    <div className="empty-state">
                      <div className="empty-state-icon">
                        <svg fill="none" viewBox="0 0 22 22" stroke="currentColor" strokeWidth="1.5">
                          <rect x="1.5" y="3.5" width="19" height="15" rx="2"/>
                          <path d="M1.5 8h19" strokeLinecap="round"/>
                        </svg>
                      </div>
                      <h3>{t(lang,'noConv')}</h3>
                      <p>{t(lang,'noConvSub')}</p>
                    </div>
                  </td>
                </tr>
              ) : convs.map(c => (
                <ConvRow
                  key={c.session_id}
                  conv={c}
                  lang={lang}
                  open={openRows.has(c.session_id)}
                  deleting={deleting === c.session_id}
                  onToggle={() => toggle(c.session_id)}
                  onPlayAudio={(track) => playAudio(c.session_id, track)}
                  onDelete={() => setConfirmSid(c.session_id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {confirmSid && (
        <ConfirmModal
          message="Delete this conversation? This cannot be undone."
          onConfirm={() => deleteConv(confirmSid)}
          onCancel={() => setConfirmSid(null)}
        />
      )}
    </>
  )
}

function ConvRow({ conv: c, lang, open, deleting, onToggle, onPlayAudio, onDelete }) {
  const sid   = c.session_id || ''
  const iso   = c.started_at || ''
  const dur   = fmtDur(c.duration_seconds || 0)
  const llm   = (c.usage || {}).llm || {}
  const tok   = llm.total_tokens      || 0
  const pTok  = llm.prompt_tokens     || 0
  const cTok  = llm.completion_tokens || 0
  const tts   = (c.usage || {}).tts_characters || 0
  const from  = (c.call_info || {}).from_number || 'browser'
  const cfg   = c.config || {}
  const voice = cfg.voice || '—'
  const prov  = (cfg.provider || '—').replace('_realtime','').replace(/\b\w/g, x => x.toUpperCase())
  const msgs  = c.messages || []
  const hasBot  = !!c.has_audio_bot
  const hasUser = !!c.has_audio_user
  const [analysis, setAnalysis] = useState(c.analysis || null)
  const createdBy = c.created_by_email || null

  const isBrowser = from === 'browser'

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
        <td className="td-2">
          {isBrowser
            ? <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.6" style={{width:'11px',height:'11px',verticalAlign:'-.1em',marginRight:'3px'}}><circle cx="8" cy="8" r="6.5"/><path d="M5.5 8a8 8 0 0 0 2.5 4.5A8 8 0 0 0 10.5 8a8 8 0 0 0-2.5-4.5A8 8 0 0 0 5.5 8zM1.5 8h13" strokeLinecap="round"/></svg>
            : <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.6" style={{width:'11px',height:'11px',verticalAlign:'-.1em',marginRight:'3px'}}><path d="M3.5 1.5h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1z" strokeLinecap="round"/><circle cx="8" cy="12" r=".8" fill="currentColor" stroke="none"/></svg>
          }
          {from}
        </td>
        <td>{dur}</td>
        <td>
          <span className="prov-badge">{prov}</span>{' '}
          <span className="voice-badge">{voice}</span>
        </td>
        <td className="td-mono">{tok ? tok.toLocaleString() : '—'}</td>
        <td>
          {hasBot && (
            <button className="play-btn" onClick={e => { e.stopPropagation(); onPlayAudio('bot') }}>
              ▶ {t(lang,'trackAgent')}
            </button>
          )}
          {hasUser && (
            <button className="play-btn" onClick={e => { e.stopPropagation(); onPlayAudio('user') }}>
              ▶ {t(lang,'trackUser')}
            </button>
          )}
          {!hasBot && !hasUser && <span style={{color:'var(--text-3)'}}>—</span>}
        </td>
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
          <td colSpan="8">
            {/* Recordings */}
            <div className="det-rec">
              <div className="det-sec-hd">{t(lang,'recordings')}</div>
              {(hasBot || hasUser) ? (
                <div className="audio-strip">
                  {hasBot && (
                    <div className="audio-track">
                      <span className="audio-label">{t(lang,'trackAgent')}</span>
                      <audio id={`audio-bot-${sid}`} controls src={`/api/audio/bot/${sid}`}></audio>
                    </div>
                  )}
                  {hasUser && (
                    <div className="audio-track">
                      <span className="audio-label">{t(lang,'trackUser')}</span>
                      <audio id={`audio-user-${sid}`} controls src={`/api/audio/user/${sid}`}></audio>
                    </div>
                  )}
                </div>
              ) : (
                <span style={{fontSize:'12px',color:'var(--text-3)'}}>{t(lang,'noRecording')}</span>
              )}
            </div>

            {/* Body: tokens + transcript */}
            <div className="det-body">
              <div className="det-tokens">
                <div className="tok-cards">
                  <div className="tok-card">
                    <span className="tok-card-label">{t(lang,'prompt')}</span>
                    <span className="tok-card-val">{pTok.toLocaleString()}</span>
                  </div>
                  <div className="tok-card">
                    <span className="tok-card-label">{t(lang,'completion')}</span>
                    <span className="tok-card-val">{cTok.toLocaleString()}</span>
                  </div>
                  <div className="tok-card">
                    <span className="tok-card-label">{t(lang,'total')}</span>
                    <span className="tok-card-val">{tok.toLocaleString()}</span>
                  </div>
                  <div className="tok-card">
                    <span className="tok-card-label">{t(lang,'ttsChars')}</span>
                    <span className="tok-card-val">{tts.toLocaleString()}</span>
                  </div>
                </div>
                <ConvAnalysis sessionId={sid} analysis={analysis} lang={lang} onAnalyzed={setAnalysis} />
              </div>

              <div className="det-transcript">
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

            {/* Advanced JSON */}
            <details className="det-adv">
              <summary>{t(lang,'advResult')}</summary>
              <pre>{JSON.stringify(c, null, 2)}</pre>
            </details>
          </td>
        </tr>
      )}
    </Fragment>
  )
}

function ConvAnalysis({ sessionId, analysis, lang, onAnalyzed }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(false)

  if (analysis) {
    const s = analysis.sentiment || 'neutral'
    const sKey = { positive:'sSentPos', neutral:'sSentNeu', negative:'sSentNeg' }[s] || 'sSentNeu'
    const hl   = analysis.highlights || []
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
            const result = await analyzeCallApi(sessionId)
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
        {pending ? t(lang,'analyzing') : t(lang,'analyzeBtn')}
      </button>
      {error && <div className="chat-error" style={{marginTop:'6px'}}>{t(lang,'analyzeError')}</div>}
    </>
  )
}
