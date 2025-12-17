"""
ClamAV virus definition update Lambda function.
Downloads definitions from S3, updates them using freshclam, and uploads back to S3.

Based on Upside Travel's bucket-antivirus-function.
Licensed under the Apache License, Version 2.0.
"""
import os
import logging

import boto3

import clamav
from common import (
    AV_DEFINITION_PATH,
    AV_DEFINITION_S3_BUCKET,
    AV_DEFINITION_S3_PREFIX,
    CLAMAVLIB_PATH,
    S3_ENDPOINT,
    get_timestamp
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Lambda handler for updating ClamAV virus definitions.

    Downloads existing definitions from S3, updates them using freshclam,
    and uploads the updated definitions back to S3.

    Args:
        event: Lambda event (unused)
        context: Lambda context

    Returns:
        Response dictionary with status
    """
    logger.info(f"Script starting at {get_timestamp()}")

    # Initialize S3 clients
    s3 = boto3.resource("s3", endpoint_url=S3_ENDPOINT)
    s3_client = boto3.client("s3", endpoint_url=S3_ENDPOINT)

    try:
        # Download existing definitions from S3 (only if they've changed)
        logger.info("Checking for existing definitions in S3")
        to_download = clamav.update_defs_from_s3(
            s3_client, AV_DEFINITION_S3_BUCKET, AV_DEFINITION_S3_PREFIX
        )

        for download in to_download.values():
            s3_path = download["s3_path"]
            local_path = download["local_path"]
            logger.info(f"Downloading definition file {local_path} from s3://{s3_path}")
            s3.Bucket(AV_DEFINITION_S3_BUCKET).download_file(s3_path, local_path)
            logger.info(f"Downloading definition file {local_path} complete!")

        # Update definitions using freshclam
        logger.info("Updating definitions using freshclam")
        clamav.update_defs_from_freshclam(AV_DEFINITION_PATH, CLAMAVLIB_PATH)

        # Handle main.cvd updates
        # If main.cvd gets updated (very rare), we need to force freshclam
        # to download the compressed version to keep file sizes down.
        # The existence of main.cud is the trigger to know this has happened.
        main_cud_path = os.path.join(AV_DEFINITION_PATH, "main.cud")
        main_cvd_path = os.path.join(AV_DEFINITION_PATH, "main.cvd")

        if os.path.exists(main_cud_path):
            logger.info("Detected main.cud file, forcing main.cvd re-download")
            os.remove(main_cud_path)
            if os.path.exists(main_cvd_path):
                os.remove(main_cvd_path)
            clamav.update_defs_from_freshclam(AV_DEFINITION_PATH, CLAMAVLIB_PATH)

        # Upload updated definitions to S3
        logger.info("Uploading updated definitions to S3")
        clamav.upload_defs_to_s3(
            s3_client,
            AV_DEFINITION_S3_BUCKET,
            AV_DEFINITION_S3_PREFIX,
            AV_DEFINITION_PATH,
            extra_args={"ServerSideEncryption": "AES256"},
        )

        logger.info(f"Script finished at {get_timestamp()}")

        return {
            'statusCode': 200,
            'body': 'Virus definitions updated successfully'
        }

    except Exception as e:
        logger.error(f"Error updating virus definitions: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': f'Error updating virus definitions: {str(e)}'
        }
