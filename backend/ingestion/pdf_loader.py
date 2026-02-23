"""
PDF Document Loader for NAAC Compliance Intelligence System
Handles PDF extraction with metadata preservation
"""

import pdfplumber
import PyPDF2
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import hashlib
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class DocumentMetadata:
    """Structure for document metadata"""
    file_path: str
    file_name: str
    total_pages: int
    file_hash: str
    extraction_method: str
    document_type: str  # 'naac_requirement' or 'mvsr_evidence'
    
    # NAAC-specific fields
    criterion: Optional[str] = None
    indicator: Optional[str] = None
    version: Optional[str] = None
    
    # MVSR-specific fields
    document_title: Optional[str] = None
    year: Optional[int] = None
    category: Optional[str] = None

class PDFLoader:
    """
    Intelligent PDF loader that extracts text and infers metadata
    Handles both NAAC requirement documents and MVSR evidence documents
    """
    
    def __init__(self):
        """Initialize PDF loader"""
        self.naac_criterion_patterns = {
            r'criterion\s*[:-]?\s*1\b': '1',
            r'criterion\s*[:-]?\s*2\b': '2', 
            r'criterion\s*[:-]?\s*3\b': '3',
            r'criterion\s*[:-]?\s*4\b': '4',
            r'criterion\s*[:-]?\s*5\b': '5',
            r'criterion\s*[:-]?\s*6\b': '6',
            r'criterion\s*[:-]?\s*7\b': '7'
        }
        
        self.indicator_pattern = r'\b(?:indicator|key\s*indicator)\s*[:-]?\s*(\d+\.\d+\.\d+)\b'
        
        # MVSR document category patterns
        self.mvsr_patterns = {
            r'(?:policy|policies)': 'policies',
            r'(?:iqac|internal.*quality)': 'iqac',
            r'(?:governance|governing|management)': 'governance',
            r'(?:student.*support|support.*student)': 'student_support',
            r'(?:report|annual.*report|self.*study)': 'reports'
        }
    
    def load_pdf(self, file_path: str, document_type: str) -> Tuple[str, DocumentMetadata]:
        """
        Load PDF and extract text with metadata inference
        
        Args:
            file_path: Path to PDF file
            document_type: 'naac_requirement' or 'mvsr_evidence'
            
        Returns:
            Tuple of (extracted_text, metadata)
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        
        # Try pdfplumber first (better for complex layouts)
        try:
            text, pages = self._extract_with_pdfplumber(file_path)
            extraction_method = "pdfplumber"
            logger.info(f"Extracted {len(text)} characters using pdfplumber from {file_path.name}")
        except Exception as e:
            logger.warning(f"pdfplumber failed for {file_path.name}: {e}")
            try:
                # Fallback to PyPDF2
                text, pages = self._extract_with_pypdf2(file_path)
                extraction_method = "pypdf2"
                logger.info(f"Extracted {len(text)} characters using PyPDF2 from {file_path.name}")
            except Exception as e2:
                logger.error(f"Both extraction methods failed for {file_path.name}: {e2}")
                raise
        
        # Generate file hash for duplicate detection
        file_hash = self._calculate_file_hash(file_path)
        
        # Create base metadata
        metadata = DocumentMetadata(
            file_path=str(file_path),
            file_name=file_path.name,
            total_pages=pages,
            file_hash=file_hash,
            extraction_method=extraction_method,
            document_type=document_type
        )
        
        # Infer specific metadata based on document type
        if document_type == "naac_requirement":
            self._infer_naac_metadata(text, file_path.name, metadata)
        elif document_type == "mvsr_evidence":
            self._infer_mvsr_metadata(text, file_path.name, metadata)
        
        return text, metadata
    
    def _extract_with_pdfplumber(self, file_path: Path) -> Tuple[str, int]:
        """Extract text using pdfplumber (handles tables and complex layouts better)"""
        text_parts = []
        
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            
            for page_num, page in enumerate(pdf.pages):
                try:
                    # Extract text
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}\n")
                    
                    # Extract tables if present
                    tables = page.extract_tables()
                    if tables:
                        for table_num, table in enumerate(tables):
                            table_text = self._format_table(table)
                            text_parts.append(f"--- Table {table_num + 1} on Page {page_num + 1} ---\n{table_text}\n")
                
                except Exception as e:
                    logger.warning(f"Error extracting page {page_num + 1} from {file_path.name}: {e}")
                    continue
        
        return "\n".join(text_parts), total_pages
    
    def _extract_with_pypdf2(self, file_path: Path) -> Tuple[str, int]:
        """Fallback extraction using PyPDF2"""
        text_parts = []
        
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            total_pages = len(reader.pages)
            
            for page_num, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}\n")
                except Exception as e:
                    logger.warning(f"Error extracting page {page_num + 1} from {file_path.name}: {e}")
                    continue
        
        return "\n".join(text_parts), total_pages
    
    def _format_table(self, table: List[List]) -> str:
        """Format extracted table as structured text"""
        if not table:
            return ""
        
        formatted_rows = []
        for row in table:
            if row:  # Skip empty rows
                # Clean and join cells
                cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                formatted_rows.append(" | ".join(cleaned_row))
        
        return "\n".join(formatted_rows)
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file for duplicate detection"""
        hash_sha256 = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        
        return hash_sha256.hexdigest()[:16]  # First 16 characters
    
    def _infer_naac_metadata(self, text: str, filename: str, metadata: DocumentMetadata):
        """Infer NAAC-specific metadata from text content"""
        text_lower = text.lower()
        
        # Detect criterion
        for pattern, criterion in self.naac_criterion_patterns.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                metadata.criterion = criterion
                logger.debug(f"Detected NAAC criterion {criterion} in {filename}")
                break
        
        # Detect indicator
        indicator_match = re.search(self.indicator_pattern, text_lower, re.IGNORECASE)
        if indicator_match:
            metadata.indicator = indicator_match.group(1)
            logger.debug(f"Detected NAAC indicator {metadata.indicator} in {filename}")
        
        # Detect version/year from filename or text
        year_match = re.search(r'(?:20\d{2}|2025|2024|2023)', text + " " + filename)
        if year_match:
            metadata.version = year_match.group(0)
        else:
            metadata.version = "2025"  # Default to current
        
        # Extract document title from first few lines
        lines = text.split('\n')[:10]
        for line in lines:
            clean_line = line.strip()
            if len(clean_line) > 10 and not clean_line.isdigit():
                metadata.document_title = clean_line[:100]  # First meaningful line as title
                break
    
    def _infer_mvsr_metadata(self, text: str, filename: str, metadata: DocumentMetadata):
        """Infer MVSR-specific metadata from text content"""
        text_lower = text.lower()
        filename_lower = filename.lower()
        
        # Detect category
        combined_text = f"{text_lower} {filename_lower}"
        for pattern, category in self.mvsr_patterns.items():
            if re.search(pattern, combined_text, re.IGNORECASE):
                metadata.category = category
                logger.debug(f"Detected MVSR category {category} in {filename}")
                break
        
        if not metadata.category:
            metadata.category = "reports"  # Default category
        
        # Extract year
        year_match = re.search(r'(?:20\d{2})', combined_text)
        if year_match:
            metadata.year = int(year_match.group(0))
        else:
            metadata.year = 2023  # Default year
        
        # Extract document title
        lines = text.split('\n')[:15]
        title_candidates = []
        
        for line in lines:
            clean_line = line.strip()
            if (len(clean_line) > 5 and 
                not clean_line.isdigit() and 
                not re.match(r'^page\s*\d+', clean_line, re.IGNORECASE)):
                title_candidates.append(clean_line)
        
        if title_candidates:
            # Take the longest meaningful line as title
            metadata.document_title = max(title_candidates, key=len)[:100]
        else:
            metadata.document_title = filename.replace('.pdf', '').replace('_', ' ').title()
        
        # Try to map to NAAC criterion based on content
        self._map_mvsr_to_criterion(text_lower, metadata)
    
    def _map_mvsr_to_criterion(self, text: str, metadata: DocumentMetadata):
        """Map MVSR document to relevant NAAC criterion based on content"""
        criterion_keywords = {
            '1': ['vision', 'mission', 'planning', 'strategic', 'institutional', 'leadership'],
            '2': ['teaching', 'learning', 'student', 'academic', 'curriculum', 'faculty'],
            '3': ['research', 'innovation', 'consultancy', 'extension', 'outreach'],
            '4': ['infrastructure', 'facility', 'library', 'laboratory', 'ict', 'technology'],
            '5': ['student support', 'progression', 'guidance', 'counseling', 'placement'],
            '6': ['governance', 'leadership', 'management', 'finance', 'administration'],
            '7': ['innovation', 'best practices', 'institutional distinctiveness']
        }
        
        # Score each criterion based on keyword matches
        scores = {}
        for criterion, keywords in criterion_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                scores[criterion] = score
        
        # Assign the highest scoring criterion
        if scores:
            metadata.criterion = max(scores.items(), key=lambda x: x[1])[0]
            logger.debug(f"Mapped MVSR document to criterion {metadata.criterion}")
        else:
            metadata.criterion = "2"  # Default to criterion 2 (most common)
    
    def batch_load_directory(self, 
                           directory_path: str, 
                           document_type: str,
                           file_pattern: str = "*.pdf") -> List[Tuple[str, DocumentMetadata]]:
        """
        Load all PDFs from a directory
        
        Args:
            directory_path: Path to directory containing PDFs
            document_type: 'naac_requirement' or 'mvsr_evidence'
            file_pattern: File pattern to match (default: *.pdf)
            
        Returns:
            List of (text, metadata) tuples
        """
        directory = Path(directory_path)
        
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        pdf_files = list(directory.glob(file_pattern))
        
        if not pdf_files:
            logger.warning(f"No PDF files found in {directory} matching pattern {file_pattern}")
            return []
        
        results = []
        for pdf_file in pdf_files:
            try:
                text, metadata = self.load_pdf(str(pdf_file), document_type)
                results.append((text, metadata))
                logger.info(f"Successfully loaded {pdf_file.name}")
            except Exception as e:
                logger.error(f"Failed to load {pdf_file.name}: {e}")
                continue
        
        logger.info(f"Loaded {len(results)} out of {len(pdf_files)} PDF files from {directory}")
        return results