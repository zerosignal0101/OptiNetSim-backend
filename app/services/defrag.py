import networkx as nx
import numpy as np
import random
import sys

import torch
import pathlib
import os

from band_defrag.environments.multiband_optical_network_env import MultibandOpticalNetworkEnv
from band_defrag.mat_algorithm.model.mat_policy import TransformerPolicy
from band_defrag.utils.config_utils import load_config_from_yaml
from band_defrag.network_sim.network_state import prepare_network_state
from band_defrag.network_sim.service_generator import generate_services
from band_defrag.utils.blocking_utils import blocking_test

max_agent = 30


def network_defrag(network_minimized: nx.DiGraph, avg_arrival_interval: float, avg_holding_time: float, service_num: float):

    config_path = os.fspath(pathlib.Path(__file__).parent.parent / 'utils' / 'defrag_config.yaml')
    all_args = load_config_from_yaml(config_path)

    dummy_env = MultibandOpticalNetworkEnv(max_agent, None, None, None, None, None, None, True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Using device: ", device)
    policy = TransformerPolicy(all_args, dummy_env.observation_space[0], dummy_env.action_space[0],
                               device=torch.device(device))
    policy.restore(pathlib.Path(__file__).parent.parent / all_args.model_dir)
    
    (allocation_status, allocated_service_idx,
     edge_distances, ksp_cache, allocated_service_dict,
     idx_to_node_id, node_id_to_idx) = prepare_network_state(network_minimized)

    services = generate_services(ksp_cache, service_num, avg_arrival_interval, avg_holding_time)
    result, defrag_timeline_events = blocking_test(network_minimized, services, max_agent, policy)

    return result, defrag_timeline_events
