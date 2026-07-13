import json
from datetime import datetime, date
from app.core.utils.db_utils import *
from app.schemas.logger import logger
from rapidfuzz import fuzz
import traceback


async def domain_analysis(data, session):
    logger.info("Performing DOM Analysis...")

    kpi_area_module = "DOM"

    if not isinstance(data, dict):
        logger.error("Invalid input data received in domain_analysis")
        return []
    ens_id_value = data.get("ens_id")
    session_id_value = data.get("session_id")

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

        DOM1A = kpi_template.copy()
        DOM1A["kpi_code"] = "DOM1A"
        DOM1A["kpi_definition"] = "Domain Validation"

        required_columns = ["domain_validation"]

        retrieved_data = await get_dynamic_ens_data(
            "external_supplier_data",
            required_columns,
            ens_id_value,
            session_id_value,
            session
        )

        rows = await get_dynamic_ens_data(
            "supplier_master_data",
            ["uploaded_client_onboarding_date"],
            ens_id_value,
            session_id_value,
            session,
        )

        if not retrieved_data or not rows:
            logger.info("DOM Analysis... No data found")
            return []

        retrieved_data = retrieved_data[0]
        domain_info = retrieved_data.get("domain_validation")

        rows = rows[0]
        client_onboarding_date = rows.get("uploaded_client_onboarding_date")

        if not isinstance(domain_info, dict):
            logger.info("DOM Analysis... domain_validation missing or invalid")
            return []

        # ---------- helpers ----------
        def normalize_timestamp(value):
            """
            Safely extract UNIX timestamp from
            int | float | str | list | None
            """
            if isinstance(value, list) and value:
                value = value[0]

            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def normalize_onboarding_date(value):
            """
            Convert date | datetime | 'dd-mm-yyyy' string -> datetime
            """
            if not value:
                return None

            if isinstance(value, datetime):
                return value

            if isinstance(value, date):
                return datetime.combine(value, datetime.min.time())

            if isinstance(value, str):
                value = value.strip()
                try:
                    return datetime.strptime(value, "%d-%m-%Y")
                except ValueError:
                    return None

            return None

        def format_date(ts):
            """
            Convert timestamp → dd-mm-yyyy
            """
            try:
                return datetime.utcfromtimestamp(ts).strftime('%d-%m-%Y') if ts else ""
            except Exception:
                return ""

        current_time = int(datetime.now().timestamp())

        creation_ts = normalize_timestamp(domain_info.get("creation_date"))
        expiration_ts = normalize_timestamp(domain_info.get("expiration_date"))

        onboarding_dt = normalize_onboarding_date(client_onboarding_date)
        creation_dt = datetime.fromtimestamp(creation_ts) if creation_ts else None

        updated_date_raw = domain_info.get("updated_date", [])
        if isinstance(updated_date_raw, list) and updated_date_raw:
            valid_updated_timestamps = [
                int(v) for v in updated_date_raw
                if v is not None and str(v).strip() != ""
            ]
            updated_ts = max(valid_updated_timestamps) if valid_updated_timestamps else None
        else:
            updated_ts = normalize_timestamp(updated_date_raw)

        ONE_YEAR_IN_SECONDS = 365 * 86400

        # True if website is expired
        expired_flag = (
            expiration_ts < current_time
            if expiration_ts else False
        )

        # True if website not updated within last 1 year
        stale_update_flag = (
            (current_time - updated_ts) > ONE_YEAR_IN_SECONDS
            if updated_ts else False
        )

        # Onboarding checks only if onboarding date exists
        onboarding_prior_to_creation_flag = (
            onboarding_dt < creation_dt
            if onboarding_dt and creation_dt else None
        )

        onboarding_past_creation_flag = (
            onboarding_dt >= creation_dt
            if onboarding_dt and creation_dt else None
        )

        required_keys = [
            "domain_name",
            "creation_date",
            "expiration_date",
            "updated_date",
            "org",
            "country",
            "registrar",
            "registrar_url",
            "emails",
            "dnssec"
        ]

        filtered_domain_info = []

        for key in required_keys:
            if key in ['country', 'org']:
                key_altered = 'Registrant ' + key
                obj = {"Factor": key_altered.title()}
            else:
                obj = {"Factor": key.replace("_", " ").title()}

            if key in {"creation_date", "expiration_date"}:
                ts = normalize_timestamp(domain_info.get(key))
                obj["Value"] = format_date(ts) if ts else ""

            elif key == "updated_date":
                raw = domain_info.get(key, [])
                if isinstance(raw, list) and raw:
                    valid_timestamps = [
                        int(v) for v in raw
                        if v is not None and str(v).strip() != ""
                    ]
                    if valid_timestamps:
                        latest_ts = max(valid_timestamps)
                        obj["Value"] = format_date(latest_ts)
                    else:
                        obj["Value"] = ""
                else:
                    ts = normalize_timestamp(raw)
                    obj["Value"] = format_date(ts) if ts else ""

            elif key == "emails":
                raw = domain_info.get(key, [])
                obj["Value"] = ", ".join(str(e) for e in raw[:2] if e) if isinstance(raw, list) else ""

            else:
                obj["Value"] = domain_info.get(key, "")

            filtered_domain_info.append(obj)

        filtered_domain_info.append({
            "Factor": "Vendor Onboarding Date (Client Database)",
            "Value": onboarding_dt.strftime("%d-%m-%Y") if onboarding_dt else ""
        })

        # Rating rules:
        #
        # If onboarding date exists:
        #   Low    -> onboarding >= creation AND not stale AND not expired
        #   High   -> onboarding < creation AND stale AND expired
        #   Medium -> everything else
        #
        # If onboarding date is null:
        #   Low    -> not stale AND not expired
        #   High   -> stale AND expired
        #   Medium -> everything else

        if onboarding_dt and creation_dt:
            green_condition = (
                onboarding_past_creation_flag
                and not stale_update_flag
                and not expired_flag
            )

            red_condition = (
                onboarding_prior_to_creation_flag
                and stale_update_flag
                and expired_flag
            )
        else:
            green_condition = (
                not stale_update_flag
                and not expired_flag
            )

            red_condition = (
                stale_update_flag
                and expired_flag
            )

        DOM1A["kpi_flag"] = True

        if red_condition:
            DOM1A["kpi_rating"] = "High"      # Red
        elif green_condition:
            DOM1A["kpi_rating"] = "Low"       # Green
        else:
            DOM1A["kpi_rating"] = "Medium"    # Yellow

        DOM1A["kpi_value"] = json.dumps(filtered_domain_info)
        DOM1A["kpi_details"] = json.dumps(filtered_domain_info)

        await upsert_kpi(
            "entity_existence",
            [DOM1A],
            ens_id_value,
            session_id_value,
            session
        )

        logger.info("DOM Analysis... Completed With Data")
        return []

    except Exception as e:
        traceback.print_exc()
        logger.error(f"DOM Analysis failed: {str(e)}", exc_info=True)
        return []


def format_date(ts):
    """
    Convert timestamp → dd-mm-yy
    """
    try:
        return datetime.utcfromtimestamp(ts).strftime('%d-%m-%y') if ts else ""
    except Exception:
        return ""