#!/usr/bin/env python3
"""
S3 上传测试脚本
模拟 GitHub Actions 的上传流程
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("错误: 未安装 boto3")
    print("请运行: pip install boto3")
    sys.exit(1)


class S3UploadTester:
    def __init__(self, bucket, region='us-east-1', base_path='releases'):
        self.bucket = bucket
        self.region = region
        self.base_path = base_path
        self.s3_client = None
        
    def initialize(self):
        """初始化 S3 客户端"""
        try:
            self.s3_client = boto3.client('s3', region_name=self.region)
            # 测试凭证
            self.s3_client.head_bucket(Bucket=self.bucket)
            print("✓ AWS 凭证有效")
            print(f"✓ 存储桶 {self.bucket} 可访问")
            return True
        except NoCredentialsError:
            print("✗ 错误: AWS 凭证未配置")
            print("请运行: aws configure")
            return False
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                print(f"✗ 错误: 存储桶 {self.bucket} 不存在")
            elif error_code == '403':
                print(f"✗ 错误: 无权访问存储桶 {self.bucket}")
            else:
                print(f"✗ 错误: {e}")
            return False
    
    def create_test_files(self, version):
        """创建测试文件"""
        print("\n创建测试文件...")
        test_dir = Path(f"test_upload_{int(datetime.now().timestamp())}")
        test_dir.mkdir(exist_ok=True)
        
        # 创建目录结构
        (test_dir / "windows").mkdir(exist_ok=True)
        (test_dir / "macos").mkdir(exist_ok=True)
        (test_dir / "checksums").mkdir(exist_ok=True)
        
        # 创建测试文件
        files = {
            f"windows/eCan-{version}-windows-amd64-Setup.exe": b"Test Windows Setup Installer",
            f"windows/eCan-{version}-windows-amd64.exe": b"Test Windows Portable",
            f"macos/eCan-{version}-macos-amd64.pkg": b"Test macOS Intel Installer",
            f"macos/eCan-{version}-macos-aarch64.pkg": b"Test macOS ARM Installer",
        }
        
        checksums = []
        for file_path, content in files.items():
            full_path = test_dir / file_path
            full_path.write_bytes(content)
            
            # 计算 SHA256
            sha256 = hashlib.sha256(content).hexdigest()
            checksums.append(f"{sha256}  ./{file_path}")
        
        # 写入校验和文件
        (test_dir / "checksums/SHA256SUMS").write_text("\n".join(checksums))
        
        print(f"✓ 测试文件已创建: {test_dir}")
        return test_dir, files
    
    def upload_files(self, test_dir, version):
        """上传文件到 S3"""
        print(f"\n上传文件到 S3...")
        s3_version_path = f"{self.base_path}/v{version}"
        uploaded_files = []
        
        for file_path in test_dir.rglob("*"):
            if file_path.is_file():
                # 计算相对路径
                relative_path = file_path.relative_to(test_dir)
                s3_key = f"{s3_version_path}/{relative_path}"
                
                try:
                    # 上传文件（不使用 ACL，依赖存储桶策略）
                    self.s3_client.upload_file(
                        str(file_path),
                        self.bucket,
                        s3_key,
                        ExtraArgs={
                            'CacheControl': 'max-age=31536000',
                            'Metadata': {'version': version}
                        }
                    )
                    
                    url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"
                    print(f"  ✓ {relative_path}")
                    uploaded_files.append({
                        'name': file_path.name,
                        'path': str(relative_path),
                        'url': url,
                        'size': file_path.stat().st_size
                    })
                except ClientError as e:
                    print(f"  ✗ {relative_path}: {e}")
        
        return s3_version_path, uploaded_files
    
    def create_metadata(self, version, s3_version_path, uploaded_files):
        """创建版本元数据"""
        print("\n创建版本元数据...")
        
        metadata = {
            'version': version,
            'release_date': datetime.utcnow().isoformat() + 'Z',
            'tag': f'v{version}',
            'test': True,
            's3_base_url': f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_version_path}",
            'files': {
                'windows': [],
                'macos': []
            }
        }
        
        for file_info in uploaded_files:
            if 'windows' in file_info['path']:
                metadata['files']['windows'].append({
                    'name': file_info['name'],
                    'url': file_info['url'],
                    'size': file_info['size']
                })
            elif 'macos' in file_info['path']:
                metadata['files']['macos'].append({
                    'name': file_info['name'],
                    'url': file_info['url'],
                    'size': file_info['size']
                })
        
        # 上传元数据（不使用 ACL）
        metadata_key = f"{s3_version_path}/version-metadata.json"
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=metadata_key,
                Body=json.dumps(metadata, indent=2),
                ContentType='application/json'
            )
            print(f"✓ 元数据已上传")
            return metadata
        except ClientError as e:
            print(f"✗ 元数据上传失败: {e}")
            return None
    
    def verify_upload(self, s3_version_path):
        """验证上传"""
        print("\n验证上传的文件...")
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=s3_version_path
            )
            
            if 'Contents' in response:
                print(f"\nS3 文件列表 (共 {len(response['Contents'])} 个文件):")
                for obj in response['Contents']:
                    size_kb = obj['Size'] / 1024
                    print(f"  {obj['Key']} ({size_kb:.2f} KB)")
                return True
            else:
                print("✗ 未找到上传的文件")
                return False
        except ClientError as e:
            print(f"✗ 验证失败: {e}")
            return False
    
    def test_download(self, s3_version_path):
        """测试下载"""
        print("\n测试文件访问...")
        test_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_version_path}/checksums/SHA256SUMS"
        
        import urllib.request
        try:
            with urllib.request.urlopen(test_url) as response:
                content = response.read().decode('utf-8')
                print("✓ 文件可以公开访问")
                print("\n校验和内容:")
                print(content)
                return True
        except Exception as e:
            print(f"✗ 文件无法访问: {e}")
            print("请检查存储桶策略是否允许公共读取")
            return False
    
    def cleanup(self, test_dir, s3_version_path):
        """清理测试文件"""
        print("\n清理测试文件...")
        
        # 清理本地文件
        import shutil
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print("✓ 本地文件已清理")
        
        # 询问是否清理 S3 文件
        response = input("\n要删除 S3 上的测试文件吗? (y/N): ")
        if response.lower() in ['y', 'yes']:
            try:
                # 列出所有对象
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix=s3_version_path
                )
                
                if 'Contents' in response:
                    # 删除所有对象
                    objects = [{'Key': obj['Key']} for obj in response['Contents']]
                    self.s3_client.delete_objects(
                        Bucket=self.bucket,
                        Delete={'Objects': objects}
                    )
                    print("✓ S3 测试文件已删除")
                else:
                    print("没有文件需要删除")
            except ClientError as e:
                print(f"✗ 删除失败: {e}")
        else:
            print(f"保留 S3 测试文件")
            print(f"手动删除命令: aws s3 rm s3://{self.bucket}/{s3_version_path}/ --recursive")


def main():
    """主函数"""
    print("=== S3 上传测试脚本 ===\n")
    
    # 从环境变量获取配置
    bucket = os.environ.get('S3_BUCKET', 'ecan-releases')
    region = os.environ.get('AWS_REGION', 'us-east-1')
    base_path = os.environ.get('S3_BASE_PATH', 'releases')
    version = os.environ.get('VERSION', '0.0.1-test')
    
    print(f"配置信息:")
    print(f"  版本: {version}")
    print(f"  S3 存储桶: {bucket}")
    print(f"  S3 路径: {base_path}")
    print(f"  AWS 区域: {region}\n")
    
    # 创建测试器
    tester = S3UploadTester(bucket, region, base_path)
    
    # 初始化
    if not tester.initialize():
        sys.exit(1)
    
    # 创建测试文件
    test_dir, files = tester.create_test_files(version)
    
    # 上传文件
    s3_version_path, uploaded_files = tester.upload_files(test_dir, version)
    
    # 创建元数据
    metadata = tester.create_metadata(version, s3_version_path, uploaded_files)
    
    # 验证上传
    tester.verify_upload(s3_version_path)
    
    # 测试下载
    tester.test_download(s3_version_path)
    
    # 显示 URL
    if metadata:
        print("\n=== 下载 URL ===")
        print(f"基础 URL: {metadata['s3_base_url']}")
        print("\nWindows:")
        for file in metadata['files']['windows']:
            print(f"  {file['name']}: {file['url']}")
        print("\nmacOS:")
        for file in metadata['files']['macos']:
            print(f"  {file['name']}: {file['url']}")
        print(f"\n元数据: {metadata['s3_base_url']}/version-metadata.json")
    
    # 清理
    tester.cleanup(test_dir, s3_version_path)
    
    print("\n✓ 测试完成!")


if __name__ == '__main__':
    main()
