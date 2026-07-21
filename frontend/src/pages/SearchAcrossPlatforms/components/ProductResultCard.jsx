const METADATA_LABELS = {
  brand: 'Brand',
  condition: 'Condition',
  stock_on_hand: 'Stock',
  part_number: 'Part number',
  ebay_price: 'eBay price',
  ref_no: 'Reference',
  serial_no: 'Serial',
  type_designation: 'Type',
  ref: 'Reference',
  model: 'Model',
}

const PLATFORM_FIELDS = {
  zoho: ['brand', 'condition', 'stock_on_hand', 'part_number', 'ebay_price'],
  atlaship: ['ref_no', 'serial_no', 'type_designation', 'condition'],
  alreza: ['brand', 'model', 'condition', 'ref'],
}

function metadataEntries(item) {
  const fields = PLATFORM_FIELDS[item.platform] || []
  return fields
    .map((field) => [METADATA_LABELS[field] || field, item.metadata?.[field]])
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .slice(0, 4)
}

function ProductResultCard({ item }) {
  const entries = metadataEntries(item)

  function handleImageError(event) {
    event.currentTarget.hidden = true
    event.currentTarget.nextElementSibling.hidden = false
  }

  return (
    <a className="product-result-card" href={item.product_url} target="_blank" rel="noopener noreferrer">
      <span className="product-thumb">
        {item.image_url ? (
          <img src={item.image_url} alt="" loading="lazy" onError={handleImageError} />
        ) : null}
        <span className="product-thumb-placeholder" hidden={Boolean(item.image_url)}>
          No image
        </span>
      </span>
      <span className="product-result-body">
        <strong>{item.name || 'Untitled product'}</strong>
        <span className="product-sku">SKU: {item.sku || 'Not available'}</span>
        {entries.length ? (
          <span className="product-meta-list">
            {entries.map(([label, value]) => (
              <small key={label}>
                {label}: {String(value)}
              </small>
            ))}
          </span>
        ) : null}
      </span>
    </a>
  )
}

export default ProductResultCard
