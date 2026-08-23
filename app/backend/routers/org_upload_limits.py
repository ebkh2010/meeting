import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.org_upload_limits import Org_upload_limitsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/org_upload_limits", tags=["org_upload_limits"])


# ---------- Pydantic Schemas ----------
class Org_upload_limitsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    max_audio_minutes: int = None
    max_audio_mb: int = None
    max_attachment_mb: int = None
    updated_by_name: str = None


class Org_upload_limitsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    max_audio_minutes: Optional[int] = None
    max_audio_mb: Optional[int] = None
    max_attachment_mb: Optional[int] = None
    updated_by_name: Optional[str] = None


class Org_upload_limitsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    max_audio_minutes: Optional[int] = None
    max_audio_mb: Optional[int] = None
    max_attachment_mb: Optional[int] = None
    updated_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Org_upload_limitsListResponse(BaseModel):
    """List response schema"""
    items: List[Org_upload_limitsResponse]
    total: int
    skip: int
    limit: int


class Org_upload_limitsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Org_upload_limitsData]


class Org_upload_limitsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Org_upload_limitsUpdateData


class Org_upload_limitsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Org_upload_limitsBatchUpdateItem]


class Org_upload_limitsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Org_upload_limitsListResponse)
async def query_org_upload_limitss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query org_upload_limitss with filtering, sorting, and pagination"""
    logger.debug(f"Querying org_upload_limitss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Org_upload_limitsService(db)
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
        logger.debug(f"Found {result['total']} org_upload_limitss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid org_upload_limits query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying org_upload_limitss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Org_upload_limitsListResponse)
async def query_org_upload_limitss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query org_upload_limitss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying org_upload_limitss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Org_upload_limitsService(db)
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
        logger.debug(f"Found {result['total']} org_upload_limitss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid org_upload_limits query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying org_upload_limitss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Org_upload_limitsResponse)
async def get_org_upload_limits(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single org_upload_limits by ID"""
    logger.debug(f"Fetching org_upload_limits with id: {id}, fields={fields}")
    
    service = Org_upload_limitsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Org_upload_limits with id {id} not found")
            raise HTTPException(status_code=404, detail="Org_upload_limits not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching org_upload_limits {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Org_upload_limitsResponse, status_code=201)
async def create_org_upload_limits(
    data: Org_upload_limitsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new org_upload_limits"""
    logger.debug(f"Creating new org_upload_limits with data: {data}")
    
    service = Org_upload_limitsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create org_upload_limits")
        
        logger.info(f"Org_upload_limits created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating org_upload_limits: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating org_upload_limits: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Org_upload_limitsResponse], status_code=201)
async def create_org_upload_limitss_batch(
    request: Org_upload_limitsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple org_upload_limitss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} org_upload_limitss")
    
    service = Org_upload_limitsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} org_upload_limitss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Org_upload_limitsResponse])
async def update_org_upload_limitss_batch(
    request: Org_upload_limitsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple org_upload_limitss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} org_upload_limitss")
    
    service = Org_upload_limitsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} org_upload_limitss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Org_upload_limitsResponse)
async def update_org_upload_limits(
    id: int,
    data: Org_upload_limitsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing org_upload_limits"""
    logger.debug(f"Updating org_upload_limits {id} with data: {data}")

    service = Org_upload_limitsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Org_upload_limits with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Org_upload_limits not found")
        
        logger.info(f"Org_upload_limits {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating org_upload_limits {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating org_upload_limits {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_org_upload_limitss_batch(
    request: Org_upload_limitsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple org_upload_limitss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} org_upload_limitss")
    
    service = Org_upload_limitsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} org_upload_limitss successfully")
        return {"message": f"Successfully deleted {deleted_count} org_upload_limitss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_org_upload_limits(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single org_upload_limits by ID"""
    logger.debug(f"Deleting org_upload_limits with id: {id}")
    
    service = Org_upload_limitsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Org_upload_limits with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Org_upload_limits not found")
        
        logger.info(f"Org_upload_limits {id} deleted successfully")
        return {"message": "Org_upload_limits deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting org_upload_limits {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")