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
#    - 名称: ecan-skills-1250000000
#      （注意：1250000000 是你的腾讯云 APPID，需要替换）
#      （命名规则：与 AWS S3 端的短名 "ecan-skills" 对齐，加 -APPID 后缀）
#      （OTA 桶使用 ecan-releases-APPID，单独建一个桶；不要和 runtime 桶混用）
#    - 访问权限: 私有读写
#    - 开启静态网站（可选，用于托管前端）
#
# 3. 获取 APPID
#    - 腾讯云控制台 → 账号信息 → APPID
#    - 或 COS 存储桶名称末尾的数字
#
# 4. 填写配置
#    - COS_BUCKET: ecan-skills-{你的APPID}    (runtime 桶)
#    - COS_OTA_BUCKET: ecan-releases-{你的APPID}  (OTA 桶，单独建)
#    - COS_REGION: ap-shanghai
#
# ============================================================

# 检查当前 APPID（通过腾讯云账号）
echo "请手动创建 COS Bucket"
echo ""
echo "访问: https://console.cloud.tencent.com/cos5/bucket"
echo "地域: ap-shanghai"
echo ""
echo "Bucket 命名格式:"
echo "  - Runtime: ecan-skills-{APPID}"
echo "  - OTA:     ecan-releases-{APPID}  (独立于 runtime)"
echo "获取 APPID: https://console.cloud.tencent.com/developer"

# ============================================================
# 从旧桶迁移数据（一次性任务）
# ============================================================
#
# 如果之前已经在用 7363-sccb0-d0gc5398xf028be6a-1251680599（即 env-id 命名风格的桶），
# 需要把里面的对象迁移到 ecan-skills-{APPID}，否则新代码会指向空桶。
#
# 推荐用 coscli 做一次性复制：
#
#   1. 安装 coscli:
#      https://cloud.tencent.com/document/product/436/63143
#
#   2. 配置 credentials ( ~/.cos.conf ):
#      [common]
#      secret_id = AKIDxxxxxxxx
#      secret_key = xxxxxxxx
#      region = ap-shanghai
#
#   3. 执行 sync（推荐，保留前缀，不重复下载未变化对象）:
#      coscli cp cos://7363-sccb0-d0gc5398xf028be6a-1251680599/ \
#              cos://ecan-skills-1251680599/ \
#              --recursive --copy-props=Content-Type,Cache-Control
#
#   4. 校验:
#      coscli ls cos://ecan-skills-1251680599/ --recursive | wc -l
#      对比两侧 object 数
#
#   5. OTA 桶同步同理（如果旧桶和 OTA 桶是同一个，需要先把 OTA 文件分离）:
#      coscli cp cos://7363-sccb0-d0gc5398xf028be6a-1251680599/dev/ \
#              cos://ecan-releases-1251680599/dev/ --recursive
#      coscli cp cos://7363-sccb0-d0gc5398xf028be6a-1251680599/test/ \
#              cos://ecan-releases-1251680599/test/ --recursive
#      ... staging / simulation / production 同理
#
#   6. 验证完所有读写后再删除旧桶（保守起见，留 7 天再删）。
