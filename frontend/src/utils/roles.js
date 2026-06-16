export function normalizeRole(role) {
  const normalizedRole = String(role || '')
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, '_')

  if (normalizedRole === 'OPERATIONS_MANAGER') {
    return 'OPS_MANAGER'
  }

  if (normalizedRole === 'SUPPORT_AGENT') {
    return 'AGENT'
  }

  return normalizedRole
}
