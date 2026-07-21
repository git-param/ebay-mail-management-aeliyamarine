import PlatformState from './PlatformState'
import ProductResultCard from './ProductResultCard'

function PlatformColumn({ platformName, result, isLoading, hasSearched }) {
  const count = result?.count || 0
  const items = result?.items || []

  return (
    <section className="platform-column" aria-label={`${platformName} results`}>
      <header className="platform-column-header">
        <h2>{platformName}</h2>
        <span>{isLoading ? '...' : count}</span>
      </header>

      {isLoading ? <PlatformState type="loading" platformName={platformName} /> : null}

      {!isLoading && result?.error ? (
        <div className="platform-error" role="alert">
          {result.error}
        </div>
      ) : null}

      {!isLoading && !result?.error && !hasSearched ? <PlatformState type="initial" platformName={platformName} /> : null}

      {!isLoading && !result?.error && hasSearched && !items.length ? <PlatformState type="empty" platformName={platformName} /> : null}

      {!isLoading && !result?.error && items.length ? (
        <div className="platform-results">
          {items.map((item) => (
            <ProductResultCard item={item} key={item.external_id || item.product_url} />
          ))}
        </div>
      ) : null}
    </section>
  )
}

export default PlatformColumn
