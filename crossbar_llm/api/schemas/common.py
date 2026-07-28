from enum import StrEnum


class ExecutionControl(StrEnum):
    GENERATE_AND_RUN = "generate_and_run"
    GENERATE = "generate"
    RESUME = "resume"


class SearchMode(StrEnum):
    DB_SEARCH = "db_search"
    VECTOR_SEARCH = "vector_search"
