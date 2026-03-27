import React, { FormEvent, useEffect, useRef, useState } from 'react'
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

const bulletize = (value?: string, fallback?: string[]) => {
  if (!value) return fallback || []
  return value
    .split(/\n+/)
    .map((line) => line.replace(/^[-*\d.\s]+/, '').trim())
    .filter(Boolean)
}

const toStatusClass = (value?: string) =>
  value ? value.toLowerCase().replace(/[^a-z]+/g, '-') : 'info'

const formatFileSize = (size: number) => {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

const App = () => {
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
                  statusMessage: response.message || 'Chunking started in the background.',
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
            >
              Send
            </button>
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
      <div className="slot-header">
        <div>
          <p className="slot-label">{label}</p>
          <h3>{document ? document.name : `Choose ${label}`}</h3>
        </div>
        {isClearVisible && (
          <button
            type="button"
            className="icon-button"
            aria-label={`Clear ${label}`}
            onClick={(event) => {
              event.stopPropagation()
              void onClear()
            }}
          >
            x
          </button>
        )}
      </div>

      {!document && (
        <>
          <p className="drop-title">Drag and drop a PDF here</p>
          <p className="drop-caption">Or browse to stage the file without chunking yet</p>
          <button
            type="button"
            className="ghost"
            onClick={(event) => {
              event.stopPropagation()
              onBrowse()
            }}
          >
            Choose file
          </button>
        </>
      )}

      {document && (
        <div className="slot-body">
          <p className="doc-meta">{formatFileSize(document.size)} · {label}</p>
          <p className="doc-meta">Saved {new Date(document.uploadedAt).toLocaleString()}</p>
          {document.ingestRequestedAt && (
            <p className="doc-meta">Upload requested {new Date(document.ingestRequestedAt).toLocaleString()}</p>
          )}
          <p className="status-hint">{document.statusMessage}</p>
          <div className="document-actions">
            <button
              className="ghost"
              type="button"
              onClick={(event) => {
                event.stopPropagation()
                onPreview()
              }}
            >
              View document
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

const AssistantMessage = ({ message }: { message: ChatMessage }) => {
  if (!message.response) return null
  const { response } = message
  const summary = bulletize(response.compliance_analysis, ['Analysis unavailable.'])
  const requirements = bulletize(response.naac_requirement)
  const evidence = bulletize(response.mvsr_evidence)
  const recommendations = bulletize(response.recommendations)

  return (
    <div className="chat-message message-assistant">
      <div className="message-avatar">AI</div>
      <div className="message-bubble assistant">
        <div className="assistant-panel">
          <div className="message-meta">
            <span className={`status-pill status-${toStatusClass(response.status)}`}>
              {response.status || 'Status pending'}
            </span>
            <span className="timestamp">
              {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>

          <AssistantSection title="Compliance overview" bullets={summary} />
          {requirements.length > 0 && (
            <AssistantSection title="Relevant NAAC notes" bullets={requirements} />
          )}
          {evidence.length > 0 && (
            <AssistantSection title="Referenced MVSR evidence" bullets={evidence} />
          )}
          {recommendations.length > 0 && (
            <AssistantSection title="Suggested next steps" bullets={recommendations} />
          )}
        </div>
        <InsightDeck response={response} />
      </div>
    </div>
  )
}

const AssistantSection = ({ title, bullets }: { title: string; bullets: string[] }) => (
  <div className="assistant-section">
    <p className="section-title">{title}</p>
    <ul>
      {bullets.slice(0, 4).map((item, index) => (
        <li key={`${title}-${index}`}>{item}</li>
      ))}
    </ul>
  </div>
)

const InsightDeck = ({ response }: { response: ComplianceResponse }) => {
  const complianceScore = Math.round(
    (response.compliance_score?.overall_score ?? response.confidence_score ?? 0) * 100
  )
  const highlights = bulletize(response.compliance_analysis).slice(0, 3)
  const gaps = response.compliance_score?.gap_analysis?.slice(0, 3) || []
  const suggestions = bulletize(response.recommendations).slice(0, 3)

  return (
    <div className="insight-grid">
      <div
        className="insight-card insight-score"
        style={{ ['--score-width' as any]: `${Math.min(complianceScore, 100)}%`, animationDelay: '0ms' }}
      >
        <p className="section-title">Compliance score</p>
        <p className="score-value">{isNaN(complianceScore) ? '-' : `${complianceScore}%`}</p>
        <div className="score-bar" />
      </div>

      <div className="insight-card" style={{ animationDelay: '80ms' }}>
        <p className="section-title">Key highlights</p>
        <ul>
          {(highlights.length ? highlights : ['No distinct highlights extracted yet.']).map((item, index) => (
            <li key={`highlight-${index}`}>{item}</li>
          ))}
        </ul>
      </div>

      <div className="insight-card" style={{ animationDelay: '160ms' }}>
        <p className="section-title">Missing sections</p>
        <ul>
          {(gaps.length ? gaps : ['No explicit gaps detected.']).map((item, index) => (
            <li key={`gap-${index}`}>{item}</li>
          ))}
        </ul>
      </div>

      <div className="insight-card" style={{ animationDelay: '240ms' }}>
        <p className="section-title">Recommendations</p>
        <ul>
          {(suggestions.length ? suggestions : ['Awaiting more details.']).map((item, index) => (
            <li key={`suggestion-${index}`}>{item}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default App
