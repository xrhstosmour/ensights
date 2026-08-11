"""Segmentation API routes.

Exposes the nested region-then-customer clustering as a tree.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import status

from app.analysis.clustering import ClusterNode
from app.core.logging import get_logger
from app.dependencies import CurrentUser
from app.dependencies import SessionDependency
from app.schemas.segmentation import SegmentationResponse
from app.services.segmentation_service import ClusteringError
from app.services.segmentation_service import SegmentationService

router = APIRouter(prefix="/segmentation", tags=["Segmentation"])
logger = get_logger("api.segmentation")


def _to_response(node: ClusterNode) -> dict[str, Any]:
    """Convert a cluster node and its children to a serialisable mapping.

    Args:
        node: The node to convert.

    Returns:
        The node as nested dictionaries.
    """
    return {
        "label": node.label,
        "level": node.level,
        "size": node.size,
        "members": node.members,
        "feature_means": node.feature_means,
        "silhouette": node.silhouette,
        "children": [_to_response(child) for child in node.children],
    }


@router.get(
    "",
    response_model=SegmentationResponse,
    summary="Nested region and customer segmentation",
    description=(
        "Clusters regions on their sales behaviour over time, then clusters "
        "the customers within each region on RFM. The number of clusters at "
        "each level is chosen by silhouette rather than fixed in advance."
    ),
)
async def segmentation(
    session: SessionDependency,
    _current_user: CurrentUser,
    minimum_k: Annotated[int, Query(ge=2, le=10)] = 2,
    maximum_k: Annotated[int, Query(ge=2, le=10)] = 6,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> SegmentationResponse:
    """Run the nested segmentation.

    Args:
        session: Async database session.
        _current_user: Authenticated caller.
        minimum_k: Smallest number of clusters to evaluate.
        maximum_k: Largest number of clusters to evaluate.
        start: Inclusive start of the window to segment.
        end: Exclusive end of the window to segment.

    Returns:
        The segmentation tree with its silhouette scores.

    Raises:
        HTTPException: 400 when the parameters are invalid.
    """
    if minimum_k > maximum_k:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="minimum_k must not exceed maximum_k",
        )

    try:
        result = await SegmentationService(session).run(
            k_range=tuple(range(minimum_k, maximum_k + 1)), start=start, end=end
        )
    except ClusteringError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    return SegmentationResponse.model_validate(
        {
            "chosen_k": result.chosen_k,
            "silhouette": result.silhouette,
            "scores": result.scores,
            "clusters": [_to_response(node) for node in result.clusters],
        }
    )
