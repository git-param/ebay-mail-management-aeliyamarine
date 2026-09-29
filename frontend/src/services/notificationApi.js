import { API, apiPath } from '../constants/api'
import { apiRequest } from './http'

async function request(path, options = {}) {
  return apiRequest(path, options, (status, data) => data.detail || data.message || 'Something went wrong')
}

export function fetchNotifications() {
  return request(API.NOTIFICATIONS.ROOT + "?limit=10")
}

export function markNotificationsRead() {
  return request(API.NOTIFICATIONS.READ, { method: 'PATCH' })
}

export function deleteNotification(notificationId) {
  return request(apiPath(API.NOTIFICATIONS.BY_NOTIFICATION_ID, { notificationId: encodeURIComponent(notificationId) }), { method: 'DELETE' })
}

export function deleteAllNotifications() {
  return request(API.NOTIFICATIONS.ROOT, { method: 'DELETE' })
}
