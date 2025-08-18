# app/services/pdf_processor.py
import fitz  # PyMuPDF
from typing import List, Dict, Tuple, Union, BinaryIO
import re
import io
import logging

logger = logging.getLogger(__name__)


class PDFProcessor:
    def __init__(self):
        self.page_limit = 10  # Limit pages to process for performance
    
    async def extract_text(self, pdf_source: Union[str, io.BytesIO, BinaryIO]) -> str:
        """
        Extract text from PDF file or stream
        
        Args:
            pdf_source: Can be a file path (str) or a byte stream (BytesIO/BinaryIO)
        
        Returns:
            Extracted text content
        """
        doc = None
        try:
            # Open PDF from different sources
            if isinstance(pdf_source, str):
                # File path
                logger.debug(f"Opening PDF from file path: {pdf_source}")
                doc = fitz.open(pdf_source)
            elif isinstance(pdf_source, (io.BytesIO, io.BufferedReader)):
                # Byte stream
                logger.debug("Opening PDF from byte stream")
                # Read all bytes if needed
                if isinstance(pdf_source, io.BytesIO):
                    pdf_bytes = pdf_source.getvalue()
                else:
                    pdf_bytes = pdf_source.read()
                    pdf_source.seek(0)  # Reset position
                
                # Open from bytes
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            else:
                raise ValueError(f"Unsupported PDF source type: {type(pdf_source)}")
            
            text_content = []
            
            # Process pages up to limit
            for page_num in range(min(len(doc), self.page_limit)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    text_content.append(f"--- Page {page_num + 1} ---\n{text}")
            
            return "\n\n".join(text_content)
            
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {str(e)}")
            raise Exception(f"Failed to extract text from PDF: {str(e)}")
        finally:
            # Clean up resources
            if doc:
                doc.close()
    
    async def extract_text_from_stream(self, pdf_stream: io.BytesIO) -> str:
        """
        Extract text specifically from a BytesIO stream
        Convenience method for clarity
        
        Args:
            pdf_stream: BytesIO object containing PDF data
        
        Returns:
            Extracted text content
        """
        return await self.extract_text(pdf_stream)
    
    async def extract_text_with_positions(self, pdf_source: Union[str, io.BytesIO]) -> List[Dict]:
        """
        Extract text with position information from PDF file or stream
        
        Args:
            pdf_source: Can be a file path (str) or a byte stream (BytesIO)
        
        Returns:
            List of text blocks with position information
        """
        doc = None
        try:
            # Open PDF from different sources
            if isinstance(pdf_source, str):
                doc = fitz.open(pdf_source)
            elif isinstance(pdf_source, io.BytesIO):
                pdf_bytes = pdf_source.getvalue()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            else:
                raise ValueError(f"Unsupported PDF source type: {type(pdf_source)}")
            
            extracted_data = []
            
            for page_num in range(min(len(doc), self.page_limit)):
                page = doc[page_num]
                blocks = page.get_text("dict")
                
                for block in blocks.get("blocks", []):
                    if block.get("type") == 0:  # Text block
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                extracted_data.append({
                                    "text": span.get("text", ""),
                                    "page": page_num + 1,
                                    "bbox": span.get("bbox"),
                                    "font": span.get("font"),
                                    "size": span.get("size")
                                })
            
            return extracted_data
            
        except Exception as e:
            logger.error(f"Failed to extract text with positions: {str(e)}")
            raise Exception(f"Failed to extract text with positions: {str(e)}")
        finally:
            if doc:
                doc.close()
    
    def extract_tables(self, pdf_source: Union[str, io.BytesIO]) -> List[List[List[str]]]:
        """
        Extract tables from PDF file or stream
        
        Args:
            pdf_source: Can be a file path (str) or a byte stream (BytesIO)
        
        Returns:
            List of tables (each table is a list of rows)
        """
        doc = None
        try:
            # Open PDF from different sources
            if isinstance(pdf_source, str):
                doc = fitz.open(pdf_source)
            elif isinstance(pdf_source, io.BytesIO):
                pdf_bytes = pdf_source.getvalue()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            else:
                raise ValueError(f"Unsupported PDF source type: {type(pdf_source)}")
            
            all_tables = []
            
            for page_num in range(min(len(doc), self.page_limit)):
                page = doc[page_num]
                tables = page.find_tables()
                
                for table in tables:
                    extracted_table = []
                    for row in table.extract():
                        extracted_table.append([cell if cell else "" for cell in row])
                    
                    if extracted_table:
                        all_tables.append(extracted_table)
            
            return all_tables
            
        except Exception as e:
            logger.error(f"Failed to extract tables: {str(e)}")
            return []
        finally:
            if doc:
                doc.close()
    
    async def validate_pdf_stream(self, pdf_stream: io.BytesIO) -> bool:
        """
        Validate if the stream contains a valid PDF
        
        Args:
            pdf_stream: BytesIO object containing potential PDF data
        
        Returns:
            True if valid PDF, False otherwise
        """
        try:
            # Check PDF header
            pdf_stream.seek(0)
            header = pdf_stream.read(5)
            pdf_stream.seek(0)
            
            if header != b'%PDF-':
                logger.warning("Invalid PDF header")
                return False
            
            # Try to open with PyMuPDF
            pdf_bytes = pdf_stream.getvalue()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = len(doc)
            doc.close()
            
            logger.debug(f"Valid PDF with {page_count} pages")
            return True
            
        except Exception as e:
            logger.error(f"PDF validation failed: {e}")
            return False
    
    def get_pdf_metadata(self, pdf_source: Union[str, io.BytesIO]) -> Dict:
        """
        Extract metadata from PDF file or stream
        
        Args:
            pdf_source: Can be a file path (str) or a byte stream (BytesIO)
        
        Returns:
            Dictionary containing PDF metadata
        """
        doc = None
        try:
            # Open PDF from different sources
            if isinstance(pdf_source, str):
                doc = fitz.open(pdf_source)
            elif isinstance(pdf_source, io.BytesIO):
                pdf_bytes = pdf_source.getvalue()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            else:
                raise ValueError(f"Unsupported PDF source type: {type(pdf_source)}")
            
            metadata = doc.metadata
            metadata['page_count'] = len(doc)
            
            # Add file size if it's a stream
            if isinstance(pdf_source, io.BytesIO):
                metadata['file_size'] = len(pdf_source.getvalue())
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to extract metadata: {str(e)}")
            return {}
        finally:
            if doc:
                doc.close()