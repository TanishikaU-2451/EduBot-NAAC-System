import React, { useState } from 'react'
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  LinearProgress,
  Chip,
  Button,
  Alert,
  Divider,
  List,
  ListItem,
  ListItemText,
  IconButton,
  Tooltip,
} from '@mui/material'
import {
  Refresh as RefreshIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  Schedule as ScheduleIcon,
  Storage as StorageIcon,
  Speed as SpeedIcon,
} from '@mui/icons-material'
import { useSystem } from '../../contexts/SystemContext'
import { getErrorMessage } from '../../services/api'

const SystemDashboard: React.FC = () => {
  const { systemHealth, systemStats, isHealthy, refreshSystemData, forceUpdate } = useSystem()
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isUpdating, setIsUpdating] = useState(false)

  const handleRefresh = async () => {
    setIsRefreshing(true)
    try {
      await refreshSystemData()
    } catch (error) {
      console.error('Refresh failed:', getErrorMessage(error))
    } finally {
      setIsRefreshing(false)
    }
  }

  const handleForceUpdate = async () => {
    setIsUpdating(true)
    try {
      await forceUpdate('incremental')
    } catch (error) {
      console.error('Update failed:', getErrorMessage(error))
    } finally {
      setIsUpdating(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'healthy': return 'success'
      case 'degraded': return 'warning'
      case 'unhealthy': return 'error'
      default: return 'default'
    }
  }

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Never'
    return new Date(dateString).toLocaleString()
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          System Dashboard
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={handleRefresh}
            disabled={isRefreshing}
          >
            {isRefreshing ? 'Refreshing...' : 'Refresh'}
          </Button>
          <Button
            variant="contained"
            onClick={handleForceUpdate}
            disabled={isUpdating || !isHealthy}
          >
            {isUpdating ? 'Updating...' : 'Force Update'}
          </Button>
        </Box>
      </Box>

      {/* System Status Alert */}
      {systemHealth && (
        <Alert
          severity={getStatusColor(systemHealth.status) as any}
          sx={{ mb: 3 }}
          icon={
            systemHealth.status === 'healthy' ? <CheckIcon /> :
            systemHealth.status === 'degraded' ? <WarningIcon /> : <ErrorIcon />
          }
        >
          System Status: <strong>{systemHealth.status.toUpperCase()}</strong>
          {systemHealth.timestamp && (
            <Typography variant="caption" sx={{ ml: 2 }}>
              Last checked: {formatDate(systemHealth.timestamp)}
            </Typography>
          )}
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Component Status */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Component Status
              </Typography>
              {systemHealth ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {Object.entries(systemHealth.components).map(([component, status]) => (
                    <Box key={component} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                        {component.replace(/_/g, ' ')}
                      </Typography>
                      <Chip
                        label={status ? 'Online' : 'Offline'}
                        color={status ? 'success' : 'error'}
                        size="small"
                        icon={status ? <CheckIcon /> : <ErrorIcon />}
                      />
                    </Box>
                  ))}
                </Box>
              ) : (
                <Box sx={{ textAlign: 'center', py: 2 }}>
                  <LinearProgress />
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    Loading component status...
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* System Statistics */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                <StorageIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                Knowledge Base Statistics
              </Typography>
              {systemStats ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2">Total Documents:</Typography>
                    <Typography variant="body2" fontWeight="bold">
                      {systemStats.pipeline_statistics.total_documents}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2">NAAC Documents:</Typography>
                    <Typography variant="body2" fontWeight="bold" color="primary">
                      {systemStats.pipeline_statistics.naac_documents}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2">MVSR Documents:</Typography>
                    <Typography variant="body2" fontWeight="bold" color="secondary">
                      {systemStats.pipeline_statistics.mvsr_documents}
                    </Typography>
                  </Box>
                  <Divider />
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2">Queries (24h):</Typography>
                    <Typography variant="body2" fontWeight="bold">
                      {systemStats.pipeline_statistics.query_count_24h}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2">Avg Response Time:</Typography>
                    <Typography variant="body2" fontWeight="bold">
                      {systemStats.pipeline_statistics.average_response_time.toFixed(2)}s
                    </Typography>
                  </Box>
                </Box>
              ) : (
                <Box sx={{ textAlign: 'center', py: 2 }}>
                  <LinearProgress />
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    Loading statistics...
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Performance Metrics */}
        {systemHealth?.pipeline_health && (
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  <SpeedIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                  Performance Metrics
                </Typography>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {Object.entries(systemHealth.pipeline_health.performance_metrics || {}).map(([metric, value]) => (
                    <Box key={metric} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                        {metric.replace(/_/g, ' ')}:
                      </Typography>
                      <Typography variant="body2" fontWeight="bold">
                        {typeof value === 'number' ? value.toFixed(2) : value}
                        {metric.includes('time') ? 's' : ''}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        )}

        {/* Recent Operations */}
        {systemStats?.update_status.recent_operations && (
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  <ScheduleIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                  Recent Operations
                </Typography>
                <List dense>
                  {systemStats.update_status.recent_operations.slice(0, 5).map((operation) => (
                    <ListItem key={operation.operation_id}>
                      <ListItemText
                        primary={operation.operation_type}
                        secondary={
                          <Box>
                            <Typography variant="caption" display="block">
                              Started: {formatDate(operation.start_time)}
                            </Typography>
                            {operation.end_time && (
                              <Typography variant="caption" display="block">
                                Ended: {formatDate(operation.end_time)}
                              </Typography>
                            )}
                            {operation.documents_processed && (
                              <Typography variant="caption" display="block">
                                Documents: {operation.documents_processed}
                              </Typography>
                            )}
                          </Box>
                        }
                      />
                      <Chip
                        label={operation.status}
                        color={operation.status === 'completed' ? 'success' : operation.status === 'failed' ? 'error' : 'default'}
                        size="small"
                      />
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>
        )}
      </Grid>
    </Box>
  )
}

export default SystemDashboard