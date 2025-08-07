import fitz  # PyMuPDF
from typing import List, Dict, Tuple
import re


class PDFProcessor:
    def __init__(self):
        self.page_limit = 10  # Limit pages to process for performance
    
    async def extract_text(self, pdf_path: str) -> str:
        """Extract text from PDF file"""
        try:
            doc = fitz.open(pdf_path)
            text_content = []
            
            # Process pages up to limit
            for page_num in range(min(len(doc), self.page_limit)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    text_content.append(f"--- Page {page_num + 1} ---\n{text}")
            
            doc.close()
            return "\n\n".join(text_content)
            
        except Exception as e:
            raise Exception(f"Failed to extract text from PDF: {str(e)}")
    
    async def extract_text_with_positions(self, pdf_path: str) -> List[Dict]:
        """Extract text with position information"""
        try:
            doc = fitz.open(pdf_path)
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
            
            doc.close()
            return extracted_data
            
        except Exception as e:
            raise Exception(f"Failed to extract text with positions: {str(e)}")
    
    def find_field_patterns(self, text: str) -> Dict[str, List[str]]:
        """Find common COA field patterns in text"""
        patterns = {
            "lot_number": [
                r"(?i)lot\s*(?:no|number|#)?\.?\s*:?\s*([A-Z0-9\-]+)",
                r"(?i)batch\s*(?:no|number|#)?\.?\s*:?\s*([A-Z0-9\-]+)",
                r"(?i)批号\s*[:：]?\s*([A-Z0-9\-]+)",
                r"(?i)批次\s*[:：]?\s*([A-Z0-9\-]+)"
            ],
            "manufacturer": [
                r"(?i)manufacturer\s*:?\s*([A-Za-z\s\.,\-&]+(?:Ltd|Inc|Corp|Co\.|Company)?)",
                r"(?i)manufactured\s+by\s*:?\s*([A-Za-z\s\.,\-&]+(?:Ltd|Inc|Corp|Co\.|Company)?)",
                r"(?i)supplier\s*:?\s*([A-Za-z\s\.,\-&]+(?:Ltd|Inc|Corp|Co\.|Company)?)",
                r"(?i)supplied\s+by\s*:?\s*([A-Za-z\s\.,\-&]+(?:Ltd|Inc|Corp|Co\.|Company)?)",
                r"(?i)生产商\s*[:：]?\s*([^\n]+)",
                r"(?i)供应商\s*[:：]?\s*([^\n]+)"
            ],
            "storage_condition": [
                r"(?i)storage\s*(?:condition|conditions|temp|temperature)?\s*:?\s*([^\n]+)",
                r"(?i)store\s*(?:at|in)?\s*:?\s*([^\n]+)",
                r"(?i)储存条件\s*[:：]?\s*([^\n]+)",
                r"(?i)贮存条件\s*[:：]?\s*([^\n]+)",
                r"(?i)保存条件\s*[:：]?\s*([^\n]+)"
            ]
        }
        
        results = {}
        for field, pattern_list in patterns.items():
            matches = []
            for pattern in pattern_list:
                found = re.findall(pattern, text)
                matches.extend(found)
            
            # Clean and deduplicate matches
            cleaned_matches = []
            for match in matches:
                cleaned = match.strip()
                if cleaned and cleaned not in cleaned_matches:
                    cleaned_matches.append(cleaned)
            
            results[field] = cleaned_matches
        
        return results
    
    def extract_tables(self, pdf_path: str) -> List[List[List[str]]]:
        """Extract tables from PDF"""
        try:
            doc = fitz.open(pdf_path)
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
            
            doc.close()
            return all_tables
            
        except Exception as e:
            print(f"Failed to extract tables: {str(e)}")
            return []