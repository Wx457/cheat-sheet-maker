import time
import uuid
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings


class MinIOClient:
    """MinIO/S3 客户端封装，提供基础存储能力。"""

    def __init__(self):
        is_local_minio = settings.S3_ENDPOINT_URL.startswith("http://")
        client_kwargs = {
            "endpoint_url": settings.S3_ENDPOINT_URL,
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
            "region_name": "us-east-1",
        }
        if is_local_minio:
            client_kwargs["use_ssl"] = False
            client_kwargs["verify"] = False

        self.s3_client = boto3.client("s3", **client_kwargs)
        self.bucket_name = settings.S3_BUCKET_NAME

    def ensure_bucket(self) -> bool:
        """检查 Bucket 是否存在，不存在则创建。"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            print(f"✅ Bucket '{self.bucket_name}' 已存在")
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                try:
                    if settings.S3_ENDPOINT_URL.startswith("http://localhost") or settings.S3_ENDPOINT_URL.startswith(
                        "http://127.0.0.1"
                    ):
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={"LocationConstraint": "us-east-1"},
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
        """上传文件到 MinIO/S3。"""
        upload_start_time = time.time()
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
            upload_elapsed = time.time() - upload_start_time
            print(
                f"⏱️ [性能监控] upload_file - 上传耗时: {upload_elapsed:.2f} 秒，文件大小: {len(file_data)} bytes，file_key: {file_key}"
            )
            print(f"✅ 文件已上传: {file_key}")
            return file_key
        except (ClientError, BotoCoreError) as exc:
            upload_elapsed = time.time() - upload_start_time
            print(f"⏱️ [性能监控] upload_file - 上传失败，耗时: {upload_elapsed:.2f} 秒")
            print(f"❌ 上传文件失败: {exc}")
            return None

    def get_presigned_url(self, file_key: str, expiration: int = 3600) -> Optional[str]:
        """生成预签名下载链接。"""
        url_start_time = time.time()
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": file_key},
                ExpiresIn=expiration,
            )
            url_elapsed = time.time() - url_start_time
            print(f"⏱️ [性能监控] get_presigned_url - 生成预签名 URL 耗时: {url_elapsed:.2f} 秒")
            return url
        except (ClientError, BotoCoreError) as exc:
            url_elapsed = time.time() - url_start_time
            print(f"⏱️ [性能监控] get_presigned_url - 生成失败，耗时: {url_elapsed:.2f} 秒")
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

