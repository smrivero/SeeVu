import { t } from './i18n.js'

export default function Sidebar({ activeScreen, onNavigate, lang, theme, online, onLangChange, onThemeChange }) {
  return (
    <nav className="sidebar">
      <div className="sb-brand">
        <svg viewBox="0 0 38 38" fill="none" xmlns="http://www.w3.org/2000/svg" style={{width:'38px',height:'38px',flexShrink:0}}>
          <defs>
            <linearGradient id="sv-sb" x1="0" y1="0" x2="38" y2="38" gradientUnits="userSpaceOnUse">
              <stop stopColor="#38C6F4"/>
              <stop offset="1" stopColor="#0B5CAD"/>
            </linearGradient>
          </defs>
          <rect width="38" height="38" rx="9" fill="url(#sv-sb)"/>
          <path d="M7 19.5 Q13 13 19 13 Q25 13 31 19.5 Q25 26 19 26 Q13 26 7 19.5Z" fill="white"/>
          <circle cx="19" cy="19.5" r="5.2" fill="#1EA7F2"/>
          <path d="M13.8 19.5v2.2M16.2 17.8v5.5M18.6 18.8v3.5M21 17v6M23.4 18v4.5" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
          <rect x="27" y="5.5" width="2.2" height="2.2" rx=".5" fill="rgba(255,255,255,.7)"/>
          <rect x="30.5" y="5.5" width="2.2" height="2.2" rx=".5" fill="rgba(255,255,255,.45)"/>
          <rect x="28.5" y="8.5" width="1.8" height="1.8" rx=".4" fill="rgba(255,255,255,.3)"/>
          <rect x="4.5" y="27" width="2.2" height="2.2" rx=".5" fill="rgba(255,255,255,.7)"/>
          <rect x="8" y="27" width="2.2" height="2.2" rx=".5" fill="rgba(255,255,255,.45)"/>
          <rect x="4.5" y="30.5" width="1.8" height="1.8" rx=".4" fill="rgba(255,255,255,.3)"/>
        </svg>
        <div>
          <div className="sb-name">SeeVu</div>
          <div className="sb-sub">AI Call Automation</div>
        </div>
      </div>

      <div className="sb-nav">
        <NavItem
          active={activeScreen === 'calls'}
          onClick={() => onNavigate('calls')}
          icon={
            <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.8">
              <rect x="1.5" y="3.5" width="13" height="10" rx="1.5"/>
              <path d="M1.5 6.5h13" strokeLinecap="round"/>
            </svg>
          }
        >
          {t(lang, 'navCalls')}
        </NavItem>

        <NavItem
          active={activeScreen === 'testcall'}
          onClick={() => onNavigate('testcall')}
          icon={
            <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.8">
              <path d="M2 11l3-3 2.5 2 3-4L13 9" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="13" cy="3.5" r="1.5"/>
            </svg>
          }
        >
          {t(lang, 'navTest')}
        </NavItem>

        <NavItem
          active={activeScreen === 'settings'}
          onClick={() => onNavigate('settings')}
          icon={
            <svg fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.8">
              <circle cx="8" cy="8" r="2.5"/>
              <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.1 3.1l1.4 1.4M11.5 11.5l1.4 1.4M3.1 12.9l1.4-1.4M11.5 4.5l1.4-1.4" strokeLinecap="round"/>
            </svg>
          }
        >
          {t(lang, 'navSettings')}
        </NavItem>
      </div>

      <div className="sb-footer">
        <div className="conn-row">
          <div className="conn-dot" style={online ? {} : {background:'var(--red)'}}></div>
          <span>{t(lang, 'connStatus')}</span>
        </div>

        <div className="sb-footer-row">
          <span className="sb-label">{t(lang, 'footerLang')}</span>
          <div className="lang-toggle">
            <button
              className={`lang-btn${lang === 'en' ? ' active' : ''}`}
              onClick={() => onLangChange('en')}
            >EN</button>
            <button
              className={`lang-btn${lang === 'es' ? ' active' : ''}`}
              onClick={() => onLangChange('es')}
            >ES</button>
          </div>
        </div>

        <div className="sb-footer-row">
          <span className="sb-label">{t(lang, 'footerTheme')}</span>
          <label className="switch">
            <input
              type="checkbox"
              checked={theme === 'dark'}
              onChange={e => onThemeChange(e.target.checked)}
            />
            <span className="slider"></span>
          </label>
        </div>

        <div className="sb-footer-row" style={{borderTop:'1px solid var(--border)',marginTop:'2px',paddingTop:'8px'}}>
          <a
            href="/logout"
            style={{fontSize:'11px',color:'var(--text-3)',textDecoration:'none'}}
            onMouseOver={e => e.target.style.color='var(--text)'}
            onMouseOut={e => e.target.style.color='var(--text-3)'}
          >
            {t(lang, 'logout')}
          </a>
        </div>
      </div>
    </nav>
  )
}

function NavItem({ active, onClick, icon, children }) {
  return (
    <button
      className={`nav-item${active ? ' active' : ''}`}
      onClick={onClick}
    >
      {icon}
      <span>{children}</span>
    </button>
  )
}
