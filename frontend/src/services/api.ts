import axios, { AxiosInstance, AxiosResponse } from 'axios'
import {
  ComplianceResponse,
  QueryRequest,
  SystemHealth,
  SystemStats,
  SchedulerStatus,
  UploadResponse,
  IngestRequest,
  UpdateRequest,
  ScheduleRequest,
  ApiError
} from '../types'

class ApiService {
  private api: AxiosInstance

  constructor() {
    this.api = axios.create({
      baseURL: process.env.REACT_APP_API_BASE_URL || '/api',
      timeout: 180000, // 3 minutes timeout for LLM responses on CPU
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Add request interceptor for logging
    this.api.interceptors.request.use(
      (config) => {
        console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`)
        return config
      },
      (error) => {
        console.error('API Request Error:', error)
        return Promise.reject(error)
      }
    )

    // Add response interceptor for error handling
    this.api.interceptors.response.use(
      (response) => response,
      (error) => {
        const apiError: ApiError = {
          detail: error.response?.data?.detail || error.message || 'Unknown error',
          status_code: error.response?.status || 500,
          timestamp: new Date().toISOString(),
        }
        console.error('API Response Error:', apiError)
        return Promise.reject(apiError)
      }
    )
  }

  // Query endpoints
  async queryCompliance(request: QueryRequest): Promise<ComplianceResponse> {
    const response: AxiosResponse<ComplianceResponse> = await this.api.post('/query', request)
    return response.data
  }

  // System health endpoints
  async getSystemHealth(): Promise<SystemHealth> {
    const response: AxiosResponse<SystemHealth> = await this.api.get('/health')
    return response.data
  }

  async getSystemStats(): Promise<SystemStats> {
    const response: AxiosResponse<SystemStats> = await this.api.get('/stats')
    return response.data
  }

  async getLastSync(): Promise<any> {
    const response = await this.api.get('/last-sync')
    return response.data
  }

  // Document ingestion endpoints
  async ingestDocuments(request: IngestRequest): Promise<any> {
    const response = await this.api.post('/ingest', request)
    return response.data
  }

  async uploadDocument(file: File, documentType: 'naac_requirement' | 'mvsr_evidence'): Promise<UploadResponse> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('document_type', documentType)

    const response: AxiosResponse<UploadResponse> = await this.api.post('/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  }

  // Update endpoints
  async forceUpdate(request: UpdateRequest): Promise<any> {
    const response = await this.api.post('/force-update', request)
    return response.data
  }

  // Scheduler endpoints
  async getSchedulerStatus(): Promise<SchedulerStatus> {
    const response: AxiosResponse<SchedulerStatus> = await this.api.get('/scheduler/status')
    return response.data
  }

  async scheduleJob(request: ScheduleRequest): Promise<any> {
    const response = await this.api.post('/scheduler/schedule', request)
    return response.data
  }

  async pauseJob(jobId: string): Promise<any> {
    const response = await this.api.post(`/scheduler/jobs/${jobId}/pause`)
    return response.data
  }

  async resumeJob(jobId: string): Promise<any> {
    const response = await this.api.post(`/scheduler/jobs/${jobId}/resume`)
    return response.data
  }

  async removeJob(jobId: string): Promise<any> {
    const response = await this.api.delete(`/scheduler/jobs/${jobId}`)
    return response.data
  }

  // Mapping analysis endpoint
  async analyzeQueryMapping(query: string): Promise<any> {
    const response = await this.api.get('/mapping/analyze', {
      params: { query },
    })
    return response.data
  }

  // Utility method for checking API connectivity
  async checkConnectivity(): Promise<boolean> {
    try {
      await this.api.get('/health')
      return true
    } catch (error) {
      console.error('API connectivity check failed:', error)
      return false
    }
  }

  // Download file helper (for future use with reports)
  async downloadFile(url: string, filename: string): Promise<void> {
    const response = await this.api.get(url, {
      responseType: 'blob',
    })

    const blob = new Blob([response.data])
    const downloadUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(downloadUrl)
  }
}

// Create singleton instance
const apiService = new ApiService()
export default apiService

// Export types and utility functions
export type { ApiError }

export const isApiError = (error: any): error is ApiError => {
  return error && typeof error === 'object' && 'detail' in error && 'status_code' in error
}

export const getErrorMessage = (error: unknown): string => {
  if (isApiError(error)) {
    return error.detail
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'An unknown error occurred'
}