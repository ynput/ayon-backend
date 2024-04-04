from fastapi import APIRouter

router = APIRouter(
    prefix="/projects/{project_name}",
    tags=["Project activities"],
)
