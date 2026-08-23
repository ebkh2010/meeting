import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.participants import ParticipantsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/participants", tags=["participants"])


# ---------- Pydantic Schemas ----------
class ParticipantsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    meeting_id: int
    membership_id: int
    member_user_id: str = None
    full_name: str = None
    rsvp_status: str = None
    rsvp_note: str = None
    attended: bool = None


class ParticipantsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    meeting_id: Optional[int] = None
    membership_id: Optional[int] = None
    member_user_id: Optional[str] = None
    full_name: Optional[str] = None
    rsvp_status: Optional[str] = None
    rsvp_note: Optional[str] = None
    attended: Optional[bool] = None


class ParticipantsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    meeting_id: int
    membership_id: int
    member_user_id: Optional[str] = None
    full_name: Optional[str] = None
    rsvp_status: Optional[str] = None
    rsvp_note: Optional[str] = None
    attended: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ParticipantsListResponse(BaseModel):
    """List response schema"""
    items: List[ParticipantsResponse]
    total: int
    skip: int
    limit: int


class ParticipantsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[ParticipantsData]


class ParticipantsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: ParticipantsUpdateData


class ParticipantsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[ParticipantsBatchUpdateItem]


class ParticipantsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=ParticipantsListResponse)
async def query_participantss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query participantss with filtering, sorting, and pagination"""
    logger.debug(f"Querying participantss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = ParticipantsService(db)
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
        logger.debug(f"Found {result['total']} participantss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid participants query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying participantss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=ParticipantsListResponse)
async def query_participantss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query participantss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying participantss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = ParticipantsService(db)
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
        logger.debug(f"Found {result['total']} participantss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid participants query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying participantss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=ParticipantsResponse)
async def get_participants(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single participants by ID"""
    logger.debug(f"Fetching participants with id: {id}, fields={fields}")
    
    service = ParticipantsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Participants with id {id} not found")
            raise HTTPException(status_code=404, detail="Participants not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching participants {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=ParticipantsResponse, status_code=201)
async def create_participants(
    data: ParticipantsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new participants"""
    logger.debug(f"Creating new participants with data: {data}")
    
    service = ParticipantsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create participants")
        
        logger.info(f"Participants created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating participants: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating participants: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[ParticipantsResponse], status_code=201)
async def create_participantss_batch(
    request: ParticipantsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple participantss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} participantss")
    
    service = ParticipantsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} participantss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[ParticipantsResponse])
async def update_participantss_batch(
    request: ParticipantsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple participantss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} participantss")
    
    service = ParticipantsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} participantss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=ParticipantsResponse)
async def update_participants(
    id: int,
    data: ParticipantsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing participants"""
    logger.debug(f"Updating participants {id} with data: {data}")

    service = ParticipantsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Participants with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Participants not found")
        
        logger.info(f"Participants {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating participants {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating participants {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_participantss_batch(
    request: ParticipantsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple participantss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} participantss")
    
    service = ParticipantsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} participantss successfully")
        return {"message": f"Successfully deleted {deleted_count} participantss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_participants(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single participants by ID"""
    logger.debug(f"Deleting participants with id: {id}")
    
    service = ParticipantsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Participants with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Participants not found")
        
        logger.info(f"Participants {id} deleted successfully")
        return {"message": "Participants deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting participants {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")