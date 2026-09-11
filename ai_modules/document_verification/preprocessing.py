"""Light image preprocessing to help OCR.

Each step is a separate function so they can be improved or reordered later.
The uploaded file itself is never modified: these functions work on a copy
held in memory.
"""

# Small scans read poorly, so anything narrower than this is enlarged.
MIN_WIDTH = 1000
MAX_WIDTH = 3000


def to_grayscale(image):
    """Colour carries no information for text recognition."""
    return image.convert("L")


def upscale_if_small(image, min_width: int = MIN_WIDTH, max_width: int = MAX_WIDTH):
    """Enlarge small images, and shrink very large ones."""
    from PIL import Image

    width, height = image.size
    if width == 0 or height == 0:
        return image

    if width < min_width:
        scale = min_width / width
    elif width > max_width:
        scale = max_width / width
    else:
        return image

    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.LANCZOS)


def enhance_contrast(image):
    """Stretch the brightness range so faint text stands out."""
    from PIL import ImageOps

    return ImageOps.autocontrast(image)


def threshold(image, cutoff: int = 160):
    """Turn the image into black text on white, which Tesseract prefers."""
    return image.point(lambda value: 255 if value > cutoff else 0, mode="L")


def prepare_for_ocr(image, use_threshold: bool = True):
    """Run the full preprocessing chain on a copy of the image."""
    prepared = to_grayscale(image.copy())
    prepared = upscale_if_small(prepared)
    prepared = enhance_contrast(prepared)
    if use_threshold:
        prepared = threshold(prepared)
    return prepared
