import json
from app.core.utils.db_utils import get_dynamic_ens_data
from app.core.utils.db_utils import *
import re
from app.schemas.logger import logger

async def company_profile(data, session):
    logger.info("Performing Company Profile...")

    ens_id = data.get("ens_id")
    session_id = data.get("session_id")
    required_columns = ["name", "country", "location", "address", "website", "is_active", "operation_type", "legal_form",
                        "national_identifier", "national_identifier_type", "alias", "incorporation_date", "shareholders","operating_revenue_usd",
                        "num_subsidiaries", "num_companies_in_corp_grp","management", "no_of_employee"]

    retrieved_data = await get_dynamic_ens_data("external_supplier_data", required_columns, ens_id,
                                                session_id, session)
    retrieved_data = retrieved_data[0]
    logger.debug("Processing retrieved company data...")

    supplier_master_data = await get_dynamic_ens_data("supplier_master_data",["national_id", "external_vendor_id", "uploaded_name"],ens_id, session_id, session)

    supplier_national_id = supplier_master_data[0].get("national_id") if supplier_master_data else None
    external_vendor_id = supplier_master_data[0].get("external_vendor_id") if supplier_master_data else None
    uploaded_name = supplier_master_data[0].get("uploaded_name") if supplier_master_data else None

    def format_alias(items):
        if isinstance(items, list):
            items = list({i for i in items if i is not None})
            items = list(set(items))[:7]
            return "\n\n".join(items)
        return items

    import re

    def format_shareholders(shareholders):
        if isinstance(shareholders, list):
            found_count = 0
            total_count = len(shareholders)
            top_shareholders = shareholders
            formatted_shareholders = []
            total_ownership = 0
            insignificant_ownership = 0.0
            more_indicator = False
            count_of_na = 0
            for shareholder in top_shareholders:
                if isinstance(shareholder, dict) and shareholder.get('significance'):
                    name = shareholder.get("name", "")
                    ownership = shareholder.get("direct_ownership", "-")
                    if ownership is None:
                        ownership_string = ""
                    elif ownership == "-":
                        ownership_string = ""
                    elif ownership == "n.a.":
                        ownership_string = ""
                    elif "ng" in ownership.lower():
                        ownership_string = " (<= 0.01%)"
                    elif "fc" in ownership.lower():
                        ownership_string = " (Foreign company)"
                    elif "wo" in ownership.lower():
                        more_indicator = True
                        ownership_string = " (Wholly owned, >= 98%)"
                    elif "mo" in ownership.lower():
                        more_indicator = True
                        ownership_string = " (Majority owned, > 50%)"
                    elif "jo" in ownership.lower():
                        ownership_string = " (Jointly owned, = 50%)"
                    elif "t" in ownership.lower():
                        ownership_string = " (Sole trader, = 100%)"
                    elif "reg" in ownership.lower():
                        ownership_string = " (Beneficial Owner from register, = 100%)"
                    elif "gp" in ownership.lower():
                        ownership_string = " (General partner)"
                    elif "dm" in ownership.lower():
                        ownership_string = " (Director / Manager)"
                    elif "ve" in ownership.lower():
                        ownership_string = " (Vessel)"
                    elif "br" in ownership.lower():
                        ownership_string = " (Owning Entity)"
                    elif "cqp1" in ownership.lower():
                        more_indicator = True
                        ownership_string = " (50% + 1 Share)"
                    elif ownership.lower().strip().startswith(">"):
                        more_indicator = True
                        ownership_string = f" ({ownership}%)"
                    elif ownership.lower().strip().startswith("<"):
                        ownership_string = f" ({ownership}%)"
                    elif not re.match(r'^\d', ownership):
                        ownership_string = ""
                    else:
                        ownership_string = f" ({ownership}%)"
                    ownership_float = max([float(x) for x in re.findall(r"\d+\.\d+|\d+", ownership_string)], default=0)
                    total_ownership = total_ownership + ownership_float
                    formatted_shareholders.append(f"{name}{ownership_string}")
                    found_count += 1
                elif isinstance(shareholder, dict):
                    # logger.info(f"with insignificance {shareholder}")
                    # logger.info(f"with insignificance {shareholder.get("direct_ownership", "-")}")
                    ownership_string=shareholder.get("direct_ownership", "-") or "0"
                    ownership_float = max([float(x) for x in re.findall(r"\d+\.\d+|\d+", ownership_string)], default=0)
                    if ownership_float==0.0:
                        count_of_na += 1
                    # logger.info(f"insignificiance {ownership_float}")
                    insignificant_ownership = insignificant_ownership + ownership_float

            if found_count > 7:
                formatted_shareholders = formatted_shareholders[:7]
                formatted_shareholders.append(f"& {total_count - 7} more shareholders")
                # additional_string = "< " if more_indicator else " "
                # if round(100 - total_ownership, 2)>0:
            if insignificant_ownership>0.00000:
                if count_of_na:
                    formatted_shareholders.append(f"Other minority shareholders ~{round(insignificant_ownership, 2)}%+")
                else:
                    formatted_shareholders.append(
                        f"Other minority shareholders ~{round(insignificant_ownership, 2)}%")
            else:
                if count_of_na and (total_ownership < 100):
                    formatted_shareholders.append(f"Other minority shareholders n.a.")



            return "\n\n".join(formatted_shareholders)
        return None

    def format_national_identifier(national_identifier, national_identifier_type, supplier_national_id):
        if isinstance(national_identifier, list) and isinstance(national_identifier_type, list):
            zipped_identifiers = list(zip(national_identifier_type, national_identifier))
            for identifier_type, identifier in zipped_identifiers:
                if identifier == supplier_national_id:
                    return f"{identifier_type}: {identifier}"

            if zipped_identifiers:
                return f"{zipped_identifiers[0][0]}: {zipped_identifiers[0][1]}"

        return national_identifier if isinstance(national_identifier, str) else None

    def management_names(management):
        additional_text=''
        if isinstance(management, list):
            total_count = len(management)
            management= heirarchy_management(management)
            total_current_count = len(management)
            management = sorted(management, key=lambda x: x['priority'])
            if len(management) <= 7:
                additional_text = 'previous'
            else:
                additional_text = 'more'
                total_current_count=7
            management = management[:7]
            names = [f"{person.get('name', '')} ({person.get('title_to_use', '')})" for person in management if isinstance(person, dict) and "name" in person]
            if total_count - total_current_count >0:
                if total_current_count == 0:
                    names.append(f"\n {total_count - total_current_count} {additional_text} key executives")
                else:
                    names.append(f"\n & {total_count - total_current_count} {additional_text} key executives")
            return "\n\n".join(names)
        return None
    def heirarchy_management(management):
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
        new_json = []
        for employee in management:
            consider_job_title=0
            employee['priority'] = int(27)
            hierarchy_cleaned = re.sub(r'[^a-zA-Z\s]', ' ', employee.get("heirarchy", ''))
            job_title_cleaned = re.sub(r'[^a-zA-Z\s]', ' ', employee.get('job_title', ''))
            if employee.get("current_or_previous").lower() == 'current':
                for official_priority, official_words_set in executive_hierarchy_word_sets.items():
                    if official_words_set.issubset(set(hierarchy_cleaned.lower().split())):
                        employee['priority'] = official_priority
                        break

                logger.debug("set 2", set(job_title_cleaned.lower().split()))
                for official_priority, official_words_set in executive_hierarchy_word_sets.items():
                    if official_words_set.issubset(set(job_title_cleaned.lower().split())):
                        if employee['priority']>official_priority:
                            consider_job_title=1
                            employee['priority'] = official_priority
                            break
                if consider_job_title:
                    employee['title_to_use'] = employee.get('job_title', '')
                else:
                    employee['title_to_use'] = employee.get('heirarchy', '')
                new_json.append(employee)
            else:
                employee['priority']=99
        return new_json
    def format_revenue(revenue_data):
        if isinstance(revenue_data, list) and revenue_data:
            latest_revenue = revenue_data[0].get("value")
            latest_date = revenue_data[0].get("closing_date", "")
            if latest_revenue is not None:
                formatted_value = format_revenue_num(latest_revenue)
                return f"{formatted_value} (USD - {latest_date})"
        return None

    def format_revenue_num(value_str):
        try:
            value = float(value_str)
            if value >= 1_000_000_000:
                return f"{value / 1_000_000_000:.0f}B"
            elif value >= 1_000_000:
                return f"{value / 1_000_000:.0f}M"
            else:
                return f"{value:,.0f}"
        except:
            return value_str

    def format_incorporation_date(date):
        if date:
            try:
                return date.strftime("%d/%m/%Y")
            except AttributeError:
                from datetime import datetime
                try:
                    date_obj = datetime.strptime(date, "%Y-%m-%d")
                    return date_obj.strftime("%d/%m/%Y")
                except ValueError:
                    return date
        return None

    company_data = {
        "name": retrieved_data.get("name"),
        "location": retrieved_data.get("location"),
        "address": retrieved_data.get("address"),
        "website": retrieved_data.get("website"),
        "active_status": retrieved_data.get("is_active"),
        "operation_type": "Publicly quoted" if retrieved_data.get("legal_form") == "Public limited companies" else "Private",
        "legal_status": retrieved_data.get("legal_form"),
        "national_identifier": format_national_identifier(retrieved_data.get("national_identifier"), retrieved_data.get("national_identifier_type"),supplier_national_id),
        "alias": format_alias(retrieved_data.get("alias")),
        "incorporation_date": format_incorporation_date(retrieved_data.get("incorporation_date")),
        "shareholders": format_shareholders(retrieved_data.get("shareholders")),
        "revenue": format_revenue(retrieved_data.get("operating_revenue_usd")),
        "subsidiaries": f"{retrieved_data.get('num_subsidiaries')} entities" if retrieved_data.get("num_subsidiaries") else None,
        "corporate_group": f"{retrieved_data.get('num_companies_in_corp_grp')} entities" if retrieved_data.get("num_companies_in_corp_grp") else None,
        "key_executives": management_names(retrieved_data.get("management")),
        "employee": f"{retrieved_data.get('no_of_employee')} employees" if retrieved_data.get("no_of_employee") else None,
        "external_vendor_id": external_vendor_id,
        "uploaded_name": uploaded_name
    }

    # logger.info(f"shareholders{company_data["shareholders"]}")

    logger.debug(json.dumps(company_data, indent=2))
    columns_data = [company_data]
    result = await upsert_dynamic_ens_data("company_profile", columns_data, ens_id, session_id, session)

    if result.get("status") == "success":
        logger.info("Company profile saved successfully.")
    else:
        logger.error(f"Error saving company profile: {result.get('error')}")

    return {"ens_id": ens_id, "module": "COPR", "status": "completed"}