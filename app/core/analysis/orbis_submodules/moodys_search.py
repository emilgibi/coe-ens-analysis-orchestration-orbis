import requests
from sqlalchemy import text
from app.core.config import get_settings
from app.core.security.jwt import create_jwt_token
from app.schemas.logger import logger


def _response_json(response):
    try:
        return response.json()
    except ValueError:
        return {"raw_response": response.text}


async def _search_orbis_master_data_by_name(org_name: str, session, limit: int = 10):
    """
    Cache-first lookup against orbis_master_data — populated by an external
    batch script ahead of the live Moody's Orbis API access being retired
    (see coe-ens-orbis-engine-orbis/src/utils/cache_lookup.js for the same
    table's other read-only consumers). Broadened (ILIKE) match, unlike
    supplier_name_validation.py's exact match, since this powers free-text
    ad-hoc search rather than validating one specific uploaded row.
    """
    try:
        result = await session.execute(
            text(
                "SELECT bvd_id, suggested_bvd_id, uploaded_name, suggested_name, "
                "country, address, national_identifier "
                "FROM orbis_master_data "
                "WHERE uploaded_name ILIKE :pattern OR suggested_name ILIKE :pattern "
                "LIMIT :limit"
            ),
            {"pattern": f"%{org_name.strip()}%", "limit": limit},
        )
        rows = result.mappings().all()
    except Exception as e:
        logger.warning(f"[DATA-SOURCE] moodys/nameSearch — cache lookup error for org_name={org_name!r}: {e}")
        # Same rationale as supplier_name_validation.py: a failed query here
        # leaves the shared session's transaction aborted for every
        # subsequent query on it unless rolled back.
        try:
            await session.rollback()
        except Exception as rollback_error:
            logger.error(f"[DATA-SOURCE] moodys/nameSearch — rollback after cache lookup failure ALSO failed: {rollback_error}")
        return []

    results = []
    for row in rows:
        bvd_id = row.get("suggested_bvd_id") or row.get("bvd_id")
        # "None" (literal string) means TrueSight was checked pre-fetch and
        # found nothing — same invalid-value set as supplier_name_validation.py.
        if not bvd_id or bvd_id in ("", "N/A", "None"):
            continue
        results.append({
            "name": row.get("suggested_name") or row.get("uploaded_name"),
            "identifier": bvd_id,
            "identifier_type": "bvdid",
            "entity_type": "company",
            "country": row.get("country"),
            "address": row.get("address"),
            "source": "cache",
        })
    return results


async def _search_orbis_live_by_name(org_name: str):
    """
    Live TrueSight fallback. The engine's /truesight/companies route
    currently requires orgCountry (and 400s without it) — deliberately not
    worked around here per direction: this call fails today regardless,
    since the Moody's subscription is expired, and the country-requirement
    question is explicitly deferred to when the subscription is renewed.
    """
    try:
        jwt_token = create_jwt_token("orchestration", "analysis")
    except Exception as e:
        logger.error(f"Error generating JWT token: {e}")
        return []

    orbis_url = get_settings().urls.orbis_engine.rstrip("/")
    url = f"{orbis_url}/api/v1/orbis/truesight/companies"
    headers = {
        "Authorization": f"Bearer {jwt_token.access_token}",
        "Accept": "application/json",
    }
    params = {"orgName": org_name.strip(), "orgCountry": ""}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        logger.info(f"[DATA-SOURCE] moodys/nameSearch — live TrueSight status code: {response.status_code}")
        if response.status_code not in (200, 201):
            return []

        payload = _response_json(response)
        data = payload.get("data", []) if isinstance(payload, dict) else []
        results = []
        for item in data if isinstance(data, list) else []:
            match = (item.get("MATCH") or {}).get("0", {}) if isinstance(item, dict) else {}
            results.append({
                "name": match.get("NAME") or item.get("name"),
                "identifier": item.get("BVDID"),
                "identifier_type": "bvdid",
                "entity_type": "company",
                "country": match.get("COUNTRY"),
                "address": match.get("ADDRESS"),
                "source": "live",
            })
        return results
    except requests.RequestException as e:
        logger.warning(f"[DATA-SOURCE] moodys/nameSearch — live TrueSight call failed: {e}")
        return []


async def search_moodys_companies_by_name(org_name: str, session):
    """
    Ad-hoc international company name search for Entity Analysis.
    Cache-first (orbis_master_data), live TrueSight as fallback — mirrors
    the shape of search_probe42_companies_by_name in the Probe42
    orchestrator's COMPANY_orbis.py for frontend consistency.
    """
    logger.info(f"[DATA-SOURCE] moodys/nameSearch — searching for org_name={org_name!r}")

    if not org_name or len(str(org_name).strip()) < 3:
        return {
            "module": "moodys_name_search",
            "status": "failed",
            "success": False,
            "upstream_status_code": 400,
            "message": "orgName must be at least 3 characters long",
            "data": [],
        }

    cache_results = await _search_orbis_master_data_by_name(org_name, session)
    if cache_results:
        logger.info(f"[DATA-SOURCE] moodys/nameSearch — SERVING FROM DATABASE — {len(cache_results)} match(es) for org_name={org_name!r}")
        return {
            "module": "moodys_name_search",
            "status": "completed",
            "success": True,
            "upstream_status_code": 200,
            "message": "Successful",
            "data": cache_results,
        }

    logger.info(f"[DATA-SOURCE] moodys/nameSearch — no cache match, attempting live API for org_name={org_name!r}")
    live_results = await _search_orbis_live_by_name(org_name)
    return {
        "module": "moodys_name_search",
        "status": "completed",
        "success": True,
        "upstream_status_code": 200,
        "message": "Successful" if live_results else "No matches found",
        "data": live_results,
    }
