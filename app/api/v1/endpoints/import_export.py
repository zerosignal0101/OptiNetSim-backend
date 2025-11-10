# app/api/v1/endpoints/import_export.py
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError  # 导入 ValidationError

from ....core.auth import get_current_active_user
from ....core.database import get_database
from ....crud import crud_network
from ....models.network import NetworkDetailResponse, NetworkImport, NetworkResponse, SubTopologyImport

router = APIRouter()


@router.get(
    "/{network_id}/export",
    response_model=NetworkDetailResponse,
    summary="Export a Network"
)
async def export_network(
        network_id: str,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: str = Depends(get_current_active_user)
):
    """
    Exports a specified optical network, including its structure, global settings, and services.
    """
    db_network = await crud_network.get_network(db, network_id)
    if db_network is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found."}
        )
    # NetworkDetailResponse automatically handles the alias mapping for SI/Span
    return NetworkDetailResponse(
        network_id=str(db_network.id),
        **db_network.model_dump(by_alias=True)  # Ensure aliases are used for export
    )


@router.post(
    "/import",
    response_model=NetworkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import a new Network"
)
async def import_network(
        network_in: NetworkImport,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: str = Depends(get_current_active_user)
):
    """
    Imports a complete network structure, creating a new network in the system.
    Server will generate new IDs for all elements, connections, and services.
    """
    try:
        db_network = await crud_network.create_network_from_import(db, network_in)
        return NetworkResponse(
            network_id=str(db_network.id),
            **db_network.model_dump()
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_IMPORT_DATA", "message": "Invalid data provided for network import.",
                    "details": e.errors()}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "IMPORT_PROCESSING_ERROR", "message": str(e)}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_SERVER_ERROR",
                "message": f"An unexpected error occurred during network import. {str(e)}"
            }
        )


@router.post(
    "/{network_id}/import",
    response_model=NetworkResponse,
    summary="Insert Topology into an Existing Network"
)
async def insert_topology(
        network_id: str,
        sub_topology_in: SubTopologyImport,
        db: AsyncIOMotorDatabase = Depends(get_database),
        current_user: str = Depends(get_current_active_user)
):
    """
    Inserts a sub-topology (elements and connections) into an existing network.
    Existing network's global settings (SI, Span, SimulationConfig) are not affected.
    """
    try:
        updated_network = await crud_network.insert_sub_topology(db, network_id, sub_topology_in)
        if updated_network is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NETWORK_NOT_FOUND", "message": f"Network with id {network_id} not found."}
            )
        return NetworkResponse(
            network_id=str(updated_network.id),
            **updated_network.model_dump()
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_INSERT_DATA", "message": "Invalid data provided for topology insertion.",
                    "details": e.errors()}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Use 409 for conflicts, as per docs
            detail={"code": "RESOURCE_CONFLICT", "message": str(e)}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_SERVER_ERROR",
                    "message": f"An unexpected error occurred during topology insertion. {str(e)}"}
        )
