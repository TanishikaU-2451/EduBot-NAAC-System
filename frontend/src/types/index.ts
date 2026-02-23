// API Response Types
export interface ComplianceResponse {
  naac_requirement: string
  mvsr_evidence: string
  naac_mapping: string
  compliance_analysis: string
  status: string
  recommendations: string
  confidence_score: number
  compliance_score?: {
    overall_score: number
    category_scores: Record<string, number>
    gap_analysis: string[]
  }
  detailed_sources?: {
    naac_sources: DocumentSource[]
    mvsr_sources: DocumentSource[]
    metadata: Record<string, any>
  }
}

export interface DocumentSource {
  document_id: string
  filename: string
  page_number?: number
  chunk_id: string
  relevance_score: number
  content_preview: string
}

export interface ChatMessage {
  id: string
  type: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
  complianceResponse?: ComplianceResponse
  isLoading?: boolean
}

export interface QueryRequest {
  query: string
  filters?: Record<string, any>
  include_sources?: boolean
}

// System Status Types
export interface SystemHealth {
  timestamp: string
  status: 'healthy' | 'degraded' | 'unhealthy'
  components: {
    rag_pipeline: boolean
    auto_ingest: boolean
    scheduler: boolean
    metadata_mapper: boolean
  }
  pipeline_health?: {
    overall_status: string
    component_status: Record<string, string>
    performance_metrics: Record<string, number>
  }
}

export interface SystemStats {
  pipeline_statistics: {
    total_documents: number
    naac_documents: number
    mvsr_documents: number
    last_query_time?: string
    query_count_24h: number
    average_response_time: number
  }
  update_status: {
    last_successful_update?: string
    recent_operations: UpdateOperation[]
    system_status: string
    component_statistics: Record<string, any>
  }
  timestamp: string
}

export interface UpdateOperation {
  operation_id: string
  operation_type: string
  start_time: string
  end_time?: string
  status: string
  documents_processed?: number
  errors?: string[]
}

// Scheduler Types
export interface SchedulerStatus {
  scheduler_status: {
    running: boolean
    job_count: number
    next_run_time?: string
    uptime_hours: number
  }
  jobs: ScheduledJob[]
  timestamp: string
}

export interface ScheduledJob {
  id: string
  name: string
  job_type: string
  schedule: string
  next_run_time?: string
  status: 'scheduled' | 'running' | 'paused' | 'failed'
  created_at: string
  last_run?: string
  run_count: number
}

// Document Upload Types
export interface UploadRequest {
  file: File
  document_type: 'naac_requirement' | 'mvsr_evidence'
}

export interface UploadResponse {
  status: 'accepted' | 'failed'
  message: string
  filename?: string
  document_type?: string
  file_size?: number
  timestamp: string
}

// Ingestion Types
export interface IngestRequest {
  document_type: 'naac_requirement' | 'mvsr_evidence'
  file_paths: string[]
  force_reingest?: boolean
  additional_metadata?: Record<string, any>
}

// Update Request Types
export interface UpdateRequest {
  update_type: 'incremental' | 'full' | 'criterion'
  criteria?: string[]
  force_check?: boolean
}

// Schedule Job Types
export interface ScheduleRequest {
  job_type: 'daily' | 'interval' | 'criterion'
  schedule: string
  criteria?: string[]
  enabled?: boolean
}

// Error Types
export interface ApiError {
  detail: string
  status_code: number
  timestamp?: string
}

// Navigation Types
export interface NavigationItem {
  path: string
  label: string
  icon: React.ReactNode
  description?: string
}

// Component Props Types
export interface ChatInterfaceProps {
  className?: string
}

export interface SystemDashboardProps {
  className?: string
}

export interface DocumentUploadProps {
  className?: string
}

export interface SchedulerManagerProps {
  className?: string
}

// Context Types
export interface QueryContextType {
  messages: ChatMessage[]
  isLoading: boolean
  sendQuery: (query: string, filters?: Record<string, any>) => Promise<void>
  clearMessages: () => void
}

export interface SystemContextType {
  systemHealth: SystemHealth | null
  systemStats: SystemStats | null
  schedulerStatus: SchedulerStatus | null
  isHealthy: boolean
  refreshSystemData: () => Promise<void>
  forceUpdate: (updateType: 'incremental' | 'full' | 'criterion', criteria?: string[]) => Promise<void>
}

// Utility Types
export type LoadingState = 'idle' | 'loading' | 'success' | 'error'

export interface ComplianceScoreBreakdown {
  criterion: string
  score: number
  status: 'compliant' | 'partial' | 'non-compliant' | 'not-applicable'
  evidence_count: number
  gap_areas: string[]
}

export interface DocumentMetadata {
  document_type: 'naac_requirement' | 'mvsr_evidence'
  filename: string
  upload_date: string
  file_size: number
  page_count?: number
  naac_criteria?: string[]
  mvsr_categories?: string[]
}

export interface QueryAnalysis {
  detected_criteria: string[]
  query_type: 'general' | 'specific' | 'comparison' | 'gap_analysis'
  confidence: number
  suggested_filters: Record<string, any>
}