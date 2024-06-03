from fastapi import APIRouter

router = APIRouter(
    prefix="/inbox",
    tags=["User inbox"],
)
