from fastapi import APIRouter

router = APIRouter(
    prefix="/projects/{project_name}/activity",
    tags=["Project activity"],
)
