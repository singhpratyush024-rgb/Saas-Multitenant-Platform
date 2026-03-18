# app/db/project_repository.py

from app.db.repository import TenantRepository
from app.models.project import Project


class ProjectRepository(TenantRepository[Project]):
    """
    Tenant-scoped repository for Projects.
    Inherits all CRUD + pagination from TenantRepository.
    Add project-specific queries here if needed.
    """
    model = Project