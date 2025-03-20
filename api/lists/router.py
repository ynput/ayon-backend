from fastapi import APIRouter

router = APIRouter(prefix="/projects/{project_name}/lists", tags=["Lists"])
