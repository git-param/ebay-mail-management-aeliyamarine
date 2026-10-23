import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'

import { Icon } from '../../../layouts/app_layout'
import { validateConversationReply } from '../../../services/conversationApi'
import MessageTypeSelector from './MessageTypeSelector'

import './replyComposer.css'
import './replyComposerLayout.css'

const REPLY_DRAFT_STORAGE_PREFIX = 'aces:conversation-reply-draft:v1'
const MAX_IMAGE_SIZE_BYTES = 12 * 1024 * 1024

function replyDraftStorageKey(userId, conversationId) {
  if (!userId || !conversationId) return ''
  return `${REPLY_DRAFT_STORAGE_PREFIX}:${userId}:${conversationId}`
}

function readReplyDraft(storageKey) {
  if (!storageKey) return null
  try {
    const draft = JSON.parse(localStorage.getItem(storageKey) || 'null')
    return draft && typeof draft.body === 'string' ? draft : null
  } catch {
    localStorage.removeItem(storageKey)
    return null
  }
}

function removeReplyDraft(storageKey) {
  if (!storageKey) return
  try {
    localStorage.removeItem(storageKey)
  } catch {
    // Sending must still succeed when browser storage is unavailable.
  }
}

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

function isImageFile(file) {
  return (
    String(file?.type || '').startsWith('image/') ||
    /\.(png|jpe?g|gif|webp)$/i.test(file?.name || '')
  )
}

export default function ReplyComposer({
  conversationId,
  buyerName,
  currentUser,
  suggestedMessageTypeId,
  isSubmitting,
  onSendReply,
  templates = [],
  messageTypes = [],
  validateMessage = validateConversationReply,
  composerLabel = 'Reply to buyer',
}) {
  const draftStorageKey = replyDraftStorageKey(currentUser?.id, conversationId)
  const initialDraft = useMemo(() => readReplyDraft(draftStorageKey), [draftStorageKey])
  const [body, setBody] = useState(() => initialDraft?.body || '')
  const [isReplyMinimized, setIsReplyMinimized] = useState(false)
  const editorRef = useRef(null)
  const editorId = useId()
  const [files, setFiles] = useState([])
  const [fileInputKey, setFileInputKey] = useState(0)
  const [violations, setViolations] = useState([])
  const [draftMessage, setDraftMessage] = useState(() =>
    initialDraft ? 'Saved draft restored for this conversation.' : '',
  )
  const [isValidating, setIsValidating] = useState(false)
  const [categoryId, setCategoryId] = useState(() => initialDraft?.categoryId || '')
  const [subtypeId, setSubtypeId] = useState(() => initialDraft?.subtypeId || '')
  const [templateCategoryId, setTemplateCategoryId] = useState('')
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [sendCopyToEmail, setSendCopyToEmail] = useState(() => initialDraft?.sendCopyToEmail ?? true)
  const [showMessageTypeError, setShowMessageTypeError] = useState(false)
  const category = messageTypes.find((item) => item.id === categoryId)
  const selectedTypeId = category?.children?.length ? subtypeId : categoryId
  const templateCategories = useMemo(() => {
    const categoryMap = new Map()
    let hasUncategorizedTemplates = false
    templates.forEach((template) => {
      if (template.category_id && template.category?.is_active !== false) {
        categoryMap.set(template.category_id, template.category.name)
      } else {
        hasUncategorizedTemplates = true
      }
    })

    const categories = Array.from(categoryMap, ([id, name]) => ({ id, name })).sort((first, second) =>
      first.name.localeCompare(second.name),
    )
    return hasUncategorizedTemplates ? [...categories, { id: 'uncategorized', name: 'Uncategorized' }] : categories
  }, [templates])
  const filteredTemplates = useMemo(() => {
    if (!templateCategoryId) return []
    return templates
      .filter((template) => {
        if (templateCategoryId === 'uncategorized') {
          return !template.category_id || template.category?.is_active === false
        }
        return template.category_id === templateCategoryId
      })
      .sort((first, second) => String(first.title || '').localeCompare(String(second.title || '')))
  }, [templateCategoryId, templates])
  const attachmentPreviews = useMemo(
    () =>
      files.map((file) => ({
        file,
        previewUrl: isImageFile(file) ? URL.createObjectURL(file) : '',
      })),
    [files],
  )

  useLayoutEffect(() => {
    const editor = editorRef.current
    if (!editor) return

    function resizeEditor() {
      // With rows=3, auto restores the original compact height before measuring
      // wrapped text. Measuring afresh also lets the editor shrink after deletion.
      editor.style.height = 'auto'
      const compactHeight = editor.getBoundingClientRect().height
      const styles = window.getComputedStyle(editor)
      const borderHeight = parseFloat(styles.borderTopWidth) + parseFloat(styles.borderBottomWidth)
      editor.style.height = `${isReplyMinimized || !body ? compactHeight : Math.max(compactHeight, editor.scrollHeight + borderHeight)}px`
    }

    resizeEditor()
    let previousWidth = editor.getBoundingClientRect().width
    const observer = new ResizeObserver(() => {
      const width = editor.getBoundingClientRect().width
      // Ignore height changes, including the user's manual resize.
      if (width !== previousWidth) {
        previousWidth = width
        resizeEditor()
      }
    })
    observer.observe(editor)
    return () => observer.disconnect()
  }, [body, isReplyMinimized])

  useEffect(
    () => () => {
      attachmentPreviews.forEach((attachment) => {
        if (attachment.previewUrl) {
          URL.revokeObjectURL(attachment.previewUrl)
        }
      })
    },
    [attachmentPreviews],
  )

  function addFiles(selectedFiles) {
    const nextFiles = [...files, ...selectedFiles]
    if (nextFiles.length > 5) {
      setViolations(['eBay allows a maximum of 5 attachments per reply.'])
      setFileInputKey((current) => current + 1)
      return
    }
    if (selectedFiles.some((file) => file.size > MAX_IMAGE_SIZE_BYTES)) {
      setViolations(['Images must be 12 MB or smaller.'])
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

  function pasteClipboardImages(event) {
    const pastedImages = Array.from(event.clipboardData?.items || [])
      .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
      .map((item) => item.getAsFile())
      .filter(Boolean)

    if (!pastedImages.length) return

    event.preventDefault()
    const unsupportedImage = pastedImages.find(
      (file) => !['image/jpeg', 'image/png'].includes(file.type),
    )
    if (unsupportedImage) {
      setViolations(['Pasted images must be JPEG or PNG files.'])
      return
    }

    addFiles(pastedImages)
  }

  function removeFile(fileIndex) {
    setFiles((current) => current.filter((_, index) => index !== fileIndex))
    setDraftMessage('')
  }

  function saveDraft() {
    setViolations([])
    if (!draftStorageKey || !body.trim()) {
      setDraftMessage('')
      setViolations(['Enter a reply before saving a draft. Attachments cannot be saved locally.'])
      return
    }

    try {
      localStorage.setItem(
        draftStorageKey,
        JSON.stringify({
          body,
          categoryId,
          subtypeId,
          sendCopyToEmail,
          savedAt: new Date().toISOString(),
        }),
      )
      setDraftMessage(
        files.length
          ? 'Draft saved. Attachments must be added again when you return.'
          : 'Draft saved locally for this conversation.',
      )
    } catch {
      setDraftMessage('')
      setViolations(['Unable to save the draft in this browser. Check browser storage settings and try again.'])
    }
  }

  function insertTemplate(templateId) {
    const template = templates.find((item) => item.id === templateId)
    setSelectedTemplateId(templateId)
    if (template) {
      const templateBody = String(template.body || '')
      const normalizedBuyerName = String(buyerName || '').trim()
      const employeeName = String(currentUser?.full_name || currentUser?.fullName || currentUser?.name || '').trim()
      const personalizedBody = templateBody.replace(/\[(name|buyer|employee name)\]/gi, (placeholder, field) =>
        (field.toLowerCase() === 'employee name' ? employeeName : normalizedBuyerName) || placeholder,
      )
      setBody(personalizedBody)
      setDraftMessage('')
    }
  }

  async function submitReply(event) {
    event.preventDefault()
    if (isSubmitting || isValidating) return
    const trimmedBody = body.trim()
    if (!trimmedBody || !conversationId || !selectedTypeId) {
      if (!selectedTypeId) {
        setShowMessageTypeError(true)
        setViolations(['Message type is required.'])
      }
      return
    }
    setShowMessageTypeError(false)
    setIsValidating(true)
    setViolations([])
    setDraftMessage('')
    try {
      const validation = await validateMessage(conversationId, trimmedBody)
      if (!validation.valid) {
        setViolations(validation.violations || ['Reply violates eBay messaging policy.'])
        return
      }
      await onSendReply(trimmedBody, files, selectedTypeId, sendCopyToEmail)
      removeReplyDraft(draftStorageKey)
      setBody('')
      setIsReplyMinimized(false)
      setFiles([])
      setSendCopyToEmail(true)
      setDraftMessage('')
      setFileInputKey((current) => current + 1)
      setCategoryId('')
      setSubtypeId('')
      setShowMessageTypeError(false)
    } catch (caughtError) {
      setViolations([caughtError.message])
    } finally {
      setIsValidating(false)
    }
  }

  return (
    <form className="reply-composer" onSubmit={submitReply}>
      <div className="composer-toolbar-row">
      <div className="composer-controls">
        {templates.length ? (
          <>
            <label className="composer-select-control">
              <span>Template Category</span>
              <Icon name="grid" />
              <select
                className="template-category-picker"
                value={templateCategoryId}
                aria-label="Choose reply template category"
                onChange={(event) => {
                  setTemplateCategoryId(event.target.value)
                  setSelectedTemplateId('')
                }}
              >
                <option value="">Template category</option>
                {templateCategories.map((templateCategory) => (
                  <option value={templateCategory.id} key={templateCategory.id}>
                    {templateCategory.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="composer-select-control">
              <span>Template</span>
              <Icon name="audit" />
              <select
                className="template-picker"
                value={selectedTemplateId}
                aria-label="Insert reply template"
                disabled={!templateCategoryId || !filteredTemplates.length}
                onChange={(event) => insertTemplate(event.target.value)}
              >
                <option value="">Template</option>
                {filteredTemplates.map((template) => (
                  <option value={template.id} key={template.id}>
                    {template.title}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : null}
        <MessageTypeSelector
          conversationId={conversationId}
          suggestedMessageTypeId={suggestedMessageTypeId}
          messageTypes={messageTypes}
          categoryId={categoryId}
          subtypeId={subtypeId}
          showRequiredError={showMessageTypeError}
          onCategoryChange={setCategoryId}
          onSubtypeChange={setSubtypeId}
        />
      </div>
        <button
          className="secondary-button compact composer-save-draft"
          type="button"
          onClick={saveDraft}
          disabled={!body.trim() && !files.length}
        >
          <Icon name="save" />
          Save Draft
        </button>
      </div>

      <div className="composer-editor-shell">
        <div className="composer-editor-heading">
          <label htmlFor={editorId}><Icon name="reply" />{composerLabel}</label>
          <button
            className="secondary-button compact composer-size-toggle"
            type="button"
            aria-controls={editorId}
            aria-expanded={!isReplyMinimized}
            disabled={!body}
            onClick={() => setIsReplyMinimized((current) => !current)}
          >
            {isReplyMinimized ? 'Expand reply' : 'Minimize reply'}
          </button>
        </div>
        <div className="field composer-editor">
          <textarea
            id={editorId}
            ref={editorRef}
            value={body}
            onChange={(event) => {
              setBody(event.target.value)
              if (!event.target.value) setIsReplyMinimized(false)
              setDraftMessage('')
            }}
            onPaste={pasteClipboardImages}
            rows="3"
            maxLength={2000}
            placeholder="Write a reply without email, phone, external links, or abusive language"
          />
        </div>
        <div className="composer-editor-footer">
          <div className="composer-attachment-action">
            <input
              id={`reply-attachments-${conversationId}`}
              key={fileInputKey}
              type="file"
              multiple
              onChange={updateFiles}
              accept=".jpg,.jpeg,.png,image/jpeg,image/png"
            />
            <label htmlFor={`reply-attachments-${conversationId}`}>
              <Icon name="paperclip" />
              {files.length ? `Attach (${files.length})` : 'Attach'}
            </label>
          </div>
          <label className="email-copy-checkbox" htmlFor={`reply-email-copy-${conversationId}`}>
            <input
              id={`reply-email-copy-${conversationId}`}
              type="checkbox"
              checked={sendCopyToEmail}
              disabled={isSubmitting || isValidating}
              onChange={(event) => setSendCopyToEmail(event.target.checked)}
            />
            <Icon name="mail" /><span>Send a copy to my email</span>
          </label>
          <div className="composer-send-actions">
            <small className="composer-character-count">{body.length} / 2000</small>
            <button
              className="primary-button composer-send-button"
              type="submit"
              aria-label={isValidating ? 'Checking message' : isSubmitting ? 'Sending message' : 'Send Reply'}
              title={isValidating ? 'Checking...' : isSubmitting ? 'Sending...' : 'Send Reply'}
              aria-disabled={!body.trim() || !selectedTypeId || isSubmitting || isValidating}
              disabled={isSubmitting || isValidating}
            >
              <Icon name="send" />
            </button>
          </div>
        </div>
      </div>
      {files.length ? (
        <div className="reply-attachment-list" aria-label="Selected attachments">
          {attachmentPreviews.map(({ file, previewUrl }, index) => (
            <span className={`reply-attachment-chip${previewUrl ? ' has-preview' : ''}`} key={`${file.name}-${file.size}-${index}`}>
              {previewUrl ? (
                <a
                  className="reply-attachment-preview-link"
                  href={previewUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`Open ${file.name} preview in a new tab`}
                >
                  <img className="reply-attachment-preview" src={previewUrl} alt="" />
                </a>
              ) : null}
              <span className="reply-attachment-meta">
                <strong title={file.name}>{file.name}</strong>
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
    </form>
  )
}
