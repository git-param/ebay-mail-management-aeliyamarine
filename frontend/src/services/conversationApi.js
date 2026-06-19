const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

function getAuthToken() {
  return localStorage.getItem('accessToken') || ''
}

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

  return messages[status] || 'Something went wrong. Please try again.'
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
  const token = getAuthToken()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
  })

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    throw new Error(getErrorMessage(response.status, data))
  }

  return data
}

export function fetchConversations(params) {
  return request(`/conversations${buildQuery(params)}`)
}

export function fetchConversation(conversationId) {
  return request(`/conversations/${conversationId}`)
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
