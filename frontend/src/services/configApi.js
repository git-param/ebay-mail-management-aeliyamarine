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

export function deleteConversationData(confirmation) {
  return apiRequest('/config/conversation-data', {
    method: 'DELETE',
    body: JSON.stringify({ confirmation }),
  })
}
