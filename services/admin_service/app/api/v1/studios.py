"""Studios API Endpoints"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.studio import StudioCreate, StudioUpdate, StudioResponse
from app.services.studio_service import StudioService
from app.dependencies import get_studio_service, get_current_admin

router = APIRouter(prefix="/studios", tags=["Studios"])

@router.get("/", response_model=List[StudioResponse])
async def get_studios(
    include_inactive: bool = False,
    admin: dict = Depends(get_current_admin),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Get all studios"""
    studios = await studio_service.get_all_studios(include_inactive)
    return studios

@router.get("/{studio_id}", response_model=StudioResponse)
async def get_studio(
    studio_id: int,
    admin: dict = Depends(get_current_admin),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Get studio by ID"""
    studio = await studio_service.get_studio(studio_id)
    if not studio:
        raise HTTPException(status_code=404, detail="Studio not found")
    return studio

@router.post("/", response_model=StudioResponse, status_code=status.HTTP_201_CREATED)
async def create_studio(
    data: StudioCreate,
    admin: dict = Depends(get_current_admin),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Create new studio"""
    studio = await studio_service.create_studio(**data.model_dump())
    return studio

@router.put("/{studio_id}", response_model=StudioResponse)
async def update_studio(
    studio_id: int,
    data: StudioUpdate,
    admin: dict = Depends(get_current_admin),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Update studio"""
    update_data = data.model_dump(exclude_unset=True)
    studio = await studio_service.update_studio(studio_id, **update_data)
    if not studio:
        raise HTTPException(status_code=404, detail="Studio not found")
    return studio

@router.delete("/{studio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_studio(
    studio_id: int,
    admin: dict = Depends(get_current_admin),
    studio_service: StudioService = Depends(get_studio_service)
):
    """Delete studio"""
    deleted = await studio_service.delete_studio(studio_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Studio not found")
