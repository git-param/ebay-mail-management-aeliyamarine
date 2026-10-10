import { API, apiPath } from '../constants/api'
import { apiFormRequest, apiRequest } from './http'

function getErrorMessage(status, data) {
  if (data.detail || data.message) {
    return data.detail || data.message
  }

  const messages = {
    400: 'The conversation request is invalid. Please check the filters and try again.',
    401: 'Your session has expired. Please sign in again.',
    403: 'You do not have permission to access this conversation.',
    404: 'The requested conversation could not be found.',
    500: 'The server could not complete the request. Please try again later.',
  }

  return messages[status] || `Conversation request failed (${status}). Please try again.`
}

function buildQuery(params = {}) {
  const query = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, value)
    }
  })

  const queryString = query.toString()
  return queryString ? `?${queryString}` : ''
}

async function request(path, options = {}) {
  return apiRequest(path, options, getErrorMessage)
}

export function fetchConversations(params) {
  return request(API.CONVERSATIONS.ROOT + (buildQuery(params)))
}

export function fetchConversation(conversationId) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID, { conversationId }))
}

export function fetchConversationAdditionalDetails(conversationId) {
  return request(apiPath(API.CONVERSATIONS.ADDITIONAL_DETAILS, { conversationId }))
}

export function fetchConversationLiveReturns(conversationId, params = {}) {
  return request(apiPath(API.CONVERSATIONS.LIVE_RETURNS, { conversationId }) + buildQuery(params))
}

export function fetchConversationContext(conversationId) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_CONTEXT, { conversationId }))
}

export function translateMessage(text, targetLanguage = 'en') {
  return request(API.CONVERSATIONS.TRANSLATE, {
    method: 'POST',
    body: JSON.stringify({ text, target_language: targetLanguage }),
  })
}

export function assignConversation(conversationId, assignedTo) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_ASSIGN, { conversationId }), {
    method: 'POST',
    body: JSON.stringify({ assigned_to: assignedTo }),
  })
}

export function bulkUpdateConversations(payload) {
  return request(API.CONVERSATIONS.BULK_UPDATE, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateConversationReadState(conversationId, isRead) {
  return request(apiPath(API.CONVERSATIONS.READ_STATE, { conversationId }), {
    method: 'PATCH',
    body: JSON.stringify({ is_read: isRead }),
  })
}

export function updateBulkConversationReadState(conversationIds, isRead) {
  return request(API.CONVERSATIONS.BULK_READ_STATE, {
    method: 'POST',
    body: JSON.stringify({ conversation_ids: conversationIds, is_read: isRead }),
  })
}

export function fetchConversationNotes(conversationId) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_NOTES, { conversationId }))
}

export function createConversationNote(conversationId, body) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_NOTES, { conversationId }), {
    method: 'POST',
    body: JSON.stringify({ body }),
  })
}

export function unassignConversation(conversationId) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_UNASSIGN, { conversationId }), {
    method: 'POST',
  })
}

export function updateConversationNote(conversationId, noteId, body) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_NOTES_BY_NOTE_ID, { conversationId, noteId }), {
    method: 'PATCH',
    body: JSON.stringify({ body }),
  })
}

export function deleteConversationNote(conversationId, noteId) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_NOTES_BY_NOTE_ID, { conversationId, noteId }), {
    method: 'DELETE',
  })
}

export function updateConversationCategory(conversationId, categoryId) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_CATEGORY, { conversationId }), {
    method: 'PATCH',
    body: JSON.stringify({ category_id: categoryId || null }),
  })
}

export function updateConversationStatus(conversationId, status) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_STATUS, { conversationId }), {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export function validateConversationReply(conversationId, body) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_REPLY_VALIDATE, { conversationId }), {
    method: 'POST',
    body: JSON.stringify({ body }),
  })
}

export function sendConversationReply(conversationId, body, messageTypeId, sendCopyToEmail = true) {
  return request(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_REPLY, { conversationId }), {
    method: 'POST',
    body: JSON.stringify({ body, message_type_id: messageTypeId, send_copy_to_email: sendCopyToEmail }),
  })
}

export function sendConversationReplyWithAttachments(conversationId, body, files = [], messageTypeId, sendCopyToEmail = true) {
  const formData = new FormData()
  formData.set('body', body)
  formData.set('message_type_id', messageTypeId)
  formData.set('send_copy_to_email', sendCopyToEmail ? 'true' : 'false')
  files.forEach((file) => formData.append('attachments', file))
  return apiFormRequest(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_REPLY, { conversationId }), formData, getErrorMessage)
}

