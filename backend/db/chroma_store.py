"""
ChromaDB Vector Store Integration for NAAC Compliance Intelligence System
Handles separate collections for NAAC Requirements and MVSR Evidence
"""

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import json
from typing import List, Dict, Any, Optional
import uuid
from pathlib import Path
import logging

# Setup logging
logger = logging.getLogger(__name__)

class ChromaVectorStore:
    """
    Manages two separate ChromaDB collections:
    1. naac_requirements - NAAC guidelines, criteria, indicators
    2. mvsr_evidence - MVSR institutional documents and evidence
    """
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        """Initialize ChromaDB with persistent storage"""
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Initialize sentence transformer embedding function
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        # Get or create collections
        self.naac_collection = self._get_or_create_collection("naac_requirements")
        self.mvsr_collection = self._get_or_create_collection("mvsr_evidence")
        
        logger.info("ChromaDB initialized with collections: naac_requirements, mvsr_evidence")
    
    def _get_or_create_collection(self, name: str):
        """Get existing collection or create new one"""
        try:
            return self.client.get_collection(
                name=name,
                embedding_function=self.embedding_function
            )
        except:
            return self.client.create_collection(
                name=name,
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )
    
    def add_naac_documents(self, documents: List[str], metadatas: List[Dict]):
        """
        Add NAAC requirement documents to the naac_requirements collection
        
        Args:
            documents: List of document chunks
            metadatas: List of metadata dictionaries with NAAC-specific fields:
                - type: "requirement"
                - criterion: "1", "2", etc.
                - indicator: "1.1.1", "2.3.3", etc.
                - version: "2025"
                - status: "active"
                - document_title: SSR Manual, etc.
        """
        if not documents or not metadatas:
            logger.warning("Empty documents or metadata provided for NAAC collection")
            return
            
        # Generate unique IDs
        ids = [f"naac_{uuid.uuid4().hex[:8]}" for _ in documents]
        
        # Validate metadata structure
        for metadata in metadatas:
            if not all(key in metadata for key in ["type", "criterion", "version"]):
                raise ValueError("NAAC metadata missing required fields: type, criterion, version")
            metadata["type"] = "requirement"  # Ensure type is set correctly
        
        try:
            self.naac_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Added {len(documents)} documents to NAAC requirements collection")
        except Exception as e:
            logger.error(f"Error adding NAAC documents: {e}")
            raise
    
    def add_mvsr_documents(self, documents: List[str], metadatas: List[Dict]):
        """
        Add MVSR evidence documents to the mvsr_evidence collection
        
        Args:
            documents: List of document chunks
            metadatas: List of metadata dictionaries with MVSR-specific fields:
                - type: "evidence"
                - criterion: "1", "2", etc. (mapped criterion)
                - document: "Mentoring Policy", etc.
                - year: 2023
                - category: "policies", "iqac", "governance", etc.
        """
        if not documents or not metadatas:
            logger.warning("Empty documents or metadata provided for MVSR collection")
            return
            
        # Generate unique IDs
        ids = [f"mvsr_{uuid.uuid4().hex[:8]}" for _ in documents]
        
        # Validate metadata structure
        for metadata in metadatas:
            if not all(key in metadata for key in ["type", "document", "year"]):
                raise ValueError("MVSR metadata missing required fields: type, document, year")
            metadata["type"] = "evidence"  # Ensure type is set correctly
        
        try:
            self.mvsr_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Added {len(documents)} documents to MVSR evidence collection")
        except Exception as e:
            logger.error(f"Error adding MVSR documents: {e}")
            raise
    
    def query_naac_requirements(self, 
                               query_text: str, 
                               n_results: int = 5,
                               criterion_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Query NAAC requirements collection using semantic similarity
        
        Args:
            query_text: Natural language query
            n_results: Number of results to return
            criterion_filter: Filter by specific criterion (e.g., "2")
            
        Returns:
            Dict containing documents, metadatas, distances
        """
        where_clause = None
        if criterion_filter:
            where_clause = {"criterion": {"$eq": criterion_filter}}
            
        try:
            results = self.naac_collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where_clause
            )
            
            logger.info(f"NAAC query returned {len(results['documents'][0])} results")
            return {
                "documents": results['documents'][0],
                "metadatas": results['metadatas'][0],
                "distances": results['distances'][0]
            }
        except Exception as e:
            logger.error(f"Error querying NAAC requirements: {e}")
            return {"documents": [], "metadatas": [], "distances": []}
    
    def query_mvsr_evidence(self, 
                           query_text: str, 
                           n_results: int = 5,
                           category_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Query MVSR evidence collection using semantic similarity
        
        Args:
            query_text: Natural language query
            n_results: Number of results to return
            category_filter: Filter by category (e.g., "policies", "iqac")
            
        Returns:
            Dict containing documents, metadatas, distances
        """
        where_clause = None
        if category_filter:
            where_clause = {"category": {"$eq": category_filter}}
            
        try:
            results = self.mvsr_collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where_clause
            )
            
            logger.info(f"MVSR query returned {len(results['documents'][0])} results")
            return {
                "documents": results['documents'][0],
                "metadatas": results['metadatas'][0],
                "distances": results['distances'][0]
            }
        except Exception as e:
            logger.error(f"Error querying MVSR evidence: {e}")
            return {"documents": [], "metadatas": [], "distances": []}
    
    def get_collection_stats(self) -> Dict[str, int]:
        """Get statistics about both collections"""
        try:
            naac_count = self.naac_collection.count()
            mvsr_count = self.mvsr_collection.count()
            
            return {
                "naac_requirements_count": naac_count,
                "mvsr_evidence_count": mvsr_count,
                "total_documents": naac_count + mvsr_count
            }
        except Exception as e:
            logger.error(f"Error getting collection stats: {e}")
            return {"naac_requirements_count": 0, "mvsr_evidence_count": 0, "total_documents": 0}
    
    def reset_collections(self):
        """Reset both collections (use with caution)"""
        try:
            self.client.delete_collection("naac_requirements")
            self.client.delete_collection("mvsr_evidence")
            
            # Recreate collections
            self.naac_collection = self._get_or_create_collection("naac_requirements")
            self.mvsr_collection = self._get_or_create_collection("mvsr_evidence")
            
            logger.info("Collections reset successfully")
        except Exception as e:
            logger.error(f"Error resetting collections: {e}")
            raise
    
    def update_naac_version(self, old_version: str, new_version: str):
        """Archive old NAAC version and prepare for new version ingestion"""
        try:
            # Get all documents with old version
            old_docs = self.naac_collection.get(
                where={"version": old_version}
            )
            
            if old_docs and old_docs['ids']:
                # Update metadata to mark as archived
                updated_metadatas = []
                for metadata in old_docs['metadatas']:
                    metadata['status'] = 'archived'
                    metadata['archived_version'] = old_version
                    updated_metadatas.append(metadata)
                
                # Update the documents
                self.naac_collection.update(
                    ids=old_docs['ids'],
                    metadatas=updated_metadatas
                )
                
                logger.info(f"Archived {len(old_docs['ids'])} documents from version {old_version}")
            
        except Exception as e:
            logger.error(f"Error updating NAAC version: {e}")
            raise