import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.org_ai_providers import Org_ai_providersService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/org_ai_providers", tags=["org_ai_providers"])


# ---------- Pydantic Schemas ----------
class Org_ai_providersData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    kind: str
    provider_key: str
    display_name: str = None
    enabled: bool = None
    priority: int = None
    base_url: str = None
    model: str = None
    api_key_enc: str = None
    auth_username: str = None
    auth_password_enc: str = None
    diarization: bool = None
    extra_json: str = None
    last_test_ok: bool = None
    last_test_at: str = None
    last_test_message: str = None


class Org_ai_providersUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    kind: Optional[str] = None
    provider_key: Optional[str] = None
    display_name: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key_enc: Optional[str] = None
    auth_username: Optional[str] = None
    auth_password_enc: Optional[str] = None
    diarization: Optional[bool] = None
    extra_json: Optional[str] = None
    last_test_ok: Optional[bool] = None
    last_test_at: Optional[str] = None
    last_test_message: Optional[str] = None


class Org_ai_providersResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    kind: str
    provider_key: str
    display_name: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key_enc: Optional[str] = None
    auth_username: Optional[str] = None
    auth_password_enc: Optional[str] = None
    diarization: Optional[bool] = None
    extra_json: Optional[str] = None
    last_test_ok: Optional[bool] = None
    last_test_at: Optional[str] = None
    last_test_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Org_ai_providersListResponse(BaseModel):
    """List response schema"""
    items: List[Org_ai_providersResponse]
    total: int
    skip: int
    limit: int


class Org_ai_providersBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Org_ai_providersData]


class Org_ai_providersBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Org_ai_providersUpdateData


class Org_ai_providersBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Org_ai_providersBatchUpdateItem]


class Org_ai_providersBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Org_ai_providersListResponse)
async def query_org_ai_providerss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query org_ai_providerss with filtering, sorting, and pagination"""
    logger.debug(f"Querying org_ai_providerss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Org_ai_providersService(db)
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
        logger.debug(f"Found {result['total']} org_ai_providerss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid org_ai_providers query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying org_ai_providerss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Org_ai_providersListResponse)
async def query_org_ai_providerss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query org_ai_providerss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying org_ai_providerss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Org_ai_providersService(db)
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
        logger.debug(f"Found {result['total']} org_ai_providerss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid org_ai_providers query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying org_ai_providerss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Org_ai_providersResponse)
async def get_org_ai_providers(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single org_ai_providers by ID"""
    logger.debug(f"Fetching org_ai_providers with id: {id}, fields={fields}")
    
    service = Org_ai_providersService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Org_ai_providers with id {id} not found")
            raise HTTPException(status_code=404, detail="Org_ai_providers not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching org_ai_providers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Org_ai_providersResponse, status_code=201)
async def create_org_ai_providers(
    data: Org_ai_providersData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new org_ai_providers"""
    logger.debug(f"Creating new org_ai_providers with data: {data}")
    
    service = Org_ai_providersService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create org_ai_providers")
        
        logger.info(f"Org_ai_providers created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating org_ai_providers: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating org_ai_providers: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Org_ai_providersResponse], status_code=201)
async def create_org_ai_providerss_batch(
    request: Org_ai_providersBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple org_ai_providerss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} org_ai_providerss")
    
    service = Org_ai_providersService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} org_ai_providerss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Org_ai_providersResponse])
async def update_org_ai_providerss_batch(
    request: Org_ai_providersBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple org_ai_providerss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} org_ai_providerss")
    
    service = Org_ai_providersService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} org_ai_providerss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Org_ai_providersResponse)
async def update_org_ai_providers(
    id: int,
    data: Org_ai_providersUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing org_ai_providers"""
    logger.debug(f"Updating org_ai_providers {id} with data: {data}")

    service = Org_ai_providersService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Org_ai_providers with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Org_ai_providers not found")
        
        logger.info(f"Org_ai_providers {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating org_ai_providers {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating org_ai_providers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_org_ai_providerss_batch(
    request: Org_ai_providersBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple org_ai_providerss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} org_ai_providerss")
    
    service = Org_ai_providersService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} org_ai_providerss successfully")
        return {"message": f"Successfully deleted {deleted_count} org_ai_providerss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_org_ai_providers(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single org_ai_providers by ID"""
    logger.debug(f"Deleting org_ai_providers with id: {id}")
    
    service = Org_ai_providersService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Org_ai_providers with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Org_ai_providers not found")
        
        logger.info(f"Org_ai_providers {id} deleted successfully")
        return {"message": "Org_ai_providers deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting org_ai_providers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")