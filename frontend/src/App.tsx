import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ThemeProvider, createTheme, CssBaseline, Box } from '@mui/material'
import { QueryProvider } from './contexts/QueryContext'
import { SystemProvider } from './contexts/SystemContext'
import Layout from './components/layout/Layout'
import ChatInterface from './components/chat/ChatInterface'
import SystemDashboard from './components/dashboard/SystemDashboard'
import DocumentUpload from './components/upload/DocumentUpload'
import SchedulerManager from './components/scheduler/SchedulerManager'

// Create Material-UI theme
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
      light: '#42a5f5',
      dark: '#1565c0',
    },
    secondary: {
      main: '#dc004e',
      light: '#ff5983',
      dark: '#9a0036',
    },
    background: {
      default: '#f5f5f5',
      paper: '#ffffff',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h4: {
      fontWeight: 600,
    },
    h5: {
      fontWeight: 500,
    },
    h6: {
      fontWeight: 500,
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
          borderRadius: '12px',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: '8px',
          textTransform: 'none',
          fontWeight: 500,
        },
      },
    },
  },
})

const App: React.FC = () => {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <SystemProvider>
        <QueryProvider>
          <Router>
            <Box sx={{ minHeight: '100vh', backgroundColor: 'background.default' }}>
              <Layout>
                <Routes>
                  <Route path="/" element={<ChatInterface />} />
                  <Route path="/dashboard" element={<SystemDashboard />} />
                  <Route path="/upload" element={<DocumentUpload />} />
                  <Route path="/scheduler" element={<SchedulerManager />} />
                </Routes>
              </Layout>
            </Box>
          </Router>
        </QueryProvider>
      </SystemProvider>
    </ThemeProvider>
  )
}

export default App