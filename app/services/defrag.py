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
from band_defrag.utils.blocking_utils import blocking_test
from band_defrag.utils.network_utils import process_topology

max_agent = 30


def network_defrag(network_minimized: nx.DiGraph, erlang: float, service_num: int):

    topology, __ = process_topology(network_minimized)

    config_path = os.fspath(pathlib.Path(__file__).parent.parent / 'utils' / 'defrag_config.yaml')
    all_args = load_config_from_yaml(config_path)

    dummy_env = MultibandOpticalNetworkEnv(None, None, {}, max_agent, None)
    policy = TransformerPolicy(all_args, dummy_env.observation_space[0], dummy_env.action_space[0],
                               device=torch.device("cpu"))
    policy.restore(pathlib.Path(__file__).parent.parent / all_args.model_dir)

    services = new_service_dict(topology, erlang, service_num)
    result, service_dict = blocking_test(topology, services, max_agent, policy)

    return result, service_dict
