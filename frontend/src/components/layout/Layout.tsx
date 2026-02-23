import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  AppBar,
  Box,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
  Badge,
  Chip,
  Tooltip,
} from '@mui/material'
import {
  Menu as MenuIcon,
  Chat as ChatIcon,
  Dashboard as DashboardIcon,
  Upload as UploadIcon,
  Schedule as ScheduleIcon,
  HealthAndSafety as HealthIcon,
} from '@mui/icons-material'
import { useSystemHealth } from '../../contexts/SystemContext'
import { NavigationItem } from '../../types'

const DRAWER_WIDTH = 240

interface LayoutProps {
  children: React.ReactNode
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { systemHealth, isHealthy } = useSystemHealth()

  const navigationItems: NavigationItem[] = [
    {
      path: '/',
      label: 'Chat Interface',
      icon: <ChatIcon />,
      description: 'Query NAAC compliance information',
    },
    {
      path: '/dashboard',
      label: 'System Dashboard',
      icon: <DashboardIcon />,
      description: 'Monitor system health and statistics',
    },
    {
      path: '/upload',
      label: 'Document Upload',
      icon: <UploadIcon />,
      description: 'Upload NAAC and MVSR documents',
    },
    {
      path: '/scheduler',
      label: 'Scheduler Manager',
      icon: <ScheduleIcon />,
      description: 'Manage automated updates',
    },
  ]

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen)
  }

  const handleNavigation = (path: string) => {
    navigate(path)
    setMobileOpen(false)
  }

  const getSystemHealthChip = () => {
    if (!systemHealth) {
      return (
        <Chip
          icon={<HealthIcon />}
          label="Checking..."
          color="default"
          size="small"
        />
      )
    }

    const color = systemHealth.status === 'healthy' ? 'success' : 
                 systemHealth.status === 'degraded' ? 'warning' : 'error'
    
    return (
      <Tooltip title={`System Status: ${systemHealth.status}`}>
        <Chip
          icon={<HealthIcon />}
          label={systemHealth.status}
          color={color}
          size="small"
        />
      </Tooltip>
    )
  }

  const drawer = (
    <Box>
      <Toolbar>
        <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 600 }}>
          NAAC Intelligence
        </Typography>
      </Toolbar>
      
      <Box sx={{ p: 2 }}>
        {getSystemHealthChip()}
      </Box>

      <List>
        {navigationItems.map((item) => (
          <ListItem key={item.path} disablePadding>
            <ListItemButton
              selected={location.pathname === item.path}
              onClick={() => handleNavigation(item.path)}
              sx={{
                '&.Mui-selected': {
                  backgroundColor: 'primary.main',
                  color: 'white',
                  '&:hover': {
                    backgroundColor: 'primary.dark',
                  },
                  '& .MuiListItemIcon-root': {
                    color: 'white',
                  },
                },
              }}
            >
              <ListItemIcon>
                {item.path === location.pathname ? (
                  <Badge
                    color="secondary"
                    variant="dot"
                    sx={{
                      '& .MuiBadge-badge': {
                        backgroundColor: 'white',
                      },
                    }}
                  >
                    {item.icon}
                  </Badge>
                ) : (
                  item.icon
                )}
              </ListItemIcon>
              <ListItemText
                primary={item.label}
                secondary={item.description}
                secondaryTypographyProps={{
                  fontSize: '0.75rem',
                  color: location.pathname === item.path ? 'rgba(255,255,255,0.7)' : 'text.secondary',
                }}
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>

      {/* Component Status Indicators */}
      {systemHealth && (
        <Box sx={{ p: 2, mt: 2, borderTop: 1, borderColor: 'divider' }}>
          <Typography variant="subtitle2" gutterBottom>
            Component Status
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2">RAG Pipeline</Typography>
              <Chip
                label={systemHealth.components.rag_pipeline ? 'Online' : 'Offline'}
                color={systemHealth.components.rag_pipeline ? 'success' : 'error'}
                size="small"
              />
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2">Auto Ingest</Typography>
              <Chip
                label={systemHealth.components.auto_ingest ? 'Online' : 'Offline'}
                color={systemHealth.components.auto_ingest ? 'success' : 'error'}
                size="small"
              />
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2">Scheduler</Typography>
              <Chip
                label={systemHealth.components.scheduler ? 'Running' : 'Stopped'}
                color={systemHealth.components.scheduler ? 'success' : 'error'}
                size="small"
              />
            </Box>
          </Box>
        </Box>
      )}
    </Box>
  )

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar
        position="fixed"
        sx={{
          width: { sm: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { sm: `${DRAWER_WIDTH}px` },
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { sm: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            {navigationItems.find(item => item.path === location.pathname)?.label || 'NAAC Compliance Intelligence'}
          </Typography>

          {/* Connection Status Indicator */}
          <Box sx={{ ml: 2 }}>
            <Badge
              color={isHealthy ? 'success' : 'error'}
              variant="dot"
              sx={{
                '& .MuiBadge-badge': {
                  animation: isHealthy ? 'none' : 'pulse 2s infinite',
                },
              }}
            >
              <HealthIcon />
            </Badge>
          </Box>
        </Toolbar>
      </AppBar>

      <Box
        component="nav"
        sx={{ width: { sm: DRAWER_WIDTH }, flexShrink: { sm: 0 } }}
      >
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true, // Better open performance on mobile.
          }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: DRAWER_WIDTH },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: DRAWER_WIDTH },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          width: { sm: `calc(100% - ${DRAWER_WIDTH}px)` },
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Toolbar />
        <Box sx={{ flexGrow: 1, p: 3 }}>
          {children}
        </Box>
      </Box>

      {/* Pulse animation for connection indicator */}
      <style>
        {`
          @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
          }
        `}
      </style>
    </Box>
  )
}

export default Layout