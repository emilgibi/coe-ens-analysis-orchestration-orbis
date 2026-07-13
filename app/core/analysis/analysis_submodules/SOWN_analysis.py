import asyncio
from app.core.utils.db_utils import *
import json
from datetime import datetime
from app.schemas.logger import logger
import re
from app.core.analysis.analysis_submodules.fetchdata import *
import traceback

async def sown_analysis(data, session):

    logger.info("Performing State Ownership Structure Analysis... Started")

    kpi_area_module = "SCO"

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
            "kpi_details": ""
        }

        SCO1A = kpi_template.copy()

        SCO1A["kpi_code"] = "SCO1A"
        SCO1A["kpi_definition"] = "Global Ultimate Owner Is Public Authority/State/Government"

        required_columns = ["shareholders", "global_ultimate_owner", "global_ultimate_owner_type"]
        retrieved_data = await get_dynamic_ens_data("external_supplier_data", required_columns, ens_id_value, session_id_value, session)
        retrieved_data = retrieved_data[0]
        logger.debug(f"retrieved data: {retrieved_data}")

        shareholders = retrieved_data.get("shareholders", None)
        global_ultimate_owner = retrieved_data.get("global_ultimate_owner", None)
        global_ultimate_owner_type = retrieved_data.get("global_ultimate_owner_type", None)

        # ---- PERFORM ANALYSIS LOGIC HERE
        if isinstance(global_ultimate_owner, list) and global_ultimate_owner:
            global_ultimate_owner_name = global_ultimate_owner[0].get("name")
        else:
            global_ultimate_owner_name = global_ultimate_owner
        if isinstance(global_ultimate_owner_type, list):
            global_ultimate_owner_type = ", ".join(global_ultimate_owner_type)
        if global_ultimate_owner_type and any(word in global_ultimate_owner_type.lower() for word in ["state", "government", "public authority"]):  # TODO INSERT LOGIC
            SCO1A["kpi_flag"] = True
            SCO1A["kpi_value"] = json.dumps(global_ultimate_owner_type)
            SCO1A["kpi_rating"] = "High"
            SCO1A["kpi_details"] = f"Global Ultimate Owner: {global_ultimate_owner_name}, is {global_ultimate_owner_type}"
        else:
            SCO1A["kpi_value"] = json.dumps(global_ultimate_owner_type)
            SCO1A["kpi_rating"] = "Low"
            SCO1A["kpi_details"] = f"Group / Global Ultimate Owner not found to be state-controlled"

        sco_kpis = [SCO1A]

        insert_status = await upsert_kpi("sown", sco_kpis, ens_id_value, session_id_value, session) # --- SHOULD WE CHANGE THIS TO BE PART OF PEP

        if insert_status["status"] == "success":
            logger.info(f"{kpi_area_module} Analysis... Completed Successfully")
            return {"ens_id": ens_id_value, "module": kpi_area_module, "status": "completed", "info": "analysed"}
        else:
            logger.error(insert_status)
            return {"ens_id": ens_id_value, "module": kpi_area_module, "status": "failure","info": "database_saving_error"}

    except Exception as e:
        logger.error(f"Error in module: {kpi_area_module}: {str(e)} \n {traceback.format_exc()}")
        return {"ens_id": ens_id_value, "module": kpi_area_module, "status": "failure", "info": str(e)}

async def pep_analysis(data, session):

    logger.info("Performing PEP Analysis...")

    kpi_area_module = "PEP"

    ens_id_value = data.get("ens_id")
    session_id_value = data.get("session_id")

    # --- Fetch exclusion list from DB ---
    try:
        db_exclusions_raw = await get_dynamic_ens_data(
            table_name="excluded_entities",
            required_columns=["name"],
            session=session
        )
        exclusion_list = [item["name"].strip().lower() for item in db_exclusions_raw if item.get("name")]
    except Exception as e:
        logger.error(f"Failed to fetch exclusion lists from DB: {str(e)} \n {traceback.format_exc()}")
        exclusion_list = []

    def is_excluded_entity_name(entity_name):
        """Check if entity name is in exclusion list"""
        if not entity_name or not isinstance(entity_name, str):
            return False
        return entity_name.strip().lower() in exclusion_list

    try:

        kpi_template = {
            "kpi_area": kpi_area_module,
            "kpi_code": "",
            "kpi_definition": "",
            "kpi_flag": False,
            "kpi_value": None,
            "kpi_rating": "",
            "kpi_details": "",
            "kpi_data": []
        }

        PEP1A = kpi_template.copy()
        PEP1B = kpi_template.copy()
        PEP2A = kpi_template.copy()
        PEP2B = kpi_template.copy()

        PEP1A["kpi_code"] = "PEP1A"
        PEP1A["kpi_definition"] = "PeP for Direct Affiliations - Organisation Level"

        PEP1B["kpi_code"] = "PEP1B"
        PEP1B["kpi_definition"] = "PeP for Direct Affiliations -  Person Level"

        PEP2A["kpi_code"] = "PEP2A"
        PEP2A["kpi_definition"] = "PeP for Indirect Affiliations - Organisation Level"

        PEP2B["kpi_code"] = "PEP2B"
        PEP2B["kpi_definition"] = "PeP for Indirect Affiliations - Person Level"

        pep_kpis = []

        required_columns = ["event_pep", "grid_event_pep", "management"]
        # await data_fetching_for_new_and_old_session(ens_id_value, session_id_value, required_columns[:2])
        retrieved_data = await get_dynamic_ens_data("external_supplier_data", required_columns, ens_id_value, session_id_value, session)
        if not retrieved_data or not isinstance(retrieved_data, list):
            logger.error(f"No data retrieved for external_supplier_data: {retrieved_data}")
            return {"ens_id": ens_id_value, "module": kpi_area_module, "status": "failure", "info": "no_data"}
        retrieved_data = retrieved_data[0]
        management_data = retrieved_data.get("management") or []  # This handles None values
        pep_management_list = [x for x in management_data if x.get("pep_indicator") and x.get("pep_indicator").lower() == 'yes' and not is_excluded_entity_name(x.get("name", ""))]
        event_pep = retrieved_data.get("event_pep", [])
        grid_event_pep = retrieved_data.get("grid_event_pep", [])

        # Data for Person-Level
        required_columns = ["grid_pep", "management_info"]
        # await data_fetching_for_new_and_old_session_personel(ens_id_value, session_id_value, required_columns[0])
        retrieved_data = await get_dynamic_ens_data("grid_management", required_columns, ens_id_value, session_id_value, session)
        person_retrieved_data = retrieved_data if retrieved_data is not None else []  # Multiple rows/people per ens_id and session_id
        # Check if all person data is blank
        person_info_none = all(person.get("grid_pep", None) is None for person in person_retrieved_data) if person_retrieved_data else True
        # logger.debug(f"person info none{person_info_none}")
        # print("checkpoint 1")
        if person_info_none and (event_pep is None) and (grid_event_pep is None) and (len(pep_management_list)==0):
            return {"ens_id": ens_id_value, "module": kpi_area_module, "status": "completed", "info": "no_data"}
        else:
            # new
            new_data = []
            # print("checkpoint 2")
            for person in person_retrieved_data:
                # print("checkpoint 3")
                grid_pep_entries = person.get("grid_pep",[])
                # print("checkpoint 4")
                management_info = person.get("management_info", {})

                if grid_pep_entries and management_info:  # This ensures it's not None or an empty list
                    # print("checkpoint 5")
                    for entry in grid_pep_entries:
                        # print("checkpoint 6")
                        entry["job_title"] = job_title_or_heirarchy(management_info) or ''
                        # print("checkpoint 7")
                        entry["current_or_previous"] = management_info.get("current_or_previous",'') or ''
                        # print("checkpoint 8")
                        entry["name"] = management_info.get("name",'') or ''
                        # print("checkpoint 9")
                        entry["appointment_date"] = management_info.get("appointment_date",'') or ''
                        # print("checkpoint 10")
                        entry["resignation_date"] = management_info.get("resignation_date",'') or ''
                    new_data.append(person)
                    # print("checkpoint 11")
            person_retrieved_data=new_data
            # print("checkpoint 12")
            # logger.debug(f"PEP FOR PERSON PRESENT {len(person_retrieved_data)}")
            # logger.debug(f"PEP FOR PERSON PRESENT {person_retrieved_data}")

        # ---------------------- PEP1A, 2A: Direct and Indirect for Org Level from table "external_supplier_data"
        pep_data = list(event_pep or []) + list(grid_event_pep or []) # TODO: ANOTHER WAY TO COMBINE THIS INFO IF IT OVERLAPS
        pep_data = [record for record in pep_data if not is_excluded_entity_name(record.get("entityName", ""))]
        pep_data = sorted(pep_data, key=lambda x: x.get("eventDate", ""), reverse=True)
        unique_pep_data=set()
        if len(pep_data) > 0:
            current_year = datetime.now().year
            indirect_eventCategory = [""]
            pep_lists_direct = pep_lists_indirect = []
            risk_rating_trigger_direct = risk_rating_trigger_indirect = False

            unique_data_points_direct = []  # For PEP1A
            unique_data_points_indirect = []  # For PEP2A
            i = j = 0
            for record in pep_data:
                # Skip excluded or blank entity names
                entity_name = record.get("entityName", "").strip()
                if not entity_name or is_excluded_entity_name(entity_name):
                    continue

                if "no" in record.get("eventDate", "").lower():
                    record["eventDate"] = "No Date"

                key = (record.get("eventDate"), record.get("eventCategory"), record.get("eventSubCategory"), record.get("eventDesc"))
                if key in unique_pep_data:
                    continue
                unique_pep_data.add(key)

                try:
                    date = datetime.strptime(record.get("eventDate"), "%Y-%m-%d")
                    time_period = current_year - date.year
                    date_string = f"As of [{date}]: "
                except:
                    date = "Unavailable Date"
                    # When date not available, The KPI Rating is high
                    risk_rating_trigger_direct = True
                    risk_rating_trigger_indirect = True
                    time_period = 999  # Workaround temp
                    date_string = ""

                if date_string == "As of [Unavailable Date]: ":
                    date_string = "As of Latest Updated List: " #TODO TEST


                event_category = record.get("eventCategory", None) # orbis grid version
                event_subcategory = record.get("eventSubCategory", None)  # orbis grid version
                pep_details = truncate_string(record.get("eventDesc",""))
                pep_entity_name = record.get("entityName", "")
                event_dict = {
                    "eventdt": record.get("eventDate", record.get("eventDt", "Unavailable")),
                    "eventcat": event_category,
                    "eventsub": event_subcategory,
                    "categoryDesc": record.get("eventCategoryDesc", record.get("categoryDesc", "")),
                    "entityName": pep_entity_name,
                    "eventDesc": pep_details
                }
                if event_category in indirect_eventCategory:
                    PEP2A["kpi_flag"] = True
                    current_unique_detail = f"{date_string}{pep_entity_name}: {pep_details}"
                    unique_data_points_indirect.append(current_unique_detail)
                    pep_lists_indirect.append(event_dict)
                    i+=1
                    if time_period <= 5:
                        risk_rating_trigger_indirect = True
                else:
                    PEP1A["kpi_flag"] = True
                    current_unique_detail = f"{date_string} {pep_entity_name}: {pep_details}"
                    unique_data_points_direct.append(current_unique_detail)
                    pep_lists_direct.append(event_dict)
                    j+=1
                    if time_period <= 5:
                        risk_rating_trigger_direct = True
                if i+j >=5:
                    break  # TODO REMOVE - TEMP

            # For sanctions - client has requested to see "this entity is not sanctioned and none of the individuals are"
            if PEP1A["kpi_flag"]:
                kpi_value_direct_dict = {
                    "count": len(pep_lists_direct) if len(pep_lists_direct) < 6 else "5 or more",
                    "target": "org",  # Since this is organization level
                    "findings": pep_lists_direct,
                    "themes": [a.get("eventsub") for a in pep_lists_direct]
                }

                data_point_counter = 1
                details ="Following PeP or Association with State Owned Companies findings :\n"
                for finding in unique_data_points_direct:
                    finding = f"{data_point_counter}. {finding}\n"
                    details += finding
                    data_point_counter += 1

                PEP1A["kpi_value"] = json.dumps(kpi_value_direct_dict)
                PEP1A["kpi_rating"] = "High" if risk_rating_trigger_direct else "Medium"
                PEP1A["kpi_details"] = details
                PEP1A["kpi_data"] = unique_data_points_direct
            else:
                PEP1A["kpi_value"] = ""
                PEP1A["kpi_rating"] = "INFO"
                PEP1A["kpi_details"] = "Screening Results Indicate No PeP Findings"
                PEP1A["kpi_data"] = []
            pep_kpis.append(PEP1A)

            if PEP2A["kpi_flag"]:
                kpi_value_indirect_dict = {
                    "count": len(pep_lists_indirect) if len(pep_lists_indirect) < 6 else "5 or more",
                    "target": "org",  # Since this is organization level
                    "findings": pep_lists_indirect,
                    "themes": [a.get("eventsub") for a in pep_lists_indirect]
                }

                data_point_counter = 1
                details = "Following PeP or Association with State Owned Companies findings :\n"
                for finding in unique_data_points_indirect:
                    finding = f"{data_point_counter}. {finding}\n"
                    details += finding
                    data_point_counter += 1

                PEP2A["kpi_value"] = json.dumps(kpi_value_indirect_dict)
                PEP2A["kpi_rating"] = "High" if risk_rating_trigger_indirect else "Medium"
                PEP2A["kpi_details"] = details
                PEP2A["kpi_data"] = unique_data_points_indirect
            else:
                PEP2A["kpi_value"] = ""
                PEP2A["kpi_rating"] = "INFO"
                PEP2A["kpi_details"] = "Screening Results Indicate No PeP Findings"
                PEP2A["kpi_data"] = []

            pep_kpis.append(PEP2A)

        logger.debug("# ------------------------------------------------------------ # PERSONS")
        # ---------------------- PEP1B, 2B: Direct and Indirect for PERSON Level from table "grid_management"
        all_person_pep_events = []
        unique_pep_entity_name = set()
        pep_lists_direct = pep_lists_indirect = []
        i = j = 0
        if not person_info_none and len(person_retrieved_data) > 0:
            for person in person_retrieved_data:
                pep_events = person.get("grid_pep",[])
                if pep_events is not None:
                    all_person_pep_events = all_person_pep_events + pep_events
                logger.debug(f"Type of pep_events: {type(pep_events)}, value: {pep_events}")
            current_year = datetime.now().year
            indirect_eventCategory = [""]
            risk_rating_trigger_direct = risk_rating_trigger_indirect = False

            unique_data_points_direct = []  # For PEP1B
            unique_data_points_indirect = []  # For PEP2B
            all_person_pep_events = [record for record in all_person_pep_events if  not is_excluded_entity_name(record.get("entityName", ""))]
            all_person_pep_events = sorted(all_person_pep_events, key=lambda x: x.get("eventDate", ""), reverse=True)
            for record in all_person_pep_events:
                # Skip excluded entities
                if is_excluded_entity_name(record.get("entityName", "")):
                    continue
                try:
                    date = datetime.strptime(record.get("eventDate"), "%Y-%m-%d")
                    time_period = current_year - date.year
                    date_string = f"As of [{date}]: "
                except:
                    date = "Unavailable Date"
                    risk_rating_trigger_direct = True
                    risk_rating_trigger_indirect = True
                    time_period = 999  # Workaround temp
                    date_string = ""

                event_category = record.get("eventCategory", None)
                event_subcategory = record.get("eventSubCategory", None)

                pep_details = truncate_string(record.get("eventDesc",""))
                pep_entity_name = record.get("entityName", "")

                event_dict = {
                    "eventdt": record.get("eventDate", "Unavailable"),
                    "eventcat": event_category,
                    "eventsub": event_subcategory,
                    "categoryDesc": record.get("eventCategoryDesc", ""),
                    "entityName": pep_entity_name,
                    "eventDesc": pep_details
                }

                if event_category in indirect_eventCategory:
                    PEP2B["kpi_flag"] = True
                    if (record.get("resignation_date") is not None) and (record.get("resignation_date")!= 'n.a'):
                        tenure = ' till '+record.get("resignation_date")
                    else:
                        tenure=''
                    current_unique_detail = f"{date_string}{pep_entity_name} ({record.get('current_or_previous')} Key Executive - {record.get('job_title')}{tenure}): {pep_details}"
                    unique_data_points_indirect.append(current_unique_detail)

                    pep_lists_indirect.append(event_dict)
                    i+=1
                    if time_period <= 5:
                        risk_rating_trigger_indirect = True
                else:
                    PEP1B["kpi_flag"] = True
                    if (record.get("resignation_date") is not None) and (record.get("resignation_date")!= 'n.a'):
                        tenure = ' till '+record.get("resignation_date")
                    else:
                        tenure=''

                    current_unique_detail = f"{date_string}{pep_entity_name} ({record.get('current_or_previous')} Key Executive - {record.get('job_title')}{tenure}): {pep_details}"
                    unique_data_points_direct.append(current_unique_detail)

                    pep_lists_direct.append(event_dict)
                    j+=1
                    if time_period <= 5:
                        risk_rating_trigger_direct = True
                if i+j >= 5:
                    break  # TODO REMOVE - TEMP


            # For sanctions & pep, have no value options TODO - also add above
            if PEP1B["kpi_flag"]:
                unique_data_points_direct = sorted(unique_data_points_direct, key=lambda x: "current key executive" not in x.lower())
                kpi_value_direct_dict = {
                    "count": len(pep_lists_direct) if len(pep_lists_direct) < 6 else "5 or more",
                    "target": "person",  # Since this is person level
                    "findings": pep_lists_direct,
                    "themes": [a.get("eventsub") for a in pep_lists_direct]
                }

                data_point_counter = 1
                details = "Following PeP or Association with State Owned Companies findings :\n"
                for finding in unique_data_points_direct:
                    finding = f"{data_point_counter}. {finding}\n"
                    details += finding
                    data_point_counter += 1

                PEP1B["kpi_value"] = json.dumps(kpi_value_direct_dict)
                PEP1B["kpi_rating"] = "High" if risk_rating_trigger_direct else "Medium"
                PEP1B["kpi_details"] = details
                PEP1B["kpi_data"] = unique_data_points_direct
            else:
                PEP1B["kpi_value"] = ""
                PEP1B["kpi_rating"] = "INFO"
                PEP1B["kpi_details"] = "Screening Results Indicate No PeP Findings"
                PEP1B["kpi_data"] = []

            if PEP2B["kpi_flag"]:
                unique_data_points_indirect = sorted(unique_data_points_indirect, key=lambda x: "current key executive" not in x.lower())
                kpi_value_indirect_dict = {
                    "count": len(pep_lists_indirect) if len(pep_lists_indirect) < 6 else "5 or more",
                    "target": "org",  # Since this is organization level
                    "findings": pep_lists_indirect,
                    "themes": [a.get("eventsub") for a in pep_lists_indirect]

                }

                data_point_counter = 1
                details = "Following PeP or Association with State Owned Companies findings :\n"
                for finding in unique_data_points_indirect:
                    finding = f"{data_point_counter}. {finding}\n"
                    details += finding
                    data_point_counter += 1

                PEP2B["kpi_value"] = json.dumps(kpi_value_indirect_dict)
                PEP2B["kpi_rating"] = "High" if risk_rating_trigger_indirect else "Medium"
                PEP2B["kpi_details"] = details
                PEP2B["kpi_data"] = unique_data_points_indirect

            else:
                PEP2B["kpi_value"] = ""
                PEP2B["kpi_rating"] = "INFO"
                PEP2B["kpi_details"] = "Screening Results Indicate No PeP Findings"
                PEP2B["kpi_data"] = []

            pep_kpis.append(PEP2B)

        elif len(pep_management_list)>0:
            j=0
            unique_data_points_direct = []
            for person in pep_management_list:
                if i >= 5:
                    break  # TODO REMOVE - TEMP
                else:
                    if person.get("name") not in unique_pep_entity_name:
                        person['job_title']=job_title_or_heirarchy(person) or ''
                        PEP1B["kpi_flag"] = True

                        if (person.get("resignation_date") is not None) and (person.get("resignation_date") != 'n.a'):
                            tenure = ' till ' + person.get("resignation_date")
                        else:
                            tenure = ''
                        current_unique_detail = f"{person.get('name')} ({person.get('current_or_previous')} Key Executive - {person.get('job_title')}{tenure}): Potential Political Exposure Findings"
                        unique_data_points_direct.append(current_unique_detail)
                        unique_pep_entity_name.add(person.get('name'))
                        event_dict = {
                            "eventdt": "",
                            "eventcat": "PEP",
                            "eventsub": "Potential Political Exposure Findings",
                            "categoryDesc": "PEP",
                            "entityName": person.get("name"),
                            "eventDesc": "Potential Political Exposure Findings"
                        }
                        pep_lists_direct.append(event_dict)
                        j += 1
            if j:
                PEP1B["kpi_flag"]= True
                kpi_value_direct_dict = {
                    "count": len(pep_lists_direct) if len(pep_lists_direct) < 6 else "5 or more",
                    "target": "person",  # Since this is organization level
                    "findings": pep_lists_direct,
                    "themes": [a.get("eventsub") for a in pep_lists_direct]
                }

                data_point_counter = 1
                details = "Following PeP findings :\n"
                for finding in unique_data_points_direct:
                    finding = f"{data_point_counter}. {finding}\n"
                    details += finding
                    data_point_counter += 1

                PEP1B["kpi_value"] = json.dumps(kpi_value_direct_dict)
                PEP1B["kpi_rating"] = "High"
                PEP1B["kpi_details"] = details
                PEP1B["kpi_data"] = unique_data_points_direct
        pep_kpis.append(PEP1B)
        # logger.debug(PEP1B)
        # ---------------------------------

        logger.debug(f"FOUND {len(pep_kpis)} KPIS IN TOTAL -------------------")
        # Insert results into the database
        insert_status = await upsert_kpi("sown", pep_kpis, ens_id_value, session_id_value, session)

        if insert_status["status"] == "success":
            logger.info(f"{kpi_area_module} Analysis... Completed Successfully")
            return {"ens_id": ens_id_value, "module": kpi_area_module, "status": "completed", "info": "analysed"}
        else:
            return {"ens_id": ens_id_value, "module": kpi_area_module, "status": "failure","info": "database_saving_error"}

    except Exception as e:
        logger.error(f"Error in module: {kpi_area_module}: {str(e)} \n {traceback.format_exc()}")
        return {"ens_id": ens_id_value, "module": kpi_area_module, "status": "failure", "info": str(e)}

def truncate_string(input_string, word_limit=40):
    try:
        words = input_string.split()  # Split the string into words
        truncated = " ".join(words[:word_limit])  # Get the first 'word_limit' words
        if len(words) > word_limit:
            truncated += " [...]"  # Add ellipsis if the string is longer than 'word_limit' words
        return truncated
    except:
        return input_string

def job_title_or_heirarchy(employee):
    executive_hierarchy_word_sets = {
        1: {'chief', 'executive', 'officer'},
        2: {'chairman'},
        3: {'vice', 'chairman'},
        4: {'president'},
        5: {'chief', 'operating', 'officer'},
        6: {'chief', 'financial', 'officer'},
        7: {'chief', 'technology', 'officer'},
        8: {'chief', 'marketing', 'officer'},
        9: {'chief', 'human', 'resources', 'officer'},
        10: {'chief', 'information', 'officer'},
        11: {'chief', 'legal', 'officer'},
        12: {'chief', 'revenue', 'officer'},
        13: {'chief', 'communications', 'officer'},
        14: {'chief', 'strategy', 'officer'},
        15: {'chief', 'digital', 'officer'},
        16: {'highest', 'executive'},
        17: {'deputy', 'executive'},
        18: {'chief', 'officer'},
        19: {'chief', 'executive'},
        20: {'vice', 'president'},
        21: {'member', 'board'},
        22: {'proxyholders'},
        23: {'representative'},
        24: {'investor', 'relations'},
        25: {'manager'},
        26: {'executive'},
        28: {'employee'},
        29: {'unspecified', 'executive'}
    }
    consider_job_title=0
    employee['priority'] = int(27)
    hierarchy_cleaned = re.sub(r'[^a-zA-Z\s]', ' ', employee.get("heirarchy", ''))
    job_title_cleaned = re.sub(r'[^a-zA-Z\s]', ' ', employee.get('job_title', ''))
    logger.debug("set1", employee.get("heirarchy", ''), set(hierarchy_cleaned.lower().split()))
    for official_priority, official_words_set in executive_hierarchy_word_sets.items():
        if official_words_set.issubset(set(hierarchy_cleaned.lower().split())):
            employee['priority'] = official_priority
            break

    for official_priority, official_words_set in executive_hierarchy_word_sets.items():
        if official_words_set.issubset(set(job_title_cleaned.lower().split())):
            if employee['priority']>official_priority:
                consider_job_title = 1
                employee['priority'] = int(official_priority)
                break
    if consider_job_title:
        return employee.get('job_title', '')
    else:
        return employee.get("heirarchy", '')