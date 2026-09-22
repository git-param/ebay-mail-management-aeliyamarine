import {
  useEffect,
  useRef,
  useState,
} from 'react'

import { Icon } from '../../../layouts/app_layout'
import BulkAssignBar from './BulkAssignBar'
import ConversationRow from './ConversationRow'
import InboxPagination from './InboxPagination'

import './conversationList.css'

const SEARCH_BY_OPTIONS = [
  ['buyer_name', 'Buyer name'],
  ['item_number', 'Item number'],
  ['order_id', 'Order ID'],
  ['message_content', 'Text message content'],
  ['sku', 'SKU'],
  ['everything', 'Everything'],
]

const SEARCH_PLACEHOLDERS = {
  '': 'Enter a keyword to search',
  buyer_name: 'Search buyer name',
  item_number: 'Search item number',
  order_id: 'Search order ID',
  message_content: 'Search text message content',
  sku: 'Search SKU',
  everything: 'Search buyer, item, order, SKU, or message',
}

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
  error,
  search,
  searchBy,
  activeFilterCount = 0,
  nearDueActive = false,
  unreadActive = false,
  breakAction = null,
  onSearch,
  onSearchByChange,
  onToggleNearDue,
  onToggleUnread,
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
  const [isSearchByOpen, setIsSearchByOpen] =
    useState(false)
  const searchByRef = useRef(null)

  const selectedSearchOption =
    SEARCH_BY_OPTIONS.find(
      ([value]) => value === searchBy,
    )

  useEffect(() => {
    setSearchInput(search || '')
  }, [search])

  useEffect(() => {
    function closeSearchBy(event) {
      if (
        !searchByRef.current?.contains(
          event.target,
        )
      ) {
        setIsSearchByOpen(false)
      }
    }

    function closeSearchByOnEscape(event) {
      if (event.key === 'Escape') {
        setIsSearchByOpen(false)
      }
    }

    document.addEventListener(
      'mousedown',
      closeSearchBy,
    )
    document.addEventListener(
      'keydown',
      closeSearchByOnEscape,
    )

    return () => {
      document.removeEventListener(
        'mousedown',
        closeSearchBy,
      )
      document.removeEventListener(
        'keydown',
        closeSearchByOnEscape,
      )
    }
  }, [])

  const selectedCount =
    selectedConversationIds?.size || 0

  function submitSearch(event) {
    event.preventDefault()

    if (!searchBy || !searchInput.trim()) {
      return
    }

    onSearch(searchInput, searchBy)
  }

  function clearSearch() {
    setSearchInput('')
    onSearch('', searchBy)
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
            className={`secondary-button compact-action near-due-button${unreadActive ? ' active' : ''}`}
            type="button"
            onClick={onToggleUnread}
            disabled={isLoading}
            aria-pressed={unreadActive}
          >
            <Icon name="message" />
            <span>Unread Conversations</span>
          </button>
          <button
            className={`secondary-button compact-action near-due-button${nearDueActive ? ' active' : ''}`}
            type="button"
            onClick={() => {
              if (onToggleNearDue) {
                onToggleNearDue()
              }
            }}
            disabled={isLoading}
            aria-pressed={nearDueActive}
            title="Show conversations with 2 hours or less of SLA time remaining"
          >
            <Icon name="clock" />
            <span>Near Due SLA</span>
            <span className="near-due-window">2h</span>
          </button>

          {breakAction}

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
        <div
          className="inbox-search-by"
          ref={searchByRef}
        >
          <button
            className={`inbox-search-by-trigger${isSearchByOpen ? ' open' : ''}${searchBy ? ' selected' : ''}`}
            type="button"
            aria-haspopup="listbox"
            aria-expanded={isSearchByOpen}
            onClick={() =>
              setIsSearchByOpen(
                (current) => !current,
              )
            }
          >
            <span>
              {selectedSearchOption?.[1] ||
                'Search by'}
            </span>
            <Icon name="chevron" />
          </button>

          {isSearchByOpen ? (
            <div
              className="inbox-search-by-menu"
              role="listbox"
              aria-label="Search by"
            >
              {SEARCH_BY_OPTIONS.map(
                ([value, label]) => (
                  <button
                    className={
                      value === searchBy
                        ? 'selected'
                        : ''
                    }
                    type="button"
                    role="option"
                    aria-selected={
                      value === searchBy
                    }
                    value={value}
                    key={value}
                    onClick={() => {
                      onSearchByChange(value)
                      setIsSearchByOpen(false)
                    }}
                >
                    <span>{label}</span>
                    {value === searchBy ? (
                      <Icon name="activate" />
                    ) : null}
                  </button>
                ),
              )}
            </div>
          ) : null}
        </div>

        <div className="inbox-search-input">
          <Icon name="search" />

          <input
            type="text"
            value={searchInput}
            placeholder={
              SEARCH_PLACEHOLDERS[
                searchBy
              ]
            }
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
          disabled={
            !searchBy ||
            !searchInput.trim()
          }
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
          {error ? (
            <EmptyPanel
              title="Unable to load conversations"
              message={error}
            />
          ) : null}

          {isLoading &&
          !conversations.length &&
          !error ? (
            <EmptyPanel
              title="Loading conversations..."
              message="Please wait while the inbox is refreshed."
            />
          ) : null}

          {!isLoading &&
          !conversations.length &&
          !error ? (
            <EmptyPanel
              title="No conversations found"
              message="Try changing your search or inbox filters."
            />
          ) : null}

          {!error ? conversations.map(
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
          ) : null}
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
