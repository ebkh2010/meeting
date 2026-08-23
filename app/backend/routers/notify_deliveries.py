import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.notify_deliveries import Notify_deliveriesService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/notify_deliveries", tags=["notify_deliveries"])


# ---------- Pydantic Schemas ----------
class Notify_deliveriesData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    meeting_id: int = None
    membership_id: int = None
    channel: str
    recipient: str = None
    recipient_name: str = None
    status: str
    provider_message_id: str = None
    error_message: str = None
    body_preview: str = None


class Notify_deliveriesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    meeting_id: Optional[int] = None
    membership_id: Optional[int] = None
    channel: Optional[str] = None
    recipient: Optional[str] = None
    recipient_name: Optional[str] = None
    status: Optional[str] = None
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None
    body_preview: Optional[str] = None


class Notify_deliveriesResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    meeting_id: Optional[int] = None
    membership_id: Optional[int] = None
    channel: str
    recipient: Optional[str] = None
    recipient_name: Optional[str] = None
    status: str
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None
    body_preview: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Notify_deliveriesListResponse(BaseModel):
    """List response schema"""
    items: List[Notify_deliveriesResponse]
    total: int
    skip: int
    limit: int


class Notify_deliveriesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Notify_deliveriesData]


class Notify_deliveriesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Notify_deliveriesUpdateData


class Notify_deliveriesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Notify_deliveriesBatchUpdateItem]


class Notify_deliveriesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Notify_deliveriesListResponse)
async def query_notify_deliveriess(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query notify_deliveriess with filtering, sorting, and pagination"""
    logger.debug(f"Querying notify_deliveriess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Notify_deliveriesService(db)
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
        logger.debug(f"Found {result['total']} notify_deliveriess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid notify_deliveries query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying notify_deliveriess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Notify_deliveriesListResponse)
async def query_notify_deliveriess_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query notify_deliveriess with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying notify_deliveriess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Notify_deliveriesService(db)
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
        logger.debug(f"Found {result['total']} notify_deliveriess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid notify_deliveries query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying notify_deliveriess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Notify_deliveriesResponse)
async def get_notify_deliveries(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single notify_deliveries by ID"""
    logger.debug(f"Fetching notify_deliveries with id: {id}, fields={fields}")
    
    service = Notify_deliveriesService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Notify_deliveries with id {id} not found")
            raise HTTPException(status_code=404, detail="Notify_deliveries not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching notify_deliveries {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Notify_deliveriesResponse, status_code=201)
async def create_notify_deliveries(
    data: Notify_deliveriesData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new notify_deliveries"""
    logger.debug(f"Creating new notify_deliveries with data: {data}")
    
    service = Notify_deliveriesService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create notify_deliveries")
        
        logger.info(f"Notify_deliveries created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating notify_deliveries: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating notify_deliveries: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Notify_deliveriesResponse], status_code=201)
async def create_notify_deliveriess_batch(
    request: Notify_deliveriesBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple notify_deliveriess in a single request"""
    logger.debug(f"Batch creating {len(request.items)} notify_deliveriess")
    
    service = Notify_deliveriesService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} notify_deliveriess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Notify_deliveriesResponse])
async def update_notify_deliveriess_batch(
    request: Notify_deliveriesBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple notify_deliveriess in a single request"""
    logger.debug(f"Batch updating {len(request.items)} notify_deliveriess")
    
    service = Notify_deliveriesService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} notify_deliveriess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Notify_deliveriesResponse)
async def update_notify_deliveries(
    id: int,
    data: Notify_deliveriesUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing notify_deliveries"""
    logger.debug(f"Updating notify_deliveries {id} with data: {data}")

    service = Notify_deliveriesService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Notify_deliveries with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Notify_deliveries not found")
        
        logger.info(f"Notify_deliveries {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating notify_deliveries {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating notify_deliveries {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_notify_deliveriess_batch(
    request: Notify_deliveriesBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple notify_deliveriess by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} notify_deliveriess")
    
    service = Notify_deliveriesService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} notify_deliveriess successfully")
        return {"message": f"Successfully deleted {deleted_count} notify_deliveriess", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_notify_deliveries(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single notify_deliveries by ID"""
    logger.debug(f"Deleting notify_deliveries with id: {id}")
    
    service = Notify_deliveriesService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Notify_deliveries with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Notify_deliveries not found")
        
        logger.info(f"Notify_deliveries {id} deleted successfully")
        return {"message": "Notify_deliveries deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notify_deliveries {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")