import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import {
  activateCategory,
  createCategory,
  deactivateCategory,
  deleteCategory,
  fetchCategories,
  fetchCategory,
  updateCategory,
} from '../../services/categoryApi'
import { normalizeRole } from '../../utils/roles'

import './categories.css'

const EMPTY_FORM = {
  name: '',
  description: '',
  color: '#2563eb',
  slaHours: '24',
  keywords: [],
}

function formatDate(value) {
  if (!value) {
    return 'Not available'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function normalizeCategory(category) {
  const keywords = Array.isArray(category.keywords) ? category.keywords : []
  return {
    ...category,
    id: category.id,
    name: category.name || '',
    description: category.description || '',
    color: category.color || '#2563eb',
    slaHours: category.sla_hours || 0,
    isActive: Boolean(category.is_active),
    status: category.is_active ? 'Active' : 'Inactive',
    keywords,
    keywordLabels: keywords.map((keyword) => keyword.keyword),
    keywordsCount: category.keywords_count ?? keywords.length,
    createdDate: formatDate(category.created_at),
    updatedDate: formatDate(category.updated_at),
    raw: category,
  }
}

function getCategoriesFromResponse(response) {
  if (Array.isArray(response)) {
    return response
  }

  if (Array.isArray(response.data)) {
    return response.data
  }

  return response.categories || response.items || []
}

function normalizeText(value) {
  return String(value || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

function toCategoryPayload(values) {
  return {
    name: values.name.trim(),
    description: values.description.trim() || null,
    color: values.color,
    sla_hours: Number(values.slaHours),
    keywords: values.keywords.map((keyword) => keyword.trim()).filter(Boolean),
  }
}

function StatCard({ label, value }) {
  return (
    <article className="stat-card">
      <span className="stat-icon">
        <Icon name="tag" />
      </span>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </article>
  )
}

function Badge({ value }) {
  const className = `status-badge status-${value.toLowerCase()}`
  return <span className={className}>{value}</span>
}

function Modal({ title, children, onClose }) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal-header">
          <h2 id="modal-title">{title}</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
            <Icon name="close" />
          </button>
        </div>
        {children}
      </section>
    </div>
  )
}

function KeywordEditor({ values, setValues, errors, setErrors }) {
  const [keywordInput, setKeywordInput] = useState('')

  function addKeyword() {
    const keyword = keywordInput.trim()
    if (!keyword) {
      return
    }

    const exists = values.keywords.some((existingKeyword) => normalizeText(existingKeyword) === normalizeText(keyword))
    if (exists) {
      setErrors((current) => ({ ...current, keywords: 'Duplicate keywords are not allowed.' }))
      return
    }

    setValues((current) => ({ ...current, keywords: [...current.keywords, keyword] }))
    setKeywordInput('')
    setErrors((current) => ({ ...current, keywords: '' }))
  }

  function removeKeyword(keyword) {
    setValues((current) => ({
      ...current,
      keywords: current.keywords.filter((existingKeyword) => existingKeyword !== keyword),
    }))
  }

  function handleKeywordKeyDown(event) {
    if (event.key === 'Enter') {
      event.preventDefault()
      addKeyword()
    }
  }

  return (
    <div className="field form-field-wide">
      <span>Keywords</span>
      <div className="keyword-input-row">
        <input
          value={keywordInput}
          onChange={(event) => setKeywordInput(event.target.value)}
          onKeyDown={handleKeywordKeyDown}
          placeholder="Add keyword"
        />
        <button className="secondary-button" type="button" onClick={addKeyword}>
          Add
        </button>
      </div>
      {values.keywords.length ? (
        <div className="keyword-tags">
          {values.keywords.map((keyword) => (
            <span className="keyword-tag" key={keyword}>
              {keyword}
              <button type="button" onClick={() => removeKeyword(keyword)} aria-label={`Remove ${keyword}`}>
                <Icon name="close" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      {errors.keywords ? <small>{errors.keywords}</small> : null}
    </div>
  )
}

function CategoryForm({ initialValues, categories, selectedCategory, isSubmitting, submitLabel, onCancel, onSubmit }) {
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState({})

  function updateField(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
  }

  function handleSubmit(event) {
    event.preventDefault()
    const nextErrors = {}

    if (!values.name.trim()) {
      nextErrors.name = 'Category name is required.'
    } else {
      const duplicateName = categories.some((category) => {
        return category.id !== selectedCategory?.id && normalizeText(category.name) === normalizeText(values.name)
      })
      if (duplicateName) {
        nextErrors.name = 'A category with this name already exists.'
      }
    }

    if (!values.slaHours) {
      nextErrors.slaHours = 'SLA hours are required.'
    } else if (!Number.isFinite(Number(values.slaHours)) || Number(values.slaHours) < 1) {
      nextErrors.slaHours = 'SLA hours must be at least 1.'
    }

    const uniqueKeywords = new Set(values.keywords.map(normalizeText))
    if (uniqueKeywords.size !== values.keywords.length) {
      nextErrors.keywords = 'Duplicate keywords are not allowed.'
    }

    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) {
      return
    }

    onSubmit(values)
  }

  return (
    <form className="management-form" onSubmit={handleSubmit}>
      <label className="field">
        <span>Category Name</span>
        <input name="name" value={values.name} onChange={updateField} />
        {errors.name ? <small>{errors.name}</small> : null}
      </label>

      <label className="field">
        <span>Color</span>
        <input name="color" type="color" value={values.color} onChange={updateField} />
      </label>

      <label className="field">
        <span>SLA Hours</span>
        <input name="slaHours" type="number" min="1" value={values.slaHours} onChange={updateField} />
        {errors.slaHours ? <small>{errors.slaHours}</small> : null}
      </label>

      <label className="field form-field-wide">
        <span>Description</span>
        <textarea name="description" value={values.description} onChange={updateField} rows="4" />
      </label>

      <KeywordEditor values={values} setValues={setValues} errors={errors} setErrors={setErrors} />

      <div className="modal-actions">
        <button className="secondary-button" type="button" onClick={onCancel}>
          Cancel
        </button>
        <button className="primary-button compact" type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Saving...' : submitLabel}
        </button>
      </div>
    </form>
  )
}

function ConfirmModal({ title, message, actionLabel, danger, isSubmitting, onCancel, onConfirm }) {
  return (
    <Modal title={title} onClose={onCancel}>
      <p className="confirm-message">{message}</p>
      <div className="modal-actions">
        <button className="secondary-button" type="button" onClick={onCancel}>
          Cancel
        </button>
        <button
          className={danger ? 'danger-button' : 'primary-button compact'}
          type="button"
          onClick={onConfirm}
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Working...' : actionLabel}
        </button>
      </div>
    </Modal>
  )
}

function CategoryDrawer({ category, onClose }) {
  if (!category) {
    return null
  }

  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="user-drawer" aria-labelledby="drawer-title">
        <div className="drawer-header">
          <h2 id="drawer-title">Category Details</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close details">
            <Icon name="close" />
          </button>
        </div>

        <div className="drawer-profile">
          <span className="category-color large" style={{ backgroundColor: category.color }} />
          <h3>{category.name}</h3>
          <p>{category.description || 'No description added.'}</p>
          <div className="badge-row">
            <Badge value={category.status} />
          </div>
        </div>

        <dl className="detail-grid">
          <div>
            <dt>Color</dt>
            <dd>{category.color}</dd>
          </div>
          <div>
            <dt>SLA Hours</dt>
            <dd>{category.slaHours}</dd>
          </div>
          <div>
            <dt>Created Date</dt>
            <dd>{category.createdDate}</dd>
          </div>
          <div>
            <dt>Updated Date</dt>
            <dd>{category.updatedDate}</dd>
          </div>
        </dl>

        <section className="drawer-section">
          <h3>Keywords</h3>
          {category.keywordLabels.length ? (
            <div className="keyword-tags">
              {category.keywordLabels.map((keyword) => (
                <span className="keyword-tag read-only" key={keyword}>
                  {keyword}
                </span>
              ))}
            </div>
          ) : (
            <p className="drawer-note">No keywords added.</p>
          )}
        </section>
      </aside>
    </div>
  )
}

function Categories({ currentUser, onLogout }) {
  const [categories, setCategories] = useState([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('All')
  const [actionCategoryId, setActionCategoryId] = useState(null)
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [modal, setModal] = useState(null)
  const [notification, setNotification] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const currentRole = normalizeRole(currentUser?.role)
  const canManage = currentRole === 'ADMIN'

  async function loadCategories() {
    setIsLoading(true)
    setError('')

    try {
      const response = await fetchCategories()
      setCategories(getCategoriesFromResponse(response).map(normalizeCategory))
    } catch (caughtError) {
      setError(caughtError.message)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadCategories()
  }, [])

  const filteredCategories = useMemo(() => {
    return categories.filter((category) => {
      const query = search.trim().toLowerCase()
      const matchesSearch =
        !query ||
        category.name.toLowerCase().includes(query) ||
        category.description.toLowerCase().includes(query) ||
        category.keywordLabels.some((keyword) => keyword.toLowerCase().includes(query))
      const matchesStatus = statusFilter === 'All' || category.status === statusFilter
      return matchesSearch && matchesStatus
    })
  }, [categories, search, statusFilter])

  const stats = useMemo(() => {
    const totalKeywords = categories.reduce((sum, category) => sum + category.keywordsCount, 0)
    const averageSla = categories.length
      ? Math.round(categories.reduce((sum, category) => sum + Number(category.slaHours || 0), 0) / categories.length)
      : 0
    return {
      total: categories.length,
      active: categories.filter((category) => category.isActive).length,
      keywords: totalKeywords,
      averageSla,
    }
  }, [categories])

  function showNotification(message) {
    setNotification(message)
    window.setTimeout(() => setNotification(''), 2800)
  }

  function showError(caughtError) {
    const message = caughtError.message || 'Something went wrong. Please try again.'
    setError(message)
    showNotification(message)
  }

  function openModal(type, category = null) {
    setActionCategoryId(null)
    setSelectedCategory(category)
    setModal(type)
  }

  function closeModal() {
    setModal(null)
    setSelectedCategory(null)
  }

  async function createCategoryFromForm(values) {
    setIsSubmitting(true)
    setError('')

    try {
      await createCategory(toCategoryPayload(values))
      closeModal()
      showNotification('Category created successfully.')
      await loadCategories()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function updateCategoryFromForm(values) {
    setIsSubmitting(true)
    setError('')

    try {
      await updateCategory(selectedCategory.id, {
        ...toCategoryPayload(values),
        is_active: selectedCategory.isActive,
      })
      closeModal()
      showNotification('Category updated successfully.')
      await loadCategories()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function setCategoryActive(category, isActive) {
    setIsSubmitting(true)
    setError('')

    try {
      if (isActive) {
        await activateCategory(category.id)
      } else {
        await deactivateCategory(category.id)
      }
      closeModal()
      showNotification(isActive ? 'Category activated successfully.' : 'Category deactivated successfully.')
      await loadCategories()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function removeCategory() {
    setIsSubmitting(true)
    setError('')

    try {
      await deleteCategory(selectedCategory.id)
      closeModal()
      showNotification('Category deleted successfully.')
      await loadCategories()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function viewCategory(category) {
    setActionCategoryId(null)
    setError('')

    try {
      const response = await fetchCategory(category.id)
      setSelectedCategory(normalizeCategory(response))
    } catch (caughtError) {
      showError(caughtError)
    }
  }

  function resetFilters() {
    setSearch('')
    setStatusFilter('All')
  }

  return (
    <AppLayout activePage="Categories" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page">
        <div className="page-header">
          <div>
            <h1>Categories</h1>
            <p>Manage conversation categories and keyword rules</p>
          </div>
          {canManage ? (
            <button className="primary-button compact" type="button" onClick={() => openModal('create')}>
              <Icon name="plus" />
              Create Category
            </button>
          ) : null}
        </div>

        <section className="stats-grid" aria-label="Category summary">
          <StatCard label="Total Categories" value={stats.total} />
          <StatCard label="Active Categories" value={stats.active} />
          <StatCard label="Total Keywords" value={stats.keywords} />
          <StatCard label="Average SLA Hours" value={stats.averageSla} />
        </section>

        <section className="filter-panel category-filter-panel" aria-label="Category filters">
          <label className="field search-field">
            <span>Search</span>
            <input
              type="search"
              placeholder="Search by category, description, or keyword"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>

          <label className="field">
            <span>Status</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option>All</option>
              <option>Active</option>
              <option>Inactive</option>
            </select>
          </label>

          <button className="secondary-button" type="button" onClick={resetFilters}>
            Reset Filters
          </button>
        </section>

        {error ? (
          <p className="form-message error management-error" role="alert">
            {error}
          </p>
        ) : null}

        <section className="table-card" aria-label="Categories table">
          {isLoading ? (
            <div className="empty-state">
              <h2>Loading categories...</h2>
            </div>
          ) : filteredCategories.length ? (
            <div className="table-scroll">
              <table className="users-table categories-table">
                <thead>
                  <tr>
                    <th>Category Name</th>
                    <th>Description</th>
                    <th>SLA Hours</th>
                    <th>Keywords Count</th>
                    <th>Status</th>
                    <th>Created Date</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCategories.map((category) => (
                    <tr key={category.id}>
                      <td>
                        <span className="category-name-cell">
                          <span className="category-color" style={{ backgroundColor: category.color }} />
                          <strong>{category.name}</strong>
                        </span>
                      </td>
                      <td className="description-cell">{category.description || 'No description'}</td>
                      <td>{category.slaHours}</td>
                      <td>{category.keywordsCount}</td>
                      <td>
                        <Badge value={category.status} />
                      </td>
                      <td>{category.createdDate}</td>
                      <td className="actions-cell">
                        <button
                          className="icon-button"
                          type="button"
                          onClick={() =>
                            setActionCategoryId((current) => (current === category.id ? null : category.id))
                          }
                          aria-label={`Open actions for ${category.name}`}
                        >
                          <Icon name="dots" />
                        </button>
                        {actionCategoryId === category.id ? (
                          <div className="action-menu">
                            <button className="menu-view" type="button" onClick={() => viewCategory(category)}>
                              <Icon name="eye" />
                              View
                            </button>
                            {canManage ? (
                              <>
                                <button className="menu-edit" type="button" onClick={() => openModal('edit', category)}>
                                  <Icon name="edit" />
                                  Edit
                                </button>
                                {category.isActive ? (
                                  <button
                                    className="menu-disable"
                                    type="button"
                                    onClick={() => openModal('deactivate', category)}
                                    disabled={isSubmitting}
                                  >
                                    <Icon name="disable" />
                                    Deactivate
                                  </button>
                                ) : (
                                  <button
                                    className="menu-activate"
                                    type="button"
                                    onClick={() => setCategoryActive(category, true)}
                                    disabled={isSubmitting}
                                  >
                                    <Icon name="activate" />
                                    Activate
                                  </button>
                                )}
                                <button
                                  className="menu-disable"
                                  type="button"
                                  onClick={() => openModal('delete', category)}
                                >
                                  <Icon name="disable" />
                                  Delete
                                </button>
                              </>
                            ) : null}
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              <h2>No categories found</h2>
              {canManage ? (
                <button className="primary-button compact" type="button" onClick={() => openModal('create')}>
                  Create Category
                </button>
              ) : null}
            </div>
          )}
        </section>
      </main>

      {notification ? <div className="toast">{notification}</div> : null}

      {modal === 'create' ? (
        <Modal title="Create Category" onClose={closeModal}>
          <CategoryForm
            initialValues={EMPTY_FORM}
            categories={categories}
            selectedCategory={null}
            isSubmitting={isSubmitting}
            submitLabel="Create Category"
            onCancel={closeModal}
            onSubmit={createCategoryFromForm}
          />
        </Modal>
      ) : null}

      {modal === 'edit' && selectedCategory ? (
        <Modal title="Edit Category" onClose={closeModal}>
          <CategoryForm
            initialValues={{
              name: selectedCategory.name,
              description: selectedCategory.description,
              color: selectedCategory.color,
              slaHours: String(selectedCategory.slaHours),
              keywords: selectedCategory.keywordLabels,
            }}
            categories={categories}
            selectedCategory={selectedCategory}
            isSubmitting={isSubmitting}
            submitLabel="Save Changes"
            onCancel={closeModal}
            onSubmit={updateCategoryFromForm}
          />
        </Modal>
      ) : null}

      {modal === 'deactivate' && selectedCategory ? (
        <ConfirmModal
          title="Deactivate Category"
          message={`Deactivate ${selectedCategory.name}? Future conversations will not match this category until it is active again.`}
          actionLabel="Deactivate"
          danger
          isSubmitting={isSubmitting}
          onCancel={closeModal}
          onConfirm={() => setCategoryActive(selectedCategory, false)}
        />
      ) : null}

      {modal === 'delete' && selectedCategory ? (
        <ConfirmModal
          title="Delete Category"
          message={`Delete ${selectedCategory.name}? This also removes its keyword rules.`}
          actionLabel="Delete"
          danger
          isSubmitting={isSubmitting}
          onCancel={closeModal}
          onConfirm={removeCategory}
        />
      ) : null}

      <CategoryDrawer
        category={selectedCategory && !modal ? selectedCategory : null}
        onClose={() => setSelectedCategory(null)}
      />
    </AppLayout>
  )
}

export default Categories
