# Avatar 系统使用指南

## 🎯 功能说明

Avatar 系统支持两种上传方式：
1. **上传图片**：显示静态头像
2. **上传视频**：显示动态头像

### 配置（在 `agent/avatar/video_generator.py`）

```python
# 是否启用自动视频生成（上传图片时自动生成视频）
# False = 关闭（推荐，性能更好）
# True  = 开启（上传图片后使用 ffmpeg 生成简单动画视频）
ENABLE_AVATAR_VIDEO_GENERATION = False
```

---

## 📤 上传方式

### 方式1：上传图片

**用户操作**：选择图片文件（png, jpg, gif, webp）

**后端处理**：
- 保存原图
- 生成缩略图
- 返回 imageUrl, thumbnailUrl

**前端显示**：
```tsx
<img src={avatar.imageUrl} alt="Avatar" />
```

### 方式2：上传视频 ✨

**用户操作**：选择视频文件（webm, mp4, mov, avi）

**后端处理**：
- 保存视频
- **可选**：如果 ffmpeg 可用，提取首帧作为封面图
- 如果 ffmpeg 不可用，imageUrl 为 null

**前端显示**：
```tsx
// 智能显示逻辑
if (avatar.videoUrl) {
  // 有视频，显示视频
  <video 
    src={avatar.videoUrl} 
    poster={avatar.imageUrl || undefined}  // imageUrl 可能为 null
    loop 
    muted 
    autoPlay 
  />
} else {
  // 无视频，显示图片
  <img src={avatar.imageUrl} />
}
```

---

## 🎨 前端实现示例

### React 组件

```tsx
interface AvatarDisplayProps {
  imageUrl?: string | null;
  videoUrl?: string | null;
  thumbnailUrl?: string | null;
}

export const AvatarDisplay: React.FC<AvatarDisplayProps> = ({
  imageUrl,
  videoUrl,
  thumbnailUrl
}) => {
  const [videoError, setVideoError] = useState(false);

  // 优先显示视频
  if (videoUrl && !videoError) {
    return (
      <video
        src={videoUrl}
        poster={imageUrl || thumbnailUrl || undefined}  // 使用图片作为封面（可能为空）
        loop
        muted
        autoPlay
        playsInline
        onError={() => setVideoError(true)}
        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
      />
    );
  }

  // 回退到图片（或视频加载失败）
  if (imageUrl || thumbnailUrl) {
    return (
      <img 
        src={imageUrl || thumbnailUrl} 
        alt="Avatar"
        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
      />
    );
  }

  // 都没有，显示占位符
  return <div className="avatar-placeholder">No Avatar</div>;
};
```

### 上传功能

```tsx
const handleFileUpload = async (file: File) => {
  const isImage = file.type.startsWith('image/');
  const isVideo = file.type.startsWith('video/');

  if (!isImage && !isVideo) {
    alert('请上传图片或视频');
    return;
  }

  // 转为 base64
  const reader = new FileReader();
  reader.onload = async () => {
    const base64 = reader.result?.toString().split(',')[1];
    
    const result = await window.ipc.call('avatar.upload_avatar', {
      username: currentUser,
      fileData: base64,
      filename: file.name,
      fileType: isVideo ? 'video' : 'image'  // 自动检测
    });

    if (result.success) {
      // result.imageUrl 可能为 null（视频上传且无 ffmpeg）
      // result.videoUrl 有值时优先显示视频
      console.log('Upload successful:', result);
    }
  };
  reader.readAsDataURL(file);
};
```

---

## 📋 API 响应格式

### 上传图片

```json
{
  "success": true,
  "id": "avatar_abc123",
  "imageUrl": "http://.../abc123_original.png",
  "thumbnailUrl": "http://.../abc123_thumb.png",
  "videoUrl": null,
  "hash": "abc123"
}
```

### 上传视频（有 ffmpeg）

```json
{
  "success": true,
  "id": "avatar_xyz789",
  "imageUrl": "http://.../xyz789_original.png",     // 从视频提取的首帧
  "thumbnailUrl": "http://.../xyz789_thumb.png",
  "videoUrl": "http://.../xyz789_video.webm",
  "hash": "xyz789",
  "metadata": {
    "source": "video_upload",
    "has_extracted_frame": true
  }
}
```

### 上传视频（无 ffmpeg）

```json
{
  "success": true,
  "id": "avatar_xyz789",
  "imageUrl": null,                                 // 无法提取首帧
  "thumbnailUrl": null,
  "videoUrl": "http://.../xyz789_video.webm",
  "hash": "xyz789",
  "metadata": {
    "source": "video_upload",
    "has_extracted_frame": false                    // 标记
  }
}
```

---

## 🔧 依赖

### 必需
- Python 3.7+
- PIL/Pillow（图片处理）

### 可选
- **ffmpeg**（提取视频首帧）
  - 不安装：视频上传时 imageUrl 为 null，前端直接显示视频
  - 安装后：可以提取首帧作为封面图

```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt-get install ffmpeg
```

---

## ✨ 核心优势

1. **性能优化**：默认关闭视频生成，上传速度快（1秒）
2. **灵活配置**：支持图片或视频上传
3. **优雅降级**：
   - ffmpeg 不可用时仍可上传视频
   - 视频加载失败时回退到图片
   - imageUrl 为 null 时直接显示视频
4. **简单实用**：无额外依赖，开箱即用

---

## 📊 性能对比

| 操作 | 时间 | 资源 |
|------|------|------|
| 上传图片 | ~1秒 | 低 |
| 上传视频（有ffmpeg） | ~2-3秒 | 中 |
| 上传视频（无ffmpeg） | ~1-2秒 | 低 |
| 自动视频生成 | ~6-11秒 | 高 |

**推荐配置**：关闭自动视频生成，让用户选择上传图片或视频

---

## ☁️ 云存储（S3）

### 自动上传到 S3

上传的图片和视频会**自动**在后台上传到 AWS S3，并更新数据库中的 S3 URL。

#### 工作流程

```
用户上传文件
    ↓
保存到本地文件系统
    ↓
保存到本地数据库 (SQLite)
    - image_path: /local/path/abc123_original.png
    - video_path: /local/path/abc123_video.webm
    ↓
后台线程上传到 S3 (非阻塞)
    - 路径: avatars/{cognito-identity-id}/images/{hash}.png
    - 路径: avatars/{cognito-identity-id}/videos/{hash}.webm
    ↓
更新数据库 S3 URL
    - cloud_image_url: https://ecan-avatars.s3.amazonaws.com/...
    - cloud_video_url: https://ecan-avatars.s3.amazonaws.com/...
    ↓
Agent 同步时使用 S3 URL
```

#### S3 存储路径

```
ecan-avatars/
  └── avatars/
      └── {cognito-identity-id}/
          ├── images/
          │   └── e33ae533de084198dead3772eaa0fdbd.png
          └── videos/
              └── e33ae533de084198dead3772eaa0fdbd.webm
```

#### 数据库字段

**avatar_resources 表**：
```python
{
    "id": "avatar_e33ae...",
    "owner": "user@example.com",
    
    # 本地路径
    "image_path": "/local/path/e33ae..._original.png",
    "video_path": "/local/path/e33ae..._video.webm",
    
    # S3 URL (自动上传后填充)
    "cloud_image_url": "https://ecan-avatars.s3.amazonaws.com/avatars/.../images/e33ae.png",
    "cloud_video_url": "https://ecan-avatars.s3.amazonaws.com/avatars/.../videos/e33ae.webm",
    
    # 其他字段
    "image_hash": "e33ae533de084198dead3772eaa0fdbd",
    "avatar_metadata": {...}
}
```

#### S3 上传配置

**代码位置**：`agent/avatar/avatar_manager.py`

```python
# 初始化 S3 uploader
self.s3_uploader = StandardS3Uploader(s3_service)

# 后台异步上传（完全非阻塞）
self._upload_to_s3_background(
    avatar_id=avatar_id,
    image_path=image_path,
    video_path=video_path,
    file_hash=file_hash
)
# 立即返回，不等待上传完成
```

**异步实现** ✨

所有 S3 操作都使用 `asyncio` 实现，完全异步、非阻塞：

```python
# S3StorageService 提供异步方法
async def upload_file_async(...)  # 异步上传
async def download_file_async(...) # 异步下载  
async def delete_file_async(...)   # 异步删除

# StandardS3Uploader 封装
async def upload_async(...)  # 标准化异步上传

# AvatarManager 后台任务
async def _upload_to_s3_async(...)  # 后台上传任务
    await uploader.upload_async(image)  # 异步上传图片
    await uploader.upload_async(video)  # 异步上传视频
    db_service.update(...)              # 更新数据库
```

**性能优势**：
- 用户上传立即完成（< 100ms）
- S3 上传在后台执行
- 不阻塞任何流程
- 协程轻量级，资源占用小

**按需创建** ✨

S3 uploader 采用按需创建（On-Demand Creation）策略：

```python
# 界面打开时：不初始化 S3（< 1ms，立即响应）
def __init__(self, user_id: str, db_service=None):
    # 不创建 S3 uploader
    pass

# 每次上传时：创建新的 uploader（保证凭证新鲜）
async def _upload_to_s3_async(...):
    # 创建新的 S3 uploader
    s3_uploader = self._create_s3_uploader()
    
    if not s3_uploader:
        logger.warning("S3 not available, skip")
        return
    
    # 使用新创建的 uploader 上传
    await s3_uploader.upload_async(...)
```

**优化效果**：
| 操作 | 之前 | 现在 |
|------|------|------|
| 打开界面 | 阻塞 800ms ❌ | 立即打开 ✅ |
| 每次上传 | 立即上传 | 创建 uploader（800ms）|

**优势**：
- ✅ 简单：无缓存逻辑，代码更清晰
- ✅ 可靠：每次获取新凭证，无过期问题
- ✅ 隔离：每次上传独立，无状态共享

#### 权限要求

- 使用 **Cognito Identity Pool** 获取临时 AWS 凭证
- IAM 策略允许用户访问自己的 S3 路径：
  ```
  avatars/${cognito-identity.amazonaws.com:sub}/*
  ```
- 详见：`docs/iam-policy-s3-access.json`

---

## 🔀 架构分离

### Avatar S3 上传 ≠ Agent AppSync 同步

这是两个**独立**的流程：

#### 1️⃣ Avatar S3 文件上传
- **触发时机**：用户上传图片/视频
- **操作**：文件 → S3，更新 `cloud_image_url`
- **代码**：`avatar_manager.py` + `StandardS3Uploader`

#### 2️⃣ Agent AppSync 数据同步
- **触发时机**：用户创建/修改 Agent
- **操作**：从数据库读取 `cloud_image_url` → 同步到 AppSync
- **代码**：`agent_cloud_sync.py` + AppSync Mutation

**关键**：Avatar 的 S3 URL 保存在本地数据库中，Agent 同步时直接使用这些 URL。

---

## 🎊 总结

✅ **简单**：配置简单，使用方便
✅ **快速**：上传速度快，用户体验好（S3 上传在后台进行）
✅ **灵活**：支持图片和视频，可选提取首帧
✅ **健壮**：无 ffmpeg 也能正常工作
✅ **云同步**：自动上传到 S3，数据安全可靠

**开始使用吧！** 🚀

