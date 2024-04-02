from fastapi import APIRouter

router = APIRouter(
    prefix="/projects/{project_name}/activities",
    tags=["Project activities"],
)
