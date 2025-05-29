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

```prompt
poetry shell
```

### pip

```prompt
pip install -r requirements.txt
```

## Usage

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
NEO4J_USER="user"
MY_NEO4J_PASSWORD="password"
NEO4J_DB_NAME="neo4j"
NEO4J_URI="neo4j://localhost:7687"
```

## Environment Configuration

The application supports both development and production environments with different security settings:

- **Development mode** (default): Disables CSRF protection and rate limiting for easier local development
- **Production mode**: Enables full security features

For details on configuring the environment, see [ENVIRONMENT.md](ENVIRONMENT.md).

## This repo is currently under development. Therefore, you may encounter some problems while replicating this repo. Feel free to open issue about it.
