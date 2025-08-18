# app/services/veeva_service.py
"""
Veeva Vault API Service for fetching PDF documents
"""
import io
import logging
import time
from typing import Optional, Dict, List, Tuple, BinaryIO
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta

from ..config import settings

logger = logging.getLogger(__name__)


class VeevaAPIError(Exception):
    """Custom exception for Veeva API errors"""
    pass


class VeevaService:
    """Service for interacting with Veeva Vault API"""
    
    def __init__(self):
        self.vault_url = settings.VEEVA_VAULT_URL
        self.username = settings.VEEVA_USERNAME
        self.password = settings.VEEVA_PASSWORD
        self.api_version = settings.VEEVA_API_VERSION
        
        # Session management
        self.session = None
        self.session_id = None
        self.session_expires_at = None
        
        # Configure requests session with retry strategy
        self.http_session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.http_session.mount("https://", adapter)
        self.http_session.mount("http://", adapter)
        
        # Set default timeout
        self.timeout = settings.VEEVA_API_TIMEOUT
        
        logger.info(f"VeevaService initialized for {self.vault_url}")
    
    def _is_session_valid(self) -> bool:
        """Check if the current session is still valid"""
        if not self.session_id or not self.session_expires_at:
            return False
        
        # Check if session will expire in next 5 minutes
        buffer_time = timedelta(minutes=5)
        return datetime.utcnow() < (self.session_expires_at - buffer_time)
    
    def authenticate(self) -> str:
        """
        Authenticate with Veeva Vault and get session ID
        Returns: Session ID string
        """
        # Check if we have a valid session
        if self._is_session_valid():
            logger.debug("Using existing valid session")
            return self.session_id
        
        logger.info("Authenticating with Veeva Vault...")
        
        auth_url = f"{self.vault_url}/api/{self.api_version}/auth"
        
        try:
            response = self.http_session.post(
                auth_url,
                data={
                    "username": self.username,
                    "password": self.password
                },
                timeout=self.timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            if data.get("responseStatus") == "SUCCESS":
                self.session_id = data.get("sessionId")
                
                # Calculate session expiration (typically 20 minutes for Veeva)
                self.session_expires_at = datetime.utcnow() + timedelta(minutes=20)
                
                # Update session headers
                self.http_session.headers.update({
                    "Authorization": self.session_id
                })
                
                logger.info("Successfully authenticated with Veeva Vault")
                return self.session_id
            else:
                error_msg = data.get("errors", [{"message": "Unknown error"}])[0].get("message")
                raise VeevaAPIError(f"Authentication failed: {error_msg}")
                
        except requests.RequestException as e:
            logger.error(f"Failed to authenticate with Veeva: {e}")
            raise VeevaAPIError(f"Authentication request failed: {str(e)}")
    
    def search_documents(self, query: str) -> List[Dict]:
        """
        Search for documents in Veeva Vault using VQL
        
        Args:
            query: VQL query string
        
        Returns:
            List of document metadata dictionaries
        """
        # Ensure we're authenticated
        self.authenticate()
        
        search_url = f"{self.vault_url}/api/{self.api_version}/query"
        
        try:
            response = self.http_session.get(
                search_url,
                headers={"Authorization": self.session_id},
                params={"q": query},
                timeout=self.timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            if data.get("responseStatus") == "SUCCESS":
                return data.get("data", [])
            else:
                error_msg = data.get("errors", [{"message": "Unknown error"}])[0].get("message")
                raise VeevaAPIError(f"Search failed: {error_msg}")
                
        except requests.RequestException as e:
            logger.error(f"Failed to search documents: {e}")
            raise VeevaAPIError(f"Search request failed: {str(e)}")

    def get_document_metadata_by_number(self, document_number: str) -> Dict:
        """
        Get document metadata by its document number (e.g., 'VV-QUAL-001851')
        
        Args:
            document_number: External document number
            
        Returns:
            Dictionary containing document metadata, including internal 'id'
        """
        logger.info(f"Searching for document {document_number} via VQL...")
        # Note: The query selects id, major version, minor version, and type.
        query = f"select id, major_version_number__v, minor_version_number__v, type__v from documents where document_number__v = '{document_number}'"
        results = self.search_documents(query)

        if not results:
            raise VeevaAPIError(f"Document Number '{document_number}' not found in Veeva Vault.")
        
        # The VQL query should return at most one result for a unique document number
        return results[0]

    def download_document_as_stream(self, document_number: str) -> Tuple[io.BytesIO, Dict]:
        """
        Download document from Veeva as a byte stream using the document number
        
        Args:
            document_number: Veeva document number (e.g., "VV-QUAL-001851")
        
        Returns:
            Tuple of (BytesIO stream, metadata dict)
        """
        # 1. Get document metadata and the crucial internal 'id' via VQL
        try:
            metadata = self.get_document_metadata_by_number(document_number)
        except VeevaAPIError as e:
            raise e

        internal_doc_id = metadata.get("id")
        if not internal_doc_id:
            raise VeevaAPIError(f"Internal ID not found for document {document_number}.")

        logger.info(f"Downloading document {document_number} (internal ID: {internal_doc_id}) from Veeva...")
        
        # 2. Build download URL using the internal_doc_id
        download_url = f"{self.vault_url}/api/{self.api_version}/objects/documents/{internal_doc_id}/renditions/viewable_rendition__v"
        
        try:
            # Stream download to avoid loading entire file in memory at once
            response = self.http_session.get(
                download_url,
                headers={"Authorization": self.session_id},
                stream=True,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                data = response.json()
                error_msg = data.get("errors", [{"message": "Unknown error"}])[0].get("message")
                raise VeevaAPIError(f"Failed to download document: {error_msg}")
            
            pdf_stream = io.BytesIO()
            chunk_size = 8192
            downloaded_size = 0
            
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    pdf_stream.write(chunk)
                    downloaded_size += len(chunk)
            
            pdf_stream.seek(0)
            
            metadata['downloaded_size'] = downloaded_size
            metadata['download_timestamp'] = datetime.utcnow().isoformat()
            
            logger.info(f"Successfully downloaded document {document_number} ({downloaded_size} bytes)")
            
            return pdf_stream, metadata
            
        except requests.RequestException as e:
            logger.error(f"Failed to download document {document_number}: {e}")
            raise VeevaAPIError(f"Document download failed: {str(e)}")
    
    def batch_download_documents(
        self, 
        document_numbers: List[str], 
        progress_callback: Optional[callable] = None
    ) -> List[Dict]:
        """
        Download multiple documents from Veeva
        
        Args:
            document_numbers: List of Veeva document numbers
            progress_callback: Optional callback function for progress updates
        
        Returns:
            List of dictionaries containing document streams and metadata
        """
        results = []
        total = len(document_numbers)
        
        for idx, doc_number in enumerate(document_numbers, 1):
            try:
                pdf_stream, metadata = self.download_document_as_stream(doc_number)
                
                results.append({
                    "success": True,
                    "document_number": doc_number,
                    "pdf_stream": pdf_stream,
                    "metadata": metadata,
                    "error": None
                })
                
                logger.info(f"Downloaded {idx}/{total}: {doc_number}")
                
            except VeevaAPIError as e:
                logger.error(f"Failed to download {doc_number}: {e}")
                
                results.append({
                    "success": False,
                    "document_number": doc_number,
                    "pdf_stream": None,
                    "metadata": None,
                    "error": str(e)
                })
            
            except Exception as e:
                logger.error(f"Unexpected error downloading {doc_number}: {e}")
                
                results.append({
                    "success": False,
                    "document_number": doc_number,
                    "pdf_stream": None,
                    "metadata": None,
                    "error": f"Unexpected error: {str(e)}"
                })
            
            # Call progress callback if provided
            if progress_callback:
                progress_callback(idx, total, doc_number)
            
            # Small delay between requests to avoid rate limiting
            if idx < total:
                time.sleep(0.5)
        
        return results
    
    def close(self):
        """Close the session and clean up resources"""
        if self.http_session:
            self.http_session.close()
        
        self.session_id = None
        self.session_expires_at = None
        
        logger.info("VeevaService session closed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
    
    def test_connection(self) -> bool:
        """
        Test connection to Veeva Vault
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.authenticate()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False