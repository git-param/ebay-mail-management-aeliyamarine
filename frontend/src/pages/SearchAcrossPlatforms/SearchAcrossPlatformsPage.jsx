import { useRef, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import { searchAcrossPlatforms } from '../../services/searchSkuApi'
import PlatformColumn from './components/PlatformColumn'
import './SearchAcrossPlatformsPage.css'

const EMPTY_RESULTS = {
  zoho: null,
  atlaship: null,
  alreza: null,
}

function SearchAcrossPlatformsPage({ currentUser, onLogout }) {
  const [query, setQuery] = useState('')
  const [limit, setLimit] = useState(10)
  const [results, setResults] = useState(EMPTY_RESULTS)
  const [isSearching, setIsSearching] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [pageError, setPageError] = useState('')
  const abortRef = useRef(null)

  async function runSearch(event) {
    event?.preventDefault()
    const nextQuery = query.trim()
    if (!nextQuery || isSearching) {
      return
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setIsSearching(true)
    setPageError('')
    setHasSearched(true)

    try {
      const response = await searchAcrossPlatforms(nextQuery, limit, controller.signal)
      if (!controller.signal.aborted) {
        setResults({
          zoho: response.zoho,
          atlaship: response.atlaship,
          alreza: response.alreza,
        })
      }
    } catch (caughtError) {
      if (caughtError.name !== 'AbortError') {
        setPageError(caughtError.message || 'Search failed. Please try again.')
      }
    } finally {
      if (!controller.signal.aborted) {
        setIsSearching(false)
      }
    }
  }

  const allFailed = hasSearched && !isSearching && ['zoho', 'atlaship', 'alreza'].every((platform) => results[platform]?.error)

  return (
    <AppLayout activePage="Search Across Platforms" currentUser={currentUser} onLogout={onLogout}>
      <main className="cross-search-page">
        <header className="cross-search-header">
          <div>
            <span className="inbox-kicker">Inventory lookup</span>
            <h1>Search Across Platforms</h1>
            <p>Search Zoho, Atlaship, and Alreza at the same time.</p>
          </div>
        </header>

        <form className="cross-search-form" onSubmit={runSearch}>
          <label className="field cross-search-input">
            <span>Search keyword</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by product name, SKU, model, part number, or keyword"
            />
          </label>
          <label className="field cross-search-limit">
            <span>Results</span>
            <select value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
              <option value="5">5 each</option>
              <option value="10">10 each</option>
              <option value="20">20 each</option>
              <option value="50">50 each</option>
            </select>
          </label>
          <button className="primary-button cross-search-button action-button action-load" type="submit" disabled={!query.trim() || isSearching}>
            <Icon name="search" />
            {isSearching ? 'Searching' : 'Search'}
          </button>
        </form>

        {pageError || allFailed ? (
          <p className="form-message error cross-search-error" role="alert">
            {pageError || 'All platforms failed. Please retry the search.'}
          </p>
        ) : null}

        <div className="platform-grid">
          <PlatformColumn platformName="Zoho" result={results.zoho} isLoading={isSearching} hasSearched={hasSearched} />
          <PlatformColumn platformName="Atlaship" result={results.atlaship} isLoading={isSearching} hasSearched={hasSearched} />
          <PlatformColumn platformName="Alreza" result={results.alreza} isLoading={isSearching} hasSearched={hasSearched} />
        </div>
      </main>
    </AppLayout>
  )
}

export default SearchAcrossPlatformsPage
