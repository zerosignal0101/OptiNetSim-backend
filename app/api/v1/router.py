# app/api/v1/router.py
from fastapi import APIRouter
from .endpoints import networks, elements, connections, services, global_settings, import_export, auth

api_router = APIRouter()

# Include authentication routes (no authentication required)
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# Include all endpoint routers here (authentication required)
api_router.include_router(networks.router, prefix="/networks", tags=["Network Management"])
api_router.include_router(elements.router, prefix="/networks/{network_id}/elements", tags=["Topology Elements"])
api_router.include_router(connections.router, prefix="/networks/{network_id}/connections", tags=["Topology Connections"])
api_router.include_router(services.router, prefix="/networks/{network_id}/services", tags=["Service Management"])
api_router.include_router(global_settings.router, prefix="/networks/{network_id}", tags=["Global Network Settings"])
api_router.include_router(import_export.router, prefix="/networks", tags=["Import/Export"]) # Note: /networks/import is a top-level route

