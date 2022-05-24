from fastapi import APIRouter
router = APIRouter(prefix="/settings", include_in_schema=True)
