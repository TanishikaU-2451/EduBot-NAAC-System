import React, { FormEvent, useEffect, useRef, useState } from 'react'
import apiService, { getErrorMessage } from './services/api'
import { ComplianceResponse } from './types'

type Role = 'system' | 'user' | 'assistant'
type DocumentType = 'naac_requirement' | 'mvsr_evidence'

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
  previewUrl?: string
}

const navigation = ['Uploads', 'Documents', 'Insights', 'Chat']
const samplePrompts = [
  'Summarize compliance for Criterion 1.1 using MVSR evidence',
  'Highlight missing sections in our research innovation portfolio',
  'Create recommendations for student support documentation',
  'Compare NAAC requirements with our existing governance reports',
]

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
      text: 'Upload a compliance document to begin. I will extract the context, answer your questions, and surface insights without jargon.',
      timestamp: new Date().toISOString(),
    },
  ])
  const [inputValue, setInputValue] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const [documentType, setDocumentType] = useState<DocumentType>('mvsr_evidence')
  const [uploadedDoc, setUploadedDoc] = useState<UploadedDocument | null>(null)
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')
  const [statusMessage, setStatusMessage] = useState('')
  const [systemHealth, setSystemHealth] = useState<'checking' | 'healthy' | 'degraded' | 'unhealthy'>('checking')
  const [toast, setToast] = useState<string | null>(null)
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const previousPreviewUrl = useRef<string | null>(null)

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
    return () => {
      if (previousPreviewUrl.current) {
        URL.revokeObjectURL(previousPreviewUrl.current)
      }
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

  const handleFileChange = async (file?: File | null) => {
    if (!file) return

    if (previousPreviewUrl.current) {
      URL.revokeObjectURL(previousPreviewUrl.current)
    }

    const previewUrl = URL.createObjectURL(file)
    previousPreviewUrl.current = previewUrl

    setUploadStatus('uploading')
    setStatusMessage('Uploading and analyzing…')
    setToast(null)

    try {
      const uploadResponse = await apiService.uploadDocument(file, documentType)
      const uploadedAt = uploadResponse.timestamp || new Date().toISOString()
      setUploadedDoc({
        name: file.name,
        size: file.size,
        uploadedAt,
        documentType,
        previewUrl,
      })
      setUploadStatus('success')
      setStatusMessage('Document ingested. Insights are ready to explore.')
    } catch (error) {
      const detail = getErrorMessage(error)
      setUploadStatus('error')
      setStatusMessage(detail)
      setToast(detail)
      URL.revokeObjectURL(previewUrl)
      previousPreviewUrl.current = null
    }
  }

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    const file = event.dataTransfer.files?.[0]
    handleFileChange(file)
  }

  const healthLabel =
    systemHealth === 'checking'
      ? 'Checking'
      : systemHealth === 'healthy'
        ? 'Operational'
        : systemHealth === 'degraded'
          ? 'Degraded'
          : 'Attention needed'

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
                <h2>{uploadedDoc ? uploadedDoc.name : 'Upload a document to begin analysis'}</h2>
              </div>
              {uploadedDoc?.previewUrl && (
                <button className="ghost" type="button" onClick={() => setIsPreviewOpen(true)}>
                  View document
                </button>
              )}
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              hidden
              onChange={(event) => handleFileChange(event.target.files?.[0])}
            />

            {!uploadedDoc && (
              <div
                className={`upload-dropzone state-${uploadStatus}`}
                role="button"
                tabIndex={0}
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar' || event.key === 'Space') {
                    event.preventDefault()
                    fileInputRef.current?.click()
                  }
                }}
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleDrop}
              >
                <p className="drop-title">Drag & drop a PDF, or browse to upload</p>
                <p className="drop-caption">Upload a document to begin analysis</p>
                <div className="doc-type-toggle">
                  {(['mvsr_evidence', 'naac_requirement'] as DocumentType[]).map((type) => (
                    <button
                      key={type}
                      type="button"
                      className={type === documentType ? 'active' : ''}
                      onClick={(event) => {
                        event.stopPropagation()
                        setDocumentType(type)
                      }}
                    >
                      {type === 'mvsr_evidence' ? 'MVSR Evidence' : 'NAAC Requirement'}
                    </button>
                  ))}
                </div>
                <button type="button" className="primary" onClick={() => fileInputRef.current?.click()}>
                  Choose file
                </button>
                {statusMessage && <p className="status-hint">{statusMessage}</p>}
              </div>
            )}

            {uploadedDoc && (
              <div className="document-card">
                <div>
                  <p className="doc-name">{uploadedDoc.name}</p>
                  <p className="doc-meta">{formatFileSize(uploadedDoc.size)} · {uploadedDoc.documentType === 'mvsr_evidence' ? 'MVSR Evidence' : 'NAAC Requirement'}</p>
                  <p className="doc-meta">Uploaded {new Date(uploadedDoc.uploadedAt).toLocaleString()}</p>
                  {statusMessage && <p className="status-hint in-card">{statusMessage}</p>}
                </div>
                <div className="document-actions">
                  <button className="ghost" type="button" onClick={() => fileInputRef.current?.click()}>
                    Replace
                  </button>
                  {uploadedDoc.previewUrl && (
                    <button className="primary" type="button" onClick={() => setIsPreviewOpen(true)}>
                      View document
                    </button>
                  )}
                </div>
              </div>
            )}
          </section>

          <section className="chat-feed">
            {!uploadedDoc && (
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
                <p>Generating insights…</p>
              </div>
            )}

            <div ref={chatEndRef} />
          </section>

          <form className="input-dock" onSubmit={handleSend}>
            <textarea
              className="chat-input"
              placeholder="Ask anything about compliance, gaps, or evidence…"
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

      {isPreviewOpen && uploadedDoc?.previewUrl && (
        <div className="preview-overlay" role="dialog" aria-modal="true">
          <div className="preview-panel">
            <div className="preview-header">
              <div>
                <p className="eyebrow">Previewing</p>
                <h3>{uploadedDoc.name}</h3>
              </div>
              <button type="button" className="ghost" onClick={() => setIsPreviewOpen(false)}>
                Close
              </button>
            </div>
            <iframe src={uploadedDoc.previewUrl} title={uploadedDoc.name} />
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
        <p className="score-value">{isNaN(complianceScore) ? '—' : `${complianceScore}%`}</p>
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