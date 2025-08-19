# COA Document Processor - Backend API

FastAPI backend for processing Certificate of Analysis (COA) documents with AI-powered field extraction.

## Features

- PDF document process from file folder and Veeva API
- AI-powered field extraction (Lot Number, Manufacturer, Storage Conditions)
- Multi-language support (English/Chinese)
- RESTful API with automatic documentation
- PostgreSQL database with Alembic migrations

## Prerequisites

- Python 3.11+
- PostgreSQL database access
- OpenAI API key (optional, for AI extraction)

## Installation

1. Clone the repository:
```bash
cd coa-backend
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Run database migrations:
```bash
alembic upgrade head
```

6. Initialize default data:
```bash
python -m app.init_data
```

## Running the Application

### Development Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Documentation

Once the server is running, access the interactive API documentation at:
- Swagger UI: `https://localhost:8000/api/docs`
- ReDoc: `https://localhost:8000/api/redoc`

## API Endpoints

### Health Check
- `GET /api/health` - Basic health check
- `GET /api/health/ready` - Readiness check with dependencies
- `GET /api/health/live` - Liveness check

### Compounds
- `GET /api/compounds` - List all compounds
- `GET /api/compounds/{id}` - Get specific compound
- `POST /api/compounds` - Create new compound
- `PUT /api/compounds/{id}` - Update compound
- `DELETE /api/compounds/{id}` - Delete compound
- `POST /api/compounds/init-defaults` - Initialize default compounds

### Templates
- `GET /api/templates` - List all templates
- `GET /api/templates/{id}` - Get specific template
- `POST /api/templates` - Create new template
- `PUT /api/templates/{id}` - Update template
- `DELETE /api/templates/{id}` - Delete template

### Documents
- `POST /api/documents/upload` - Upload PDF document
- `POST /api/documents/process` - Process document for extraction
- `GET /api/documents/{id}` - Get document details
- `GET /api/documents/{id}/data` - Get extracted data
- `GET /api/documents` - List all documents
- `DELETE /api/documents/{id}` - Delete document

## Project Structure

```
coa-backend/
├── app/
│   ├── api/           # API routes
│   ├── models/        # SQLAlchemy models
│   ├── schemas/       # Pydantic schemas
│   ├── services/      # Business logic
|   ├── Auth/          # SSO
│   ├── config.py      # Configuration
│   ├── database.py    # Database setup
│   └── main.py        # FastAPI app
├── alembic/           # Database migrations
├── uploads/           # File storage
├── requirements.txt   # Dependencies
└── README.md
```

## Database Schema

- **compounds**: Chemical compounds (BGB-21447, etc.)
- **templates**: Document templates per compound/region
- **coa_documents**: Uploaded PDF documents
- **extracted_data**: AI-extracted field data
- **batch_data_cache**: all extracted data with realeated compound and templete

## Configuration

Key configuration options in `.env`:

- `DB_*`: PostgreSQL connection settings
- `OPENAI_API_KEY`: OpenAI API key for AI extraction
- `UPLOAD_DIR`: Directory for file storage
- `MAX_FILE_SIZE`: Maximum upload file size




