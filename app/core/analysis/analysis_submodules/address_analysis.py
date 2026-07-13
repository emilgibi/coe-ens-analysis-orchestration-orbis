import json
from datetime import datetime
from app.core.utils.db_utils import *
from app.schemas.logger import logger
import traceback

async def google_address_analysis(data, retrieved_data, session):
    logger.info("Performing Google Rating Analysis...")

    kpi_area_module = "ADD"

    if not isinstance(data, dict):
        logger.error("Invalid input data received in domain_analysis")
        return []

    ens_id_value = data.get("ens_id")
    session_id_value = data.get("session_id")
    identifier = data.get("identifier")

    try:
        kpi_template = {
            "kpi_area": kpi_area_module,
            "kpi_code": "",
            "kpi_definition": "",
            "kpi_flag": False,
            "kpi_value": None,
            "kpi_rating": "",
            "kpi_details": "",
        }

        ADD1A = kpi_template.copy()
        ADD1A["kpi_code"] = "ADD1A"
        ADD1A["kpi_definition"] = "Google Address Validation"

        if not retrieved_data:
            logger.info("Google Address Analysis... No data found")
            return []
        data=retrieved_data.get("data",{})
        address=data.get("address","")
        zone_result=data.get("zone_result",{})
        zone=zone_result.get("zone","")
        confidence=zone_result.get("confidence","")
        reason=zone_result.get("reason","")

        kpi_value=[
            {
               'factor': 'Address',
               'value': address,
            },
            {
                'factor': 'Zone',
                'value': zone,
            },
            {
                'factor': 'Reason',
                'value': reason,
            }
        ]

        if not zone:
            logger.info("Google Address Analysis... Google Rating missing or invalid")
            return []
        kpi_rating='Medium'
        if zone.lower() in ['commercial', 'industrial']:
            kpi_rating = 'Low'
        if zone.lower() in ['residential']:
            kpi_rating = 'High'
        ADD1A["kpi_flag"] = True
        ADD1A["kpi_rating"] = kpi_rating

        ADD1A["kpi_value"] = json.dumps(kpi_value)
        ADD1A["kpi_details"] = json.dumps(kpi_value)

        await upsert_kpi(
            "entity_existence",
            [ADD1A],
            ens_id_value,
            session_id_value,
            session
        )

        logger.info("Google Address Analysis... Completed With Data")
        return []

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Google Address Analysis failed: {str(e)}", exc_info=True)
        return []