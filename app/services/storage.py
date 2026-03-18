# app/services/storage.py
#
# S3-ready storage abstraction.
# Swap LocalStorage for S3Storage by changing one line in get_storage().
#
# S3Storage stub is included — fill in boto3 calls when ready.

import os
import uuid
import aiofiles
from pathlib import Path
from abc import ABC, abstractmethod

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Config
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ── Abstract interface ────────────────────────────────────────────────────────

class StorageBackend(ABC):

    @abstractmethod
    async def save(self, data: bytes, filename: str) -> str:
        """Save file data. Returns the storage path."""
        ...

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        """Delete file by storage path."""
        ...

    @abstractmethod
    def public_url(self, storage_path: str) -> str:
        """Return a URL to access the file."""
        ...


# ── Local disk storage ────────────────────────────────────────────────────────

class LocalStorage(StorageBackend):

    def __init__(self, base_dir: Path = UPLOAD_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(exist_ok=True)

    async def save(self, data: bytes, filename: str) -> str:
        path = self.base_dir / filename
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return str(path)

    async def delete(self, storage_path: str) -> None:
        path = Path(storage_path)
        if path.exists():
            path.unlink()

    def public_url(self, storage_path: str) -> str:
        # In production, serve via a static files route or CDN
        filename = Path(storage_path).name
        return f"/uploads/{filename}"


# ── S3 storage stub (swap in when ready) ─────────────────────────────────────

class S3Storage(StorageBackend):
    """
    Swap in when moving to production.
    pip install boto3 aioboto3
    Set AWS_BUCKET, AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY in .env
    """

    def __init__(self):
        self.bucket = os.getenv("AWS_BUCKET", "your-bucket")
        self.region = os.getenv("AWS_REGION", "us-east-1")

    async def save(self, data: bytes, filename: str) -> str:
        # import aioboto3
        # async with aioboto3.Session().client("s3") as s3:
        #     await s3.put_object(Bucket=self.bucket, Key=filename, Body=data)
        raise NotImplementedError("Configure S3 credentials to use S3Storage")

    async def delete(self, storage_path: str) -> None:
        raise NotImplementedError("Configure S3 credentials to use S3Storage")

    def public_url(self, storage_path: str) -> str:
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{storage_path}"


# ── Factory ───────────────────────────────────────────────────────────────────

def get_storage() -> StorageBackend:
    """Change to S3Storage() for production."""
    backend = os.getenv("STORAGE_BACKEND", "local")
    if backend == "s3":
        return S3Storage()
    return LocalStorage()


# ── Helpers ───────────────────────────────────────────────────────────────────

def generate_stored_filename(original_filename: str) -> str:
    """Generate a unique filename preserving the extension."""
    ext = Path(original_filename).suffix.lower()
    return f"{uuid.uuid4().hex}{ext}"