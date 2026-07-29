import { apiRequest } from './http'

async function request(path, options = {}) {
  return apiRequest(path, options, (status, data) => data.detail || data.message || 'Something went wrong')
}

export function fetchNotifications() {
  return request('/notifications?limit=10')
}

export function markNotificationsRead() {
  return request('/notifications/read', { method: 'PATCH' })
}

export function deleteNotification(notificationId) {
  return request(`/notifications/${encodeURIComponent(notificationId)}`, { method: 'DELETE' })
}

export function deleteAllNotifications() {
  return request('/notifications', { method: 'DELETE' })
}
