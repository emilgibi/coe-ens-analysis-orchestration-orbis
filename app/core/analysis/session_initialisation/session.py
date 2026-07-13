from sqlalchemy import insert, or_, select
from sqlalchemy.exc import SQLAlchemyError  # To catch SQLAlchemy-specific errors
from app.core.config import get_settings
from app.models import *
from app.core.utils.db_utils import *
from app.schemas.logger import logger
from datetime import datetime, timedelta, timezone
async def ensid_screening_status_initialisation(session_id_value: str, session):

    logger.info(f"Initialising for session_id: {session_id_value}")
    # Get all ens_id of session_id - insert into ensid_screening_status: # ensid_screening_status will be updated with relevant columns at the end of each component

    required_columns = ["ens_id"]  # We want only [{"ens_id": "ABC-123"},{"ens_id": "ABZ-122"},
    ens_ids_rows = await get_ens_ids_for_session_id("supplier_master_data", required_columns, session_id_value, session)
    logger.debug("GOT ENS ID ROWS")
    logger.debug(ens_ids_rows)
    ens_ids_rows = [{**entry,
                     "overall_status": STATUS.STARTED,
                     "orbis_retrieval_status": STATUS.NOT_STARTED,
                     "screening_modules_status": STATUS.NOT_STARTED,
                     "report_generation_status": STATUS.NOT_STARTED
                     } for entry in ens_ids_rows]

    insert_status = await upsert_ensid_screening_status(ens_ids_rows, session_id_value, session)
    # print(insert_status)
    # container_creation_status=create_container_to_azure_blob(session_id_value)
    container_creation_status=create_r2_container(session_id_value)
    if not container_creation_status:
        logger.error("ERROR CREATING CONTAINER")  # TODO HANDLE ERROR HERE

    return {"ens_id": "", "module": "session_init", "status": "completed"}  # TODO CHANGE THIS

async def ensid_screening_status_nonrepetitive(session_id_value: str, ENABLE_PRODUCTION_SKIP_LOGIC: bool,  session):
    logger.info(f"Initialising for session_id: {session_id_value}")

    session_data = await get_dynamic_ens_data("session_screening_status",["source"],None, session_id_value, session)
    source = session_data[0]["source"] if session_data else None
    logger.debug(f"Current Source {source}")
    required_columns = ["ens_id"]
    ens_ids_rows = await get_ens_ids_for_session_id("supplier_master_data",required_columns, session_id_value,session)

    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=30)

    final_rows = []
    skipped_ens_ids = []

    for entry in ens_ids_rows:
        ens_id = entry["ens_id"]
        should_skip = False

        recent_runs = await get_dynamic_ens_data("ensid_screening_status",
            ["ens_id", "session_id", "overall_status", "create_time"],ens_id=ens_id, session_id=None, session=session)

        recent_runs = [
            r for r in recent_runs
            if r.get("create_time") and datetime.fromisoformat(str(r["create_time"])) > cutoff_time
        ]

        if recent_runs and ENABLE_PRODUCTION_SKIP_LOGIC:
            if source == "CM":
                recent_session_ids = [r["session_id"] for r in recent_runs]

                recent_session_sources = await get_session_statuses(recent_session_ids, session)

                cm_recent = [
                    s for s in recent_session_sources
                    if s["source"] == "CM"
                ]

                if cm_recent:
                    should_skip = True
                    logger.info(
                        f"ENS ID {ens_id} skipped: previous session(s) "
                        f"{[s['session_id'] for s in cm_recent]} had CM source in last 30 mins."
                    )
            else:
                for r in recent_runs:
                    if r["overall_status"] in STATUS.COMPLETED or r["overall_status"] in STATUS.IN_PROGRESS:
                        should_skip = True
                        logger.info(
                            f"ENS ID {ens_id} skipped: status {r['overall_status']} "
                            f"in session {r['session_id']} within last 30 mins."
                        )
                        break

        if should_skip:
            skipped_row = {
                **entry,
                "overall_status": STATUS.SKIPPED,
                "orbis_retrieval_status": STATUS.SKIPPED,
                "screening_modules_status": STATUS.SKIPPED,
                "report_generation_status": STATUS.SKIPPED,
            }
            final_rows.append(skipped_row)
            skipped_ens_ids.append(ens_id)
        else:
            started_row = {
                **entry,
                "overall_status": STATUS.STARTED,
                "orbis_retrieval_status": STATUS.NOT_STARTED,
                "screening_modules_status": STATUS.NOT_STARTED,
                "report_generation_status": STATUS.NOT_STARTED,
            }
            final_rows.append(started_row)

    await upsert_ensid_screening_status(final_rows, session_id_value, session)

    container_creation_status = create_r2_container(session_id_value)
    if not container_creation_status:
        logger.error("ERROR CREATING CONTAINER")

    return {
        "ens_id": "",
        "module": "session_init",
        "status": "completed",
        "skipped_ids": skipped_ens_ids
    }


from azure.storage.blob import BlobServiceClient
import logging
import os
import boto3
from botocore.exceptions import ClientError
def create_container_to_azure_blob(session_id):
    """
    Creates the container if it doesn't exist.
    """

    connection_string = os.getenv("BLOB_STORAGE__CONNECTION_STRING")
    container_name = session_id

    try:
        # Initialize the BlobServiceClient
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)

        # Get the container client
        container_client = blob_service_client.get_container_client(container_name)

        # Create the container if it does not exist
        if not container_client.exists():
            container_client.create_container()
            logger.debug(f"Created container: {container_name}")
            logger.debug("container created")
        return True

    except Exception as e:
        logger.error(f"{container_name} container failed to add to Azure Blob Storage. Error: {str(e)}")
        return False
    
def create_r2_container(session_id: str) -> bool:
    """
    Mimics container creation in Cloudflare R2 by uploading a zero-byte placeholder object.
    Note: R2 does not support programmatic bucket creation via S3 API. Buckets must be pre-created via dashboard.
    
    :param session_id: Used as a prefix to simulate a folder/container structure.
    :return: True if placeholder upload is successful, False otherwise.
    """

    try:
        # Load credentials and configuration
        access_key = get_settings().r2_storage.access_key #os.getenv("STORAGE__ACCESS_KEY")
        secret_key = get_settings().r2_storage.secreate_account_key #os.getenv("STORAGE__SECREATE_ACCOUNT_KEY")
        endpoint_url = get_settings().r2_storage.storage_account_url #os.getenv("STORAGE__STORAGE_ACCOUNT_URL")
        bucket_name = get_settings().r2_storage.storage_container_name #os.getenv("STORAGE__CONTAINER_NAME", "generated-reports")


        if not all([access_key, secret_key, endpoint_url]):
            logger.error("Missing R2 credentials or config in environment.")
            return False

        # Create an S3 client
        s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url,
            region_name="auto",
            verify=False
        )

        # Upload a zero-byte placeholder object to simulate folder creation
        s3.put_object(Bucket=bucket_name, Key=f"{session_id}/.init")

        logger.debug(f"Simulated container created for session_id: {session_id}")
        return True

    except ClientError as e:
        logger.error(f"Failed to create 'container' in R2 for session_id {session_id}. Error: {str(e)}")
        return False