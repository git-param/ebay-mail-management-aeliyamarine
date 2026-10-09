const RECIPIENT_PARAMS = ['new_buyer', 'sending_account', 'sold_order', 'sending_account_name']

export function orderConversationUrl(result) {
  const params = new URLSearchParams()
  if (result.conversation_id) {
    params.set('conversation_id', result.conversation_id)
  } else {
    params.set('new_buyer', result.buyer_username)
    params.set('sending_account', result.account_id)
    params.set('sold_order', result.order_id)
    params.set('sending_account_name', result.account_name)
  }
  return `/inbox?${params}`
}

export function getOrderRecipientFromUrl() {
  const params = new URLSearchParams(window.location.search)
  const buyerUsername = params.get('new_buyer')
  const accountId = params.get('sending_account')
  const orderId = params.get('sold_order')
  return buyerUsername && accountId && orderId ? {
    buyerUsername, accountId, orderId, accountName: params.get('sending_account_name'),
  } : null
}

export function clearOrderRecipientParams(url) {
  RECIPIENT_PARAMS.forEach((parameter) => url.searchParams.delete(parameter))
}
