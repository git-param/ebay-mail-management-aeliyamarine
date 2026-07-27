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
