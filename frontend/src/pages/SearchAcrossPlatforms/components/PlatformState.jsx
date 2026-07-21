function PlatformState({ type, platformName }) {
  const messages = {
    initial: 'Enter a keyword to search all three platforms.',
    loading: `Searching ${platformName}...`,
    empty: `No results found on ${platformName}.`,
  }

  return (
    <div className={`platform-state platform-state-${type}`}>
      <span aria-hidden="true" />
      <p>{messages[type]}</p>
    </div>
  )
}

export default PlatformState
