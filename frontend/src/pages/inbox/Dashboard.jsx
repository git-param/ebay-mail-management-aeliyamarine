import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'

import AppLayout from '../../layouts/app_layout'
import { fetchCategories } from '../../services/categoryApi'
import {
  assignConversation,
  bulkUpdateConversations,
  createConversationNote,
  fetchConversation,
  fetchConversationNotes,
  fetchConversations,
  sendConversationReply,
  sendConversationReplyWithAttachments,
  updateConversationCategory,
  updateConversationStatus,
} from '../../services/conversationApi'
import { fetchEbayAccounts } from '../../services/ebayAccountApi'
import { fetchMessageTypeTree } from '../../services/messageTypeApi'
import { fetchTemplates } from '../../services/templateApi'
import { fetchUsers } from '../../services/userApi'
import { normalizeRole } from '../../utils/roles'

import ConversationList from './conversationList/ConversationList'
import InboxFiltersDrawer from './conversationList/InboxFiltersDrawer'
import { EmptyPanel } from './conversationList/ConversationList'
import ConversationDetail from './conversationDetail/ConversationDetail'
import DetailsPanel from './conversationDetail/DetailsPanel'
import {
  DEFAULT_PAGE_SIZE,
  DETAILS_WIDTH_KEY,
  LIST_WIDTH_KEY,
  addOneDayToIsoDate,
  clamp,
  getConversationIdFromUrl,
  getList,
  getStoredNumber,
  normalizeAccount,
  normalizeCategory,
  normalizeUser,
  periodRange,
} from './inboxUtils'

import './dashboard.css'

const EMPTY_FILTERS = {
  search: '',
  status: '',
  period: 'all',
  ...periodRange('all'),
  conversation_type: '',
  ebay_account_id: '',
  assigned_user_id: '',
  category_id: '',
  sla_due_within_hours: '',
}

const LIST_PANE_OPEN_KEY =
  'inbox.listPaneOpen'

function Dashboard({
  currentUser,
  onLogout,
}) {
  const canManageAssignments = [
    'ADMIN',
    'OPS_MANAGER',
    'AGENT',
  ].includes(
    normalizeRole(currentUser?.role),
  )

  const [filters, setFilters] =
    useState(EMPTY_FILTERS)

  const [page, setPage] =
    useState(0)

  const [pageSize, setPageSize] =
    useState(DEFAULT_PAGE_SIZE)

  const [conversations, setConversations] =
    useState([])

  const [total, setTotal] =
    useState(0)

  const [
    selectedConversationId,
    setSelectedConversationId,
  ] = useState(getConversationIdFromUrl)

  const [
    bulkSelectedIds,
    setBulkSelectedIds,
  ] = useState(() => new Set())

  const [
    bulkAssignedUserId,
    setBulkAssignedUserId,
  ] = useState('')

  const [detail, setDetail] =
    useState(null)

  const [notes, setNotes] =
    useState([])

  const [users, setUsers] =
    useState([])

  const [categories, setCategories] =
    useState([])

  const [accounts, setAccounts] =
    useState([])

  const [templates, setTemplates] =
    useState([])

  const [messageTypes, setMessageTypes] =
    useState([])

  const [listWidth, setListWidth] =
    useState(() =>
      getStoredNumber(
        LIST_WIDTH_KEY,
        360,
      ),
    )

  const [detailsWidth, setDetailsWidth] =
    useState(() =>
      getStoredNumber(
        DETAILS_WIDTH_KEY,
        320,
      ),
    )

  const [
    isDetailsOpen,
    setIsDetailsOpen,
  ] = useState(true)

  const [
    isListPaneOpen,
    setIsListPaneOpen,
  ] = useState(
    () =>
      localStorage.getItem(
        LIST_PANE_OPEN_KEY,
      ) !== 'false',
  )

  const [
    isFiltersOpen,
    setIsFiltersOpen,
  ] = useState(false)

  const [mobilePane, setMobilePane] =
    useState('list')

  const [
    isListLoading,
    setIsListLoading,
  ] = useState(true)

  const [
    isDetailLoading,
    setIsDetailLoading,
  ] = useState(false)

  const [
    isNotesLoading,
    setIsNotesLoading,
  ] = useState(false)

  const [
    isSubmitting,
    setIsSubmitting,
  ] = useState(false)

  const [listError, setListError] =
    useState('')

  const [detailError, setDetailError] =
    useState('')

  const [actionError, setActionError] =
    useState('')

  const [usersError, setUsersError] =
    useState('')

  const offset = page * pageSize

  const pageCount = Math.max(
    1,
    Math.ceil(total / pageSize),
  )

  const hasSelectedConversation =
    Boolean(selectedConversationId)

  const selectedConversation =
    useMemo(
      () =>
        conversations.find(
          (conversation) =>
            conversation.id ===
            selectedConversationId,
        ),
      [
        conversations,
        selectedConversationId,
      ],
    )

  const visibleConversation =
    detail || selectedConversation

  const activeFilterCount =
    useMemo(() => {
      const excludedFields = new Set([
        'period',
        'date_from',
        'date_to',
        // Near Due SLA has its own visible toggle, so do not duplicate it
        // inside the generic Filters count badge.
        'sla_due_within_hours',
      ])

      let count = Object.entries(
        filters,
      ).filter(
        ([key, value]) =>
          !excludedFields.has(key) &&
          Boolean(value),
      ).length

      if (
        (filters.period || 'all') !==
        'all'
      ) {
        count += 1
      }

      return count
    }, [filters])

  const workspaceStyle =
    hasSelectedConversation
      ? {
          gridTemplateColumns:
            !isListPaneOpen
              ? isDetailsOpen &&
                visibleConversation
                ? `minmax(0, 1fr) 8px ${detailsWidth}px`
                : 'minmax(0, 1fr)'
              : isDetailsOpen &&
                visibleConversation
              ? `${listWidth}px 8px minmax(0, 1fr) 8px ${detailsWidth}px`
              : `${listWidth}px 8px minmax(0, 1fr)`,
        }
      : undefined

  const loadConversations =
    useCallback(async () => {
      setIsListLoading(true)
      setListError('')

      try {
        const {
          period,
          ...requestFilters
        } = filters

        if (
          period === 'custom' &&
          requestFilters.date_to
        ) {
          requestFilters.date_to =
            addOneDayToIsoDate(
              requestFilters.date_to,
            )
        }

        const response =
          await fetchConversations({
            limit: pageSize,
            offset,
            ...requestFilters,
          })

        setConversations(
          response.items || [],
        )

        setTotal(response.total || 0)
      } catch (caughtError) {
        setListError(
          caughtError.message ||
            'Unable to load conversations.',
        )

        setConversations([])
        setTotal(0)
      } finally {
        setIsListLoading(false)
      }
    }, [
      filters,
      offset,
      pageSize,
    ])

  const loadConversationDetail =
    useCallback(
      async (conversationId) => {
        if (!conversationId) {
          setDetail(null)
          setDetailError('')
          return
        }

        setIsDetailLoading(true)
        setDetailError('')

        try {
          const response =
            await fetchConversation(
              conversationId,
            )

          setDetail(response)

          setConversations((items) =>
            items.map((item) =>
              item.id === response.id
                ? {
                    ...item,
                    ...response,
                  }
                : item,
            ),
          )
        } catch (caughtError) {
          setDetailError(
            caughtError.message ||
              'Unable to load conversation detail.',
          )

          setDetail(null)
        } finally {
          setIsDetailLoading(false)
        }
      },
      [],
    )

  const loadNotes = useCallback(
    async (conversationId) => {
      if (!conversationId) {
        setNotes([])
        return
      }

      setIsNotesLoading(true)

      try {
        const response =
          await fetchConversationNotes(
            conversationId,
          )

        setNotes(getList(response))
      } catch {
        setNotes([])
      } finally {
        setIsNotesLoading(false)
      }
    },
    [],
  )

  const loadSupportData =
    useCallback(async () => {
      const [
        categoryResult,
        accountResult,
        userResult,
        templateResult,
        messageTypeResult,
      ] = await Promise.allSettled([
        fetchCategories(),
        fetchEbayAccounts(),
        fetchUsers(),
        fetchTemplates(),
        fetchMessageTypeTree(),
      ])

      if (
        categoryResult.status ===
        'fulfilled'
      ) {
        setCategories(
          getList(categoryResult.value)
            .map(normalizeCategory)
            .filter(
              (category) =>
                category.isActive,
            ),
        )
      } else {
        setCategories([])
      }

      if (
        accountResult.status ===
        'fulfilled'
      ) {
        setAccounts(
          getList(accountResult.value).map(
            normalizeAccount,
          ),
        )
      } else {
        setAccounts([])
      }

      if (
        userResult.status ===
        'fulfilled'
      ) {
        setUsers(
          getList(userResult.value)
            .map(normalizeUser)
            .filter(
              (user) => user.isActive,
            ),
        )

        setUsersError('')
      } else {
        setUsers([])
        setUsersError(
          userResult.reason?.message ||
            'Users are unavailable for assignment.',
        )
      }

      if (
        templateResult.status ===
        'fulfilled'
      ) {
        setTemplates(
          getList(
            templateResult.value,
          ).filter(
            (template) =>
              template.is_active !== false,
          ),
        )
      } else {
        setTemplates([])
      }

      if (
        messageTypeResult.status ===
        'fulfilled'
      ) {
        setMessageTypes(
          messageTypeResult.value || [],
        )
      } else {
        setMessageTypes([])
      }
    }, [])

  useEffect(() => {
    loadSupportData()
  }, [loadSupportData])

  useEffect(() => {
    function syncConversationFromUrl() {
      const conversationId =
        getConversationIdFromUrl()

      setSelectedConversationId(
        conversationId,
      )

      setMobilePane(
        conversationId
          ? 'thread'
          : 'list',
      )
    }

    syncConversationFromUrl()

    window.addEventListener(
      'popstate',
      syncConversationFromUrl,
    )

    return () => {
      window.removeEventListener(
        'popstate',
        syncConversationFromUrl,
      )
    }
  }, [])

  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  useEffect(() => {
    if (page >= pageCount) {
      setPage(pageCount - 1)
    }
  }, [page, pageCount])

  useEffect(() => {
    loadConversationDetail(
      selectedConversationId,
    )

    loadNotes(
      selectedConversationId,
    )
  }, [
    loadConversationDetail,
    loadNotes,
    selectedConversationId,
  ])

  useEffect(() => {
    localStorage.setItem(
      LIST_WIDTH_KEY,
      String(listWidth),
    )
  }, [listWidth])

  useEffect(() => {
    localStorage.setItem(
      DETAILS_WIDTH_KEY,
      String(detailsWidth),
    )
  }, [detailsWidth])

  useEffect(() => {
    localStorage.setItem(
      LIST_PANE_OPEN_KEY,
      String(isListPaneOpen),
    )
  }, [isListPaneOpen])

  function beginListResize(event) {
    event.preventDefault()
    const workspaceLeft =
      event.currentTarget
        .closest('.inbox-page')
        ?.getBoundingClientRect()
        .left || 0

    function move(mouseEvent) {
      setListWidth(
        clamp(
          mouseEvent.clientX -
            workspaceLeft,
          320,
          Math.min(
            620,
            window.innerWidth * 0.42,
          ),
        ),
      )
    }

    function stop() {
      window.removeEventListener(
        'mousemove',
        move,
      )

      window.removeEventListener(
        'mouseup',
        stop,
      )
    }

    window.addEventListener(
      'mousemove',
      move,
    )

    window.addEventListener(
      'mouseup',
      stop,
    )
  }

  function beginDetailsResize(event) {
    event.preventDefault()

    function move(mouseEvent) {
      setDetailsWidth(
        clamp(
          window.innerWidth -
            mouseEvent.clientX,
          260,
          460,
        ),
      )
    }

    function stop() {
      window.removeEventListener(
        'mousemove',
        move,
      )

      window.removeEventListener(
        'mouseup',
        stop,
      )
    }

    window.addEventListener(
      'mousemove',
      move,
    )

    window.addEventListener(
      'mouseup',
      stop,
    )
  }

  function selectConversation(
    conversationId,
  ) {
    setSelectedConversationId(
      conversationId,
    )

    setMobilePane('thread')
    setActionError('')

    const url = new URL(
      window.location.href,
    )

    url.searchParams.set(
      'conversation_id',
      conversationId,
    )

    window.history.replaceState(
      {},
      '',
      url,
    )
  }

  function returnToList() {
    setSelectedConversationId('')
    setDetail(null)
    setNotes([])
    setDetailError('')
    setActionError('')
    setMobilePane('list')

    const url = new URL(
      window.location.href,
    )

    url.searchParams.delete(
      'conversation_id',
    )

    window.history.replaceState(
      {},
      '',
      url,
    )
  }

  function toggleBulkSelection(
    conversationId,
  ) {
    setBulkSelectedIds(
      (current) => {
        const next = new Set(current)

        if (
          next.has(conversationId)
        ) {
          next.delete(conversationId)
        } else {
          next.add(conversationId)
        }

        return next
      },
    )
  }

  function clearBulkSelection() {
    setBulkSelectedIds(new Set())
    setBulkAssignedUserId('')
  }

  function changePageSize(
    nextPageSize,
  ) {
    setPageSize(nextPageSize)
    setPage(0)
  }

  function changeFilter(key, value) {
    setFilters((current) =>
      typeof key === 'object'
        ? {
            ...current,
            ...key,
          }
        : {
            ...current,
            [key]: value,
          },
    )

    setPage(0)
    setSelectedConversationId('')
    setDetail(null)
    setNotes([])
    setMobilePane('list')
  }

  function resetFilters() {
    setFilters({
      ...EMPTY_FILTERS,
    })

    setPage(0)
    setSelectedConversationId('')
    setDetail(null)
    setNotes([])
    setMobilePane('list')
  }

  function toggleNearDueSla() {
    const isActive =
      Number(
        filters.sla_due_within_hours,
      ) === 2

    changeFilter(
      'sla_due_within_hours',
      isActive ? '' : 2,
    )
  }

  async function refreshSelectedConversation() {
    await Promise.all([
      loadConversations(),

      selectedConversationId
        ? loadConversationDetail(
            selectedConversationId,
          )
        : Promise.resolve(),

      selectedConversationId
        ? loadNotes(
            selectedConversationId,
          )
        : Promise.resolve(),
    ])
  }

  async function handleAssign(userId) {
    if (!selectedConversationId) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      await assignConversation(
        selectedConversationId,
        userId,
      )

      await refreshSelectedConversation()
    } catch (caughtError) {
      setActionError(
        caughtError.message ||
          'Unable to assign conversation.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleBulkAssign(event) {
    event.preventDefault()

    const conversationIds =
      Array.from(bulkSelectedIds)

    if (
      !conversationIds.length ||
      !bulkAssignedUserId
    ) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      await bulkUpdateConversations({
        conversation_ids:
          conversationIds,
        assigned_to:
          bulkAssignedUserId,
      })

      clearBulkSelection()

      await refreshSelectedConversation()
    } catch (caughtError) {
      setActionError(
        caughtError.message ||
          'Unable to assign selected conversations.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleAddNote(body) {
    if (!selectedConversationId) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      await createConversationNote(
        selectedConversationId,
        body,
      )

      await Promise.all([
        loadNotes(
          selectedConversationId,
        ),

        loadConversationDetail(
          selectedConversationId,
        ),
      ])
    } catch (caughtError) {
      setActionError(
        caughtError.message ||
          'Unable to create note.',
      )

      throw caughtError
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleCategoryChange(
    categoryId,
  ) {
    if (!selectedConversationId) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      const response =
        await updateConversationCategory(
          selectedConversationId,
          categoryId,
        )

      setDetail(response)

      await loadConversations()
    } catch (caughtError) {
      setActionError(
        caughtError.message ||
          'Unable to update category.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleStatusChange(
    status,
  ) {
    if (!selectedConversationId) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      const response =
        await updateConversationStatus(
          selectedConversationId,
          status,
        )

      setDetail(response)

      await loadConversations()
    } catch (caughtError) {
      setActionError(
        caughtError.message ||
          'Unable to update status.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleSendReply(
    body,
    files = [],
    messageTypeId,
    sendCopyToEmail = true,
  ) {
    if (!selectedConversationId) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      const response = files.length
        ? await sendConversationReplyWithAttachments(
            selectedConversationId,
            body,
            files,
            messageTypeId,
            sendCopyToEmail,
          )
        : await sendConversationReply(
            selectedConversationId,
            body,
            messageTypeId,
            sendCopyToEmail,
          )

      await refreshSelectedConversation()

      if (
        response
          ?.attachment_delivery_warning
      ) {
        setActionError(
          response
            .attachment_delivery_warning,
        )
      }

      return response
    } catch (caughtError) {
      setActionError(
        caughtError.message ||
          'Unable to send reply.',
      )

      throw caughtError
    } finally {
      setIsSubmitting(false)
    }
  }

  function openDetails() {
    setIsDetailsOpen(true)

    if (window.innerWidth <= 820) {
      setMobilePane('details')
    }
  }

  function hideDetails() {
    setIsDetailsOpen(false)
  }

  function closeMobileDetails() {
    setMobilePane('thread')
  }

  const pageClassName = [
    'inbox-page',

    hasSelectedConversation
      ? 'conversation-open'
      : 'list-only',

    isDetailsOpen &&
    visibleConversation
      ? 'details-open'
      : 'details-collapsed',

    !isListPaneOpen &&
    hasSelectedConversation
      ? 'list-pane-hidden'
      : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <AppLayout
      activePage="Inbox"
      currentUser={currentUser}
      onLogout={onLogout}
    >
      <main
        className={pageClassName}
        style={workspaceStyle}
        data-mobile-pane={mobilePane}
      >
        {isListPaneOpen ||
        !hasSelectedConversation ? (
          <ConversationList
            conversations={conversations}
            total={total}
            page={page}
            pageCount={pageCount}
            pageSize={pageSize}
            selectedConversationId={
              selectedConversationId
            }
            selectedConversationIds={
              bulkSelectedIds
            }
            selectedBulkUserId={
              bulkAssignedUserId
            }
            users={
              canManageAssignments
                ? users
                : []
            }
            usersError={
              canManageAssignments
                ? usersError
                : ''
            }
            bulkAssignError={
              actionError
            }
            isLoading={
              isListLoading
            }
            isBulkAssigning={
              isSubmitting
            }
            search={filters.search}
            activeFilterCount={
              activeFilterCount
            }
            nearDueActive={
              Number(
                filters.sla_due_within_hours,
              ) === 2
            }
            onSearch={(searchValue) =>
              changeFilter(
                'search',
                searchValue.trim(),
              )
            }
            onToggleNearDue={
              toggleNearDueSla
            }
            onRefresh={
              loadConversations
            }
            onOpenFilters={() =>
              setIsFiltersOpen(true)
            }
            onSelectConversation={
              selectConversation
            }
            onToggleBulk={
              canManageAssignments
                ? toggleBulkSelection
                : () => {}
            }
            onBulkUserChange={
              setBulkAssignedUserId
            }
            onBulkAssign={
              handleBulkAssign
            }
            onClearBulkSelection={
              clearBulkSelection
            }
            onPageChange={setPage}
            onPageSizeChange={
              changePageSize
            }
          />
        ) : null}

        {listError ? (
          <p
            className="form-message error management-error"
            role="alert"
          >
            {listError}
          </p>
        ) : null}

        {hasSelectedConversation ? (
          <>
            {isListPaneOpen ? (
              <button
                className="resize-handle"
                type="button"
                onMouseDown={
                  beginListResize
                }
                aria-label="Resize conversation list"
              />
            ) : null}

            <section className="inbox-detail-panel">
              {detailError ? (
                <EmptyPanel
                  title="Could not load conversation"
                  message={detailError}
                />
              ) : (
                <ConversationDetail
                  detail={
                    visibleConversation
                  }
                  notes={notes}
                  users={users}
                  usersError={usersError}
                  categories={
                    categories
                  }
                  accounts={accounts}
                  templates={templates}
                  messageTypes={
                    messageTypes
                  }
                  isLoading={
                    isDetailLoading
                  }
                  notesLoading={
                    isNotesLoading
                  }
                  actionError={
                    actionError
                  }
                  isSubmitting={
                    isSubmitting
                  }
                  isDetailsOpen={
                    isDetailsOpen
                  }
                  mobilePane={
                    mobilePane
                  }
                  onBack={returnToList}
                  isListPaneOpen={
                    isListPaneOpen
                  }
                  onToggleListPane={() =>
                    setIsListPaneOpen(
                      (current) =>
                        !current,
                    )
                  }
                  onOpenDetails={
                    openDetails
                  }
                  onHideDetails={
                    hideDetails
                  }
                  onCloseDetails={
                    closeMobileDetails
                  }
                  onAssign={
                    handleAssign
                  }
                  onAddNote={
                    handleAddNote
                  }
                  onCategoryChange={
                    handleCategoryChange
                  }
                  onStatusChange={
                    handleStatusChange
                  }
                  onSendReply={
                    handleSendReply
                  }
                />
              )}
            </section>

            {isDetailsOpen &&
            visibleConversation ? (
              <>
                <button
                  className="resize-handle"
                  type="button"
                  onMouseDown={
                    beginDetailsResize
                  }
                  aria-label="Resize details panel"
                />

                <DetailsPanel
                  detail={
                    visibleConversation
                  }
                  notes={notes}
                  users={users}
                  usersError={
                    usersError
                  }
                  categories={
                    categories
                  }
                  accounts={accounts}
                  notesLoading={
                    isNotesLoading
                  }
                  isSubmitting={
                    isSubmitting
                  }
                  onAssign={
                    handleAssign
                  }
                  onAddNote={
                    handleAddNote
                  }
                  onCategoryChange={
                    handleCategoryChange
                  }
                  onStatusChange={
                    handleStatusChange
                  }
                />
              </>
            ) : null}
          </>
        ) : null}

        <InboxFiltersDrawer
          isOpen={isFiltersOpen}
          filters={filters}
          users={users}
          categories={categories}
          accounts={accounts}
          currentUser={currentUser}
          onFilterChange={
            changeFilter
          }
          onSearchSubmit={(
            searchValue,
          ) =>
            changeFilter(
              'search',
              searchValue.trim(),
            )
          }
          onReset={resetFilters}
          onClose={() =>
            setIsFiltersOpen(false)
          }
        />
      </main>
    </AppLayout>
  )
}

export default Dashboard
