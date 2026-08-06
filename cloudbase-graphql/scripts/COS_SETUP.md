# ============================================================
# eCan.ai CN - 云存储 COS Bucket 创建指南
# ============================================================
#
# 由于腾讯云 CLI 配置复杂，建议手动创建 COS Bucket
#
# 步骤：
# 1. 打开腾讯云 COS 控制台
#    https://console.cloud.tencent.com/cos5/bucket
#
# 2. 创建存储桶
#    - 地域: ap-shanghai（与 TCB 环境一致）
#    - 名称: ecan-cn-files-1250000000
#      （注意：1250000000 是你的腾讯云 APPID，需要替换）
#    - 访问权限: 私有读写
#    - 开启静态网站（可选，用于托管前端）
#
# 3. 获取 APPID
#    - 腾讯云控制台 → 账号信息 → APPID
#    - 或 COS 存储桶名称末尾的数字
#
# 4. 填写配置
#    - COS_BUCKET: ecan-cn-files-{你的APPID}
#    - COS_REGION: ap-shanghai
#
# ============================================================

# 检查当前 APPID（通过腾讯云账号）
echo "请手动创建 COS Bucket"
echo ""
echo "访问: https://console.cloud.tencent.com/cos5/bucket"
echo "地域: ap-shanghai"
echo ""
echo "Bucket 命名格式: ecan-cn-files-{APPID}"
echo "获取 APPID: https://console.cloud.tencent.com/developer"
