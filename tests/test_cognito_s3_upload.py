"""
Test script to verify Cognito credentials can be used for S3 upload/download.

This script tests:
1. Getting AWS temporary credentials from Cognito ID token
2. Using those credentials to upload a file to S3
3. Downloading the file back from S3
4. Deleting the test file from S3
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_cognito_credentials():
    """Test getting AWS credentials from Cognito"""
    from auth.aws_credentials_provider import create_credentials_provider
    from auth.auth_manager import AuthManager
    
    print("\n" + "="*60)
    print("Testing Cognito AWS Credentials Provider")
    print("="*60)
    
    # Create credentials provider
    provider = create_credentials_provider()
    if not provider:
        print("❌ Failed to create credentials provider")
        print("   Make sure COGNITO.IDENTITY_POOL_ID is configured in auth_config.yml")
        return None
    
    print("✅ Credentials provider created")
    print(f"   Identity Pool ID: {provider.identity_pool_id}")
    print(f"   Region: {provider.region}")
    
    # Get ID token from auth manager
    # Note: This requires user to be logged in
    print("\n📝 Note: This test requires a valid user session")
    print("   Please ensure you have logged in before running this test")
    
    # For testing, you can manually provide an ID token
    # Or use the auth manager if available
    id_token = os.getenv('TEST_ID_TOKEN')
    
    if not id_token:
        print("\n⚠️  No ID token provided")
        print("   Set TEST_ID_TOKEN environment variable with a valid Cognito ID token")
        print("   Or run this test after logging in to the application")
        return None
    
    print("\n🔑 Getting AWS credentials from Cognito...")
    credentials = provider.get_credentials(id_token)
    
    if not credentials:
        print("❌ Failed to get AWS credentials")
        return None
    
    print("✅ Got AWS credentials successfully")
    print(f"   Access Key ID: {credentials['AccessKeyId'][:10]}...")
    print(f"   Expiration: {credentials['Expiration']}")
    
    return credentials


def test_s3_operations(credentials):
    """Test S3 upload/download/delete operations"""
    import boto3
    from botocore.exceptions import ClientError
    import tempfile
    
    print("\n" + "="*60)
    print("Testing S3 Operations with Cognito Credentials")
    print("="*60)
    
    # Get bucket name from environment
    bucket = os.getenv('AVATAR_CLOUD_BUCKET', 'ecan-avatars')
    region = os.getenv('AVATAR_CLOUD_REGION', 'us-east-1')
    
    print(f"\n📦 S3 Bucket: {bucket}")
    print(f"🌍 Region: {region}")
    
    # Create S3 client with Cognito credentials
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=region
        )
        print("✅ S3 client created with Cognito credentials")
    except Exception as e:
        print(f"❌ Failed to create S3 client: {e}")
        return False
    
    # Test file
    test_key = 'avatars/test/cognito_test.txt'
    test_content = b'Test content from Cognito credentials'
    
    # Test 1: Upload
    print("\n📤 Test 1: Upload file to S3")
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=test_key,
            Body=test_content,
            ContentType='text/plain'
        )
        print(f"✅ Upload successful: s3://{bucket}/{test_key}")
    except ClientError as e:
        print(f"❌ Upload failed: {e}")
        print(f"   Error code: {e.response['Error']['Code']}")
        print(f"   Error message: {e.response['Error']['Message']}")
        return False
    
    # Test 2: Download
    print("\n📥 Test 2: Download file from S3")
    try:
        response = s3_client.get_object(Bucket=bucket, Key=test_key)
        downloaded_content = response['Body'].read()
        
        if downloaded_content == test_content:
            print("✅ Download successful and content matches")
        else:
            print("❌ Downloaded content doesn't match")
            return False
    except ClientError as e:
        print(f"❌ Download failed: {e}")
        return False
    
    # Test 3: Delete
    print("\n🗑️  Test 3: Delete file from S3")
    try:
        s3_client.delete_object(Bucket=bucket, Key=test_key)
        print("✅ Delete successful")
    except ClientError as e:
        print(f"❌ Delete failed: {e}")
        return False
    
    print("\n" + "="*60)
    print("✅ All S3 operations completed successfully!")
    print("="*60)
    
    return True


def test_s3_storage_service():
    """Test S3StorageService with Cognito credentials"""
    from agent.avatar.cloud_storage import create_s3_storage_service, S3StorageConfig
    import tempfile
    
    print("\n" + "="*60)
    print("Testing S3StorageService with Cognito Credentials")
    print("="*60)
    
    # Create S3 storage service (will auto-detect Cognito credentials)
    print("\n🔧 Creating S3 storage service...")
    
    # Configure bucket name
    config = S3StorageConfig(
        bucket=os.getenv('AVATAR_CLOUD_BUCKET', 'ecan-avatars'),
        region=os.getenv('AVATAR_CLOUD_REGION', 'us-east-1'),
        path_prefix='avatars/'
    )
    
    storage_service = create_s3_storage_service(config, use_cognito_credentials=True)
    
    if not storage_service:
        print("❌ Failed to create S3 storage service")
        print("   Make sure you are logged in and Cognito is configured")
        return False
    
    print("✅ S3 storage service created")
    
    # Create a test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('Test content from S3StorageService')
        test_file_path = f.name
    
    try:
        test_key = 'test/storage_service_test.txt'
        
        # Test upload
        print(f"\n📤 Uploading test file...")
        success, url, error = storage_service.upload_file(
            test_file_path,
            test_key,
            content_type='text/plain'
        )
        
        if not success:
            print(f"❌ Upload failed: {error}")
            return False
        
        print(f"✅ Upload successful")
        print(f"   URL: {url}")
        
        # Test download
        print(f"\n📥 Downloading test file...")
        download_path = test_file_path + '.downloaded'
        success, error = storage_service.download_file(test_key, download_path)
        
        if not success:
            print(f"❌ Download failed: {error}")
            return False
        
        print(f"✅ Download successful")
        
        # Verify content
        with open(download_path, 'r') as f:
            content = f.read()
            if content == 'Test content from S3StorageService':
                print("✅ Content verified")
            else:
                print("❌ Content mismatch")
                return False
        
        # Test delete
        print(f"\n🗑️  Deleting test file...")
        success, error = storage_service.delete_file(test_key)
        
        if not success:
            print(f"❌ Delete failed: {error}")
            return False
        
        print(f"✅ Delete successful")
        
        print("\n" + "="*60)
        print("✅ S3StorageService test completed successfully!")
        print("="*60)
        
        return True
        
    finally:
        # Cleanup
        if os.path.exists(test_file_path):
            os.unlink(test_file_path)
        if os.path.exists(download_path):
            os.unlink(download_path)


def main():
    """Main test function"""
    print("\n" + "="*80)
    print(" Cognito S3 Upload/Download Test Suite")
    print("="*80)
    
    # Test 1: Get Cognito credentials
    credentials = test_cognito_credentials()
    
    if credentials:
        # Test 2: S3 operations with boto3 client
        test_s3_operations(credentials)
    
    # Test 3: S3StorageService (will auto-get Cognito credentials)
    # Note: This requires being logged in to the application
    # test_s3_storage_service()
    
    print("\n" + "="*80)
    print(" Test Suite Completed")
    print("="*80)
    print("\n📝 Notes:")
    print("   - To test S3StorageService, run this from within the application")
    print("   - Or set TEST_ID_TOKEN environment variable with a valid ID token")
    print("   - Make sure AVATAR_CLOUD_BUCKET is configured")
    print("\n")


if __name__ == '__main__':
    main()
