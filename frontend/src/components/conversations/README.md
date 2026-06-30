# Conversation components

These components are used by `pages/dashboard.jsx` when an inbox conversation
is open.

- `ReplyComposer.jsx` owns reply draft state, attachments, validation, and
  submits the selected Message Type to the callback provided by Dashboard.
- `MessageTypeSelector.jsx` maps the backend's suggested Message Type ID into
  the parent/subtype controls. The controls remain editable by the user.

Keep API list loading and conversation refresh logic in `dashboard.jsx`. Put
thread or reply-specific presentation and local interaction state here.
