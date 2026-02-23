import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react'
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
    const loadingMessage: ChatMessage = {
      id: uuidv4(),
      type: 'assistant',
      content: 'Analyzing your query and searching knowledge base...',
      timestamp: new Date(),
      isLoading: true,
    }
    setMessages((prev) => [...prev, loadingMessage])

    try {
      const response: ComplianceResponse = await apiService.queryCompliance({
        query: query.trim(),
        filters,
        include_sources: true,
      })

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
  let formatted = ''

  // NAAC Requirements
  if (response.naac_requirement) {
    formatted += `## 📋 NAAC Requirements\n\n${response.naac_requirement}\n\n`
  }

  // MVSR Evidence
  if (response.mvsr_evidence) {
    formatted += `## 🎓 MVSR Evidence\n\n${response.mvsr_evidence}\n\n`
  }

  // NAAC Mapping
  if (response.naac_mapping) {
    formatted += `## 🗺️ NAAC Criterion Mapping\n\n${response.naac_mapping}\n\n`
  }

  // Compliance Analysis
  if (response.compliance_analysis) {
    formatted += `## 🔍 Compliance Analysis\n\n${response.compliance_analysis}\n\n`
  }

  // Status
  if (response.status) {
    const statusIcon = getStatusIcon(response.status)
    formatted += `## ${statusIcon} Compliance Status\n\n**${response.status}**\n\n`
  }

  // Recommendations
  if (response.recommendations) {
    formatted += `## 💡 Recommendations\n\n${response.recommendations}\n\n`
  }

  // Confidence Score
  if (response.confidence_score !== undefined) {
    const confidencePercent = Math.round(response.confidence_score * 100)
    formatted += `## 📊 Analysis Confidence\n\n**${confidencePercent}%** confidence in this analysis\n\n`
  }

  // Compliance Score Details
  if (response.compliance_score) {
    formatted += `## 📈 Detailed Scoring\n\n`
    
    if (response.compliance_score.overall_score !== undefined) {
      formatted += `**Overall Compliance Score:** ${Math.round(response.compliance_score.overall_score * 100)}%\n\n`
    }

    if (response.compliance_score.category_scores) {
      formatted += `**Category Breakdown:**\n`
      Object.entries(response.compliance_score.category_scores).forEach(([category, score]) => {
        const percentage = Math.round((score as number) * 100)
        formatted += `- ${category}: ${percentage}%\n`
      })
      formatted += '\n'
    }

    if (response.compliance_score.gap_analysis) {
      formatted += `**Gap Areas:**\n`
      response.compliance_score.gap_analysis.forEach((gap: string) => {
        formatted += `- ${gap}\n`
      })
      formatted += '\n'
    }
  }

  return formatted.trim()
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