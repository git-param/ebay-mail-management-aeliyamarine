import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../layouts/app_layout'
import { createTemplate, deleteTemplate, fetchTemplates, updateTemplate } from '../services/templateApi'

const EMPTY_FORM = {
  title: '',
  body: '',
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
    isActive: template.is_active !== false,
    status: template.is_active === false ? 'Inactive' : 'Active',
    createdDate: formatDate(template.created_at),
    updatedDate: formatDate(template.updated_at),
  }
}

function toPayload(values) {
  return {
    title: values.title.trim(),
    body: values.body.trim(),
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

function TemplateForm({ initialValues, templates, selectedTemplate, isSubmitting, submitLabel, onCancel, onSubmit }) {
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
  const [templates, setTemplates] = useState([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('All')
  const [actionTemplateId, setActionTemplateId] = useState(null)
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [modal, setModal] = useState(null)
  const [notification, setNotification] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function loadTemplates() {
    setIsLoading(true)
    setError('')

    try {
      const response = await fetchTemplates({ includeInactive: true })
      setTemplates(getList(response).map(normalizeTemplate))
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
        !query || template.title.toLowerCase().includes(query) || template.body.toLowerCase().includes(query)
      const matchesStatus = statusFilter === 'All' || template.status === statusFilter
      return matchesSearch && matchesStatus
    })
  }, [search, statusFilter, templates])

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
      averageLength,
    }
  }, [templates])

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
    setSelectedTemplate(template)
    setModal(type)
  }

  function closeModal() {
    setModal(null)
    setSelectedTemplate(null)
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

  function resetFilters() {
    setSearch('')
    setStatusFilter('All')
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
          <StatCard label="Avg. Characters" value={stats.averageLength} />
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

          <button className="secondary-button" type="button" onClick={resetFilters}>
            Reset Filters
          </button>
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
                          <strong>{template.title}</strong>
                        </span>
                      </td>
                      <td className="template-preview-cell">{template.body}</td>
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
                            <button className="menu-disable" type="button" onClick={() => openModal('delete', template)}>
                              <Icon name="disable" />
                              Delete
                            </button>
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
              isActive: selectedTemplate.isActive,
            }}
            templates={templates}
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

      <TemplateDrawer
        template={selectedTemplate && !modal ? selectedTemplate : null}
        onClose={() => setSelectedTemplate(null)}
      />
    </AppLayout>
  )
}

export default Templates
