"""Tests for Studio CRUD"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.studio_service import StudioService
from app.models.studio import Studio

@pytest.mark.asyncio
async def test_create_studio(db_session: AsyncSession):
    """Test creating a studio"""
    service = StudioService(db_session)
    
    studio = await service.create_studio(
        name="Test Studio",
        description="Test Description",
        address="Test Address"
    )
    
    assert studio.id is not None
    assert studio.name == "Test Studio"
    assert studio.is_active is True

@pytest.mark.asyncio
async def test_get_studio(db_session: AsyncSession):
    """Test getting a studio by ID"""
    service = StudioService(db_session)
    
    created = await service.create_studio(name="Test Studio")
    fetched = await service.get_studio(created.id)
    
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Test Studio"

@pytest.mark.asyncio
async def test_update_studio(db_session: AsyncSession):
    """Test updating a studio"""
    service = StudioService(db_session)
    
    studio = await service.create_studio(name="Original Name")
    updated = await service.update_studio(studio.id, name="Updated Name")
    
    assert updated.name == "Updated Name"

@pytest.mark.asyncio
async def test_delete_studio(db_session: AsyncSession):
    """Test deleting a studio"""
    service = StudioService(db_session)
    
    studio = await service.create_studio(name="To Delete")
    deleted = await service.delete_studio(studio.id)
    
    assert deleted is True
    
    fetched = await service.get_studio(studio.id)
    assert fetched is None
