# app/crud/crud_network.py

from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError  # 导入 ValidationError
from uuid6 import uuid6

from ..models.network import (
    NetworkCreate, NetworkInDB, NetworkUpdate, ElementCreate, ElementInDB,
    ElementUpdate, ConnectionCreate, ConnectionInDB, ServiceCreate, ServiceInDB, ServiceUpdate,
    NetworkImport, SubTopologyImport,
    SIConfig, SpanConfig, SimulationConfig  # 导入全局配置模型
)

COLLECTION = "networks"


# --- Network CRUD ---

async def create_network(db: AsyncIOMotorDatabase, network: NetworkCreate, user_id: str) -> NetworkInDB:
    network_data = network.model_dump()
    now = datetime.utcnow()
    db_network = NetworkInDB(**network_data, user_id=user_id, created_at=now, updated_at=now)

    # Using model_dump(by_alias=True) to respect the '_id' alias
    await db[COLLECTION].insert_one(db_network.model_dump(by_alias=True))
    return db_network


async def get_network(db: AsyncIOMotorDatabase, network_id: str, user_id: str) -> Optional[NetworkInDB]:
    if not ObjectId.is_valid(network_id):
        return None
    doc = await db[COLLECTION].find_one({
        "_id": ObjectId(network_id),
        "user_id": user_id  # User isolation filter
    })
    return NetworkInDB(**doc) if doc else None


async def get_all_networks(
        db: AsyncIOMotorDatabase,
        user_id: str,  # Add user context
        page: int,
        limit: int,
        name_contains: Optional[str],
        sort_by: str,
        order: str
) -> Tuple[List[NetworkInDB], int]:  # 修改返回类型提示
    query = {"user_id": user_id}  # User isolation filter
    if name_contains:
        query["network_name"] = {"$regex": name_contains, "$options": "i"}

    total_count = await db[COLLECTION].count_documents(query)

    sort_order = 1 if order == "asc" else -1
    # 修正排序字段：当 sort_by 为 network_name 时，直接用 network_name，否则用创建或更新时间
    effective_sort_by = "network_name" if sort_by == "network_name" else sort_by
    cursor = db[COLLECTION].find(query).sort(effective_sort_by, sort_order).skip((page - 1) * limit).limit(limit)

    networks = [NetworkInDB(**doc) async for doc in cursor]
    return networks, total_count


async def update_network(db: AsyncIOMotorDatabase, network_id: str, payload: NetworkUpdate, user_id: str) -> Optional[NetworkInDB]:
    if not ObjectId.is_valid(network_id):
        return None

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:  # 如果没有提供更新数据，则无需操作
        return await get_network(db, network_id, user_id)

    update_data["updated_at"] = datetime.utcnow()

    result = await db[COLLECTION].find_one_and_update(
        {
            "_id": ObjectId(network_id),
            "user_id": user_id  # User isolation filter
        },
        {"$set": update_data},
        return_document=True,  # 返回更新后的文档
        upsert=False  # 不创建新文档
    )
    return NetworkInDB(**result) if result else None


async def delete_network(db: AsyncIOMotorDatabase, network_id: str, user_id: str) -> bool:
    if not ObjectId.is_valid(network_id):
        return False
    result = await db[COLLECTION].delete_one({
        "_id": ObjectId(network_id),
        "user_id": user_id  # User isolation filter
    })
    return result.deleted_count > 0


# --- Topology Element (Node) CRUD ---

async def get_element_from_network(db: AsyncIOMotorDatabase, network_id: str, element_id: str, user_id: str) -> Optional[ElementInDB]:
    network = await get_network(db, network_id, user_id)
    if not network:
        return None
    for element in network.elements:
        if element.element_id == element_id:
            return element
    return None


async def add_element_to_network(db: AsyncIOMotorDatabase, network_id: str, element: ElementCreate, user_id: str) \
        -> Optional[ElementInDB]:
    if not ObjectId.is_valid(network_id):
        return None

    new_element = ElementInDB(**element.model_dump(exclude_unset=True, exclude={"element_id"}))  # 生成新的 element_id
    result = await db[COLLECTION].update_one(
        {"_id": ObjectId(network_id), "user_id": user_id},
        {
            "$push": {"elements": new_element.model_dump()},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    return new_element if result.modified_count > 0 else None


async def update_element_in_network(db: AsyncIOMotorDatabase, network_id: str, element_id: str,
                                    payload: ElementUpdate, user_id: str) -> Optional[ElementInDB]:
    if not ObjectId.is_valid(network_id):
        return None

    network = await get_network(db, network_id, user_id)
    if not network:
        return None

    # Check if element exists in the network
    if not any(el.element_id == element_id for el in network.elements):
        return None  # Element not found within the specified network

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        # If payload is empty, just fetch the existing element
        return next((el for el in network.elements if el.element_id == element_id), None)

    # Construct the update query for specific fields within the embedded element
    set_fields = {f"elements.$.{key}": value for key, value in update_data.items()}
    set_fields["updated_at"] = datetime.utcnow()  # Update network's updated_at timestamp

    result = await db[COLLECTION].update_one(
        {"_id": ObjectId(network_id), "user_id": user_id, "elements.element_id": element_id},
        {"$set": set_fields}
    )
    if result.modified_count > 0:
        # Fetch the updated network to return the specific element
        updated_network = await get_network(db, network_id, user_id)
        return next((el for el in updated_network.elements if el.element_id == element_id), None)
    return None


async def delete_element_from_network(db: AsyncIOMotorDatabase, network_id: str, element_id: str, user_id: str) -> bool:
    if not ObjectId.is_valid(network_id):
        return False
    result = await db[COLLECTION].update_one(
        {"_id": ObjectId(network_id), "user_id": user_id},
        {
            "$pull": {
                "elements": {"element_id": element_id},
                "connections": {
                    "$or": [
                        {"from_node": element_id},
                        {"to_node": element_id}
                    ]
                }
            },
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    return result.modified_count > 0


# --- Topology Connection CRUD ---

async def get_connection_from_network(db: AsyncIOMotorDatabase, network_id: str, connection_id: str, user_id: str) -> Optional[
    ConnectionInDB]:
    network = await get_network(db, network_id, user_id)
    if not network:
        return None
    for connection in network.connections:
        if connection.connection_id == connection_id:
            return connection
    return None


async def add_connection_to_network(db: AsyncIOMotorDatabase, network_id: str, connection: ConnectionCreate, user_id: str) -> \
        Optional[ConnectionInDB]:
    if not ObjectId.is_valid(network_id):
        return None

    new_connection = ConnectionInDB(**connection.model_dump())
    result = await db[COLLECTION].update_one(
        {"_id": ObjectId(network_id), "user_id": user_id},
        {
            "$push": {"connections": new_connection.model_dump()},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    return new_connection if result.modified_count > 0 else None


async def delete_connection_from_network(db: AsyncIOMotorDatabase, network_id: str, connection_id: str, user_id: str) -> bool:
    if not ObjectId.is_valid(network_id):
        return False
    result = await db[COLLECTION].update_one(
        {"_id": ObjectId(network_id), "user_id": user_id},
        {
            "$pull": {"connections": {"connection_id": connection_id}},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    return result.modified_count > 0


# --- Service CRUD ---

async def get_all_services_in_network(db: AsyncIOMotorDatabase, network_id: str, user_id: str) -> Optional[List[ServiceInDB]]:
    network = await get_network(db, network_id, user_id)
    if not network:
        return None
    return network.services


async def get_service_from_network(db: AsyncIOMotorDatabase, network_id: str, service_id: str, user_id: str) -> Optional[ServiceInDB]:
    network = await get_network(db, network_id, user_id)
    if not network:
        return None
    for service in network.services:
        if service.service_id == service_id:
            return service
    return None


async def add_service_to_network(db: AsyncIOMotorDatabase, network_id: str, service: ServiceCreate, user_id: str) -> Optional[
    ServiceInDB]:
    if not ObjectId.is_valid(network_id):
        return None

    new_service = ServiceInDB(**service.model_dump())
    result = await db[COLLECTION].update_one(
        {"_id": ObjectId(network_id), "user_id": user_id},
        {
            "$push": {"services": new_service.model_dump()},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    return new_service if result.modified_count > 0 else None


async def update_service_in_network(db: AsyncIOMotorDatabase, network_id: str, service_id: str,
                                    payload: ServiceUpdate, user_id: str) -> Optional[ServiceInDB]:
    if not ObjectId.is_valid(network_id):
        return None

    network = await get_network(db, network_id, user_id)
    if not network:
        return None

    if not any(s.service_id == service_id for s in network.services):
        return None  # Service not found

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return next((s for s in network.services if s.service_id == service_id), None)

    set_fields = {f"services.$.{key}": value for key, value in update_data.items()}
    set_fields["updated_at"] = datetime.utcnow()
    set_fields["services.$.updated_at"] = datetime.utcnow()

    result = await db[COLLECTION].update_one(
        {"_id": ObjectId(network_id), "user_id": user_id, "services.service_id": service_id},
        {"$set": set_fields}
    )
    if result.modified_count > 0:
        updated_network = await get_network(db, network_id, user_id)
        return next((s for s in updated_network.services if s.service_id == service_id), None)
    return None


async def delete_service_from_network(db: AsyncIOMotorDatabase, network_id: str, service_id: str, user_id: str) -> bool:
    if not ObjectId.is_valid(network_id):
        return False
    result = await db[COLLECTION].update_one(
        {"_id": ObjectId(network_id), "user_id": user_id},
        {
            "$pull": {"services": {"service_id": service_id}},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    return result.modified_count > 0


# --- Global Settings Update ---

async def update_simulation_config(db: AsyncIOMotorDatabase, network_id: str, payload: SimulationConfig, user_id: str) -> Optional[
    SimulationConfig]:
    if not ObjectId.is_valid(network_id):
        return None
    update_data = payload.model_dump(exclude_unset=True)
    return await update_global_setting(db, network_id, "simulation_config", update_data, user_id)


async def update_si_config(db: AsyncIOMotorDatabase, network_id: str, payload: SIConfig, user_id: str) -> Optional[SIConfig]:
    if not ObjectId.is_valid(network_id):
        return None
    update_data = payload.model_dump(exclude_unset=True)
    result = await update_global_setting(db, network_id, "SI", update_data, user_id)
    return SIConfig(**result) if result else None


async def update_span_config(db: AsyncIOMotorDatabase, network_id: str, payload: SpanConfig, user_id: str) -> Optional[SpanConfig]:
    if not ObjectId.is_valid(network_id):
        return None
    update_data = payload.model_dump(exclude_unset=True)
    result = await update_global_setting(db, network_id, "Span", update_data, user_id)
    return SpanConfig(**result) if result else None


async def update_global_setting(db: AsyncIOMotorDatabase, network_id: str, setting_path: str,
                                # changed from setting_name to setting_path
                                payload: Dict[str, Any], user_id: str) -> Optional[Dict[str, Any]]:
    if not payload:
        # If payload is empty, return current setting
        network = await get_network(db, network_id, user_id)
        return getattr(network, setting_path).model_dump() if network else None

    # Construct the update query using dotted notation
    # payload already only contains fields to update.
    # We need to prepend the setting_path for mongo.
    update_fields = {f"{setting_path}.{k}": v for k, v in payload.items()}
    update_fields["updated_at"] = datetime.utcnow()

    result = await db[COLLECTION].find_one_and_update(
        {"_id": ObjectId(network_id), "user_id": user_id},
        {"$set": update_fields},
        return_document=True,
        upsert=False
    )
    # Return the specific sub-document from the updated network document
    if result:
        # Access the updated sub-document using setting_path
        # Convert it back to Pydantic model for type safety and validation
        if setting_path == "SI":
            return SIConfig(**result.get(setting_path, {})).model_dump()
        elif setting_path == "Span":
            return SpanConfig(**result.get(setting_path, {})).model_dump()
        elif setting_path == "simulation_config":
            return SimulationConfig(**result.get(setting_path, {})).model_dump()
    return None


# --- Import/Export ---

async def create_network_from_import(db: AsyncIOMotorDatabase, import_data: NetworkImport, user_id: str) -> NetworkInDB:
    element_id_map = {}
    elements_in_db = []
    for el_create in import_data.elements:
        # Generate a new unique ID for the element
        new_element_id = str(uuid6())
        # Map the client-provided temporary ID (if any) to the new generated ID
        if el_create.element_id:
            element_id_map[el_create.element_id] = new_element_id
        # Create ElementInDB using the new generated ID
        elements_in_db.append(ElementInDB(
            element_id=new_element_id,
            name=el_create.name,
            type=el_create.type,
            type_variety=el_create.type_variety,
            params=el_create.params,
            metadata=el_create.metadata
        ))

    connections_in_db = []
    for conn_create in import_data.connections:
        # Resolve from_node and to_node using the element_id_map
        # If a node ID was temporary and mapped, use the new ID.
        # Otherwise, assume it's an external reference or an ID meant to be kept (unlikely for new network import).
        from_node_resolved = element_id_map.get(conn_create.from_node, conn_create.from_node)
        to_node_resolved = element_id_map.get(conn_create.to_node, conn_create.to_node)

        # Basic validation: ensure resolved IDs are valid UUIDs if they were mapped
        if (conn_create.from_node in element_id_map and not ElementInDB.model_validate(
                {"element_id": from_node_resolved, "name": "temp", "type": "Fiber"})) or \
                (conn_create.to_node in element_id_map and not ElementInDB.model_validate(
                    {"element_id": to_node_resolved, "name": "temp", "type": "Fiber"})):
            raise ValueError(
                f"Invalid node ID reference found during connection import: from_node={conn_create.from_node}, to_node={conn_create.to_node}")

        connections_in_db.append(ConnectionInDB(from_node=from_node_resolved, to_node=to_node_resolved))

    # Services are directly created with new IDs
    services_in_db = []
    for s_create in import_data.services:
        services_in_db.append(ServiceInDB(**s_create.model_dump()))

    now = datetime.utcnow()
    network_doc = {
        "network_name": import_data.network_name,
        "user_id": user_id,  # Add user_id for user isolation
        "created_at": now,
        "updated_at": now,
        "elements": [el.model_dump() for el in elements_in_db],
        "connections": [conn.model_dump() for conn in connections_in_db],
        "services": [s.model_dump() for s in services_in_db],
        "SI": import_data.SI.model_dump(),  # Use si_config for internal storage
        "Span": import_data.Span.model_dump(),  # Use span_config for internal storage
        "simulation_config": import_data.simulation_config.model_dump(),
    }

    result = await db[COLLECTION].insert_one(network_doc)
    created_doc = await db[COLLECTION].find_one({"_id": result.inserted_id})
    return NetworkInDB(**created_doc)


async def insert_sub_topology(db: AsyncIOMotorDatabase, network_id: str, sub_topo: SubTopologyImport, user_id: str) -> Optional[
    NetworkInDB]:
    if not ObjectId.is_valid(network_id):
        return None

    existing_network = await get_network(db, network_id, user_id)
    if not existing_network:
        return None

    element_id_map = {}
    new_elements_for_db = []
    new_connections_for_db = []

    # Process elements
    for el_create in sub_topo.elements:
        new_element_id = str(uuid6())  # Always generate new ID
        original_element_id = el_create.element_id  # Client's temporary ID if provided

        if original_element_id:
            # Check for conflict if strategy is 'error'
            if sub_topo.strategy == "error" and any(
                    el.element_id == original_element_id for el in existing_network.elements):
                raise ValueError(f"Element ID conflict: {original_element_id} already exists in network {network_id}")
            # Map original ID to new generated ID
            element_id_map[original_element_id] = new_element_id

        # Create ElementInDB with the newly generated ID
        new_elements_for_db.append(ElementInDB(
            element_id=new_element_id,
            name=el_create.name,
            type=el_create.type,
            type_variety=el_create.type_variety,
            params=el_create.params,
            operational=el_create.operational,
            metadata=el_create.metadata
        ))

    # Process connections
    for conn_create in sub_topo.connections:
        # Resolve from_node and to_node using the element_id_map.
        # If not found in map, assume it's an existing ID in the target network.
        from_node_resolved = element_id_map.get(conn_create.from_node, conn_create.from_node)
        to_node_resolved = element_id_map.get(conn_create.to_node, conn_create.to_node)

        new_connection_id = str(uuid6())

        # Check for connection conflict if strategy is 'error'
        if sub_topo.strategy == "error" and \
                any(c.from_node == from_node_resolved and c.to_node == to_node_resolved for c in
                    existing_network.connections):
            raise ValueError(
                f"Connection conflict: {from_node_resolved} -> {to_node_resolved} already exists in network {network_id}")

        new_connections_for_db.append(ConnectionInDB(
            connection_id=new_connection_id,
            from_node=from_node_resolved,
            to_node=to_node_resolved
        ))

    # Update the network with new elements and connections
    result = await db[COLLECTION].update_one(
        {"_id": ObjectId(network_id), "user_id": user_id},
        {
            "$push": {
                "elements": {"$each": [el.model_dump() for el in new_elements_for_db]},
                "connections": {"$each": [c.model_dump() for c in new_connections_for_db]}
            },
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    if result.modified_count > 0:
        return await get_network(db, network_id, user_id)
    return None
