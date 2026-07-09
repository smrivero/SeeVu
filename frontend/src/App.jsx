import { useState, useEffect } from 'react'
import { checkAuth, logoutApi, fetchProviders, fetchConfig, fetchPrompts } from './api.js'
import LoginScreen from './LoginScreen.jsx'
import Sidebar from './Sidebar.jsx'
import CallsScreen from './CallsScreen.jsx'
import TestCallScreen from './TestCallScreen.jsx'
import SettingsScreen from './SettingsScreen.jsx'
import SavePromptModal from './SavePromptModal.jsx'

export default function App() {
  const [authed, setAuthed]     = useState(null) // null=loading, false=login, true=dashboard
  const [screen, setScreen]     = useState('calls')
  const [lang, setLang]         = useState(() => localStorage.getItem('lang') || 'en')
  const [theme, setTheme]       = useState(() => localStorage.getItem('theme') || 'light')
  const [providers, setProviders] = useState({})
  const [config, setConfig]     = useState({ provider: 'openai_realtime', voice: 'verse' })
  const [prompts, setPrompts]   = useState([])
  const [online, setOnline]     = useState(true)
  const [modal, setModal]       = useState(null)

  useEffect(() => {
    checkAuth().then(ok => {
      setAuthed(ok)
      if (ok) loadData()
    })
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem('lang', lang)
  }, [lang])

  function loadData() {
    Promise.all([fetchProviders(), fetchConfig(), fetchPrompts()]).then(([p, c, pr]) => {
      setProviders(p)
      setConfig(c)
      setPrompts(pr)
    })
  }

  if (authed === null) return null

  if (!authed) return <LoginScreen onLogin={() => { setAuthed(true); loadData() }} />

  return (
    <>
      <Sidebar
        activeScreen={screen}
        onNavigate={setScreen}
        lang={lang}
        theme={theme}
        online={online}
        onLangChange={setLang}
        onThemeChange={dark => setTheme(dark ? 'dark' : 'light')}
        onLogout={async () => {
          await logoutApi()
          setAuthed(false)
        }}
      />

      <div className="main">
        <div className={`screen${screen === 'calls' ? ' active' : ''}`}>
          <CallsScreen
            lang={lang}
            onOnlineChange={setOnline}
          />
        </div>

        <div className={`screen${screen === 'testcall' ? ' active' : ''}`}>
          <TestCallScreen
            lang={lang}
            providers={providers}
            config={config}
            prompts={prompts}
            onPromptsChange={setPrompts}
            onConfigChange={setConfig}
            onOpenModal={content => setModal({ content })}
          />
        </div>

        <div className={`screen${screen === 'settings' ? ' active' : ''}`}>
          <SettingsScreen
            lang={lang}
            providers={providers}
            config={config}
            prompts={prompts}
            onPromptsChange={setPrompts}
            onConfigChange={setConfig}
            onOpenModal={content => setModal({ content })}
          />
        </div>
      </div>

      {modal && (
        <SavePromptModal
          lang={lang}
          content={modal.content}
          onClose={() => setModal(null)}
          onSaved={newPrompts => { setPrompts(newPrompts); setModal(null) }}
        />
      )}
    </>
  )
}
