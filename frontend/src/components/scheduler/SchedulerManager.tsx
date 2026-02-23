import React, { useState } from 'react'
import {
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  Alert,
  Grid,
  Chip,
  List,
  ListItem,
  ListItemText,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  DialogActions,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from '@mui/material'
import {
  Schedule as ScheduleIcon,
  Add as AddIcon,
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material'
import { useSchedulerStatus } from '../../contexts/SystemContext'
import apiService, { getErrorMessage } from '../../services/api'

const SchedulerManager: React.FC = () => {
  const schedulerStatus = useSchedulerStatus()
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [newJobType, setNewJobType] = useState<'daily' | 'interval' | 'criterion'>('daily')
  const [newJobSchedule, setNewJobSchedule] = useState('')

  const handleRefresh = async () => {
    setIsRefreshing(true)
    // Refresh would be handled by the SystemContext
    setTimeout(() => setIsRefreshing(false), 1000)
  }

  const handleAddJob = async () => {
    try {
      await apiService.scheduleJob({
        job_type: newJobType,
        schedule: newJobSchedule,
        enabled: true,
      })
      setShowAddDialog(false)
      setNewJobSchedule('')
      await handleRefresh()
    } catch (error) {
      console.error('Failed to add job:', getErrorMessage(error))
    }
  }

  const handleJobAction = async (jobId: string, action: 'pause' | 'resume' | 'remove') => {
    try {
      switch (action) {
        case 'pause':
          await apiService.pauseJob(jobId)
          break
        case 'resume':
          await apiService.resumeJob(jobId)
          break
        case 'remove':
          await apiService.removeJob(jobId)
          break
      }
      await handleRefresh()
    } catch (error) {
      console.error(`Failed to ${action} job:`, getErrorMessage(error))
    }
  }

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Not scheduled'
    return new Date(dateString).toLocaleString()
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'scheduled': return 'success'
      case 'running': return 'primary'
      case 'paused': return 'warning'
      case 'failed': return 'error'
      default: return 'default'
    }
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          Scheduler Manager
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={handleRefresh}
            disabled={isRefreshing}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setShowAddDialog(true)}
          >
            Add Job
          </Button>
        </Box>
      </Box>

      <Typography variant="body1" color="text.secondary" paragraph>
        Manage automated update schedules and monitor job execution.
      </Typography>

      <Grid container spacing={3}>
        {/* Scheduler Status */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                <ScheduleIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                Scheduler Status
              </Typography>
              
              {schedulerStatus ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2">Status:</Typography>
                    <Chip
                      label={schedulerStatus.scheduler_status.running ? 'Running' : 'Stopped'}
                      color={schedulerStatus.scheduler_status.running ? 'success' : 'error'}
                      size="small"
                    />
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2">Active Jobs:</Typography>
                    <Typography variant="body2" fontWeight="bold">
                      {schedulerStatus.scheduler_status.job_count}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2">Uptime:</Typography>
                    <Typography variant="body2" fontWeight="bold">
                      {schedulerStatus.scheduler_status.uptime_hours.toFixed(1)}h
                    </Typography>
                  </Box>
                  {schedulerStatus.scheduler_status.next_run_time && (
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2">Next Run:</Typography>
                      <Typography variant="body2" fontWeight="bold">
                        {formatDate(schedulerStatus.scheduler_status.next_run_time)}
                      </Typography>
                    </Box>
                  )}
                </Box>
              ) : (
                <Alert severity="info">Loading scheduler status...</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Scheduled Jobs */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Scheduled Jobs
              </Typography>
              
              {schedulerStatus?.jobs && schedulerStatus.jobs.length > 0 ? (
                <List>
                  {schedulerStatus.jobs.map((job) => (
                    <ListItem
                      key={job.id}
                      sx={{
                        border: 1,
                        borderColor: 'divider',
                        borderRadius: 1,
                        mb: 1,
                      }}
                      secondaryAction={
                        <Box sx={{ display: 'flex', gap: 1 }}>
                          {job.status === 'paused' ? (
                            <IconButton
                              size="small"
                              onClick={() => handleJobAction(job.id, 'resume')}
                              title="Resume"
                            >
                              <PlayIcon />
                            </IconButton>
                          ) : (
                            <IconButton
                              size="small"
                              onClick={() => handleJobAction(job.id, 'pause')}
                              title="Pause"
                            >
                              <PauseIcon />
                            </IconButton>
                          )}
                          <IconButton
                            size="small"
                            onClick={() => handleJobAction(job.id, 'remove')}
                            title="Remove"
                          >
                            <DeleteIcon />
                          </IconButton>
                        </Box>
                      }
                    >
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Typography variant="subtitle1">{job.name}</Typography>
                            <Chip
                              label={job.status}
                              color={getStatusColor(job.status) as any}
                              size="small"
                            />
                          </Box>
                        }
                        secondary={
                          <Box>
                            <Typography variant="body2">
                              Type: {job.job_type} | Schedule: {job.schedule}
                            </Typography>
                            <Typography variant="caption">
                              Next run: {formatDate(job.next_run_time)}
                            </Typography>
                            {job.last_run && (
                              <Typography variant="caption" sx={{ ml: 2 }}>
                                Last run: {formatDate(job.last_run)}
                              </Typography>
                            )}
                            <Typography variant="caption" sx={{ ml: 2 }}>
                              Runs: {job.run_count}
                            </Typography>
                          </Box>
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Alert severity="info">No scheduled jobs found.</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Add Job Dialog */}
      <Dialog open={showAddDialog} onClose={() => setShowAddDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Schedule New Job</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <FormControl>
              <InputLabel>Job Type</InputLabel>
              <Select
                value={newJobType}
                onChange={(e) => setNewJobType(e.target.value as any)}
                label="Job Type"
              >
                <MenuItem value="daily">Daily Update</MenuItem>
                <MenuItem value="interval">Interval Update</MenuItem>
                <MenuItem value="criterion">Criterion Update</MenuItem>
              </Select>
            </FormControl>
            
            <TextField
              label={
                newJobType === 'daily' ? 'Time (HH:MM)' :
                newJobType === 'interval' ? 'Hours' : 'Cron Expression'
              }
              placeholder={
                newJobType === 'daily' ? '02:00' :
                newJobType === 'interval' ? '6' : '0 0 * * 1'
              }
              value={newJobSchedule}
              onChange={(e) => setNewJobSchedule(e.target.value)}
              fullWidth
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowAddDialog(false)}>Cancel</Button>
          <Button
            onClick={handleAddJob}
            variant="contained"
            disabled={!newJobSchedule.trim()}
          >
            Schedule Job
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default SchedulerManager