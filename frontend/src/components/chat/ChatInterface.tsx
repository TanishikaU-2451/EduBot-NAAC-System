import React, { useState, useRef, useEffect } from 'react'
import {
  Box,
  Paper,
  TextField,
  IconButton,
  Typography,
  List,
  ListItem,
  Avatar,
  Chip,
  Button,
  Divider,
  Collapse,
  Card,
  CardContent,
} from '@mui/material'
import {
  Send as SendIcon,
  Person as PersonIcon,
  SmartToy as BotIcon,
  Clear as ClearIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Info as InfoIcon,
} from '@mui/icons-material'
import ReactMarkdown from 'react-markdown'
import { useQuery } from '../../contexts/QueryContext'
import { ChatMessage } from '../../types'

const ChatInterface: React.FC = () => {
  const [inputValue, setInputValue] = useState('')
  const [expandedDetails, setExpandedDetails] = useState<Record<string, boolean>>({})
  const { messages, isLoading, sendQuery, clearMessages } = useQuery()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Sample queries for quick access
  const sampleQueries = [
    "What are the NAAC requirements for Criterion 1.1?",
    "Show me MVSR's evidence for academic diversity",
    "Analyze compliance gaps in curriculum design",
    "What documents are needed for accreditation?",
    "Compare NAAC standards with MVSR practices",
  ]

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputValue.trim() || isLoading) return

    await sendQuery(inputValue.trim())
    setInputValue('')
  }

  const handleSampleQueryClick = (query: string) => {
    setInputValue(query)
    inputRef.current?.focus()
  }

  const toggleDetails = (messageId: string) => {
    setExpandedDetails(prev => ({
      ...prev,
      [messageId]: !prev[messageId],
    }))
  }

  const renderMessage = (message: ChatMessage) => {
    const isUser = message.type === 'user'
    const isSystem = message.type === 'system'
    const isAssistant = message.type === 'assistant'

    return (
      <ListItem
        key={message.id}
        sx={{
          flexDirection: 'column',
          alignItems: isUser ? 'flex-end' : 'flex-start',
          px: 0,
          py: 1,
        }}
        className={`message-${message.type} fade-in`}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            maxWidth: '85%',
            width: isSystem ? '100%' : 'auto',
            flexDirection: isUser ? 'row-reverse' : 'row',
            gap: 1,
          }}
        >
          <Avatar
            sx={{
              bgcolor: isUser ? 'primary.main' : isSystem ? 'secondary.main' : 'success.main',
              width: 32,
              height: 32,
            }}
          >
            {isUser ? <PersonIcon /> : <BotIcon />}
          </Avatar>

          <Paper
            elevation={1}
            sx={{
              p: 2,
              backgroundColor: isUser ? 'primary.main' : isSystem ? 'secondary.main' : 'background.paper',
              color: isUser || isSystem ? 'white' : 'text.primary',
              borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
              position: 'relative',
            }}
          >
            {message.isLoading ? (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="body2">{message.content}</Typography>
                <Box
                  sx={{
                    display: 'flex',
                    gap: 0.5,
                    '& div': {
                      width: 4,
                      height: 4,
                      bgcolor: 'currentColor',
                      borderRadius: '50%',
                      animation: 'pulse 1.5s ease-in-out infinite',
                    },
                    '& div:nth-of-type(2)': { animationDelay: '0.2s' },
                    '& div:nth-of-type(3)': { animationDelay: '0.4s' },
                  }}
                >
                  <div />
                  <div />
                  <div />
                </Box>
              </Box>
            ) : (
              <ReactMarkdown className="markdown-content">
                {message.content}
              </ReactMarkdown>
            )}

            {/* Compliance Response Details */}
            {message.complianceResponse && !message.isLoading && (
              <Box sx={{ mt: 1 }}>
                <Button
                  size="small"
                  onClick={() => toggleDetails(message.id)}
                  endIcon={expandedDetails[message.id] ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  sx={{ color: 'inherit', minWidth: 'auto' }}
                >
                  <InfoIcon sx={{ mr: 0.5, fontSize: 16 }} />
                  Details
                </Button>
                
                <Collapse in={expandedDetails[message.id]}>
                  <Box sx={{ mt: 1, p: 1, bgcolor: 'rgba(0,0,0,0.1)', borderRadius: 1 }}>
                    <Typography variant="caption" display="block" gutterBottom>
                      Confidence: {Math.round(message.complianceResponse.confidence_score * 100)}%
                    </Typography>
                    
                    {message.complianceResponse.compliance_score && (
                      <Typography variant="caption" display="block" gutterBottom>
                        Overall Score: {Math.round(message.complianceResponse.compliance_score.overall_score * 100)}%
                      </Typography>
                    )}

                    {message.complianceResponse.detailed_sources && (
                      <Box sx={{ mt: 1 }}>
                        <Typography variant="caption" display="block" gutterBottom>
                          Sources: {message.complianceResponse.detailed_sources.naac_sources?.length || 0} NAAC, {message.complianceResponse.detailed_sources.mvsr_sources?.length || 0} MVSR
                        </Typography>
                      </Box>
                    )}
                  </Box>
                </Collapse>
              </Box>
            )}

            <Typography
              variant="caption"
              sx={{
                display: 'block',
                textAlign: isUser ? 'right' : 'left',
                mt: 1,
                opacity: 0.7,
              }}
            >
              {message.timestamp.toLocaleTimeString()}
            </Typography>
          </Paper>
        </Box>
      </ListItem>
    )
  }

  return (
    <Box sx={{ height: 'calc(100vh - 160px)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="h4" gutterBottom>
          NAAC Compliance Intelligence
        </Typography>
        <Typography variant="body1" color="text.secondary" paragraph>
          Ask questions about NAAC requirements, MVSR evidence, and compliance analysis. 
          I can help you understand accreditation criteria and identify gaps.
        </Typography>
        
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Chip
            label={`${messages.length - 1} messages`} // -1 to exclude system message
            variant="outlined"
            size="small"
          />
          <Button
            variant="outlined"
            size="small"
            startIcon={<ClearIcon />}
            onClick={clearMessages}
            disabled={messages.length <= 1}
          >
            Clear Chat
          </Button>
        </Box>
      </Box>

      {/* Sample Queries */}
      {messages.length === 1 && ( // Only show when just the system message exists
        <Card sx={{ mb: 2, bgcolor: 'primary.50' }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Try asking about:
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {sampleQueries.map((query, index) => (
                <Chip
                  key={index}
                  label={query}
                  variant="outlined"
                  clickable
                  onClick={() => handleSampleQueryClick(query)}
                  sx={{ mb: 1 }}
                />
              ))}
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Messages Container */}
      <Paper
        elevation={0}
        sx={{
          flexGrow: 1,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          bgcolor: 'grey.50',
          border: 1,
          borderColor: 'divider',
          borderRadius: 2,
        }}
      >
        <Box
          sx={{
            flexGrow: 1,
            overflow: 'auto',
            px: 2,
            py: 1,
          }}
        >
          <List sx={{ py: 0 }}>
            {messages.map(renderMessage)}
            <div ref={messagesEndRef} />
          </List>
        </Box>

        {/* Input Area */}
        <Divider />
        <Box sx={{ p: 2 }}>
          <form onSubmit={handleSubmit}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
              <TextField
                ref={inputRef}
                fullWidth
                multiline
                maxRows={4}
                variant="outlined"
                placeholder="Ask about NAAC compliance, requirements, or MVSR evidence..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                disabled={isLoading}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSubmit(e)
                  }
                }}
                sx={{
                  '& .MuiOutlinedInput-root': {
                    borderRadius: '20px',
                    bgcolor: 'background.paper',
                  },
                }}
              />
              <IconButton
                type="submit"
                disabled={!inputValue.trim() || isLoading}
                sx={{
                  bgcolor: 'primary.main',
                  color: 'white',
                  '&:hover': {
                    bgcolor: 'primary.dark',
                  },
                  '&:disabled': {
                    bgcolor: 'grey.300',
                    color: 'grey.500',
                  },
                }}
              >
                <SendIcon />
              </IconButton>
            </Box>
          </form>
        </Box>
      </Paper>

      {/* Pulse animation styles */}
      <style>
        {`
          @keyframes pulse {
            0%, 80%, 100% { opacity: 0; }
            40% { opacity: 1; }
          }
        `}
      </style>
    </Box>
  )
}

export default ChatInterface