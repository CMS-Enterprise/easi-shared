"""
CloudWatch metrics for virus scanning operations.
"""
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

cloudwatch = boto3.client('cloudwatch')


def send(env, bucket, key, status):
    """
    Send CloudWatch metrics for virus scan results.

    Args:
        env: Environment name (dev, staging, prod)
        bucket: S3 bucket name
        key: S3 object key
        status: Scan status (CLEAN or INFECTED)
    """
    try:
        metric_data = [
            {
                'MetricName': 'VirusScan',
                'Dimensions': [
                    {'Name': 'Environment', 'Value': env},
                    {'Name': 'Bucket', 'Value': bucket},
                    {'Name': 'Status', 'Value': status}
                ],
                'Value': 1,
                'Unit': 'Count'
            }
        ]

        cloudwatch.put_metric_data(
            Namespace='ClamAV/AntiVirus',
            MetricData=metric_data
        )

        logger.info(f"Sent CloudWatch metric: {status} for s3://{bucket}/{key} in {env}")

    except ClientError as e:
        logger.error(f"Failed to send CloudWatch metrics: {str(e)}")
        # Don't raise - metrics failure shouldn't fail the scan
    except Exception as e:
        logger.error(f"Unexpected error sending metrics: {str(e)}")
