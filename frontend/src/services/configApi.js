import { API } from '../constants/api'
import { apiRequest } from './http'

export function fetchConfigSettings() {
  return apiRequest(API.CONFIG.ROOT)
}

export function updateConfigSettings(settings) {
  return apiRequest(API.CONFIG.ROOT, {
    method: 'PUT',
    body: JSON.stringify({ settings }),
  })
}

export function fetchAccountSyncStates() {
  return apiRequest(API.CONFIG.ACCOUNT_SYNC)
}

export function updateAccountSyncState(payload) {
  return apiRequest(API.CONFIG.ACCOUNT_SYNC, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteConversationData(confirmation, date_from, date_to) {
  return apiRequest(API.CONFIG.CONVERSATION_DATA, {
    method: 'DELETE',
    body: JSON.stringify({ confirmation, date_from: date_from || null, date_to: date_to || null }),
  })
}
