# T/ TalentOS — Recruiter Intelligence Dashboard

TalentOS is an AI-powered recruiter intelligence platform that automates the transition from "Inbox Chaos" to "Ranked Hires". It summarizes Work History, normalizes Skill Taxonomies, and performs deep Gap Analysis on candidates before you even open a resume.

## 🚀 Speed to Hire
- **Multi-Agent Parsing**: Specialized models structure work history and clean messy PDF/DOCX data.
- **Semantic Matching**: Beyond keywords — scores candidates against JDs using LLM-backed gap analysis.
- **Dashboard Funnel**: Visual pipeline that highlights top-tier matches instantly.

## 🛠 Tech Stack
- **Frontend**: Next.js 14, Tailwind CSS, Framer Motion, Recharts.
- **Auth**: NextAuth v5 (Beta), bcryptjs, Middleware-guarded routes.
- **Backend**: FastAPI (Python), spaCy, LiteLLM.
- **Database**: Supabase (PostgreSQL).
- **Infrastructure**: Docker & Docker Compose.

## 📦 Getting Started

### 1. Environment Configuration
Create a `.env.local` in `frontend/` and a `.env` in the root (backend).

**Frontend (`frontend/.env.local`):**
```env
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
AUTH_SECRET=your_nextauth_secret
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Backend (`.env`):**
```env
DATABASE_URL=postgresql+asyncpg://... (Supabase connection string)
OPENAI_API_KEY=your_key
```

### 2. Run with Docker (Recommended)
```bash
docker-compose up --build
```
Access the dashboard at `http://localhost:3000`.

### 3. Local Development
**Backend:**
```bash
pip install -r requirements.txt
python -m uvicorn api.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## 🏗 Database Setup
Run the `supabase_schema.sql` located in the documentation folder in your Supabase SQL Editor to initialize all tables.

---
Built with ❤️ by the TalentOS Intelligence Team.
