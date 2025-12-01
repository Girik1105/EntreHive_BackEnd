"""
Image Compression Engine for EntreHive

This module provides image compression, resizing, and optimization utilities
for profile pictures, post images, and project banners.

Features:
- Automatic image compression using Pillow
- Resize to max dimensions while maintaining aspect ratio
- Convert to WebP format for better compression
- Strip EXIF metadata for privacy
- Create thumbnails for list views
- Maximum file size enforcement
"""

from PIL import Image, ExifTags
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys
import logging

logger = logging.getLogger(__name__)


class ImageCompressor:
    """
    Image compression utility class for handling various image types.
    """

    # Maximum dimensions for different image types
    PROFILE_MAX_SIZE = (800, 800)
    BANNER_MAX_SIZE = (1920, 1080)
    POST_MAX_SIZE = (1200, 1200)
    THUMBNAIL_SIZE = (300, 300)

    # Quality settings (1-100)
    DEFAULT_QUALITY = 85
    THUMBNAIL_QUALITY = 75

    # Maximum input file size (5MB)
    MAX_INPUT_SIZE_MB = 5
    MAX_INPUT_SIZE_BYTES = MAX_INPUT_SIZE_MB * 1024 * 1024

    # Target output size (500KB for main images, 100KB for thumbnails)
    TARGET_SIZE_BYTES = 500 * 1024
    THUMBNAIL_TARGET_SIZE_BYTES = 100 * 1024

    # Supported input formats
    SUPPORTED_FORMATS = {'JPEG', 'JPG', 'PNG', 'GIF', 'WEBP', 'BMP', 'TIFF'}

    @classmethod
    def validate_image(cls, image_file):
        """
        Validate that the uploaded file is a valid image.

        Args:
            image_file: Django uploaded file object

        Returns:
            tuple: (is_valid, error_message)
        """
        if not image_file:
            return False, "No image file provided"

        # Check file size
        if hasattr(image_file, 'size') and image_file.size > cls.MAX_INPUT_SIZE_BYTES:
            return False, f"Image file size exceeds {cls.MAX_INPUT_SIZE_MB}MB limit"

        try:
            # Try to open and verify the image
            image_file.seek(0)
            img = Image.open(image_file)
            img.verify()  # Verify it's actually an image
            image_file.seek(0)

            # Check format
            img = Image.open(image_file)
            if img.format and img.format.upper() not in cls.SUPPORTED_FORMATS:
                return False, f"Unsupported image format: {img.format}"

            image_file.seek(0)
            return True, None

        except Exception as e:
            logger.warning(f"Image validation failed: {e}")
            return False, "Invalid image file"

    @classmethod
    def strip_exif(cls, image):
        """
        Remove EXIF metadata from image for privacy.

        Args:
            image: PIL Image object

        Returns:
            PIL Image object without EXIF data
        """
        # Create a new image without EXIF data
        data = list(image.getdata())
        image_without_exif = Image.new(image.mode, image.size)
        image_without_exif.putdata(data)
        return image_without_exif

    @classmethod
    def resize_image(cls, image, max_size):
        """
        Resize image to fit within max_size while maintaining aspect ratio.

        Args:
            image: PIL Image object
            max_size: tuple (max_width, max_height)

        Returns:
            PIL Image object (resized if necessary)
        """
        # Only resize if image is larger than max size
        if image.width <= max_size[0] and image.height <= max_size[1]:
            return image

        # Calculate new size maintaining aspect ratio
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        return image

    @classmethod
    def compress_to_target_size(cls, image, target_size_bytes, initial_quality=85):
        """
        Compress image to target file size by adjusting quality.

        Args:
            image: PIL Image object
            target_size_bytes: Target file size in bytes
            initial_quality: Starting quality (1-100)

        Returns:
            BytesIO object containing compressed image
        """
        quality = initial_quality
        min_quality = 20

        while quality >= min_quality:
            buffer = BytesIO()

            # Convert to RGB if necessary (for PNG with transparency)
            if image.mode in ('RGBA', 'P'):
                # Create white background for transparent images
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'RGBA':
                    background.paste(image, mask=image.split()[3])
                else:
                    background.paste(image)
                image_to_save = background
            else:
                image_to_save = image.convert('RGB') if image.mode != 'RGB' else image

            # Save as WebP for better compression
            image_to_save.save(buffer, format='WEBP', quality=quality, optimize=True)

            if buffer.tell() <= target_size_bytes or quality <= min_quality:
                buffer.seek(0)
                return buffer, quality

            quality -= 5

        buffer.seek(0)
        return buffer, quality

    @classmethod
    def compress_image(cls, image_file, image_type='post'):
        """
        Main compression function for images.

        Args:
            image_file: Django uploaded file object
            image_type: 'profile', 'banner', 'post', or 'thumbnail'

        Returns:
            InMemoryUploadedFile: Compressed image ready for storage

        Raises:
            ValueError: If image validation fails
        """
        # Validate input
        is_valid, error = cls.validate_image(image_file)
        if not is_valid:
            raise ValueError(error)

        # Determine max size based on image type
        size_map = {
            'profile': cls.PROFILE_MAX_SIZE,
            'banner': cls.BANNER_MAX_SIZE,
            'post': cls.POST_MAX_SIZE,
            'thumbnail': cls.THUMBNAIL_SIZE,
        }
        max_size = size_map.get(image_type, cls.POST_MAX_SIZE)

        # Determine target size
        target_size = cls.THUMBNAIL_TARGET_SIZE_BYTES if image_type == 'thumbnail' else cls.TARGET_SIZE_BYTES

        # Determine quality
        quality = cls.THUMBNAIL_QUALITY if image_type == 'thumbnail' else cls.DEFAULT_QUALITY

        try:
            # Open image
            image_file.seek(0)
            image = Image.open(image_file)

            # Handle orientation from EXIF
            try:
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation] == 'Orientation':
                        break

                exif = image._getexif()
                if exif is not None:
                    orientation_value = exif.get(orientation)
                    if orientation_value == 3:
                        image = image.rotate(180, expand=True)
                    elif orientation_value == 6:
                        image = image.rotate(270, expand=True)
                    elif orientation_value == 8:
                        image = image.rotate(90, expand=True)
            except (AttributeError, KeyError, IndexError):
                pass

            # Strip EXIF metadata
            image = cls.strip_exif(image)

            # Resize image
            image = cls.resize_image(image, max_size)

            # Compress to target size
            buffer, final_quality = cls.compress_to_target_size(image, target_size, quality)

            # Generate output filename
            original_name = getattr(image_file, 'name', 'image.jpg')
            base_name = original_name.rsplit('.', 1)[0] if '.' in original_name else original_name
            new_filename = f"{base_name}_compressed.webp"

            # Create InMemoryUploadedFile
            compressed_file = InMemoryUploadedFile(
                file=buffer,
                field_name=None,
                name=new_filename,
                content_type='image/webp',
                size=buffer.getbuffer().nbytes,
                charset=None
            )

            logger.info(
                f"Image compressed: {original_name} -> {new_filename}, "
                f"size: {buffer.getbuffer().nbytes / 1024:.1f}KB, quality: {final_quality}"
            )

            return compressed_file

        except Exception as e:
            logger.error(f"Image compression failed: {e}")
            raise ValueError(f"Failed to compress image: {str(e)}")

    @classmethod
    def compress_profile_picture(cls, image_file):
        """Compress profile picture."""
        return cls.compress_image(image_file, image_type='profile')

    @classmethod
    def compress_banner_image(cls, image_file):
        """Compress banner image."""
        return cls.compress_image(image_file, image_type='banner')

    @classmethod
    def compress_post_image(cls, image_file):
        """Compress post image."""
        return cls.compress_image(image_file, image_type='post')

    @classmethod
    def create_thumbnail(cls, image_file):
        """Create thumbnail from image."""
        return cls.compress_image(image_file, image_type='thumbnail')


def compress_uploaded_image(image_file, image_type='post'):
    """
    Convenience function to compress an uploaded image.

    Args:
        image_file: Django uploaded file object
        image_type: 'profile', 'banner', 'post', or 'thumbnail'

    Returns:
        InMemoryUploadedFile: Compressed image
    """
    return ImageCompressor.compress_image(image_file, image_type)
