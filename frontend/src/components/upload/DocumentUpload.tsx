import React, { useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  IconButton,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material'
import {
  CloudUpload as CloudUploadIcon,
  Close as CloseIcon,
  Upload as UploadIcon,
} from '@mui/icons-material'
import { useSystem } from '../../contexts/SystemContext'
import apiService, { getErrorMessage } from '../../services/api'

type DocumentType = 'naac_requirement' | 'mvsr_evidence'
type StagedStatus = 'idle' | 'staging' | 'staged' | 'ingesting' | 'queued' | 'error'

interface StagedFile {
  name: string
  size: number
  storedPath?: string
  status: StagedStatus
  message: string
  savedAt?: string
  requestedAt?: string
}

const labels: Record<DocumentType, string> = {
  naac_requirement: 'NAAC Requirements',
  mvsr_evidence: 'MVSR Evidence',
}

const formatDocumentCountMessage = (count: number) =>
  count === 1 ? '1 document' : `${count} documents`

const DocumentUpload: React.FC = () => {
  const [filesByType, setFilesByType] = useState<Record<DocumentType, StagedFile | null>>({
    naac_requirement: null,
    mvsr_evidence: null,
  })
  const [isStartingUpload, setIsStartingUpload] = useState(false)
  const [banner, setBanner] = useState<{ severity: 'success' | 'error' | 'info'; text: string } | null>(null)
  const { isHealthy } = useSystem()
  const naacInputRef = useRef<HTMLInputElement>(null)
  const mvsrInputRef = useRef<HTMLInputElement>(null)

  const getInputRef = (documentType: DocumentType) =>
    documentType === 'naac_requirement' ? naacInputRef : mvsrInputRef

  const clearStagedFile = async (documentType: DocumentType) => {
    const current = filesByType[documentType]
    if (!current) return

    setFilesByType((prev) => ({
      ...prev,
      [documentType]: null,
    }))

    const inputRef = getInputRef(documentType)
    if (inputRef.current) {
      inputRef.current.value = ''
    }

    if (current.storedPath && current.status !== 'queued' && current.status !== 'ingesting') {
      try {
        await apiService.deleteStagedUpload(current.storedPath)
      } catch (error) {
        setBanner({ severity: 'error', text: getErrorMessage(error) })
      }
    }
  }

  const handleFileSelect = async (documentType: DocumentType, event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    if (filesByType[documentType]) {
      await clearStagedFile(documentType)
    }

    setBanner(null)
    setFilesByType((prev) => ({
      ...prev,
      [documentType]: {
        name: file.name,
        size: file.size,
        status: 'staging',
        message: 'Saving file. Chunking will wait for Upload documents.',
      },
    }))

    try {
      const response = await apiService.uploadDocument(file, documentType)
      setFilesByType((prev) => ({
        ...prev,
        [documentType]: {
          name: file.name,
          size: file.size,
          storedPath: response.stored_path,
          status: 'staged',
          message: 'Staged.',
          savedAt: response.timestamp,
        },
      }))
    } catch (error) {
      const detail = getErrorMessage(error)
      setFilesByType((prev) => ({
        ...prev,
        [documentType]: {
          name: file.name,
          size: file.size,
          status: 'error',
          message: detail,
        },
      }))
      setBanner({ severity: 'error', text: detail })
    }
  }

  const handleUpload = async () => {
    const stagedFiles = (Object.entries(filesByType) as [DocumentType, StagedFile | null][])
      .filter((entry): entry is [DocumentType, StagedFile] => !!entry[1] && entry[1].status === 'staged' && !!entry[1].storedPath)

    if (!stagedFiles.length) return

    setBanner(null)
    setIsStartingUpload(true)
    const stagedCount = stagedFiles.length

    const results = await Promise.all(
      stagedFiles.map(async ([documentType, stagedFile]) => {
        setFilesByType((prev) => ({
          ...prev,
          [documentType]: prev[documentType]
            ? {
                ...prev[documentType]!,
                status: 'ingesting',
                message: 'Chunking started. Sending to the database...',
              }
            : prev[documentType],
        }))

        try {
          const response = await apiService.ingestDocuments({
            document_type: documentType,
            file_paths: [stagedFile.storedPath!],
          })

          setFilesByType((prev) => ({
            ...prev,
            [documentType]: prev[documentType]
              ? {
                  ...prev[documentType]!,
                  status: 'queued',
                  message: `${labels[documentType]} processing started in the background.`,
                  requestedAt: response.timestamp,
                }
              : prev[documentType],
          }))

          return null
        } catch (error) {
          const detail = getErrorMessage(error)
          setFilesByType((prev) => ({
            ...prev,
            [documentType]: prev[documentType]
              ? {
                  ...prev[documentType]!,
                  status: 'error',
                  message: detail,
                }
              : prev[documentType],
          }))
          return detail
        }
      })
    )

    const firstError = results.find(Boolean)
    if (firstError) {
      setBanner({ severity: 'error', text: firstError })
    } else {
      setBanner({
        severity: 'success',
        text:
          stagedCount === 1
            ? 'Upload started. 1 document is now processing in the background.'
            : `Upload started. ${formatDocumentCountMessage(stagedCount)} are now processing in the background.`,
      })
    }

    setIsStartingUpload(false)
  }

  const hasStagedFiles = Object.values(filesByType).some((file) => file?.status === 'staged')

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Document Upload
      </Typography>

      <Typography variant="body1" color="text.secondary" paragraph>
        Stage one PDF for NAAC Requirements and one for MVSR Evidence. Chunking starts only after you click Upload documents.
      </Typography>

      {!isHealthy && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          System is not healthy. Upload may not work properly.
        </Alert>
      )}

      {banner && (
        <Alert severity={banner.severity} sx={{ mb: 3 }}>
          {banner.text}
        </Alert>
      )}

      <Grid container spacing={3}>
        {(['naac_requirement', 'mvsr_evidence'] as DocumentType[]).map((documentType) => {
          const stagedFile = filesByType[documentType]
          const inputId = `${documentType}-file-input`

          return (
            <Grid item xs={12} md={6} key={documentType}>
              <Card variant="outlined" sx={{ height: '100%' }}>
                <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, height: '100%' }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
                    <Box>
                      <Typography variant="overline" color="text.secondary">
                        {labels[documentType]}
                      </Typography>
                      <Typography variant="h6">
                        {stagedFile ? stagedFile.name : `Choose ${labels[documentType]}`}
                      </Typography>
                    </Box>
                    {stagedFile && stagedFile.status !== 'queued' && stagedFile.status !== 'ingesting' && (
                      <IconButton aria-label={`Clear ${labels[documentType]}`} onClick={() => void clearStagedFile(documentType)}>
                        <CloseIcon />
                      </IconButton>
                    )}
                  </Stack>

                  <input
                    ref={getInputRef(documentType)}
                    id={inputId}
                    type="file"
                    accept=".pdf"
                    onChange={(event) => void handleFileSelect(documentType, event)}
                    style={{ display: 'none' }}
                  />

                  {!stagedFile && (
                    <label htmlFor={inputId}>
                      <Button
                        variant="outlined"
                        component="span"
                        startIcon={<CloudUploadIcon />}
                        fullWidth
                        sx={{ p: 3, borderStyle: 'dashed' }}
                      >
                        Choose PDF
                      </Button>
                    </label>
                  )}

                  {stagedFile && (
                    <Stack spacing={1.25}>
                      <Chip
                        label={stagedFile.status === 'staged' ? 'Ready to upload' : stagedFile.status}
                        color={
                          stagedFile.status === 'error'
                            ? 'error'
                            : stagedFile.status === 'queued'
                              ? 'success'
                              : 'primary'
                        }
                        size="small"
                        sx={{ alignSelf: 'flex-start' }}
                      />
                      <Typography variant="body2" color="text.secondary">
                        {(stagedFile.size / 1024 / 1024).toFixed(2)} MB
                      </Typography>
                      {stagedFile.savedAt && (
                        <Typography variant="body2" color="text.secondary">
                          Saved {new Date(stagedFile.savedAt).toLocaleString()}
                        </Typography>
                      )}
                      {stagedFile.requestedAt && (
                        <Typography variant="body2" color="text.secondary">
                          Upload requested {new Date(stagedFile.requestedAt).toLocaleString()}
                        </Typography>
                      )}
                      <Typography variant="body2">{stagedFile.message}</Typography>
                    </Stack>
                  )}
                </CardContent>
              </Card>
            </Grid>
          )
        })}
      </Grid>

      <Box sx={{ mt: 3 }}>
        <Button
          variant="contained"
          startIcon={<UploadIcon />}
          onClick={handleUpload}
          disabled={!hasStagedFiles || isStartingUpload}
        >
          {isStartingUpload ? 'Starting upload...' : 'Upload documents'}
        </Button>
        {isStartingUpload && <LinearProgress sx={{ mt: 2 }} />}
      </Box>

      <Card sx={{ mt: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Upload Guidelines
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>NAAC Requirements:</strong> Official NAAC documentation, criteria, guidelines, and assessment frameworks.
          </Typography>
          <Typography variant="body2" paragraph>
            <strong>MVSR Evidence:</strong> Institutional documents, policies, reports, and evidence supporting NAAC compliance.
          </Typography>
          <Typography variant="body2">
            Files are staged first, then chunked only when Upload documents is pressed.
          </Typography>
        </CardContent>
      </Card>
    </Box>
  )
}

export default DocumentUpload
