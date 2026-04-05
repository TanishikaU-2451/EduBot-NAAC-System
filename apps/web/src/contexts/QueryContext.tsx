import React, { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { ChatMessage, QueryContextType, ComplianceResponse } from '../types'
import apiService, { getErrorMessage } from '../services/api'

const QueryContext = createContext<QueryContextType | undefined>(undefined)

interface QueryProviderProps {
  children: ReactNode
}

export const QueryProvider: React.FC<QueryProviderProps> = ({ children }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uuidv4(),
      type: 'system',
      content: '👋 Welcome to the NAAC Compliance Intelligence System! I can help you understand NAAC requirements, find MVSR evidence, and analyze compliance gaps. Ask me anything about NAAC accreditation!',
      timestamp: new Date(),
    },
  ])
  const [isLoading, setIsLoading] = useState(false)
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const loadingMsgIdRef = useRef<string | null>(null)

  const sendQuery = useCallback(async (query: string, filters?: Record<string, any>) => {
    if (!query.trim()) return

    const userMessage: ChatMessage = {
      id: uuidv4(),
      type: 'user',
      content: query.trim(),
      timestamp: new Date(),
    }

    // Add user message
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)

    // Add loading message
    const loadingId = uuidv4()
    loadingMsgIdRef.current = loadingId
    const loadingMessage: ChatMessage = {
      id: loadingId,
      type: 'assistant',
      content: '⏳ Analyzing your query... (this may take up to 60 seconds)',
      timestamp: new Date(),
      isLoading: true,
    }
    setMessages((prev) => [...prev, loadingMessage])

    // Update elapsed time every 5 seconds
    let elapsed = 0
    timerRef.current = setInterval(() => {
      elapsed += 5
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === loadingId
            ? { ...msg, content: `⏳ Still thinking... (${elapsed}s elapsed)` }
            : msg
        )
      )
    }, 5000)

    try {
      const response: ComplianceResponse = await apiService.queryCompliance({
        query: query.trim(),
        filters,
        include_sources: true,
      })

      if (timerRef.current) clearInterval(timerRef.current)

      // Remove loading message and add response
      setMessages((prev) => {
        const withoutLoading = prev.filter((msg) => !msg.isLoading)
        const assistantMessage: ChatMessage = {
          id: uuidv4(),
          type: 'assistant',
          content: formatComplianceResponse(response),
          timestamp: new Date(),
          complianceResponse: response,
        }
        return [...withoutLoading, assistantMessage]
      })
    } catch (error) {
      if (timerRef.current) clearInterval(timerRef.current)
      // Remove loading message and add error
      setMessages((prev) => {
        const withoutLoading = prev.filter((msg) => !msg.isLoading)
        const errorMessage: ChatMessage = {
          id: uuidv4(),
          type: 'assistant',
          content: `❌ Sorry, I encountered an error processing your query: ${getErrorMessage(error)}`,
          timestamp: new Date(),
        }
        return [...withoutLoading, errorMessage]
      })
    } finally {
      setIsLoading(false)
    }
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([
      {
        id: uuidv4(),
        type: 'system',
        content: '👋 Welcome to the NAAC Compliance Intelligence System! I can help you understand NAAC requirements, find MVSR evidence, and analyze compliance gaps. Ask me anything about NAAC accreditation!',
        timestamp: new Date(),
      },
    ])
  }, [])

  return (
    <QueryContext.Provider value={{ messages, isLoading, sendQuery, clearMessages }}>
      {children}
    </QueryContext.Provider>
  )
}

export const useQuery = () => {
  const context = useContext(QueryContext)
  if (context === undefined) {
    throw new Error('useQuery must be used within a QueryProvider')
  }
  return context
}

// Helper function to format compliance response
const formatComplianceResponse = (response: ComplianceResponse): string => {
  const parts: string[] = []

  // Primary answer — always show compliance_analysis as the main answer
  if (response.compliance_analysis) {
    parts.push(response.compliance_analysis)
  }

  // Status badge
  if (response.status) {
    const icon = getStatusIcon(response.status)
    parts.push(`\n---\n${icon} **Status:** ${response.status}`)
  }

  // NAAC requirements if meaningful
  if (response.naac_requirement && !response.naac_requirement.startsWith('NAAC context retrieved')) {
    parts.push(`\n**📋 NAAC Requirements:**\n${response.naac_requirement}`)
  }

  // MVSR evidence if meaningful
  if (response.mvsr_evidence && !response.mvsr_evidence.startsWith('MVSR evidence retrieved')) {
    parts.push(`\n**🎓 MVSR Evidence:**\n${response.mvsr_evidence}`)
  }

  // Recommendations if present
  if (response.recommendations) {
    parts.push(`\n**💡 Recommendations:**\n${response.recommendations}`)
  }

  return parts.join('\n').trim() || 'I was unable to generate a response. Please try again.'
}

const getStatusIcon = (status: string): string => {
  const lowerStatus = status.toLowerCase()
  if (lowerStatus.includes('compliant') && !lowerStatus.includes('non')) {
    return '✅'
  } else if (lowerStatus.includes('partial')) {
    return '⚠️'
  } else if (lowerStatus.includes('non-compliant')) {
    return '❌'
  } else if (lowerStatus.includes('gap')) {
    return '🔄'
  } else {
    return '📋'
  }
}