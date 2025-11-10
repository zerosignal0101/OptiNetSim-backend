# app/api/v1/endpoints/connections.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ....core.auth import get_current_active_user
from ....core.database import get_database
from ....crud import crud_network
from ....models.network import ConnectionCreate, ConnectionInDB
from ....models.user import TokenData

router = APIRouter()


@router.post(
    "",
    response_model=ConnectionInDB,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Topology Connection"
)
async def create_connection(
        network_id: str,
        connection_in: ConnectionCreate,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Creates a new connection between two topology nodes within the specified optical network.
    """
    # Basic validation: Check if from_node and to_node exist as elements in the network
    network = await crud_network.get_network(db, network_id, current_user.username)
    if not network:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found."}
        )

    from_node_exists = any(el.element_id == connection_in.from_node for el in network.elements)
    to_node_exists = any(el.element_id == connection_in.to_node for el in network.elements)

    if not from_node_exists or not to_node_exists:
        missing_nodes = []
        if not from_node_exists: missing_nodes.append(connection_in.from_node)
        if not to_node_exists: missing_nodes.append(connection_in.to_node)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_CONNECTION",
                    "message": f"One or more nodes do not exist in the network: {', '.join(missing_nodes)}."}
        )

    existing_connection = any(
        conn.from_node == connection_in.from_node and conn.to_node == connection_in.to_node
        for conn in network.connections
    )
    if existing_connection:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONNECTION_ALREADY_EXISTS",
                    "message": f"A connection between '{connection_in.from_node}' and '{connection_in.to_node}' already exists."}
        )

    db_connection = await crud_network.add_connection_to_network(db, network_id, connection_in, current_user.username)
    if db_connection is None:
        # This case should ideally not happen if network_id is valid and nodes exist
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_SERVER_ERROR", "message": "Failed to create connection due to unexpected error."}
        )
    return db_connection


@router.get(
    "/{connection_id}",
    response_model=ConnectionInDB,
    summary="Get a specific Topology Connection by ID"
)
async def get_connection(
        network_id: str,
        connection_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Retrieves the detailed information for a specific topology connection within a network.
    """
    connection = await crud_network.get_connection_from_network(db, network_id, connection_id, current_user.username)
    if connection is None:
        network_exists = await crud_network.get_network(db, network_id, current_user.username)
        if not network_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found."}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CONNECTION_NOT_FOUND",
                        "message": f"Connection with id {connection_id} not found in network {network_id}."}
            )
    return connection


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Topology Connection"
)
async def delete_connection(
        network_id: str,
        connection_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: TokenData = Depends(get_current_active_user)
):
    """
    Deletes a specific topology connection from a network.
    """
    success = await crud_network.delete_connection_from_network(db, network_id, connection_id, current_user.username)
    if not success:
        network_exists = await crud_network.get_network(db, network_id, current_user.username)
        if not network_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found."}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CONNECTION_NOT_FOUND",
                        "message": f"Connection with id {connection_id} not found in network {network_id}."}
            )
    return None
