from fastapi import APIRouter

router = APIRouter(
    prefix="/projects/{project_name}/versions/{version_id}/review}",
    tags=["Review"],
)
