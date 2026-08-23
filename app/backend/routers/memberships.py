import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.memberships import MembershipsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/memberships", tags=["memberships"])


# ---------- Pydantic Schemas ----------
class MembershipsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    member_user_id: str = None
    email: str = None
    full_name: str
    role: str
    status: str = None
    is_virtual: bool = None


class MembershipsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    member_user_id: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    is_virtual: Optional[bool] = None


class MembershipsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    member_user_id: Optional[str] = None
    email: Optional[str] = None
    full_name: str
    role: str
    status: Optional[str] = None
    is_virtual: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MembershipsListResponse(BaseModel):
    """List response schema"""
    items: List[MembershipsResponse]
    total: int
    skip: int
    limit: int


class MembershipsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[MembershipsData]


class MembershipsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: MembershipsUpdateData


class MembershipsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[MembershipsBatchUpdateItem]


class MembershipsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=MembershipsListResponse)
async def query_membershipss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query membershipss with filtering, sorting, and pagination"""
    logger.debug(f"Querying membershipss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = MembershipsService(db)
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
        logger.debug(f"Found {result['total']} membershipss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid memberships query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying membershipss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=MembershipsListResponse)
async def query_membershipss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query membershipss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying membershipss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = MembershipsService(db)
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
        logger.debug(f"Found {result['total']} membershipss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid memberships query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying membershipss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=MembershipsResponse)
async def get_memberships(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single memberships by ID"""
    logger.debug(f"Fetching memberships with id: {id}, fields={fields}")
    
    service = MembershipsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Memberships with id {id} not found")
            raise HTTPException(status_code=404, detail="Memberships not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching memberships {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=MembershipsResponse, status_code=201)
async def create_memberships(
    data: MembershipsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new memberships"""
    logger.debug(f"Creating new memberships with data: {data}")
    
    service = MembershipsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create memberships")
        
        logger.info(f"Memberships created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating memberships: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating memberships: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[MembershipsResponse], status_code=201)
async def create_membershipss_batch(
    request: MembershipsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple membershipss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} membershipss")
    
    service = MembershipsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} membershipss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[MembershipsResponse])
async def update_membershipss_batch(
    request: MembershipsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple membershipss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} membershipss")
    
    service = MembershipsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} membershipss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=MembershipsResponse)
async def update_memberships(
    id: int,
    data: MembershipsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing memberships"""
    logger.debug(f"Updating memberships {id} with data: {data}")

    service = MembershipsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Memberships with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Memberships not found")
        
        logger.info(f"Memberships {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating memberships {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating memberships {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_membershipss_batch(
    request: MembershipsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple membershipss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} membershipss")
    
    service = MembershipsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} membershipss successfully")
        return {"message": f"Successfully deleted {deleted_count} membershipss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_memberships(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single memberships by ID"""
    logger.debug(f"Deleting memberships with id: {id}")
    
    service = MembershipsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Memberships with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Memberships not found")
        
        logger.info(f"Memberships {id} deleted successfully")
        return {"message": "Memberships deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting memberships {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")