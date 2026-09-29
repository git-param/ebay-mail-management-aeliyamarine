import { API, apiPath } from '../constants/api'
import { apiRequest } from './http'

async function request(path, options = {}) {
  return apiRequest(path, options, (status, data) => data.detail || data.message || 'Unable to load templates')
}

export function fetchTemplates({ includeInactive = false } = {}) {
  const query = includeInactive ? '?include_inactive=true' : ''
  return request(API.TEMPLATES.ROOT + (query))
}

export function createTemplate(payload) {
  return request(API.TEMPLATES.ROOT, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTemplate(templateId, payload) {
  return request(apiPath(API.TEMPLATES.BY_TEMPLATE_ID, { templateId }), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteTemplate(templateId) {
  return request(apiPath(API.TEMPLATES.BY_TEMPLATE_ID, { templateId }), {
    method: 'DELETE',
  })
}

export function fetchTemplateCategories({ includeInactive = false } = {}) {
  const query = includeInactive ? '?include_inactive=true' : ''
  return request(API.TEMPLATES.CATEGORIES + (query))
}

export function createTemplateCategory(payload) {
  return request(API.TEMPLATES.CATEGORIES, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTemplateCategory(categoryId, payload) {
  return request(apiPath(API.TEMPLATES.CATEGORIES_BY_CATEGORY_ID, { categoryId }), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteTemplateCategory(categoryId) {
  return request(apiPath(API.TEMPLATES.CATEGORIES_BY_CATEGORY_ID, { categoryId }), {
    method: 'DELETE',
  })
}

export function fetchRoleTemplatePermissions(roleId) {
  return request(apiPath(API.TEMPLATES.ROLES_BY_ROLE_ID_PERMISSIONS, { roleId }))
}

export function updateRoleTemplatePermissions(roleId, permissionCodes) {
  return request(apiPath(API.TEMPLATES.ROLES_BY_ROLE_ID_PERMISSIONS, { roleId }), {
    method: 'PUT',
    body: JSON.stringify({ permission_codes: permissionCodes }),
  })
}
