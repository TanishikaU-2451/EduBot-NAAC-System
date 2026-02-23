"""
Document Chunking for NAAC Compliance Intelligence System
Intelligent text chunking with context preservation and metadata inheritance
"""

import re
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class TextChunk:
    """Structure for text chunks with metadata"""
    text: str
    chunk_index: int
    start_page: int
    end_page: int
    chunk_type: str  # 'paragraph', 'section', 'table', 'list'
    metadata: Dict[str, Any]

class DocumentChunker:
    """
    Intelligent document chunker that preserves context and maintains metadata
    Optimized for NAAC compliance documents and MVSR institutional evidence
    """
    
    def __init__(self, 
                 chunk_size: int = 512,
                 chunk_overlap: int = 50,
                 min_chunk_size: int = 100):
        """
        Initialize document chunker
        
        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks in characters
            min_chunk_size: Minimum chunk size to avoid tiny chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        
        # Patterns for identifying document structures
        self.section_patterns = [
            r'^\s*(?:criterion|key\s+indicator)\s*[:-]?\s*\d+(?:\.\d+)*',  # NAAC sections
            r'^\s*chapter\s+\d+',                                          # Chapter headers
            r'^\s*\d+\.\s+[A-Za-z]',                                      # Numbered sections
            r'^\s*[A-Z][A-Z\s]{5,50}$',                                   # All-caps headers
        ]
        
        self.table_patterns = [
            r'\|.*\|',                                                     # Table rows with pipes
            r'^\s*\d+\s+[^\d].*[^\d]\s+\d+\s*$',                         # Tabular data
        ]
        
        self.list_patterns = [
            r'^\s*[•·\-\*]\s+',                                           # Bullet points
            r'^\s*\d+\.\s+',                                              # Numbered lists
            r'^\s*[a-z]\)\s+',                                            # Lettered lists
        ]
    
    def chunk_document(self, 
                      text: str, 
                      metadata: Dict[str, Any]) -> List[TextChunk]:
        """
        Chunk document text intelligently preserving context
        
        Args:
            text: Full document text
            metadata: Document metadata to inherit
            
        Returns:
            List of TextChunk objects
        """
        if not text or len(text.strip()) < self.min_chunk_size:
            logger.warning("Document too short to chunk effectively")
            return []
        
        # Pre-process text
        text = self._preprocess_text(text)
        
        # Identify document structure
        sections = self._identify_sections(text)
        
        # Chunk each section
        all_chunks = []
        chunk_index = 0
        
        for section in sections:
            section_chunks = self._chunk_section(section, metadata, chunk_index)
            all_chunks.extend(section_chunks)
            chunk_index += len(section_chunks)
        
        logger.info(f"Created {len(all_chunks)} chunks from document")
        return all_chunks
    
    def _preprocess_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Remove excessive whitespace while preserving structure
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple newlines to double
        text = re.sub(r'[ \t]+', ' ', text)             # Multiple spaces to single
        text = re.sub(r'\r\n', '\n', text)              # Windows line endings to Unix
        
        # Fix common PDF extraction issues
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # Missing spaces between sentences
        text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)       # Hyphenated words across lines
        
        return text.strip()
    
    def _identify_sections(self, text: str) -> List[Dict[str, Any]]:
        """
        Identify logical sections in the document
        
        Returns:
            List of section dictionaries with text, type, page info
        """
        lines = text.split('\n')
        sections = []
        current_section = {
            'text': '',
            'type': 'content',
            'start_line': 0,
            'start_page': 1,
            'end_page': 1
        }
        
        for line_num, line in enumerate(lines):
            stripped_line = line.strip()
            
            # Check if this is a section header
            is_header = False
            for pattern in self.section_patterns:
                if re.match(pattern, stripped_line, re.IGNORECASE):
                    is_header = True
                    break
            
            # Extract page number if present
            page_match = re.search(r'--- Page (\d+) ---', line)
            if page_match:
                current_section['end_page'] = int(page_match.group(1))
                continue
            
            # If we found a header and we have content, start a new section
            if is_header and current_section['text'].strip():
                sections.append(current_section)
                current_section = {
                    'text': line + '\n',
                    'type': self._classify_section_type(stripped_line),
                    'start_line': line_num,
                    'start_page': current_section['end_page'],
                    'end_page': current_section['end_page']
                }
            else:
                current_section['text'] += line + '\n'
        
        # Add the last section
        if current_section['text'].strip():
            sections.append(current_section)
        
        # If no sections found, treat entire text as one section
        if not sections:
            sections = [{
                'text': text,
                'type': 'content',
                'start_line': 0,
                'start_page': 1,
                'end_page': self._estimate_total_pages(text)
            }]
        
        return sections
    
    def _classify_section_type(self, header_text: str) -> str:
        """Classify the type of section based on header text"""
        header_lower = header_text.lower()
        
        if any(word in header_lower for word in ['criterion', 'indicator', 'key']):
            return 'criterion'
        elif any(word in header_lower for word in ['table', 'figure', 'chart']):
            return 'table'
        elif any(word in header_lower for word in ['list', 'points', 'items']):
            return 'list'
        elif any(word in header_lower for word in ['chapter', 'section']):
            return 'section'
        else:
            return 'content'
    
    def _chunk_section(self, 
                      section: Dict[str, Any], 
                      base_metadata: Dict[str, Any],
                      start_chunk_index: int) -> List[TextChunk]:
        """
        Chunk a single section intelligently
        
        Args:
            section: Section dictionary with text and metadata
            base_metadata: Base metadata to inherit
            start_chunk_index: Starting index for chunks
            
        Returns:
            List of TextChunk objects
        """
        section_text = section['text']
        
        if len(section_text) <= self.chunk_size:
            # Section fits in one chunk
            chunk_metadata = base_metadata.copy()
            chunk_metadata.update({
                'section_type': section['type'],
                'start_page': section['start_page'],
                'end_page': section['end_page']
            })
            
            return [TextChunk(
                text=section_text.strip(),
                chunk_index=start_chunk_index,
                start_page=section['start_page'],
                end_page=section['end_page'],
                chunk_type=section['type'],
                metadata=chunk_metadata
            )]
        
        # Section needs to be split
        return self._split_large_section(section, base_metadata, start_chunk_index)
    
    def _split_large_section(self, 
                           section: Dict[str, Any],
                           base_metadata: Dict[str, Any],
                           start_chunk_index: int) -> List[TextChunk]:
        """Split large sections while preserving context"""
        
        text = section['text']
        chunks = []
        
        # Try splitting by paragraphs first
        paragraphs = self._split_by_paragraphs(text)
        
        current_chunk = ""
        current_pages = [section['start_page']]
        
        for paragraph in paragraphs:
            # Check if adding this paragraph would exceed chunk size
            if (len(current_chunk) + len(paragraph) > self.chunk_size and 
                len(current_chunk) > self.min_chunk_size):
                
                # Create chunk with current content
                chunk_metadata = base_metadata.copy()
                chunk_metadata.update({
                    'section_type': section['type'],
                    'start_page': min(current_pages),
                    'end_page': max(current_pages)
                })
                
                chunks.append(TextChunk(
                    text=current_chunk.strip(),
                    chunk_index=start_chunk_index + len(chunks),
                    start_page=min(current_pages),
                    end_page=max(current_pages),
                    chunk_type=section['type'],
                    metadata=chunk_metadata
                ))
                
                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk, self.chunk_overlap)
                current_chunk = overlap_text + paragraph
                current_pages = [max(current_pages)]
            else:
                current_chunk += paragraph
            
            # Track page numbers in paragraph
            page_matches = re.findall(r'--- Page (\d+) ---', paragraph)
            for page_match in page_matches:
                current_pages.append(int(page_match))
        
        # Add final chunk if there's remaining content
        if current_chunk.strip():
            chunk_metadata = base_metadata.copy()
            chunk_metadata.update({
                'section_type': section['type'],
                'start_page': min(current_pages) if current_pages else section['start_page'],
                'end_page': max(current_pages) if current_pages else section['end_page']
            })
            
            chunks.append(TextChunk(
                text=current_chunk.strip(),
                chunk_index=start_chunk_index + len(chunks),
                start_page=min(current_pages) if current_pages else section['start_page'],
                end_page=max(current_pages) if current_pages else section['end_page'],
                chunk_type=section['type'],
                metadata=chunk_metadata
            ))
        
        return chunks
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs preserving structure"""
        # Split by double newlines (paragraph breaks)
        paragraphs = re.split(r'\n\s*\n', text)
        
        # Clean up and filter empty paragraphs
        cleaned_paragraphs = []
        for para in paragraphs:
            cleaned = para.strip()
            if cleaned and len(cleaned) > 10:  # Filter very short paragraphs
                cleaned_paragraphs.append(cleaned + '\n\n')
        
        return cleaned_paragraphs if cleaned_paragraphs else [text]
    
    def _get_overlap_text(self, text: str, overlap_size: int) -> str:
        """Get the last portion of text for overlap"""
        if len(text) <= overlap_size:
            return text
        
        # Try to find a good breaking point (sentence end)
        overlap_text = text[-overlap_size:]
        sentence_end = overlap_text.rfind('.')
        
        if sentence_end != -1 and sentence_end > overlap_size // 2:
            return text[-(overlap_size - sentence_end):] 
        
        return overlap_text
    
    def _estimate_total_pages(self, text: str) -> int:
        """Estimate total pages from text"""
        page_markers = re.findall(r'--- Page (\d+) ---', text)
        if page_markers:
            return max(int(p) for p in page_markers)
        
        # Rough estimate: 500 characters per page
        estimated = max(1, len(text) // 500)
        return estimated
    
    def prepare_for_vectorstore(self, chunks: List[TextChunk]) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Prepare chunks for vector store ingestion
        
        Args:
            chunks: List of TextChunk objects
            
        Returns:
            Tuple of (documents, metadatas) ready for ChromaDB
        """
        documents = []
        metadatas = []
        
        for chunk in chunks:
            # Clean text for embedding
            clean_text = re.sub(r'--- Page \d+ ---', '', chunk.text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            if len(clean_text) < self.min_chunk_size:
                continue  # Skip chunks that are too small
            
            documents.append(clean_text)
            
            # Prepare metadata for ChromaDB
            metadata = chunk.metadata.copy()
            metadata.update({
                'chunk_index': chunk.chunk_index,
                'chunk_type': chunk.chunk_type,
                'start_page': chunk.start_page,
                'end_page': chunk.end_page,
                'chunk_length': len(clean_text)
            })
            
            # Ensure all metadata values are strings or numbers (ChromaDB requirement)
            cleaned_metadata = {}
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    cleaned_metadata[key] = value
                else:
                    cleaned_metadata[key] = str(value)
            
            metadatas.append(cleaned_metadata)
        
        logger.info(f"Prepared {len(documents)} chunks for vector store")
        return documents, metadatas
    
    def get_chunk_statistics(self, chunks: List[TextChunk]) -> Dict[str, Any]:
        """Get statistics about the chunks"""
        if not chunks:
            return {"total_chunks": 0}
        
        chunk_lengths = [len(chunk.text) for chunk in chunks]
        chunk_types = [chunk.chunk_type for chunk in chunks]
        
        from collections import Counter
        type_counts = Counter(chunk_types)
        
        return {
            "total_chunks": len(chunks),
            "avg_chunk_length": sum(chunk_lengths) // len(chunk_lengths),
            "min_chunk_length": min(chunk_lengths),
            "max_chunk_length": max(chunk_lengths),
            "chunk_types": dict(type_counts),
            "total_pages_covered": max(chunk.end_page for chunk in chunks) if chunks else 0
        }