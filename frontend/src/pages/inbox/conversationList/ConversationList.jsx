import { useEffect, useState } from 'react'

import { Icon } from '../../../layouts/app_layout'
import BulkAssignBar from './BulkAssignBar'
import ConversationRow from './ConversationRow'
import InboxPagination from './InboxPagination'

import './conversationList.css'

function EmptyPanel({
  title,
  message,
}) {
  return (
    <div className="inbox-empty">
      <h2>{title}</h2>
      <p>{message}</p>
    </div>
  )
}

function ConversationList({
  conversations,
  total,
  page,
  pageCount,
  pageSize,
  selectedConversationId,
  selectedConversationIds,
  selectedBulkUserId,
  users,
  usersError,
  bulkAssignError,
  isLoading,
  isBulkAssigning,
  search,
  activeFilterCount = 0,
  onSearch,
  onRefresh,
  onOpenFilters,
  onSelectConversation,
  onToggleBulk,
  onBulkUserChange,
  onBulkAssign,
  onClearBulkSelection,
  onPageChange,
  onPageSizeChange,
}) {
  const [searchInput, setSearchInput] =
    useState(search || '')

  useEffect(() => {
    setSearchInput(search || '')
  }, [search])

  const selectedCount =
    selectedConversationIds?.size || 0

  function submitSearch(event) {
    event.preventDefault()
    onSearch(searchInput)
  }

  function clearSearch() {
    setSearchInput('')
    onSearch('')
  }

  return (
    <section className="inbox-list-panel">
      <header className="inbox-header">
        <div>
          <p className="inbox-kicker">
            Customer support
          </p>

          <h1>Inbox</h1>

          <p>
            {total || 0}{' '}
            conversation
            {Number(total) === 1
              ? ''
              : 's'}
          </p>
        </div>

        <div className="inbox-header-actions">
          <button
            className="secondary-button compact-action"
            type="button"
            onClick={onRefresh}
            disabled={isLoading}
          >
            <Icon name="refresh" />

            {isLoading
              ? 'Refreshing...'
              : 'Refresh'}
          </button>

          <button
            className="secondary-button compact-action"
            type="button"
            onClick={onOpenFilters}
          >
            <Icon name="filter" />

            Filters

            {activeFilterCount > 0 ? (
              <span className="filter-count">
                {activeFilterCount}
              </span>
            ) : null}
          </button>
        </div>
      </header>

      <form
        className="inbox-search-bar"
        onSubmit={submitSearch}
      >
        <div className="inbox-search-input">
          <Icon name="search" />

          <input
            type="search"
            value={searchInput}
            placeholder="Search buyer, subject, item, or message"
            onChange={(event) =>
              setSearchInput(
                event.target.value,
              )
            }
          />

          {searchInput ? (
            <button
              className="icon-button"
              type="button"
              onClick={clearSearch}
              aria-label="Clear search"
            >
              <Icon name="close" />
            </button>
          ) : null}
        </div>

        <button
          className="primary-button compact"
          type="submit"
        >
          Search
        </button>
      </form>

      <BulkAssignBar
        selectedCount={selectedCount}
        selectedUser={selectedBulkUserId}
        users={users}
        usersError={usersError}
        error={bulkAssignError}
        isSubmitting={isBulkAssigning}
        onUserChange={onBulkUserChange}
        onAssign={onBulkAssign}
        onClear={onClearBulkSelection}
      />

      <div className="conversation-table-scroll">
        <div className="conversation-table-head" aria-hidden="true">
          <span></span>
          <span>Customer</span>
          <span>Seller</span>
          <span>Message</span>
          <span>Category</span>
          <span>Messages</span>
          <span>SLA</span>
          <span>Last Update</span>
        </div>

        <div className="conversation-list">
          {isLoading &&
          !conversations.length ? (
            <EmptyPanel
              title="Loading conversations..."
              message="Please wait while the inbox is refreshed."
            />
          ) : null}

          {!isLoading &&
          !conversations.length ? (
            <EmptyPanel
              title="No conversations found"
              message="Try changing your search or inbox filters."
            />
          ) : null}

          {conversations.map(
            (conversation) => (
              <ConversationRow
                conversation={conversation}
                isSelected={
                  conversation.id ===
                  selectedConversationId
                }
                isBulkSelected={
                  selectedConversationIds?.has(
                    conversation.id,
                  ) || false
                }
                onSelect={
                  onSelectConversation
                }
                onToggleBulk={
                  onToggleBulk
                }
                key={conversation.id}
              />
            ),
          )}
        </div>
      </div>

      <InboxPagination
        page={page}
        pageCount={pageCount}
        pageSize={pageSize}
        total={total}
        onPageChange={onPageChange}
        onPageSizeChange={
          onPageSizeChange
        }
      />
    </section>
  )
}

export { EmptyPanel }
export default ConversationList