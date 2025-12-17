"""
ClamAV virus scanning functions with smart definition management.
"""
import os
import logging
import subprocess
from typing import Dict, Tuple

from common import (
    CLAMSCAN_PATH,
    CLAMAV_DB_PATH,
    FRESHCLAM_PATH,
    CLAMAVLIB_PATH,
    AV_DEFINITION_PATH,
    AV_STATUS_CLEAN,
    AV_STATUS_INFECTED
)

logger = logging.getLogger()

# Track if definitions are loaded
DEFS_LOADED = False


def update_defs_from_s3(s3_client, bucket, prefix):
    """
    Determine which virus definition files need to be downloaded from S3.

    Compares local and S3 timestamps to only download files that have changed.

    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket containing virus definitions
        prefix: S3 prefix for virus definitions

    Returns:
        Dictionary of files to download with their S3 and local paths
    """
    to_download = {}

    # Create local directory
    os.makedirs(CLAMAV_DB_PATH, exist_ok=True)

    # List all definition files in S3
    try:
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)

        if 'Contents' not in response:
            logger.warning(f"No virus definitions found in s3://{bucket}/{prefix}")
            return to_download

        for s3_object in response['Contents']:
            s3_key = s3_object['Key']
            filename = os.path.basename(s3_key)

            # Skip directory markers
            if not filename:
                continue

            # Only process .cvd and .cld files
            if not (filename.endswith('.cvd') or filename.endswith('.cld')):
                continue

            local_path = os.path.join(CLAMAV_DB_PATH, filename)
            s3_modified = s3_object['LastModified']

            # Check if we need to download
            download_file = False

            if not os.path.exists(local_path):
                logger.info(f"{filename} does not exist locally, will download")
                download_file = True
            else:
                # Compare timestamps
                local_modified = os.path.getmtime(local_path)

                # Convert S3 timestamp to epoch for comparison
                s3_timestamp = s3_modified.timestamp()

                if s3_timestamp > local_modified:
                    logger.info(f"{filename} is newer in S3, will download")
                    download_file = True
                else:
                    logger.info(f"{filename} is up to date")

            if download_file:
                to_download[filename] = {
                    's3_path': s3_key,
                    'local_path': local_path
                }

        return to_download

    except Exception as e:
        logger.error(f"Error checking virus definitions in S3: {str(e)}")
        raise


def download_virus_definitions(s3_client, bucket, prefix):
    """
    Download virus definitions from S3, only if they've changed.

    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket containing virus definitions
        prefix: S3 prefix for virus definitions
    """
    global DEFS_LOADED

    if not bucket:
        logger.error("Virus definitions bucket not configured")
        raise Exception("AV_DEFINITION_S3_BUCKET environment variable not set")

    logger.info(f"Checking virus definitions in s3://{bucket}/{prefix}")

    # Determine what needs to be downloaded
    to_download = update_defs_from_s3(s3_client, bucket, prefix)

    if not to_download:
        logger.info("All virus definitions are up to date")
        DEFS_LOADED = True
        return

    # Download each file
    for filename, paths in to_download.items():
        s3_path = paths['s3_path']
        local_path = paths['local_path']

        logger.info(f"Downloading {filename} from s3://{bucket}/{s3_path}")

        try:
            s3_client.download_file(bucket, s3_path, local_path)
            logger.info(f"Downloaded {filename} successfully")
        except Exception as e:
            logger.error(f"Failed to download {filename}: {str(e)}")
            raise

    DEFS_LOADED = True
    logger.info("Virus definitions updated successfully")


def scan_file(file_path: str) -> Tuple[str, str]:
    """
    Scan a file using ClamAV.

    Args:
        file_path: Path to the file to scan

    Returns:
        Tuple of (status, signature):
        - status: AV_STATUS_CLEAN or AV_STATUS_INFECTED
        - signature: Virus signature name if infected, else empty string
    """
    try:
        logger.info(f"Scanning file: {file_path}")

        # Run clamscan
        result = subprocess.run(
            [
                CLAMSCAN_PATH,
                '--database=' + CLAMAV_DB_PATH,
                '--no-summary',
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=300
        )

        scan_output = result.stdout + result.stderr
        logger.info(f"Scan output: {scan_output}")

        # ClamAV return codes:
        # 0 = No virus found
        # 1 = Virus found
        # 2+ = Error

        if result.returncode == 0:
            return (AV_STATUS_CLEAN, '')

        elif result.returncode == 1:
            # Extract virus signature from output
            virus_signature = 'Unknown'
            for line in scan_output.split('\n'):
                if 'FOUND' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        virus_signature = parts[1].strip().replace('FOUND', '').strip()
                    break

            return (AV_STATUS_INFECTED, virus_signature)

        else:
            logger.error(f"ClamAV scan error (return code {result.returncode}): {scan_output}")
            raise Exception(f"ClamAV scan failed with return code {result.returncode}")

    except subprocess.TimeoutExpired:
        logger.error("ClamAV scan timed out")
        raise Exception("Virus scan timed out after 300 seconds")

    except Exception as e:
        logger.error(f"Error during virus scan: {str(e)}")
        raise


def update_defs_from_freshclam(db_path: str, lib_path: str):
    """
    Update virus definitions using freshclam.

    Args:
        db_path: Path to virus definition database directory
        lib_path: Path to ClamAV library directory
    """
    try:
        logger.info("Updating virus definitions using freshclam")

        # Ensure database directory exists
        os.makedirs(db_path, exist_ok=True)

        # Run freshclam to update definitions
        result = subprocess.run(
            [
                FRESHCLAM_PATH,
                f'--datadir={db_path}',
                f'--config-file=/opt/etc/freshclam.conf',
                '--no-warnings'
            ],
            capture_output=True,
            text=True,
            timeout=300
        )

        output = result.stdout + result.stderr
        logger.info(f"Freshclam output: {output}")

        if result.returncode != 0:
            logger.warning(f"Freshclam returned non-zero exit code: {result.returncode}")
        else:
            logger.info("Freshclam update completed successfully")

    except subprocess.TimeoutExpired:
        logger.error("Freshclam update timed out")
        raise Exception("Freshclam update timed out after 300 seconds")

    except Exception as e:
        logger.error(f"Error updating definitions with freshclam: {str(e)}")
        raise


def upload_defs_to_s3(s3_client, bucket: str, prefix: str, db_path: str, extra_args: dict = None):
    """
    Upload virus definition files to S3.

    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket to upload to
        prefix: S3 prefix for virus definitions
        db_path: Local path to virus definition files
        extra_args: Extra arguments to pass to S3 upload (e.g., ServerSideEncryption)
    """
    try:
        logger.info(f"Uploading virus definitions to s3://{bucket}/{prefix}")

        # Get list of definition files to upload
        definition_files = []
        for filename in os.listdir(db_path):
            if filename.endswith('.cvd') or filename.endswith('.cld'):
                definition_files.append(filename)

        if not definition_files:
            logger.warning("No definition files found to upload")
            return

        logger.info(f"Found {len(definition_files)} definition files to upload")

        # Upload each file
        for filename in definition_files:
            local_path = os.path.join(db_path, filename)
            s3_key = os.path.join(prefix, filename)

            logger.info(f"Uploading {filename} to s3://{bucket}/{s3_key}")

            upload_kwargs = {
                'Bucket': bucket,
                'Key': s3_key,
                'Filename': local_path
            }

            if extra_args:
                upload_kwargs['ExtraArgs'] = extra_args

            s3_client.upload_file(**upload_kwargs)
            logger.info(f"Successfully uploaded {filename}")

        logger.info("All virus definitions uploaded successfully")

    except Exception as e:
        logger.error(f"Error uploading definitions to S3: {str(e)}")
        raise
