from pathlib import Path
from typing import Union, Dict, List, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
import numpy as np
import asyncio

from gnpy.tools.json_io import network_from_json, load_equipment
from gnpy.core.elements import Transceiver, Fiber, RamanFiber, Roadm, Edfa
import gnpy.core.ansi_escapes as ansi_escapes
from gnpy.core.utils import automatic_nch, watt2dbm, dbm2watt, pretty_summary_print, per_label_average
import gnpy.core.exceptions as exceptions
from gnpy.core.utils import lin2db, pretty_summary_print, per_label_average, watt2dbm
from gnpy.tools.worker_utils import designed_network, transmission_simulation, planning
from gnpy.topology.request import PathRequest

from app.models.network import NetworkInDB, ServiceInDB


def single_link_simulate(db_network: NetworkInDB, service: ServiceInDB):
    equipment = load_equipment(Path(__file__).parent.parent / 'utils' / 'eqpt_config_openroadm_ver5.json')

    network_dict = db_network.model_dump()

    for element in network_dict['elements']:
        # 将 element_id 键名替换为 uid
        element['uid'] = element.pop('element_id')

        # 移除 name 键值对
        element.pop('name', None)
        element.pop('metadata', None)

    # 遍历 connections 列表中的每个元素
    for connection in network_dict['connections']:
        # 移除 connection_id 键值对
        connection.pop('connection_id', None)

    sim_params = network_dict['simulation_config'].copy()
    network = network_from_json(network_dict, equipment)

    transceivers = {n.uid: n for n in network.nodes() if isinstance(n, Transceiver)}
    if not transceivers:
        return '网络中未找到收发器'
    if len(transceivers) < 2:
        return '至少需要两个收发器才能进行网络仿真'

    source = transceivers.pop(service.source_id, None)
    destination = transceivers.pop(service.destination_id, None)

    nodes_list = service.path
    nodes_list.append(service.destination_id)
    loose_list = ['STRICT']

    if not source:
        source = list(transceivers.values())[0]
        del transceivers[source.uid]
        print('No source node specified: picking random transceiver')

    if not destination:
        destination = list(transceivers.values())[0]
        nodes_list = [destination.uid]
        loose_list = ['STRICT']
        print('No destination node specified: picking random transceiver')

    initial_spectrum = None
    # print(nodes_list, loose_list)
    network, req, ref_req = designed_network(equipment, network, source.uid, destination.uid,
                                             nodes_list=nodes_list, loose_list=loose_list,
                                             initial_spectrum=initial_spectrum)
    path, propagations_for_path, powers_dbm, infos = transmission_simulation(equipment, network, req, ref_req)

    return path, propagations_for_path, powers_dbm, infos


def simulate_service_path_wavelength(
        db_network: NetworkInDB,
        source_id: str, destination_id: str,
        path: List[str], wavelength: int, power: float
):
    equipment = load_equipment(Path(__file__).parent.parent / 'utils' / 'eqpt_config_openroadm_ver5.json')

    network_dict = db_network.model_dump()

    for element in network_dict['elements']:
        # 将 element_id 键名替换为 uid
        element['uid'] = element.pop('element_id')

        # 移除 name 键值对
        element.pop('name', None)
        element.pop('metadata', None)

    # 遍历 connections 列表中的每个元素
    for connection in network_dict['connections']:
        # 移除 connection_id 键值对
        connection.pop('connection_id', None)

    sim_params = network_dict['simulation_config'].copy()
    network = network_from_json(network_dict, equipment)

    transceivers = {n.uid: n for n in network.nodes() if isinstance(n, Transceiver)}
    if not transceivers:
        return '网络中未找到收发器'
    if len(transceivers) < 2:
        return '至少需要两个收发器才能进行网络仿真'

    source = transceivers.pop(source_id, None)
    destination = transceivers.pop(destination_id, None)

    nodes_list = path
    nodes_list.append(destination_id)
    loose_list = ['STRICT']

    if not source:
        source = list(transceivers.values())[0]
        del transceivers[source.uid]
        print('No source node specified: picking random transceiver')

    if not destination:
        destination = list(transceivers.values())[0]
        nodes_list = [destination.uid]
        loose_list = ['STRICT']
        print('No destination node specified: picking random transceiver')

    # 示例：指定两个载波块 (N, M)
    # 第一个块: 中心频率索引 0, 占用 8 个槽
    # 第二个块: 中心频率索引 16, 占用 8 个槽
    service_effective_freq_slot = [
        {'N': wavelength, 'M': 1}
    ]

    # 收发器参数（从 equipment 中选择一个存在的类型和模式）
    default_trx_type = 'OpenROADM MSA ver. 5.0'
    default_trx_mode = equipment['Transceiver'][default_trx_type].mode[0]['format']  # 示例，使用第一个模式

    # 从设备的默认模式中获取必要的参数，用于构建 PathRequest
    # 注意：effective_freq_slot 优先级最高，但其他参数如 spacing, baud_rate, bit_rate 等仍需正确，
    #      尤其是在 PathRequest 内部进行一致性校验时。
    try:
        trx_mode_info = equipment['Transceiver'][default_trx_type].mode[0]
    except IndexError:
        print(f"收发器类型 '{default_trx_type}' 没有定义任何模式。")
        exit(1)

    # service_power_dbm = 0  # dBm
    # service_power_watt = dbm2watt(service_power_dbm)
    # service_tx_power_dbm = 0  # dBm
    # service_tx_power_watt = dbm2watt(service_tx_power_dbm)

    service_power_watt = power
    service_tx_power_watt = power

    service_req = PathRequest(
        request_id='custom_req_001',
        source=source_id,
        destination=destination_id,
        bidir=False,  # 可以设置为 True
        trx_type=default_trx_type,
        trx_mode=default_trx_mode,
        nodes_list=nodes_list,
        loose_list=loose_list,
        spacing=trx_mode_info['min_spacing'],  # 使用兼容的 spacing
        power=service_power_watt,  # 参考通道功率
        nb_channel=None,  # 精确指定载波后，此项可为 None
        f_min=equipment['SI']['default'].f_min,  # 仍需提供，用于校验
        f_max=equipment['SI']['default'].f_max,  # 仍需提供，用于校验
        format=default_trx_mode,
        baud_rate=trx_mode_info['baud_rate'],
        OSNR=trx_mode_info['OSNR'],
        penalties=trx_mode_info['penalties'],
        bit_rate=trx_mode_info['bit_rate'],
        roll_off=trx_mode_info['roll_off'],
        tx_osnr=trx_mode_info['tx_osnr'],
        tx_power=service_tx_power_watt,  # 发送端功率
        min_spacing=trx_mode_info['min_spacing'],
        cost=trx_mode_info['cost'],
        # path_bandwidth 应该与 effective_freq_slot 定义的通道总速率匹配
        path_bandwidth=trx_mode_info['bit_rate'] * len(service_effective_freq_slot),
        effective_freq_slot=service_effective_freq_slot,  # <<<< 指定载波编号的关键！
        equalization_offset_db=trx_mode_info['equalization_offset_db']
    )

    network, req, ref_req = designed_network(equipment, network, service_req=service_req, no_insert_edfas=False)
    path, propagations_for_path, powers_dbm, infos = transmission_simulation(equipment, network, req, ref_req)

    return path, propagations_for_path, powers_dbm, infos


async def run_simulation_in_executor(
        db_network: NetworkInDB,
        simulation_source_id: str,
        simulation_destination_id: str,
        service_data_dict: Dict[str, Any]
) -> float | None:
    """
    一个异步的包装函数，它在线程池中运行同步的、阻塞的仿真函数。
    """
    try:
        loop = asyncio.get_running_loop()
        # loop.run_in_executor 会在默认的线程池执行器中运行同步函数，
        # 并返回一个可以 await 的 future 对象。
        path, _propagations, _powers, _infos = await loop.run_in_executor(
            None,  # 使用默认的 ThreadPoolExecutor
            simulate_service_path_wavelength,
            db_network,
            simulation_source_id,
            simulation_destination_id,
            service_data_dict['path'],
            service_data_dict['wavelength'],
            service_data_dict['power']
        )

        # 注意：这里的 gnpy 相关代码也是同步的，所以放在这里是安全的
        last_transceiver = path[-1]
        if isinstance(last_transceiver, Transceiver):
            # 假设 per_label_average 返回一个字典
            avg_snr = per_label_average(last_transceiver.snr, last_transceiver.propagated_labels)
            return list(avg_snr.values())[0] if avg_snr else None

        return None

    except Exception as e:
        print(f"[ERROR] Simulation failed for service {service_data_dict.get('id', 'N/A')}: {e}")
        return None
