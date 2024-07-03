from fastapi import APIRouter

router = APIRouter(
    prefix="/projects/{project_name}/reviewables",
    tags=["Review"],
)
