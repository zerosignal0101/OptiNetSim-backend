# app/api/v1/endpoints/services.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
import networkx as nx

from ....core.auth import get_current_active_user
from ....core.database import get_database
from ....crud import crud_network
from ....models.network import ServiceCreate, ServiceInDB, ServiceUpdate
from ....utils.minimize import minimize_network
from ....models.simulation import SingleLinkSimulationResponse, SimulationTransceiverResult
from ....services.simulation import single_link_simulate

router = APIRouter()


@router.get(
    "",
    response_model=List[ServiceInDB],
    summary="List Services for a Network"
)
async def list_services(
        network_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: str = Depends(get_current_active_user)
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
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: str = Depends(get_current_active_user)
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

    network_raw, minimized_elements, __, ___ = minimize_network(db_network)
    element_dict = {el['element_id']: el for el in minimized_elements}
    service_in.path = nx.shortest_path(network_raw, service_in.source_id, service_in.destination_id, 'weight')
    service_in.source_id = element_dict[service_in.source_id]['metadata']['transceiver']['element_id']
    service_in.destination_id = element_dict[service_in.destination_id]['metadata']['transceiver']['element_id']

    print(service_in.path)
    print(service_in.source_id)
    print(service_in.destination_id)

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
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: str = Depends(get_current_active_user)
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
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: str = Depends(get_current_active_user)
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
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: str = Depends(get_current_active_user)
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

@router.get(
    "/{service_id}/single-link",
    summary="Single Link Simulation"
)
async def single_link(
        network_id: str,
        service_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: str = Depends(get_current_active_user)
):
    """
    Single link Simulation
    """
    db_network = await crud_network.get_network(db, network_id)
    if db_network is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND",
                    "message": f"Network with id {network_id} not found."}
        )

    service = await crud_network.get_service_from_network(db, network_id, service_id)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SERVICE_NOT_FOUND",
                    "message": f"Service with id {service_id} not found in network {network_id}."}
        )

    path, propagations_for_path, powers_dbm, infos = single_link_simulate(db_network, service)

    response = SingleLinkSimulationResponse(snr_results=[])
    from gnpy.core.utils import per_label_average
    from gnpy.core.elements import Transceiver, Fiber, RamanFiber, Roadm, Edfa
    for element in path:
        if type(element) is Transceiver:
            response.snr_results.append(SimulationTransceiverResult(
                element_id=element.uid,
                snr_01nm=list(per_label_average(element.snr_01nm, element.propagated_labels).values())[0],
                snr=list(per_label_average(element.snr, element.propagated_labels).values())[0],
                osnr_ase_01nm=list(per_label_average(element.osnr_ase_01nm, element.propagated_labels).values())[0],
                osnr_ase=list(per_label_average(element.osnr_ase, element.propagated_labels).values())[0],
            ))

    return response
