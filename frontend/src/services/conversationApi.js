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
  return request(`/conversations${buildQuery(params)}`)
}

export function fetchConversation(conversationId) {
  return request(`/conversations/${conversationId}`)
}

export function fetchConversationContext(conversationId) {
  return request(`/conversations/${conversationId}/context`)
}

export function assignConversation(conversationId, assignedTo) {
  return request(`/conversations/${conversationId}/assign`, {
    method: 'POST',
    body: JSON.stringify({ assigned_to: assignedTo }),
  })
}

export function bulkUpdateConversations(payload) {
  return request('/conversations/bulk-update', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchConversationNotes(conversationId) {
  return request(`/conversations/${conversationId}/notes`)
}

export function createConversationNote(conversationId, body) {
  return request(`/conversations/${conversationId}/notes`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  })
}

export function updateConversationCategory(conversationId, categoryId) {
  return request(`/conversations/${conversationId}/category`, {
    method: 'PATCH',
    body: JSON.stringify({ category_id: categoryId || null }),
  })
}

export function updateConversationStatus(conversationId, status) {
  return request(`/conversations/${conversationId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export function validateConversationReply(conversationId, body) {
  return request(`/conversations/${conversationId}/reply/validate`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  })
}

export function sendConversationReply(conversationId, body, messageTypeId) {
  return request(`/conversations/${conversationId}/reply`, {
    method: 'POST',
    body: JSON.stringify({ body, message_type_id: messageTypeId }),
  })
}

export function sendConversationReplyWithAttachments(conversationId, body, files = [], messageTypeId) {
  const formData = new FormData()
  formData.set('body', body)
  formData.set('message_type_id', messageTypeId)
  files.forEach((file) => formData.append('attachments', file))
  return apiFormRequest(`/conversations/${conversationId}/reply`, formData, getErrorMessage)
}

