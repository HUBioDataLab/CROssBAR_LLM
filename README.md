# CROssBAR-LLM

This repo is created within the scope of the [CROssBARv2](https://github.com/HUBioDataLab/CROssBARv2) project to convert natural language questions into [Cypher](https://en.wikipedia.org/wiki/Cypher_(query_language)) query language. We leverage LangChain to construct Large Language Model (LLM) chains for the generation of Cypher queries and the subsequent parsing of the resulting output. Streamlit is employed to create an interactive user interface for this process.

## Installation

### poetry

First, ensure that you have `poetry` installed on your system.

```prompt
poetry --version
```

If it's not installed, install via `pip`:

```prompt
pip install -U poetry
```

To install the package:

```prompt
poetry install
```

To get into the `poetry` virtual env:

If poetry version <2 :
```prompt
poetry shell
```

If poetry version 2>= :
```prompt
poetry env activate
```

### pip

```prompt
pip install -r requirements.txt
```

## Usage

### Setting up Environment Variables

To use this package, ensure that you have `.env` file present in the root folder of it. You should use the template below:

```env
# Environment: 'development' (default) or 'production'
# See ENVIRONMENT.md for more details
CROSSBAR_ENV=development

OPENAI_API_KEY="sk-************************************************"
GEMINI_API_KEY="AI*****************-**-******-*********"
ANTHROPIC_API_KEY="sk-ant-***-***********************-****"
NVIDIA_API_KEY="nvapi-************************************"
GROQ_API_KEY="gsk_****************************************"
REPLICATE_API_KEY="***************************************"
NEO4J_USERNAME="user"
MY_NEO4J_PASSWORD="password"
NEO4J_DATABASE_NAME="neo4j"
NEO4J_URI="neo4j://localhost:7687"
```

### Running the Application

The CROssBAR-LLM application consists of two main components:
- **Backend**: FastAPI server that handles natural language to Cypher query conversion
- **Frontend**: React application providing the user interface

#### Option 1: Running in Development Mode (Recommended for development)

**Backend Setup:**

1. Navigate to the backend directory:
   ```bash
   cd crossbar_llm/backend
   ```

2. Run the FastAPI server:
   ```bash
   # If using poetry
   poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000

   # If using pip
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

   The backend API will be available at `http://localhost:8000`

**Frontend Setup:**

1. In a new terminal, navigate to the frontend directory:
   ```bash
   cd crossbar_llm/frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   # or if using pnpm
   pnpm install
   ```

3. Start the development server:
   ```bash
   npm start
   # or if using pnpm
   pnpm start
   ```

   The frontend will be available at `http://localhost:3000`

#### Option 2: Running with Docker (Recommended for production)

1. Build the Docker image:
   ```bash
   docker build -t crossbar-llm .
   ```

2. Run the container:
   ```bash
   docker run -p 8000:8000 -p 8501:8501 --env-file .env crossbar-llm
   ```

   - Backend API: `http://localhost:8000`
   - Frontend: `http://localhost:8501`

#### Option 3: Running with the Startup Script

If you have all dependencies installed locally, you can use the provided startup script:

```bash
./startup.sh
```

This will start both the backend (port 8000) and frontend (port 8501) services.

### Using the Application

1. Open your web browser and navigate to:
   - Development mode: `http://localhost:3000`
   - Production/Docker mode: `http://localhost:8501`

2. In the interface, you can:
   - Enter natural language questions about the CROssBAR knowledge graph
   - View the generated Cypher queries
   - See query results and visualizations
   - Explore the knowledge graph relationships

3. Example queries you can try:
   - "Show me all proteins related to cancer"
   - "What drugs target EGFR?"
   - "Find pathways associated with diabetes"

### API Documentation

When the backend is running, you can access:
- Interactive API documentation: `http://localhost:8000/docs`
- Alternative API documentation: `http://localhost:8000/redoc`

### Troubleshooting

- Ensure Neo4j database is running and accessible at the URI specified in `.env`
- Check that all required API keys are properly set in the `.env` file
- For CORS issues in development, ensure `CROSSBAR_ENV=development` is set
- If ports 8000 or 8501 are already in use, modify the port numbers in the respective commands

## Environment Configuration

The application supports both development and production environments with different security settings:

- **Development mode** (default): Disables CSRF protection and rate limiting for easier local development
- **Production mode**: Enables full security features

For details on configuring the environment, see [ENVIRONMENT.md](ENVIRONMENT.md).

## This repo is currently under development. Therefore, you may encounter some problems while replicating this repo. Feel free to open issue about it.
