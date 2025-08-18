# app/api/v1/documents.py - Enhanced with Veeva Integration
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from uuid import UUID
from sqlalchemy import text
import os
import glob
import aiofiles
from datetime import datetime
import hashlib
import json
import requests
from pathlib import Path
import io
import gc  # For garbage collection
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

from ...database import get_db
from ...config import settings
from ...models.document import COADocument, ProcessingStatus
from ...models.extracted_data import ExtractedData
from ...schemas.document import (
    DirectoryProcessRequest,
    VeevaProcessRequest  # New schema for Veeva processing
)
from ...schemas.extracted_data import ProcessingResultResponse, ApiResponse
from ...services.file_manager import FileManager
from ...services.pdf_processor import PDFProcessor
from ...services.ai_extractor import AIExtractor
from ...services.veeva_service import VeevaService, VeevaAPIError  # New Veeva service

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize services
file_manager = FileManager(settings.UPLOAD_DIR)
pdf_processor = PDFProcessor()
ai_extractor = AIExtractor()

# ============ 缓存相关函数 ============

class BatchDataCache:
    """批次数据缓存管理器"""
    def __init__(self, db: Session):
        self.db = db
        self._create_table_if_not_exists()
    
    def _create_table_if_not_exists(self):
        """创建缓存表（如果不存在）"""
        try:
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS coa_processor.batch_data_cache (
                    id SERIAL PRIMARY KEY,
                    compound_id VARCHAR(255) NOT NULL,
                    template_id VARCHAR(255) NOT NULL,
                    batch_data JSONB NOT NULL,
                    file_hashes TEXT[],
                    total_files INTEGER NOT NULL DEFAULT 0,
                    processed_files TEXT[],
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(compound_id, template_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_batch_cache_compound_template 
                ON coa_processor.batch_data_cache(compound_id, template_id);
            """))
            self.db.commit()
        except Exception as e:
            print(f"缓存表创建警告: {e}")
            self.db.rollback()

def get_cache_record(db: Session, compound_id: str, template_id: str) -> Optional[Dict]:
    """获取缓存记录"""
    try:
        result = db.execute(
            text("""
            SELECT batch_data, updated_at, total_files, processed_files, file_hashes
            FROM coa_processor.batch_data_cache 
            WHERE compound_id = :compound_id AND template_id = :template_id
            """),
            {"compound_id": compound_id, "template_id": template_id}
        ).fetchone()
        
        if result:
            return {
                "batchData": result[0],  # JSONB data
                "lastUpdated": result[1].isoformat(),
                "totalFiles": result[2],
                "processedFiles": result[3] or [],
                "fileHashes": result[4] or []
            }
    except Exception as e:
        print(f"获取缓存记录失败: {e}")
    return None

def update_cache_record(db: Session, compound_id: str, template_id: str, 
                       batch_data: List[Dict], file_hashes: List[str], 
                       processed_files: List[str]):
    """更新或创建缓存记录"""
    try:
        current_time = datetime.utcnow()
        
        # 先尝试更新
        result = db.execute(
            text("""
            UPDATE coa_processor.batch_data_cache 
            SET batch_data = :batch_data, file_hashes = :file_hashes, 
                total_files = :total_files, processed_files = :processed_files, 
                updated_at = :updated_at
            WHERE compound_id = :compound_id AND template_id = :template_id
            """),
            {
                "batch_data": json.dumps(batch_data),
                "file_hashes": file_hashes,
                "total_files": len(batch_data),
                "processed_files": processed_files,
                "updated_at": current_time,
                "compound_id": compound_id,
                "template_id": template_id
            }
        )
        
        # 如果没有更新任何行，则插入新记录
        if result.rowcount == 0:
            db.execute(
                text("""
                INSERT INTO coa_processor.batch_data_cache 
                (compound_id, template_id, batch_data, file_hashes, total_files, 
                 processed_files, created_at, updated_at)
                VALUES (:compound_id, :template_id, :batch_data, :file_hashes, 
                        :total_files, :processed_files, :created_at, :updated_at)
                """),
                {
                    "compound_id": compound_id,
                    "template_id": template_id,
                    "batch_data": json.dumps(batch_data),
                    "file_hashes": file_hashes,
                    "total_files": len(batch_data),
                    "processed_files": processed_files,
                    "created_at": current_time,
                    "updated_at": current_time
                }
            )
        
        db.commit()
        return True
    except Exception as e:
        print(f"缓存更新失败: {e}")
        db.rollback()
        return False

def delete_cache_record(db: Session, compound_id: str, template_id: str) -> int:
    """删除缓存记录"""
    try:
        result = db.execute(
            text("""
            DELETE FROM coa_processor.batch_data_cache 
            WHERE compound_id = :compound_id AND template_id = :template_id
            """),
            {"compound_id": compound_id, "template_id": template_id}
        )
        db.commit()
        return result.rowcount
    except Exception as e:
        print(f"缓存删除失败: {e}")
        db.rollback()
        return 0


def calculate_file_hashes(pdf_directory: str) -> List[str]:
    """计算目录中PDF文件的哈希值"""
    hashes = []
    try:
        pdf_files = glob.glob(os.path.join(pdf_directory, "*.pdf"))
        for pdf_file in pdf_files:
            filename = os.path.basename(pdf_file)
            # 使用文件修改时间和大小的组合作为简单哈希
            stat = os.stat(pdf_file)
            file_hash = f"{filename}:{stat.st_size}:{int(stat.st_mtime)}"
            hashes.append(file_hash)
    except Exception as e:
        print(f"计算文件哈希失败: {e}")
    return sorted(hashes)  # 排序以保证一致性





# ============ NEW: Veeva Integration Functions ============

async def process_veeva_document_stream(
    pdf_stream: io.BytesIO,
    document_id: str,
    metadata: Dict,
    compound_id: UUID,
    db: Session
) -> Dict:
    """
    Process a single PDF document from Veeva stream
    
    Args:
        pdf_stream: BytesIO containing PDF data
        document_id: Veeva document ID
        metadata: Document metadata from Veeva
        compound_id: Compound ID for database
        db: Database session
    
    Returns:
        Dictionary with processing results
    """
    document = None
    
    try:
        # Create filename from metadata
        doc_name = metadata.get('name__v', document_id)
        doc_version = f"{metadata.get('major_version_number__v', 1)}.{metadata.get('minor_version_number__v', 0)}"
        filename = f"{doc_name}_v{doc_version}.pdf"
        
        logger.info(f"📄 Processing Veeva document: {filename} (ID: {document_id})")
        
        # Check if document already exists
        existing_doc = db.query(COADocument).filter(
            COADocument.filename == filename,
            COADocument.compound_id == compound_id
        ).first()
        
        if existing_doc:
            logger.warning(f"⚠️ Document already exists: {filename}, skipping...")
            return {
                "status": "skipped",
                "filename": filename,
                "document_id": document_id,
                "message": "Document already processed"
            }
        
        # Create database record
        document = COADocument(
            compound_id=compound_id,
            filename=filename,
            file_path=f"veeva://{document_id}",  # Virtual path for Veeva documents
            file_size=f"{metadata.get('downloaded_size', 0) / 1024:.2f} KB",
            processing_status=ProcessingStatus.PROCESSING.value
        )
        
        db.add(document)
        db.flush()  # Get ID but don't commit yet
        
        # Extract PDF text from stream
        logger.info("📖 Extracting text from PDF stream...")
        pdf_text = await pdf_processor.extract_text_from_stream(pdf_stream)
        
        if not pdf_text.strip():
            raise Exception("No text content found in PDF")
        
        logger.info(f"✅ Extracted {len(pdf_text)} characters of text")
        
        # Use AI to extract batch data
        logger.info("🔍 Extracting COA batch analysis data...")
        batch_data = await ai_extractor.extract_coa_batch_data(pdf_text, filename)
        
        # Validate and clean data
        batch_data = ai_extractor.validate_batch_data(batch_data)
        
        # Update document status
        document.processing_status = ProcessingStatus.COMPLETED.value
        document.processed_at = datetime.utcnow()
        
        # Save extracted batch data
        batch_number = batch_data.get('batch_number', '')
        manufacture_date = batch_data.get('manufacture_date', '')
        manufacturer = batch_data.get('manufacturer', '')
        
        # Save basic batch information
        basic_fields = [
            ('batch_number', batch_number),
            ('manufacture_date', manufacture_date),
            ('manufacturer', manufacturer)
        ]
        
        for field_name, field_value in basic_fields:
            if field_value:
                data = ExtractedData(
                    document_id=document.id,
                    field_name=field_name,
                    field_value=field_value,
                    confidence_score=0.95,
                    original_text=field_value
                )
                db.add(data)
        
        # Save test results data
        test_results = batch_data.get('test_results', {})
        for test_param, result_value in test_results.items():
            if result_value and result_value not in ['TBD', '']:
                data = ExtractedData(
                    document_id=document.id,
                    field_name=test_param,
                    field_value=result_value,
                    confidence_score=0.90,
                    original_text=result_value
                )
                db.add(data)
        
        # Commit transaction
        db.commit()
        
        # Add Veeva-specific metadata to batch data
        batch_data['veeva_document_id'] = document_id
        batch_data['veeva_version'] = doc_version
        
        logger.info(f"✅ Successfully processed Veeva document: {filename}")
        
        return {
            "status": "success",
            "filename": filename,
            "document_id": document_id,
            "batch_data": batch_data
        }
        
    except Exception as e:
        # Rollback transaction
        db.rollback()
        
        error_msg = str(e)
        logger.error(f"❌ Error processing Veeva document {document_id}: {error_msg}")
        
        # Update document status if it was created
        if document and document.id:
            try:
                fail_doc = db.query(COADocument).filter(
                    COADocument.id == document.id
                ).first()
                if fail_doc:
                    fail_doc.processing_status = ProcessingStatus.FAILED.value
                    fail_doc.error_message = error_msg[:500]
                    db.commit()
            except Exception as update_error:
                logger.error(f"Failed to update document status: {update_error}")
                db.rollback()
        
        return {
            "status": "failed",
            "filename": filename if 'filename' in locals() else document_id,
            "document_id": document_id,
            "error": error_msg
        }
    finally:
        # Clean up memory
        if pdf_stream:
            pdf_stream.close()
            del pdf_stream
        gc.collect()

# ============ NEW: Veeva Processing Endpoint ============

@router.post("/process-from-veeva", response_model=ApiResponse)
async def process_from_veeva(
    request: VeevaProcessRequest,
    db: Session = Depends(get_db)
):
    """
    Process COA documents directly from Veeva Vault
    
    This endpoint:
    1. Receives a list of Veeva document IDs
    2. Downloads each document as a stream from Veeva
    3. Processes them in memory without saving to disk
    4. Extracts batch analysis data
    5. Stores results in database
    """
    
    if not settings.VEEVA_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Veeva integration is not enabled"
        )
    
    try:
        print(f"\n{'='*80}")
        print(f"🚀 VEEVA COA BATCH ANALYSIS PROCESSING STARTED")
        print(f"{'='*80}")
        print(f"📋 Document IDs: {request.document_ids}")
        print(f"🧬 Compound ID: {request.compound_id}")
        print(f"📋 Template ID: {request.template_id}")
        print(f"🔄 Force reprocess: {request.force_reprocess}")
        
        # Initialize cache manager
        cache_manager = BatchDataCache(db)
        
        # Check cache if not forcing reprocess
        if not request.force_reprocess and settings.ENABLE_CACHE:
            # Create a hash of document IDs for cache key
            doc_ids_hash = hashlib.md5(
                ",".join(sorted(request.document_ids)).encode()
            ).hexdigest()
            
            cache_data = get_cache_record(db, request.compound_id, request.template_id)
            
            if cache_data:
                # Check if same documents
                cached_hashes = cache_data.get("fileHashes", [])
                if doc_ids_hash in cached_hashes:
                    print(f"✅ Cache hit! Returning cached data")
                    return ApiResponse(
                        success=True,
                        data={
                            "processedFiles": cache_data.get("processedFiles", []),
                            "failedFiles": [],
                            "totalFiles": cache_data.get("totalFiles", 0),
                            "batchData": cache_data["batchData"],
                            "status": "success",
                            "fromCache": True,
                            "source": "veeva",
                            "message": f"Loaded from cache (last updated: {cache_data['lastUpdated']})"
                        }
                    )
        
        # Initialize Veeva service
        veeva_service = VeevaService()
        
        # Test connection
        if not veeva_service.test_connection():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to connect to Veeva Vault"
            )
        
        print(f"✅ Connected to Veeva Vault successfully")
        
        batch_data_list = []
        processed_files = []
        failed_files = []
        
        # Process documents concurrently
        tasks = []
        
        for doc_id in request.document_ids:
            try:
                print(f"\n📥 Downloading from Veeva: {doc_id}")
                
                # Download document from Veeva
                pdf_stream, metadata = veeva_service.download_document_as_stream(doc_id)
                
                # Process the document stream
                result = await process_veeva_document_stream(
                    pdf_stream=pdf_stream,
                    document_id=doc_id,
                    metadata=metadata,
                    compound_id=UUID(request.compound_id),
                    db=db
                )
                
                if result["status"] == "success":
                    batch_data_list.append(result["batch_data"])
                    processed_files.append(result["filename"])
                elif result["status"] == "skipped":
                    print(f"⏭️ Skipped: {result['message']}")
                else:
                    failed_files.append({
                        "document_id": doc_id,
                        "filename": result.get("filename", doc_id),
                        "error": result.get("error", "Unknown error")
                    })
                    
            except VeevaAPIError as e:
                logger.error(f"❌ Veeva API error for {doc_id}: {e}")
                failed_files.append({
                    "document_id": doc_id,
                    "filename": doc_id,
                    "error": str(e)
                })
            except Exception as e:
                logger.error(f"❌ Unexpected error for {doc_id}: {e}")
                failed_files.append({
                    "document_id": doc_id,
                    "filename": doc_id,
                    "error": str(e)
                })
        
        # Close Veeva service
        veeva_service.close()
        
        # Update cache if processing was successful
        if batch_data_list and settings.ENABLE_CACHE:
            try:
                doc_ids_hash = hashlib.md5(
                    ",".join(sorted(request.document_ids)).encode()
                ).hexdigest()
                
                update_cache_record(
                    db, request.compound_id, request.template_id,
                    batch_data_list, [doc_ids_hash], processed_files
                )
                print(f"✅ Cache updated successfully")
            except Exception as e:
                print(f"⚠️ Cache update failed: {e}")
        
        # Summary
        print(f"\n{'='*80}")
        print(f"📈 VEEVA PROCESSING SUMMARY")
        print(f"{'='*80}")
        print(f"📄 Total documents requested: {len(request.document_ids)}")
        print(f"✅ Successfully processed: {len(processed_files)}")
        print(f"❌ Failed: {len(failed_files)}")
        print(f"📊 Total batches analyzed: {len(batch_data_list)}")
        
        if failed_files:
            print(f"\n❌ Failed documents:")
            for failed in failed_files:
                print(f"   • {failed['document_id']}: {failed['error']}")
        
        return ApiResponse(
            success=True,
            data={
                "processedFiles": processed_files,
                "failedFiles": failed_files,
                "totalFiles": len(request.document_ids),
                "batchData": batch_data_list,
                "status": "success" if processed_files else "failed",
                "fromCache": False,
                "source": "veeva",
                "message": f"Processed {len(batch_data_list)} batches from Veeva"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Veeva processing failed: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

# ============ Hybrid Processing Endpoint ============

@router.post("/process-hybrid", response_model=ApiResponse)
async def process_hybrid(
    request: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Hybrid processing endpoint that can handle both local files and Veeva documents
    
    Request format:
    {
        "compound_id": "uuid",
        "template_id": "uuid",
        "source": "local" | "veeva" | "auto",
        "document_ids": ["VV-QDOC-xxx", ...],  // For Veeva
        "directory_path": "/path/to/pdfs",     // For local
        "force_reprocess": false
    }
    """
    
    source = request.get("source", "auto")
    
    if source == "veeva" or (source == "auto" and request.get("document_ids")):
        # Process from Veeva
        veeva_request = VeevaProcessRequest(
            compound_id=request["compound_id"],
            template_id=request["template_id"],
            document_ids=request["document_ids"],
            force_reprocess=request.get("force_reprocess", False)
        )
        return await process_from_veeva(veeva_request, db)
        
    elif source == "local" or (source == "auto" and request.get("directory_path")):
        # Process from local directory
        dir_request = DirectoryProcessRequest(
            compound_id=request["compound_id"],
            template_id=request["template_id"],
            directory_path=request.get("directory_path"),
            force_reprocess=request.get("force_reprocess", False)
        )
        return await process_directory(dir_request, db)
        
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request: must specify either document_ids for Veeva or directory_path for local processing"
        )


# ============ 新增缓存API端点 ============

@router.get("/check-cache", response_model=ApiResponse)
async def check_cache(
    compound_id: str = Query(...),
    template_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """检查数据库中是否已有批次数据缓存"""
    try:
        # 初始化缓存管理器
        cache_manager = BatchDataCache(db)
        
        # 获取缓存记录
        cache_data = get_cache_record(db, compound_id, template_id)
        
        if cache_data:
            # 检查文件是否有变更
            pdf_directory = getattr(settings, 'PDF_DIRECTORY', settings.UPLOAD_DIR)
            current_hashes = calculate_file_hashes(pdf_directory)
            cached_hashes = cache_data.get("fileHashes", [])
            
            files_changed = set(current_hashes) != set(cached_hashes)
            
            if files_changed:
                return ApiResponse(
                    success=True,
                    data=None,
                    message="Files have changed since last cache, need reprocessing"
                )
            
            return ApiResponse(
                success=True,
                data=cache_data
            )
        else:
            return ApiResponse(
                success=True,
                data=None,
                message="No cache found"
            )
            
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"Failed to check cache: {str(e)}"
        )

@router.delete("/clear-cache", response_model=ApiResponse)
async def clear_cache(
    compound_id: str = Query(...),
    template_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """清除指定化合物和模板的缓存数据"""
    try:
        # 初始化缓存管理器
        cache_manager = BatchDataCache(db)
        
        # 删除缓存记录
        deleted_count = delete_cache_record(db, compound_id, template_id)
        
        return ApiResponse(
            success=True,
            data={"deleted_count": deleted_count},
            message=f"Cleared {deleted_count} cache records"
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"Failed to clear cache: {str(e)}"
        )

@router.get("/cache-status", response_model=ApiResponse)
async def get_cache_status(
    db: Session = Depends(get_db)
):
    """获取缓存状态统计"""
    try:
        # 初始化缓存管理器
        cache_manager = BatchDataCache(db)
        
        # 获取缓存统计
        try:
            result = db.execute(text("""
                SELECT 
                    COUNT(*) as total_records,
                    MAX(updated_at) as last_updated,
                    SUM(total_files) as total_files
                FROM coa_processor.batch_data_cache
            """)).fetchone()
            
            cache_records = db.execute(text("""
                SELECT compound_id, template_id, total_files, updated_at
                FROM coa_processor.batch_data_cache
                ORDER BY updated_at DESC
                LIMIT 10
            """)).fetchall()
            
            return ApiResponse(
                success=True,
                data={
                    "total_records": result[0] if result else 0,
                    "last_updated": result[1].isoformat() if result and result[1] else None,
                    "total_cached_files": result[2] if result else 0,
                    "recent_records": [
                        {
                            "compound_id": record[0],
                            "template_id": record[1],
                            "total_files": record[2],
                            "updated_at": record[3].isoformat()
                        } for record in cache_records
                    ]
                }
            )
        except Exception as sql_error:
            print(f"SQL查询错误: {sql_error}")
            # 如果表不存在，返回空状态
            return ApiResponse(
                success=True,
                data={
                    "total_records": 0,
                    "last_updated": None,
                    "total_cached_files": 0,
                    "recent_records": []
                }
            )
        
    except Exception as e:
        print(f"获取缓存状态失败: {e}")
        return ApiResponse(
            success=False,
            error=f"Failed to get cache status: {str(e)}"
        )
    
@router.get("/debug-directory", response_model=ApiResponse)
async def debug_directory_info(
    compound_id: str = Query(...),
    template_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """调试端点：检查PDF目录和文件状态"""
    try:
        debug_info = {}
        
        # 1. 检查PDF目录配置
        pdf_directory = getattr(settings, 'PDF_DIRECTORY', settings.UPLOAD_DIR)
        debug_info['pdf_directory'] = pdf_directory
        debug_info['directory_exists'] = os.path.exists(pdf_directory)
        
        # 2. 检查目录内容
        if os.path.exists(pdf_directory):
            all_files = os.listdir(pdf_directory)
            pdf_files = glob.glob(os.path.join(pdf_directory, "*.pdf"))
            debug_info['all_files'] = all_files
            debug_info['pdf_files'] = [os.path.basename(f) for f in pdf_files]
            debug_info['pdf_count'] = len(pdf_files)
            
            # 3. 检查PDF文件详情
            pdf_details = []
            for pdf_file in pdf_files[:3]:  # 只检查前3个文件
                try:
                    stat = os.stat(pdf_file)
                    # 尝试提取文本
                    text_sample = await pdf_processor.extract_text(pdf_file)
                    
                    pdf_details.append({
                        'filename': os.path.basename(pdf_file),
                        'size_kb': round(stat.st_size / 1024, 2),
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'text_length': len(text_sample),
                        'text_preview': text_sample[:200] + "..." if len(text_sample) > 200 else text_sample,
                        'can_extract_text': len(text_sample.strip()) > 0
                    })
                except Exception as e:
                    pdf_details.append({
                        'filename': os.path.basename(pdf_file),
                        'error': str(e)
                    })
            
            debug_info['pdf_details'] = pdf_details
        else:
            debug_info['all_files'] = []
            debug_info['pdf_files'] = []
            debug_info['pdf_count'] = 0
            debug_info['pdf_details'] = []
        
        # 4. 检查AI服务配置
        ai_config = {
            'use_azure_openai': getattr(settings, 'USE_AZURE_OPENAI', False),
            'azure_deployment': getattr(settings, 'AZURE_OPENAI_DEPLOYMENT_NAME', None),
            'has_openai_key': bool(getattr(settings, 'OPENAI_API_KEY', None)),
            'test_parameters_count': len(ai_extractor.get_test_parameters())
        }
        debug_info['ai_config'] = ai_config
        
        # 5. 检查缓存状态
        cache_data = get_cache_record(db, compound_id, template_id)
        debug_info['cache_exists'] = cache_data is not None
        if cache_data:
            debug_info['cache_info'] = {
                'batch_count': len(cache_data.get('batchData', [])),
                'last_updated': cache_data.get('lastUpdated'),
                'file_hashes_count': len(cache_data.get('fileHashes', []))
            }
        
        return ApiResponse(
            success=True,
            data=debug_info
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"Debug failed: {str(e)}"
        )

# ============ 增强的主要处理端点 ============

async def download_pdfs_if_needed():
    """
    如果 uploads/pdfs 目录为空，从前端下载 PDF 文件
    这是一个一次性的解决方案
    """
    pdf_directory = getattr(settings, 'PDF_DIRECTORY', settings.UPLOAD_DIR + '/pdfs')
    
    # 检查目录是否存在且为空
    if not os.path.exists(pdf_directory):
        os.makedirs(pdf_directory, exist_ok=True)
    
    existing_pdfs = glob.glob(os.path.join(pdf_directory, "*.pdf"))
    
    # 如果已有 PDF 文件，跳过下载
    if existing_pdfs:
        print(f"📄 目录中已有 {len(existing_pdfs)} 个 PDF 文件，跳过下载")
        return
    
    print("📥 检测到 PDF 目录为空，开始从前端下载文件...")
    
    # 前端 PDF 文件的 URL 列表（需要根据你的实际前端地址修改）
    frontend_base_url = "https://beone-d.beigenecorp.net/aimta/assets/pdfs"  # 修改为你的前端地址
    
    pdf_files = [
        "BGNE_GQA_BGB-16673_DS_CR-C200727003-FPF24001_COA-US.pdf",
        "BGNE_GQA_BGB-16673_DS_CR-C200727003-FPF24002_COA-US.pdf", 
        "BGNE_GQA_BGB-16673_DS_CR-C200727003-FPF24003_COA-US.pdf",
        "BGNE_GQA_BGB-16673_DS_CR-C200727003-FPF24004_COA-US.pdf",
        "BGNE_ESQ_BGB-16673_DS_CM-C200727003-FPF25101_COA-US.pdf"
    ]
    
    downloaded_count = 0
    
    for pdf_filename in pdf_files:
        try:
            pdf_url = f"{frontend_base_url}/{pdf_filename}"
            local_path = os.path.join(pdf_directory, pdf_filename)
            
            print(f"📥 下载: {pdf_filename}")
            
            response = requests.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            # 验证是否是有效的 PDF 文件
            if not response.content.startswith(b'%PDF'):
                print(f"⚠️  {pdf_filename} 不是有效的 PDF 文件，跳过")
                continue
            
            # 保存文件
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            file_size = len(response.content)
            print(f"✅ {pdf_filename} 下载成功 ({file_size} bytes)")
            downloaded_count += 1
            
        except requests.RequestException as e:
            print(f"❌ 下载 {pdf_filename} 失败: {e}")
        except Exception as e:
            print(f"❌ 保存 {pdf_filename} 失败: {e}")
    
    print(f"📊 下载完成: {downloaded_count}/{len(pdf_files)} 个文件")

@router.post("/process-directory", response_model=ApiResponse)
async def process_directory(
    request: DirectoryProcessRequest,  # 所有参数都通过 JSON body 传递
    db: Session = Depends(get_db)
):
    """Process all PDF files in the specified directory and extract batch analysis data"""
    try:
        await download_pdfs_if_needed()
        # 从 request 对象获取参数
        force_reprocess = getattr(request, 'force_reprocess', False)
        
        print(f"收到请求:")
        print(f"  - compound_id: {request.compound_id}")
        print(f"  - template_id: {request.template_id}")
        print(f"  - force_reprocess: {force_reprocess}")
        
        # 初始化缓存管理器
        cache_manager = BatchDataCache(db)
        
        # 使用配置中的PDF目录
        pdf_directory = getattr(settings, 'PDF_DIRECTORY', settings.UPLOAD_DIR)
        os.makedirs(pdf_directory, exist_ok=True)

        # 如果目录为空，提供上传提示
        if not os.path.exists(pdf_directory):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"PDF directory not found: {pdf_directory}. Please upload PDF files to this directory."
            )
        
        pdf_files = glob.glob(os.path.join(pdf_directory, "*.pdf"))
        
        if not pdf_files:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,  
                detail=f"No PDF files found in directory: {pdf_directory}. Please upload PDF files first."
            )
        
        # 如果不是强制重新处理，检查缓存
        if not force_reprocess:
            print(f"\n🔍 Checking cache for compound: {request.compound_id}, template: {request.template_id}")
            cache_data = get_cache_record(db, request.compound_id, request.template_id)
            
            if cache_data:
                # 检查文件是否有变更
                current_hashes = calculate_file_hashes(pdf_directory)
                cached_hashes = cache_data.get("fileHashes", [])
                
                if set(current_hashes) == set(cached_hashes):
                    # 文件没有变更，返回缓存数据
                    print(f"✅ Cache hit! Loading {len(cache_data['batchData'])} batches from cache")
                    print(f"📅 Cache last updated: {cache_data['lastUpdated']}")
                    
                    return ApiResponse(
                        success=True,
                        data={
                            "processedFiles": cache_data.get("processedFiles", []),
                            "failedFiles": [],
                            "totalFiles": cache_data.get("totalFiles", 0),
                            "batchData": cache_data["batchData"],
                            "status": "success",
                            "fromCache": True,
                            "message": f"Loaded {len(cache_data['batchData'])} batches from cache (last updated: {cache_data['lastUpdated']})"
                        }
                    )
                else:
                    print(f"📝 Files have changed since last cache, proceeding with processing...")
            else:
                print(f"❌ No cache found, proceeding with processing...")
        else:
            print(f"🔄 Force reprocess requested, skipping cache check...")
        
        # 执行原有的批量PDF处理逻辑
        print(f"\n{'='*80}")
        print(f"🚀 COA BATCH ANALYSIS PROCESSING STARTED")
        print(f"{'='*80}")
        print(f"📁 Directory: {pdf_directory}")
        print(f"📄 Found {len(pdf_files)} PDF files")
        print(f"🧬 Compound ID: {request.compound_id}")
        print(f"📋 Template ID: {request.template_id}")
        
        # 显示AI服务状态
        if hasattr(settings, 'USE_AZURE_OPENAI') and settings.USE_AZURE_OPENAI:
            print(f"🔵 AI Service: Azure OpenAI ({getattr(settings, 'AZURE_OPENAI_DEPLOYMENT_NAME', 'Unknown')})")
        elif hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY:
            print(f"🟢 AI Service: Standard OpenAI")
        else:
            print(f"⚠️  AI Service: Not available")
        
        print(f"🧪 Test Parameters: {len(ai_extractor.get_test_parameters())} items")
        print(f"{'='*80}")
        
        batch_data_list = []
        processed_files = []
        failed_files = []
        
        for i, pdf_file in enumerate(pdf_files, 1):
            # 为每个文件创建独立的事务
            document = None
            
            # 使用子事务或新会话
            try:
                # 开始新事务
                with db.begin_nested():  # 使用嵌套事务
                    filename = os.path.basename(pdf_file)
                    print(f"\n📄 Processing file {i}/{len(pdf_files)}: {filename}")
                    print("-" * 80)
                    
                    # 检查文件是否已存在
                    existing_doc = db.query(COADocument).filter(
                        COADocument.filename == filename,
                        COADocument.compound_id == UUID(request.compound_id)
                    ).first()
                    
                    if existing_doc:
                        print(f"⚠️  Document already exists: {filename}, skipping...")
                        continue
                    
                    # 创建数据库记录 - 修复：使用 ProcessingStatus.PROCESSING.value
                    document = COADocument(
                        compound_id=UUID(request.compound_id),
                        filename=filename,
                        file_path=pdf_file,
                        file_size=f"{os.path.getsize(pdf_file) / 1024:.2f} KB",
                        processing_status=ProcessingStatus.PROCESSING.value  # 修复：使用枚举值而不是硬编码字符串
                    )
                    
                    db.add(document)
                    db.flush()  # 获取ID但不提交
                    
                    # 提取PDF文本
                    print("📖 Extracting text from PDF...")
                    pdf_text = await pdf_processor.extract_text(pdf_file)
                    
                    if not pdf_text.strip():
                        raise Exception("No text content found in PDF")
                    
                    print(f"✅ Extracted {len(pdf_text)} characters of text")
                    
                    # 使用AI提取批次数据
                    print("🔍 Extracting COA batch analysis data...")
                    batch_data = await ai_extractor.extract_coa_batch_data(pdf_text, filename)
                    
                    # 验证和清理数据
                    batch_data = ai_extractor.validate_batch_data(batch_data)
                    
                    # 更新文档状态 - 修复：使用 ProcessingStatus.COMPLETED.value
                    document.processing_status = ProcessingStatus.COMPLETED.value  # 修复：使用枚举值
                    document.processed_at = datetime.utcnow()
                    
                    # 保存提取的批次数据
                    batch_number = batch_data.get('batch_number', '')
                    manufacture_date = batch_data.get('manufacture_date', '')
                    manufacturer = batch_data.get('manufacturer', '')
                    
                    # 保存基本批次信息
                    basic_fields = [
                        ('batch_number', batch_number),
                        ('manufacture_date', manufacture_date),
                        ('manufacturer', manufacturer)
                    ]
                    
                    for field_name, field_value in basic_fields:
                        if field_value:
                            data = ExtractedData(
                                document_id=document.id,
                                field_name=field_name,
                                field_value=field_value,
                                confidence_score=0.95,
                                original_text=field_value
                            )
                            db.add(data)
                    
                    # 保存测试结果数据
                    test_results = batch_data.get('test_results', {})
                    for test_param, result_value in test_results.items():
                        if result_value and result_value not in ['TBD', '']:
                            data = ExtractedData(
                                document_id=document.id,
                                field_name=test_param,
                                field_value=result_value,
                                confidence_score=0.90,
                                original_text=result_value
                            )
                            db.add(data)
                
                # 提交嵌套事务
                db.commit()
                
                # 添加到成功列表
                batch_data_list.append(batch_data)
                processed_files.append(filename)
                
                # 显示处理摘要
                print(f"\n✅ Successfully processed: {filename}")
                print(f"📦 Batch: {batch_number}")
                print(f"📅 Date: {manufacture_date}")
                print(f"🧪 Test Results: {len([v for v in test_results.values() if v not in ['TBD', 'ND', '']])}/{len(test_results)}")
                
            except Exception as e:
                # 回滚嵌套事务
                db.rollback()
                
                error_msg = str(e)
                filename = os.path.basename(pdf_file) if 'pdf_file' in locals() else "unknown"
                print(f"❌ Error processing {filename}: {error_msg}")
                failed_files.append({"filename": filename, "error": error_msg})
                
                # 如果文档已创建，尝试更新状态为失败
                if document and document.id:
                    try:
                        # 使用新的嵌套事务来更新失败状态
                        with db.begin_nested():
                            fail_doc = db.query(COADocument).filter(
                                COADocument.id == document.id
                            ).first()
                            if fail_doc:
                                # 修复：使用 ProcessingStatus.FAILED.value
                                fail_doc.processing_status = ProcessingStatus.FAILED.value  # 修复：使用枚举值
                                fail_doc.error_message = error_msg[:500]  # 限制错误消息长度
                        db.commit()
                    except Exception as update_error:
                        print(f"Failed to update document status: {update_error}")
                        db.rollback()
                
                continue
        
        # 如果处理成功，更新缓存
        if batch_data_list:
            try:
                print(f"\n💾 Updating cache...")
                current_hashes = calculate_file_hashes(pdf_directory)
                cache_updated = update_cache_record(
                    db, request.compound_id, request.template_id, 
                    batch_data_list, current_hashes, processed_files
                )
                if cache_updated:
                    print(f"✅ Cache updated successfully")
                else:
                    print(f"⚠️ Cache update failed")
            except Exception as e:
                print(f"⚠️ Cache update error: {e}")
        
        # 处理完成后的汇总
        print(f"\n{'='*80}")
        print(f"📈 BATCH ANALYSIS PROCESSING SUMMARY")
        print(f"{'='*80}")
        print(f"📄 Total files found: {len(pdf_files)}")
        print(f"✅ Successfully processed: {len(processed_files)}")
        print(f"❌ Failed: {len(failed_files)}")
        print(f"📊 Total batches analyzed: {len(batch_data_list)}")
        
        if failed_files:
            print(f"\n❌ Failed files:")
            for failed in failed_files:
                print(f"   • {failed['filename']}: {failed['error']}")
        
        if batch_data_list:
            print(f"\n✅ Successfully processed batches:")
            for batch_data in batch_data_list:
                batch_num = batch_data.get('batch_number', 'Unknown')
                mfg_date = batch_data.get('manufacture_date', 'Unknown')
                test_count = len([v for v in batch_data.get('test_results', {}).values() if v not in ['TBD', 'ND', '']])
                print(f"   • {batch_num} (Mfg: {mfg_date}) - {test_count} test results")
        
        print(f"\n🔄 Data Structure:")
        print(f"   • Each batch maintains independent data (no merging)")
        print(f"   • Ready for table generation with {len(batch_data_list)} columns")
        print(f"   • Test parameters: {len(ai_extractor.get_test_parameters())} items")
        print(f"{'='*80}")
        
        # 准备返回数据（保持每个批次独立）
        return ApiResponse(
            success=True,
            data={
                "processedFiles": processed_files,
                "failedFiles": failed_files,
                "totalFiles": len(pdf_files),
                "batchData": batch_data_list,  # 批次数据列表，不合并
                "status": "success" if processed_files else "failed",
                "fromCache": False,
                "cacheUpdated": len(batch_data_list) > 0,
                "message": f"Successfully processed {len(batch_data_list)} batches for COA analysis"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Directory processing failed: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

# ============ 保留原有的其他端点 ============

@router.get("/batch-analysis/{compound_id}", response_model=ApiResponse)
async def get_batch_analysis_data(
    compound_id: UUID,
    db: Session = Depends(get_db)
):
    """Get all batch analysis data for a compound"""
    try:
        # 获取该化合物的所有文档 - 修复：使用 ProcessingStatus.COMPLETED.value
        documents = db.query(COADocument).filter(
            COADocument.compound_id == compound_id,
            COADocument.processing_status == ProcessingStatus.COMPLETED.value  # 修复：使用枚举值
        ).all()
        
        if not documents:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No processed documents found for compound {compound_id}"
            )
        
        batch_data_list = []
        
        for document in documents:
            # 获取该文档的所有提取数据
            extracted_data = db.query(ExtractedData).filter(
                ExtractedData.document_id == document.id
            ).all()
            
            if extracted_data:
                # 重构批次数据
                batch_data = {
                    "filename": document.filename,
                    "batch_number": "",
                    "manufacture_date": "",
                    "manufacturer": "",
                    "test_results": {}
                }
                
                for data in extracted_data:
                    if data.field_name == "batch_number":
                        batch_data["batch_number"] = data.field_value
                    elif data.field_name == "manufacture_date":
                        batch_data["manufacture_date"] = data.field_value
                    elif data.field_name == "manufacturer":
                        batch_data["manufacturer"] = data.field_value
                    else:
                        batch_data["test_results"][data.field_name] = data.field_value
                
                batch_data_list.append(batch_data)
        
        return ApiResponse(
            success=True,
            data={
                "compoundId": str(compound_id),
                "totalBatches": len(batch_data_list),
                "batchData": batch_data_list
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/upload", response_model=ApiResponse)
async def upload_document(
    file: UploadFile = File(...),
    compound_id: str = Form(...),
    template_id: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Upload a COA document (legacy endpoint)"""
    try:
        if not file.filename.endswith('.pdf'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF files are allowed"
            )
        
        if file.size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE / 1024 / 1024}MB"
            )
        
        file_path = await file_manager.save_upload(file, compound_id)
        
        # 修复：使用 ProcessingStatus.PENDING.value
        document = COADocument(
            compound_id=UUID(compound_id),
            filename=file.filename,
            file_path=file_path,
            file_size=f"{file.size / 1024:.2f} KB",
            processing_status=ProcessingStatus.PENDING.value  # 修复：使用枚举值而不是硬编码字符串
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        return ApiResponse(
            success=True,
            data={
                "documentId": str(document.id),
                "filename": document.filename,
                "status": document.processing_status
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )