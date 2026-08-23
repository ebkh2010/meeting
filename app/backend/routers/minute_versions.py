import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.minute_versions import Minute_versionsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/minute_versions", tags=["minute_versions"])


# ---------- Pydantic Schemas ----------
class Minute_versionsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    minutes_id: int
    meeting_id: int = None
    version: int
    body_markdown: str = None
    summary: str = None
    status_at_version: str = None
    changed_by_name: str = None
    change_note: str = None


class Minute_versionsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    minutes_id: Optional[int] = None
    meeting_id: Optional[int] = None
    version: Optional[int] = None
    body_markdown: Optional[str] = None
    summary: Optional[str] = None
    status_at_version: Optional[str] = None
    changed_by_name: Optional[str] = None
    change_note: Optional[str] = None


class Minute_versionsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    minutes_id: int
    meeting_id: Optional[int] = None
    version: int
    body_markdown: Optional[str] = None
    summary: Optional[str] = None
    status_at_version: Optional[str] = None
    changed_by_name: Optional[str] = None
    change_note: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Minute_versionsListResponse(BaseModel):
    """List response schema"""
    items: List[Minute_versionsResponse]
    total: int
    skip: int
    limit: int


class Minute_versionsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Minute_versionsData]


class Minute_versionsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Minute_versionsUpdateData


class Minute_versionsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Minute_versionsBatchUpdateItem]


class Minute_versionsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Minute_versionsListResponse)
async def query_minute_versionss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query minute_versionss with filtering, sorting, and pagination"""
    logger.debug(f"Querying minute_versionss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Minute_versionsService(db)
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
        logger.debug(f"Found {result['total']} minute_versionss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid minute_versions query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying minute_versionss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Minute_versionsListResponse)
async def query_minute_versionss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query minute_versionss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying minute_versionss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Minute_versionsService(db)
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
        logger.debug(f"Found {result['total']} minute_versionss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid minute_versions query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying minute_versionss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Minute_versionsResponse)
async def get_minute_versions(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single minute_versions by ID"""
    logger.debug(f"Fetching minute_versions with id: {id}, fields={fields}")
    
    service = Minute_versionsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Minute_versions with id {id} not found")
            raise HTTPException(status_code=404, detail="Minute_versions not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching minute_versions {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Minute_versionsResponse, status_code=201)
async def create_minute_versions(
    data: Minute_versionsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new minute_versions"""
    logger.debug(f"Creating new minute_versions with data: {data}")
    
    service = Minute_versionsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create minute_versions")
        
        logger.info(f"Minute_versions created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating minute_versions: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating minute_versions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Minute_versionsResponse], status_code=201)
async def create_minute_versionss_batch(
    request: Minute_versionsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple minute_versionss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} minute_versionss")
    
    service = Minute_versionsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} minute_versionss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Minute_versionsResponse])
async def update_minute_versionss_batch(
    request: Minute_versionsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple minute_versionss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} minute_versionss")
    
    service = Minute_versionsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} minute_versionss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Minute_versionsResponse)
async def update_minute_versions(
    id: int,
    data: Minute_versionsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing minute_versions"""
    logger.debug(f"Updating minute_versions {id} with data: {data}")

    service = Minute_versionsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Minute_versions with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Minute_versions not found")
        
        logger.info(f"Minute_versions {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating minute_versions {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating minute_versions {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_minute_versionss_batch(
    request: Minute_versionsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple minute_versionss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} minute_versionss")
    
    service = Minute_versionsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} minute_versionss successfully")
        return {"message": f"Successfully deleted {deleted_count} minute_versionss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_minute_versions(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single minute_versions by ID"""
    logger.debug(f"Deleting minute_versions with id: {id}")
    
    service = Minute_versionsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Minute_versions with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Minute_versions not found")
        
        logger.info(f"Minute_versions {id} deleted successfully")
        return {"message": "Minute_versions deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting minute_versions {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")