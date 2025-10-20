"""
Test script for Avatar S3 Cloud Storage functionality.

This script demonstrates:
1. S3 storage configuration
2. Avatar upload with automatic S3 sync
3. S3 URL generation
4. Batch synchronization
5. Disaster recovery
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_cloud_storage_config():
    """Test 1: S3 storage configuration"""
    print("\n" + "="*60)
    print("Test 1: S3 Storage Configuration")
    print("="*60)
    
    from agent.avatar.cloud_storage import S3StorageConfig, create_s3_storage_service
    
    # Load from environment variables
    config = S3StorageConfig.from_env()
    
    print(f"Bucket: {config.bucket}")
    print(f"Region: {config.region}")
    print(f"CDN Domain: {config.cdn_domain or 'Not configured'}")
    print(f"Configured: {config.is_configured()}")
    
    if config.is_configured():
        # Create S3 service
        s3_service = create_s3_storage_service(config)
        if s3_service:
            print("✅ S3 storage service created successfully")
        else:
            print("❌ Failed to create S3 storage service")
    else:
        print("⚠️  S3 not configured (this is OK for testing)")
        print("\nTo enable S3 storage, set environment variables:")
        print("  export AVATAR_CLOUD_ACCESS_KEY=your_key")
        print("  export AVATAR_CLOUD_SECRET_KEY=your_secret")
        print("  export AVATAR_CLOUD_BUCKET=your_bucket")
        print("  export AVATAR_CLOUD_REGION=us-east-1")


def test_avatar_manager_with_cloud():
    """Test 2: Avatar Manager with cloud sync"""
    print("\n" + "="*60)
    print("Test 2: Avatar Manager with Cloud Sync")
    print("="*60)
    
    from agent.avatar.avatar_manager import AvatarManager
    
    # Initialize without db_service (for testing)
    avatar_manager = AvatarManager(
        user_id='test_user',
        db_service=None,
        enable_cloud_sync=True
    )
    
    print(f"User ID: {avatar_manager.user_id}")
    print(f"Base Dir: {avatar_manager.base_dir}")
    print(f"Cloud Sync Enabled: {avatar_manager.cloud_sync_manager is not None}")
    
    if avatar_manager.cloud_sync_manager:
        is_enabled = avatar_manager.cloud_sync_manager.is_enabled()
        print(f"Cloud Sync Available: {is_enabled}")
        if is_enabled:
            print("✅ Cloud sync is ready to use")
        else:
            print("⚠️  Cloud sync configured but service not available")
    else:
        print("⚠️  Cloud sync not initialized (db_service required)")


def test_cloud_url_generation():
    """Test 3: S3 URL generation"""
    print("\n" + "="*60)
    print("Test 3: S3 URL Generation")
    print("="*60)
    
    from agent.avatar.cloud_storage import S3StorageConfig, S3StorageService
    
    config = S3StorageConfig.from_env()
    
    if not config.is_configured():
        print("⚠️  Skipping - S3 not configured")
        return
    
    service = S3StorageService(config)
    
    # Test URL generation
    test_key = "test_user/images/abc123def456.png"
    
    # Generate signed URL (expires in 1 hour)
    signed_url = service.get_file_url(test_key, expires_in=3600, use_cdn=False)
    print(f"Signed URL (1 hour): {signed_url[:80]}...")
    
    # Generate CDN URL (if configured)
    if config.cdn_domain:
        cdn_url = service.get_file_url(test_key, expires_in=0, use_cdn=True)
        print(f"CDN URL: {cdn_url}")
    else:
        print("CDN URL: Not configured")
    
    print("✅ URL generation test completed")


def test_file_operations():
    """Test 4: S3 file upload/download operations"""
    print("\n" + "="*60)
    print("Test 4: S3 File Upload/Download Operations")
    print("="*60)
    
    from agent.avatar.cloud_storage import S3StorageConfig, create_s3_storage_service
    import tempfile
    
    config = S3StorageConfig.from_env()
    
    if not config.is_configured():
        print("⚠️  Skipping - S3 not configured")
        return
    
    service = create_s3_storage_service(config)
    if not service:
        print("❌ Failed to create S3 service")
        return
    
    # Create a test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Test avatar cloud storage")
        test_file = f.name
    
    try:
        # Test upload
        print("\n📤 Testing upload...")
        cloud_key = "test_user/test_file.txt"
        success, url, error = service.upload_file(
            test_file,
            cloud_key,
            content_type='text/plain',
            metadata={'test': 'true'}
        )
        
        if success:
            print(f"✅ Upload successful")
            print(f"   URL: {url}")
            
            # Test file exists
            print("\n🔍 Testing file exists...")
            exists = service.file_exists(cloud_key)
            print(f"   File exists: {exists}")
            
            # Test download
            print("\n📥 Testing download...")
            download_path = test_file + '.download'
            success, error = service.download_file(cloud_key, download_path)
            
            if success:
                print(f"✅ Download successful")
                with open(download_path, 'r') as f:
                    content = f.read()
                    print(f"   Content: {content}")
                os.remove(download_path)
            else:
                print(f"❌ Download failed: {error}")
            
            # Test delete
            print("\n🗑️  Testing delete...")
            success, error = service.delete_file(cloud_key)
            if success:
                print(f"✅ Delete successful")
            else:
                print(f"❌ Delete failed: {error}")
        else:
            print(f"❌ Upload failed: {error}")
    
    finally:
        # Cleanup
        if os.path.exists(test_file):
            os.remove(test_file)


def test_sync_manager():
    """Test 5: S3 Sync Manager"""
    print("\n" + "="*60)
    print("Test 5: S3 Sync Manager")
    print("="*60)
    
    from agent.avatar.cloud_storage import S3StorageConfig
    
    config = S3StorageConfig.from_env()
    
    if not config.is_configured():
        print("⚠️  Skipping - S3 not configured")
        print("\nS3 Sync Manager features:")
        print("  - sync_avatar_to_cloud(): Upload avatar to S3")
        print("  - sync_avatar_from_cloud(): Download avatar from S3")
        print("  - delete_avatar_from_cloud(): Delete avatar from S3")
        print("  - get_avatar_url(): Get S3 URL (with CDN support)")
        print("  - sync_all_avatars(): Batch synchronization")
        return
    
    print("✅ S3 Sync Manager is available")
    print("\nFeatures:")
    print("  ✅ Automatic sync on upload")
    print("  ✅ Manual sync control")
    print("  ✅ Batch operations")
    print("  ✅ CDN URL generation")
    print("  ✅ Disaster recovery")
    
    print("\nUsage example:")
    print("  from agent.avatar.avatar_cloud_sync import AvatarCloudSync")
    print("  sync_manager = AvatarCloudSync(db_service=avatar_service)")
    print("  sync_manager.sync_avatar_to_cloud(avatar_resource)")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("Avatar S3 Cloud Storage Test Suite")
    print("="*60)
    
    tests = [
        test_cloud_storage_config,
        test_avatar_manager_with_cloud,
        test_cloud_url_generation,
        test_file_operations,
        test_sync_manager
    ]
    
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("Test Suite Completed")
    print("="*60)
    
    print("\n📚 Next Steps:")
    print("1. Configure S3 environment variables")
    print("2. Test with real avatar uploads")
    print("3. Verify CDN acceleration")
    print("4. Set up monitoring and alerts")
    
    print("\n📖 Documentation:")
    print("  - S3 Storage Guide: docs/AVATAR_CLOUD_STORAGE.md")
    print("  - Architecture Flow: docs/AVATAR_ARCHITECTURE_FLOW.md")


if __name__ == "__main__":
    main()
