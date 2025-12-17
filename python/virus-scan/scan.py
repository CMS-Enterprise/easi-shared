"""
ClamAV-based virus scanning Lambda function for S3 PUT events.
Downloads virus definitions from S3 at runtime.
Logs infected files to CloudWatch without deleting them.

Features:
- Smart virus definition downloads (only when changed)
- S3 version checking for security
- SNS notifications for scan events
- CloudWatch metrics
- S3 tagging for scan results
"""
import os
import json
import logging
import boto3
from urllib.parse import unquote_plus
from typing import Dict, Any

# Import custom modules
import clamav
import metrics
from common import (
    AV_DEFINITION_S3_BUCKET,
    AV_DEFINITION_S3_PREFIX,
    AV_PROCESS_ORIGINAL_VERSION_ONLY,
    AV_SCAN_START_SNS_ARN,
    AV_STATUS_SNS_ARN,
    AV_STATUS_SNS_PUBLISH_CLEAN,
    AV_STATUS_SNS_PUBLISH_INFECTED,
    AV_SIGNATURE_METADATA,
    AV_STATUS_METADATA,
    AV_TIMESTAMP_METADATA,
    AV_SCAN_START_METADATA,
    AV_STATUS_CLEAN,
    AV_STATUS_INFECTED,
    ENV,
    get_timestamp,
    create_dir,
    str_to_bool
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
sns_client = boto3.client('sns')


def verify_s3_object_version(s3_object):
    """
    Verify that only the original version of a file is processed.

    This is a security check to prevent processing multiple versions of a file,
    which could allow an infected version to be processed while a clean version
    is still being scanned.

    Args:
        s3_object: Boto3 S3 Object resource

    Raises:
        Exception: If multiple versions detected or versioning not enabled
    """
    if not str_to_bool(AV_PROCESS_ORIGINAL_VERSION_ONLY):
        logger.info("Version checking disabled")
        return

    try:
        s3 = boto3.resource('s3')
        bucket_versioning = s3.BucketVersioning(s3_object.bucket_name)

        if bucket_versioning.status == 'Enabled':
            bucket = s3.Bucket(s3_object.bucket_name)
            versions = list(bucket.object_versions.filter(Prefix=s3_object.key))

            # Filter out delete markers and get current versions only
            current_versions = [v for v in versions if not hasattr(v, 'delete_marker') or not v.delete_marker]

            if len(current_versions) > 1:
                # Check if this object's version is the latest
                latest_version = current_versions[0]  # Versions are sorted by date, newest first

                if s3_object.version_id and s3_object.version_id != latest_version.id:
                    raise Exception(
                        f"Not processing old version of {s3_object.bucket_name}/{s3_object.key}. "
                        f"Current version: {s3_object.version_id}, Latest: {latest_version.id}"
                    )

                logger.info(f"Version check passed: processing latest version {latest_version.id}")
            else:
                logger.info(f"Version check passed: only 1 current version exists")
        else:
            # If versioning is not enabled, that's okay - just log a warning
            logger.warning(f"Object versioning not enabled in bucket {s3_object.bucket_name}")
    except Exception as e:
        logger.error(f"Version check failed: {str(e)}")
        raise


def sns_start_scan(s3_object, timestamp):
    """
    Publish scan start notification to SNS.

    Args:
        s3_object: Boto3 S3 Object resource
        timestamp: Scan start timestamp
    """
    if not AV_SCAN_START_SNS_ARN:
        return

    try:
        message = {
            'bucket': s3_object.bucket_name,
            'key': s3_object.key,
            'version': s3_object.version_id,
            AV_SCAN_START_METADATA: True,
            AV_TIMESTAMP_METADATA: timestamp,
        }

        sns_client.publish(
            TargetArn=AV_SCAN_START_SNS_ARN,
            Message=json.dumps({'default': json.dumps(message)}),
            MessageStructure='json'
        )

        logger.info(f"Published scan start notification to SNS")
    except Exception as e:
        logger.error(f"Failed to publish scan start to SNS: {str(e)}")


def sns_scan_results(s3_object, scan_status, scan_signature, timestamp):
    """
    Publish scan results to SNS.

    Args:
        s3_object: Boto3 S3 Object resource
        scan_status: Scan status (CLEAN or INFECTED)
        scan_signature: Virus signature if infected
        timestamp: Scan completion timestamp
    """
    if not AV_STATUS_SNS_ARN:
        return

    # Check if we should publish based on status
    if scan_status == AV_STATUS_CLEAN and not str_to_bool(AV_STATUS_SNS_PUBLISH_CLEAN):
        logger.info("Skipping SNS notification for CLEAN file (disabled)")
        return

    if scan_status == AV_STATUS_INFECTED and not str_to_bool(AV_STATUS_SNS_PUBLISH_INFECTED):
        logger.info("Skipping SNS notification for INFECTED file (disabled)")
        return

    try:
        message = {
            'bucket': s3_object.bucket_name,
            'key': s3_object.key,
            'version': s3_object.version_id,
            AV_SIGNATURE_METADATA: scan_signature,
            AV_STATUS_METADATA: scan_status,
            AV_TIMESTAMP_METADATA: timestamp,
        }

        sns_client.publish(
            TargetArn=AV_STATUS_SNS_ARN,
            Message=json.dumps({'default': json.dumps(message)}),
            MessageStructure='json',
            MessageAttributes={
                AV_STATUS_METADATA: {'DataType': 'String', 'StringValue': scan_status},
                AV_SIGNATURE_METADATA: {'DataType': 'String', 'StringValue': scan_signature},
            }
        )

        logger.info(f"Published scan results to SNS: {scan_status}")
    except Exception as e:
        logger.error(f"Failed to publish scan results to SNS: {str(e)}")


def tag_object(s3_object, scan_status, scan_signature, timestamp):
    """
    Tag S3 object with scan results.

    Args:
        s3_object: Boto3 S3 Object resource
        scan_status: Scan status (CLEAN or INFECTED)
        scan_signature: Virus signature if infected
        timestamp: Scan timestamp
    """
    try:
        # Get existing tags
        try:
            existing_tags = s3_client.get_object_tagging(
                Bucket=s3_object.bucket_name,
                Key=s3_object.key
            )['TagSet']
        except:
            existing_tags = []

        # Remove old scan tags
        new_tags = [
            tag for tag in existing_tags
            if tag['Key'] not in [AV_SIGNATURE_METADATA, AV_STATUS_METADATA, AV_TIMESTAMP_METADATA]
        ]

        # Add new scan tags
        new_tags.extend([
            {'Key': AV_SIGNATURE_METADATA, 'Value': scan_signature or 'none'},
            {'Key': AV_STATUS_METADATA, 'Value': scan_status},
            {'Key': AV_TIMESTAMP_METADATA, 'Value': timestamp}
        ])

        # Apply tags
        s3_client.put_object_tagging(
            Bucket=s3_object.bucket_name,
            Key=s3_object.key,
            Tagging={'TagSet': new_tags}
        )

        logger.info(f"Tagged s3://{s3_object.bucket_name}/{s3_object.key} with status: {scan_status}")

    except Exception as e:
        logger.error(f"Failed to tag object: {str(e)}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for S3 PUT events.
    Scans uploaded files for viruses and logs results to CloudWatch.

    Args:
        event: S3 event notification
        context: Lambda context

    Returns:
        Response dictionary with status and results
    """
    start_time = get_timestamp()
    logger.info(f"=== Virus scan starting at {start_time} ===")
    logger.info(f"Event: {json.dumps(event)}")

    try:
        # Parse S3 event
        # TODO check timestamp of definitions and see if need update before downloading
        # TODO decide if we want to delete virus positive files after scanning 
        # TODO Lambda logs are not tagged correctly, need to tag env and errors  
        records = event.get('Records', [])
        if not records:
            raise Exception("No records found in event")

        record = records[0]
        bucket_name = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])

        logger.info(f"Processing s3://{bucket_name}/{key}")

        # Create S3 object resource
        s3 = boto3.resource('s3')
        s3_object = s3.Object(bucket_name, key)

        # Security: Verify only original version is being processed
        verify_s3_object_version(s3_object)

        # Publish scan start notification
        sns_start_scan(s3_object, start_time)

        # Download virus definitions (smart download - only if changed)
        logger.info("Checking virus definitions...")
        clamav.download_virus_definitions(
            s3_client,
            AV_DEFINITION_S3_BUCKET,
            AV_DEFINITION_S3_PREFIX
        )

        # Download file to /tmp
        temp_dir = '/tmp/virus-scan'
        create_dir(temp_dir)
        local_file_path = os.path.join(temp_dir, os.path.basename(key))

        logger.info(f"Downloading file to {local_file_path}")
        s3_object.download_file(local_file_path)

        # Scan the file
        scan_status, scan_signature = clamav.scan_file(local_file_path)
        scan_time = get_timestamp()

        logger.info(f"Scan result: {scan_status} - {scan_signature or 'none'}")

        # Log appropriate message based on status
        if scan_status == AV_STATUS_INFECTED:
            logger.warning(
                f"INFECTED FILE DETECTED: s3://{bucket_name}/{key} - "
                f"Virus: {scan_signature}"
            )
        else:
            logger.info(f"File is clean: s3://{bucket_name}/{key}")

        # Tag the object with scan results
        tag_object(s3_object, scan_status, scan_signature, scan_time)

        # Publish scan results to SNS
        sns_scan_results(s3_object, scan_status, scan_signature, scan_time)

        # Send CloudWatch metrics
        metrics.send(
            env=ENV,
            bucket=bucket_name,
            key=key,
            status=scan_status
        )

        # Clean up downloaded file
        try:
            os.remove(local_file_path)
            logger.info(f"Cleaned up temp file: {local_file_path}")
        except OSError as e:
            logger.warning(f"Failed to clean up temp file: {str(e)}")

        end_time = get_timestamp()
        logger.info(f"=== Virus scan completed at {end_time} ===")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Virus scan completed',
                'result': {
                    'bucket': bucket_name,
                    'key': key,
                    'status': scan_status,
                    'signature': scan_signature,
                    'timestamp': scan_time
                }
            })
        }

    except Exception as e:
        logger.error(f"Error during virus scan: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error during virus scan',
                'error': str(e)
            })
        }
