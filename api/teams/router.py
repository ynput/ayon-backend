from fastapi import APIRouter

router = APIRouter(tags=["Teams"], prefix="/projects/{project_name}/teams")
