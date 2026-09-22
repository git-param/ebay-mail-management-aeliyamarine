import { apiRequest } from './http'

export function fetchConfigSettings() {
  return apiRequest('/config')
}

export function updateConfigSettings(settings) {
  return apiRequest('/config', {
    method: 'PUT',
    body: JSON.stringify({ settings }),
  })
}

export function fetchAccountSyncStates() {
  return apiRequest('/config/account-sync')
}

export function updateAccountSyncState(payload) {
  return apiRequest('/config/account-sync', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteConversationData(confirmation, date_from, date_to) {
  return apiRequest('/config/conversation-data', {
    method: 'DELETE',
    body: JSON.stringify({ confirmation, date_from: date_from || null, date_to: date_to || null }),
  })
}
