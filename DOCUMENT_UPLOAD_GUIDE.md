# Document Upload Guide for NAAC Compliance Intelligence System

## 📁 Where to Place Initial Documents

I've created the following directories for you:

### 🏛️ NAAC Documents (`data/naac_documents/`)
Place official NAAC documentation here for system understanding of requirements:

**Required Documents:**
- NAAC Manual for Universities (Latest version)
- Assessment and Accreditation Framework  
- NAAC Criterion Documents (1.1 to 7.3)
- Self Study Report (SSR) Guidelines
- Data Validation & Verification (DVV) Guidelines
- Best Practices Framework
- Institutional Information for Quality Assessment (IIQA)

**File Naming Convention:**
- `NAAC_Manual_University_2024.pdf`
- `NAAC_Criterion_1_1_Curricular_Planning.pdf`
- `NAAC_Assessment_Framework_2024.pdf`
- `DVV_Guidelines_2024.pdf`

### 🎓 MVSR Evidence Documents (`data/mvsr_documents/`)
Place MVSR Engineering College institutional documents here:

**Required Documents:**
- Institutional Profile and History
- Academic Policies and Procedures
- Faculty Details and Profiles
- Student Admission and Outcome Records
- Infrastructure and Facility Reports
- Research and Development Documentation
- Industry Collaboration Records
- Alumni and Placement Reports
- Financial Audit Reports
- Governance and Leadership Documents

**File Naming Convention:**
- `MVSR_Academic_Policy_2024.pdf`
- `MVSR_Faculty_Profiles_2024.pdf` 
- `MVSR_Infrastructure_Report_2024.pdf`
- `MVSR_Research_Publications_2023-24.pdf`

## 📥 How to Upload Documents

### Method 1: Direct File Placement (Recommended for Initial Setup)
1. Copy your PDF documents to the appropriate directories:
   - `data/naac_documents/` - for NAAC requirements
   - `data/mvsr_documents/` - for MVSR evidence

2. The system will automatically detect and process these documents when you run the startup script.

### Method 2: Web Interface Upload (After System Starts)
1. Start the system using `start.bat`
2. Open http://localhost:3000 in your browser
3. Go to "Document Upload" section
4. Select document type (NAAC Requirements or MVSR Evidence)
5. Upload PDF files directly through the web interface

### Method 3: API Upload (For Batch Operations)
Use the `/upload` endpoint to programmatically upload documents.

## 🔄 Document Processing

The system will:
1. **Extract text** from PDF documents
2. **Chunk content** into meaningful segments
3. **Generate embeddings** for semantic search
4. **Store in ChromaDB** with proper metadata
5. **Index for retrieval** during queries

## 📋 Document Requirements

- **Format**: PDF only (readable text, not scanned images)
- **Size**: Maximum 50MB per file
- **Quality**: Clear, well-structured content
- **Language**: English
- **Content**: Official institutional documents preferred

## 🚀 Getting Started

1. **Place initial documents** in the directories above
2. **Run the startup script**: `start.bat`
3. **Wait for processing** - initial document ingestion may take several minutes
4. **Start querying** the system about NAAC compliance

## 💡 Tips

- **Start with key documents**: NAAC Manual and MVSR Academic Policy
- **Use descriptive filenames** for easier management
- **Check document quality** before upload - ensure text is extractable
- **Add documents incrementally** to monitor processing progress
- **Use the web interface** for ongoing document additions

## 📊 Monitoring Upload Progress

Check the System Dashboard at http://localhost:3000/dashboard to monitor:
- Document processing status
- Knowledge base statistics
- System health during uploads