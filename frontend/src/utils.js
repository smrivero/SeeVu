export function normalizePromptContent(content) {
  return (content || '').replace(/\r\n/g, '\n').trim()
}

/** Encuentra el prompt guardado que corresponde al contenido activo. */
export function findPromptByContent(prompts, content) {
  const normalized = normalizePromptContent(content)
  if (!normalized) return null

  const exact = prompts.find((p) => normalizePromptContent(p.content) === normalized)
  if (exact) return exact

  // Mismo template con ediciones menores (ej. cambiar el nombre del agente)
  const activeTail = normalized.split('\n').slice(1).join('\n')
  return prompts.find((p) => {
    const savedTail = normalizePromptContent(p.content).split('\n').slice(1).join('\n')
    return savedTail.length > 80 && activeTail === savedTail
  }) || null
}

export function resolveActivePromptSelection(prompts, activeData) {
  const content = activeData?.content || ''
  const savedId = activeData?.prompt_id || activeData?.promptId
  if (savedId && prompts.some((p) => p.id === savedId)) {
    return { content, promptId: savedId }
  }
  const match = findPromptByContent(prompts, content)
  return { content, promptId: match?.id || '' }
}

export function fmtDur(s) {
  return s < 60 ? s + 's' : Math.floor(s / 60) + 'm ' + (s % 60) + 's'
}

export function relTime(iso) {
  if (!iso) return '—'
  const d = Math.floor((Date.now() - new Date(iso)) / 1000)
  if (d < 60)    return 'just now'
  if (d < 3600)  return Math.floor(d / 60) + 'm ago'
  if (d < 86400) return Math.floor(d / 3600) + 'h ago'
  return Math.floor(d / 86400) + 'd ago'
}
