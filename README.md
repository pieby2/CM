# CM — Smart Flashcard Engine

AI-powered flashcard app that turns any PDF into a smart, practice-ready deck with spaced repetition.

## Features

- **PDF → Flashcards**: Drop a PDF (textbook chapter, class notes) and get AI-generated flashcards covering definitions, relationships, worked examples, and edge cases
- **Spaced Repetition**: Dual-scheduler system — SM-2 for new cards, Half-Life Regression for mature cards
- **Concept Graph**: Cards are tagged with concepts; weak concepts surface automatically
- **Progress Tracking**: Mastery stats, study streaks, and focus area insights
- **Deck Management**: Create, search, edit, delete decks with full CRUD
- **Delight**: 3D card flip animations, keyboard shortcuts, confetti celebrations

## Project layout

- `apps/api`: FastAPI backend — scheduler, concept graph, PDF pipeline, card generation
- `apps/hlr`: FastAPI HLR microservice — Half-Life Regression for recall prediction
- `apps/web`: React + Vite frontend — review sessions, PDF import, deck management
- `apps/api/db/migrations`: versioned SQL migrations
- `apps/api/scripts`: migration and seed scripts
- `docker-compose.yml`: Postgres and Redis for local development

## Quick start

1. Start infra:

```bash
docker compose up -d
```

2. API setup:

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\..\..env.example .env
# Edit .env and set at least one AI key: CUE_GEMINI_API_KEY / CUE_OPENAI_API_KEY / CUE_GROQ_API_KEY
# Optional: set CUE_DEFAULT_AI_PROVIDER=gemini|openai|groq
python -m scripts.migrate
python -m scripts.seed
uvicorn app.main:app --reload --port 8000
```

3. HLR microservice setup (separate terminal):

```bash
cd apps/hlr
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8010
```

4. Install OCR binary (required for scanned PDFs fallback):

```powershell
winget install --id UB-Mannheim.TesseractOCR -e
```

5. Web setup:

```bash
cd apps/web
npm install
npm run dev
```

6. Run PDF worker (optional, for async processing):

```bash
cd apps/api
.venv\Scripts\activate
python -m app.workers.pdf_worker --poll-seconds 5
```

7. Open the app:

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- HLR docs: http://localhost:8010/docs

## API highlights

### Users & Decks
- `POST /api/users` — create or get user
- `GET /api/decks?user_id=<id>&search=<query>` — list/search decks
- `POST /api/decks` — create deck
- `PUT /api/decks/{deck_id}` — update deck
- `DELETE /api/decks/{deck_id}` — delete deck

### Cards
- `POST /api/cards` — create card
- `GET /api/cards?deck_id=<id>` — list cards
- `GET /api/cards/{card_id}` — get card
- `PUT /api/cards/{card_id}` — update card
- `DELETE /api/cards/{card_id}` — delete card

### Reviews
- `GET /api/reviews/today?user_id=<id>&deck_id=<id>&limit=30` — due cards
- `POST /api/reviews/grade` — grade a review
- `GET /api/reviews/history?user_id=<id>&days=30` — daily review aggregates
- `GET /api/reviews/streak?user_id=<id>` — study streak stats

### PDF Import & AI Generation
- `POST /api/imports/pdf` — upload PDF (multipart)
- `POST /api/imports/{job_id}/process` — extract & chunk text
- `POST /api/imports/{job_id}/generate` — AI-generate flashcards from sections
- `GET /api/imports/{job_id}/sections` — view extracted sections

### Concepts
- `POST /api/concepts/attach` — attach concepts to a card
- `GET /api/concepts/weak?user_id=<id>&deck_id=<id>` — weakest concepts

## Architecture

### Scheduler Pipeline
```
Card review → SM-2 (< 5 reviews) or HLR microservice (≥ 5 reviews)
                ↓                        ↓
         Standard interval        Half-life based interval
                ↓                        ↓
              next_due ←── fallback if HLR unavailable
```

### PDF → Flashcard Pipeline
```
Upload PDF → PyMuPDF/pdfplumber/OCR extraction
     → Heading detection & section chunking
     → Gemini AI card generation (per section)
     → Auto-tag with concepts
     → Create deck + cards + card states
```

## Keyboard Shortcuts (Review)
| Key | Action |
|-----|--------|
| `Space` / `Enter` | Reveal answer |
| `1` | Rate: Again |
| `2` | Rate: Hard |
| `3` | Rate: Good |
| `4` | Rate: Easy |
