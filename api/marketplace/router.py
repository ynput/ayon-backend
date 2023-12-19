from fastapi import APIRouter

router = APIRouter(
    prefix="/marketplace",
    tags=["Marketplace"],
    exclude_from_schema=True,
)
