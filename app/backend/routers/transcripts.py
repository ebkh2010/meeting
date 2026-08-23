import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.transcripts import TranscriptsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/transcripts", tags=["transcripts"])


# ---------- Pydantic Schemas ----------
class TranscriptsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    meeting_id: int
    recording_id: int
    provider: str = None
    model: str = None
    full_text: str = None
    segments_json: str = None
    duration_seconds: int = None
    known_word_ratio: float = None
    stats_words: int = None
    stats_known_words: int = None
    job_id: int = None


class TranscriptsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    meeting_id: Optional[int] = None
    recording_id: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    full_text: Optional[str] = None
    segments_json: Optional[str] = None
    duration_seconds: Optional[int] = None
    known_word_ratio: Optional[float] = None
    stats_words: Optional[int] = None
    stats_known_words: Optional[int] = None
    job_id: Optional[int] = None


class TranscriptsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    meeting_id: int
    recording_id: int
    provider: Optional[str] = None
    model: Optional[str] = None
    full_text: Optional[str] = None
    segments_json: Optional[str] = None
    duration_seconds: Optional[int] = None
    known_word_ratio: Optional[float] = None
    stats_words: Optional[int] = None
    stats_known_words: Optional[int] = None
    job_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TranscriptsListResponse(BaseModel):
    """List response schema"""
    items: List[TranscriptsResponse]
    total: int
    skip: int
    limit: int


class TranscriptsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[TranscriptsData]


class TranscriptsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: TranscriptsUpdateData


class TranscriptsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[TranscriptsBatchUpdateItem]


class TranscriptsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=TranscriptsListResponse)
async def query_transcriptss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query transcriptss with filtering, sorting, and pagination"""
    logger.debug(f"Querying transcriptss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = TranscriptsService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")
        
        result = await service.get_list(
            skip=skip, 
            limit=limit,
            query_dict=query_dict,
            sort=sort,
        )
        logger.debug(f"Found {result['total']} transcriptss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid transcripts query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying transcriptss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=TranscriptsListResponse)
async def query_transcriptss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query transcriptss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying transcriptss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = TranscriptsService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")

        result = await service.get_list(
            skip=skip,
            limit=limit,
            query_dict=query_dict,
            sort=sort
        )
        logger.debug(f"Found {result['total']} transcriptss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid transcripts query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying transcriptss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=TranscriptsResponse)
async def get_transcripts(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single transcripts by ID"""
    logger.debug(f"Fetching transcripts with id: {id}, fields={fields}")
    
    service = TranscriptsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Transcripts with id {id} not found")
            raise HTTPException(status_code=404, detail="Transcripts not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transcripts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=TranscriptsResponse, status_code=201)
async def create_transcripts(
    data: TranscriptsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new transcripts"""
    logger.debug(f"Creating new transcripts with data: {data}")
    
    service = TranscriptsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create transcripts")
        
        logger.info(f"Transcripts created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating transcripts: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating transcripts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[TranscriptsResponse], status_code=201)
async def create_transcriptss_batch(
    request: TranscriptsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple transcriptss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} transcriptss")
    
    service = TranscriptsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} transcriptss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[TranscriptsResponse])
async def update_transcriptss_batch(
    request: TranscriptsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple transcriptss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} transcriptss")
    
    service = TranscriptsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} transcriptss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=TranscriptsResponse)
async def update_transcripts(
    id: int,
    data: TranscriptsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing transcripts"""
    logger.debug(f"Updating transcripts {id} with data: {data}")

    service = TranscriptsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Transcripts with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Transcripts not found")
        
        logger.info(f"Transcripts {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating transcripts {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating transcripts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_transcriptss_batch(
    request: TranscriptsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple transcriptss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} transcriptss")
    
    service = TranscriptsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} transcriptss successfully")
        return {"message": f"Successfully deleted {deleted_count} transcriptss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_transcripts(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single transcripts by ID"""
    logger.debug(f"Deleting transcripts with id: {id}")
    
    service = TranscriptsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Transcripts with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Transcripts not found")
        
        logger.info(f"Transcripts {id} deleted successfully")
        return {"message": "Transcripts deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting transcripts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")