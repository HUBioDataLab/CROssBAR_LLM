import csv
import io
import numpy as np

from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from crossbar_llm.api.core.settings import Settings
from crossbar_llm.agent_tools.config import VectorMappings

@dataclass
class ValidatedUpload:
    filename: str
    suffix: str
    size_bytes: int
    content_type: str | None


class FileGuard:
    def __init__(self, settings: Settings, vector_index: str):
        self.settings = settings
        self.vector_index = vector_index
        self.index_name_to_vector_size = VectorMappings().index_name_to_vector_size()
    
    async def validate_file(self, upload: UploadFile) -> ValidatedUpload:
        if not upload.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file must have a filename")

        suffix = Path(upload.filename).suffix.lower().lstrip(".")
        if suffix not in self.settings.allowed_upload_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unsupported file extension: .{suffix}",
            )
        
        raw = await upload.read(self.settings.upload_size_max_bytes + 1)
        await upload.seek(0)

        if len(raw) > self.settings.upload_size_max_bytes:
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="uploaded file is too large")
        
        if upload.content_type and upload.content_type not in self.settings.allowed_upload_content_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unsupported content type: {upload.content_type}")
        
        if suffix == "npy" and not raw.startswith(b"\x93NUMPY"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid npy file signature")

        if suffix == "csv" and b"\x00" in raw[:1024]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="csv file appears to be binary")
        
        return ValidatedUpload(
            filename=upload.filename,
            suffix=suffix,
            size_bytes=len(raw),
            content_type=upload.content_type,
        )
    
    async def load_embedding(self, upload: UploadFile) -> np.ndarray:
        meta = await self.validate_file(upload)
        raw = await upload.read(self.settings.upload_size_max_bytes + 1)
        await upload.seek(0)

        if meta.suffix == "npy":
            array = np.load(io.BytesIO(raw))
            await self.validate_embedding(array)

            return array
        else:
            text = raw.decode("utf-8")
            reader = csv.reader(io.StringIO(text))
            first_row = next(reader, None)
            if not first_row:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="csv file is empty")
            
            array = np.array([float(item) for item in first_row], dtype=float)
            await self.validate_embedding(array)
            return array
    
    async def validate_embedding(self, embedding: np.ndarray) -> None:
        if embedding.ndim != 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="embedding must be a 1D array")
        
        if embedding.size == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="embedding vector cannot be empty")
        
        if np.isnan(embedding).any() or np.isinf(embedding).any():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="embedding contains NaN or infinite values")
        
        if not np.issubdtype(embedding.dtype, np.floating):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="embedding must be of a floating-point type")
        
        if self.vector_index not in self.index_name_to_vector_size:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="embedding vector index is not recognized")
        elif embedding.shape[0] != self.index_name_to_vector_size[self.vector_index]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"embedding vector size {embedding.shape[0]} does not match expected size {self.index_name_to_vector_size[self.vector_index]} for index {self.vector_index}",
            )
        



        

        

    
