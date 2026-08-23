import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.ai_usage_events import Ai_usage_eventsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/ai_usage_events", tags=["ai_usage_events"])


# ---------- Pydantic Schemas ----------
class Ai_usage_eventsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    job_id: int = None
    meeting_id: int = None
    kind: str
    provider: str = None
    model: str = None
    minutes_charged: int = None
    detail: str = None


class Ai_usage_eventsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    job_id: Optional[int] = None
    meeting_id: Optional[int] = None
    kind: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    minutes_charged: Optional[int] = None
    detail: Optional[str] = None


class Ai_usage_eventsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    job_id: Optional[int] = None
    meeting_id: Optional[int] = None
    kind: str
    provider: Optional[str] = None
    model: Optional[str] = None
    minutes_charged: Optional[int] = None
    detail: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Ai_usage_eventsListResponse(BaseModel):
    """List response schema"""
    items: List[Ai_usage_eventsResponse]
    total: int
    skip: int
    limit: int


class Ai_usage_eventsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Ai_usage_eventsData]


class Ai_usage_eventsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Ai_usage_eventsUpdateData


class Ai_usage_eventsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Ai_usage_eventsBatchUpdateItem]


class Ai_usage_eventsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Ai_usage_eventsListResponse)
async def query_ai_usage_eventss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query ai_usage_eventss with filtering, sorting, and pagination"""
    logger.debug(f"Querying ai_usage_eventss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Ai_usage_eventsService(db)
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
        logger.debug(f"Found {result['total']} ai_usage_eventss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid ai_usage_events query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying ai_usage_eventss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Ai_usage_eventsListResponse)
async def query_ai_usage_eventss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query ai_usage_eventss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying ai_usage_eventss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Ai_usage_eventsService(db)
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
        logger.debug(f"Found {result['total']} ai_usage_eventss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid ai_usage_events query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying ai_usage_eventss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Ai_usage_eventsResponse)
async def get_ai_usage_events(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single ai_usage_events by ID"""
    logger.debug(f"Fetching ai_usage_events with id: {id}, fields={fields}")
    
    service = Ai_usage_eventsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Ai_usage_events with id {id} not found")
            raise HTTPException(status_code=404, detail="Ai_usage_events not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching ai_usage_events {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Ai_usage_eventsResponse, status_code=201)
async def create_ai_usage_events(
    data: Ai_usage_eventsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new ai_usage_events"""
    logger.debug(f"Creating new ai_usage_events with data: {data}")
    
    service = Ai_usage_eventsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create ai_usage_events")
        
        logger.info(f"Ai_usage_events created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating ai_usage_events: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating ai_usage_events: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Ai_usage_eventsResponse], status_code=201)
async def create_ai_usage_eventss_batch(
    request: Ai_usage_eventsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple ai_usage_eventss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} ai_usage_eventss")
    
    service = Ai_usage_eventsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} ai_usage_eventss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Ai_usage_eventsResponse])
async def update_ai_usage_eventss_batch(
    request: Ai_usage_eventsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple ai_usage_eventss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} ai_usage_eventss")
    
    service = Ai_usage_eventsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} ai_usage_eventss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Ai_usage_eventsResponse)
async def update_ai_usage_events(
    id: int,
    data: Ai_usage_eventsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing ai_usage_events"""
    logger.debug(f"Updating ai_usage_events {id} with data: {data}")

    service = Ai_usage_eventsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Ai_usage_events with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Ai_usage_events not found")
        
        logger.info(f"Ai_usage_events {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating ai_usage_events {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating ai_usage_events {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_ai_usage_eventss_batch(
    request: Ai_usage_eventsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple ai_usage_eventss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} ai_usage_eventss")
    
    service = Ai_usage_eventsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} ai_usage_eventss successfully")
        return {"message": f"Successfully deleted {deleted_count} ai_usage_eventss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_ai_usage_events(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single ai_usage_events by ID"""
    logger.debug(f"Deleting ai_usage_events with id: {id}")
    
    service = Ai_usage_eventsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Ai_usage_events with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Ai_usage_events not found")
        
        logger.info(f"Ai_usage_events {id} deleted successfully")
        return {"message": "Ai_usage_events deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting ai_usage_events {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")