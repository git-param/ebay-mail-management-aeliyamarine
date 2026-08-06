import { useEffect, useState } from 'react'

import { Icon } from '../../../layouts/app_layout'
import { normalizeRole } from '../../../utils/roles'
import {
  PERIOD_OPTIONS,
  STATUSES,
  periodRange,
} from '../inboxUtils'

function FilterSelect({
  label,
  value,
  onChange,
  children,
}) {
  return (
    <label className="field">
      <span>{label}</span>

      <select
        value={value || ''}
        onChange={(event) =>
          onChange(event.target.value)
        }
      >
        {children}
      </select>
    </label>
  )
}

function InboxFiltersDrawer({
  isOpen,
  filters,
  users,
  categories,
  accounts,
  currentUser,
  onFilterChange,
  onSearchSubmit,
  onReset,
  onClose,
}) {
  const [searchInput, setSearchInput] = useState(
    filters.search || '',
  )

  useEffect(() => {
    setSearchInput(filters.search || '')
  }, [filters.search])

  useEffect(() => {
    if (!isOpen) {
      return undefined
    }

    function handleEscape(event) {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener(
      'keydown',
      handleEscape,
    )

    return () => {
      document.removeEventListener(
        'keydown',
        handleEscape,
      )
    }
  }, [isOpen, onClose])

  if (!isOpen) {
    return null
  }

  const isAgent =
    normalizeRole(currentUser?.role) === 'AGENT'

  const assignmentUsers = isAgent
    ? users.filter(
        (user) => user.id === currentUser?.id,
      )
    : users

  const selectedPeriod =
    filters.period || 'all'

  const customPeriod =
    selectedPeriod === 'custom'

  function changePeriod(value) {
    const range =
      value === 'custom'
        ? {}
        : periodRange(value)

    onFilterChange({
      period: value,
      ...range,
    })
  }

  function submitFilters(event) {
    event.preventDefault()

    onSearchSubmit(searchInput)
    onClose()
  }

  function resetFilters() {
    setSearchInput('')
    onReset()
    onClose()
  }

  function closeOnBackdrop(event) {
    if (event.target === event.currentTarget) {
      onClose()
    }
  }

  return (
    <div
      className="filters-drawer-backdrop"
      role="presentation"
      onMouseDown={closeOnBackdrop}
    >
      <aside
        className="filters-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="filters-title"
      >
        <div className="drawer-header">
          <h2 id="filters-title">
            Filters
          </h2>

          <button
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label="Close filters"
          >
            <Icon name="close" />
          </button>
        </div>

        <form
          className="filters-form"
          onSubmit={submitFilters}
        >
          <label className="field">
            <span>Search</span>

            <input
              type="search"
              placeholder="Search buyer, subject, item, or message body"
              value={searchInput}
              onChange={(event) =>
                setSearchInput(
                  event.target.value,
                )
              }
            />
          </label>

          <FilterSelect
            label="Status"
            value={filters.status}
            onChange={(value) =>
              onFilterChange(
                'status',
                value,
              )
            }
          >
            <option value="">
              All statuses
            </option>

            {STATUSES.map((status) => (
              <option
                value={status}
                key={status}
              >
                {status}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect
            label="Period"
            value={selectedPeriod}
            onChange={changePeriod}
          >
            {PERIOD_OPTIONS.map(
              ([value, label]) => (
                <option
                  value={value}
                  key={value}
                >
                  {label}
                </option>
              ),
            )}
          </FilterSelect>

          {customPeriod ? (
            <>
              <label className="field">
                <span>From</span>

                <input
                  type="date"
                  value={
                    filters.date_from || ''
                  }
                  onChange={(event) =>
                    onFilterChange(
                      'date_from',
                      event.target.value,
                    )
                  }
                />
              </label>

              <label className="field">
                <span>To</span>

                <input
                  type="date"
                  value={
                    filters.date_to || ''
                  }
                  onChange={(event) =>
                    onFilterChange(
                      'date_to',
                      event.target.value,
                    )
                  }
                />
              </label>
            </>
          ) : null}

          <FilterSelect
            label="Conversation type"
            value={
              filters.conversation_type
            }
            onChange={(value) =>
              onFilterChange(
                'conversation_type',
                value,
              )
            }
          >
            <option value="">
              All conversation types
            </option>

            <option value="FROM_MEMBERS">
              From members
            </option>

            <option value="FROM_EBAY">
              From eBay
            </option>
          </FilterSelect>

          <FilterSelect
            label="eBay Account"
            value={
              filters.ebay_account_id
            }
            onChange={(value) =>
              onFilterChange(
                'ebay_account_id',
                value,
              )
            }
          >
            <option value="">
              All accounts
            </option>

            {accounts.map((account) => (
              <option
                value={account.id}
                key={account.id}
              >
                {account.label}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect
            label="Assigned User"
            value={
              filters.assigned_user_id
            }
            onChange={(value) =>
              onFilterChange(
                'assigned_user_id',
                value,
              )
            }
          >
            <option value="">
              Anyone
            </option>

            {assignmentUsers.map(
              (user) => (
                <option
                  value={user.id}
                  key={user.id}
                >
                  {user.fullName}
                </option>
              ),
            )}
          </FilterSelect>

          <FilterSelect
            label="Category"
            value={filters.category_id}
            onChange={(value) =>
              onFilterChange(
                'category_id',
                value,
              )
            }
          >
            <option value="">
              All categories
            </option>

            {categories.map(
              (category) => (
                <option
                  value={category.id}
                  key={category.id}
                >
                  {category.name}
                </option>
              ),
            )}
          </FilterSelect>

          <div className="modal-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={resetFilters}
            >
              Reset
            </button>

            <button
              className="primary-button compact"
              type="submit"
            >
              Apply
            </button>
          </div>
        </form>
      </aside>
    </div>
  )
}

export { FilterSelect }
export default InboxFiltersDrawer