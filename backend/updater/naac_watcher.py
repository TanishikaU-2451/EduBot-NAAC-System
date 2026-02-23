"""
NAAC Website Watcher for Automatic Updates
Monitors NAAC website for new documents and guideline changes
"""

import requests
from bs4 import BeautifulSoup
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import logging
from datetime import datetime, timedelta
import time
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
import re

logger = logging.getLogger(__name__)

@dataclass
class DocumentInfo:
    """Information about a discovered document"""
    title: str
    url: str
    file_type: str  # 'pdf', 'doc', 'docx', etc.
    size: Optional[str] = None
    last_modified: Optional[str] = None
    checksum: Optional[str] = None
    criterion: Optional[str] = None
    version: Optional[str] = None
    document_type: str = 'naac_requirement'

@dataclass
class WatchResult:
    """Result of website watching operation"""
    timestamp: str
    total_documents_found: int
    new_documents: List[DocumentInfo]
    updated_documents: List[DocumentInfo]
    errors: List[str]
    success: bool

class NAACWebsiteWatcher:
    """
    Monitors NAAC website for document updates
    Detects new and modified documents automatically
    """
    
    def __init__(self, 
                 cache_dir: str = "./naac_cache",
                 user_agent: str = "NAAC-Compliance-Bot/1.0"):
        """
        Initialize NAAC website watcher
        
        Args:
            cache_dir: Directory to store cached document information
            user_agent: User agent string for web requests
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive'
        })
        
        # NAAC website URLs to monitor
        self.naac_urls = {
            'main_site': 'https://www.naac.gov.in',
            'assessment_docs': 'https://www.naac.gov.in/assessment-and-accreditation',
            'manuals': 'https://www.naac.gov.in/images/docs/Manuals',
            'criteria_docs': 'https://www.naac.gov.in/images/docs/Criteria',
            'ssr_manual': 'https://www.naac.gov.in/images/docs/SSR',
            'guidelines': 'https://www.naac.gov.in/images/docs/Guidelines',
            'circulars': 'https://www.naac.gov.in/images/docs/Circulars'
        }
        
        # Document cache
        self.document_cache = self._load_document_cache()
        
        # File type patterns
        self.document_patterns = [
            r'\.pdf$', r'\.doc$', r'\.docx$', r'\.rtf$'
        ]
        
        # Criterion detection patterns
        self.criterion_patterns = {
            'criterion_1': r'curricular|curriculum|academic.*program',
            'criterion_2': r'teaching.*learning|faculty|evaluation|assessment',
            'criterion_3': r'research|innovation|extension|consultancy',
            'criterion_4': r'infrastructure|learning.*resources|library|laboratory',
            'criterion_5': r'student.*support|progression|guidance',
            'criterion_6': r'governance|leadership|management|administration',
            'criterion_7': r'institutional.*values|best.*practices|distinctiveness'
        }
    
    def watch_for_updates(self, 
                         check_all_urls: bool = True,
                         specific_urls: Optional[List[str]] = None) -> WatchResult:
        """
        Check NAAC website for document updates
        
        Args:
            check_all_urls: Whether to check all configured URLs
            specific_urls: List of specific URLs to check (if check_all_urls is False)
            
        Returns:
            WatchResult with discovered updates
        """
        logger.info("Starting NAAC website watch for updates")
        
        start_time = datetime.now()
        new_documents = []
        updated_documents = []
        errors = []
        
        # Determine URLs to check
        urls_to_check = {}
        if check_all_urls:
            urls_to_check = self.naac_urls
        elif specific_urls:
            urls_to_check = {url: url for url in specific_urls}
        
        # Check each URL
        for url_name, url in urls_to_check.items():
            try:
                logger.info(f"Checking {url_name}: {url}")
                
                new_docs, updated_docs = self._check_url_for_documents(url, url_name)
                new_documents.extend(new_docs)
                updated_documents.extend(updated_docs)
                
                # Add delay to be respectful to the server
                time.sleep(2)
                
            except Exception as e:
                error_msg = f"Error checking {url_name} ({url}): {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Update cache with new findings
        self._update_document_cache(new_documents + updated_documents)
        
        result = WatchResult(
            timestamp=start_time.isoformat(),
            total_documents_found=len(new_documents) + len(updated_documents),
            new_documents=new_documents,
            updated_documents=updated_documents,
            errors=errors,
            success=len(errors) == 0
        )
        
        logger.info(f"Watch completed: {len(new_documents)} new, {len(updated_documents)} updated documents")
        return result
    
    def _check_url_for_documents(self, 
                                url: str, 
                                url_name: str) -> Tuple[List[DocumentInfo], List[DocumentInfo]]:
        """
        Check a specific URL for documents
        
        Returns:
            Tuple of (new_documents, updated_documents)
        """
        new_documents = []
        updated_documents = []
        
        try:
            # Get page content
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all links to documents
            document_links = self._extract_document_links(soup, url)
            
            # Process each document link
            for link_url, link_text in document_links:
                try:
                    doc_info = self._analyze_document_link(link_url, link_text, url_name)
                    
                    if doc_info:
                        # Check if document is new or updated
                        cached_doc = self._get_cached_document(doc_info.url)
                        
                        if not cached_doc:
                            new_documents.append(doc_info)
                            logger.info(f"New document found: {doc_info.title}")
                        elif self._is_document_updated(cached_doc, doc_info):
                            updated_documents.append(doc_info)
                            logger.info(f"Updated document found: {doc_info.title}")
                
                except Exception as e:
                    logger.warning(f"Error analyzing document link {link_url}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error checking URL {url}: {e}")
            raise
        
        return new_documents, updated_documents
    
    def _extract_document_links(self, soup: BeautifulSoup, base_url: str) -> List[Tuple[str, str]]:
        """Extract document links from HTML"""
        
        document_links = []
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link['href']
            link_text = link.get_text(strip=True)
            
            # Convert relative URLs to absolute
            if href.startswith('/'):
                full_url = urljoin(base_url, href)
            elif href.startswith('http'):
                full_url = href
            else:
                full_url = urljoin(base_url + '/', href)
            
            # Check if this is a document link
            if self._is_document_link(full_url):
                document_links.append((full_url, link_text))
        
        # Also check for embedded links in text and other elements
        for element in soup.find_all(text=re.compile(r'https?://[^\s]+\.(?:pdf|doc|docx)')):
            urls = re.findall(r'https?://[^\s]+\.(?:pdf|doc|docx)', element)
            for url in urls:
                document_links.append((url, "Embedded link"))
        
        return document_links
    
    def _is_document_link(self, url: str) -> bool:
        """Check if URL points to a document"""
        
        url_lower = url.lower()
        
        # Check file extension patterns
        for pattern in self.document_patterns:
            if re.search(pattern, url_lower):
                return True
        
        return False
    
    def _analyze_document_link(self, 
                              url: str, 
                              link_text: str, 
                              source_section: str) -> Optional[DocumentInfo]:
        """
        Analyze a document link and extract metadata
        
        Args:
            url: Document URL
            link_text: Link text from HTML
            source_section: Section where link was found
            
        Returns:
            DocumentInfo object or None if analysis fails
        """
        try:
            # Get file info without downloading
            head_response = self.session.head(url, timeout=15)
            
            # Extract file info
            file_size = head_response.headers.get('Content-Length')
            last_modified = head_response.headers.get('Last-Modified')
            content_type = head_response.headers.get('Content-Type', '')
            
            # Determine file type from URL or content type
            file_type = self._determine_file_type(url, content_type)
            
            # Generate title from link text or filename
            title = self._generate_title(link_text, url)
            
            # Detect criterion from title and URL
            criterion = self._detect_criterion(title, url, source_section)
            
            # Detect version/year
            version = self._detect_version(title, url)
            
            # Generate URL checksum for change detection
            url_checksum = hashlib.md5(url.encode()).hexdigest()[:16]
            
            doc_info = DocumentInfo(
                title=title,
                url=url,
                file_type=file_type,
                size=file_size,
                last_modified=last_modified,
                checksum=url_checksum,
                criterion=criterion,
                version=version,
                document_type='naac_requirement'
            )
            
            return doc_info
            
        except Exception as e:
            logger.warning(f"Error analyzing document {url}: {e}")
            return None
    
    def _determine_file_type(self, url: str, content_type: str) -> str:
        """Determine file type from URL and content type"""
        
        # Check URL extension first
        url_lower = url.lower()
        if url_lower.endswith('.pdf'):
            return 'pdf'
        elif url_lower.endswith('.doc'):
            return 'doc'
        elif url_lower.endswith('.docx'):
            return 'docx'
        elif url_lower.endswith('.rtf'):
            return 'rtf'
        
        # Check content type
        if 'pdf' in content_type.lower():
            return 'pdf'
        elif 'msword' in content_type.lower():
            return 'doc'
        elif 'officedocument' in content_type.lower():
            return 'docx'
        
        return 'unknown'
    
    def _generate_title(self, link_text: str, url: str) -> str:
        """Generate document title from link text or URL"""
        
        # Clean link text
        if link_text and len(link_text.strip()) > 0:
            title = link_text.strip()
            # Remove common prefixes
            title = re.sub(r'^(click here|download|view|pdf|doc)\s*[:\-]?\s*', '', title, flags=re.IGNORECASE)
            if len(title) > 5:
                return title[:100]  # Limit length
        
        # Extract from filename in URL
        parsed_url = urlparse(url)
        filename = Path(parsed_url.path).name
        
        if filename:
            # Remove extension and clean up
            title = Path(filename).stem
            title = title.replace('_', ' ').replace('-', ' ')
            title = ' '.join(word.capitalize() for word in title.split())
            return title
        
        return f"NAAC Document ({datetime.now().strftime('%Y-%m-%d')})"
    
    def _detect_criterion(self, title: str, url: str, source: str) -> Optional[str]:
        """Detect NAAC criterion from document title, URL, and source"""
        
        combined_text = f"{title} {url} {source}".lower()
        
        # Check each criterion pattern
        for criterion, pattern in self.criterion_patterns.items():
            if re.search(pattern, combined_text, re.IGNORECASE):
                return criterion.split('_')[1]  # Return just the number
        
        # Check for explicit criterion numbers
        criterion_match = re.search(r'criterion\s*[:\-]?\s*(\d+)', combined_text, re.IGNORECASE)
        if criterion_match:
            return criterion_match.group(1)
        
        return None
    
    def _detect_version(self, title: str, url: str) -> str:
        """Detect document version or year"""
        
        combined_text = f"{title} {url}"
        
        # Look for years
        year_match = re.search(r'20\d{2}', combined_text)
        if year_match:
            return year_match.group(0)
        
        # Default to current year
        return str(datetime.now().year)
    
    def _get_cached_document(self, url: str) -> Optional[Dict[str, Any]]:
        """Get document from cache"""
        return self.document_cache.get(url)
    
    def _is_document_updated(self, cached_doc: Dict[str, Any], new_doc: DocumentInfo) -> bool:
        """Check if document has been updated"""
        
        # Compare last modified date
        if new_doc.last_modified and cached_doc.get('last_modified'):
            if new_doc.last_modified != cached_doc['last_modified']:
                return True
        
        # Compare file size
        if new_doc.size and cached_doc.get('size'):
            if new_doc.size != cached_doc['size']:
                return True
        
        # Compare title (might indicate content change)
        if new_doc.title != cached_doc.get('title', ''):
            return True
        
        return False
    
    def _update_document_cache(self, documents: List[DocumentInfo]):
        """Update document cache with new documents"""
        
        for doc in documents:
            self.document_cache[doc.url] = asdict(doc)
        
        self._save_document_cache()
    
    def _load_document_cache(self) -> Dict[str, Any]:
        """Load document cache from file"""
        
        cache_file = self.cache_dir / "naac_documents.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading document cache: {e}")
        
        return {}
    
    def _save_document_cache(self):
        """Save document cache to file"""
        
        cache_file = self.cache_dir / "naac_documents.json"
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(self.document_cache, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving document cache: {e}")
    
    def get_watch_statistics(self) -> Dict[str, Any]:
        """Get statistics about watched documents"""
        
        total_docs = len(self.document_cache)
        
        # Count by criterion
        criterion_counts = {}
        file_type_counts = {}
        
        for doc_data in self.document_cache.values():
            criterion = doc_data.get('criterion', 'unknown')
            criterion_counts[criterion] = criterion_counts.get(criterion, 0) + 1
            
            file_type = doc_data.get('file_type', 'unknown')
            file_type_counts[file_type] = file_type_counts.get(file_type, 0) + 1
        
        return {
            'total_documents_tracked': total_docs,
            'criterion_distribution': criterion_counts,
            'file_type_distribution': file_type_counts,
            'cache_location': str(self.cache_dir),
            'last_cache_update': datetime.now().isoformat()
        }
    
    def clear_cache(self):
        """Clear the document cache"""
        self.document_cache = {}
        self._save_document_cache()
        logger.info("Document cache cleared")