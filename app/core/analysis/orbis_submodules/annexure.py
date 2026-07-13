from app.core.utils.db_utils import get_dynamic_ens_data
from app.schemas.logger import logger
import re
from typing import List, Dict, Any
import json


def format_shareholders_for_annexure(shareholders: List[Dict[str, Any]]) -> str:
    """
    Format shareholders list for annexure display with ownership percentages
    Categorizes shareholders into Direct and Indirect based on significance
    """
    if not isinstance(shareholders, list) or not shareholders:
        return "No shareholder information available."

    direct_shareholders = []
    indirect_shareholders = []

    for shareholder in shareholders:
        if isinstance(shareholder, dict):
            name = shareholder.get("name", "").strip()
            direct_ownership = shareholder.get("direct_ownership")
            total_ownership = shareholder.get("total_ownership")
            significance = shareholder.get("significance", False)

            if not name:
                continue

            ownership = None
            if direct_ownership and str(direct_ownership).strip() not in ["", "n.a.", "null", "-"]:
                ownership = str(direct_ownership).strip()
            # elif total_ownership and str(total_ownership).strip() not in ["", "n.a.", "null", "-"]:
            #     ownership = str(total_ownership).strip()  ## TODO: Temporary disable as unsure.

            ownership_string = ""
            display_name = name
            should_include = True

            if ownership:
                ownership = ownership.strip()

                if ownership is None:
                    ownership_string = ""
                elif ownership == "-":
                    ownership_string = ""
                elif ownership == "n.a.":
                    ownership_string = ""
                elif "ng" in ownership.lower():
                    ownership_string = " (<= 0.01%)"
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

            # Final display name with ownership string
            final_display = f"{display_name}{ownership_string}"

            if ownership_string == "":
                indirect_shareholders.append(final_display)
            else:
                direct_shareholders.append(final_display)

    # Format the output
    result_parts = []

    if direct_shareholders:
        result_parts.append("\n\nDirect Shareholders\n\n")
        for i, shareholder in enumerate(direct_shareholders, 1):
            result_parts.append(f"{i}. {shareholder}")

    if indirect_shareholders: # AKA INSIGNIFICANT
        if result_parts:
            result_parts.append("")
            result_parts.append("\n\nOther Shareholders\n\n")
        for i, shareholder in enumerate(indirect_shareholders, 1):
            result_parts.append(f"{i}. {shareholder}")

    if not result_parts:
        return "No shareholder information available."

    return "\n".join(result_parts)

def format_management_for_annexure(management_data: List[Dict[str, Any]]) -> str:
    """
    Management/key executives list for annexure
    """
    if not isinstance(management_data, list) or not management_data:
        return "No management information available."

    current_execs = []
    previous_execs = []
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
    # logger.debug("checkpoint 1")

    for employee in management_data:
        if isinstance(employee, dict):
            consider_job_title = 0
            employee['priority'] = int(27)
            hierarchy_cleaned = re.sub(r'[^a-zA-Z\s]', ' ', employee.get("hierarchy",''))
            job_title_cleaned = re.sub(r'[^a-zA-Z\s]', ' ', employee.get('job_title', ''))
            logger.debug("set1",employee.get("hierarchy",''),set(hierarchy_cleaned.lower().split()))
            for official_priority, official_words_set in executive_hierarchy_word_sets.items():
                if official_words_set.issubset(set(hierarchy_cleaned.lower().split())):
                    employee['priority'] = int(official_priority)
                    break
            # logger.debug("checkpoint 2")
            logger.debug("set 2",set(job_title_cleaned.lower().split()))
            for official_priority, official_words_set in executive_hierarchy_word_sets.items():
                if official_words_set.issubset(set(job_title_cleaned.lower().split())):
                    if employee['priority'] > official_priority:
                        consider_job_title=1
                        employee['priority'] = int(official_priority)
                        break
            logger.debug("priority",employee['priority'])
            # logger.debug("checkpoint 3")
            name = employee.get("name", "").strip()
            job_title = employee.get("job_title", "").strip()
            hierarchy = employee.get("hierarchy",'').strip()
            department = employee.get("department", "").strip()
            current_status = employee.get("current_or_previous", "").strip().lower()

            if not name:
                continue

            position = []
            if consider_job_title:
                position.append(job_title)
                if department and department not in job_title:
                    position.append(f"({department})")
            else:
                position.append(hierarchy)
                if department and department not in hierarchy:
                    position.append(f"({department})")
            position_desc = " ".join(position)

            employee['description'] = f"{name} - {position_desc}" if position_desc else name

            if current_status == "previous":
                previous_execs.append(employee)
            else:
                current_execs.append(employee)
        else:
            logger.debug("without dic found",employee)
    sections = []
    logger.debug("done")
    if current_execs:
        current_execs = sorted(current_execs, key=lambda x: x.get('priority',99))
        current_section = ["Current Key Executives\n\n"]
        current_section.extend(f"{i}. {exec['description']}" for i, exec in enumerate(current_execs, 1))
        sections.append("\n".join(current_section))

    if previous_execs:
        previous_execs = sorted(previous_execs, key=lambda x: x.get('priority',99))
        previous_section = ["\n\nPrevious Key Executives\n\n"]
        previous_section.extend(f"{i}. {exec['description']}" for i, exec in enumerate(previous_execs, 1))
        sections.append("\n".join(previous_section))

    # with open('priority.json', 'w')as file:
    #     json.dump(current_execs+previous_execs,file,indent=2)
    if not sections:
        return "No management information available."

    return "\n".join(sections)

