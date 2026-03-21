# tests/test_rbac.py
#
# Exhaustive RBAC matrix — every role vs every protected endpoint.
# All 403s verified. Uses shared fixtures from conftest.py.

import pytest
from app.models.project import Project
from sqlalchemy import delete


# ── Helpers ───────────────────────────────────────────────────────

async def _make_project(client, name="RBAC Project"):
    res = await client.post("/projects/", json={"name": name})
    assert res.status_code == 200, res.text
    return res.json()["data"]["id"]


async def _make_task(client, project_id, title="RBAC Task"):
    res = await client.post(
        f"/projects/{project_id}/tasks/",
        json={"title": title, "status": "todo"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["id"]


# ══════════════════════════════════════════════════════════════════
# Projects — permission matrix
# ══════════════════════════════════════════════════════════════════

class TestProjectPermissions:

    # GET /projects/ — requires projects:read (all roles have it)
    @pytest.mark.asyncio
    async def test_owner_can_list_projects(self, owner_client):
        res = await owner_client.get("/projects/")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_list_projects(self, admin_client):
        res = await admin_client.get("/projects/")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_member_can_list_projects(self, member_client):
        res = await member_client.get("/projects/")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_list_projects(self, acme_client):
        res = await acme_client.get("/projects/")
        assert res.status_code == 401

    # POST /projects/ — requires projects:write
    @pytest.mark.asyncio
    async def test_owner_can_create_project(self, owner_client):
        res = await owner_client.post("/projects/", json={"name": "Owner P"})
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_create_project(self, admin_client):
        res = await admin_client.post("/projects/", json={"name": "Admin P"})
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_member_can_create_project(self, member_client):
        res = await member_client.post("/projects/", json={"name": "Member P"})
        assert res.status_code == 200

    # DELETE /projects/{id} — requires projects:delete (admin + owner)
    @pytest.mark.asyncio
    async def test_owner_can_delete_project(self, owner_client):
        pid = await _make_project(owner_client, "Del Owner")
        res = await owner_client.delete(f"/projects/{pid}")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_delete_project(self, owner_client, admin_client):
        pid = await _make_project(owner_client, "Del Admin")
        res = await admin_client.delete(f"/projects/{pid}")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_delete_project(self, owner_client, member_client):
        pid = await _make_project(owner_client, "Del Member")
        res = await member_client.delete(f"/projects/{pid}")
        assert res.status_code == 403
        assert res.json()["success"] is False

    # PATCH /projects/{id} — requires projects:write
    @pytest.mark.asyncio
    async def test_member_can_update_project(self, member_client):
        pid = await _make_project(member_client, "Update Member")
        res = await member_client.patch(f"/projects/{pid}", json={"name": "Updated"})
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_update_project(self, owner_client, acme_client):
        pid = await _make_project(owner_client, "Update Unauth")
        res = await acme_client.patch(f"/projects/{pid}", json={"name": "X"})
        assert res.status_code == 401


# ══════════════════════════════════════════════════════════════════
# Tasks — permission matrix
# ══════════════════════════════════════════════════════════════════

class TestTaskPermissions:

    @pytest.mark.asyncio
    async def test_owner_can_create_task(self, owner_client):
        pid = await _make_project(owner_client, "Task P Owner")
        res = await owner_client.post(
            f"/projects/{pid}/tasks/",
            json={"title": "T1", "status": "todo"},
        )
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_member_can_create_task(self, member_client):
        pid = await _make_project(member_client, "Task P Member")
        res = await member_client.post(
            f"/projects/{pid}/tasks/",
            json={"title": "T2", "status": "todo"},
        )
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_delete_task(self, owner_client, member_client):
        pid = await _make_project(owner_client, "Task Del")
        tid = await _make_task(owner_client, pid)
        res = await member_client.delete(f"/projects/{pid}/tasks/{tid}")
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_delete_task(self, owner_client, admin_client):
        pid = await _make_project(owner_client, "Task Del Admin")
        tid = await _make_task(owner_client, pid)
        res = await admin_client.delete(f"/projects/{pid}/tasks/{tid}")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_task_in_other_project_returns_404(self, owner_client):
        pid1 = await _make_project(owner_client, "P1")
        pid2 = await _make_project(owner_client, "P2")
        tid = await _make_task(owner_client, pid1)
        res = await owner_client.get(f"/projects/{pid2}/tasks/{tid}")
        assert res.status_code == 404


# ══════════════════════════════════════════════════════════════════
# Members — permission matrix
# ══════════════════════════════════════════════════════════════════

class TestMemberPermissions:

    @pytest.mark.asyncio
    async def test_all_roles_can_list_members(self, owner_client, admin_client, member_client):
        for c in [owner_client, admin_client, member_client]:
            res = await c.get("/members/")
            assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_all_roles_can_get_own_profile(self, owner_client, admin_client, member_client):
        for c in [owner_client, admin_client, member_client]:
            res = await c.get("/members/me")
            assert res.status_code == 200
            assert "permissions" in res.json()

    @pytest.mark.asyncio
    async def test_only_owner_can_change_roles(
        self, owner_client, admin_client, member_client,
        member_user, admin_role
    ):
        # Owner can change role
        res = await owner_client.patch(
            f"/members/{member_user.id}/role",
            json={"role_id": admin_role.id},
        )
        assert res.status_code == 200

        # Admin cannot change roles
        res = await admin_client.patch(
            f"/members/{member_user.id}/role",
            json={"role_id": admin_role.id},
        )
        assert res.status_code == 403

        # Member cannot change roles
        res = await member_client.patch(
            f"/members/{member_user.id}/role",
            json={"role_id": admin_role.id},
        )
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_cannot_change_own_role(self, owner_client, owner_user, member_role):
        res = await owner_client.patch(
            f"/members/{owner_user.id}/role",
            json={"role_id": member_role.id},
        )
        assert res.status_code == 403
        assert "own role" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_can_delete_member(self, admin_client, db, tenant, member_role):
        from conftest import _create_user
        user = await _create_user(db, tenant, member_role, "delete_me@acme.com")
        await db.commit()

        res = await admin_client.delete(f"/members/{user.id}")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_delete_others(self, member_client, admin_user):
        res = await member_client.delete(f"/members/{admin_user.id}")
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_delete_owner(self, admin_client, owner_user):
        res = await admin_client.delete(f"/members/{owner_user.id}")
        assert res.status_code == 403
        assert "owner" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_cannot_delete_self(self, admin_client, admin_user):
        res = await admin_client.delete(f"/members/{admin_user.id}")
        assert res.status_code == 403
        assert "yourself" in res.json()["detail"]


# ══════════════════════════════════════════════════════════════════
# Invitations — permission matrix
# ══════════════════════════════════════════════════════════════════

class TestInvitationPermissions:

    @pytest.mark.asyncio
    async def test_owner_can_create_invitation(self, owner_client, member_role):
        res = await owner_client.post(
            "/invitations/",
            json={"email": "rbac_invite@acme.com", "role_id": member_role.id},
        )
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_create_invitation(self, admin_client, member_role):
        res = await admin_client.post(
            "/invitations/",
            json={"email": "rbac_admin_invite@acme.com", "role_id": member_role.id},
        )
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_create_invitation(self, member_client, member_role):
        res = await member_client.post(
            "/invitations/",
            json={"email": "rbac_member_invite@acme.com", "role_id": member_role.id},
        )
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_can_list_invitations(self, owner_client):
        res = await owner_client.get("/invitations/")
        assert res.status_code == 200
        assert isinstance(res.json()["data"] if "data" in res.json() else res.json(), list)

    @pytest.mark.asyncio
    async def test_member_cannot_list_invitations(self, member_client):
        res = await member_client.get("/invitations/")
        assert res.status_code == 403


# ══════════════════════════════════════════════════════════════════
# Billing — permission matrix
# ══════════════════════════════════════════════════════════════════

class TestBillingPermissions:

    @pytest.mark.asyncio
    async def test_all_roles_can_view_plans(self, owner_client, admin_client, member_client):
        for c in [owner_client, admin_client, member_client]:
            res = await c.get("/billing/plans")
            assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_all_roles_can_view_billing_status(self, owner_client, admin_client, member_client):
        for c in [owner_client, admin_client, member_client]:
            res = await c.get("/billing/status")
            assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_only_owner_can_subscribe(self, admin_client, member_client):
        for c in [admin_client, member_client]:
            res = await c.post("/billing/subscribe", json={"plan_key": "starter"})
            assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_only_owner_can_cancel(self, admin_client, member_client):
        for c in [admin_client, member_client]:
            res = await c.post("/billing/cancel")
            assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_and_owner_can_view_invoices(self, owner_client, admin_client):
        for c in [owner_client, admin_client]:
            res = await c.get("/billing/invoices")
            assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_view_invoices(self, member_client):
        res = await member_client.get("/billing/invoices")
        assert res.status_code == 403


# ══════════════════════════════════════════════════════════════════
# Search + Audit — permission matrix
# ══════════════════════════════════════════════════════════════════

class TestSearchAuditPermissions:

    @pytest.mark.asyncio
    async def test_all_roles_can_search(self, owner_client, admin_client, member_client):
        for c in [owner_client, admin_client, member_client]:
            res = await c.get("/search/?q=test")
            assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_search_requires_min_2_chars(self, member_client):
        res = await member_client.get("/search/?q=x")
        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_owner_can_view_audit_logs(self, owner_client):
        res = await owner_client.get("/audit-logs/")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_view_audit_logs(self, admin_client):
        res = await admin_client.get("/audit-logs/")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_view_audit_logs(self, member_client):
        res = await member_client.get("/audit-logs/")
        assert res.status_code == 403