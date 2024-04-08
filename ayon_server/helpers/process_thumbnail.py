import io

from PIL import Image
from starlette.concurrency import run_in_threadpool


async def process_thumbnail(
    image_bytes: bytes,
    size: tuple = (150, 150),
    format: str = "JPEG",
) -> bytes:
    def process_image():
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.resize(size, Image.LANCZOS)

            img_byte_arr = io.BytesIO()
            # Note: For JPEG, consider adding `optimize=True` and `quality`
            img.save(img_byte_arr, format=format)

            return img_byte_arr.getvalue()

    # Run the blocking image processing in a separate thread
    normalized_bytes = await run_in_threadpool(process_image)
    return normalized_bytes
