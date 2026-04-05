import React, { FormEvent, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import apiService, { getErrorMessage } from './services/api'
import { ComplianceResponse } from './types'

type Role = 'system' | 'user' | 'assistant'
type DocumentType = 'naac_requirement' | 'mvsr_evidence'
type UploadState = 'idle' | 'staging' | 'staged' | 'ingesting' | 'queued' | 'error'

interface ChatMessage {
  id: string
  role: Role
  text?: string
  response?: ComplianceResponse
  timestamp: string
}

interface UploadedDocument {
  name: string
  size: number
  uploadedAt: string
  documentType: DocumentType
  previewUrl: string
  storedPath?: string
  storedFilename?: string
  ingestRequestedAt?: string
  status: UploadState
  statusMessage: string
}

const navigation = ['Uploads', 'Documents', 'Insights', 'Chat']
const samplePrompts = [
  'Summarize compliance for Criterion 1.1 using MVSR evidence',
  'Highlight missing sections in our research innovation portfolio',
  'Create recommendations for student support documentation',
  'Compare NAAC requirements with our existing governance reports',
]

const documentLabels: Record<DocumentType, string> = {
  mvsr_evidence: 'MVSR Evidence',
  naac_requirement: 'NAAC Requirements',
}

const createId = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2)



const toStatusClass = (value?: string) =>
  value ? value.toLowerCase().replace(/[^a-z]+/g, '-') : 'info'

const formatFileSize = (size: number) => {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

const formatDocumentCountMessage = (count: number) =>
  count === 1 ? '1 document' : `${count} documents`

const App = ({ username = 'User', onLogout }: { username?: string; onLogout?: () => void }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: createId(),
      role: 'system',
      text: 'Stage one MVSR evidence PDF and one NAAC requirements PDF, then click Upload documents to start chunking.',
      timestamp: new Date().toISOString(),
    },
  ])
  const [inputValue, setInputValue] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const [systemHealth, setSystemHealth] = useState<'checking' | 'healthy' | 'degraded' | 'unhealthy'>('checking')
  const [toast, setToast] = useState<string | null>(null)
  const [documents, setDocuments] = useState<Record<DocumentType, UploadedDocument | null>>({
    mvsr_evidence: null,
    naac_requirement: null,
  })
  const [isUploadStarting, setIsUploadStarting] = useState(false)
  const [previewDocumentType, setPreviewDocumentType] = useState<DocumentType | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const mvsrInputRef = useRef<HTMLInputElement>(null)
  const naacInputRef = useRef<HTMLInputElement>(null)
  const previewUrls = useRef<Partial<Record<DocumentType, string>>>({})
  const activeUploadIds = useRef<Partial<Record<DocumentType, string>>>({})

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isThinking])

  useEffect(() => {
    let active = true
    const loadHealth = async () => {
      try {
        const health = await apiService.getSystemHealth()
        if (!active) return
        setSystemHealth(health.status)
      } catch {
        if (!active) return
        setSystemHealth('unhealthy')
      }
    }
    loadHealth()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    const previewUrlMap = previewUrls.current
    return () => {
      ;(Object.keys(previewUrlMap) as DocumentType[]).forEach((documentType) => {
        const previewUrl = previewUrlMap[documentType]
        if (previewUrl) {
          URL.revokeObjectURL(previewUrl)
        }
      })
    }
  }, [])

  const handleSend = async (event?: FormEvent) => {
    event?.preventDefault()
    const trimmed = inputValue.trim()
    if (!trimmed || isThinking) return

    const userMessage: ChatMessage = {
      id: createId(),
      role: 'user',
      text: trimmed,
      timestamp: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInputValue('')
    setIsThinking(true)
    setToast(null)

    try {
      const response = await apiService.queryCompliance({
        query: trimmed,
        include_sources: true,
      })

      const assistantMessage: ChatMessage = {
        id: createId(),
        role: 'assistant',
        response,
        timestamp: new Date().toISOString(),
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (error) {
      const detail = getErrorMessage(error)
      setToast(detail)
      setMessages((prev) => [
        ...prev,
        {
          id: createId(),
          role: 'assistant',
          text: `I ran into an issue while talking to the compliance engine: ${detail}`,
          timestamp: new Date().toISOString(),
        },
      ])
    } finally {
      setIsThinking(false)
    }
  }

  const handlePromptInsert = (prompt: string) => {
    setInputValue(prompt)
  }

  const getInputRef = (documentType: DocumentType) =>
    documentType === 'mvsr_evidence' ? mvsrInputRef : naacInputRef

  const revokePreviewUrl = (documentType: DocumentType) => {
    const previewUrl = previewUrls.current[documentType]
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      delete previewUrls.current[documentType]
    }
  }

  const clearDocument = async (documentType: DocumentType) => {
    const currentDocument = documents[documentType]
    if (!currentDocument) return

    delete activeUploadIds.current[documentType]

    if (previewDocumentType === documentType) {
      setPreviewDocumentType(null)
    }

    revokePreviewUrl(documentType)
    const inputRef = getInputRef(documentType)
    if (inputRef.current) {
      inputRef.current.value = ''
    }

    setDocuments((prev) => ({
      ...prev,
      [documentType]: null,
    }))

    if (currentDocument.storedPath && currentDocument.status !== 'queued' && currentDocument.status !== 'ingesting') {
      try {
        await apiService.deleteStagedUpload(currentDocument.storedPath)
      } catch (error) {
        setToast(getErrorMessage(error))
      }
    }
  }

  const handleFileChange = async (documentType: DocumentType, file?: File | null) => {
    if (!file) return

    if (documents[documentType]) {
      await clearDocument(documentType)
    }

    const requestId = createId()
    activeUploadIds.current[documentType] = requestId

    const previewUrl = URL.createObjectURL(file)
    previewUrls.current[documentType] = previewUrl

    setDocuments((prev) => ({
      ...prev,
      [documentType]: {
        name: file.name,
        size: file.size,
        uploadedAt: new Date().toISOString(),
        documentType,
        previewUrl,
        status: 'staging',
        statusMessage: 'Saving file. Chunking will wait until you click Upload documents.',
      },
    }))
    setToast(null)

    try {
      const uploadResponse = await apiService.uploadDocument(file, documentType)

      if (activeUploadIds.current[documentType] !== requestId) {
        if (uploadResponse.stored_path) {
          try {
            await apiService.deleteStagedUpload(uploadResponse.stored_path)
          } catch {
            // Ignore cleanup errors for abandoned staged uploads.
          }
        }
        return
      }

      setDocuments((prev) => ({
        ...prev,
        [documentType]: {
          name: file.name,
          size: file.size,
          uploadedAt: uploadResponse.timestamp || new Date().toISOString(),
          documentType,
          previewUrl,
          storedPath: uploadResponse.stored_path,
          storedFilename: uploadResponse.stored_filename,
          status: 'staged',
          // Do not echo backend copy in the UI; keep it short and neutral.
          statusMessage: 'Staged.',
        },
      }))
    } catch (error) {
      if (activeUploadIds.current[documentType] !== requestId) {
        return
      }

      const detail = getErrorMessage(error)
      setToast(detail)
      revokePreviewUrl(documentType)
      delete activeUploadIds.current[documentType]
      setDocuments((prev) => ({
        ...prev,
        [documentType]: null,
      }))
    }
  }

  const handleDrop = (documentType: DocumentType, event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    const file = event.dataTransfer.files?.[0]
    handleFileChange(documentType, file)
  }

  const handleUploadDocuments = async () => {
    const stagedDocuments = (Object.entries(documents) as [DocumentType, UploadedDocument | null][])
      .filter((entry): entry is [DocumentType, UploadedDocument] => !!entry[1] && entry[1].status === 'staged' && !!entry[1].storedPath)

    if (!stagedDocuments.length || isUploadStarting) return

    setIsUploadStarting(true)
    setToast(null)
    const stagedCount = stagedDocuments.length

    const results = await Promise.all(
      stagedDocuments.map(async ([documentType, document]) => {
        setDocuments((prev) => ({
          ...prev,
          [documentType]: prev[documentType]
            ? {
                ...prev[documentType]!,
                status: 'ingesting',
                statusMessage: 'Chunking started. Storing this document in the database...',
              }
            : prev[documentType],
        }))

        try {
          const response = await apiService.ingestDocuments({
            document_type: documentType,
            file_paths: [document.storedPath!],
          })

          setDocuments((prev) => ({
            ...prev,
            [documentType]: prev[documentType]
              ? {
                  ...prev[documentType]!,
                  status: 'queued',
                  ingestRequestedAt: response.timestamp || new Date().toISOString(),
                  statusMessage: `${documentLabels[documentType]} processing started in the background.`,
                }
              : prev[documentType],
          }))

          return null
        } catch (error) {
          const detail = getErrorMessage(error)
          setDocuments((prev) => ({
            ...prev,
            [documentType]: prev[documentType]
              ? {
                  ...prev[documentType]!,
                  status: 'error',
                  statusMessage: detail,
                }
              : prev[documentType],
          }))
          return detail
        }
      })
    )

    const firstError = results.find(Boolean)
    if (firstError) {
      setToast(firstError)
    } else {
      setToast(
        stagedCount === 1
          ? 'Started processing 1 document in the background.'
          : `Started processing ${formatDocumentCountMessage(stagedCount)} in the background.`
      )
    }

    setIsUploadStarting(false)
  }

  const healthLabel =
    systemHealth === 'checking'
      ? 'Checking'
      : systemHealth === 'healthy'
        ? 'Operational'
        : systemHealth === 'degraded'
          ? 'Degraded'
          : 'Attention needed'

  const previewDocument = previewDocumentType ? documents[previewDocumentType] : null
  const hasAnyDocument = Object.values(documents).some(Boolean)
  const hasStagedDocuments = Object.values(documents).some((document) => document?.status === 'staged')

  const renderMessage = (message: ChatMessage) => {
    if (message.role === 'assistant' && message.response) {
      return <AssistantMessage key={message.id} message={message} />
    }

    return (
      <div key={message.id} className={`chat-message message-${message.role}`}>
        <div className="message-avatar">{message.role === 'user' ? 'You' : 'Guide'}</div>
        <div className="message-bubble">
          <p>{message.text}</p>
          <span className="timestamp">{new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <p className="brand-name">EduBot</p>
          <h1>Compliance Studio</h1>
          <p className="subtitle">Built for NAAC excellence</p>
        </div>
        <nav>
          {navigation.map((item) => (
            <button
              key={item}
              className={`nav-item ${item === 'Chat' ? 'active' : ''}`}
              type="button"
            >
              <span>{item}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-status">
          <p>System status</p>
          <span className={`status-pill status-${systemHealth}`}>{healthLabel}</span>
        </div>
        <div className="sidebar-user">
          <p className="sidebar-user-name">👤 {username}</p>
          {onLogout && (
            <button type="button" className="logout-btn" onClick={onLogout}>
              Sign out
            </button>
          )}
        </div>
      </aside>

      <main className="workspace">
        <div className="chat-surface">
          <section className="document-context">
            <div className="context-header">
              <div>
                <p className="eyebrow">Document workspace</p>
                <h2>Separate MVSR evidence and NAAC requirements uploads</h2>
                <p className="context-copy">Each section keeps its own PDF. The database upload starts only after you click Upload documents.</p>
              </div>
              <button
                className="primary upload-trigger"
                type="button"
                onClick={handleUploadDocuments}
                disabled={isUploadStarting || !hasStagedDocuments}
              >
                {isUploadStarting ? 'Starting upload...' : 'Upload documents'}
              </button>
            </div>

            <input
              ref={mvsrInputRef}
              type="file"
              accept="application/pdf"
              hidden
              onChange={(event) => handleFileChange('mvsr_evidence', event.target.files?.[0])}
            />
            <input
              ref={naacInputRef}
              type="file"
              accept="application/pdf"
              hidden
              onChange={(event) => handleFileChange('naac_requirement', event.target.files?.[0])}
            />

            <div className="upload-grid">
              {(['mvsr_evidence', 'naac_requirement'] as DocumentType[]).map((documentType) => (
                <UploadSlot
                  key={documentType}
                  document={documents[documentType]}
                  label={documentLabels[documentType]}
                  onBrowse={() => getInputRef(documentType).current?.click()}
                  onClear={() => clearDocument(documentType)}
                  onPreview={() => setPreviewDocumentType(documentType)}
                  onDrop={(event) => handleDrop(documentType, event)}
                />
              ))}
            </div>
          </section>

          <section className="chat-feed">
            {!hasAnyDocument && (
              <div className="sample-prompts">
                <p>Need inspiration?</p>
                <div className="chips">
                  {samplePrompts.map((prompt) => (
                    <button key={prompt} type="button" onClick={() => handlePromptInsert(prompt)}>
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map(renderMessage)}

            {isThinking && (
              <div className="typing-indicator">
                <span />
                <span />
                <span />
                <p>Generating insights...</p>
              </div>
            )}

            <div ref={chatEndRef} />
          </section>

          <form className="input-dock" onSubmit={handleSend}>
            <div className="input-box">
              <textarea
                className="chat-input"
                placeholder="Ask anything about compliance, gaps, or evidence..."
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                rows={1}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    handleSend(event)
                  }
                }}
              />
              <button
                type="submit"
                className="chat-send"
                disabled={!inputValue.trim() || isThinking}
                title="Send message"
              >
                ↑
              </button>
            </div>
          </form>
        </div>
      </main>

      {toast && (
        <div className="toast" role="status">{toast}</div>
      )}

      {previewDocument && (
        <div className="preview-overlay" role="dialog" aria-modal="true">
          <div className="preview-panel">
            <div className="preview-header">
              <div>
                <p className="eyebrow">Previewing</p>
                <h3>{previewDocument.name}</h3>
              </div>
              <button type="button" className="ghost" onClick={() => setPreviewDocumentType(null)}>
                Close
              </button>
            </div>
            <iframe src={previewDocument.previewUrl} title={previewDocument.name} />
          </div>
        </div>
      )}
    </div>
  )
}

const UploadSlot = ({
  document,
  label,
  onBrowse,
  onClear,
  onPreview,
  onDrop,
}: {
  document: UploadedDocument | null
  label: string
  onBrowse: () => void
  onClear: () => Promise<void> | void
  onPreview: () => void
  onDrop: (event: React.DragEvent<HTMLDivElement>) => void
}) => {
  const isClickable = !document
  const isClearVisible = !!document && document.status !== 'queued' && document.status !== 'ingesting'

  return (
    <div
      className={`upload-slot state-${document?.status || 'idle'}`}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onClick={isClickable ? onBrowse : undefined}
      onKeyDown={
        isClickable
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar' || event.key === 'Space') {
                event.preventDefault()
                onBrowse()
              }
            }
          : undefined
      }
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
    >
      <div className="slot-info">
        <p className="slot-label">{label}</p>
        {!document ? (
          <h3 className="slot-empty-text">Drop PDF here or Browse</h3>
        ) : (
          <div className="doc-details">
            <h3 className="doc-name" title={document.name}>{document.name}</h3>
            <span className="doc-meta-inline">
              {formatFileSize(document.size)} • {document.statusMessage || (document.status === 'staged' ? 'Ready to upload' : document.status)}
            </span>
          </div>
        )}
      </div>

      <div className="slot-actions">
        {document && (
          <button
            type="button"
            className="ghost sm"
            onClick={(event) => {
              event.stopPropagation()
              onPreview()
            }}
            title="Preview Document"
          >
            👁
          </button>
        )}
        {isClearVisible && (
          <button
            type="button"
            className="icon-button sm"
            onClick={(event) => {
              event.stopPropagation()
              void onClear()
            }}
            title="Remove Document"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  )
}

const AssistantMessage = ({ message }: { message: ChatMessage }) => {
  if (!message.response) return null
  const { response } = message

  // Logging actual output vs what will be rendered
  console.log('--- ACTUAL RAW BACKEND RESPONSE ---')
  console.log(response)
  console.log('--- DISPLAYED UI TEXT ---')
  console.log(response.compliance_analysis)

  const complianceScore = response.compliance_score?.overall_score ?? response.confidence_score

  return (
    <div className="chat-message message-assistant">
      <div className="message-avatar">AI</div>
      <div className="message-bubble assistant">
        <div className="assistant-panel" style={{ display: 'block' }}>
          <div className="message-meta" style={{ marginBottom: '1rem' }}>
            <span className={`status-pill status-${toStatusClass(response.status)}`}>
              {response.status || 'Status pending'}
            </span>
            {complianceScore !== undefined && (
              <span className="status-pill status-info" style={{ marginLeft: '10px', background: 'var(--bg-card)', color: 'var(--text-secondary)' }}>
                Compliance: {Math.round(complianceScore * 100)}%
              </span>
            )}
            <span className="timestamp" style={{ marginLeft: 'auto' }}>
              {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>

          <div className="assistant-single-answer" style={{ 
            color: 'var(--text-primary)', 
            lineHeight: '1.6', 
            fontSize: '15px' 
          }}>
            <ReactMarkdown>{response.compliance_analysis || 'Analysis unavailable.'}</ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
