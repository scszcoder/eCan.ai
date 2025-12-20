# Avatar Management System

eCan.ai 的 Avatar 管理系统，支持系统默认头像、用户上传、AI 视频生成和云端同步。

## 📁 目录结构

```
agent/avatar/
├── __init__.py                 # 模块初始化
├── avatar_manager.py           # 核心管理器
├── cloud_storage.py           # 云端存储（待实现）
├── video_generator.py         # 视频生成（待实现）
└── README.md                  # 本文件
```

## 🚀 快速开始

### 基本使用

```python
from agent.avatar.avatar_manager import AvatarManager

# 创建管理器实例
avatar_manager = AvatarManager(
    user_id="user123",
    db_service=db_service  # 可选
)

# 获取系统默认头像
system_avatars = avatar_manager.get_system_avatars()

# 上传用户头像
with open("avatar.png", "rb") as f:
    file_data = f.read()
    
result = await avatar_manager.upload_avatar(
    file_data=file_data,
    filename="avatar.png"
)

# 获取已上传的头像
uploaded_avatars = avatar_manager.get_uploaded_avatars()

# 设置 Agent 头像
await avatar_manager.set_agent_avatar(
    agent_id="agent_123",
    avatar_type="uploaded",
    image_url="/avatars/uploaded/abc123_original.png",
    video_url="/avatars/generated/abc123_video.mp4"
)
```

## 📊 API 文档

### AvatarManager

#### 初始化

```python
AvatarManager(user_id: str, db_service=None)
```

**参数**:
- `user_id`: 用户标识符
- `db_service`: 数据库服务（可选）

#### 方法

##### get_system_avatars()

获取系统默认头像列表。

**返回**:
```python
[
    {
        "id": "A001",
        "name": "Professional Male",
        "tags": ["professional", "male", "formal"],
        "type": "system",
        "imageUrl": "/avatars/system/A001.png",
        "videoUrl": "/avatars/system/A001.mp4",
        "imageExists": True,
        "videoExists": True
    },
    ...
]
```

##### upload_avatar(file_data: bytes, filename: str)

上传用户头像。

**参数**:
- `file_data`: 图片文件字节数据
- `filename`: 原始文件名

**返回**:
```python
{
    "success": True,
    "imageUrl": "/avatars/uploaded/abc123_original.png",
    "thumbnailUrl": "/avatars/uploaded/abc123_thumb.png",
    "hash": "abc123",
    "metadata": {
        "format": "png",
        "size": 12345,
        "dimensions": [512, 512]
    }
}
```

##### get_uploaded_avatars()

获取用户已上传的头像列表。

**返回**:
```python
[
    {
        "type": "uploaded",
        "hash": "abc123",
        "imageUrl": "/avatars/uploaded/abc123_original.png",
        "thumbnailUrl": "/avatars/uploaded/abc123_thumb.png",
        "videoUrl": "/avatars/generated/abc123_video.mp4",
        "imageExists": True,
        "videoExists": True
    },
    ...
]
```

##### set_agent_avatar(agent_id, avatar_type, image_url, video_url=None, metadata=None)

设置 Agent 的头像。

**参数**:
- `agent_id`: Agent ID
- `avatar_type`: 头像类型（system/uploaded/generated）
- `image_url`: 图片 URL
- `video_url`: 视频 URL（可选）
- `metadata`: 元数据（可选）

**返回**:
```python
{
    "success": True,
    "agent_id": "agent_123",
    "avatar_type": "system",
    "avatar_image_url": "/avatars/system/A001.png",
    "avatar_video_url": "/avatars/system/A001.mp4"
}
```

##### generate_avatar_video(image_path, model="stable-diffusion-video", params=None)

生成头像动画视频（待实现）。

**参数**:
- `image_path`: 源图片路径
- `model`: AI 模型名称
- `params`: 生成参数

**返回**:
```python
{
    "success": False,
    "error": "Video generation feature coming soon"
}
```

## 🎨 支持的格式

### 图片格式
- PNG
- JPG/JPEG
- GIF
- WebP

### 文件大小限制
- 图片: 最大 10MB
- 视频: 最大 50MB

### 推荐尺寸
- 图片: 512x512 像素
- 缩略图: 256x256 像素

## 📁 文件存储

### 本地存储结构

```
{user_data_dir}/avatars/
├── system/                    # 系统默认头像
│   ├── A001.png              # 原图
│   ├── A001.mp4              # 动画视频
│   ├── A002.png
│   └── ...
├── uploaded/                  # 用户上传
│   ├── {hash}_original.png   # 原图
│   ├── {hash}_thumb.png      # 缩略图
│   └── ...
└── generated/                 # AI 生成
    ├── {hash}_video.mp4      # 生成的视频
    └── ...
```

### 云端存储（待实现）

- S3/OSS 存储
- 自动同步
- CDN 加速
- 预签名 URL

## 🔒 安全特性

### 文件验证
- 格式验证: 只允许指定的图片格式
- 大小验证: 限制文件大小
- 内容验证: 使用 PIL 验证图片完整性

### 访问控制
- 用户隔离: 每个用户只能访问自己的头像
- 路径安全: 防止路径遍历攻击

### 文件完整性
- MD5 Hash: 每个文件计算 MD5 hash
- 去重: 相同文件不重复存储

## 🎯 使用示例

### 示例 1: 完整的头像上传流程

```python
from agent.avatar.avatar_manager import AvatarManager

async def upload_user_avatar(user_id: str, file_path: str):
    """上传用户头像的完整流程"""
    
    # 创建管理器
    manager = AvatarManager(user_id=user_id)
    
    # 读取文件
    with open(file_path, 'rb') as f:
        file_data = f.read()
    
    # 上传
    result = await manager.upload_avatar(
        file_data=file_data,
        filename=os.path.basename(file_path)
    )
    
    if result["success"]:
        print(f"✅ Upload successful!")
        print(f"Image URL: {result['imageUrl']}")
        print(f"Thumbnail URL: {result['thumbnailUrl']}")
        print(f"Hash: {result['hash']}")
        return result
    else:
        print(f"❌ Upload failed: {result['error']}")
        return None
```

### 示例 2: 为 Agent 设置头像

```python
async def set_avatar_for_agent(user_id: str, agent_id: str, avatar_type: str):
    """为 Agent 设置头像"""
    
    manager = AvatarManager(user_id=user_id)
    
    if avatar_type == "system":
        # 使用系统默认头像
        image_url = "/avatars/system/A001.png"
        video_url = "/avatars/system/A001.mp4"
    else:
        # 使用用户上传的头像
        uploaded = manager.get_uploaded_avatars()
        if uploaded:
            image_url = uploaded[0]["imageUrl"]
            video_url = uploaded[0].get("videoUrl")
        else:
            print("No uploaded avatars found")
            return
    
    # 设置头像
    result = await manager.set_agent_avatar(
        agent_id=agent_id,
        avatar_type=avatar_type,
        image_url=image_url,
        video_url=video_url
    )
    
    print(f"✅ Avatar set for agent {agent_id}")
    return result
```

### 示例 3: 获取所有可用头像

```python
def get_all_available_avatars(user_id: str):
    """获取所有可用的头像"""
    
    manager = AvatarManager(user_id=user_id)
    
    # 系统头像
    system = manager.get_system_avatars()
    print(f"System avatars: {len(system)}")
    
    # 用户上传的头像
    uploaded = manager.get_uploaded_avatars()
    print(f"Uploaded avatars: {len(uploaded)}")
    
    return {
        "system": system,
        "uploaded": uploaded
    }
```

## 🔧 配置

### 环境变量

```bash
# 用户数据目录
ECAN_USER_DATA_DIR=/path/to/user/data

# 云端存储（可选）
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_S3_BUCKET=ecan-avatars
AWS_S3_REGION=us-west-2
```

### 配置文件

创建 `/config/avatar_config.yml`:

```yaml
avatar:
  local_storage:
    base_dir: "{user_data_dir}/avatars"
    max_file_size: 10485760  # 10MB
    supported_formats: ["png", "jpg", "jpeg", "gif", "webp"]
    thumbnail_size: [256, 256]
  
  cloud_storage:
    provider: "s3"
    bucket: "ecan-avatars"
    region: "us-west-2"
    cdn_domain: "https://cdn.ecan.ai"
  
  video_generation:
    default_model: "stable-diffusion-video"
    default_duration: 3.0
    max_concurrent_jobs: 3
```

## 🧪 测试

```python
# 运行测试
pytest agent/avatar/tests/

# 测试覆盖率
pytest --cov=agent.avatar agent/avatar/tests/
```

## 📚 相关文档

- [架构设计文档](../../docs/avatar_management_architecture.md)
- [实施计划](../../docs/avatar_implementation_plan.md)
- [系统总结](../../docs/avatar_system_summary.md)

## 🤝 贡献

欢迎贡献代码！请遵循以下步骤：

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 📝 许可证

Copyright © 2025 eCan.ai
