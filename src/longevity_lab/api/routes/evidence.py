"""Comprehensive evidence and runtime status routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from longevity_lab.api.dependencies import get_evidence_service
from longevity_lab.api.schemas import EvidenceStatusResponse
from longevity_lab.services.evidence_service import EvidenceService

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("/status", response_model=EvidenceStatusResponse)
def status(
    evidence_service: Annotated[EvidenceService, Depends(get_evidence_service)],
    year: int = Query(2023, ge=2000, le=2100),
) -> EvidenceStatusResponse:
    """Return source, local asset, report, artifact, and feature status."""
    return evidence_service.get_status(year=year)
