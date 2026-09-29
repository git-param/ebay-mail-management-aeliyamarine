import { API, apiPath } from '../constants/api'
import { apiRequest } from './http'

function getErrorMessage(status, data) {
  if (data.detail || data.message) {
    return data.detail || data.message
  }

  const messages = {
    400: 'The category details are invalid. Please check and try again.',
    401: 'Your session has expired. Please sign in again.',
    403: 'You do not have permission to manage categories.',
    404: 'The requested category could not be found.',
    500: 'The server could not complete the request. Please try again later.',
  }

  return messages[status] || 'Something went wrong. Please try again.'
}

async function request(path, options = {}) {
  return apiRequest(path, options, getErrorMessage)
}

export function fetchCategories() {
  return request(API.CATEGORIES.ROOT)
}

export function fetchCategory(categoryId) {
  return request(apiPath(API.CATEGORIES.BY_CATEGORY_ID, { categoryId }))
}

export function createCategory(payload) {
  return request(API.CATEGORIES.ROOT, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateCategory(categoryId, payload) {
  return request(apiPath(API.CATEGORIES.BY_CATEGORY_ID, { categoryId }), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function activateCategory(categoryId) {
  return request(apiPath(API.CATEGORIES.BY_CATEGORY_ID_ACTIVATE, { categoryId }), {
    method: 'PATCH',
  })
}

export function deactivateCategory(categoryId) {
  return request(apiPath(API.CATEGORIES.BY_CATEGORY_ID_DEACTIVATE, { categoryId }), {
    method: 'PATCH',
  })
}

export function deleteCategory(categoryId) {
  return request(apiPath(API.CATEGORIES.BY_CATEGORY_ID, { categoryId }), {
    method: 'DELETE',
  })
}

export function createCategoryKeyword(categoryId, payload) {
  return request(apiPath(API.CATEGORIES.BY_CATEGORY_ID_KEYWORDS, { categoryId }), {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deleteCategoryKeyword(categoryId, keywordId) {
  return request(apiPath(API.CATEGORIES.BY_CATEGORY_ID_KEYWORDS_BY_KEYWORD_ID, { categoryId, keywordId }), {
    method: 'DELETE',
  })
}

export function updateUserCategoryAssignments(userId, categoryIds) {
  return request(apiPath(API.CATEGORIES.USERS_BY_USER_ID_ASSIGNMENTS, { userId }), {
    method: 'PUT',
    body: JSON.stringify({ category_ids: categoryIds }),
  })
}
