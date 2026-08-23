import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.recordings import RecordingsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/recordings", tags=["recordings"])


# ---------- Pydantic Schemas ----------
class RecordingsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    meeting_id: int
    bucket_name: str = None
    object_key: str
    file_name: str = None
    mime_type: str = None
    size_bytes: int = None
    duration_seconds: int = None
    upload_status: str = None
    consent_ack: bool = None
    purge_after: str = None
    uploaded_by_name: str = None


class RecordingsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    meeting_id: Optional[int] = None
    bucket_name: Optional[str] = None
    object_key: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    duration_seconds: Optional[int] = None
    upload_status: Optional[str] = None
    consent_ack: Optional[bool] = None
    purge_after: Optional[str] = None
    uploaded_by_name: Optional[str] = None


class RecordingsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    meeting_id: int
    bucket_name: Optional[str] = None
    object_key: str
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    duration_seconds: Optional[int] = None
    upload_status: Optional[str] = None
    consent_ack: Optional[bool] = None
    purge_after: Optional[str] = None
    uploaded_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RecordingsListResponse(BaseModel):
    """List response schema"""
    items: List[RecordingsResponse]
    total: int
    skip: int
    limit: int


class RecordingsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[RecordingsData]


class RecordingsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: RecordingsUpdateData


class RecordingsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[RecordingsBatchUpdateItem]


class RecordingsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=RecordingsListResponse)
async def query_recordingss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query recordingss with filtering, sorting, and pagination"""
    logger.debug(f"Querying recordingss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = RecordingsService(db)
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
        logger.debug(f"Found {result['total']} recordingss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid recordings query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying recordingss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=RecordingsListResponse)
async def query_recordingss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query recordingss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying recordingss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = RecordingsService(db)
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
        logger.debug(f"Found {result['total']} recordingss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid recordings query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying recordingss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=RecordingsResponse)
async def get_recordings(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single recordings by ID"""
    logger.debug(f"Fetching recordings with id: {id}, fields={fields}")
    
    service = RecordingsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Recordings with id {id} not found")
            raise HTTPException(status_code=404, detail="Recordings not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching recordings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=RecordingsResponse, status_code=201)
async def create_recordings(
    data: RecordingsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new recordings"""
    logger.debug(f"Creating new recordings with data: {data}")
    
    service = RecordingsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create recordings")
        
        logger.info(f"Recordings created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating recordings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating recordings: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[RecordingsResponse], status_code=201)
async def create_recordingss_batch(
    request: RecordingsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple recordingss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} recordingss")
    
    service = RecordingsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} recordingss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[RecordingsResponse])
async def update_recordingss_batch(
    request: RecordingsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple recordingss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} recordingss")
    
    service = RecordingsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} recordingss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=RecordingsResponse)
async def update_recordings(
    id: int,
    data: RecordingsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing recordings"""
    logger.debug(f"Updating recordings {id} with data: {data}")

    service = RecordingsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Recordings with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Recordings not found")
        
        logger.info(f"Recordings {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating recordings {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating recordings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_recordingss_batch(
    request: RecordingsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple recordingss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} recordingss")
    
    service = RecordingsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} recordingss successfully")
        return {"message": f"Successfully deleted {deleted_count} recordingss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_recordings(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single recordings by ID"""
    logger.debug(f"Deleting recordings with id: {id}")
    
    service = RecordingsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Recordings with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Recordings not found")
        
        logger.info(f"Recordings {id} deleted successfully")
        return {"message": "Recordings deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting recordings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")