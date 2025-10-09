import networkx as nx
from collections import defaultdict
import uuid6

from app.models.network import NetworkInDB


def minimize_network(db_network: NetworkInDB):
    network_dict = db_network.model_dump()

    # 预处理：建立 element_id 到 element 的映射字典
    element_dict = {el['element_id']: el for el in network_dict['elements']}

    # 预处理：建立邻接关系映射
    adjacency_map = defaultdict(list)
    for conn in network_dict['connections']:
        adjacency_map[conn['from_node']].append(conn['to_node'])
    # 构建图
    network_raw = nx.DiGraph()
    for el in network_dict['elements']:
        network_raw.add_node(
            el['element_id'],
            x=el['metadata'].get('location', {}).get('x', 0),
            y=el['metadata'].get('location', {}).get('y', 0)
        )
    for conn in network_dict['connections']:
        network_raw.add_edge(conn['from_node'], conn['to_node'])
    # 批量处理节点
    nodes_to_remove = set()
    edges_to_add = []  # 存储 (from, to, weight) 元组
    # 1. 处理 Transceiver 节点
    for element_id in list(element_dict.keys()):
        if element_id not in network_raw:
            continue

        element_data = element_dict[element_id]
        if element_data['type'] == 'Transceiver':
            for next_node in list(network_raw.successors(element_id)):
                next_node_data = element_dict[next_node]
                next_node_type = next_node_data['type']
                if next_node_type == 'Roadm':
                    next_node_data['metadata']['transceiver'] = {}
                    next_node_data['metadata']['transceiver']['element_id'] = next_node
                    next_node_data['metadata']['transceiver']['name'] = next_node_data['name']
            nodes_to_remove.add(element_id)
    # 2. 处理 Roadm 节点
    for element_id in list(element_dict.keys()):
        if element_id not in network_raw or element_dict[element_id]['type'] != 'Roadm':
            continue

        # 处理每个出边
        for next_node in list(network_raw.successors(element_id)):
            if next_node in nodes_to_remove:
                continue

            current_node = next_node
            fiber_total_length = 0
            path_nodes = []

            # 沿路径遍历直到遇到 Roadm 或 Transceiver
            while current_node in element_dict:
                node_data = element_dict[current_node]
                node_type = node_data['type']

                # 遇到终止节点
                if node_type in ('Roadm', 'Transceiver'):
                    break

                # 处理中间节点
                if node_type in ('Edfa', 'Fiber', 'Fused'):
                    path_nodes.append(current_node)
                    if node_type == 'Fiber':
                        fiber_total_length += node_data['params'].get('length', 0)

                    # 获取下一个节点
                    next_nodes = adjacency_map.get(current_node, [])
                    if not next_nodes:
                        break
                    current_node = next_nodes[0]
                else:
                    break

            # 添加合并边
            if (path_nodes and
                    element_dict.get(current_node, {}).get('type') == 'Roadm' and
                    fiber_total_length > 0):
                edges_to_add.append((element_id, current_node, fiber_total_length))
                nodes_to_remove.update(path_nodes)
    # 批量执行图操作
    network_raw.remove_nodes_from(nodes_to_remove)
    for u, v, weight in edges_to_add:
        network_raw.add_edge(u, v, weight=weight)

    # 构建最小化后的网络数据
    minimized_elements = [
        el for el in network_dict['elements']
        if el['element_id'] not in nodes_to_remove
    ]

    minimized_connections = []
    for u, v, data in network_raw.edges(data=True):
        conn = {
            "from_node": u,
            "to_node": v,
            "connection_id": str(uuid6.uuid6())  # 生成新的连接ID
        }
        if 'weight' in data:
            conn['weight'] = data['weight']  # 添加光纤长度作为权重
        minimized_connections.append(conn)

    return network_raw, minimized_elements, minimized_connections, network_dict