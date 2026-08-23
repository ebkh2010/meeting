import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.invitations import InvitationsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/invitations", tags=["invitations"])


# ---------- Pydantic Schemas ----------
class InvitationsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    email: str
    role: str
    token: str
    status: str = None
    expires_at: str = None
    invited_by_name: str = None


class InvitationsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None
    token: Optional[str] = None
    status: Optional[str] = None
    expires_at: Optional[str] = None
    invited_by_name: Optional[str] = None


class InvitationsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    email: str
    role: str
    token: str
    status: Optional[str] = None
    expires_at: Optional[str] = None
    invited_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InvitationsListResponse(BaseModel):
    """List response schema"""
    items: List[InvitationsResponse]
    total: int
    skip: int
    limit: int


class InvitationsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[InvitationsData]


class InvitationsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: InvitationsUpdateData


class InvitationsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[InvitationsBatchUpdateItem]


class InvitationsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=InvitationsListResponse)
async def query_invitationss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query invitationss with filtering, sorting, and pagination"""
    logger.debug(f"Querying invitationss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = InvitationsService(db)
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
        logger.debug(f"Found {result['total']} invitationss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid invitations query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying invitationss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=InvitationsListResponse)
async def query_invitationss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query invitationss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying invitationss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = InvitationsService(db)
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
        logger.debug(f"Found {result['total']} invitationss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid invitations query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying invitationss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=InvitationsResponse)
async def get_invitations(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single invitations by ID"""
    logger.debug(f"Fetching invitations with id: {id}, fields={fields}")
    
    service = InvitationsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Invitations with id {id} not found")
            raise HTTPException(status_code=404, detail="Invitations not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching invitations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=InvitationsResponse, status_code=201)
async def create_invitations(
    data: InvitationsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new invitations"""
    logger.debug(f"Creating new invitations with data: {data}")
    
    service = InvitationsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create invitations")
        
        logger.info(f"Invitations created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating invitations: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating invitations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[InvitationsResponse], status_code=201)
async def create_invitationss_batch(
    request: InvitationsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple invitationss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} invitationss")
    
    service = InvitationsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} invitationss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[InvitationsResponse])
async def update_invitationss_batch(
    request: InvitationsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple invitationss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} invitationss")
    
    service = InvitationsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} invitationss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=InvitationsResponse)
async def update_invitations(
    id: int,
    data: InvitationsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing invitations"""
    logger.debug(f"Updating invitations {id} with data: {data}")

    service = InvitationsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Invitations with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Invitations not found")
        
        logger.info(f"Invitations {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating invitations {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating invitations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_invitationss_batch(
    request: InvitationsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple invitationss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} invitationss")
    
    service = InvitationsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} invitationss successfully")
        return {"message": f"Successfully deleted {deleted_count} invitationss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_invitations(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single invitations by ID"""
    logger.debug(f"Deleting invitations with id: {id}")
    
    service = InvitationsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Invitations with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Invitations not found")
        
        logger.info(f"Invitations {id} deleted successfully")
        return {"message": "Invitations deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting invitations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")