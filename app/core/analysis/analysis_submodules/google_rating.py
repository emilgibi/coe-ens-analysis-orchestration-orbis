from app.core.utils.db_utils import *
from app.schemas.logger import logger
import traceback


async def google_rating_analysis(data, session):
    logger.info("Performing Google Rating Analysis...")

    kpi_area_module = "NWS"

    if not isinstance(data, dict):
        logger.error("Invalid input data received in domain_analysis")
        return []

    ens_id_value = data.get("ens_id")
    session_id_value = data.get("session_id")
    bvd_id = data.get("bvd_id")

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

        NWS2A = kpi_template.copy()
        NWS2A["kpi_code"] = "NWS2A"
        NWS2A["kpi_definition"] = "Google Rating Validation"

        required_columns = ["rating", "no_of_reviews", "reviews", "name"]

        retrieved_data = await get_dynamic_data(
            "google_ratings",
            required_columns,
            "bvd_id",
            bvd_id,
            session
        )

        if not retrieved_data:
            logger.info("Google Rating Analysis... No data found")
            return []

        retrieved_data = retrieved_data[0]
        rating = retrieved_data.get("rating")
        reviews = retrieved_data.get("reviews")
        no_of_reviews = retrieved_data.get("no_of_reviews")
        name= retrieved_data.get("name")

        if not rating:
            logger.info("Google rating Analysis... Google Rating missing or invalid")
            return []

        paragraph=''
        name_para=f'Name: {name}\n'
        rating_para=f'Rating: {rating}\n'
        no_of_reviews_para=f'Number of Reviews: {no_of_reviews}\n\n\n'
        reviews_para=f'Reviews:\n'
        n=1
        for r in reviews:
            r_para=''
            r_para=f'\t{n}. Name: {r.get("author_name")} | Rating: {r.get("rating")}\n{r.get("text")}\n\n'
            reviews_para+=r_para
            n+=1
            if n>3:
                continue

        paragraph=name_para+rating_para+no_of_reviews_para+reviews_para
        rating=float(rating)
        kpi_rating='Low'
        if rating <3:
            kpi_rating='High'
        elif 3< rating <4:
            kpi_rating='Medium'
        NWS2A["kpi_flag"] = True
        NWS2A["kpi_rating"] = kpi_rating

        NWS2A["kpi_value"] = paragraph
        NWS2A["kpi_details"] = paragraph

        await upsert_kpi(
            "news",
            [NWS2A],
            ens_id_value,
            session_id_value,
            session
        )

        logger.info("Google Rating Analysis... Completed With Data")
        return []

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Google Rating Analysis failed: {str(e)}", exc_info=True)
        return []