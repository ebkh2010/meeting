import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.decisions import DecisionsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/decisions", tags=["decisions"])


# ---------- Pydantic Schemas ----------
class DecisionsData(BaseModel):
    """Entity data schema (for create/update)"""
    organization_id: int
    meeting_id: int
    minutes_id: int = None
    position: int = None
    title: str
    description: str = None
    source: str = None


class DecisionsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    organization_id: Optional[int] = None
    meeting_id: Optional[int] = None
    minutes_id: Optional[int] = None
    position: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None


class DecisionsResponse(BaseModel):
    """Entity response schema"""
    id: int
    organization_id: int
    meeting_id: int
    minutes_id: Optional[int] = None
    position: Optional[int] = None
    title: str
    description: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DecisionsListResponse(BaseModel):
    """List response schema"""
    items: List[DecisionsResponse]
    total: int
    skip: int
    limit: int


class DecisionsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[DecisionsData]


class DecisionsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: DecisionsUpdateData


class DecisionsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[DecisionsBatchUpdateItem]


class DecisionsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=DecisionsListResponse)
async def query_decisionss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query decisionss with filtering, sorting, and pagination"""
    logger.debug(f"Querying decisionss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = DecisionsService(db)
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
        logger.debug(f"Found {result['total']} decisionss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid decisions query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying decisionss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=DecisionsListResponse)
async def query_decisionss_all(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query decisionss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying decisionss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = DecisionsService(db)
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
        logger.debug(f"Found {result['total']} decisionss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid decisions query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying decisionss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=DecisionsResponse)
async def get_decisions(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single decisions by ID"""
    logger.debug(f"Fetching decisions with id: {id}, fields={fields}")
    
    service = DecisionsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Decisions with id {id} not found")
            raise HTTPException(status_code=404, detail="Decisions not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching decisions {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=DecisionsResponse, status_code=201)
async def create_decisions(
    data: DecisionsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new decisions"""
    logger.debug(f"Creating new decisions with data: {data}")
    
    service = DecisionsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create decisions")
        
        logger.info(f"Decisions created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating decisions: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating decisions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[DecisionsResponse], status_code=201)
async def create_decisionss_batch(
    request: DecisionsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple decisionss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} decisionss")
    
    service = DecisionsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} decisionss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[DecisionsResponse])
async def update_decisionss_batch(
    request: DecisionsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple decisionss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} decisionss")
    
    service = DecisionsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} decisionss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=DecisionsResponse)
async def update_decisions(
    id: int,
    data: DecisionsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing decisions"""
    logger.debug(f"Updating decisions {id} with data: {data}")

    service = DecisionsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Decisions with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Decisions not found")
        
        logger.info(f"Decisions {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating decisions {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating decisions {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_decisionss_batch(
    request: DecisionsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple decisionss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} decisionss")
    
    service = DecisionsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} decisionss successfully")
        return {"message": f"Successfully deleted {deleted_count} decisionss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_decisions(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single decisions by ID"""
    logger.debug(f"Deleting decisions with id: {id}")
    
    service = DecisionsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Decisions with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Decisions not found")
        
        logger.info(f"Decisions {id} deleted successfully")
        return {"message": "Decisions deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting decisions {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")