const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

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
    throw new Error(getErrorMessage(response.status, data))
  }

  return data
}

export function fetchCategories() {
  return request('/categories')
}

export function fetchCategory(categoryId) {
  return request(`/categories/${categoryId}`)
}

export function createCategory(payload) {
  return request('/categories', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateCategory(categoryId, payload) {
  return request(`/categories/${categoryId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function activateCategory(categoryId) {
  return request(`/categories/${categoryId}/activate`, {
    method: 'PATCH',
  })
}

export function deactivateCategory(categoryId) {
  return request(`/categories/${categoryId}/deactivate`, {
    method: 'PATCH',
  })
}

export function deleteCategory(categoryId) {
  return request(`/categories/${categoryId}`, {
    method: 'DELETE',
  })
}

export function createCategoryKeyword(categoryId, payload) {
  return request(`/categories/${categoryId}/keywords`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deleteCategoryKeyword(categoryId, keywordId) {
  return request(`/categories/${categoryId}/keywords/${keywordId}`, {
    method: 'DELETE',
  })
}

export function updateUserCategoryAssignments(userId, categoryIds) {
  return request(`/categories/users/${userId}/assignments`, {
    method: 'PUT',
    body: JSON.stringify({ category_ids: categoryIds }),
  })
}
