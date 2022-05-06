__all__ = ["router"]

from crud_projects import list_projects, projects, deploy
from crud_projects.router import router

# To keep the linter happy
assert list_projects
assert projects
assert deploy
