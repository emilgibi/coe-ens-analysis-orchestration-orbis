from app.core.utils.db_utils import *
from app.core.database_session import SessionFactory
from app.schemas.logger import logger
import traceback
import json

async def data_fetching_for_new_and_old_session(ens_id, present_session_id, columns):
    session = SessionFactory()

    # fetch old session id
    required_column = ['last_session_id']
    last_session_id = await get_dynamic_ens_data("entity_universe", required_column, ens_id, session_id=None, session=session)
    logger.debug(f"Org - last session id: {last_session_id}")
    if len(last_session_id)==0:
        logger.info(f'org - No session Id Found')
        return True
    last_session_id=last_session_id[0]
    last_session_id=last_session_id.get('last_session_id','0') or '0'
    if last_session_id == '0':
        logger.info(f'org - No session Id Found')
        return True
    for column in columns:
        columns_to_insert = {}
        try:
            logger.info(f'org - checking diff for columns - {column}')
            # fetch for new session_id
            retrieved_data = await get_dynamic_ens_data("external_supplier_data", [f'{column}'], ens_id,
                                                        present_session_id, session)
            new_data = retrieved_data[0].get(f'{column}', [])
            logger.debug("Org - New Data Retrieved")

            # fetch for old session_id
            retrieved_data = await get_dynamic_ens_data("external_supplier_data", [f'{column}'], ens_id,
                                                        last_session_id, session)
            old_data = retrieved_data[0].get(f'{column}', [])
            logger.debug("Org - Old Data Retrieved")
            # logger.info(f"for {column} the no of old data - {len(old_data)} and new_data - {len(new_data)}")

            # identify the column where old data are missing
            combined_dict = merge_if_diff(old_data,new_data)
            if len(combined_dict) > 0:
                logger.info(f"Org - found difference in {column}")
                columns_to_insert[f'{column}'] = combined_dict
            else:
                logger.info(f"Org - No difference in {column}")
        except:
            logger.error(f"Error while processing diff in {column}  - {traceback.format_exc()}")

        # save all the changed column to db
        if columns_to_insert:
            row_to_insert=[columns_to_insert]
            status = await upsert_dynamic_ens_data("external_supplier_data",row_to_insert,ens_id,present_session_id,session)
        logger.debug("Done")
        logger.info(f"Org - completed diff for column- {column}")

    return True


async def data_fetching_for_new_and_old_session_personel(ens_id, present_session_id, column):
    logger.info(f'person - checking diff for columns - {column}')
    session = SessionFactory()
    # fetch old session id
    required_column = ['last_session_id']
    last_session_id = await get_dynamic_ens_data("entity_universe", required_column, ens_id, session_id=None, session=session)
    if len(last_session_id) == 0:
        logger.info(f'Person - No session Id Found')
        return True
    last_session_id = last_session_id[0].get('last_session_id','0') or '0'
    if last_session_id == '0':
        return True
    logger.debug(f"Person - last session id: {last_session_id}")
    required_columns = [f"{column}", "contact_id"]
    # fetch data for new session_id
    retrieved_data = await get_dynamic_ens_data("grid_management", required_columns, ens_id, present_session_id,
                                                session)
    new_data=retrieved_data
    # print(new_data)
    logger.debug("Person - New Data Retrieved")
    logger.debug(new_data)

    # fetch data for old session_id
    retrieved_data = await get_dynamic_ens_data("grid_management", required_columns, ens_id, last_session_id,
                                                session)
    old_data = retrieved_data
    logger.debug("Person - Old Data Retrieved")

    # identify the column where old data are missing
    for old_personal in old_data:
        for new_personal in new_data:
            if old_personal.get('contact_id',None)==new_personal.get('contact_id',None):
                columns_to_insert = {}
                logger.debug(f"\t old data -  {old_personal.get(f'{column}')}")
                logger.debug(f"\t new data - {new_personal.get(f'{column}')}")
                combined_dict = merge_if_diff(old_personal.get(f'{column}',[]) or [], new_personal.get(f'{column}',[]) or [])
                if len(combined_dict) > 0 :
                    logger.info(f"Person - found difference in {column} for {new_personal.get('contact_id')}")
                    columns_to_insert[f'{column}'] = combined_dict
                    status = await upsert_dynamic_management_data('grid_management', [columns_to_insert], ens_id,
                                                                  present_session_id, new_personal.get('contact_id'),
                                                                  session)
    missing_rows = merge_if_diff_personnels(old_data,new_data)
    if len(missing_rows):
        logger.info(f"Person - Missing Rows Identified for {column}")
        logger.debug(missing_rows)
        for row in missing_rows:
            status = await upsert_dynamic_management_data('grid_management', [row], ens_id,
                                                          present_session_id, row.get('contact_id'),
                                                          session)
    logger.info(f"Person - completed diff for all grid columns")
    return True


def merge_if_diff(a, b):
    set_a = {dict_to_hashable(d) for d in a if isinstance(d, dict)} if a else set()
    set_b = {dict_to_hashable(d) for d in b if isinstance(d, dict)} if b else set()
    logger.debug(f"{len(set_a),len(set_b)}")
    diff = set_a - set_b
    if diff:
        logger.debug(f"------->old{set_a}")
        logger.debug(f"------->new{set_b}")
        combined = set_a | set_b
        logger.debug(len(combined))
        return [hashable_to_dict(items) for items in combined]
    return []

def merge_if_diff_orbis_management(a, b):
    a = a or []
    b = b or []
    if len(a)>0:
        ids_b = [d.get("id") for d in b if "id" in d]
        missing_data = [d for d in a if d.get("id") not in ids_b]

        if missing_data:
            logger.info("found missing management")
            return b + missing_data
        else:
            logger.info("no diff in management")
    return []

def merge_if_diff_personnels(a, b):
    a = a or []
    b = b or []
    logger.debug(f"--> row {len(a)}, {len(b)}")
    if len(a)>0:
        ids_b = [d.get("contact_id") for d in b if "contact_id" in d]
        missing_data = [d for d in a if d.get("contact_id") not in ids_b]

        if missing_data:
            logger.info("found missing row in grid management")
            return missing_data
        else:
            logger.info("no new management to be added")
    return []


async def data_fetching_for_new_and_old_session_additional_indicator(ens_id, present_session_id, columns):
    session = SessionFactory()
    columns_to_insert = {}

    # fetch old session id
    required_column = ['last_session_id']
    last_session_id = await get_dynamic_ens_data("entity_universe", required_column, ens_id, session_id=None, session=session)
    if len(last_session_id) == 0:
        logger.info(f'org - No session Id Found')
        return True
    logger.debug(f"Org - last session id: {last_session_id}")
    last_session_id=last_session_id[0]
    last_session_id=last_session_id.get('last_session_id','0') or '0'
    if last_session_id == '0':
        return True
    for column in columns:
        logger.info(f'org - checking diff for columns - {column}')
        # fetch for new session_id
        retrieved_data = await get_dynamic_ens_data("external_supplier_data", [f'{column}'], ens_id,
                                                    present_session_id, session)
        new_data = retrieved_data[0].get(f'{column}', '')
        logger.debug(f"new data - {new_data}")
        logger.debug("Org - New Data Retrieved")

        if new_data:
            continue
        else:
            # fetch for old session_ids
            retrieved_data = await get_dynamic_ens_data("external_supplier_data", [f'{column}'], ens_id,
                                                        last_session_id, session)
            old_data = retrieved_data[0].get(f'{column}', '')
            logger.debug(f"old data - {old_data}")
            logger.debug("Org - Old Data Retrieved")
            if old_data:
                logger.info(f"Org - Rewriting {column}")
                columns_to_insert[f'{column}'] = old_data
            else:
                logger.info(f"Org - Not rewriting in {column}")
                continue

    # save all the changed column to db
    if columns_to_insert:
        columns_to_insert=[columns_to_insert]
        status = await upsert_dynamic_ens_data("external_supplier_data",columns_to_insert,ens_id,present_session_id,session)
    logger.debug("Done")
    logger.info(f"Org - completed diff for all Additional Information")
    return True

async def data_fetching_for_new_and_old_session_orbis_management(ens_id, present_session_id):
    logger.info(f'org - checking diff for columns - management')

    session = SessionFactory()
    columns_to_insert={}

    # fetch old session id
    required_column = ['last_session_id']
    last_session_id = await get_dynamic_ens_data("entity_universe", required_column, ens_id, session_id=None, session=session)
    if len(last_session_id) == 0:
        logger.info(f'org - No session Id Found')
        return True
    last_session_id = last_session_id[0].get('last_session_id','0') or '0'
    if last_session_id == '0':
        return True
    logger.debug(f"Person - last session id: {last_session_id}")

    # fetch new data
    required_columns=['management']
    retrieved_data = await get_dynamic_ens_data("external_supplier_data", required_columns, ens_id, present_session_id,
                                                session)
    new_data = retrieved_data[0].get('management', []) or []
    logger.debug("Org - New Data Retrieved")

    # fetch data for old session_id
    retrieved_data = await get_dynamic_ens_data("external_supplier_data", required_columns, ens_id, last_session_id,
                                                session)
    old_data = retrieved_data[0].get('management',[]) or []
    logger.debug("Person - Old Data Retrieved")

    # identify the column where old data are missing
    # logger.info(f"for management the no of old data - {len(old_data)} and new_data - {len(new_data)}")
    combined_dict = merge_if_diff_orbis_management(old_data, new_data)
    if len(combined_dict) > 0:
        logger.info(f"Org - found difference in management")
        columns_to_insert['management'] = combined_dict
        try:
            status = await upsert_dynamic_ens_data("external_supplier_data", [columns_to_insert], ens_id, present_session_id,
                                                   session)
        except Exception as e:
            logger.error(f"Error in data_fetching_for_new_and_old_session_orbis_management while inserting to db- {str(e)}")
    else:
        logger.info(f"Org - No difference in management")
    logger.debug("Done")
    return True


def dict_to_hashable(d):
    """Convert dict into a hashable frozenset, handling nested lists/dicts."""
    return frozenset((k, json.dumps(v, sort_keys=True)) for k, v in d.items())

def hashable_to_dict(fset):
    """Convert back from frozenset (with JSON values) into a dict."""
    return {k: json.loads(v) for k, v in fset}