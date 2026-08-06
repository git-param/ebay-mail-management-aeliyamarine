import { PAGE_SIZE_OPTIONS } from '../inboxUtils'

function getVisiblePageItems(
  currentPage,
  pageCount,
) {
  if (pageCount <= 7) {
    return Array.from(
      { length: pageCount },
      (_, index) => index,
    )
  }

  const pages = new Set([
    0,
    pageCount - 1,
    currentPage,
  ])

  if (currentPage > 0) {
    pages.add(currentPage - 1)
  }

  if (currentPage + 1 < pageCount) {
    pages.add(currentPage + 1)
  }

  if (currentPage <= 2) {
    pages.add(1)
    pages.add(2)
    pages.add(3)
  }

  if (currentPage >= pageCount - 3) {
    pages.add(pageCount - 2)
    pages.add(pageCount - 3)
    pages.add(pageCount - 4)
  }

  const sortedPages = Array.from(pages)
    .filter(
      (pageNumber) =>
        pageNumber >= 0 &&
        pageNumber < pageCount,
    )
    .sort((first, second) => first - second)

  const items = []

  sortedPages.forEach((pageNumber, index) => {
    const previousPage = sortedPages[index - 1]

    if (
      index > 0 &&
      pageNumber - previousPage > 1
    ) {
      items.push(`ellipsis-${pageNumber}`)
    }

    items.push(pageNumber)
  })

  return items
}

function InboxPagination({
  page,
  pageCount,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}) {
  const safePageCount = Math.max(
    Number(pageCount) || 0,
    1,
  )

  const safePage = Math.min(
    Math.max(Number(page) || 0, 0),
    safePageCount - 1,
  )

  const safePageSize =
    Number(pageSize) || PAGE_SIZE_OPTIONS[0]

  const safeTotal = Math.max(
    Number(total) || 0,
    0,
  )

  const pageItems = getVisiblePageItems(
    safePage,
    safePageCount,
  )

  const start = safeTotal
    ? safePage * safePageSize + 1
    : 0

  const end = Math.min(
    (safePage + 1) * safePageSize,
    safeTotal,
  )

  function changePage(nextPage) {
    if (
      nextPage < 0 ||
      nextPage >= safePageCount ||
      nextPage === safePage
    ) {
      return
    }

    onPageChange(nextPage)
  }

  function changePageSize(event) {
    const nextPageSize = Number(
      event.target.value,
    )

    if (!Number.isFinite(nextPageSize)) {
      return
    }

    onPageSizeChange(nextPageSize)
  }

  return (
    <div className="pagination-bar">
      <div className="pagination-summary">
        <strong>
          Showing {start}-{end}
        </strong>

        <span>
          of {safeTotal} conversations
        </span>
      </div>

      <div
        className="pagination-controls"
        aria-label="Conversation pagination"
      >
        <button
          className="pagination-button"
          type="button"
          disabled={safePage === 0}
          onClick={() =>
            changePage(safePage - 1)
          }
        >
          Previous
        </button>

        <div className="pagination-pages">
          {pageItems.map((item) => {
            if (typeof item === 'string') {
              return (
                <span
                  className="pagination-ellipsis"
                  key={item}
                  aria-hidden="true"
                >
                  ...
                </span>
              )
            }

            const isCurrentPage =
              item === safePage

            return (
              <button
                className={`pagination-page ${
                  isCurrentPage ? 'active' : ''
                }`}
                type="button"
                aria-current={
                  isCurrentPage
                    ? 'page'
                    : undefined
                }
                onClick={() =>
                  changePage(item)
                }
                key={item}
              >
                {item + 1}
              </button>
            )
          })}
        </div>

        <button
          className="pagination-button"
          type="button"
          disabled={
            safePage + 1 >= safePageCount
          }
          onClick={() =>
            changePage(safePage + 1)
          }
        >
          Next
        </button>
      </div>

      <label className="pagination-size">
        <span>Rows</span>

        <select
          value={safePageSize}
          onChange={changePageSize}
        >
          {PAGE_SIZE_OPTIONS.map((option) => (
            <option
              value={option}
              key={option}
            >
              {option}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}

export { getVisiblePageItems }
export default InboxPagination