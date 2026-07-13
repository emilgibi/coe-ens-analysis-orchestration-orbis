import requests
from app.core.config import get_settings
from app.core.security.jwt import create_jwt_token
from app.schemas.logger import logger
from app.core.utils.db_utils import *
import traceback

def normalize_website(website: str | None) -> str | None:
    """
    Normalize website safely.
    Returns None if website is invalid.
    """
    if isinstance(website, str):
        website = website.strip()
        if website:
            website = website.rstrip("/")
            website = website.replace("https://", "").replace("http://", "").replace("www.", "")
            return website
    return None


async def cyber_risk_validation(data, session):
    logger.info("Cyber Risk Analysis - Started")

    if not isinstance(data, dict):
        logger.error("Cyber Risk Analysis - invalid input")
        return {"status": "failed"}

    ens_id     = data.get("ens_id")
    session_id = data.get("session_id")

    # ── Fetch domain and company name from DB ─────────────────────────────────
    try:
        incoming_columns = await get_dynamic_ens_data(
            "external_supplier_data",
            ["website", "name"],
            ens_id,
            session_id,
            session,
        )

        if not incoming_columns:
            logger.info("Cyber Risk Analysis - No supplier data found")
            return {"status": "passed"}

        row          = incoming_columns[0]
        company_name = row.get("name", "")
        domain       = normalize_website(row.get("website"))

        if not domain:
            logger.info("Cyber Risk Analysis - No domain/website found")
            return {"status": "passed"}

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Cyber Risk Analysis - Failed to fetch data from DB: {e}")
        return {"status": "failed"}

    # ── Generate JWT ──────────────────────────────────────────────────────────
    try:
        jwt_token = create_jwt_token("orchestration", "analysis")
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Cyber Risk Analysis - JWT generation failed: {e}")
        return {"status": "failed"}

    url     = f"{get_settings().urls.orbis_engine}/api/v1/orbis/cyber"
    headers = {"Authorization": f"Bearer {jwt_token.access_token}"}
    params  = {
        "companyName": company_name,
        "domain":      domain,
        "session_id":   session_id,
        "ens_id":       ens_id,
    }

    # ── Call cyber risk API ───────────────────────────────────────────────────
    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=60,
        )

        logger.info(f"Cyber Risk Analysis - status code: {response.status_code}")

        try:
            response_data = response.json()
        except Exception as e:
            traceback.print_exc()
            logger.error("Cyber Risk Analysis - Response is not valid JSON")
            logger.error(response.text)
            return {"status": "failed"}

        if response.status_code in (200, 201):
            logger.info(f"Cyber Risk Analysis - Completed for ENS {ens_id}")
            return {"status": "completed", "data": response_data.get("data")}

        logger.error(f"Cyber Risk Analysis - API error: {response_data}")
        return {"status": "failed"}

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Cyber Risk Analysis - Exception for ENS {ens_id}: {e}")
        return {"status": "failed"}