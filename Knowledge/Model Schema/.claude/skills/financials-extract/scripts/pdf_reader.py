"""Thin wrappers over pymupdf (text) and pdfplumber (tables)."""
from __future__ import annotations

from pathlib import Path

import pdfplumber
import pymupdf


def get_page_count(pdf_path: Path) -> int:
    with pymupdf.open(pdf_path) as doc:
        return doc.page_count


def get_all_page_texts(pdf_path: Path) -> list[str]:
    """Return a list of page texts, index 0 = page 1."""
    with pymupdf.open(pdf_path) as doc:
        return [page.get_text() for page in doc]


def get_page_text(pdf_path: Path, page_num_1indexed: int) -> str:
    with pymupdf.open(pdf_path) as doc:
        return doc[page_num_1indexed - 1].get_text()


def extract_tables(pdf_path: Path, page_num_1indexed: int) -> list[list[list[str | None]]]:
    """Extract tables from a page. Returns list of tables, each as rows of cells."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num_1indexed - 1]
        tables = page.extract_tables() or []
        return tables
