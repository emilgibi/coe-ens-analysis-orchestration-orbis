import os
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
from io import BytesIO
import matplotlib.pyplot as plt
import logging 
from app.core.config import get_settings
from app.schemas.logger import logger
load_dotenv()

plots = r"app\core\analysis\report_generation_submodules\output\plots"
def create_matplotlib(self, sentiment_data_agg: list, name: str, num_max_articles: int):
    months = [item["month"] for item in sentiment_data_agg]
    negatives = [item["negative"] for item in sentiment_data_agg]

    # Create the plot
    plt.figure(figsize=(12, 5))
    plt.bar(months, negatives, color='lightcoral')

    # Add labels and title
    plt.xlabel('Month')
    plt.ylabel('Negative News')
    plt.title(name)
    plt.axhline(0, color='black', linewidth=0.8) 
    plt.yticks(range(0, num_max_articles))
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Save the plot as a PNG image
    plot_image_path = os.path.join(plots, f"{name}_plot.png")
    plt.savefig(plot_image_path, format='png', dpi=300)
    plt.close()  # Close the plot to free up memory

    return plot_image_path

from azure.storage.blob import BlobServiceClient
import logging
from io import BytesIO
def upload_to_azure_blob(file_buffer: BytesIO, file_name: str, session_id):
    """
    Uploads a file to Azure Blob Storage. Creates the container if it doesn't exist.

    :param file_buffer: The buffer containing the file to be uploaded.
    :param file_name: The name of the file to be saved in blob storage.
    :param session_id: The container name (used as session identifier).
    :return: True if upload is successful, False otherwise.
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
            logger.info(f"Created container: {container_name}")

        # Get a blob client
        blob_client = container_client.get_blob_client(file_name)

        # Upload the file buffer, seek to the start before uploading
        file_buffer.seek(0)  # Ensure we're at the start of the buffer
        
        # Upload the buffer directly to blob storage
        blob_client.upload_blob(file_buffer, overwrite=True)
        logger.info(f"Successfully uploaded {file_name} to Azure Blob Storage.")
        return True

    except Exception as e:
        logger.error(f"Failed to upload {file_name} to Azure Blob Storage. Error: {e}")
        return False

import boto3
from botocore.exceptions import ClientError

def upload_to_r2(file_buffer: BytesIO, file_name: str, session_id: str) -> bool:
    """
    Uploads a file to Cloudflare R2 (S3-compatible). 
    Creates the "folder" prefix using session_id.

    :param file_buffer: The buffer containing the file to be uploaded.
    :param file_name: The name of the file to be saved (e.g., report.pdf).
    :param session_id: Used as a prefix/folder name (e.g., session123).
    :return: True if upload is successful, False otherwise.
    """

    try:
        # Load credentials and config from environment variables
        access_key = get_settings().r2_storage.access_key
        secret_key = get_settings().r2_storage.secreate_account_key #os.getenv("STORAGE__SECREATE_ACCOUNT_KEY")
        endpoint_url = get_settings().r2_storage.storage_account_url #os.getenv("STORAGE__STORAGE_ACCOUNT_URL")
        bucket_name = get_settings().r2_storage.storage_container_name #os.getenv("STORAGE__CONTAINER_NAME", "generated-reports")

        if not all([access_key, secret_key, endpoint_url]):
            logger.error("Missing R2 credentials or config in environment variables.")
            return False

        # Initialize S3 client for R2
        s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url,
            region_name="auto",
            verify=False
        )

        # Reset buffer position before upload
        file_buffer.seek(0)

        # Upload file
        s3.put_object(
            Bucket=bucket_name,
            Key=f"{session_id}/{file_name}",
            Body=file_buffer
        )

        logger.info(f"Successfully uploaded {file_name} to R2 in session {session_id}.")
        return True

    except ClientError as e:
        logger.error(f"Failed to upload {file_name} to R2: {e}")
        return False
    
def clear_output_folder(output_folder):
    """
    Explicitly clear all files in the output folder.
    """
    if os.path.exists(output_folder):
        for file in os.listdir(output_folder):
            file_path = os.path.join(output_folder, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
                logger.info(f"Removed file: {file}")

        logger.info("Output folder cleared: All files removed.")
    else:
        logger.warning("Output folder does not exist. Nothing to clear.")