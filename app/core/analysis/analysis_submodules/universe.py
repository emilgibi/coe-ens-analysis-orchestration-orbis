from app.core.database_session import _ASYNC_ENGINE, SessionFactory
from app.schemas.logger import logger
from app.core.utils.db_utils import *
import json
import datetime
from dateutil.parser import isoparse
from app.models import NotificationType, SOURCEENUM

async def update_entity_universe_table(ens_id: str, session_id:str, session):
    existing_universe_info=''
    required_columns = ["bvd_id","name","name_international","address","postcode","city","country","phone_or_fax","email_or_website",
                        "national_id","state", "external_vendor_id"]
    existing_universe_info = await get_dynamic_ens_data("entity_universe", required_columns, ens_id, None, session)
    if len(existing_universe_info)>0:
        existing_universe_info = existing_universe_info[0]
    logger.debug("2")
    logger.debug("UNIVERSE")
    logger.debug(existing_universe_info)

    info_from_current_session = await get_dynamic_ens_data("supplier_master_data", required_columns, ens_id, session_id, session)
    info_from_current_session = info_from_current_session[0]
    logger.debug("3")
    logger.debug("CURRENT INFO")
    logger.debug(info_from_current_session)

    current_session_timestamp = await get_dynamic_ens_data("session_screening_status", ["create_time"], None, session_id, session)
    current_session_timestamp = current_session_timestamp[0].get("create_time")
    if not isinstance(current_session_timestamp, datetime.datetime):
        current_session_timestamp = isoparse(current_session_timestamp)
    logger.debug("4")
    logger.debug("current_session_timestamp")
    logger.debug(current_session_timestamp)

    cols_for_ratings = ["kpi_code", "kpi_rating"]
    current_ratings = await get_dynamic_ens_data("ovar", cols_for_ratings, ens_id, session_id, session)
    logger.debug(current_ratings)
    theme_ratings = {}
    for rating_row in current_ratings:
        if rating_row.get("kpi_rating", "").lower() != "deactivated":
            theme_ratings.update({
                rating_row.get("kpi_code", "").replace(" ", "_"): rating_row.get("kpi_rating", "")
            })

    logger.debug("5")
    logger.debug("RATINGS")
    logger.debug(theme_ratings)

    # TODO need an indicator
    if existing_universe_info:

        for key in existing_universe_info.keys():
            if key in info_from_current_session.keys():
                if existing_universe_info[key] != info_from_current_session[key]:
                    logger.debug(key)
                    logger.debug("EXISTING:")
                    logger.debug(existing_universe_info[key])
                    logger.debug("NEW:")
                    logger.debug(info_from_current_session[key])
        updated_row = {
                    "bvd_id": info_from_current_session.get("bvd_id"),
                    "name": info_from_current_session.get("name"),
                    "name_international": info_from_current_session.get("name_international"),
                    "address": info_from_current_session.get("address"),
                    "postcode": info_from_current_session.get("postcode"),
                    "city": info_from_current_session.get("city"),
                    "country": info_from_current_session.get("country"),
                    "phone_or_fax": info_from_current_session.get("phone_or_fax"),
                    "email_or_website": info_from_current_session.get("email_or_website"),
                    "national_id": info_from_current_session.get("national_id"),
                    "state": info_from_current_session.get("state"),
                    "address_type": info_from_current_session.get("address_type"),
                    "last_session_id": session_id,
                    "last_screened_date": current_session_timestamp,
                    "overall_supplier_rating": theme_ratings.get("supplier"),
                    "thematic_rating": theme_ratings
        }
        if info_from_current_session.get("external_vendor_id"):
            updated_row['external_vendor_id']=info_from_current_session.get("external_vendor_id")
    else:
        required_upload_columns = ["unmodified_name","unmodified_address","unmodified_postcode","unmodified_country",
                                   "unmodified_city","unmodified_phone_or_fax","unmodified_email_or_website","unmodified_national_id",
                                   "unmodified_state","unmodified_address_type"]
        info_from_current_upload = await get_dynamic_ens_data("upload_supplier_master_data", required_upload_columns, ens_id,
                                                               session_id, session)
        info_from_current_upload = info_from_current_upload[0]

        required_external_columns = ["management"]
        info_from_current_external = await get_dynamic_ens_data("external_supplier_data", required_external_columns, ens_id,
                                                               session_id, session)
        info_from_current_external = info_from_current_external[0]

        updated_row = {
                    "ens_id": ens_id,
                    "bvd_id": info_from_current_session.get("bvd_id"),
                    "name": info_from_current_session.get("name"),
                    "name_international": info_from_current_session.get("name_international"),
                    "address": info_from_current_session.get("address"),
                    "postcode": info_from_current_session.get("postcode"),
                    "city": info_from_current_session.get("city"),
                    "country": info_from_current_session.get("country"),
                    "phone_or_fax": info_from_current_session.get("phone_or_fax"),
                    "email_or_website": info_from_current_session.get("email_or_website"),
                    "national_id": info_from_current_session.get("national_id"),
                    "state": info_from_current_session.get("state"),
                    "last_session_id": session_id,
                    "last_screened_date": current_session_timestamp,
                    "overall_supplier_rating": theme_ratings.get("supplier"),
                    "thematic_rating": theme_ratings,
                    "external_vendor_id": info_from_current_session.get("external_vendor_id"),
                    "unmodified_name": info_from_current_upload.get("unmodified_name"),
                    "management": info_from_current_external.get("management",{}),
                    "unmodified_name_international": info_from_current_upload.get("unmodified_name_international"),
                    "unmodified_address": info_from_current_upload.get("unmodified_address"),
                    "unmodified_postcode": info_from_current_upload.get("unmodified_postcode"),
                    "unmodified_country": info_from_current_upload.get("unmodified_country"),
                    "unmodified_city": info_from_current_upload.get("unmodified_city"),
                    "unmodified_phone_or_fax": info_from_current_upload.get("unmodified_phone_or_fax"),
                    "unmodified_email_or_website": info_from_current_upload.get("unmodified_email_or_website"),
                    "unmodified_national_id": info_from_current_upload.get("unmodified_national_id"),
                    "unmodified_state": info_from_current_upload.get("unmodified_state"),
                    "unmodified_address_type": info_from_current_upload.get("unmodified_address_type")
        }

    logger.debug("overall_supplier_rating")
    logger.debug(theme_ratings.get("supplier"))

    logger.debug("updated_row")
    logger.debug(updated_row)
    # with open(f"123_xyz.json", 'w') as file:
    #     json.dump(updated_row, file, indent=2)

    # data should be a list
    upsert_status='sample'
    upsert_status = await upsert_entity_universe_data([updated_row], ens_id, session)
    return upsert_status



async def process_kpi_diffs(ens_id:str, current_session_id: str, prior_session_id:str, session):
    try:
        logger.debug(f'previous session_id {prior_session_id}')
        logger.debug(f'current session_id {current_session_id}')
        alert_kpi_codes = ['AMO1A', 'AMO1B',
                           'AMR1A', 'AMR1B',
                           'PEP1A', 'PEP1B', 'PEP2A', 'PEP2B',
                           'SAN1A', 'SAN1B', 'SAN2A', 'SAN2B',
                           'BCF1A', 'BCF1B',
                           'ONF1A', 'NWS1A']
        all_differences = {}
        all_notifications = []
        missing_data_kpis = []
        response=await get_session_source(current_session_id,session)
        source=response[0].get('source',SOURCEENUM.NU) or SOURCEENUM.NU
        theme_mappings = {
            "sanctions": ["SAN"],
            "government_political": ["PEP", "SCO"],
            "bribery_corruption_overall": ["BCF"],
            "financials": ["FIN", "BKR"],
            "other_adverse_media": ["NWS", "AMR", "AMO", "ONF"],
            "additional_indicator": ["CYB", "ESG", "WEB"]
        }  # change this to from DB
        logger.debug("check 1")
        theme_display_names = {
            "sanctions": "Sanctions",
            "government_political": "Government & Political Exposure",
            "bribery_corruption_overall": "Anti-Bribery and Anti-Corruption",
            "financials": "Financials",
            "other_adverse_media": "Other Adverse Media",
            "additional_indicator": "Additional Indicators"
        }
        logger.debug("check 2")
        reverse_area_mapping = {code: theme for theme, codes in theme_mappings.items() for code in codes}

        required_columns = ["kpi_area", "kpi_code", "kpi_definition", "kpi_rating", "kpi_flag", "kpi_details", "kpi_data"]
        kpi_table_name = ['cyes', 'fstb', 'lgrk', 'oval', 'rfct', 'sape', 'sown', 'news']
        logger.debug("check 3")
        all_current_kpis = []
        all_prior_kpis = []
        for table_name in kpi_table_name:
            res_kpis = await get_dynamic_ens_data(table_name, required_columns, ens_id, current_session_id, session)
            all_current_kpis.extend(res_kpis)
            if prior_session_id:
                res_kpis_old = await get_dynamic_ens_data(table_name, required_columns, ens_id, prior_session_id, session)
                all_prior_kpis.extend(res_kpis_old)
        logger.debug("check 4")
        # First, build a lookup dictionary from B for quick matching
        kpi_codes_lookup_prior = {d['kpi_code']: d for d in all_prior_kpis}

        logger.debug("HERE ARE THE FINDINGS")
        logger.info("check 5")
        # Loop through A and find matches
        for current_kpi in all_current_kpis:
            kpi_code = current_kpi.get('kpi_code')
            kpi_definition = current_kpi.get("kpi_definition")
            kpi_area = current_kpi.get("kpi_area")
            if kpi_code and kpi_code in kpi_codes_lookup_prior:
                logger.debug(f'kpi_definition {kpi_definition}{kpi_code}')
                prior_kpi = kpi_codes_lookup_prior[kpi_code]
                logger.debug("check 6")
                logger.debug("GOT KPIS CURRENT AND PRIOR")
                logger.debug(prior_kpi)
                logger.debug(current_kpi)
                logger.debug("check 7")
                current_data = current_kpi.get("kpi_data") if current_kpi.get("kpi_data") else []
                logger.debug(f"current data: {kpi_code}-{current_data}")
                # prior_data = ["a"] # FALLBACKS FOR TESTING
                prior_data = prior_kpi.get("kpi_data") if prior_kpi.get("kpi_data") else []
                logger.debug(f"prior data {prior_data}")
                logger.debug("check 8")

                current_complement = list(set(current_data) - set(prior_data))
                prior_complement = list(set(prior_data) - set(current_data))
                logger.debug("check 9")
                logger.debug(len(current_complement))
                logger.debug(f'length prior data-{len(prior_data)}, length current data-{len(current_data)}')
                logger.debug(f'length prior complement-{len(prior_complement)}, length current complement-{len(current_complement)}')
                if len(prior_complement) > 0 and len(current_data) != 5 and kpi_code in alert_kpi_codes :
                    missing_data_kpis.append(kpi_definition)
                if len(current_complement) > 0:
                    # FORMAT INTO NOTIFICATIONS
                    logger.debug("DIFFERENCES FOUND")
                    logger.debug(current_complement)
                    title = "Alert: " if source =='CM' else "Update: "
                    title = title + kpi_definition
                    description = "\n\n".join(current_complement)
                    theme = reverse_area_mapping.get(kpi_area, False)
                    differences_value = {kpi_code: current_complement}
                    if source.value in ['CM','PD']:
                        notification = {
                            "ens_id": ens_id,
                            "session_id": current_session_id,
                            "notification_type": NotificationType.ALERT if source=='CM' else NotificationType.UPDATE,
                            "title": title,
                            "description": description,
                            "theme": theme,
                            "data_value": json.dumps(differences_value)
                        }

                        logger.debug("NOTIFICATION FOUND")
                        logger.debug(notification)
                        all_notifications.append(notification)
                    # SAVE NOTIFICATION TO DB HERE

                    all_differences.update(differences_value.copy())
        annexure = ''
        if len(missing_data_kpis)>0:
            annexure = 'Findings previously identified for the following KPIs are no longer present in the data source:'
            for i in range(0,len(missing_data_kpis)):
                annexure += f'\n{i+1}. {missing_data_kpis[i]}'

        logger.debug("ALL DONE HERE")
        # logger.debug(json.dumps(all_differences, indent=4))
        # output = {
        #     "notifications": all_notifications,
        #     "differences": all_differences
        # }
        # with open("diff.json", "w") as file:
        #     json.dump(output, file, indent=2)
        logger.debug(f'annexure - {annexure}')
        return all_differences, all_notifications, annexure
    except Exception as e:
        logger.error(e)
        return {}, []

async def generate_rating_change_notifications(ens_id:str, current_session_id: str, prior_session_id:str, session):
    if prior_session_id:
        notification={}
        overall_title=''
        required_columns = ["kpi_area", "kpi_code", "kpi_definition", "kpi_rating", "update_time"]
        rating_rank = {"high": 1, "medium": 2, "low": 3, "info": 4, "no alerts":4}

        theme_display_names = {
            "sanctions": "Sanctions",
            "government_political": "Government & Political Exposure",
            "bribery_corruption_overall": "Anti-Bribery and Anti-Corruption",
            "financials": "Financials",
            "other_adverse_media": "Other Adverse Media",
            "additional_indicator": "Additional Indicators",
            "entity_existence": "Entity Existence",
        }

        current_ratings = await get_dynamic_ens_data("ovar", required_columns, ens_id, current_session_id, session)
        current_theme_ratings = {}
        if len(current_ratings) == 0:
            logger.info('Rating changes - Current Ratings not available. Ending process')
            return {}
        for rating_row in current_ratings:
            if rating_row.get("kpi_rating", "").lower() != "deactivated":
                current_theme_ratings.update({
                    rating_row.get("kpi_code", "").replace(" ", "_"): rating_row.get("kpi_rating", "")
                })

        prior_ratings = await get_dynamic_ens_data("ovar", required_columns, ens_id, prior_session_id, session)
        if len(prior_ratings)==0:
            logger.info('Rating changes - Prior Ratings not available. Ending process')
            return {}
        prior_theme_ratings = {}
        for rating_row in prior_ratings:
            if rating_row.get("kpi_rating", "").lower() != "deactivated":
                prior_theme_ratings.update({
                    rating_row.get("kpi_code", "").replace(" ", "_"): rating_row.get("kpi_rating", "")
                })

        all_changes = []
        overall_description = "No changes to overall rating"
        any_change_flag = False
        overall_change_flag = False
        for theme in current_theme_ratings.keys():

            current_rating = current_theme_ratings.get(theme,'No Alerts')
            prior_rating = prior_theme_ratings.get(theme,'No Alerts')
            # prior_rating = "High" # TODO JUST FOR TESTING OVERRIDE
            # print("check 3.6")
            # print(current_rating.lower(),prior_rating.lower())
            if current_rating != prior_rating:
                any_change_flag = True
                current_rating_rank = rating_rank[current_rating.lower()]
                prior_rating_rank = rating_rank[prior_rating.lower()]

                if current_rating_rank < prior_rating_rank:
                    direction = "increased"
                elif current_rating_rank > prior_rating_rank:
                    direction = "decreased"
                else:
                    direction = "changed"

                if theme in ["cyber", "esg"]:
                    continue

                if theme == "supplier":
                    overall_change_flag = True
                    overall_title = f"Rating Change: Overall Rating has {direction} to {current_rating}\n"
                    overall_description = f"Overall Rating has {direction} from {prior_rating} to {current_rating}\n"
                    # Handle separately
                else:
                    description = f"{theme_display_names[theme]} rating has {direction} from {prior_rating} to {current_rating}\n"
                    all_changes.append(description)

        description = ""
        if any_change_flag:
            if overall_change_flag:
                title = overall_title
                if len(all_changes) > 0:
                    description = overall_description + " due to the following risk area ratings: \n\n" + "\n\n".join(all_changes)
            else:
                title = "Rating Change: Risk Areas"
                description = "The following risk area(s) have changed rating, without any impact on overall risk rating: \n\n" + "\n\n".join(all_changes)

            notification = {
                "ens_id": ens_id,
                "session_id": current_session_id,
                "notification_type": NotificationType.RATING_CHANGE,
                "title": title,
                "description": description,
                "theme": "risk_rating",
                "data_value": json.dumps(current_theme_ratings)
            }

            logger.debug("GOT RATING NOTIFICATION")
            logger.debug(json.dumps(notification, indent=4))

        return notification
    else:
        return {}

# Get all current KPIs
# Get all previous KPIs
# For each KPI code in current
# 1. if also in prior:
    # compare data_value
    # check current'
    # add to notification [KPI Title] - Alert
    # add to notification [KPI Title] - Update
# 2. if not in prior
    # entire kpi is new, full KPI is highlighted (?)

## TODO Discuss WHAT DO WE DO IF MULTIPLE WEBHOOKS COME LEADING TO THE SAME ENS_ID (?)