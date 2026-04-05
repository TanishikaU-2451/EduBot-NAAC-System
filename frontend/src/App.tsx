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
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isDarkMode, setIsDarkMode] = useState(false)
  
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

  // Apply dark mode class to root html/body
  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [isDarkMode])

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

      if (activeUploadIds.current[documentType] !== requestId) return

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
          statusMessage: 'Staged.',
        },
      }))
    } catch (error) {
      if (activeUploadIds.current[documentType] !== requestId) return
      
      const detail = getErrorMessage(error)
      setToast(detail)
      revokePreviewUrl(documentType)
      delete activeUploadIds.current[documentType]
      setDocuments((prev) => ({ ...prev, [documentType]: null }))
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
            [documentType]: prev[documentType] ? { ...prev[documentType]!, status: 'error', statusMessage: detail } : prev[documentType],
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

  const hasAnyDocument = Object.values(documents).some(Boolean)
  const hasStagedDocuments = Object.values(documents).some((document) => document?.status === 'staged')
  const previewDocument = previewDocumentType ? documents[previewDocumentType] : null

  return (
    <div className="flex h-screen overflow-hidden font-sans text-themeLight-text bg-themeLight-bg secondary dark:text-themeDark-text dark:bg-themeDark-bg transition-colors duration-300">
      
      {/* Sidebar - Collapsible */}
      <aside className={`flex flex-col border-r border-themeLight-border dark:border-themeDark-border bg-themeLight-bgSecondary dark:bg-themeDark-bgSecondary transition-all duration-300 ${isSidebarOpen ? 'w-64' : 'w-0 opacity-0 overflow-hidden'}`}>
        <div className="flex flex-col h-full p-4">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-themeLight-buttonPrimary dark:bg-themeDark-buttonPrimary flex items-center justify-center text-white font-bold text-xs tracking-wider">
                EB
              </div>
              <h1 className="font-semibold text-lg tracking-tight">EduBot</h1>
            </div>
            <button onClick={() => setIsSidebarOpen(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1" title="Close Sidebar">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto">
            <nav className="space-y-1 mb-6">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3 px-2">Navigation</p>
              {navigation.map((item) => (
                <button
                  key={item}
                  className={`w-full text-left px-3 py-2 rounded-xl text-sm font-medium transition-colors ${item === 'Chat' ? 'bg-themeLight-buttonPrimary/10 dark:bg-themeDark-buttonPrimary/20 text-themeLight-buttonPrimary dark:text-gray-200' : 'hover:bg-themeLight-bg dark:hover:bg-themeDark-bg text-gray-600 dark:text-gray-400'}`}
                >
                  {item}
                </button>
              ))}
            </nav>

            <div className="mt-8">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3 px-2">System Status</p>
              <div className="px-3 py-2 bg-themeLight-bg dark:bg-themeDark-bg rounded-xl border border-themeLight-border dark:border-themeDark-border flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${systemHealth === 'healthy' ? 'bg-green-500' : systemHealth === 'degraded' ? 'bg-yellow-500' : systemHealth === 'unhealthy' ? 'bg-red-500' : 'bg-gray-400 animate-pulse'}`}></span>
                <span className="text-sm font-medium capitalize">{systemHealth}</span>
              </div>
            </div>
          </div>

          {/* User Profile */}
          <div className="pt-4 border-t border-themeLight-border dark:border-themeDark-border flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-themeLight-accent dark:bg-themeDark-accent text-white flex items-center justify-center font-medium text-sm">
                {username.charAt(0).toUpperCase()}
              </div>
              <span className="font-medium text-sm truncate max-w-[100px]">{username}</span>
            </div>
            {onLogout && (
              <button 
                onClick={() => { console.log('Logout Clicked'); onLogout(); }} 
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1" 
                title="Sign out"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* Main Workspace */}
      <main className="flex-1 flex flex-col min-w-0 relative">
        <header className="h-16 flex items-center justify-between px-6 border-b border-themeLight-border dark:border-themeDark-border sticky top-0 z-10 bg-themeLight-bg/80 dark:bg-themeDark-bg/80 backdrop-blur-md">
          <div className="flex items-center gap-4">
            {!isSidebarOpen && (
              <button onClick={() => setIsSidebarOpen(true)} className="p-2 -ml-2 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 transition-colors" title="Open Sidebar">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
              </button>
            )}
            <h2 className="font-medium text-lg text-themeLight-text dark:text-themeDark-text">Compliance model</h2>
          </div>
          
          {/* Theme Toggle */}
          <button 
            onClick={() => setIsDarkMode(!isDarkMode)} 
            className="w-10 h-10 rounded-full flex items-center justify-center bg-themeLight-bgSecondary dark:bg-themeDark-bgSecondary text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 transition-all focus:outline-none focus:ring-2 focus:ring-themeLight-accent dark:focus:ring-themeDark-accent"
            title="Toggle theme"
          >
            {isDarkMode ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
            )}
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-8 scroll-smooth">
          {/* Document Context Header Area */}
          <div className="max-w-4xl mx-auto mb-12">
            <div className="bg-themeLight-bgSecondary/50 dark:bg-themeDark-bgSecondary/30 rounded-2xl p-6 border border-themeLight-border dark:border-themeDark-border shadow-soft dark:shadow-soft-dark">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                <div>
                  <p className="text-xs font-semibold text-themeLight-accent dark:text-themeDark-accent uppercase tracking-widest mb-1">Document Workspace</p>
                  <h3 className="text-xl font-medium mb-1">Evidence & Requirements</h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Select files to chunk and upload to the knowledge base.</p>
                </div>
                <button
                  className="px-5 py-2.5 bg-themeLight-buttonPrimary hover:bg-themeLight-buttonHover dark:bg-themeDark-buttonPrimary dark:hover:bg-themeDark-buttonHover text-white rounded-xl shadow-sm transition-all font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={handleUploadDocuments}
                  disabled={isUploadStarting || !hasStagedDocuments}
                >
                  {isUploadStarting ? 'Uploading...' : 'Launch Knowledge Upload'}
                </button>
              </div>

              <input ref={mvsrInputRef} type="file" accept="application/pdf" hidden onChange={(e) => handleFileChange('mvsr_evidence', e.target.files?.[0])} />
              <input ref={naacInputRef} type="file" accept="application/pdf" hidden onChange={(e) => handleFileChange('naac_requirement', e.target.files?.[0])} />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
            </div>
          </div>

          <div className="max-w-4xl mx-auto space-y-8 pb-32">
            {!hasAnyDocument && (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <p className="text-gray-500 dark:text-gray-400 mb-6 font-medium">Try asking about...</p>
                <div className="flex flex-wrap justify-center gap-3">
                  {samplePrompts.map((prompt) => (
                    <button key={prompt} onClick={() => handlePromptInsert(prompt)} className="bg-themeLight-bgSecondary hover:bg-themeLight-border dark:bg-themeDark-bgSecondary dark:hover:bg-themeDark-border text-xs md:text-sm px-4 py-2 rounded-2xl transition-colors border border-themeLight-border dark:border-themeDark-border text-gray-700 dark:text-gray-300">
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => {
              if (message.role === 'assistant' && message.response) {
                return <AssistantMessage key={message.id} message={message} />
              }
              if (message.role === 'system') return null; // Hide system message purely meant to prompt about PDF drop

              return (
                <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] rounded-3xl px-6 py-4 shadow-sm ${message.role === 'user' ? 'bg-themeLight-messageUser dark:bg-themeDark-messageUser text-themeLight-text dark:text-themeDark-text rounded-br-sm' : 'bg-themeLight-messageAI dark:bg-themeDark-messageAI border border-themeLight-border dark:border-themeDark-border rounded-bl-sm'}`}>
                    <p className="text-[15px] leading-relaxed">{message.text}</p>
                  </div>
                </div>
              )
            })}

            {isThinking && (
              <div className="flex justify-start">
                <div className="bg-themeLight-messageAI dark:bg-themeDark-messageAI border border-themeLight-border dark:border-themeDark-border rounded-3xl rounded-bl-sm px-6 py-4 shadow-sm flex items-center gap-2">
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></span>
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></span>
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></span>
                </div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>
        </div>

        {/* Input Dock */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-themeLight-bg via-themeLight-bg to-transparent dark:from-themeDark-bg dark:via-themeDark-bg pt-10 pb-6 px-6 z-20">
          <div className="max-w-4xl mx-auto">
            <form onSubmit={handleSend} className="relative flex items-center">
              <button type="button" onClick={() => getInputRef('mvsr_evidence').current?.click()} className="absolute left-4 p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors" title="Attach Document" >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
              </button>
              <textarea
                className="w-full bg-themeLight-messageAI dark:bg-themeDark-messageAI border border-themeLight-border dark:border-themeDark-border rounded-2xl pl-14 pr-16 py-4 focus:outline-none focus:ring-2 focus:ring-themeLight-accent/50 dark:focus:ring-themeDark-accent/50 resize-none shadow-soft dark:shadow-soft-dark text-[15px] placeholder-gray-400 transition-all"
                placeholder="Ask Claude about compliance, gaps, or evidence..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                rows={1}
                style={{ minHeight: '60px', maxHeight: '200px' }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend(e);
                  }
                }}
              />
              <button
                type="submit"
                disabled={!inputValue.trim() || isThinking}
                className="absolute right-4 w-8 h-8 flex items-center justify-center rounded-xl bg-themeLight-buttonPrimary dark:bg-themeDark-buttonPrimary hover:bg-themeLight-buttonHover dark:hover:bg-themeDark-buttonHover text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="19" x2="12" y2="5"></line><polyline points="5 12 12 5 19 12"></polyline></svg>
              </button>
            </form>
            <p className="text-center text-xs text-gray-400 mt-3 font-medium">EduBot is an AI assistant and may occasionally make mistakes.</p>
          </div>
        </div>
      </main>

      {/* Toast Notification */}
      {toast && (
        <div className="absolute top-6 left-1/2 transform -translate-x-1/2 bg-gray-900 text-white px-6 py-3 rounded-full text-sm shadow-xl z-50 animate-bounce">
          {toast}
        </div>
      )}

      {/* Document Preview Modal */}
      {previewDocument && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 md:p-12">
          <div className="bg-themeLight-bg dark:bg-themeDark-bg rounded-2xl shadow-2xl w-full max-w-6xl h-full flex flex-col overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-themeLight-border dark:border-themeDark-border">
              <div>
                <p className="text-xs uppercase tracking-wider text-gray-500 font-semibold mb-1">Previewing</p>
                <h3 className="font-medium text-lg truncate max-w-lg">{previewDocument.name}</h3>
              </div>
              <button onClick={() => setPreviewDocumentType(null)} className="p-2 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 bg-gray-100 dark:bg-gray-800 rounded-xl transition-colors">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            <iframe src={previewDocument.previewUrl} title={previewDocument.name} className="flex-1 w-full border-none bg-gray-100" />
          </div>
        </div>
      )}
    </div>
  )
}

const UploadSlot = ({ document, label, onBrowse, onClear, onPreview, onDrop }: {
  document: UploadedDocument | null
  label: string
  onBrowse: () => void
  onClear: () => Promise<void> | void
  onPreview: () => void
  onDrop: (event: React.DragEvent<HTMLDivElement>) => void
}) => {
  const isClickable = !document;
  const isClearVisible = !!document && document.status !== 'queued' && document.status !== 'ingesting';

  return (
    <div
      onClick={isClickable ? onBrowse : undefined}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
      className={`relative p-5 rounded-2xl border-2 border-dashed transition-all group ${isClickable ? 'border-themeLight-border dark:border-themeDark-border hover:border-themeLight-accent dark:hover:border-themeDark-accent hover:bg-themeLight-bg/50 dark:hover:bg-themeDark-bgSecondary/50 cursor-pointer' : 'border-transparent bg-themeLight-bg dark:bg-themeDark-bg shadow-sm'}`}
    >
      <div className="flex flex-col gap-2">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest">{label}</p>
        {!document ? (
          <div className="py-4 text-center">
            <svg className="w-8 h-8 mx-auto mb-2 text-gray-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5"><path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" /></svg>
            <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Click or drag PDF here</p>
          </div>
        ) : (
          <div className="flex items-center justify-between mt-2">
            <div className="min-w-0 flex-1">
              <h4 className="font-medium text-sm text-themeLight-text dark:text-themeDark-text truncate pr-4" title={document.name}>{document.name}</h4>
              <p className="text-xs text-gray-500 mt-1 flex items-center gap-2">
                <span>{formatFileSize(document.size)}</span>
                <span className="w-1 h-1 rounded-full bg-gray-300"></span>
                <span className={`capitalize ${document.status === 'staged' ? 'text-green-600 dark:text-green-500' : ''}`}>{document.status === 'staged' ? 'Ready' : document.statusMessage || document.status}</span>
              </p>
            </div>
            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button type="button" onClick={(e) => { e.stopPropagation(); onPreview() }} className="p-1.5 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors" title="Preview">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
              </button>
              {isClearVisible && (
                <button type="button" onClick={(e) => { e.stopPropagation(); void onClear() }} className="p-1.5 text-red-400 hover:text-red-600 transition-colors" title="Remove">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const AssistantMessage = ({ message }: { message: ChatMessage }) => {
  if (!message.response) return null
  const { response } = message
  const complianceScore = response.compliance_score?.overall_score ?? response.confidence_score

  return (
    <div className="flex justify-start max-w-3xl">
      <div className="w-8 h-8 rounded-full bg-themeLight-buttonPrimary dark:bg-themeDark-buttonPrimary flex-shrink-0 flex items-center justify-center text-white mt-1 mr-4 shadow-sm">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="2"></circle><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48 0a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"></path></svg>
      </div>
      <div className="flex-1">
        {complianceScore !== undefined && (
          <div className="inline-block bg-themeLight-bgSecondary dark:bg-themeDark-bgSecondary text-xs rounded-full px-2 py-1 mb-2 font-medium">
            Compliance Score: {Math.round(complianceScore * 100)}%
          </div>
        )}
        <div className="prose prose-sm md:prose-base dark:prose-invert prose-p:leading-relaxed text-themeLight-text dark:text-themeDark-text">
          <ReactMarkdown>{response.compliance_analysis || 'Analysis unavailable.'}</ReactMarkdown>
        </div>

        {/* Message Actions */}
        <div className="flex items-center gap-3 mt-4 opacity-50 hover:opacity-100 transition-opacity">
          <button onClick={() => console.log('Copy clicked')} className="p-1.5 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 transition-colors bg-themeLight-bgSecondary dark:bg-themeDark-bgSecondary rounded-md" title="Copy">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
          </button>
          <button onClick={() => console.log('Edit clicked')} className="p-1.5 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 transition-colors bg-themeLight-bgSecondary dark:bg-themeDark-bgSecondary rounded-md" title="Edit">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
          </button>
          <button onClick={() => console.log('Regenerate clicked')} className="p-1.5 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 transition-colors bg-themeLight-bgSecondary dark:bg-themeDark-bgSecondary rounded-md" title="Regenerate">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
          </button>
          <div className="w-px h-4 bg-gray-300 dark:bg-gray-700 mx-1"></div>
          <button onClick={() => console.log('Thumbs Up clicked')} className="p-1.5 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 transition-colors bg-themeLight-bgSecondary dark:bg-themeDark-bgSecondary rounded-md" title="Thumbs Up">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path></svg>
          </button>
          <button onClick={() => console.log('Thumbs Down clicked')} className="p-1.5 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 transition-colors bg-themeLight-bgSecondary dark:bg-themeDark-bgSecondary rounded-md" title="Thumbs Down">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"></path></svg>
          </button>
        </div>
      </div>
    </div>
  )
}

export default App