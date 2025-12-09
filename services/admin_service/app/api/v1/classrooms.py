"""Classrooms API Endpoints"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.classroom import ClassroomCreate, ClassroomUpdate, ClassroomResponse
from app.services.classroom_service import ClassroomService
from app.dependencies import get_classroom_service, get_current_admin

router = APIRouter(prefix="/classrooms", tags=["Classrooms"])

@router.get("/studios/{studio_id}/classrooms", response_model=List[ClassroomResponse])
async def get_studio_classrooms(
    studio_id: int,
    admin: dict = Depends(get_current_admin),
    classroom_service: ClassroomService = Depends(get_classroom_service)
):
    """Get all classrooms in studio"""
    return await classroom_service.get_studio_classrooms(studio_id)

@router.get("/{classroom_id}", response_model=ClassroomResponse)
async def get_classroom(
    classroom_id: int,
    admin: dict = Depends(get_current_admin),
    classroom_service: ClassroomService = Depends(get_classroom_service)
):
    """Get classroom by ID"""
    classroom = await classroom_service.get_classroom(classroom_id)
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    return classroom

@router.post("/studios/{studio_id}/classrooms", response_model=ClassroomResponse, status_code=status.HTTP_201_CREATED)
async def create_classroom(
    studio_id: int,
    data: ClassroomCreate,
    admin: dict = Depends(get_current_admin),
    classroom_service: ClassroomService = Depends(get_classroom_service)
):
    """Create new classroom in studio"""
    classroom = await classroom_service.create_classroom(studio_id, **data.model_dump())
    return classroom

@router.put("/{classroom_id}", response_model=ClassroomResponse)
async def update_classroom(
    classroom_id: int,
    data: ClassroomUpdate,
    admin: dict = Depends(get_current_admin),
    classroom_service: ClassroomService = Depends(get_classroom_service)
):
    """Update classroom"""
    update_data = data.model_dump(exclude_unset=True)
    classroom = await classroom_service.update_classroom(classroom_id, **update_data)
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    return classroom

@router.delete("/{classroom_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_classroom(
    classroom_id: int,
    admin: dict = Depends(get_current_admin),
    classroom_service: ClassroomService = Depends(get_classroom_service)
):
    """Delete classroom"""
    deleted = await classroom_service.delete_classroom(classroom_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Classroom not found")
