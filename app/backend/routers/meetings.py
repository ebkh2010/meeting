import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.meetings import MeetingsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/meetings", tags=["meetings"])


# ---------- Pydantic Schemas ----------
class MeetingsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    title: str
    description: str = None
    meeting_type: str = None
    starts_at: str
    duration_minutes: int = None
    location: str = None
    online_url: str = None
    secretary_membership_id: int = None
    secretary_name: str = None
    status: str = None
    created_by_user_id: str = None
    created_by_name: str = None


class MeetingsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    starts_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    online_url: Optional[str] = None
    secretary_membership_id: Optional[int] = None
    secretary_name: Optional[str] = None
    status: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_by_name: Optional[str] = None


class MeetingsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    title: str
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    starts_at: str
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    online_url: Optional[str] = None
    secretary_membership_id: Optional[int] = None
    secretary_name: Optional[str] = None
    status: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MeetingsListResponse(BaseModel):
    """List response schema"""
    items: List[MeetingsResponse]
    total: int
    skip: int
    limit: int


class MeetingsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[MeetingsData]


class MeetingsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: MeetingsUpdateData


class MeetingsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[MeetingsBatchUpdateItem]


class MeetingsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=MeetingsListResponse)
async def query_meetingss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query meetingss with filtering, sorting, and pagination"""
    logger.debug(f"Querying meetingss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = MeetingsService(db)
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
        logger.debug(f"Found {result['total']} meetingss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid meetings query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying meetingss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=MeetingsListResponse)
async def query_meetingss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query meetingss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying meetingss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = MeetingsService(db)
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
        logger.debug(f"Found {result['total']} meetingss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid meetings query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying meetingss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=MeetingsResponse)
async def get_meetings(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single meetings by ID"""
    logger.debug(f"Fetching meetings with id: {id}, fields={fields}")
    
    service = MeetingsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Meetings with id {id} not found")
            raise HTTPException(status_code=404, detail="Meetings not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching meetings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=MeetingsResponse, status_code=201)
async def create_meetings(
    data: MeetingsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new meetings"""
    logger.debug(f"Creating new meetings with data: {data}")
    
    service = MeetingsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create meetings")
        
        logger.info(f"Meetings created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating meetings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating meetings: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[MeetingsResponse], status_code=201)
async def create_meetingss_batch(
    request: MeetingsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple meetingss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} meetingss")
    
    service = MeetingsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} meetingss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[MeetingsResponse])
async def update_meetingss_batch(
    request: MeetingsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple meetingss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} meetingss")
    
    service = MeetingsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} meetingss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=MeetingsResponse)
async def update_meetings(
    id: int,
    data: MeetingsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing meetings"""
    logger.debug(f"Updating meetings {id} with data: {data}")

    service = MeetingsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Meetings with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Meetings not found")
        
        logger.info(f"Meetings {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating meetings {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating meetings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_meetingss_batch(
    request: MeetingsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple meetingss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} meetingss")
    
    service = MeetingsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} meetingss successfully")
        return {"message": f"Successfully deleted {deleted_count} meetingss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_meetings(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single meetings by ID"""
    logger.debug(f"Deleting meetings with id: {id}")
    
    service = MeetingsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Meetings with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Meetings not found")
        
        logger.info(f"Meetings {id} deleted successfully")
        return {"message": "Meetings deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting meetings {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")