from fastapi import APIRouter

from panoptes_server import __version__
from panoptes_server.schemas import ServiceInfo

router = APIRouter()


@router.get("/service-info", response_model=ServiceInfo)
async def service_info() -> ServiceInfo:
    return ServiceInfo(status="running", version=__version__)
