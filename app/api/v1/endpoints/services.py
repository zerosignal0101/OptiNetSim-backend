# app/api/v1/endpoints/services.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
import networkx as nx

from ....core.database import get_database
from ....crud import crud_network
from ....models.network import ServiceCreate, ServiceInDB, ServiceUpdate
from ....utils.minimize import minimize_network

router = APIRouter()


@router.get(
    "",
    response_model=List[ServiceInDB],
    summary="List Services for a Network"
)
async def list_services(
        network_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Retrieves a list of all services provisioned within the specified optical network.
    """
    services = await crud_network.get_all_services_in_network(db, network_id)
    if services is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found."}
        )
    return services


@router.post(
    "",
    response_model=ServiceInDB,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Service in a Network"
)
async def create_service(
        network_id: str,
        service_in: ServiceCreate,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Creates a new service (e.g., optical path, channel) within the specified optical network.
    """
    # 获取原始网络数据
    db_network = await crud_network.get_network(db, network_id)
    if db_network is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found"}
        )

    network_raw, _, __, ___ = minimize_network(db_network)
    service_in.path = nx.shortest_path(network_raw, service_in.source_id, service_in.destination_id, 'weight')

    # Optional: Add validation for service_in.path elements to ensure they exist as nodes/connections
    db_service = await crud_network.add_service_to_network(db, network_id, service_in)
    if db_service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found."}
        )
    return db_service


@router.get(
    "/{service_id}",
    response_model=ServiceInDB,
    summary="Get a specific Service by ID"
)
async def get_service(
        network_id: str,
        service_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Retrieves the detailed information for a specific service within a network.
    """
    service = await crud_network.get_service_from_network(db, network_id, service_id)
    if service is None:
        network_exists = await crud_network.get_network(db, network_id)
        if not network_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found."}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SERVICE_NOT_FOUND",
                        "message": f"Service with id {service_id} not found in network {network_id}."}
            )
    return service


@router.patch(
    "/{service_id}",
    response_model=ServiceInDB,
    summary="Update a Service"
)
async def update_service(
        network_id: str,
        service_id: str,
        payload: ServiceUpdate,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Updates specific fields of a service within a network.
    Only fields provided in the request body will be updated.
    """
    updated_service = await crud_network.update_service_in_network(db, network_id, service_id, payload)
    if updated_service is None:
        network_exists = await crud_network.get_network(db, network_id)
        if not network_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found."}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SERVICE_NOT_FOUND",
                        "message": f"Service with id {service_id} not found in network {network_id}."}
            )
    return updated_service


@router.delete(
    "/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Service"
)
async def delete_service(
        network_id: str,
        service_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Deletes a specific service from a network.
    """
    success = await crud_network.delete_service_from_network(db, network_id, service_id)
    if not success:
        network_exists = await crud_network.get_network(db, network_id)
        if not network_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found."}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SERVICE_NOT_FOUND",
                        "message": f"Service with id {service_id} not found in network {network_id}."}
            )
    return None
