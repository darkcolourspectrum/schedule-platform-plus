"""Classrooms API Endpoints"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.classroom import ClassroomCreate, ClassroomUpdate, ClassroomResponse
from app.services.classroom_service import ClassroomService
from app.dependencies import get_classroom_service, get_current_admin

router = APIRouter(prefix="/classrooms", tags=["Classrooms"])


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
