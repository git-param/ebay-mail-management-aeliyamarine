export function bestOfferMoney(amount, currency) {
  if (amount == null || !currency) return '—'
  try { return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(amount)) }
  catch { return `${amount} ${currency}` }
}

export function bestOfferDate(value) {
  return value ? new Date(value).toLocaleString() : '—'
}

