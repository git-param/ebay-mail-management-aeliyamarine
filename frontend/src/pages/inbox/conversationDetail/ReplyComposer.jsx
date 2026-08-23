import { useState } from 'react'

import { Icon } from '../../../layouts/app_layout'
import { validateConversationReply } from '../../../services/conversationApi'
import MessageTypeSelector from './MessageTypeSelector'

import './replyComposer.css'
/**
 * Reply editor rendered below an open conversation thread.
 * Owns drafts, attachments, policy validation, and the editable Message Type
 * suggestion. Dashboard supplies delivery and refresh behavior via props.
 */
function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return 'Unknown size'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function ReplyComposer({ conversationId, suggestedMessageTypeId, isSubmitting, onSendReply, templates, messageTypes = [] }) {
  const [body, setBody] = useState('')
  const [files, setFiles] = useState([])
  const [fileInputKey, setFileInputKey] = useState(0)
  const [violations, setViolations] = useState([])
  const [draftMessage, setDraftMessage] = useState('')
  const [isValidating, setIsValidating] = useState(false)
  const [categoryId, setCategoryId] = useState('')
  const [subtypeId, setSubtypeId] = useState('')
  const [sendCopyToEmail, setSendCopyToEmail] = useState(true)
  const category = messageTypes.find((item) => item.id === categoryId)
  const selectedTypeId = category?.children?.length ? subtypeId : categoryId

  function addFiles(selectedFiles) {
    const nextFiles = [...files, ...selectedFiles]
    if (nextFiles.length > 5) {
      setViolations(['eBay allows a maximum of 5 attachments per reply.'])
      setFileInputKey((current) => current + 1)
      return
    }
    setViolations([])
    setDraftMessage('')
    setFiles(nextFiles)
    setFileInputKey((current) => current + 1)
  }

  function updateFiles(event) {
    addFiles(Array.from(event.target.files || []))
  }

  function removeFile(fileIndex) {
    setFiles((current) => current.filter((_, index) => index !== fileIndex))
    setDraftMessage('')
  }

  function saveDraft() {
    setViolations([])
    setDraftMessage('Draft saved locally for this conversation.')
  }

  async function submitReply(event) {
    event.preventDefault()
    if (isSubmitting || isValidating) return
    const trimmedBody = body.trim()
    if (!trimmedBody || !conversationId || !selectedTypeId) {
      if (!selectedTypeId) setViolations(['Message type is required.'])
      return
    }
    setIsValidating(true)
    setViolations([])
    setDraftMessage('')
    try {
      const validation = await validateConversationReply(conversationId, trimmedBody)
      if (!validation.valid) {
        setViolations(validation.violations || ['Reply violates eBay messaging policy.'])
        return
      }
      await onSendReply(trimmedBody, files, selectedTypeId, sendCopyToEmail)
      setBody('')
      setFiles([])
      setSendCopyToEmail(true)
      setDraftMessage('')
      setFileInputKey((current) => current + 1)
      setCategoryId('')
      setSubtypeId('')
    } catch (caughtError) {
      setViolations([caughtError.message])
    } finally {
      setIsValidating(false)
    }
  }

  return (
    <form className="reply-composer" onSubmit={submitReply}>
      <div className="composer-toolbar composer-controls">
        {templates.length ? (
          <label className="composer-select-control">
            <span>Template</span>
            <select
              className="template-picker"
              value=""
              aria-label="Insert reply template"
              onChange={(event) => {
                const template = templates.find((item) => item.id === event.target.value)
                if (template) {
                  setBody((current) => {
                    const separator = current.trim() ? '\n\n' : ''
                    return `${current}${separator}${template.body}`
                  })
                }
              }}
            >
              <option value="">Choose template</option>
              {templates.map((template) => (
                <option value={template.id} key={template.id}>
                  {template.title}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <MessageTypeSelector
          conversationId={conversationId}
          suggestedMessageTypeId={suggestedMessageTypeId}
          messageTypes={messageTypes}
          categoryId={categoryId}
          subtypeId={subtypeId}
          onCategoryChange={setCategoryId}
          onSubtypeChange={setSubtypeId}
        />
      </div>

      <label className="field composer-editor">
        <span>Reply to buyer</span>
        <textarea
          value={body}
          onChange={(event) => {
            setBody(event.target.value)
            setDraftMessage('')
          }}
          rows="3"
          maxLength={2000}
          placeholder="Write a reply without email, phone, external links, or abusive language"
        />
      </label>
      {files.length ? (
        <div className="reply-attachment-list" aria-label="Selected attachments">
          {files.map((file, index) => (
            <span className="reply-attachment-chip" key={`${file.name}-${file.size}-${index}`}>
              <span>
                <strong>{file.name}</strong>
                <small>{formatFileSize(file.size)}</small>
              </span>
              <button type="button" onClick={() => removeFile(index)} aria-label={`Remove ${file.name}`}>
                x
              </button>
            </span>
          ))}
        </div>
      ) : null}
      {violations.length ? (
        <div className="reply-policy-warning" role="alert">
          {violations.map((violation) => (
            <p key={violation}>{violation}</p>
          ))}
        </div>
      ) : null}
      {draftMessage ? (
        <div className="reply-draft-message" role="status">
          <p>{draftMessage}</p>
        </div>
      ) : null}
      <div className="reply-composer-actions">
        <div className="composer-attachment-action">
          <input id={`reply-attachments-${conversationId}`} key={fileInputKey} type="file" multiple onChange={updateFiles} accept=".pdf,.txt,.jpg,.jpeg,.png,application/pdf,text/plain,image/jpeg,image/png" />
          <label htmlFor={`reply-attachments-${conversationId}`} title="Attach files" aria-label="Attach files"><Icon name="paperclip" /></label>
          <small>{files.length ? `${files.length} attached` : 'Attach'} Â· {body.length}/2000</small>
        </div>
        <label className="email-copy-checkbox" htmlFor={`reply-email-copy-${conversationId}`}>
          <input id={`reply-email-copy-${conversationId}`} type="checkbox" checked={sendCopyToEmail} disabled={isSubmitting || isValidating} onChange={(event) => setSendCopyToEmail(event.target.checked)} />
          <span>Send a copy to my email</span>
        </label>
        <button className="secondary-button compact" type="button" onClick={saveDraft} disabled={!body.trim() && !files.length}>
          Save Draft
        </button>
        <button className="primary-button compact" type="submit" disabled={!body.trim() || !selectedTypeId || isSubmitting || isValidating}>
          {isValidating ? 'Checking...' : isSubmitting ? 'Sending...' : 'Send Reply'}
        </button>
      </div>
    </form>
  )
}
