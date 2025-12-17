# ClamAV S3 Virus Scanner for AWS Lambda

Production-ready serverless virus scanning solution for S3 using ClamAV. Automatically scans files uploaded to S3 and logs results to CloudWatch.

## Features

- **Virus Scanning**: Uses ClamAV to scan files uploaded to S3
- **Smart Virus Definitions**: Only downloads virus definitions from S3 when they've changed
- **Security**: Optional version checking to prevent race conditions
- **SNS Notifications**: Publishes scan start and completion events to SNS topics
- **CloudWatch Metrics**: Tracks scan results in CloudWatch metrics
- **S3 Tagging**: Tags scanned files with status, signature, and timestamp
- **No Deletion**: Infected files are logged and tagged, but NOT deleted
- **Modular Design**: Clean separation of concerns for maintainability

## Architecture

```
S3 Upload → Lambda Trigger → Virus Scan → Tag + Log + Notify
                                ↓
                         Virus Definitions (S3)
```

## Files

### Lambda Function
- `scan.py` - Main Lambda handler with all orchestration logic
- `common.py` - Shared utilities and constants
- `clamav.py` - ClamAV scanning and virus definition management
- `metrics.py` - CloudWatch metrics integration

### Build Files
- `Dockerfile.simple` - Builds ClamAV Lambda layer from pre-built packages
- `build-simple.sh` - Script to build the ClamAV layer
- `package-lambda.sh` - Script to package Lambda function code
- `build-virus-defs.sh` - Script to download virus definitions locally
- `upload-virus-defs.sh` - Script to upload virus definitions to S3

### Configuration
- `updated-iam-policy.json` - Complete IAM policy for Lambda execution role

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `AV_DEFINITION_S3_BUCKET` | S3 bucket containing virus definitions | `aws-cms-cmmi-mint-dev-app-virus-scans` |
| `AV_DEFINITION_S3_PREFIX` | S3 prefix for virus definitions | `clamav_defs/` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV` | `dev` | Environment name (for metrics) |
| `AV_PROCESS_ORIGINAL_VERSION_ONLY` | `True` | Only process original file version |
| `AV_SCAN_START_SNS_ARN` | _(empty)_ | SNS topic ARN for scan start notifications |
| `AV_STATUS_SNS_ARN` | _(empty)_ | SNS topic ARN for scan result notifications |
| `AV_STATUS_SNS_PUBLISH_CLEAN` | `False` | Publish SNS for clean files |
| `AV_STATUS_SNS_PUBLISH_INFECTED` | `True` | Publish SNS for infected files |

## Setup

### 1. Build ClamAV Layer

```bash
cd python/virus-scan
./build-simple.sh
```

This creates `layer/clamav-layer.zip` (~30-50MB).

### 2. Upload Virus Definitions to S3

```bash
# Download latest virus definitions
./build-virus-defs.sh

# Upload to S3
aws s3 sync clamAV-def/ s3://aws-cms-cmmi-mint-dev-app-virus-scans/clamav_defs/
```

### 3. Package Lambda Function

```bash
./package-lambda.sh
```

This creates `lambda-function.zip`.

### 4. Deploy to AWS

#### Create Lambda Layer

```bash
aws lambda publish-layer-version \
  --layer-name clamav-antivirus-layer \
  --description "ClamAV binaries and libraries for virus scanning" \
  --zip-file fileb://layer/clamav-layer.zip \
  --compatible-runtimes python3.14 \
  --compatible-architectures x86_64
```

#### Create Lambda Function

```bash
aws lambda create-function \
  --function-name s3-anti-virus-scan \
  --runtime python3.14 \
  --role arn:aws:iam::287978760228:role/lambda-execution-role \
  --handler scan.lambda_handler \
  --zip-file fileb://lambda-function.zip \
  --timeout 300 \
  --memory-size 2048 \
  --layers arn:aws:lambda:us-east-1:287978760228:layer:clamav-antivirus-layer:1 \
  --environment Variables='{
    "AV_DEFINITION_S3_BUCKET":"aws-cms-cmmi-mint-dev-app-virus-scans",
    "AV_DEFINITION_S3_PREFIX":"clamav_defs/",
    "ENV":"dev",
    "AV_PROCESS_ORIGINAL_VERSION_ONLY":"False"
  }'
```

#### Update Existing Function

```bash
# Update code
aws lambda update-function-code \
  --function-name s3-anti-virus-scan \
  --zip-file fileb://lambda-function.zip

# Update environment variables
aws lambda update-function-configuration \
  --function-name s3-anti-virus-scan \
  --environment Variables='{
    "AV_DEFINITION_S3_BUCKET":"aws-cms-cmmi-mint-dev-app-virus-scans",
    "AV_DEFINITION_S3_PREFIX":"clamav_defs/",
    "ENV":"dev"
  }'
```

### 5. Configure S3 Trigger

Add an S3 event notification to trigger the Lambda:

```bash
aws s3api put-bucket-notification-configuration \
  --bucket aws-cms-cmmi-mint-dev-app-file-uploads \
  --notification-configuration '{
    "LambdaFunctionConfigurations": [{
      "LambdaFunctionArn": "arn:aws:lambda:us-east-1:287978760228:function:s3-anti-virus-scan",
      "Events": ["s3:ObjectCreated:*"]
    }]
  }'
```

### 6. Update IAM Policy

Apply the IAM policy from `updated-iam-policy.json` to your Lambda execution role.

## IAM Permissions

The Lambda function requires these permissions:

- **CloudWatch Logs**: Write logs
- **CloudWatch Metrics**: Publish metrics
- **S3 (Upload Bucket)**: Read, tag objects, check versioning
- **S3 (Virus Definitions Bucket)**: Read definitions, list bucket
- **SNS** (optional): Publish notifications
- **KMS** (if using encrypted S3): Decrypt objects

See [updated-iam-policy.json](updated-iam-policy.json) for the complete policy.

## How It Works

### Scan Flow

1. **File uploaded** to S3 triggers Lambda
2. **Version check** (optional): Verifies only original version exists
3. **SNS notification** (optional): Publishes scan start event
4. **Download virus definitions** from S3 (smart download - only if changed)
5. **Download file** from S3 to /tmp
6. **Scan file** using ClamAV
7. **Tag object** with scan results
8. **Log to CloudWatch** (WARNING for infected, INFO for clean)
9. **Publish to SNS** (optional): Scan results
10. **Send metrics** to CloudWatch

### Tag Schema

Files are tagged with:
- `av-status`: `CLEAN` or `INFECTED`
- `av-signature`: Virus name (e.g., `Eicar-Signature`) or `none`
- `av-timestamp`: ISO 8601 timestamp of scan

### CloudWatch Logs

- **CLEAN files**: `INFO` level log
- **INFECTED files**: `WARNING` level log with virus details

Example infected file log:
```
INFECTED FILE DETECTED: s3://bucket/file.exe - Virus: Win.Test.EICAR_HDB-1
```

### CloudWatch Metrics

Metrics published to `ClamAV/AntiVirus` namespace:
- **Metric**: `VirusScan`
- **Dimensions**: `Environment`, `Bucket`, `Status`
- **Value**: Count (1 per scan)

### SNS Notifications

If configured, SNS messages include:
```json
{
  "bucket": "bucket-name",
  "key": "file-path",
  "version": "version-id",
  "av-status": "INFECTED",
  "av-signature": "Win.Test.EICAR_HDB-1",
  "av-timestamp": "2025-12-15T10:30:00.123456"
}
```

## Security Features

### Version Checking

When `AV_PROCESS_ORIGINAL_VERSION_ONLY=True`:
- Verifies bucket versioning is enabled
- Ensures only one version of the file exists
- Prevents race condition attacks where infected file is uploaded while clean version is being scanned

**Important**: Requires S3 bucket versioning to be enabled.

### No Deletion Policy

This implementation does NOT delete infected files. Instead:
- Files are tagged with infection status
- CloudWatch logs capture infection details
- SNS can notify downstream systems
- Security teams can review infected files

To delete infected files, add logic to call `s3_object.delete()` after tagging.

## Maintenance

### Update Virus Definitions

Virus definitions should be updated regularly (daily recommended):

```bash
# Download latest definitions
./build-virus-defs.sh

# Upload to S3
aws s3 sync clamAV-def/ s3://aws-cms-cmmi-mint-dev-app-virus-scans/clamav_defs/
```

Or automate with a scheduled Lambda/EventBridge rule.

### Update ClamAV Layer

When ClamAV releases updates:

```bash
# Rebuild layer
./build-simple.sh

# Publish new version
aws lambda publish-layer-version \
  --layer-name clamav-antivirus-layer \
  --zip-file fileb://layer/clamav-layer.zip \
  --compatible-runtimes python3.14

# Update function to use new layer version
aws lambda update-function-configuration \
  --function-name s3-anti-virus-scan \
  --layers arn:aws:lambda:us-east-1:287978760228:layer:clamav-antivirus-layer:2
```

## Troubleshooting

### GLIBC Version Errors

If you see errors about GLIBC versions:
- Ensure you're building with `--platform linux/amd64`
- Verify Dockerfile excludes system libraries (libc, libm, etc.)
- Lambda runtime provides system libraries

### AccessDenied Errors

Check IAM policy includes all required permissions from `updated-iam-policy.json`.

### Virus Definitions Not Found

Ensure:
- `AV_DEFINITION_S3_BUCKET` and `AV_DEFINITION_S3_PREFIX` are set correctly
- Virus definition files exist in S3
- Lambda has `s3:GetObject` and `s3:ListBucket` permissions

### Timeout Errors

Large files may take longer to scan. Increase Lambda timeout:

```bash
aws lambda update-function-configuration \
  --function-name s3-anti-virus-scan \
  --timeout 600
```

## Testing

Test with EICAR test file (safe test virus):

```bash
# Create EICAR test file
echo 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > eicar.txt

# Upload to S3
aws s3 cp eicar.txt s3://aws-cms-cmmi-mint-dev-app-file-uploads/test/eicar.txt

# Check CloudWatch Logs
aws logs tail /aws/lambda/s3-anti-virus-scan --follow

# Check tags
aws s3api get-object-tagging \
  --bucket aws-cms-cmmi-mint-dev-app-file-uploads \
  --key test/eicar.txt
```

Expected result: File tagged with `av-status: INFECTED` and CloudWatch WARNING log.

## Cost Estimation

- **Lambda**: ~$0.20 per 1M scans (2GB memory, 30s avg duration)
- **S3**: Standard S3 pricing for reads
- **CloudWatch**: Logs and metrics (minimal)
- **Layer storage**: ~$0.03/month per GB

## Credits

Based on concepts from [Upside Travel bucket-antivirus-function](https://github.com/upsidetravel/bucket-antivirus-function).

## License

Apache License 2.0
