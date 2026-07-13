# app/core/phase1_analysis.py
import json
from http.client import HTTPException

import jwt

from app.core.analysis.graph_database_module.graph_utils import _q1_2
# from app.core.analysis.orbis_submodules.annexure import shareholders_analysis
from app.core.analysis.session_initialisation.session import *
from app.core.analysis.session_initialisation.json_formatted_session_logging import *

from app.core.analysis.analysis_submodules.CYES_analysis import *
from app.core.analysis.analysis_submodules.FSTB_analysis import *
from app.core.analysis.analysis_submodules.LGRK_analysis import *
from app.core.analysis.analysis_submodules.NEWS_analysis import *
from app.core.analysis.analysis_submodules.OVRR_analysis import *
from app.core.analysis.analysis_submodules.OVAL_analysis import *
from app.core.analysis.analysis_submodules.RFCT_analysis import *
from app.core.analysis.analysis_submodules.SOWN_analysis import *
from app.core.analysis.analysis_submodules.CR_analysis import *
from app.core.analysis.analysis_submodules.SAPE_analysis import *
from app.core.analysis.analysis_submodules.COPR_analysis import *
from app.core.analysis.orbis_submodules.COMPANY_orbis import *
from app.core.analysis.orbis_submodules.GRID_orbis import *
from app.core.analysis.orbis_submodules.GRID_byID import *
from app.core.analysis.orbis_submodules.GRID_byNAME import *
from app.core.analysis.orbis_submodules.NEWS import *
from app.core.analysis.analysis_submodules.NEWS_analysis import *
from app.core.analysis.orbis_submodules.MATCH_orbis import *
from app.core.analysis.report_generation_submodules.report import *
from app.core.analysis.report_generation_submodules.json_formatted_report import *
from app.core.analysis.supplier_validation_submodules.supplier_name_validation import *
from app.core.analysis.graph_database_module.configure import *
from app.core.database_session import _ASYNC_ENGINE, SessionFactory
from app.schemas.logger import logger, session_id_var, ens_id_var
from app.core.utils.db_utils import *
from collections import Counter
from app.core.analysis.analysis_submodules.universe import *
import traceback
from app.core.analysis.orbis_submodules.address_validation import *
from app.core.analysis.orbis_submodules.domain_validation import *
from app.core.analysis.orbis_submodules.googleAPI import *
from app.core.analysis.analysis_submodules.domain_analysis import *
from app.core.analysis.analysis_submodules.google_rating import *
from app.core.analysis.orbis_submodules.cyber_validation import *

ENABLE_CONTINUOUS_MONITORING = False # DO NOT CHANGE TO TRUE UNLESS REQUIRED
ENABLE_PRODUCTION_SKIPPING_LOGIC = True  # CHANGE TO FALSE FOR LOCAL TESTING.

def batch_generator(all_items_list, batch_size):
    for i in range(0, len(all_items_list), batch_size):
        yield all_items_list[i: i + batch_size]

def _count_statuses_for_cols(ens_rows: list[dict]) -> dict[str, int]:
    total = len(ens_rows or [])
    completed = failed = skipped = 0
    for r in (ens_rows or []):
        s = (r.get("overall_status") or "").strip().upper()
        if s == STATUS.COMPLETED:
            completed += 1
        elif s == STATUS.FAILED:
            failed += 1
        elif s == STATUS.SKIPPED:
            skipped += 1
    return {
        "total_ens_count": total,
        "completed_ens_count": completed,
        "failed_ens_count": failed,
        "skipped_ens_count": skipped,
    }

async def run_supplier_name_validation(data, session):

    logger.info(f"<<< RUNNING SVP FOR NEW SESSION >>>")
    logger.debug(f"API Data: {data} ")

    try:

        # Get All ENS IDs for Session
        session_id_value = data.get("session_id")
        logger.info(f"SESSION = {session_id_value}")
        data_for_sessionId = await get_dynamic_ens_data("upload_supplier_master_data", required_columns=["all"], ens_id=None, session_id=session_id_value, session=session)

        # Updating the Status value in session_screening_status
        session_status_cols = [{"supplier_name_validation_status": STATUS.IN_PROGRESS}]
        insert_status = await upsert_session_screening_status(session_status_cols, session_id_value, SessionFactory())
        if insert_status.get("status", "") == "failure":
            logger.warning("Failed to UPDATE status for session = IN_PROGRESS, check db_util parameters")

        # 2. Run Name Validation Pipeline Concurrently (In Batches of N Concurrent Suppliers)
        batch_size = 1
        batch_data = batch_generator(data_for_sessionId, batch_size)
        api_response = []
        for nameval_batch in batch_data:
            nameval_tasks = [supplier_name_validation(element, session, search_engine="bing") for element in nameval_batch]
            nameval_batch_result = await asyncio.gather(*nameval_tasks)
            api_response.extend(nameval_batch_result)
            logger.debug("|| output || %s", nameval_batch_result)

        # Run de-duplication for session
        logger.info(f"Performing Name Validation Duplicate Analysis for {session_id_value}")
        await ensid_duplicate_in_session(session_id_value, session)

        # Updating the Status value in session_screening_status
        session_status_cols = [{"supplier_name_validation_status": STATUS.COMPLETED}]
        insert_status = await upsert_session_screening_status(session_status_cols, session_id_value, SessionFactory())
        if insert_status.get("status", "") == "failure":
            logger.warning("Failed to UPDATE status for session = COMPLETED, check db_util parameters")
        else:
            logger.info(f"<<< COMPLETED Name Validation FOR {session_id_value}>>>")

        return {"overall_process_status": STATUS.COMPLETED.value, "supplier_data": api_response}

    except Exception as e:

        logger.error(f"ERROR IN SUPPLIER NAME VALIDATION PIPELINE FOR {session_id_value} ---> {str(e)}")
        # Updating the Status value in session_screening_status
        session_status_cols = [{"supplier_name_validation_status": STATUS.FAILED, "overall_status": STATUS.FAILED}]
        insert_status = await upsert_session_screening_status(session_status_cols, session_id_value, SessionFactory())

        return {"overall_process_status": STATUS.FAILED.value, "supplier_data": []}



async def run_report_generation_standalone(data, session):

    """
    This is the standalone report generation function to be used in its own test endpoint
    Not to be used in deployed analysis pipeline
    :param data:
    :param session: db session
    :return:
    """
    logger.info(f"<<< RUNNING RGC FOR NEW SESSION - STANDALONE CALL FOR ONLY RGC>>>")
    logger.info(f"API Data: {data} ")
    # 1. session initialisation run
    session_id_value = data.get("session_id")
    logger.info(f"SESSION = {session_id_value}")

    # data_for_sessionId = await get_ens_ids_for_session_id("upload_supplier_master_data", session_id=session_id_value, session=session)
    data_for_sessionId = await get_dynamic_ens_data("supplier_master_data", required_columns=["all"],
                                                    ens_id=None, session_id=session_id_value, session=session)  # TODO IDEALLY DONT PULL ALL COLS?
    logger.info("\n\nData for session ID %s", data_for_sessionId)

    # TODO: Confirm if a col exists for this status
    # Update the status message for report generation
    validation = {"screening_analysis_status": STATUS.IN_PROGRESS.value}
    update_status = await update_dynamic_ens_data("session_screening_status", validation, ens_id=None, session_id=session_id_value, session=session)
    if update_status["status"]=="success":
        logger.info("UPDATED status for session = IN_PROGRESS")
    else:
        logger.info("Failed to UPDATE status for session = IN_PROGRESS, check db_util parameters")

    batch_size = 3
    batch_data = batch_generator(data_for_sessionId, batch_size)

    api_response = []
    count = 0
    for nameval_batch in batch_data:
        for element in nameval_batch:
            logger.info(f"\n\nRunning for ens ID: {element}")
            nameval_tasks = [report_generation(element, session, ts_data=None, upload_to_blob=True, session_outputs=True)]
            nameval_batch_result = await asyncio.gather(*nameval_tasks)
            for runs in range(len(nameval_batch_result)):
                process_status, result = nameval_batch_result[runs]
                api_response.append(result)
                if process_status:
                    # TODO: the enum for this needs to be STATUS instead of TruesightStatus
                    temp = {"report_generation_status":STATUS.COMPLETED.value}
                    update_status = await update_dynamic_ens_data("ensid_screening_status", temp, session=session, ens_id=element["ens_id"], session_id=session_id_value)
                else:
                    # TODO: the enum for this needs to be STATUS instead of TruesightStatus
                    temp = {"report_generation_status":STATUS.FAILED.value}
                    update_status = await update_dynamic_ens_data("ensid_screening_status", temp, session=session, ens_id=element["ens_id"], session_id=session_id_value)

    # TODO: again, check if a col exists for this
    validation = {"screening_analysis_status": STATUS.COMPLETED.value}
    update_status = await update_dynamic_ens_data("session_screening_status", validation, ens_id=None, session_id=session_id_value, session=session)
    if update_status["status"]=="success":
        logger.info("UPDATED status for session = COMPLETED")
    else:
        logger.info("Failed to UPDATE status for session = COMPLETED, check db_util parameters")

    return {"overall_process_status": STATUS.COMPLETED.value, "report_data": api_response}

async def run_report_generation_single(data, session):
    logger.info(f"<<< RUNNING RGC FOR NEW SESSION >>>")
    logger.info(f"API Data: {data} ")
    # 1. session initialisation run
    ens_id_value = data.get("ens_id")
    session_id_value = data.get("session_id")
    logger.info(f"SESSION = {session_id_value}")

    # data_for_sessionId = await get_ens_ids_for_session_id("upload_supplier_master_data", session_id=session_id_value, session=session)
    data_for_sessionId = await get_dynamic_ens_data("supplier_master_data", required_columns=["all"],
                                                    ens_id=ens_id_value, session_id=session_id_value, session=session)
    logger.info("\n\nData for session ID %s",data_for_sessionId)

    # TODO: Confirm if a col exists for this status
    # Update the status message for report generation
    validation = {"report_generation_status": STATUS.IN_PROGRESS.value}
    update_status = await update_dynamic_ens_data("session_screening_status", validation, ens_id=None, session_id=session_id_value, session=session)
    if update_status["status"]=="success":
        logger.info("UPDATED status for session = IN_PROGRESS")
    else:
        logger.info("Failed to UPDATE status for session = IN_PROGRESS, check db_util parameters")

    api_response = []
    process_status, result = await report_generation(data_for_sessionId[0], session, ts_data=None, upload_to_blob=True, session_outputs=True)
    api_response.append(result)

    if process_status:
        # TODO: the enum for this needs to be STATUS instead of TruesightStatus
        temp = {"process_status":STATUS.COMPLETED.value}
        update_status = await update_dynamic_ens_data("upload_supplier_master_data", temp, session=session, ens_id=data_for_sessionId[0]["ens_id"], session_id=session_id_value)
    else:
        # TODO: the enum for this needs to be STATUS instead of TruesightStatus
        temp = {"process_status":STATUS.FAILED.value}
        update_status = await update_dynamic_ens_data("upload_supplier_master_data", temp, session=session, ens_id=data_for_sessionId[0]["ens_id"], session_id=session_id_value)

    # TODO: again, check if a col exists for this
    validation = {"report_generation_status": STATUS.COMPLETED.value}
    update_status = await update_dynamic_ens_data("session_screening_status", validation, ens_id=None, session_id=session_id_value, session=session)
    if update_status["status"]=="success":
        logger.info("UPDATED status for session = COMPLETED")
    else:
        logger.info("Failed to UPDATE status for session = COMPLETED, check db_util parameters")

    return {"overall_process_status": STATUS.COMPLETED.value, "report_data": api_response}


async def run_analysis_tasks(data, session):
    """
     Execute all analysis functions concurrently, then run report generation.
    """
    logger.info("--------------- IN ANALYSIS TASKS FUNCTION ----------------------")
    logger.info(data)

    session_id = data.get("session_id")
    ens_id = data.get("ens_id")
    bvd_id = data.get("bvd_id")
    ens_id_var.set(ens_id)

    logger.info("--------------- STARTING ORBIS RETRIEVAL FOR ENS ID----------------------")

    orbis_status = await run_orbis(ens_id, session_id, bvd_id, session)
    logger.info(orbis_status)
    #if basic company data fails or reaches exceptio
    if orbis_status.get("company_data",STATUS.FAILED) == STATUS.FAILED or orbis_status.get("entered_exception", STATUS.COMPLETED)==STATUS.FAILED:
        ens_ids_rows = [{"ens_id": ens_id, "screening_modules_status": STATUS.FAILED, "report_generation_status": STATUS.IN_PROGRESS}]
        insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id, SessionFactory())
        return []
    orbis_status_values = Counter(orbis_status.values())

    # if more than 2 status is failed
    if orbis_status_values[STATUS.FAILED]>5:
        ens_ids_rows = [{"ens_id": ens_id, "screening_modules_status": STATUS.FAILED,"report_generation_status": STATUS.IN_PROGRESS}]
        insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id, SessionFactory())
        return []
    try:
        column_for_org = ['grid_event_sanctions', 'event_sanctions', 'grid_event_bribery_fraud_corruption',
                          'event_bribery_fraud_corruption', 'grid_event_pep', 'event_pep',
                          'grid_event_adverse_media_other_crimes', 'event_adverse_media_other_crimes',
                          'grid_event_adverse_media_reputational_risk', 'event_adverse_media_reputational_risk', 'orbis_news']
        await data_fetching_for_new_and_old_session(ens_id, session_id, column_for_org)
    except:
        logger.error(f"error while finding diff in Grid Data {traceback.format_exc()}")
    try:
        column_for_personnel = ['grid_adverse_media_other_crimes', 'grid_adverse_media_reputational_risk', 'grid_sanctions',
                                'grid_bribery_fraud_corruption', 'grid_pep']
        for column in column_for_personnel:
            await data_fetching_for_new_and_old_session_personel(ens_id, session_id, column)
    except:
        logger.error(f"error while finding diff in Grid Management Data {traceback.format_exc()}")
    try:
        column_for_additional = ["cyber_risk_score", "cyber_date", "implied_cyber_risk_score",
                                 "implied_cyber_risk_score_date", "esg_environmental_rating", "esg_social_rating",
                                 "esg_governance_rating", "esg_overall_rating", "esg_date"]
        await data_fetching_for_new_and_old_session_additional_indicator(ens_id, session_id, column_for_additional)
    except:
        logger.error(f"error while finding diff additonal information {traceback.format_exc()}")
    # Try catch already in function, TODO: add handler Here for Returning Fail Case

    logger.info("--------------- BEGINNING ANALYSIS FOR ENS ID -----------------------------")

    # List of analysis functions to run concurrently
    analysis_tasks = [
        company_profile(data, SessionFactory()),
        orbis_news_analysis(data,SessionFactory()),
        website_analysis(data, SessionFactory()),
        esg_analysis(data, SessionFactory()),
        cyber_analysis(data, SessionFactory()),
        cyber_analysis_api(data, SessionFactory()),
        # shareholders_analysis(data, session),
        main_financial_analysis(data, SessionFactory()),
        legal_analysis(data,SessionFactory()),
        ownership_analysis(data, SessionFactory()),
        sanctions_analysis(data,SessionFactory()),
        pep_analysis(data,SessionFactory()),
        adverse_media_analysis(data,SessionFactory()),
        adverse_media_reputation_risk(data, SessionFactory()),
        bribery_corruption_fraud_analysis(data,SessionFactory()),
        regulatory_analysis(data, SessionFactory()),
        sown_analysis(data, SessionFactory()),
        country_risk_analysis(data,SessionFactory()),
        ownership_flag(data,SessionFactory()),
        domain_analysis(data,SessionFactory()),
        google_rating_analysis(data,SessionFactory())
    ]

    try:
        analysis_results = await asyncio.gather(*analysis_tasks)

        # # Store shareholders data for reporting
        # sh_result = next((r for r in analysis_results if r["analysis_type"] == "shareholders"), None)
        # if sh_result and sh_result["annexure_ready"]:
        #     data["shareholders"] = sh_result["data"]

        ovrr_result = await ovrr(data, SessionFactory())
        logger.info(ovrr_result)
        # / --- UPDATE ENSID STATUS
        ens_ids_rows = [{"ens_id": ens_id, "screening_modules_status": STATUS.COMPLETED}]
        insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id, SessionFactory())
        logger.debug(insert_status)

    except Exception as e:
        ens_ids_rows = [{"ens_id": ens_id, "screening_modules_status": STATUS.FAILED}]
        insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id, SessionFactory())
        logger.debug(insert_status)
        # why is overall status failed
        ens_ids_rows = [{"ens_id": ens_id, "overall_status": STATUS.FAILED}]
        insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id, SessionFactory())

        return []
    try:
        #finding difference in data and rating
        required_column=['last_session_id']
        last_session_id = await get_dynamic_ens_data("entity_universe",required_column,ens_id,session=session)
        if len(last_session_id)>0:
            last_session_id = last_session_id[0].get('last_session_id','')
            logger.debug(f"last session id {last_session_id}")
        else:
            last_session_id=''
        if last_session_id:
            all_diffs={}
            all_notification=[]
            annexure = ''
            all_diffs,diff_notifications,annexure=await process_kpi_diffs(ens_id=ens_id,current_session_id=session_id,prior_session_id=last_session_id,session=session)
            rating_notification=await generate_rating_change_notifications(ens_id,session_id,last_session_id,session)
            logger.debug(f"all diff ---> {len(all_diffs)}")
            logger.debug(f"all notifications ---> {len(diff_notifications)}")
            logger.debug(type(diff_notifications))
            logger.debug(type(rating_notification))
            if rating_notification:
                all_notification.append(rating_notification)
            if diff_notifications:
                all_notification+=diff_notifications
        else:
            all_diffs={}
            all_notification=[]
            annexure = ''
    except Exception as e:
        logger.error(f"ERROR WHILE IDENTIFYING DIFFERENCES IN DATA OR RATING: {e} \n {traceback.format_exc()}")

        ens_ids_rows = [{"ens_id": ens_id, "screening_modules_status": STATUS.FAILED, "overall_status": STATUS.FAILED}]
        insert_status = await upsert_ensid_screening_status(
            ens_ids_rows, session_id, SessionFactory()
        )
        logger.debug(f"[{ens_id}] upsert_ensid_screening_status FAILED returned: {insert_status}")

        return []
    try:
        logger.info(f"[{ens_id}] Starting report generation for session_id={session_id}")

        ens_ids_rows = [{"ens_id": ens_id, "report_generation_status": STATUS.IN_PROGRESS}]
        logger.info(f"[{ens_id}] Marking report status as IN PROGRESS")
        insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id, SessionFactory())
        logger.debug(f"[{ens_id}] UPSERT OF ENSID SCREENING STATUS RETURNED {insert_status}")

        logger.info(f"[{ens_id}] Running report_generation_poc...")
        report_result, status = await report_generation_poc(
            data, session, all_diffs, annexure, ts_data=None, upload_to_blob=True, save_locally=False
        )
        logger.info(f"[{ens_id}] report_generation_poc completed with status={status}")

        logger.info(" ---------- TPRP HAS BEEN DISABLED ------------ ")
        # logger.info(f"[{ens_id}] Formatting JSON report...")
        # report_json = await format_json_report(data, SessionFactory())
        # json_file_name = f"{ens_id}/report.json"
        # logger.info(f"[{ens_id}] Uploading report.json to R2 storage: {json_file_name}")
        # upload_to_r2(report_json, json_file_name, session_id)

        if status == 200:
            logger.info(f"[{ens_id}] Report generation SUCCESS — updating status to COMPLETED")
            ens_ids_rows = [
                {"ens_id": ens_id, "report_generation_status": STATUS.COMPLETED, "overall_status": STATUS.COMPLETED}]
            insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id, SessionFactory())
            logger.debug(f"[{ens_id}] upsert_ensid_screening_status COMPLETED returned: {insert_status}")

            logger.info(f"[{ens_id}] Updating entity_universe_table...")
            response = await update_entity_universe_table(ens_id, session_id, session)
            logger.debug(f"[{ens_id}] update_entity_universe_table returned: {response}")

            if last_session_id and all_notification:
                logger.info(f"[{ens_id}] Inserting notifications...")
                output = await insert_notification_data("notification", all_notification, ens_id, session_id, session)
                logger.debug(f"[{ens_id}] insert_notification_data returned: {output}")

        else:
            logger.warning(f"[{ens_id}] Report generation FAILED in report_generation_poc — updating status to FAILED")
            ens_ids_rows = [
                {"ens_id": ens_id, "report_generation_status": STATUS.FAILED, "overall_status": STATUS.FAILED}]
            insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id, SessionFactory())
            logger.debug(f"[{ens_id}] upsert_ensid_screening_status FAILED returned: {insert_status}")

        logger.info(f"[{ens_id}] Report flow completed successfully — returning results")
        return analysis_results + [report_result]  # TODO Neaten

    except Exception as e:

        logger.error(f"ERROR RUNNING:{ens_id}, {str(e)}")

        ens_ids_rows = [{"ens_id": ens_id, "report_generation_status": STATUS.FAILED, "overall_status": STATUS.FAILED}]
        insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id, SessionFactory())

        return []

    # TODO: THIS IS WHERE THE UNIVERSE TABLE WILL BE UPDATED
    # once report gen is successful-> 1) update universe table, 2) save kpi notifications to db, 3) save rating notification to db
    # logger.debug("----------------- Running Universe Update Functions")
    #
    # status = await update_entity_universe_table(ens_id, session_id, session)
    #
    # return analysis_results + [report_result]  # TODO Neaten


async def run_orbis(ens_id, session_id, bvd_id, session):
    """
    :param ens_id:
    :param session_id:
    :param bvd_id:
    :param session:
    :return:
    """
    output_json = {}
    try:
        data = {
            "session_id": session_id,
            "ens_id": ens_id,
            "bvd_id": bvd_id
        }

        logger.info("PERFORMING ORBIS RETRIEVAL FOR %s", ens_id)

        ens_id_row = [{"ens_id": ens_id, "orbis_retrieval_status": STATUS.IN_PROGRESS}]
        insert_status = await upsert_ensid_screening_status(ens_id_row, session_id, SessionFactory())


        # 1. ORBIS COMPANY - most of the main fields in external_supplier_data (FOR COMPANY LEVEL)
        company_result = await orbis_company(data, session)
        logger.info(company_result)
        if company_result["status"] == 'failed':
            logger.error(f"ERROR IN ORBIS COMPANY DATA RETRIEVAL FOR {ens_id}")
            status_ens_id = [
                {"ens_id": ens_id, "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
            insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
            output_json["company_data"]=STATUS.FAILED
            # return output_json
        else:
            output_json["company_data"] = STATUS.COMPLETED
        try:
            await data_fetching_for_new_and_old_session_orbis_management(ens_id,session_id)
        except:
            logger.error(f"error while finding diff in orbis management {traceback.format_exc()}")



        # 2. ORBIS GRID - fields which are "event_" in external_supplier_data (FOR COMPANY LEVEL)
        orbis_grid_result = await orbis_grid_search(data, session)
        if orbis_grid_result["status"] == 'failed':
            logger.error(f"ERROR IN ORBIS GRID RETRIEVAL FOR {ens_id}")
            status_ens_id = [
                {"ens_id": ens_id, "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
            insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
            # return {"company_result": STATUS.FAILED, "orbis_grid_result": STATUS.FAILED}
            output_json["orbis_grid_organization"] = STATUS.FAILED
        else:
            output_json["orbis_grid_organization"] = STATUS.COMPLETED
        orbis_grid_adv_indicator = orbis_grid_result.get("adv_count", 0)

        # 3A. GRID-GRID by ID <may not work> (FOR COMPANY LEVEL)
        grid_grid_result = await gridbyid_organisation(data, session)
        grid_grid_data_indicator = grid_grid_result.get("data", False)
        grid_grid_adv_indicator = grid_grid_result.get("adv_count", 0)
        grid_grid_msg = grid_grid_result.get("message", "")
        if grid_grid_result["status"] == 'failed':
            logger.error(f"ERROR IN GRID BY ID RETRIEVAL FOR {ens_id}")
            status_ens_id = [
                {"ens_id": ens_id, "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
            insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
            output_json["grid_grid_id_organization"] = STATUS.FAILED
        else:
            output_json["grid_grid_id_organization"] = STATUS.COMPLETED

        grid_grid_id_adv_indicator = 0
        if grid_grid_msg == "No event for the particular entity" or not grid_grid_data_indicator:
            logger.info("No Initial GRID")
            grid_grid_id_result = await gridbyname_organisation(data, session)
            grid_grid_id_adv_indicator = grid_grid_id_result.get("adv_count", 0)
            if grid_grid_id_result["status"] == 'failed':
                logger.error(f"ERROR IN GRID BY NAME RETRIEVAL FOR {ens_id}")
                status_ens_id = [
                    {"ens_id": ens_id, "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
                insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
                output_json["grid_grid_name_organization"] = STATUS.FAILED
            else:
                output_json["grid_grid_name_organization"] = STATUS.COMPLETED
        # 3C. (FALLBACK) ORBIS NEWS
            logger.debug("total: %d %d %d total sum: %d", int(orbis_grid_adv_indicator), int(grid_grid_adv_indicator), int(grid_grid_id_adv_indicator), int(orbis_grid_adv_indicator) + int(grid_grid_adv_indicator) + int(grid_grid_id_adv_indicator))
        if int(orbis_grid_adv_indicator) + int(grid_grid_adv_indicator) + int(grid_grid_id_adv_indicator) == 0:
            try:
                    logger.info("-------- Running: other news findings")
                    orbis_news_result = await orbis_news_search(data,session)
                    orbis_news_data_indicator = orbis_news_result.get("data", False)
                    if orbis_news_result["status"] == 'failed':
                        logger.error(f"ERROR IN ORBIS NEWS RETRIEVAL FOR {ens_id}")
                        status_ens_id = [
                            {"ens_id": ens_id,
                             "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
                        insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
                        output_json["orbis_news"] = STATUS.FAILED
                    else:
                        output_json["orbis_news"] = STATUS.COMPLETED

                    if orbis_news_data_indicator == False:
                        logger.info("---------- Running: 2 Sents")
                        # two_cents_result=await newsscreening_main_company(data, session)
                        # two_cents_result = await newsscreening_main_company_throttle(data, session)
                    else:
                        logger.info("Skipping: 2 Sents")
            except Exception as e:
                    logger.error(f"ERROR RUNNING 2 SENTS ------------- {str(e)}")
        else:
            logger.debug("total: %d %d %d total sum: %d", int(orbis_grid_adv_indicator), int(grid_grid_adv_indicator), int(grid_grid_id_adv_indicator), int(orbis_grid_adv_indicator) + int(grid_grid_adv_indicator) + int(grid_grid_id_adv_indicator))
            logger.info("Skipping: other news findings")
            output_json["orbis_news"] = STATUS.COMPLETED

        # orbis_news_result = await orbis_news_search(data, session)
        # 4. (FALLBACK) GRID-GRID by NAME (FOR PERSON LEVEL)
        grid_grid_result_person = await gridbyname_person(data, session)
        if grid_grid_result_person["status"] == 'failed':
            logger.error(f"ERROR IN GRID PERSONNEL RETRIEVAL FOR {ens_id}")
            status_ens_id = [
                {"ens_id": ens_id,
                 "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
            insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
            output_json["grid_grid_name_personnel"] = STATUS.COMPLETED

        #check difference with old session_id
        # Check combined result
        # orbis_result = {"company_result": company_result["status"], "orbis_grid_result": orbis_grid_result["status"]} #update more here if needed
        orbis_result = {}
        # / --- UPDATE ENSID STATUS

        #5. DOMAIN VALIDATION
        try:
            web_result = await domain_validation(data, session)
            print("webresult", web_result)
            if web_result["status"] == 'failed':
                logger.error(f"ERROR IN WEB DOMAIN RETRIEVAL FOR {ens_id}")
                output_json["web_data"] = STATUS.FAILED
                status_ens_id = [
                    {"ens_id": ens_id,
                     "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
                insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
            else:
                output_json["web_data"] = STATUS.COMPLETED
        except Exception as e:
            traceback.print_exc()
            logger.error(f"ERROR IN EXTRACTING WEB INFO FOR {ens_id}")
            output_json["web_data"] = STATUS.FAILED

        # 6. Google Review
        try:
            san_result = await google_rating_screening(data, session)
            if san_result["status"] == 'failed':
                logger.error(f"ERROR IN Google Review RETRIEVAL FOR {ens_id}")
                output_json["review_data"] = STATUS.FAILED
                status_ens_id = [
                    {"ens_id": ens_id,
                     "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
                insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
            else:
                output_json["review_data"] = STATUS.COMPLETED
        except Exception as e:
            traceback.print_exc()
            logger.error(f"ERROR IN EXTRACTING Google Review INFO FOR {ens_id}")
            output_json["review_data"] = STATUS.FAILED

        # 7. google address
        try:
            san_result = await google_address_validation(data, session)
            if san_result["status"] == 'failed':
                logger.error(f"ERROR IN Google Address Validation RETRIEVAL FOR {ens_id}")
                output_json["add_data"] = STATUS.FAILED
                status_ens_id = [
                    {"ens_id": ens_id,
                     "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
                insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
            else:
                output_json["add_data"] = STATUS.COMPLETED
        except Exception as e:
            traceback.print_exc()
            logger.error(f"ERROR IN EXTRACTING Google Address Validation INFO FOR {ens_id}")
            output_json["add_data"] = STATUS.FAILED

        # 8. google photos
        try:
            san_result = await google_photo_screening(data, session)
            if san_result["status"] == 'failed':
                logger.error(f"ERROR IN Google Photo RETRIEVAL FOR {ens_id}")
                output_json["photo_data"] = STATUS.FAILED
                status_ens_id = [
                    {"ens_id": ens_id,
                     "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
                insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
            else:
                output_json["photo_data"] = STATUS.COMPLETED
        except Exception as e:
            traceback.print_exc()
            logger.error(f"ERROR IN EXTRACTING Google Photo INFO FOR {ens_id}")
            output_json["photo_data"] = STATUS.FAILED

        # 9. Cyber Risk
        try:
            san_result = await cyber_risk_validation(data, session)
            if san_result["status"] == 'failed':
                logger.error(f"ERROR IN Google Address Validation RETRIEVAL FOR {ens_id}")
                output_json["add_data"] = STATUS.FAILED
                status_ens_id = [
                    {"ens_id": ens_id,
                     "orbis_retrieval_status": STATUS.FAILED}]  # must be list even though just 1 row
                insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
            else:
                output_json["add_data"] = STATUS.COMPLETED
        except Exception as e:
            traceback.print_exc()
            logger.error(f"ERROR IN EXTRACTING Google Address Validation INFO FOR {ens_id}")
            output_json["add_data"] = STATUS.FAILED

        status_ens_id = [{"ens_id": ens_id, "orbis_retrieval_status": STATUS.COMPLETED}] #must be list even though just 1 row
        insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())

        return output_json

    except Exception as e:

        logger.error(f"ERROR IN ORBIS RETRIEVAL FOR {ens_id}: {str(e)}")

        # / --- UPDATE ENSID STATUS
        status_ens_id = [{"ens_id": ens_id, "orbis_retrieval_status": STATUS.FAILED}] #must be list even though just 1 row
        insert_status = await upsert_ensid_screening_status(status_ens_id, session_id, SessionFactory())
        output_json["entered_exception"]=STATUS.FAILED
        return output_json


def trigger_continuous_bulk(data: List[Dict[str, Any]], auth_token: str):
    url = get_settings().urls.application_backend + "/monitoring/continuousbulk/"
    print("THE URL LOOKS LIKE THIS:", url)
    payload = {"data": data}

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        print("THE RESPONSE IS ", response)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

async def trigger_continuous_monitoring_pipeline(session_id_value, session):

    try:
        logger.info(f"[{session_id_value}] Starting continuous monitoring pipeline...")

        ens_id_statuses = await get_all_ensid_screening_status_static(session_id_value, session)
        bulk_data = [
            {"ens_id": row["ens_id"], "status": True}
            for row in ens_id_statuses
            if row["overall_status"] == STATUS.COMPLETED
        ]

        try:
            jwt_token = create_jwt_token("application_orchestration", "development")
            auth_token = jwt_token.access_token
        except Exception as e:
            logger.error(f"Error generating JWT token: {str(e)}")
            raise

        if bulk_data:
            cm_result = trigger_continuous_bulk(bulk_data, auth_token)
            logger.info(f"[{session_id_value}] Triggered Continuous Monitoring Bulk: {cm_result}")
            return {"success": True, "result": cm_result, "processed_count": len(bulk_data)}
        else:
            logger.info(f"[{session_id_value}] No completed ENS IDs found. Skipping Continuous Monitoring.")
            return {"success": True, "result": "No completed ENS IDs", "processed_count": 0}

    except Exception as e:
        logger.error(f"[{session_id_value}] Failed triggering Continuous Monitoring Bulk: {str(e)}")
        return {"success": False, "error": str(e)}

async def run_analysis(data, session):

    session_id_value = data.get("session_id")
    session_id_var.set(session_id_value)

    logger.info(f"STARTING ANALYSIS FOR SESSION ID: {session_id_value}")
    result = await ensid_screening_status_nonrepetitive(session_id_value, ENABLE_PRODUCTION_SKIPPING_LOGIC, session)
    skipped_ids = result.get("skipped_ids", [])

    all_ens_ids = await get_ens_ids_for_session_id("supplier_master_data",["ens_id", "session_id", "bvd_id", "name", "country", "national_id", "address"], session_id_value, session)
    all_ens_ids = [row for row in all_ens_ids if row["ens_id"] not in skipped_ids]

    # Config flag for continuous monitoring
    enable_continuous_monitoring = data.get("enable_continuous_monitoring", ENABLE_CONTINUOUS_MONITORING)

    # / --- UPDATE SESSIONID STATUS TO STARTED
    session_status_cols = [{"screening_analysis_status": STATUS.IN_PROGRESS, "overall_status": STATUS.IN_PROGRESS}]
    insert_status = await upsert_session_screening_status(session_status_cols, session_id_value, SessionFactory())
    # print(insert_status)  # TODO CHECK

    try:
        screening_batch_size = 1
        screening_batches = batch_generator(all_ens_ids, screening_batch_size)
        screening_retrieval_status = []
        # inbuilt_additional_delay_frequency = 15 / (screening_batch_size)
        inbuilt_additional_delay_frequency = 20
        counter = 0
        throttle_flag = False
        for screening_batch in screening_batches:
            counter += 1
            # / --- UPDATE ENSID STATUS
            ens_ids_rows = [{**{"ens_id": entry["ens_id"]}, "screening_modules_status": STATUS.IN_PROGRESS} for entry in screening_batch]
            insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id_value, SessionFactory())
            # print(insert_status)

            # / --- RUN SCREENING TASKS FOR BATCH
            screening_tasks = [run_analysis_tasks(entry, SessionFactory()) for entry in screening_batch]
            screening_batch_result = await asyncio.gather(*screening_tasks)
            screening_retrieval_status.extend(screening_batch_result)
            logger.debug("|| output || %s", screening_batch_result)

            try:
                if counter % inbuilt_additional_delay_frequency == 0:
                    if throttle_flag:
                        sleep_time = random.randint(300, 600)
                    else:
                        sleep_time = random.randint(60, 300)
                    logger.warning(f"Completed {counter} Suppliers - Throttling: Awaiting Delay for {sleep_time} Seconds .... ")
                    await asyncio.sleep(sleep_time)
                    logger.info("Throttle Completed")
            except Exception as e:
                logger.warning(f"Issue in interval throttle {str(e)}")

        ens_id_statuses = await get_dynamic_ens_data("ensid_screening_status",["ens_id", "screening_modules_status", "orbis_retrieval_status","report_generation_status", "overall_status"],
            None, session_id_value, SessionFactory())

        inprogress_ids = [
            row["ens_id"]
            for row in ens_id_statuses
            if any(
                row[col] == STATUS.IN_PROGRESS
                for col in ["screening_modules_status", "orbis_retrieval_status",
                            "report_generation_status", "overall_status"]
                if row.get(col) is not None
            )
        ]
        if inprogress_ids:
            update_rows = [
                {
                    "ens_id": ens_id,
                    "overall_status": STATUS.FAILED,
                }
                for ens_id in inprogress_ids
            ]
            await upsert_ensid_screening_status(update_rows, session_id_value, SessionFactory())
            await session.commit()
            logger.warning(f"[{session_id_value}] Converted {len(inprogress_ids)} ENSIDs "
                           f"from IN_PROGRESS → FAILED")

        ens_id_statuses = await get_dynamic_ens_data("ensid_screening_status",["ens_id", "overall_status"],None, session_id_value, session)
        statuses = [row["overall_status"] for row in ens_id_statuses]

        # Finalize session status
        if all(s == STATUS.FAILED for s in statuses):
            # Case 1: All failed
            session_status_cols = [
                {"screening_analysis_status": STATUS.FAILED, "overall_status": STATUS.FAILED}
            ]
        elif all(s == STATUS.COMPLETED for s in statuses):
            # Case 2: All completed successfully
            session_status_cols = [
                {"screening_analysis_status": STATUS.COMPLETED, "overall_status": STATUS.COMPLETED}
            ]
        elif all(s == STATUS.SKIPPED for s in statuses):
            # Case 3: All skipped
            session_status_cols = [
                {"screening_analysis_status": STATUS.SKIPPED, "overall_status": STATUS.SKIPPED}
            ]
        else:
            # Case 3: Mixed state (some failed, some completed)
            session_status_cols = [
                {"screening_analysis_status": STATUS.COMPLETED, "overall_status": STATUS.COMPLETED}
            ]

        insert_status = await upsert_session_screening_status(session_status_cols, session_id_value, SessionFactory())
        logger.debug(f"[{session_id_value}] Updated session status: {insert_status}")

        # PERFORM ADDITIONAL VALIDATION / SUMMARIES HERE (?)
        log_json = await format_json_log(session_id_value, SessionFactory())
        log_json_file_name="output_log.json"
        # upload_to_azure_blob(log_json,log_json_file_name,session_id_value)
        upload_to_r2(log_json,log_json_file_name,session_id_value)
        log_csv= await format_csv_report(session_id_value,SessionFactory())
        log_csv_file_name="name_validation_result.csv"
        # upload_to_azure_blob(log_csv, log_csv_file_name, session_id_value)
        upload_to_r2(log_csv, log_csv_file_name, session_id_value)
        
        trigger_graph = False
        if trigger_graph:
            try: 
                fallback_client_id = "5b638302-73cb-4a69-b76d-1efa5c00797a"

                client_id = None
                
                if client_id is None:
                    logger.warning(f"No Client ID passed, using fallback {fallback_client_id}")
                    client_id = fallback_client_id

                if client_id == "string":
                    logger.warning(f"No Client ID passed, using fallback {fallback_client_id}")
                    client_id = fallback_client_id

                await _q1_2(session, client_id, session_id_value)
            except Exception as e:
                _tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                logger.error(_tb)
                raise HTTPException(status_code=500, detail=f"Error generating default graph: {_tb}")

        # --- TRIGGER CONTINUOUS MONITORING BULK
        if enable_continuous_monitoring:
            cm_result = await trigger_continuous_monitoring_pipeline(session_id_value, session)
            logger.info(f"[{session_id_value}] Continuous monitoring Setup result: {cm_result}")
        else:
            logger.info(f"[{session_id_value}] Continuous monitoring Setup Disabled. Skipping config pipeline.")

    except Exception as e:
        logger.error(f"ERROR IN ANALYSIS PIPELINE: {str(e)}")

        session_status_cols = [{"screening_analysis_status": STATUS.FAILED, "overall_status": STATUS.FAILED}]
        insert_status = await upsert_session_screening_status(session_status_cols, session_id_value, SessionFactory())
        # print(insert_status)
    finally:
        # Update last_scheduled_date only if source = 'PD'
        try:
            async with SessionFactory() as session:  # ensures proper close
                # Do aggrigation of ens_ids find : total_count::int, completed_count::int, failed_count::int, skipped_count::int   from public.ensid_screening_status -> overall_status, upsert this info into public.session_screening_status for that respective session_id
                logger.info(f"count : Aggrigation of ens_ids find {session_id_value}")

                # 1) Fetch ENS rows for session
                ens_rows = await get_dynamic_ens_data(
                    "ensid_screening_status",
                    required_columns=["all"],
                    ens_id=None,
                    session_id=session_id_value,
                    session=session,
                )
                logger.info(f"count : Fetch ENS rows for session {ens_rows}")
                # 2) Compute counts
                counts = _count_statuses_for_cols(ens_rows)
                logger.info(f"count : Compute counts {counts}")
                # 3) Build payload for your EXISTING upsert (unchanged)
                session_status_cols = [{
                    "total_ens_count": counts["total_ens_count"],
                    "completed_ens_count": counts["completed_ens_count"],
                    "failed_ens_count": counts["failed_ens_count"],
                    "skipped_ens_count": counts["skipped_ens_count"],
                }]
                logger.info(f"count : Build payload for your EXISTING upsert {counts}")
                # 4) Call your existing upsert (unchanged)
                trigger_response = await upsert_session_screening_status(
                    session_status_cols,
                    session_id_value,
                    session
                )
                logger.info(f"count : Call your existing upsert {trigger_response}")


        except Exception:
            logger.exception("Failed updating periodic last/next scheduled date")

    return []


async def get_default_graph(session):
    status = await default_graph(session)
    if status["status"] == 'pass':
        return {"graph": STATUS.COMPLETED}
    elif status["status"] == 'fail':
        return {"graph": STATUS.FAILED}
