import AppLayout from '../layouts/app_layout'

function Dashboard({ currentUser, onLogout }) {
  return (
    <AppLayout activePage="Dashboard" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page">
        <div className="page-header">
          <div>
            <h1>Dashboard</h1>
            <p>Welcome to Omni-Desk</p>
          </div>
        </div>

        <section className="dashboard-card">
          <p>This dashboard is under development.</p>
        </section>
      </main>
    </AppLayout>
  )
}

export default Dashboard
