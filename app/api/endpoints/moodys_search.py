from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api import deps
from app.models import User
from app.schemas.responses import ResponseMessage
from app.core.analysis.orbis_submodules.moodys_search import search_moodys_companies_by_name

router = APIRouter()


@router.get(
    "/moodys/nameSearch",
    response_model=ResponseMessage,
    description="List Moody's Orbis company matches by name (cache-first, live TrueSight fallback)",
)
async def moodys_name_search(
    orgName: str = Query(..., min_length=3),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    try:
        results = await search_moodys_companies_by_name(orgName, session)
        if results.get("status") != "completed":
            status_code = int(results.get("upstream_status_code") or 502)
            if status_code < 400:
                status_code = 502
            raise HTTPException(
                status_code=status_code,
                detail={
                    "message": results.get("message", "Unable to fetch Moody's name search data"),
                    "data": results,
                },
            )

        return ResponseMessage(
            status=str(results.get("upstream_status_code", 200)),
            data={"results": results.get("data", [])},
            message=results.get("message", "Successful"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Moody's name search data: {str(e)}")
