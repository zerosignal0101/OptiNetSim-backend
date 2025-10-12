from pathlib import Path
from typing import Union, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
import numpy as np

from gnpy.tools.json_io import network_from_json, load_equipment
from gnpy.core.elements import Transceiver, Fiber, RamanFiber, Roadm, Edfa
import gnpy.core.ansi_escapes as ansi_escapes
from gnpy.core.utils import automatic_nch, watt2dbm, dbm2watt, pretty_summary_print, per_label_average
import gnpy.core.exceptions as exceptions
from gnpy.core.utils import lin2db, pretty_summary_print, per_label_average, watt2dbm
from gnpy.tools.worker_utils import designed_network, transmission_simulation, planning

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
