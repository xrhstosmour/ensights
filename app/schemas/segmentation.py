"""Response schemas for the segmentation endpoint."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import BaseSchema


class ClusterNodeResponse(BaseSchema):
    """One cluster in the segmentation tree."""

    label: str
    level: int
    size: int
    members: list[str] = Field(default_factory=list)
    feature_means: dict[str, float] = Field(default_factory=dict)
    silhouette: float | None = Field(
        default=None,
        description=(
            "Silhouette of the partition this cluster belongs to, shared with "
            "its siblings. None when the group was too small to partition."
        ),
    )
    children: list[ClusterNodeResponse] = Field(default_factory=list)


class SegmentationResponse(BaseSchema):
    """A full segmentation run."""

    chosen_k: int | None = None
    silhouette: float | None = None
    scores: dict[int, float] = Field(
        default_factory=dict,
        description="Silhouette score per candidate number of clusters.",
    )
    clusters: list[ClusterNodeResponse] = Field(default_factory=list)
