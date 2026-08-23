import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.org_notify_settings import Org_notify_settingsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/org_notify_settings", tags=["org_notify_settings"])


# ---------- Pydantic Schemas ----------
class Org_notify_settingsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    smtp_enabled: bool = None
    smtp_host: str = None
    smtp_port: int = None
    smtp_username: str = None
    smtp_password_enc: str = None
    smtp_use_tls: bool = None
    smtp_use_ssl: bool = None
    smtp_from_email: str = None
    smtp_from_name: str = None
    sms_enabled: bool = None
    sms_api_key_enc: str = None
    sms_line_number: str = None


class Org_notify_settingsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    smtp_enabled: Optional[bool] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password_enc: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_use_ssl: Optional[bool] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    sms_enabled: Optional[bool] = None
    sms_api_key_enc: Optional[str] = None
    sms_line_number: Optional[str] = None


class Org_notify_settingsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    smtp_enabled: Optional[bool] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password_enc: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_use_ssl: Optional[bool] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    sms_enabled: Optional[bool] = None
    sms_api_key_enc: Optional[str] = None
    sms_line_number: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Org_notify_settingsListResponse(BaseModel):
    """List response schema"""
    items: List[Org_notify_settingsResponse]
    total: int
    skip: int
    limit: int


class Org_notify_settingsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Org_notify_settingsData]


class Org_notify_settingsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Org_notify_settingsUpdateData


class Org_notify_settingsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Org_notify_settingsBatchUpdateItem]


class Org_notify_settingsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Org_notify_settingsListResponse)
async def query_org_notify_settingss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query org_notify_settingss with filtering, sorting, and pagination"""
    logger.debug(f"Querying org_notify_settingss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Org_notify_settingsService(db)
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
        logger.debug(f"Found {result['total']} org_notify_settingss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid org_notify_settings query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying org_notify_settingss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Org_notify_settingsListResponse)
async def query_org_notify_settingss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query org_notify_settingss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying org_notify_settingss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Org_notify_settingsService(db)
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
        logger.debug(f"Found {result['total']} org_notify_settingss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid org_notify_settings query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying org_notify_settingss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Org_notify_settingsResponse)
async def get_org_notify_settings(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single org_notify_settings by ID"""
    logger.debug(f"Fetching org_notify_settings with id: {id}, fields={fields}")
    
    service = Org_notify_settingsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Org_notify_settings with id {id} not found")
            raise HTTPException(status_code=404, detail="Org_notify_settings not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching org_notify_settings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Org_notify_settingsResponse, status_code=201)
async def create_org_notify_settings(
    data: Org_notify_settingsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new org_notify_settings"""
    logger.debug(f"Creating new org_notify_settings with data: {data}")
    
    service = Org_notify_settingsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create org_notify_settings")
        
        logger.info(f"Org_notify_settings created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating org_notify_settings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating org_notify_settings: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Org_notify_settingsResponse], status_code=201)
async def create_org_notify_settingss_batch(
    request: Org_notify_settingsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple org_notify_settingss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} org_notify_settingss")
    
    service = Org_notify_settingsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} org_notify_settingss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Org_notify_settingsResponse])
async def update_org_notify_settingss_batch(
    request: Org_notify_settingsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple org_notify_settingss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} org_notify_settingss")
    
    service = Org_notify_settingsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} org_notify_settingss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Org_notify_settingsResponse)
async def update_org_notify_settings(
    id: int,
    data: Org_notify_settingsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing org_notify_settings"""
    logger.debug(f"Updating org_notify_settings {id} with data: {data}")

    service = Org_notify_settingsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Org_notify_settings with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Org_notify_settings not found")
        
        logger.info(f"Org_notify_settings {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating org_notify_settings {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating org_notify_settings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_org_notify_settingss_batch(
    request: Org_notify_settingsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple org_notify_settingss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} org_notify_settingss")
    
    service = Org_notify_settingsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} org_notify_settingss successfully")
        return {"message": f"Successfully deleted {deleted_count} org_notify_settingss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_org_notify_settings(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single org_notify_settings by ID"""
    logger.debug(f"Deleting org_notify_settings with id: {id}")
    
    service = Org_notify_settingsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Org_notify_settings with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Org_notify_settings not found")
        
        logger.info(f"Org_notify_settings {id} deleted successfully")
        return {"message": "Org_notify_settings deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting org_notify_settings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")