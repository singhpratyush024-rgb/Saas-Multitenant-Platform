# 🚀 SaaS Multi-Tenant Platform

A production-ready, full-stack SaaS boilerplate with multi-tenancy, role-based access control, real-time WebSocket notifications, Stripe billing, and a polished Next.js dashboard.

---

## ✨ Features

### Backend
- **Multi-tenancy** — Complete workspace isolation per tenant via `X-Tenant-ID` header
- **JWT Authentication** — Access + refresh tokens, token blacklisting on logout
- **Role-Based Access Control** — Owner / Admin / Member with permission-level guards
- **Stripe Billing** — Plans, subscriptions, trials, grace periods, webhook handling
- **Real-time WebSocket** — Tenant-scoped connection rooms, live event broadcasting
- **Background Tasks** — Celery + Redis for email, scheduled jobs, usage stats
- **Audit Logging** — Immutable log of all resource mutations
- **Structured Error Responses** — Every error includes `request_id` for tracing
- **API Versioning** — Routes available at both `/` and `/api/v1/`
- **OpenAPI Docs** — Fully documented at `/docs` and `/redoc`

### Frontend
- **Next.js 14 App Router** — Server components, layouts, route groups
- **shadcn/ui + Tailwind CSS** — Rose theme, dark mode support
- **TanStack Query** — Data fetching, caching, background refetch
- **Zustand** — Auth state with localStorage persistence
- **Axios** — Auto-injects `Authorization` and `X-Tenant-ID` headers, silent token refresh
- **WebSocket Hook** — Auto-reconnects, fires toasts on live events
- **Role-based UI** — Buttons and sections hide/show based on user role

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.12) |
| Database | PostgreSQL 15 + SQLAlchemy async |
| Cache / Queue | Redis 7 |
| Task Queue | Celery |
| Payments | Stripe |
| Email | fastapi-mail (Mailtrap / SMTP) |
| Frontend | Next.js 14, TypeScript |
| Styling | Tailwind CSS + shadcn/ui |
| State | Zustand + TanStack Query |
| Auth | JWT (python-jose + passlib) |
| Containerisation | Docker + Docker Compose |
| CI | GitHub Actions |
| Deployment | Railway (backend) + Vercel (frontend) |

---

## 📁 Project Structure

```
saas-multitenant-platform/
├── app/
│   ├── api/
│   │   ├── routes/          # auth, billing, members, projects, tasks, invitations...
│   │   └── router.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   ├── redis.py
│   │   ├── email.py
│   │   ├── exception_handlers.py
│   │   └── websocket_manager.py
│   ├── dependencies/        # auth, tenant, permission guards
│   ├── middleware/          # tenant, rate limit, request ID
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # audit, notifications, seed scripts
│   └── worker/              # Celery tasks
├── frontend/
│   ├── app/
│   │   ├── (auth)/          # login, register
│   │   ├── (dashboard)/     # projects, tasks, members, billing, settings
│   │   └── invite/          # accept invitation
│   ├── components/
│   │   ├── layout/          # sidebar, header
│   │   └── ui/              # shadcn components + custom
│   ├── hooks/               # use-role, use-websocket
│   ├── lib/
│   │   ├── api/             # auth, projects, tasks, members, billing
│   │   └── axios.ts
│   └── store/               # Zustand auth store
├── migrations/              # Alembic migrations
├── tests/                   # 171 passing tests
├── nginx/                   # Nginx reverse proxy config
├── docker-compose.yml
├── docker-compose.prod.yml
├── railway.json
└── .github/
    └── workflows/
        └── ci.yml           # pytest + ruff on push
```

---

## 🚀 Getting Started

### Prerequisites
- Docker Desktop
- Node.js 18+
- Python 3.12+

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/saas-multitenant-platform.git
cd saas-multitenant-platform
```

### 2. Configure environment

```bash
cp .env.prod.example .env
# Edit .env with your values
```

Required variables:

```env
DATABASE_URL=postgresql+asyncpg://postgres:password@db:5432/saas_db
REDIS_URL=redis://redis:6379
SECRET_KEY=your-secret-key-min-32-chars
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
EMAIL_ENABLED=true
MAIL_SERVER=sandbox.smtp.mailtrap.io
MAIL_USERNAME=your-mailtrap-user
MAIL_PASSWORD=your-mailtrap-pass
MAIL_FROM=noreply@yourdomain.com
```

### 3. Start backend

```bash
docker-compose up --build
```

### 4. Start frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### 5. Create your first workspace user

```bash
docker-compose exec api python -c "
import asyncio
from app.core.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.models.role import Role
from app.core.security import hash_password
from app.services.seed_roles import seed_default_roles
from app.services.seed_plans import seed_plans
from sqlalchemy import select

async def run():
    async for db in get_db():
        t = Tenant(name='My Company', slug='mycompany', plan='free')
        db.add(t)
        await db.flush()
        await seed_default_roles(db, t.id)
        await seed_plans(db)
        role = (await db.execute(select(Role).where(Role.tenant_id==t.id, Role.name=='owner'))).scalar_one()
        u = User(email='owner@mycompany.com', hashed_password=hash_password('password123'), tenant_id=t.id, role='owner', role_id=role.id)
        db.add(u)
        await db.commit()
        print('Done — login: owner@mycompany.com / password123 / workspace: mycompany')
        break

asyncio.run(run())
"
```

---

## 🔑 Authentication Flow

```
POST /auth/register   → creates user in tenant
POST /auth/login      → returns access_token (24h) + refresh_token (7d)
POST /auth/refresh    → get new access token
POST /auth/logout     → blacklists token in Redis
```

All protected routes require:
```
Authorization: Bearer <access_token>
X-Tenant-ID: <tenant-slug>
```

---

## 🔐 Role Permissions

| Permission | Member | Admin | Owner |
|---|:---:|:---:|:---:|
| Read projects/tasks | ✅ | ✅ | ✅ |
| Create projects/tasks | ✅ | ✅ | ✅ |
| Delete projects | ❌ | ✅ | ✅ |
| Invite members | ❌ | ✅ | ✅ |
| Change member roles | ❌ | ❌ | ✅ |
| Manage billing | ❌ | ❌ | ✅ |
| View audit logs | ❌ | ✅ | ✅ |

---

## 🔄 WebSocket Real-time Events

Connect: `ws://localhost:8000/ws/connect?token=<JWT>&tenant=<slug>`

Events broadcast to all tenant members:

| Event | Trigger |
|---|---|
| `project.created` | New project added |
| `project.updated` | Project name/desc changed |
| `project.deleted` | Project removed |
| `task.created` | New task added |
| `task.updated` | Task status/title changed |
| `task.deleted` | Task removed |
| `member.joined` | Invitation accepted |
| `member.removed` | Member kicked |
| `billing.plan_changed` | Subscription upgraded/downgraded |

---

## 💳 Billing Plans

| Plan | Members | Projects | Storage | API Access | Price |
|---|---|---|---|---|---|
| Free | 3 | 5 | 100 MB | ❌ | $0 |
| Starter | 10 | 25 | 1 GB | ✅ | $29/mo |
| Pro | 50 | 100 | 10 GB | ✅ | $99/mo |
| Enterprise | Unlimited | Unlimited | Unlimited | ✅ | $299/mo |

---

## 🧪 Testing

```bash
# Activate venv
.\venv\Scripts\activate   # Windows
source venv/bin/activate  # Mac/Linux

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_auth_full.py -v
```

**171 tests passing** across:
- `test_auth_full.py` — registration, login, logout, token refresh, cross-tenant isolation
- `test_rbac.py` — all role/permission combinations
- `test_integration.py` — invite flow, Stripe webhooks, Celery tasks, audit logs
- `test_billing.py` — plan management, usage tracking
- `test_members.py` — member CRUD, role changes
- `test_projects.py` — project CRUD with cache
- `test_tasks.py` — task CRUD, status transitions

---

## 🚢 Deployment

### Backend → Railway

1. Push to GitHub
2. Connect repo at [railway.app](https://railway.app)
3. Add PostgreSQL + Redis services
4. Set environment variables from `.env.prod.example`
5. Railway auto-deploys on push

### Frontend → Vercel

1. Import repo at [vercel.com](https://vercel.com)
2. Set root directory to `frontend`
3. Add `NEXT_PUBLIC_API_URL=https://your-railway-url.railway.app`
4. Deploy

### CI/CD

GitHub Actions runs on every push to `main`:
- `ruff check` — lint Python code
- `pytest` — full test suite against a fresh PostgreSQL + Redis instance

---

## 📡 API Documentation

Once running, visit:
- **Swagger UI** → [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc** → [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🛡️ Security

- Passwords hashed with bcrypt
- JWT tokens signed with HS256
- Refresh tokens stored in localStorage, access tokens expire in 24h
- Blacklisted tokens stored in Redis
- Cross-tenant access blocked at both middleware and dependency level
- Rate limiting via Redis middleware
- Nginx security headers in production (HSTS, X-Frame-Options, etc.)

---

## 📄 License

MIT — free to use, modify, and deploy.

---

<p align="center">Built with FastAPI · Next.js · PostgreSQL · Redis · Stripe</p>