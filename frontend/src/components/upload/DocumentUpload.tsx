import React, { useState } from 'react'
import {
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  Alert,
  LinearProgress,
  Grid,
  Chip,
  List,
  ListItem,
  ListItemText,
} from '@mui/material'
import {
  Upload as UploadIcon,
  CloudUpload as CloudUploadIcon,
} from '@mui/icons-material'
import { useSystem } from '../../contexts/SystemContext'
import apiService, { getErrorMessage } from '../../services/api'

const DocumentUpload: React.FC = () => {
  const [filesByType, setFilesByType] = useState<Record<'naac_requirement' | 'mvsr_evidence', File[]>>({
    naac_requirement: [],
    mvsr_evidence: [],
  })
  const [isUploading, setIsUploading] = useState(false)
  const [uploadResults, setUploadResults] = useState<string[]>([])
  const [documentType, setDocumentType] = useState<'naac_requirement' | 'mvsr_evidence'>('mvsr_evidence')
  const { isHealthy } = useSystem()

  const selectedFiles = filesByType[documentType]

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      const nextFiles = Array.from(event.target.files)
      setFilesByType((prev) => ({
        ...prev,
        [documentType]: nextFiles,
      }))

      // Allow selecting the same file again after switching types.
      event.target.value = ''
    }
  }

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return

    setIsUploading(true)
    setUploadResults([])

    try {
      const results = await Promise.all(
        selectedFiles.map(async (file) => {
          try {
            const result = await apiService.uploadDocument(file, documentType)
            return `✅ ${file.name}: ${result.message}`
          } catch (error) {
            return `❌ ${file.name}: ${getErrorMessage(error)}`
          }
        })
      )
      setUploadResults(results)
    } catch (error) {
      setUploadResults([`❌ Upload failed: ${getErrorMessage(error)}`])
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Document Upload
      </Typography>
      
      <Typography variant="body1" color="text.secondary" paragraph>
        Upload PDF documents to add them to the knowledge base. Choose the document type based on content.
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Upload Documents
              </Typography>
              
              {!isHealthy && (
                <Alert severity="warning" sx={{ mb: 2 }}>
                  System is not healthy. Upload may not work properly.
                </Alert>
              )}

              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Document Type:
                </Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Chip
                    label="NAAC Requirements"
                    color={documentType === 'naac_requirement' ? 'primary' : 'default'}
                    clickable
                    onClick={() => setDocumentType('naac_requirement')}
                  />
                  <Chip
                    label="MVSR Evidence"
                    color={documentType === 'mvsr_evidence' ? 'primary' : 'default'}
                    clickable
                    onClick={() => setDocumentType('mvsr_evidence')}
                  />
                </Box>
              </Box>

              <Box sx={{ mb: 2 }}>
                <input
                  type="file"
                  accept=".pdf"
                  multiple
                  onChange={handleFileSelect}
                  style={{ display: 'none' }}
                  id="file-upload"
                />
                <label htmlFor="file-upload">
                  <Button
                    variant="outlined"
                    component="span"
                    startIcon={<CloudUploadIcon />}
                    fullWidth
                    sx={{ p: 3, borderStyle: 'dashed' }}
                  >
                    Choose PDF Files
                  </Button>
                </label>
              </Box>

              {selectedFiles.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    Selected Files ({documentType === 'naac_requirement' ? 'NAAC Requirements' : 'MVSR Evidence'}):
                  </Typography>
                  <List dense>
                    {selectedFiles.map((file, index) => (
                      <ListItem key={index}>
                        <ListItemText
                          primary={file.name}
                          secondary={`${(file.size / 1024 / 1024).toFixed(2)} MB`}
                        />
                      </ListItem>
                    ))}
                  </List>
                </Box>
              )}

              <Button
                variant="contained"
                startIcon={<UploadIcon />}
                onClick={handleUpload}
                disabled={selectedFiles.length === 0 || isUploading}
                fullWidth
              >
                {isUploading ? 'Uploading...' : `Upload ${selectedFiles.length} File(s)`}
              </Button>

              {isUploading && <LinearProgress sx={{ mt: 2 }} />}

              {uploadResults.length > 0 && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    Upload Results:
                  </Typography>
                  <List dense>
                    {uploadResults.map((result, index) => (
                      <ListItem key={index}>
                        <ListItemText primary={result} />
                      </ListItem>
                    ))}
                  </List>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card>
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
              
              <Typography variant="body2" paragraph>
                <strong>File Requirements:</strong>
                • PDF format only
                • Maximum 50MB per file
                • Clear, readable text
                • Properly structured content
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}

export default DocumentUpload