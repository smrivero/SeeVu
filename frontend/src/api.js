export async function checkAuth() {
  const r = await fetch('/api/auth/me')
  return r.ok
}

export async function loginApi(email, password) {
  const r = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const data = await r.json()
  return { ok: r.ok, data }
}

export async function logoutApi() {
  await fetch('/api/auth/logout', { method: 'POST' })
}

export async function getMeApi() {
  const r = await fetch('/api/auth/me')
  if (!r.ok) return null
  return r.json()
}

export async function fetchProviders() {
  return fetch('/api/providers').then(r => r.json())
}

export async function fetchConfig() {
  return fetch('/api/config').then(r => r.json())
}

export async function saveConfig(provider, voice, logLevel) {
  return fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, voice, log_level: logLevel }),
  }).then(r => r.json())
}

export async function fetchConversations() {
  const r = await fetch('/api/conversations')
  if (!r.ok) throw new Error('offline')
  return r.json()
}

export async function fetchPrompts() {
  return fetch('/api/prompts').then(r => r.json())
}

export async function fetchActivePrompt() {
  return fetch('/api/prompt/active').then(r => r.json())
}

export async function savePromptApi(name, lang, content) {
  return fetch('/api/prompts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, lang, content }),
  }).then(r => r.json())
}

export async function applyPromptApi(content, promptId = null) {
  return fetch('/api/prompt/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, prompt_id: promptId || undefined }),
  }).then(r => r.json())
}

export async function fetchLiveSession() {
  return fetch('/api/live-session').then(r => r.json())
}

export async function analyzeCallApi(sessionId) {
  const r = await fetch(`/api/analyze/${sessionId}`, { method: 'POST' })
  if (!r.ok) throw new Error('analyze failed')
  return r.json()
}

export async function deleteConversationApi(sessionId) {
  const r = await fetch(`/api/conversations/${sessionId}`, { method: 'DELETE' })
  return r.json()
}
