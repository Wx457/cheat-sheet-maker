"""
MinIO/S3 存储服务
使用 boto3 与 MinIO (S3 兼容) 交互
"""
import boto3
import time
from botocore.exceptions import ClientError, BotoCoreError
from typing import Optional
from datetime import datetime
import uuid

from app.core.config import settings


class StorageService:
    """MinIO/S3 存储服务类"""
    
    def __init__(self):
        """初始化 S3 客户端"""
        # 判断是否为本地 MinIO（HTTP）
        is_local_minio = settings.S3_ENDPOINT_URL.startswith('http://')
        
        # 配置 S3 客户端（兼容 MinIO）
        client_kwargs = {
            'endpoint_url': settings.S3_ENDPOINT_URL,
            'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
            'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
            'region_name': 'us-east-1',  # MinIO 不关心 region，但 boto3 需要
        }
        
        # 如果是本地 MinIO (HTTP)，添加额外配置
        if is_local_minio:
            client_kwargs['use_ssl'] = False
            client_kwargs['verify'] = False
        
        self.s3_client = boto3.client('s3', **client_kwargs)
        self.bucket_name = settings.S3_BUCKET_NAME
    
    def ensure_bucket(self) -> bool:
        """
        检查 Bucket 是否存在，不存在则创建
        
        Returns:
            True 如果 Bucket 存在或创建成功，False 如果失败
        """
        try:
            # 尝试检查 Bucket 是否存在
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            print(f"✅ Bucket '{self.bucket_name}' 已存在")
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            
            if error_code == '404':
                # Bucket 不存在，创建它
                try:
                    if settings.S3_ENDPOINT_URL.startswith('http://localhost') or \
                       settings.S3_ENDPOINT_URL.startswith('http://127.0.0.1'):
                        # MinIO 本地部署，使用 location_constraint=None
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        # AWS S3 或其他兼容服务
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': 'us-east-1'}
                        )
                    print(f"✅ 已创建 Bucket '{self.bucket_name}'")
                    return True
                except ClientError as create_error:
                    print(f"❌ 创建 Bucket 失败: {create_error}")
                    return False
            else:
                # 其他错误（如权限问题）
                print(f"❌ 检查 Bucket 时发生错误: {e}")
                return False
        except BotoCoreError as e:
            print(f"❌ Boto3 连接错误: {e}")
            return False
    
    def upload_file(self, file_data: bytes, filename: str) -> Optional[str]:
        """
        上传文件到 MinIO/S3
        
        Args:
            file_data: 文件的二进制数据
            filename: 文件名（将作为 object key）
            
        Returns:
            file_key: 文件的 key（用于后续访问），如果失败则返回 None
        """
        # ========== [性能监控 - 可删除] ==========
        upload_start_time = time.time()
        # ========== [性能监控 - 可删除] ==========
        
        try:
            # 生成唯一的文件 key（包含时间戳和 UUID，避免冲突）
            timestamp = datetime.utcnow().strftime("%Y%m%d")
            unique_id = str(uuid.uuid4())[:8]
            file_key = f"{timestamp}/{unique_id}_{filename}"
            
            # 上传文件
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=file_data,
                ContentType='application/pdf'
            )
            
            # ========== [性能监控 - 可删除] ==========
            upload_elapsed = time.time() - upload_start_time
            print(f"⏱️ [性能监控] upload_file - 上传耗时: {upload_elapsed:.2f} 秒，文件大小: {len(file_data)} bytes，file_key: {file_key}")
            # ========== [性能监控 - 可删除] ==========
            
            print(f"✅ 文件已上传: {file_key}")
            return file_key
            
        except ClientError as e:
            # ========== [性能监控 - 可删除] ==========
            upload_elapsed = time.time() - upload_start_time
            print(f"⏱️ [性能监控] upload_file - 上传失败，耗时: {upload_elapsed:.2f} 秒")
            # ========== [性能监控 - 可删除] ==========
            print(f"❌ 上传文件失败: {e}")
            return None
        except BotoCoreError as e:
            # ========== [性能监控 - 可删除] ==========
            upload_elapsed = time.time() - upload_start_time
            print(f"⏱️ [性能监控] upload_file - 上传失败，耗时: {upload_elapsed:.2f} 秒")
            # ========== [性能监控 - 可删除] ==========
            print(f"❌ Boto3 错误: {e}")
            return None
    
    def get_presigned_url(self, file_key: str, expiration: int = 3600) -> Optional[str]:
        """
        生成预签名下载链接
        
        Args:
            file_key: 文件的 key
            expiration: 链接有效期（秒），默认 1 小时
            
        Returns:
            预签名 URL，如果失败则返回 None
        """
        # ========== [性能监控 - 可删除] ==========
        url_start_time = time.time()
        # ========== [性能监控 - 可删除] ==========
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': file_key
                },
                ExpiresIn=expiration
            )
            
            # ========== [性能监控 - 可删除] ==========
            url_elapsed = time.time() - url_start_time
            print(f"⏱️ [性能监控] get_presigned_url - 生成预签名 URL 耗时: {url_elapsed:.2f} 秒")
            # ========== [性能监控 - 可删除] ==========
            
            return url
        except ClientError as e:
            # ========== [性能监控 - 可删除] ==========
            url_elapsed = time.time() - url_start_time
            print(f"⏱️ [性能监控] get_presigned_url - 生成失败，耗时: {url_elapsed:.2f} 秒")
            # ========== [性能监控 - 可删除] ==========
            print(f"❌ 生成预签名 URL 失败: {e}")
            return None
        except BotoCoreError as e:
            # ========== [性能监控 - 可删除] ==========
            url_elapsed = time.time() - url_start_time
            print(f"⏱️ [性能监控] get_presigned_url - 生成失败，耗时: {url_elapsed:.2f} 秒")
            # ========== [性能监控 - 可删除] ==========
            print(f"❌ Boto3 错误: {e}")
            return None


# 创建全局存储服务实例
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """获取存储服务实例（单例模式）"""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
        # 确保 Bucket 存在
        _storage_service.ensure_bucket()
    return _storage_service

