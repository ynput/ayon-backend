from fastapi import APIRouter

router = APIRouter(
    prefix="/projects/{project_name}/dashboard",
    tags=["Project dashboard"],
)
