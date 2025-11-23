import networkx as nx
import numpy as np
import random
import sys

import torch
import pathlib
import os

from band_defrag.network_loader.multiband_optical_network_env import MultibandOpticalNetworkEnv
from band_defrag.mat_algorithm.model.mat_policy import TransformerPolicy
from band_defrag.utils.config_utils import load_config_from_yaml
from band_defrag.utils.network_utils import read_graphml_as_topology, new_service_dict
from band_defrag.utils.blocking_utils import blocking_test, allocate_ksp_only
from band_defrag.utils.network_utils import process_topology

max_agent = 30


def network_ksp_only(
        network_minimized: nx.DiGraph,
        avg_arrival_interval: float,
        avg_holding_time: float,
        service_arrival_time_max: float
):
    topology, __ = process_topology(network_minimized)

    services = new_service_dict(topology, avg_arrival_interval, avg_holding_time, service_arrival_time_max)
    service_dict_list = []
    for service in services.values():
        service_dict_list.append(service.to_dict())

    result, defrag_timeline_events = allocate_ksp_only(topology, services)

    return result, service_dict_list, defrag_timeline_events


def network_defrag(
        network_minimized: nx.DiGraph,
        avg_arrival_interval: float,
        avg_holding_time: float,
        service_arrival_time_max: float
):
    topology, __ = process_topology(network_minimized)

    config_path = os.fspath(pathlib.Path(__file__).parent.parent / 'utils' / 'defrag_config.yaml')
    all_args = load_config_from_yaml(config_path)

    dummy_env = MultibandOpticalNetworkEnv(None, None, {}, max_agent, None)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Using device: ", device)
    policy = TransformerPolicy(all_args, dummy_env.observation_space[0], dummy_env.action_space[0],
                               device=torch.device(device))
    policy.restore(pathlib.Path(__file__).parent.parent / all_args.model_dir)

    services = new_service_dict(topology, avg_arrival_interval, avg_holding_time, service_arrival_time_max)
    result, defrag_timeline_events = blocking_test(topology, services, max_agent, policy)

    return result, defrag_timeline_events
