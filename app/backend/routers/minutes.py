import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.minutes import MinutesService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/minutes", tags=["minutes"])


# ---------- Pydantic Schemas ----------
class MinutesData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    meeting_id: int
    status: str = None
    body_markdown: str = None
    summary: str = None
    current_version: int = None
    generated_by: str = None
    review_requested_at: str = None
    approved_by_name: str = None
    approved_at: str = None
    locked_at: str = None


class MinutesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    meeting_id: Optional[int] = None
    status: Optional[str] = None
    body_markdown: Optional[str] = None
    summary: Optional[str] = None
    current_version: Optional[int] = None
    generated_by: Optional[str] = None
    review_requested_at: Optional[str] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[str] = None
    locked_at: Optional[str] = None


class MinutesResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    meeting_id: int
    status: Optional[str] = None
    body_markdown: Optional[str] = None
    summary: Optional[str] = None
    current_version: Optional[int] = None
    generated_by: Optional[str] = None
    review_requested_at: Optional[str] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[str] = None
    locked_at: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MinutesListResponse(BaseModel):
    """List response schema"""
    items: List[MinutesResponse]
    total: int
    skip: int
    limit: int


class MinutesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[MinutesData]


class MinutesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: MinutesUpdateData


class MinutesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[MinutesBatchUpdateItem]


class MinutesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=MinutesListResponse)
async def query_minutess(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query minutess with filtering, sorting, and pagination"""
    logger.debug(f"Querying minutess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = MinutesService(db)
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
        logger.debug(f"Found {result['total']} minutess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid minutes query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying minutess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=MinutesListResponse)
async def query_minutess_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query minutess with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying minutess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = MinutesService(db)
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
        logger.debug(f"Found {result['total']} minutess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid minutes query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying minutess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=MinutesResponse)
async def get_minutes(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single minutes by ID"""
    logger.debug(f"Fetching minutes with id: {id}, fields={fields}")
    
    service = MinutesService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Minutes with id {id} not found")
            raise HTTPException(status_code=404, detail="Minutes not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching minutes {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=MinutesResponse, status_code=201)
async def create_minutes(
    data: MinutesData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new minutes"""
    logger.debug(f"Creating new minutes with data: {data}")
    
    service = MinutesService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create minutes")
        
        logger.info(f"Minutes created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating minutes: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating minutes: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[MinutesResponse], status_code=201)
async def create_minutess_batch(
    request: MinutesBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple minutess in a single request"""
    logger.debug(f"Batch creating {len(request.items)} minutess")
    
    service = MinutesService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} minutess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[MinutesResponse])
async def update_minutess_batch(
    request: MinutesBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple minutess in a single request"""
    logger.debug(f"Batch updating {len(request.items)} minutess")
    
    service = MinutesService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} minutess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=MinutesResponse)
async def update_minutes(
    id: int,
    data: MinutesUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing minutes"""
    logger.debug(f"Updating minutes {id} with data: {data}")

    service = MinutesService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Minutes with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Minutes not found")
        
        logger.info(f"Minutes {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating minutes {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating minutes {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_minutess_batch(
    request: MinutesBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple minutess by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} minutess")
    
    service = MinutesService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} minutess successfully")
        return {"message": f"Successfully deleted {deleted_count} minutess", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_minutes(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single minutes by ID"""
    logger.debug(f"Deleting minutes with id: {id}")
    
    service = MinutesService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Minutes with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Minutes not found")
        
        logger.info(f"Minutes {id} deleted successfully")
        return {"message": "Minutes deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting minutes {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")