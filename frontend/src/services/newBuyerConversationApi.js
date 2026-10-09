import { API } from '../constants/api'
import { apiFormRequest, apiRequest } from './http'

export function validateFirstBuyerMessage(_conversationId, body) {
  return apiRequest(API.CONVERSATIONS.START_VALIDATE, {
    method: 'POST',
    body: JSON.stringify({ body }),
  })
}

export function sendFirstBuyerMessage({ accountId, buyerUsername, body, files, messageTypeId, sendCopyToEmail }) {
  const formData = new FormData()
  formData.set('account_id', accountId)
  formData.set('buyer_username', buyerUsername)
  formData.set('body', body)
  formData.set('message_type_id', messageTypeId)
  formData.set('send_copy_to_email', String(sendCopyToEmail))
  files.forEach((file) => formData.append('attachments', file))
  return apiFormRequest(API.CONVERSATIONS.START, formData)
}
