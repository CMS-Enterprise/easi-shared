"""
Common utilities and constants for ClamAV virus scanning Lambda.
"""
import os
import logging
from datetime import datetime

logger = logging.getLogger()

# Environment variable names and defaults
AV_DEFINITION_S3_BUCKET = os.environ.get('AV_DEFINITION_S3_BUCKET', '')
AV_DEFINITION_S3_PREFIX = os.environ.get('AV_DEFINITION_S3_PREFIX', 'clamav_defs/')
AV_PROCESS_ORIGINAL_VERSION_ONLY = os.environ.get('AV_PROCESS_ORIGINAL_VERSION_ONLY', 'True')
AV_SCAN_START_SNS_ARN = os.environ.get('AV_SCAN_START_SNS_ARN', '')
AV_STATUS_SNS_ARN = os.environ.get('AV_STATUS_SNS_ARN', '')
AV_STATUS_SNS_PUBLISH_CLEAN = os.environ.get('AV_STATUS_SNS_PUBLISH_CLEAN', 'False')
AV_STATUS_SNS_PUBLISH_INFECTED = os.environ.get('AV_STATUS_SNS_PUBLISH_INFECTED', 'True')
ENV = os.environ.get('ENV', 'dev')

# Metadata/Tag keys
AV_SIGNATURE_METADATA = 'av-signature'
AV_STATUS_METADATA = 'av-status'
AV_TIMESTAMP_METADATA = 'av-timestamp'
AV_SCAN_START_METADATA = 'av-scan-start'

# Status values
AV_STATUS_CLEAN = 'CLEAN'
AV_STATUS_INFECTED = 'INFECTED'

# ClamAV paths
CLAMSCAN_PATH = '/opt/bin/clamscan'
FRESHCLAM_PATH = '/opt/bin/freshclam'
CLAMAV_DB_PATH = '/tmp/clamav'
CLAMAVLIB_PATH = '/opt/lib'
AV_DEFINITION_PATH = '/tmp/clamav'
S3_ENDPOINT = os.environ.get('S3_ENDPOINT', None)


def get_timestamp():
    """Get current timestamp in ISO format."""
    return datetime.utcnow().isoformat()


def create_dir(directory):
    """Create directory if it doesn't exist."""
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.info(f"Created directory: {directory}")


def str_to_bool(value):
    """Convert string to boolean."""
    if isinstance(value, bool):
        return value
    return str(value).lower() in ('true', '1', 'yes', 'on')
