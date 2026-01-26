import uuid
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings


class MinIOClient:
    """AWS S3 客户端封装，提供基础存储能力。"""

    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.bucket_name = settings.S3_BUCKET_NAME

    def ensure_bucket(self) -> bool:
        """检查 Bucket 是否存在，不存在则创建。"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            print(f"✅ Bucket '{self.bucket_name}' 已存在")
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "404" or error_code == "NoSuchBucket":
                try:
                    # AWS S3: 需要根据 region 设置 LocationConstraint
                    # us-east-1 是特殊区域，不需要 LocationConstraint
                    # 其他区域（如 us-east-2）需要设置 LocationConstraint
                    if settings.AWS_REGION == "us-east-1":
                        # us-east-1 不需要 LocationConstraint
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        # 其他区域（如 us-east-2）需要 LocationConstraint
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={"LocationConstraint": settings.AWS_REGION},
                        )
                    print(f"✅ 已创建 Bucket '{self.bucket_name}'")
                    return True
                except ClientError as create_error:
                    print(f"❌ 创建 Bucket 失败: {create_error}")
                    return False
            print(f"❌ 检查 Bucket 时发生错误: {exc}")
            return False
        except BotoCoreError as exc:
            print(f"❌ Boto3 连接错误: {exc}")
            return False

    def upload_file(self, file_data: bytes, filename: str) -> Optional[str]:
        """上传文件到 S3。"""
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d")
            unique_id = str(uuid.uuid4())[:8]
            file_key = f"{timestamp}/{unique_id}_{filename}"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=file_data,
                ContentType="application/pdf",
            )
            print(f"✅ 文件已上传: {file_key}")
            return file_key
        except (ClientError, BotoCoreError) as exc:
            print(f"❌ 上传文件失败: {exc}")
            return None

    def get_presigned_url(self, file_key: str, expiration: int = 3600) -> Optional[str]:
        """生成预签名下载链接。"""
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": file_key},
                ExpiresIn=expiration,
            )
            return url
        except (ClientError, BotoCoreError) as exc:
            print(f"❌ 生成预签名 URL 失败: {exc}")
            return None


_minio_client: Optional["MinIOClient"] = None


def get_minio_client() -> "MinIOClient":
    """获取 MinIOClient 单例，并确保 bucket 存在。"""
    global _minio_client
    if _minio_client is None:
        _minio_client = MinIOClient()
        _minio_client.ensure_bucket()
    return _minio_client

