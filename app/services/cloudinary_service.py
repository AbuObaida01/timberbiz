import cloudinary
import cloudinary.uploader
from fastapi import HTTPException
from app.config import settings

# Configuring cloudinary
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

def upload_image(file_bytes: bytes, folder:str="timberbiz/trees") -> str:
    """
    Upload image bytes to Cloudinary.
    Returns the secure URL of the uploaded image.
    """
    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            folder=folder,
            resource_type="image"
        )
        return result["secure_url"]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Image upload failed: {str(e)}"
        )

def delete_image(public_id: str) -> bool:
    """Delete an image from Cloudinary by its public ID"""
    try:
        cloudinary.uploader.destroy(public_id)
        return True
    except Exception as e:
        return False