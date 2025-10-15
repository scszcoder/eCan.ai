# AWS S3 Release Setup Guide

This guide explains how to configure AWS S3 for hosting eCan release artifacts and OTA updates.

## Overview

The release workflow uploads build artifacts (EXE, PKG installers) to AWS S3 instead of GitHub Releases, providing:

- **Faster downloads**: Direct S3 downloads without GitHub API rate limits
- **Better control**: Full control over file organization and access
- **Cost-effective**: S3 storage is cheaper than GitHub bandwidth for large files
- **CDN integration**: Easy CloudFront integration for global distribution
- **Organized structure**: Standardized directory layout for all versions

## S3 Directory Structure

```
s3://your-bucket/
├── releases/
│   ├── v0.0.1/
│   │   ├── windows/
│   │   │   ├── eCan-0.0.1-windows-amd64.exe
│   │   │   └── eCan-0.0.1-windows-amd64-Setup.exe
│   │   ├── macos/
│   │   │   ├── eCan-0.0.1-macos-amd64.pkg
│   │   │   └── eCan-0.0.1-macos-aarch64.pkg
│   │   ├── checksums/
│   │   │   └── SHA256SUMS
│   │   └── version-metadata.json
│   ├── v0.0.2/
│   │   └── ...
│   └── latest/
│       ├── windows/
│       ├── macos/
│       └── checksums/
```

## AWS Configuration

### 1. Create S3 Bucket

1. Go to [AWS S3 Console](https://s3.console.aws.amazon.com/)
2. Click **Create bucket**
3. Configure:
   - **Bucket name**: `ecan-releases` (or your preferred name)
   - **Region**: `us-east-1` (or your preferred region)
   - **Block Public Access**: Uncheck "Block all public access" (we need public read)
   - **Bucket Versioning**: Enable (recommended)
   - **Tags**: Add relevant tags for cost tracking

4. Click **Create bucket**

### 2. Configure Bucket Policy

Add this bucket policy to allow public read access:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::ecan-releases/*"
        }
    ]
}
```

**To apply:**
1. Go to bucket → **Permissions** tab
2. Scroll to **Bucket policy**
3. Click **Edit** and paste the policy
4. Replace `ecan-releases` with your bucket name
5. Click **Save changes**

### 3. Create IAM User for GitHub Actions

1. Go to [IAM Console](https://console.aws.amazon.com/iam/)
2. Click **Users** → **Add users**
3. User name: `github-actions-ecan-release`
4. Select **Access key - Programmatic access**
5. Click **Next: Permissions**

### 4. Create IAM Policy

Create a custom policy with minimal required permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "S3ListBucket",
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:GetBucketLocation"
            ],
            "Resource": "arn:aws:s3:::ecan-releases"
        },
        {
            "Sid": "S3ObjectOperations",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::ecan-releases/*"
        }
    ]
}
```

**To create:**
1. In IAM → **Policies** → **Create policy**
2. Click **JSON** tab and paste the policy
3. Replace `ecan-releases` with your bucket name
4. Click **Next: Tags** → **Next: Review**
5. Name: `GitHubActionsECanReleasePolicy`
6. Click **Create policy**

### 5. Attach Policy to User

1. Go back to user creation
2. Click **Attach existing policies directly**
3. Search for `GitHubActionsECanReleasePolicy`
4. Check the policy
5. Click **Next: Tags** → **Next: Review** → **Create user**

### 6. Save Access Keys

1. After user creation, you'll see **Access key ID** and **Secret access key**
2. **IMPORTANT**: Copy these values - you won't see the secret again!
3. Store them securely for the next step

## GitHub Secrets Configuration

Add these secrets to your GitHub repository:

### Required Secrets

Go to **Repository Settings** → **Secrets and variables** → **Actions** → **New repository secret**

1. **AWS_ACCESS_KEY_ID**
   - Value: Your IAM user access key ID
   - Example: `AKIAIOSFODNN7EXAMPLE`

2. **AWS_SECRET_ACCESS_KEY**
   - Value: Your IAM user secret access key
   - Example: `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`

3. **S3_BUCKET**
   - Value: Your S3 bucket name
   - Example: `ecan-releases`

### Optional Secrets

4. **AWS_REGION** (optional, defaults to `us-east-1`)
   - Value: Your S3 bucket region
   - Example: `us-west-2`

5. **S3_BASE_PATH** (optional, defaults to `releases`)
   - Value: Base path within bucket
   - Example: `releases` or `downloads`

## Workflow Configuration

The release workflow automatically:

1. **Builds** Windows and macOS installers
2. **Uploads** to S3 with organized structure:
   - Version-specific directory: `releases/v{version}/`
   - Platform subdirectories: `windows/`, `macos/`
   - Checksums directory: `checksums/`
3. **Updates** latest version directory
4. **Generates** appcast.xml with S3 URLs
5. **Creates** version metadata JSON

### S3 Upload Job

The `upload-to-s3` job:
- Downloads all build artifacts
- Organizes files by platform
- Generates SHA256 checksums
- Uploads to S3 with public-read ACL
- Sets cache headers for optimal performance
- Creates version metadata

### Appcast Generation

The `publish-appcast` job:
- Uses S3 URLs instead of GitHub release URLs
- Generates signed appcast.xml files
- Publishes to gh-pages for OTA updates

## Download URLs

After release, files are available at:

### Version-specific URLs
```
https://{bucket}.s3.{region}.amazonaws.com/releases/v{version}/windows/eCan-{version}-windows-amd64-Setup.exe
https://{bucket}.s3.{region}.amazonaws.com/releases/v{version}/macos/eCan-{version}-macos-amd64.pkg
https://{bucket}.s3.{region}.amazonaws.com/releases/v{version}/checksums/SHA256SUMS
```

### Latest version URLs
```
https://{bucket}.s3.{region}.amazonaws.com/releases/latest/windows/eCan-{version}-windows-amd64-Setup.exe
https://{bucket}.s3.{region}.amazonaws.com/releases/latest/macos/eCan-{version}-macos-amd64.pkg
```

### Metadata
```
https://{bucket}.s3.{region}.amazonaws.com/releases/v{version}/version-metadata.json
```

## CloudFront CDN (Optional)

For better global performance, add CloudFront:

1. Go to [CloudFront Console](https://console.aws.amazon.com/cloudfront/)
2. Click **Create Distribution**
3. Configure:
   - **Origin Domain**: Select your S3 bucket
   - **Origin Path**: `/releases` (optional)
   - **Viewer Protocol Policy**: Redirect HTTP to HTTPS
   - **Cache Policy**: CachingOptimized
   - **Price Class**: Use all edge locations (or select regions)

4. After creation, use CloudFront URL:
   ```
   https://d1234567890.cloudfront.net/v{version}/windows/eCan-{version}-windows-amd64-Setup.exe
   ```

## Testing

### Test S3 Upload

1. Trigger workflow manually:
   ```bash
   gh workflow run release.yml -f platform=all -f arch=all -f ref=master
   ```

2. Check workflow logs for:
   ```
   === Uploading artifacts to S3 ===
   S3 bucket: ecan-releases
   S3 path: releases/v{version}
   ```

3. Verify files in S3 Console

### Test Download

```bash
# Test Windows installer
curl -I https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v0.0.1/windows/eCan-0.0.1-windows-amd64-Setup.exe

# Test macOS installer
curl -I https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v0.0.1/macos/eCan-0.0.1-macos-amd64.pkg

# Test checksums
curl https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v0.0.1/checksums/SHA256SUMS
```

### Verify Appcast

Check appcast URLs point to S3:

```bash
curl https://scszcoder.github.io/ecbot/appcast-windows.xml | grep "url="
curl https://scszcoder.github.io/ecbot/appcast-macos.xml | grep "url="
```

Should show S3 URLs like:
```xml
<enclosure url="https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v0.0.1/windows/..." />
```

## Cost Estimation

### S3 Storage
- **Standard storage**: $0.023 per GB/month
- **Example**: 500MB installer × 10 versions = 5GB = ~$0.12/month

### S3 Data Transfer
- **First 100GB/month**: Free
- **Next 10TB/month**: $0.09 per GB
- **Example**: 1000 downloads × 500MB = 500GB = ~$36/month

### CloudFront (Optional)
- **First 1TB/month**: $0.085 per GB
- **Example**: 1000 downloads × 500MB = 500GB = ~$42.50/month

## Troubleshooting

### Upload Fails

**Error**: `Access Denied`
- Check IAM policy has `s3:PutObject` permission
- Verify bucket name in secrets matches actual bucket
- Ensure AWS credentials are correct

**Error**: `Bucket not found`
- Verify `S3_BUCKET` secret is set correctly
- Check bucket exists in specified region
- Ensure region matches `AWS_REGION` secret

### Download Fails

**Error**: `403 Forbidden`
- Check bucket policy allows public read
- Verify ACL is set to `public-read` during upload
- Check Block Public Access settings

**Error**: `404 Not Found`
- Verify file was uploaded successfully
- Check S3 path structure matches expected format
- Ensure workflow completed successfully

### Appcast Issues

**URLs point to GitHub instead of S3**
- Check `publish-appcast` job depends on `upload-to-s3`
- Verify `S3_BASE_URL` is passed correctly
- Check Python script uses `s3_base_url` variable

## Security Best Practices

1. **IAM User**: Use dedicated user with minimal permissions
2. **Access Keys**: Rotate regularly (every 90 days)
3. **Bucket Policy**: Only allow public read, not write
4. **Encryption**: Enable S3 default encryption
5. **Versioning**: Enable for recovery from accidental deletion
6. **Logging**: Enable S3 access logging for audit trail
7. **MFA Delete**: Enable for production buckets

## Migration from GitHub Releases

To migrate from GitHub Releases to S3:

1. Set up S3 and configure secrets (this guide)
2. Run release workflow - it will upload to both S3 and GitHub
3. Verify S3 downloads work correctly
4. Update appcast URLs (automatic in workflow)
5. Monitor OTA updates work with S3 URLs
6. Optionally disable GitHub release creation by removing `create-release` job

## Support

For issues:
- Check [GitHub Actions logs](https://github.com/scszcoder/ecbot/actions)
- Review [AWS S3 documentation](https://docs.aws.amazon.com/s3/)
- Open issue on [GitHub](https://github.com/scszcoder/ecbot/issues)
