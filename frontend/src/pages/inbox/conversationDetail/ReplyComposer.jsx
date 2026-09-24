import { useEffect, useMemo, useState } from 'react'

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

function isImageFile(file) {
  return (
    String(file?.type || '').startsWith('image/') ||
    /\.(png|jpe?g|gif|webp)$/i.test(file?.name || '')
  )
}

export default function ReplyComposer({ conversationId, buyerName, suggestedMessageTypeId, isSubmitting, onSendReply, templates = [], messageTypes = [] }) {
  const [body, setBody] = useState('')
  const [files, setFiles] = useState([])
  const [fileInputKey, setFileInputKey] = useState(0)
  const [violations, setViolations] = useState([])
  const [draftMessage, setDraftMessage] = useState('')
  const [isValidating, setIsValidating] = useState(false)
  const [categoryId, setCategoryId] = useState('')
  const [subtypeId, setSubtypeId] = useState('')
  const [templateCategoryId, setTemplateCategoryId] = useState('')
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [sendCopyToEmail, setSendCopyToEmail] = useState(true)
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
    setDraftMessage('Draft saved locally for this conversation.')
  }

  function insertTemplate(templateId) {
    const template = templates.find((item) => item.id === templateId)
    setSelectedTemplateId(templateId)
    if (template) {
      const templateBody = String(template.body || '')
      const normalizedBuyerName = String(buyerName || '').trim()
      const personalizedBody = normalizedBuyerName
        ? templateBody.replace(/\[name\]/gi, normalizedBuyerName)
        : templateBody

      setBody(personalizedBody)
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
      setShowMessageTypeError(false)
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
          <>
            <label className="composer-select-control">
              <span>Template Category</span>
              <select
                className="template-category-picker"
                value={templateCategoryId}
                aria-label="Choose reply template category"
                onChange={(event) => {
                  setTemplateCategoryId(event.target.value)
                  setSelectedTemplateId('')
                }}
              >
                <option value="">Choose category</option>
                {templateCategories.map((templateCategory) => (
                  <option value={templateCategory.id} key={templateCategory.id}>
                    {templateCategory.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="composer-select-control">
              <span>Template</span>
              <select
                className="template-picker"
                value={selectedTemplateId}
                aria-label="Insert reply template"
                disabled={!templateCategoryId || !filteredTemplates.length}
                onChange={(event) => insertTemplate(event.target.value)}
              >
                <option value="">{templateCategoryId ? 'Choose template' : 'Choose category first'}</option>
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

      <label className="field composer-editor">
        <span>Reply to buyer</span>
        <textarea
          value={body}
          onChange={(event) => {
            setBody(event.target.value)
            setDraftMessage('')
          }}
          onPaste={pasteClipboardImages}
          rows="3"
          maxLength={2000}
          placeholder="Write a reply without email, phone, external links, or abusive language"
        />
      </label>
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
      <div className="reply-composer-actions">
        <div className="composer-attachment-action">
          <input id={`reply-attachments-${conversationId}`} key={fileInputKey} type="file" multiple onChange={updateFiles} accept=".pdf,.txt,.jpg,.jpeg,.png,application/pdf,text/plain,image/jpeg,image/png" />
          <label htmlFor={`reply-attachments-${conversationId}`} title="Attach files" aria-label="Attach files"><Icon name="paperclip" /></label>
          <small>{files.length ? `${files.length} attached` : 'Attach'} · {body.length}/2000</small>
        </div>
        <label className="email-copy-checkbox" htmlFor={`reply-email-copy-${conversationId}`}>
          <input id={`reply-email-copy-${conversationId}`} type="checkbox" checked={sendCopyToEmail} disabled={isSubmitting || isValidating} onChange={(event) => setSendCopyToEmail(event.target.checked)} />
          <span>Send a copy to my email</span>
        </label>
        <button className="secondary-button compact" type="button" onClick={saveDraft} disabled={!body.trim() && !files.length}>
          Save Draft
        </button>
        <button
          className="primary-button compact"
          type="submit"
          aria-disabled={!body.trim() || !selectedTypeId || isSubmitting || isValidating}
          disabled={isSubmitting || isValidating}
        >
          {isValidating ? 'Checking...' : isSubmitting ? 'Sending...' : 'Send Reply'}
        </button>
      </div>
    </form>
  )
}
