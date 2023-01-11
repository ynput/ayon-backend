__all__ = ["router"]

from projects import anatomy, deploy, list_projects, projects, roots, settings
from projects.router import router

# To keep the linter happy
assert list_projects
assert projects
assert deploy
assert settings
assert anatomy
assert roots
