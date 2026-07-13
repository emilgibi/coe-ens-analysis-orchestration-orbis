import requests
import traceback
from app.core.config import get_settings
from app.core.security.jwt import create_jwt_token
from app.schemas.logger import logger
from app.core.utils.db_utils import get_dynamic_ens_data
from app.core.analysis.analysis_submodules.address_analysis import *
from requests.exceptions import ConnectionError, Timeout, HTTPError

async def google_address_validation(data, session):
    logger.info(" ---> Google Validation: Starting Google Address Validation")

    session_id      = data.get("session_id")
    ens_id          = data.get("ens_id")
    bvd_id          = data.get("bvd_id")

    # ─────────────────────────────────────
    # Fetch address from DB
    # ─────────────────────────────────────
    try:
        rows = await get_dynamic_ens_data(
            "supplier_master_data",
            ["uploaded_address"],
            ens_id,
            session_id,
            session,
        )
        if not rows or not rows[0].get("uploaded_address"):
            logger.info(" ---> Google Validation: Address not uploaded. Finding in external_supplier_data")
            rows = await get_dynamic_ens_data(
                "external_supplier_data",
                ["address", "name"],
                ens_id,
                session_id,
                session,
            )
            if not rows or not rows[0].get("address"):
                logger.info(
                    "No address found | session_id=%s ens_id=%s",
                    session_id, ens_id
                )
                return {"module": "Google Address Validation", "status": "passed"}
            else:
                logger.info(" ---> Google Validation: Found address in external Supplier")
                address = rows[0]["address"]
                name = rows[0]["name"]
        else:
            logger.info(" ---> Google Validation: Address uploaded. Continuting")
            address = rows[0]["uploaded_address"]
            name = rows[0]["name"]
    except Exception as e:
        logger.error(
            "DB fetch failed | session_id=%s ens_id=%s error=%s",
            session_id, ens_id, str(e)
        )
        return {"module": "Google Address Validation", "status": "failed"}


    # ─────────────────────────────────────
    # JWT generation
    # ─────────────────────────────────────
    try:
        jwt_token = create_jwt_token("orchestration", "analysis")
    except Exception as e:
        logger.error(
            "JWT generation failed | session_id=%s error=%s",
            session_id, str(e)
        )
        return {"module": "Google Address Validation", "status": "failed"}
    url = f"{get_settings().urls.news_backend}/items/address_validation_orbis"

    headers = {
        "Authorization": f"Bearer {jwt_token.access_token}"
    }
    print(name,address,bvd_id)
    payload = {
        "name":            name,
        "address":         address,
        "bvd_id":          bvd_id,
    }

    # ─────────────────────────────────────
    # Call validation API (CONTROLLED ERRORS)
    # ─────────────────────────────────────
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30,
        )

        logger.info(
            "Address validation response | status=%s session_id=%s",
            response.status_code, session_id
        )

        try:
            response_data = response.json()
        except ValueError:
            logger.error(
                "Invalid JSON response | session_id=%s body=%s",
                session_id, response.text
            )
            return {"module": "Google Address Validation", "status": "failed"}

        await google_address_analysis(data, response_data, session)

        return {
            "module": "Google Address Validation",
            "status": "completed",
            "data": response_data,
        }

    except ConnectionError:
        logger.warning(
            "Address validation service unavailable | url=%s session_id=%s",
            url, session_id
        )
        return {"module": "Google Address Validation", "status": "failed"}

    except Timeout:
        logger.warning(
            "Address validation timed out | session_id=%s",
            session_id
        )
        return {"module": "Google Address Validation", "status": "failed"}

    except HTTPError as e:
        logger.error(
            "Address validation HTTP error | session_id=%s error=%s",
            session_id, str(e)
        )
        return {"module": "Google Address Validation", "status": "failed"}

    except Exception as e:
        logger.exception(
            "Unexpected error in Google Address Validation | session_id=%s",
            session_id
        )
        return {"module": "Google Address Validation", "status": "failed"}