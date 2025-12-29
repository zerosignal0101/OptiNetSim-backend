from typing import List, Optional

import networkx as nx
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
import gnpy
from tqdm import tqdm

from band_defrag.utils.blocking_utils import EVENT_ALLOCATION, EVENT_REALLOCATION, EVENT_RELEASE_EXPIRED

from ....core.database import get_database
from ....core.auth import get_current_active_user
from ....crud import crud_network
from ....models.defrag import DefragRequest, DefragResponse, DefragService
from ....models.user import TokenData
from ....models.network import (
    NetworkCreate, NetworkResponse, NetworkListResponse,
    NetworkDetailResponse, NetworkUpdate, ServiceInDB
)
from ....models.simulation import SingleLinkSimulationResponse, SNRResult, SingleLinkSimulationRequest, PowerResult
from ....services.simulation import simulate_service_path_wavelength, single_link_simulate
from ....utils.minimize import minimize_network
from ....services.defrag import network_defrag, network_ksp_only

router = APIRouter()


@router.post(
    "",
    response_model=NetworkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Optical Network"
)
async def create_network(
        network_in: NetworkCreate,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Creates a new, empty optical network with a given name.
    """
    db_network = await crud_network.create_network(db, network=network_in, user_id=current_user.username)
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
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Retrieves a paginated, filterable, and sortable list of all networks.
    """
    networks, total_count = await crud_network.get_all_networks(
        db, current_user.username, page, limit, name_contains, sort_by, order
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
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Retrieves the full topology and configuration for a specific network.
    """
    db_network = await crud_network.get_network(db, network_id, current_user.username)
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
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Retrieves the minimized topology and configuration for a specific network.
    The minimization process:
    1. Removes Transceivers not directly connected to Roadms
    2. Collapses chains of Edfa/Fiber/Fused nodes between Roadms into single edges
       with fiber length as weight
    """
    # 获取原始网络数据
    db_network = await crud_network.get_network(db, network_id, current_user.username)
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
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Updates the name of a specific network.
    """
    updated_network = await crud_network.update_network(db, network_id, payload, current_user.username)
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
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Deletes a network and all its associated topology, services, and configurations.
    """
    success = await crud_network.delete_network(db, network_id, current_user.username)
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
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Deletes a network and all its associated topology, services, and configurations.
    """
    # 获取原始网络数据
    db_network = await crud_network.get_network(db, network_id, current_user.username)
    if db_network is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found"}
        )

    network_raw, minimized_elements, _minimized_connections, _network_dict = minimize_network(db_network)

    result, defrag_timeline_events = network_defrag(network_raw, payload.avg_arrival_interval, payload.avg_holding_time,
                                                    payload.service_arrival_time_max)

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
                if isinstance(last_transceiver, Transceiver):
                    service_data_dict['gsnr'] = list(per_label_average(
                        last_transceiver.snr,
                        last_transceiver.propagated_labels
                    ).values())[0]
            else:
                print('[WARN] Can not simulate with None element id.')

            # 3. 将创建好的 Pydantic 模型添加到响应列表中
            timeline_event['details'] = service_data_dict

    response = DefragResponse(result=result, defrag_timeline_events=defrag_timeline_events)

    return response


@router.post(
    "/{network_id}/ksp_only",
    status_code=status.HTTP_200_OK,
    response_model=DefragResponse,
    summary="Allocate service on an Optical Network"
)
async def ksp_only(
        network_id: str,
        payload: DefragRequest,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Deletes a network and all its associated topology, services, and configurations.
    """
    # 获取原始网络数据
    db_network = await crud_network.get_network(db, network_id, current_user.username)
    if db_network is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found"}
        )

    network_raw, minimized_elements, _minimized_connections, _network_dict = minimize_network(db_network)

    result, service_dict_list, defrag_timeline_events = network_ksp_only(network_raw, payload.avg_arrival_interval,
                                                                       payload.avg_holding_time,
                                                                       payload.service_arrival_time_max)

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
                if isinstance(last_transceiver, Transceiver):
                    service_data_dict['gsnr'] = list(per_label_average(
                        last_transceiver.snr,
                        last_transceiver.propagated_labels
                    ).values())[0]
            else:
                print('[WARN] Can not simulate with None element id.')

            # 3. 将创建好的 Pydantic 模型添加到响应列表中
            timeline_event['details'] = service_data_dict

    response = DefragResponse(result=result, defrag_timeline_events=defrag_timeline_events)

    return response


@router.post(
    "/{network_id}/single-link",
    status_code=status.HTTP_200_OK,
    summary="Single Link Simulation"
)
async def single_link(
        network_id: str,
        payload: SingleLinkSimulationRequest,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Single link Simulation
    """
    db_network = await crud_network.get_network(db, network_id, current_user.username)
    if db_network is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND",
                    "message": f"Network with id {network_id} not found."}
        )

    network_raw, minimized_elements, _minimized_connections, _network_dict = minimize_network(db_network)

    minimized_element_dict = {}
    for element in minimized_elements:
        element_id = element['element_id']
        minimized_element_dict[element_id] = element

    source_id = minimized_element_dict[payload.source_id]['metadata']['transceiver']['element_id']
    destination_id = minimized_element_dict[payload.destination_id]['metadata']['transceiver']['element_id']

    shortest_path = nx.shortest_path(network_raw, payload.source_id, payload.destination_id)

    service = ServiceInDB(
        name='Simulation',
        service_id='test',
        source_id=source_id,
        destination_id=destination_id,
        path=shortest_path
    )

    path, propagations_for_path, powers_dbm, infos = single_link_simulate(db_network, service)

    response = SingleLinkSimulationResponse(path=shortest_path, snr_results=[], power_results=[], full_result={})
    from gnpy.core.utils import per_label_average
    from gnpy.core.elements import Transceiver, Fiber, RamanFiber, Roadm, Edfa
    for element in path:
        if type(element) is Transceiver:
            response.snr_results.append(SNRResult(
                element_id=element.uid,
                snr_01nm=list(per_label_average(element.snr_01nm, element.propagated_labels).values())[0],
                snr=list(per_label_average(element.snr, element.propagated_labels).values())[0],
                osnr_ase_01nm=list(per_label_average(element.osnr_ase_01nm, element.propagated_labels).values())[0],
                osnr_ase=list(per_label_average(element.osnr_ase, element.propagated_labels).values())[0],
            ))
        elif type(element) is Fiber or type(element) is Edfa or type(element) is RamanFiber or type(element) is Roadm:
            response.power_results.append(PowerResult(
                element_id=element.uid,
                pch_out_dbm=list(per_label_average(element.pch_out_dbm, element.propagated_labels).values())[0],
            ))

    element_id_name = {}
    for element in db_network.elements:
        element_id = element.element_id
        element_id_name[element_id] = element.name

    path_elements = []
    for element in path:
        element_id = element.uid
        element_name = element_id_name[element_id]
        replaced_str = str(element).replace(element.uid, element_name or element.uid)

        # 解析字符串为字典
        element_dict = {}
        lines = replaced_str.split('\n')

        if lines:
            # 处理第一行元素描述
            element_dict["element"] = lines[0].strip()

            # 处理后续属性行
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue

                # 分割键值对
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    # 尝试转换为数值类型
                    try:
                        value = float(value) if '.' in value else int(value)
                    except ValueError:
                        pass  # 保持字符串类型

                    element_dict[key] = value

        path_elements.append(element_dict)

    channel_data = []
    from gnpy.core.utils import lin2db, db2lin
    for final_carrier, ch_osnr, ch_snr_nl, ch_snr in zip(
            infos.carriers, path[-1].osnr_ase, path[-1].osnr_nli, path[-1].snr):
        ch_freq = final_carrier.frequency * 1e-12
        ch_power = lin2db(final_carrier.power.signal * 1e3)
        channel_info = {  # 创建一个字典来存储单个通道的信息
            'channel_number': final_carrier.channel_number,
            'channel_frequency': round(ch_freq, 5),
            'channel_power': round(ch_power, 2),
            'OSNR_ASE': round(ch_osnr, 2),
            'SNR_NLI': round(ch_snr_nl, 2),
            'GSNR': round(ch_snr, 2)
        }
        channel_data.append(channel_info)  # 将通道信息添加到列表中

    response.full_result = {
        'path': path_elements,
        'channels': channel_data,
    }

    return response
