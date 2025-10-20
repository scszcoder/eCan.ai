"""
Test script for StandardS3Uploader

This script demonstrates how to use the standardized S3 uploader.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_path_generator():
    """Test S3PathGenerator"""
    print("\n" + "="*60)
    print("Testing S3PathGenerator")
    print("="*60)
    
    from agent.cloud import S3PathGenerator
    
    # Test 1: Avatar image path
    path1 = S3PathGenerator.generate_path(
        resource_type='avatar',
        owner='user@example.com',
        file_category='image',
        file_hash='abc123def456',
        file_ext='.png'
    )
    print(f"\n✅ Avatar image path: {path1}")
    assert path1 == 'avatars/user@example.com/images/abc123def456.png'
    
    # Test 2: Avatar video path
    path2 = S3PathGenerator.generate_path(
        resource_type='avatar',
        owner='user@example.com',
        file_category='video',
        file_hash='xyz789abc123',
        file_ext='.mp4'
    )
    print(f"✅ Avatar video path: {path2}")
    assert path2 == 'avatars/user@example.com/videos/xyz789abc123.mp4'
    
    # Test 3: Document with date prefix
    path3 = S3PathGenerator.generate_path(
        resource_type='document',
        owner='user@example.com',
        file_category='pdf',
        file_hash='report_hash',
        file_ext='.pdf',
        date_prefix=True
    )
    print(f"✅ Document path (with date): {path3}")
    assert 'documents/user@example.com/pdfs/' in path3
    assert '/report_hash.pdf' in path3
    
    # Test 4: Parse path
    parsed = S3PathGenerator.parse_path(path1)
    print(f"\n✅ Parsed path: {parsed}")
    assert parsed['resource_type'] == 'avatars'
    assert parsed['owner'] == 'user@example.com'
    assert parsed['file_category'] == 'images'
    assert parsed['file_hash'] == 'abc123def456'
    assert parsed['file_ext'] == '.png'
    
    print("\n✅ All S3PathGenerator tests passed!")


def test_standard_uploader_mock():
    """Test StandardS3Uploader with mock S3 service"""
    print("\n" + "="*60)
    print("Testing StandardS3Uploader (Mock)")
    print("="*60)
    
    from agent.cloud import StandardS3Uploader
    
    # Create a mock S3 service
    class MockS3Service:
        def upload_file(self, local_path, cloud_key, content_type=None, metadata=None):
            print(f"\n📤 Mock upload:")
            print(f"   Local: {local_path}")
            print(f"   S3 Key: {cloud_key}")
            print(f"   Content-Type: {content_type}")
            print(f"   Metadata: {metadata}")
            
            # Simulate successful upload
            url = f"https://ecan-avatars.s3.amazonaws.com/{cloud_key}"
            return True, url, ""
        
        def download_file(self, cloud_key, local_path):
            print(f"\n📥 Mock download:")
            print(f"   S3 Key: {cloud_key}")
            print(f"   Local: {local_path}")
            return True, ""
        
        def delete_file(self, cloud_key):
            print(f"\n🗑️  Mock delete:")
            print(f"   S3 Key: {cloud_key}")
            return True, ""
    
    # Create uploader with mock service
    mock_service = MockS3Service()
    uploader = StandardS3Uploader(mock_service)
    
    # Test upload
    print("\n--- Test Upload ---")
    success, url, error = uploader.upload(
        local_path='/path/to/avatar.png',
        owner='user@example.com',
        resource_type='avatar',
        resource_id='avatar_123',
        file_category='image',
        file_hash='abc123def456',
        extra_metadata={
            'avatar_type': 'uploaded',
            'format': 'png'
        }
    )
    
    print(f"\n✅ Upload result:")
    print(f"   Success: {success}")
    print(f"   URL: {url}")
    
    assert success == True
    assert 'avatars/user@example.com/images/abc123def456.png' in url
    
    # Test download
    print("\n--- Test Download ---")
    success, error = uploader.download(
        owner='user@example.com',
        resource_type='avatar',
        file_category='image',
        file_hash='abc123def456',
        file_ext='.png',
        local_path='/tmp/downloaded_avatar.png'
    )
    
    print(f"\n✅ Download result:")
    print(f"   Success: {success}")
    
    assert success == True
    
    # Test delete
    print("\n--- Test Delete ---")
    success, error = uploader.delete(
        owner='user@example.com',
        resource_type='avatar',
        file_category='image',
        file_hash='abc123def456',
        file_ext='.png'
    )
    
    print(f"\n✅ Delete result:")
    print(f"   Success: {success}")
    
    assert success == True
    
    print("\n✅ All StandardS3Uploader tests passed!")


def test_real_s3_upload():
    """
    Test with real S3 service (requires configuration)
    
    Set these environment variables:
    - AVATAR_CLOUD_BUCKET
    - AWS_ACCESS_KEY_ID or use Cognito credentials
    """
    print("\n" + "="*60)
    print("Testing with Real S3 Service")
    print("="*60)
    
    # Check if S3 is configured
    bucket = os.getenv('AVATAR_CLOUD_BUCKET')
    if not bucket:
        print("\n⚠️  Skipping real S3 test - AVATAR_CLOUD_BUCKET not set")
        return
    
    try:
        from agent.cloud import create_standard_uploader
        
        uploader = create_standard_uploader()
        
        if not uploader:
            print("\n⚠️  Skipping real S3 test - S3 service not configured")
            return
        
        # Create a test file
        test_file = '/tmp/test_avatar.txt'
        with open(test_file, 'w') as f:
            f.write('This is a test avatar file for S3 upload.')
        
        print(f"\n✅ Created test file: {test_file}")
        
        # Upload
        print("\n--- Uploading to S3 ---")
        success, url, error = uploader.upload(
            local_path=test_file,
            owner='test_user@example.com',
            resource_type='avatar',
            resource_id='test_avatar_001',
            file_category='document',
            file_hash='test_hash_123',
            extra_metadata={
                'test': 'true',
                'purpose': 'integration_test'
            }
        )
        
        if success:
            print(f"\n✅ Upload successful!")
            print(f"   URL: {url}")
            
            # Download
            print("\n--- Downloading from S3 ---")
            download_path = '/tmp/test_avatar_downloaded.txt'
            success, error = uploader.download(
                owner='test_user@example.com',
                resource_type='avatar',
                file_category='document',
                file_hash='test_hash_123',
                file_ext='.txt',
                local_path=download_path
            )
            
            if success:
                print(f"✅ Download successful!")
                print(f"   Path: {download_path}")
                
                # Verify content
                with open(download_path, 'r') as f:
                    content = f.read()
                    print(f"   Content: {content}")
                
                # Cleanup
                os.remove(download_path)
            else:
                print(f"❌ Download failed: {error}")
            
            # Delete from S3
            print("\n--- Deleting from S3 ---")
            success, error = uploader.delete(
                owner='test_user@example.com',
                resource_type='avatar',
                file_category='document',
                file_hash='test_hash_123',
                file_ext='.txt'
            )
            
            if success:
                print(f"✅ Delete successful!")
            else:
                print(f"❌ Delete failed: {error}")
        else:
            print(f"❌ Upload failed: {error}")
        
        # Cleanup local test file
        os.remove(test_file)
        
        print("\n✅ Real S3 test completed!")
        
    except Exception as e:
        print(f"\n❌ Real S3 test failed: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("StandardS3Uploader Test Suite")
    print("="*60)
    
    try:
        # Test 1: Path Generator
        test_path_generator()
        
        # Test 2: Mock Uploader
        test_standard_uploader_mock()
        
        # Test 3: Real S3 (optional)
        test_real_s3_upload()
        
        print("\n" + "="*60)
        print("✅ All tests completed successfully!")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
