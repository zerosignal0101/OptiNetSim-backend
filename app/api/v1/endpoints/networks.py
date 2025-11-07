from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
import gnpy
from tqdm import tqdm
import numpy as np

from band_defrag.utils.blocking_utils import EVENT_ALLOCATION, EVENT_REALLOCATION, EVENT_RELEASE_EXPIRED

from ....core.database import get_database
from ....crud import crud_network
from ....models.defrag import DefragRequest, DefragResponse, DefragService
from ....models.network import (
    NetworkCreate, NetworkResponse, NetworkListResponse,
    NetworkDetailResponse, NetworkUpdate
)
from ....services.simulation import simulate_service_path_wavelength
from ....utils.minimize import minimize_network
from ....services.defrag import network_defrag

router = APIRouter()


@router.post(
    "",
    response_model=NetworkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Optical Network"
)
async def create_network(
        network_in: NetworkCreate,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Creates a new, empty optical network with a given name.
    """
    db_network = await crud_network.create_network(db, network=network_in)
    return NetworkResponse(
        network_id=str(db_network.id),
        **db_network.model_dump()
    )


@router.get(
    "",
    response_model=NetworkListResponse,
    summary="Get a list of all Optical Networks"
)
async def get_all_networks(
        page: int = Query(1, ge=1, description="Current page number"),
        limit: int = Query(20, ge=1, le=100, description="Items per page"),
        name_contains: Optional[str] = Query(None, description="Filter by network name (case-insensitive)"),
        sort_by: str = Query("created_at", enum=["created_at", "updated_at", "network_name"]),
        order: str = Query("desc", enum=["asc", "desc"]),
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Retrieves a paginated, filterable, and sortable list of all networks.
    """
    networks, total_count = await crud_network.get_all_networks(
        db, page, limit, name_contains, sort_by, order
    )

    response_networks = [
        NetworkResponse(network_id=str(net.id), **net.model_dump())
        for net in networks
    ]

    return NetworkListResponse(
        networks=response_networks,
        total_count=total_count,
        page=page,
        limit=limit
    )


@router.get(
    "/{network_id}",
    response_model=NetworkDetailResponse,
    summary="Get a specific Optical Network by ID"
)
async def get_network(
        network_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Retrieves the full topology and configuration for a specific network.
    """
    db_network = await crud_network.get_network(db, network_id)
    if db_network is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found"}
        )
    return NetworkDetailResponse(
        network_id=str(db_network.id),
        **db_network.model_dump()
    )


@router.get(
    "/{network_id}/minimized",
    response_model=NetworkDetailResponse,
    summary="Get a minimized Optical Network by ID"
)
async def get_minimized_network(
        network_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Retrieves the minimized topology and configuration for a specific network.
    The minimization process:
    1. Removes Transceivers not directly connected to Roadms
    2. Collapses chains of Edfa/Fiber/Fused nodes between Roadms into single edges
       with fiber length as weight
    """
    # 获取原始网络数据
    db_network = await crud_network.get_network(db, network_id)
    if db_network is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found"}
        )

    network_raw, minimized_elements, minimized_connections, network_dict = minimize_network(db_network)

    # 构建响应数据
    response_data = {
        "network_id": str(db_network.id),
        "network_name": db_network.network_name,
        "created_at": db_network.created_at,
        "updated_at": db_network.updated_at,
        "elements": minimized_elements,
        "connections": minimized_connections,
        "services": network_dict['services'],  # 服务保持不变
        "SI": network_dict['SI'],
        "Span": network_dict['Span'],
        "simulation_config": network_dict['simulation_config']
    }
    return NetworkDetailResponse(**response_data)


@router.patch(
    "/{network_id}",
    response_model=NetworkResponse,
    summary="Update an Optical Network's name"
)
async def update_network_name(
        network_id: str,
        payload: NetworkUpdate,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Updates the name of a specific network.
    """
    updated_network = await crud_network.update_network(db, network_id, payload)
    if updated_network is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found"}
        )
    return NetworkResponse(
        network_id=str(updated_network.id),
        **updated_network.model_dump()
    )


@router.delete(
    "/{network_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an Optical Network"
)
async def delete_network(
        network_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Deletes a network and all its associated topology, services, and configurations.
    """
    success = await crud_network.delete_network(db, network_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found"}
        )
    return None


@router.post(
    "/{network_id}/defrag",
    status_code=status.HTTP_200_OK,
    response_model=DefragResponse,
    summary="Defrag an Optical Network"
)
async def defrag_network(
        network_id: str,
        payload: DefragRequest,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Deletes a network and all its associated topology, services, and configurations.
    """
    # 获取原始网络数据
    db_network = await crud_network.get_network(db, network_id)
    if db_network is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found"}
        )

    network_raw, minimized_elements, _minimized_connections, _network_dict = minimize_network(db_network)

    result, defrag_timeline_events = network_defrag(network_raw, payload.avg_arrival_interval, payload.avg_holding_time,
                                                    payload.service_num)

    for timeline_event in tqdm(
                defrag_timeline_events,
                total=len(defrag_timeline_events),
                desc='Event simulation with gnpy',
                leave=True
        ):
        if timeline_event['event_type'] == EVENT_ALLOCATION or timeline_event['event_type'] == EVENT_REALLOCATION:
            service_data_dict = timeline_event['details']

            simulation_source_id = None
            for element in minimized_elements:
                if element['element_id'] == service_data_dict['source_id']:
                    simulation_source_id = element['metadata']['transceiver']['element_id']
                    break

            simulation_destination_id = None
            for element in minimized_elements:
                if element['element_id'] == service_data_dict['destination_id']:
                    simulation_destination_id = element['metadata']['transceiver']['element_id']
                    break

            if simulation_source_id and simulation_destination_id:
                path, propagations_for_path, powers_dbm, infos = simulate_service_path_wavelength(
                    db_network,
                    simulation_source_id,
                    simulation_destination_id,
                    service_data_dict['path'],
                    service_data_dict['wavelength'],
                    service_data_dict['power']
                )

                from gnpy.core.elements import Transceiver, Fiber, RamanFiber, Roadm, Edfa
                from gnpy.core.utils import per_label_average
                last_transceiver = path[-1]
                last_gsnr = 0.0
                if isinstance(last_transceiver, Transceiver):
                    last_gsnr = list(per_label_average(
                        last_transceiver.snr,
                        last_transceiver.propagated_labels
                    ).values())[0]
                    service_data_dict['gsnr'] = last_gsnr
                if last_gsnr >= 26.5 - 1:
                    capacity = 800
                elif last_gsnr >= 25.0 - 1:
                    capacity = 700
                elif last_gsnr >= 23.5 - 1:
                    capacity = 600
                elif last_gsnr >= 21.0 - 1:
                    capacity = 500
                elif last_gsnr >= 18.7 - 1:
                    capacity = 400
                elif last_gsnr >= 15:
                    capacity = 200
                else:
                    capacity = 1e-6
                utilization = service_data_dict['bit_rate_requirement'] / capacity
                if utilization > 1.0:
                    utilization = 1.0
                service_data_dict['utilization'] = utilization
            else:
                print('[WARN] Can not simulate with None element id.')

            # 3. 将创建好的 Pydantic 模型添加到响应列表中
            timeline_event['details'] = service_data_dict

    response = DefragResponse(result=result, defrag_timeline_events=defrag_timeline_events)

    return response
