import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import BaseModel, Field

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# Read .env file if present
def _load_env_file():
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v

_load_env_file()


class AppConfig(BaseModel):
    default_release: str = Field(default_factory=lambda: os.getenv("DEFAULT_RELEASE", "2023.00"))
    max_history_turns: int = 6
    log_level: str = "INFO"


class LLMConfig(BaseModel):
    provider: str = Field(
        default_factory=lambda: os.getenv(
            "LLM_PROVIDER", "groq" if os.getenv("GROQ_API_KEY") else "ollama"
        )
    )
    base_url: str = Field(
        default_factory=lambda: os.getenv(
            "LLM_BASE_URL",
            "https://api.groq.com/openai/v1"
            if (os.getenv("GROQ_API_KEY") or os.getenv("LLM_PROVIDER") == "groq")
            else "http://localhost:11434/v1",
        )
    )
    model: str = Field(
        default_factory=lambda: os.getenv(
            "LLM_MODEL",
            "llama-3.3-70b-versatile"
            if (os.getenv("GROQ_API_KEY") or os.getenv("LLM_PROVIDER") == "groq")
            else "gpt-oss:20b",
        )
    )
    router_model: str = Field(
        default_factory=lambda: os.getenv(
            "LLM_ROUTER_MODEL",
            "llama-3.3-70b-versatile"
            if (os.getenv("GROQ_API_KEY") or os.getenv("LLM_PROVIDER") == "groq")
            else "gpt-oss:20b",
        )
    )
    api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"))
    temperature: float = 0.1
    max_tokens: int = 1200
    timeout_s: int = 60
    hosted_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "HOSTED_LLM_ENABLED", "true" if os.getenv("GROQ_API_KEY") else "false"
        ).lower()
        == "true"
    )


class EmbeddingsConfig(BaseModel):
    model: str = "BAAI/bge-m3"
    device: str = "cpu"
    batch_size: int = 16
    max_length: int = 1024


class RerankerConfig(BaseModel):
    model: str = "BAAI/bge-reranker-v2-m3"
    top_n_in: int = 40
    top_n_out: int = 6
    min_score: float = 0.30


class RetrievalConfig(BaseModel):
    dense_k: int = 40
    sparse_k: int = 40
    fusion: str = "rrf"
    keyword_boost: bool = True


class ChunkingConfig(BaseModel):
    target_tokens: int = 450
    max_tokens: int = 800
    overlap_tokens: int = 60
    table_rows_per_chunk: int = 25


class ContextConfig(BaseModel):
    max_context_tokens: int = 3500
    expand_to_parent: bool = True


class QdrantConfig(BaseModel):
    url: str = Field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    collection: str = "edocs_chunks"


class PostgresConfig(BaseModel):
    dsn: str = Field(default_factory=lambda: os.getenv("POSTGRES_DSN", "postgresql://edocs:edocs@localhost:5432/edocs"))


class SecurityConfig(BaseModel):
    auth_mode: str = "api_key"
    rate_limit_per_minute: int = 30
    log_retention_days: int = 90


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or (CONFIG_DIR / "settings.yaml")
    data = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # Override with environment variables
    settings = Settings(**data)
    if os.getenv("LLM_BASE_URL"):
        settings.llm.base_url = os.environ["LLM_BASE_URL"]
    if os.getenv("LLM_MODEL"):
        settings.llm.model = os.environ["LLM_MODEL"]
    if os.getenv("LLM_PROVIDER"):
        settings.llm.provider = os.environ["LLM_PROVIDER"]
    if os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY"):
        settings.llm.api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
    if os.getenv("HOSTED_LLM_ENABLED"):
        settings.llm.hosted_enabled = os.environ["HOSTED_LLM_ENABLED"].lower() == "true"

    return settings


def load_field_labels(config_path: Path | None = None) -> Dict[str, str]:
    path = config_path or (CONFIG_DIR / "field_labels.yaml")
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}
