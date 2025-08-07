import os
import uuid
import aiofiles
from datetime import datetime
from typing import Union
from fastapi import UploadFile
import shutil


class FileManager:
    def __init__(self, upload_dir: str):
        self.upload_dir = upload_dir
        self._ensure_upload_dir()
    
    def _ensure_upload_dir(self):
        """Ensure upload directory exists"""
        os.makedirs(self.upload_dir, exist_ok=True)
    
    def _generate_filename(self, original_filename: str, compound_id: str) -> str:
        """Generate a unique filename"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = os.path.splitext(original_filename)[1]
        unique_id = str(uuid.uuid4())[:8]
        
        return f"{compound_id}_{timestamp}_{unique_id}{file_ext}"
    
    async def save_upload(self, file: UploadFile, compound_id: str) -> str:
        """Save uploaded file and return the file path"""
        # Create compound-specific directory
        compound_dir = os.path.join(self.upload_dir, compound_id)
        os.makedirs(compound_dir, exist_ok=True)
        
        # Generate unique filename
        filename = self._generate_filename(file.filename, compound_id)
        file_path = os.path.join(compound_dir, filename)
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        return file_path
    
    def delete_file(self, file_path: str) -> bool:
        """Delete a file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
            return False
    
    def get_file_info(self, file_path: str) -> dict:
        """Get file information"""
        if not os.path.exists(file_path):
            return None
        
        stat = os.stat(file_path)
        return {
            "path": file_path,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime),
            "modified": datetime.fromtimestamp(stat.st_mtime)
        }