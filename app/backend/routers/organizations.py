import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.organizations import OrganizationsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/organizations", tags=["organizations"])


# ---------- Pydantic Schemas ----------
class OrganizationsData(BaseModel):
    """Entity data schema (for create/update)"""
    name: str
    slug: str
    plan_code: str = None
    timezone: str = None
    status: str = None
    monthly_ai_minutes_quota: int = None
    ai_minutes_used: int = None
    quota_period: str = None
    max_concurrent_ai_jobs: int = None
    audio_retention_days: int = None
    max_audio_mb: int = None
    max_audio_minutes: int = None
    is_demo: bool = None


class OrganizationsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    name: Optional[str] = None
    slug: Optional[str] = None
    plan_code: Optional[str] = None
    timezone: Optional[str] = None
    status: Optional[str] = None
    monthly_ai_minutes_quota: Optional[int] = None
    ai_minutes_used: Optional[int] = None
    quota_period: Optional[str] = None
    max_concurrent_ai_jobs: Optional[int] = None
    audio_retention_days: Optional[int] = None
    max_audio_mb: Optional[int] = None
    max_audio_minutes: Optional[int] = None
    is_demo: Optional[bool] = None


class OrganizationsResponse(BaseModel):
    """Entity response schema"""
    id: int
    name: str
    slug: str
    plan_code: Optional[str] = None
    timezone: Optional[str] = None
    status: Optional[str] = None
    monthly_ai_minutes_quota: Optional[int] = None
    ai_minutes_used: Optional[int] = None
    quota_period: Optional[str] = None
    max_concurrent_ai_jobs: Optional[int] = None
    audio_retention_days: Optional[int] = None
    max_audio_mb: Optional[int] = None
    max_audio_minutes: Optional[int] = None
    is_demo: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OrganizationsListResponse(BaseModel):
    """List response schema"""
    items: List[OrganizationsResponse]
    total: int
    skip: int
    limit: int


class OrganizationsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[OrganizationsData]


class OrganizationsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: OrganizationsUpdateData


class OrganizationsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[OrganizationsBatchUpdateItem]


class OrganizationsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=OrganizationsListResponse)
async def query_organizationss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query organizationss with filtering, sorting, and pagination"""
    logger.debug(f"Querying organizationss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = OrganizationsService(db)
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
        logger.debug(f"Found {result['total']} organizationss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid organizations query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying organizationss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=OrganizationsListResponse)
async def query_organizationss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query organizationss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying organizationss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = OrganizationsService(db)
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
        logger.debug(f"Found {result['total']} organizationss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid organizations query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying organizationss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=OrganizationsResponse)
async def get_organizations(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single organizations by ID"""
    logger.debug(f"Fetching organizations with id: {id}, fields={fields}")
    
    service = OrganizationsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Organizations with id {id} not found")
            raise HTTPException(status_code=404, detail="Organizations not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching organizations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=OrganizationsResponse, status_code=201)
async def create_organizations(
    data: OrganizationsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new organizations"""
    logger.debug(f"Creating new organizations with data: {data}")
    
    service = OrganizationsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create organizations")
        
        logger.info(f"Organizations created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating organizations: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating organizations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[OrganizationsResponse], status_code=201)
async def create_organizationss_batch(
    request: OrganizationsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple organizationss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} organizationss")
    
    service = OrganizationsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} organizationss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[OrganizationsResponse])
async def update_organizationss_batch(
    request: OrganizationsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple organizationss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} organizationss")
    
    service = OrganizationsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} organizationss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=OrganizationsResponse)
async def update_organizations(
    id: int,
    data: OrganizationsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing organizations"""
    logger.debug(f"Updating organizations {id} with data: {data}")

    service = OrganizationsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Organizations with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Organizations not found")
        
        logger.info(f"Organizations {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating organizations {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating organizations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_organizationss_batch(
    request: OrganizationsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple organizationss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} organizationss")
    
    service = OrganizationsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} organizationss successfully")
        return {"message": f"Successfully deleted {deleted_count} organizationss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_organizations(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single organizations by ID"""
    logger.debug(f"Deleting organizations with id: {id}")
    
    service = OrganizationsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Organizations with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Organizations not found")
        
        logger.info(f"Organizations {id} deleted successfully")
        return {"message": "Organizations deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting organizations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")