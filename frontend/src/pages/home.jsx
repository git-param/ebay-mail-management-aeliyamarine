import { Icon } from '../layouts/app_layout'
import HomeScene from './HomeScene'

import './home.css'

const capabilities = [
  {
    icon: 'message',
    title: 'Shared message operations',
    copy: 'Keep marketplace conversations, assignments, internal notes, and replies in one working queue.',
    accent: 'teal',
  },
  {
    icon: 'package',
    title: 'Order context at hand',
    copy: 'Move from a buyer message to sold-item, shipping, and product details without losing the thread.',
    accent: 'coral',
  },
  {
    icon: 'handshake',
    title: 'Offer management',
    copy: 'Review active offers, coordinate decisions, and keep negotiations visible to the whole team.',
    accent: 'gold',
  },
  {
    icon: 'chart',
    title: 'Operational reporting',
    copy: 'See message volume, response activity, task progress, and marketplace work from one reporting layer.',
    accent: 'blue',
  },
  {
    icon: 'users',
    title: 'Clear team ownership',
    copy: 'Route work by role, assign conversations, and give every request an accountable owner.',
    accent: 'green',
  },
  {
    icon: 'search',
    title: 'Cross-platform search',
    copy: 'Find product and marketplace information quickly when a customer needs a precise answer.',
    accent: 'red',
  },
]

const workflow = [
  ['01', 'Receive', 'Bring new customer conversations into a shared, organized inbox.'],
  ['02', 'Understand', 'See buyer, product, order, and marketplace context beside the message.'],
  ['03', 'Act', 'Reply, assign, manage an offer, or update the related operational record.'],
  ['04', 'Improve', 'Use reports and audit history to strengthen day-to-day performance.'],
]

function BrandMark() {
  return (
    <span className="home-brand-mark" aria-hidden="true">
      A
    </span>
  )
}

export default function Home() {
  return (
    <main className="home-page">
      <header className="home-nav">
        <a className="home-brand" href="/" aria-label="ACES home">
          <BrandMark />
          <span>
            <strong>ACES</strong>
            <small>Aeliya Communications &amp; Engagement System</small>
          </span>
        </a>

        <nav className="home-nav-links" aria-label="Home navigation">
          <a href="#capabilities">Capabilities</a>
          <a href="#workflow">Workflow</a>
          <a href="#control">Team control</a>
        </nav>

        <a className="home-login-button" href="/login">
          Login
          <span aria-hidden="true">&#8594;</span>
        </a>
      </header>

      <section className="home-hero" aria-labelledby="home-title">
        <HomeScene />
        <span className="home-chapter" aria-hidden="true">01 / COMMAND</span>
        <div className="home-hero-copy">
          <p className="home-eyebrow">Aeliya Communications &amp; Engagement System</p>
          <h1 id="home-title">ACES</h1>
          <h2>Every signal.<br />One command.</h2>
          <p className="home-hero-description">
            Coordinate marketplace conversations, offers, sold postings, tasks, and team performance without switching between disconnected workflows.
          </p>
          <div className="home-hero-actions">
            <a className="home-primary-action" href="/login">
              Login to ACES
              <span aria-hidden="true">&#8594;</span>
            </a>
            <a className="home-secondary-action" href="#capabilities">
              Explore the platform
            </a>
          </div>
        </div>
        <a className="home-scroll-cue" href="#operations">
          <span />
          Enter the system
        </a>
      </section>

      <section className="home-story" id="operations" aria-labelledby="operations-title">
        <img
          src="/aces-operations-hero.png"
          alt="An ecommerce operations team managing customer messages and orders"
        />
        <div className="home-story-shade" aria-hidden="true" />
        <span className="home-chapter" aria-hidden="true">02 / OPERATIONS</span>
        <div className="home-story-copy">
          <p className="home-kicker">The complete picture</p>
          <h2 id="operations-title">From first message<br />to final action.</h2>
          <p>Customer intent, order context, ownership, and performance remain visible in one continuous operational view.</p>
        </div>
        <div className="home-story-status" aria-label="Live platform status">
          <span><i /> Shared inbox online</span>
          <span><i /> Order context synced</span>
          <span><i /> Activity trace active</span>
        </div>
      </section>

      <section className="home-signal-band" aria-label="Platform highlights">
        <div>
          <Icon name="message" />
          <span><strong>One shared inbox</strong> for customer communication</span>
        </div>
        <div>
          <Icon name="package" />
          <span><strong>Live order context</strong> beside every workflow</span>
        </div>
        <div>
          <Icon name="audit" />
          <span><strong>Traceable activity</strong> across teams and roles</span>
        </div>
      </section>

      <section className="home-capabilities" id="capabilities">
        <div className="home-section-heading">
          <p className="home-kicker">Built around the work</p>
          <h2>Everything your operations team needs to keep moving.</h2>
          <p>ACES connects communication with the marketplace and team context needed to act on it.</p>
        </div>

        <div className="home-capability-grid">
          {capabilities.map((item) => (
            <article className="home-capability" key={item.title}>
              <span className={`home-capability-icon ${item.accent}`}>
                <Icon name={item.icon} />
              </span>
              <h3>{item.title}</h3>
              <p>{item.copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="home-workflow" id="workflow">
        <div className="home-workflow-image-wrap">
          <img
            src="/aces-workflow.png"
            alt="An operations specialist coordinating customer messages with parcel fulfillment"
            loading="lazy"
          />
          <div className="home-image-caption">
            <Icon name="activate" />
            Communication and fulfillment stay connected
          </div>
        </div>

        <div className="home-workflow-copy">
          <p className="home-kicker">A connected workflow</p>
          <h2>Turn incoming questions into clear next actions.</h2>
          <p className="home-section-intro">
            ACES keeps the customer conversation and the operational response in the same line of sight.
          </p>
          <ol className="home-workflow-list">
            {workflow.map(([number, title, copy]) => (
              <li key={number}>
                <span>{number}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{copy}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="home-control" id="control">
        <div className="home-control-inner">
          <div>
            <p className="home-kicker">Control without friction</p>
            <h2>The right view for every role.</h2>
            <p>
              Agents stay focused on their queue. Operations managers coordinate workload and performance. Administrators manage access, accounts, configuration, and audit history.
            </p>
          </div>
          <div className="home-role-list" aria-label="ACES roles">
            <span><Icon name="message" /> Agent workspace</span>
            <span><Icon name="chart" /> Operations oversight</span>
            <span><Icon name="settings" /> Administrative control</span>
          </div>
        </div>
      </section>

      <section className="home-final-cta">
        <BrandMark />
        <div>
          <h2>Ready to get to work?</h2>
          <p>Sign in with your organization credentials to open your ACES workspace.</p>
        </div>
        <a className="home-primary-action" href="/login">
          Go to login
          <span aria-hidden="true">&#8594;</span>
        </a>
      </section>

      <footer className="home-footer">
        <span>ACES</span>
        <p>Aeliya Communications &amp; Engagement System</p>
        <a href="mailto:paramdholakia3@gmail.com">Contact for query: paramdholakia3@gmail.com</a>
      </footer>
    </main>
  )
}
