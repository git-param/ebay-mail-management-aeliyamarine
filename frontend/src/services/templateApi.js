const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || data.message || 'Unable to load templates')
  }
  return data
}

export function fetchTemplates() {
  return request('/templates')
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
