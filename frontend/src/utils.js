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
