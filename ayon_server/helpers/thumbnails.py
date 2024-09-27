import base64
import functools
import io

from PIL import Image
from starlette.concurrency import run_in_threadpool


async def process_thumbnail(
    image_bytes: bytes,
    size: tuple[int | None, int | None] = (150, None),
    format: str | None = None,
) -> bytes:
    """
    Resize an image to the specified dimensions and format asynchronously.

    Parameters:
    image_bytes: Byte stream of the original image.
    size: Desired (width, height) of the thumbnail.
        If one of the dimensions is None,
        it will be calculated based on the aspect ratio
    format: Desired image format (e.g., 'JPEG', 'PNG').
        If None, retains the original format.

    Returns:
    bytes: Byte stream of the resized and potentially reformatted image.

    Raises:
    ValueError: If both dimensions in size are None.
    """

    def process_image():
        with Image.open(io.BytesIO(image_bytes)) as img:
            target_format = format or img.format or "JPEG"

            # Ensure that we have valid dimensions
            if size == (None, None):
                raise ValueError("Both width and height cannot be None")

            new_width, new_height = size
            original_width, original_height = img.size

            if new_width is None:
                assert new_height is not None  # keeps pyright happy
                new_width = int(new_height * original_width / original_height)
            elif new_height is None:
                assert new_width is not None  # keeps pyright happy
                new_height = int(new_width * original_height / original_width)

            if new_width > original_width or new_height > original_height:
                # If the requested size is larger than the original image,
                # return the original image
                return image_bytes

            img = img.resize((new_width, new_height), Image.LANCZOS)  # type: ignore
            img_byte_arr = io.BytesIO()

            # Adjustments for specific formats
            if target_format == "JPEG":
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(img_byte_arr, format=target_format, optimize=True, quality=85)
            else:
                img.save(img_byte_arr, format=target_format)

            return img_byte_arr.getvalue()

    # Run the blocking image processing in a separate thread
    normalized_bytes = await run_in_threadpool(process_image)
    return normalized_bytes


@functools.cache
def get_fake_thumbnail() -> bytes:
    """Returns a fake thumbnail image as a byte stream.

    The image is a 1x1 pixel PNG encoded in base64.
    """
    base64_string = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="  # noqa
    return base64.b64decode(base64_string)
