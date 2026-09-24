import { Component } from 'react'

class AppErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, errorInfo) {
    console.error('Application render failed', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="app-error-page" role="alert">
          <section className="app-error-panel">
            <h1>Something went wrong</h1>
            <p>
              The application could not update this screen. Your reply may
              already have been sent, so check the conversation after reloading.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
            >
              Reload application
            </button>
          </section>
        </main>
      )
    }

    return this.props.children
  }
}

export default AppErrorBoundary
