from typing import Literal
from pydantic import BaseModel, Field

class Document(BaseModel):
    doc_id: str                 # "<chm_stem>/<path>"
    release: str
    chm: str
    path: str
    title: str
    breadcrumbs: list[list[str]]
    toc_order: int | None
    topic_type: str
    product_area: str
    summary: str | None = None
    markdown: str
    images: list[str] = Field(default_factory=list)
    also_in: list[str] = Field(default_factory=list)
    orphan: bool = False
    content_hash: str

class Chunk(BaseModel):
    chunk_id: str               # "<doc_id>#<n>"
    doc_id: str
    release: str
    text: str                   # header + body
    section_path: list[str] = Field(default_factory=list)
    anchor: str | None = None
    topic_type: str
    product_area: str
    kind: Literal["topic", "table_part", "steps_part", "field_card", "record_overview"]
    token_count: int
    content_hash: str

class FieldRecord(BaseModel):
    release: str
    record: str
    field_name: str
    field_number: str | None = None
    poweron_mnemonic: str | None = None
    symxchange_mnemonic: str | None = None
    data_type: str | None = None
    source: str | None = None
    help_file: str | None = None
    default_control: str | None = None
    default_value: str | None = None
    description: str | None = None
    doc_id: str

class DocLink(BaseModel):
    source_doc_id: str
    target_doc_id: str
    anchor: str = ""
    link_text: str = ""

class IngestStats(BaseModel):
    release: str
    chm_hashes: dict[str, str] = Field(default_factory=dict)
    documents_count: int = 0
    chunks_count: int = 0
    fields_count: int = 0
    links_count: int = 0
    broken_links_count: int = 0
    duration_seconds: float = 0.0
    warnings: list[str] = Field(default_factory=list)
