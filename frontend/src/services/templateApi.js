import { apiRequest } from './http'

async function request(path, options = {}) {
  return apiRequest(path, options, (status, data) => data.detail || data.message || 'Unable to load templates')
}

export function fetchTemplates({ includeInactive = false } = {}) {
  const query = includeInactive ? '?include_inactive=true' : ''
  return request(`/templates${query}`)
}

export function createTemplate(payload) {
  return request('/templates', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTemplate(templateId, payload) {
  return request(`/templates/${templateId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteTemplate(templateId) {
  return request(`/templates/${templateId}`, {
    method: 'DELETE',
  })
}

export function fetchRoleTemplatePermissions(roleId) {
  return request(`/templates/roles/${roleId}/permissions`)
}

export function updateRoleTemplatePermissions(roleId, permissionCodes) {
  return request(`/templates/roles/${roleId}/permissions`, {
    method: 'PUT',
    body: JSON.stringify({ permission_codes: permissionCodes }),
  })
}
