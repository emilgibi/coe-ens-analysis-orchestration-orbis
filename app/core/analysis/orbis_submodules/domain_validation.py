import aiohttp
import traceback
from datetime import datetime

from app.schemas.logger import logger
from app.core.utils.db_utils import (
    get_dynamic_ens_data,
    upsert_dynamic_ens_data,
)
from app.core.config import get_settings


def normalize_website(website: str | None) -> str | None:
    """
    Normalize website safely.
    Returns None if website is invalid.
    """
    if isinstance(website, str):
        website = website.strip()
        if website:
            return website.rstrip("/")
    return None


async def domain_validation(data, session):
    logger.info("Domain Validation - Started")

    if not isinstance(data, dict):
        logger.error("Domain Validation - invalid input")
        return {"status": "failed"}

    ens_id = data.get("ens_id")
    session_id = data.get("session_id")

    try:
        incoming_columns = await get_dynamic_ens_data(
            "external_supplier_data",
            ["name","website"],
            ens_id,
            session_id,
            session,
        )

        if not incoming_columns:
            logger.info("Domain Validation - No supplier data found")
            return {"status": "passed"}

        row = incoming_columns[0]
        website = normalize_website(row.get("website"))

        if not website:
            logger.info("Domain Validation - No Website Found")
            return {"status": "passed"}

        result = await fetch_whois(website)

        if result:
            logger.info("Domain Validation - WHOIS info found")

            column = [{
                "domain_validation": result,
            }]

            await upsert_dynamic_ens_data(
                "external_supplier_data",
                column,
                ens_id,
                session_id,
                session,
            )

        else:
            logger.info("Domain Validation - WHOIS info not found")

        return {"status": "passed"}

    except Exception as e:
        traceback.print_exc()
        logger.error(
            f"Domain Validation - Error for ENS {ens_id}: {str(e)}",
            exc_info=True,
        )
        return {"status": "failed"}


async def fetch_whois(website: str) -> dict | None:
    """
    Fetch WHOIS details asynchronously using aiohttp.
    """
    settings = get_settings()

    url = "https://api.api-ninjas.com/v1/whois"
    headers = {
        "X-Api-Key": "hADPI7SJiTwO9Ywj3AR7T7R9FBCV8EDq1RjE67cJ",  # ✅ move API key to config
    }
    params = {"domain": website}

    timeout = aiohttp.ClientTimeout(total=10)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, headers=headers, params=params, ssl=False) as response:
                if response.status == 200:
                    return await response.json()

                logger.warning(
                    f"WHOIS request failed for {website} - Status {response.status}"
                )
                return None

        except Exception as e:
            traceback.print_exc()
            logger.error(
                f"WHOIS fetch failed for {website}: {str(e)}",
                exc_info=True,
            )
            return None