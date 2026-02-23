import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react'
import { SystemHealth, SystemStats, SchedulerStatus, SystemContextType } from '../types'
import apiService, { getErrorMessage } from '../services/api'

const SystemContext = createContext<SystemContextType | undefined>(undefined)

interface SystemProviderProps {
  children: ReactNode
}

export const SystemProvider: React.FC<SystemProviderProps> = ({ children }) => {
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null)
  const [systemStats, setSystemStats] = useState<SystemStats | null>(null)
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null)
  const [isHealthy, setIsHealthy] = useState(false)

  const refreshSystemData = useCallback(async () => {
    try {
      // Fetch all system data in parallel
      const [healthData, statsData, schedulerData] = await Promise.allSettled([
        apiService.getSystemHealth(),
        apiService.getSystemStats(),
        apiService.getSchedulerStatus(),
      ])

      // Handle health data
      if (healthData.status === 'fulfilled') {
        setSystemHealth(healthData.value)
        setIsHealthy(healthData.value.status === 'healthy')
      } else {
        console.error('Failed to fetch system health:', healthData.reason)
        setIsHealthy(false)
      }

      // Handle stats data
      if (statsData.status === 'fulfilled') {
        setSystemStats(statsData.value)
      } else {
        console.error('Failed to fetch system stats:', statsData.reason)
      }

      // Handle scheduler data
      if (schedulerData.status === 'fulfilled') {
        setSchedulerStatus(schedulerData.value)
      } else {
        console.error('Failed to fetch scheduler status:', schedulerData.reason)
      }
    } catch (error) {
      console.error('Error refreshing system data:', getErrorMessage(error))
      setIsHealthy(false)
    }
  }, [])

  const forceUpdate = useCallback(async (
    updateType: 'incremental' | 'full' | 'criterion',
    criteria?: string[]
  ) => {
    try {
      const request = {
        update_type: updateType,
        criteria,
        force_check: true,
      }

      await apiService.forceUpdate(request)
      
      // Refresh system data after initiating update
      await refreshSystemData()
    } catch (error) {
      console.error('Force update failed:', getErrorMessage(error))
      throw error
    }
  }, [refreshSystemData])

  // Auto-refresh system data periodically
  useEffect(() => {
    // Initial load
    refreshSystemData()

    // Set up periodic refresh every 30 seconds
    const interval = setInterval(refreshSystemData, 30000)

    return () => clearInterval(interval)
  }, [refreshSystemData])

  // Check connectivity on mount
  useEffect(() => {
    const checkInitialConnectivity = async () => {
      try {
        const isConnected = await apiService.checkConnectivity()
        setIsHealthy(isConnected)
      } catch (error) {
        console.error('Initial connectivity check failed:', getErrorMessage(error))
        setIsHealthy(false)
      }
    }

    checkInitialConnectivity()
  }, [])

  return (
    <SystemContext.Provider
      value={{
        systemHealth,
        systemStats,
        schedulerStatus,
        isHealthy,
        refreshSystemData,
        forceUpdate,
      }}
    >
      {children}
    </SystemContext.Provider>
  )
}

export const useSystem = () => {
  const context = useContext(SystemContext)
  if (context === undefined) {
    throw new Error('useSystem must be used within a SystemProvider')
  }
  return context
}

// Additional hooks for specific system data
export const useSystemHealth = () => {
  const { systemHealth, isHealthy } = useSystem()
  return { systemHealth, isHealthy }
}

export const useSystemStats = () => {
  const { systemStats } = useSystem()
  return systemStats
}

export const useSchedulerStatus = () => {
  const { schedulerStatus } = useSystem()
  return schedulerStatus
}