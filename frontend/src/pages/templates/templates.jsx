import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import {
  createTemplate,
  createTemplateCategory,
  deleteTemplate,
  deleteTemplateCategory,
  fetchTemplateCategories,
  fetchTemplates,
  updateTemplate,
  updateTemplateCategory,
} from '../../services/templateApi'
import { normalizeRole } from '../../utils/roles'

import './templates.css'

const EMPTY_FORM = {
  title: '',
  body: '',
  categoryId: '',
  isActive: true,
}

const EMPTY_CATEGORY_FORM = {
  name: '',
  description: '',
  isActive: true,
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

function getList(response) {
  if (Array.isArray(response)) {
    return response
  }

  return response.items || response.data || response.templates || []
}

function normalizeText(value) {
  return String(value || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

function normalizeTemplate(template) {
  return {
    ...template,
    id: template.id,
    title: template.title || '',
    body: template.body || '',
    categoryId: template.category_id || '',
    categoryName: template.category?.name || 'Uncategorized',
    isActive: template.is_active !== false,
    status: template.is_active === false ? 'Inactive' : 'Active',
    createdDate: formatDate(template.created_at),
    updatedDate: formatDate(template.updated_at),
  }
}

function normalizeCategory(category) {
  return {
    ...category,
    id: category.id,
    name: category.name || '',
    description: category.description || '',
    isActive: category.is_active !== false,
    status: category.is_active === false ? 'Inactive' : 'Active',
    createdDate: formatDate(category.created_at),
    updatedDate: formatDate(category.updated_at),
  }
}

function toPayload(values) {
  return {
    title: values.title.trim(),
    body: values.body.trim(),
    category_id: values.categoryId || null,
    is_active: Boolean(values.isActive),
  }
}

function toCategoryPayload(values) {
  return {
    name: values.name.trim(),
    description: values.description.trim() || null,
    is_active: Boolean(values.isActive),
  }
}

function StatCard({ label, value }) {
  return (
    <article className="stat-card">
      <span className="stat-icon">
        <Icon name="message" />
      </span>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </article>
  )
}

function Badge({ value }) {
  return <span className={`status-badge status-${value.toLowerCase()}`}>{value}</span>
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

function TemplateForm({ initialValues, templates, categories, selectedTemplate, isSubmitting, submitLabel, onCancel, onSubmit }) {
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState({})

  function updateField(event) {
    const { checked, name, type, value } = event.target
    setValues((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
  }

  function handleSubmit(event) {
    event.preventDefault()
    const nextErrors = {}
    const title = values.title.trim()
    const body = values.body.trim()

    if (!title) {
      nextErrors.title = 'Template title is required.'
    } else if (title.length > 160) {
      nextErrors.title = 'Template title must be 160 characters or less.'
    } else {
      const duplicateTitle = templates.some((template) => {
        return template.id !== selectedTemplate?.id && normalizeText(template.title) === normalizeText(title)
      })
      if (duplicateTitle) {
        nextErrors.title = 'A template with this title already exists.'
      }
    }

    if (!body) {
      nextErrors.body = 'Template body is required.'
    } else if (body.length > 5000) {
      nextErrors.body = 'Template body must be 5000 characters or less.'
    }

    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) {
      return
    }

    onSubmit(values)
  }

  return (
    <form className="management-form template-form" onSubmit={handleSubmit}>
      <label className="field form-field-wide">
        <span>Template Title</span>
        <input name="title" value={values.title} onChange={updateField} maxLength={160} />
        {errors.title ? <small>{errors.title}</small> : null}
      </label>

      <label className="field form-field-wide">
        <span>Message Body</span>
        <textarea
          name="body"
          value={values.body}
          onChange={updateField}
          rows="8"
          maxLength={5000}
          placeholder="Write the reusable reply text agents can insert into conversations"
        />
        {errors.body ? <small>{errors.body}</small> : null}
      </label>

      <label className="field form-field-wide">
        <span>Category</span>
        <select name="categoryId" value={values.categoryId} onChange={updateField}>
          <option value="">Uncategorized</option>
          {categories.map((category) => (
            <option value={category.id} key={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </label>

      <label className="template-toggle">
        <input name="isActive" type="checkbox" checked={values.isActive} onChange={updateField} />
        <span>
          <strong>Active template</strong>
          <small>Active templates are available inside the reply composer.</small>
        </span>
      </label>

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

function CategoryForm({ initialValues, categories, selectedCategory, isSubmitting, submitLabel, onCancel, onSubmit }) {
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState({})

  function updateField(event) {
    const { checked, name, type, value } = event.target
    setValues((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
  }

  function handleSubmit(event) {
    event.preventDefault()
    const nextErrors = {}
    const name = values.name.trim()

    if (!name) {
      nextErrors.name = 'Category name is required.'
    } else if (name.length > 160) {
      nextErrors.name = 'Category name must be 160 characters or less.'
    } else {
      const duplicateName = categories.some((category) => {
        return category.id !== selectedCategory?.id && normalizeText(category.name) === normalizeText(name)
      })
      if (duplicateName) {
        nextErrors.name = 'A category with this name already exists.'
      }
    }

    if (values.description.trim().length > 500) {
      nextErrors.description = 'Description must be 500 characters or less.'
    }

    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return

    onSubmit(values)
  }

  return (
    <form className="management-form template-form" onSubmit={handleSubmit}>
      <label className="field form-field-wide">
        <span>Category Name</span>
        <input name="name" value={values.name} onChange={updateField} maxLength={160} />
        {errors.name ? <small>{errors.name}</small> : null}
      </label>

      <label className="field form-field-wide">
        <span>Description</span>
        <textarea name="description" value={values.description} onChange={updateField} rows="4" maxLength={500} />
        {errors.description ? <small>{errors.description}</small> : null}
      </label>

      <label className="template-toggle">
        <input name="isActive" type="checkbox" checked={values.isActive} onChange={updateField} />
        <span>
          <strong>Active category</strong>
          <small>Active categories are available when creating and choosing templates.</small>
        </span>
      </label>

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

function ConfirmModal({ template, isSubmitting, onCancel, onConfirm }) {
  return (
    <Modal title="Delete Template" onClose={onCancel}>
      <p className="confirm-message">
        Delete {template.title}? Agents will no longer be able to use this reply template.
      </p>
      <div className="modal-actions">
        <button className="secondary-button" type="button" onClick={onCancel}>
          Cancel
        </button>
        <button className="danger-button" type="button" onClick={onConfirm} disabled={isSubmitting}>
          {isSubmitting ? 'Deleting...' : 'Delete'}
        </button>
      </div>
    </Modal>
  )
}

function ConfirmCategoryModal({ category, isSubmitting, onCancel, onConfirm }) {
  return (
    <Modal title="Delete Category" onClose={onCancel}>
      <p className="confirm-message">
        Delete {category.name}? Templates in this category will become uncategorized.
      </p>
      <div className="modal-actions">
        <button className="secondary-button" type="button" onClick={onCancel}>
          Cancel
        </button>
        <button className="danger-button" type="button" onClick={onConfirm} disabled={isSubmitting}>
          {isSubmitting ? 'Deleting...' : 'Delete'}
        </button>
      </div>
    </Modal>
  )
}

function TemplateDrawer({ template, onClose }) {
  if (!template) {
    return null
  }

  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="user-drawer" aria-labelledby="template-drawer-title">
        <div className="drawer-header">
          <h2 id="template-drawer-title">Template Preview</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close details">
            <Icon name="close" />
          </button>
        </div>

        <div className="drawer-profile template-drawer-profile">
          <span className="template-avatar">
            <Icon name="message" />
          </span>
          <h3>{template.title}</h3>
          <div className="badge-row">
            <Badge value={template.status} />
            <span className="category-pill">{template.categoryName}</span>
          </div>
        </div>

        <section className="drawer-section">
          <h3>Reply Text</h3>
          <p className="template-preview-body">{template.body}</p>
        </section>

        <dl className="detail-grid">
          <div>
            <dt>Created</dt>
            <dd>{template.createdDate}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{template.updatedDate}</dd>
          </div>
        </dl>
      </aside>
    </div>
  )
}

function Templates({ currentUser, onLogout }) {
  const canDeleteTemplates = normalizeRole(currentUser?.role) !== 'AGENT'
  const [templates, setTemplates] = useState([])
  const [categories, setCategories] = useState([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('All')
  const [categoryFilter, setCategoryFilter] = useState('All')
  const [actionTemplateId, setActionTemplateId] = useState(null)
  const [actionCategoryId, setActionCategoryId] = useState(null)
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [modal, setModal] = useState(null)
  const [notification, setNotification] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function loadTemplates() {
    setIsLoading(true)
    setError('')

    try {
      const [templateResponse, categoryResponse] = await Promise.all([
        fetchTemplates({ includeInactive: true }),
        fetchTemplateCategories({ includeInactive: true }),
      ])
      setTemplates(getList(templateResponse).map(normalizeTemplate))
      setCategories(getList(categoryResponse).map(normalizeCategory))
    } catch (caughtError) {
      setError(caughtError.message)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadTemplates()
  }, [])

  const filteredTemplates = useMemo(() => {
    return templates.filter((template) => {
      const query = search.trim().toLowerCase()
      const matchesSearch =
        !query ||
        template.title.toLowerCase().includes(query) ||
        template.body.toLowerCase().includes(query) ||
        template.categoryName.toLowerCase().includes(query)
      const matchesStatus = statusFilter === 'All' || template.status === statusFilter
      const matchesCategory =
        categoryFilter === 'All' ||
        (categoryFilter === 'Uncategorized' && !template.categoryId) ||
        template.categoryId === categoryFilter
      return matchesSearch && matchesStatus && matchesCategory
    })
  }, [categoryFilter, search, statusFilter, templates])

  const stats = useMemo(() => {
    const active = templates.filter((template) => template.isActive).length
    const inactive = templates.length - active
    const averageLength = templates.length
      ? Math.round(templates.reduce((sum, template) => sum + template.body.length, 0) / templates.length)
      : 0

    return {
      total: templates.length,
      active,
      inactive,
      categories: categories.length,
      averageLength,
    }
  }, [categories.length, templates])

  function showNotification(message) {
    setNotification(message)
    window.setTimeout(() => setNotification(''), 2800)
  }

  function showError(caughtError) {
    const message = caughtError.message || 'Something went wrong. Please try again.'
    setError(message)
    showNotification(message)
  }

  function openModal(type, template = null) {
    setActionTemplateId(null)
    setActionCategoryId(null)
    setSelectedTemplate(template)
    setSelectedCategory(template)
    setModal(type)
  }

  function closeModal() {
    setModal(null)
    setSelectedTemplate(null)
    setSelectedCategory(null)
  }

  async function createTemplateFromForm(values) {
    setIsSubmitting(true)
    setError('')

    try {
      await createTemplate(toPayload(values))
      closeModal()
      showNotification('Template created successfully.')
      await loadTemplates()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function updateTemplateFromForm(values) {
    setIsSubmitting(true)
    setError('')

    try {
      await updateTemplate(selectedTemplate.id, toPayload(values))
      closeModal()
      showNotification('Template updated successfully.')
      await loadTemplates()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function removeTemplate() {
    setIsSubmitting(true)
    setError('')

    try {
      await deleteTemplate(selectedTemplate.id)
      closeModal()
      showNotification('Template deleted successfully.')
      await loadTemplates()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function createCategoryFromForm(values) {
    setIsSubmitting(true)
    setError('')

    try {
      await createTemplateCategory(toCategoryPayload(values))
      closeModal()
      showNotification('Category created successfully.')
      await loadTemplates()
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
      await updateTemplateCategory(selectedCategory.id, toCategoryPayload(values))
      closeModal()
      showNotification('Category updated successfully.')
      await loadTemplates()
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
      await deleteTemplateCategory(selectedCategory.id)
      closeModal()
      showNotification('Category deleted successfully.')
      await loadTemplates()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  function resetFilters() {
    setSearch('')
    setStatusFilter('All')
    setCategoryFilter('All')
  }

  return (
    <AppLayout activePage="Templates" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page templates-page">
        <div className="page-header">
          <div>
            <h1>Templates</h1>
            <p>Create reusable replies for faster, consistent buyer messages</p>
          </div>
          <button className="primary-button compact" type="button" onClick={() => openModal('create')}>
            <Icon name="plus" />
            Create Template
          </button>
        </div>

        <section className="stats-grid" aria-label="Template summary">
          <StatCard label="Total Templates" value={stats.total} />
          <StatCard label="Active Templates" value={stats.active} />
          <StatCard label="Inactive Templates" value={stats.inactive} />
          <StatCard label="Categories" value={stats.categories} />
        </section>

        <section className="filter-panel template-filter-panel" aria-label="Template filters">
          <label className="field search-field">
            <span>Search</span>
            <input
              type="search"
              placeholder="Search by title or message text"
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

          <label className="field">
            <span>Category</span>
            <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
              <option>All</option>
              <option>Uncategorized</option>
              {categories.map((category) => (
                <option value={category.id} key={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>

          <button className="secondary-button" type="button" onClick={resetFilters}>
            Reset Filters
          </button>
        </section>

        <section className="category-management-panel" aria-label="Template categories">
          <div className="section-heading-row">
            <div>
              <h2>Template Categories</h2>
              <p>Group reply templates for faster selection in the inbox.</p>
            </div>
            <button className="secondary-button compact" type="button" onClick={() => openModal('create-category')}>
              <Icon name="plus" />
              Create Category
            </button>
          </div>
          {categories.length ? (
            <div className="category-chip-grid">
              {categories.map((category) => (
                <span className="category-management-chip" key={category.id}>
                  <span>
                    <strong>{category.name}</strong>
                    <small>{category.status}</small>
                  </span>
                  <button
                    className="icon-button"
                    type="button"
                    onClick={() => setActionCategoryId((current) => (current === category.id ? null : category.id))}
                    aria-label={`Open actions for ${category.name}`}
                  >
                    <Icon name="dots" />
                  </button>
                  {actionCategoryId === category.id ? (
                    <div className="action-menu category-action-menu">
                      <button className="menu-edit" type="button" onClick={() => openModal('edit-category', category)}>
                        <Icon name="edit" />
                        Edit
                      </button>
                      {canDeleteTemplates ? (
                        <button className="menu-disable" type="button" onClick={() => openModal('delete-category', category)}>
                          <Icon name="disable" />
                          Delete
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </span>
              ))}
            </div>
          ) : (
            <p className="category-empty-text">No categories yet. Templates can still be left uncategorized.</p>
          )}
        </section>

        {error ? (
          <p className="form-message error management-error" role="alert">
            {error}
          </p>
        ) : null}

        <section className="table-card" aria-label="Templates table">
          {isLoading ? (
            <div className="empty-state">
              <h2>Loading templates...</h2>
            </div>
          ) : filteredTemplates.length ? (
            <div className="table-scroll">
              <table className="users-table templates-table">
                <thead>
                  <tr>
                    <th>Template</th>
                    <th>Category</th>
                    <th>Preview</th>
                    <th>Status</th>
                    <th>Updated</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTemplates.map((template) => (
                    <tr key={template.id}>
                      <td>
                        <span className="template-name-cell">
                          <span className="template-avatar small">
                            <Icon name="message" />
                          </span>
                          <strong title={template.title}>{template.title}</strong>
                        </span>
                      </td>
                      <td>
                        <span className="category-pill" title={template.categoryName}>{template.categoryName}</span>
                      </td>
                      <td className="template-preview-cell" title={template.body}>{template.body}</td>
                      <td>
                        <Badge value={template.status} />
                      </td>
                      <td>{template.updatedDate}</td>
                      <td className="actions-cell">
                        <button
                          className="icon-button"
                          type="button"
                          onClick={() =>
                            setActionTemplateId((current) => (current === template.id ? null : template.id))
                          }
                          aria-label={`Open actions for ${template.title}`}
                        >
                          <Icon name="dots" />
                        </button>
                        {actionTemplateId === template.id ? (
                          <div className="action-menu">
                            <button className="menu-view" type="button" onClick={() => setSelectedTemplate(template)}>
                              <Icon name="eye" />
                              View
                            </button>
                            <button className="menu-edit" type="button" onClick={() => openModal('edit', template)}>
                              <Icon name="edit" />
                              Edit
                            </button>
                            {canDeleteTemplates ? (
                              <button className="menu-disable" type="button" onClick={() => openModal('delete', template)}>
                                <Icon name="disable" />
                                Delete
                              </button>
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
              <h2>No templates found</h2>
              <button className="primary-button compact" type="button" onClick={() => openModal('create')}>
                Create Template
              </button>
            </div>
          )}
        </section>
      </main>

      {notification ? <div className="toast">{notification}</div> : null}

      {modal === 'create' ? (
        <Modal title="Create Template" onClose={closeModal}>
          <TemplateForm
            initialValues={EMPTY_FORM}
            templates={templates}
            categories={categories.filter((category) => category.isActive)}
            selectedTemplate={null}
            isSubmitting={isSubmitting}
            submitLabel="Create Template"
            onCancel={closeModal}
            onSubmit={createTemplateFromForm}
          />
        </Modal>
      ) : null}

      {modal === 'edit' && selectedTemplate ? (
        <Modal title="Edit Template" onClose={closeModal}>
          <TemplateForm
            initialValues={{
              title: selectedTemplate.title,
              body: selectedTemplate.body,
              categoryId: selectedTemplate.categoryId,
              isActive: selectedTemplate.isActive,
            }}
            templates={templates}
            categories={categories.filter((category) => category.isActive || category.id === selectedTemplate.categoryId)}
            selectedTemplate={selectedTemplate}
            isSubmitting={isSubmitting}
            submitLabel="Save Changes"
            onCancel={closeModal}
            onSubmit={updateTemplateFromForm}
          />
        </Modal>
      ) : null}

      {modal === 'delete' && selectedTemplate ? (
        <ConfirmModal
          template={selectedTemplate}
          isSubmitting={isSubmitting}
          onCancel={closeModal}
          onConfirm={removeTemplate}
        />
      ) : null}

      {modal === 'create-category' ? (
        <Modal title="Create Category" onClose={closeModal}>
          <CategoryForm
            initialValues={EMPTY_CATEGORY_FORM}
            categories={categories}
            selectedCategory={null}
            isSubmitting={isSubmitting}
            submitLabel="Create Category"
            onCancel={closeModal}
            onSubmit={createCategoryFromForm}
          />
        </Modal>
      ) : null}

      {modal === 'edit-category' && selectedCategory ? (
        <Modal title="Edit Category" onClose={closeModal}>
          <CategoryForm
            initialValues={{
              name: selectedCategory.name,
              description: selectedCategory.description,
              isActive: selectedCategory.isActive,
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

      {modal === 'delete-category' && selectedCategory ? (
        <ConfirmCategoryModal
          category={selectedCategory}
          isSubmitting={isSubmitting}
          onCancel={closeModal}
          onConfirm={removeCategory}
        />
      ) : null}

      <TemplateDrawer
        template={selectedTemplate && !modal ? selectedTemplate : null}
        onClose={() => setSelectedTemplate(null)}
      />
    </AppLayout>
  )
}

export default Templates
