"""EXIF of a photo: shooting date and camera settings, shared by the server and the review page."""

import math
from datetime import datetime

from PIL import Image, UnidentifiedImageError

# EXIF tags: in the main IFD, then in the Exif sub-IFD.
MAKE, MODEL, DATE_CHANGED, EXIF_IFD = 271, 272, 306, 0x8769
EXPOSURE_TIME, F_NUMBER, ISO, DATE_TAKEN, OFFSET_TAKEN, FOCAL_LENGTH = 33434, 33437, 34855, 36867, 36881, 37386


def read_exif(source):
    """Shooting date and camera settings of the photo (path or file object); None for what its EXIF does not give."""
    try:
        with Image.open(source) as image:
            exif = image.getexif()
    except (OSError, UnidentifiedImageError):
        exif = Image.Exif()
    sub = exif.get_ifd(EXIF_IFD)
    iso = sub.get(ISO)
    return {
        # DateTimeOriginal, otherwise DateTime (last change).
        "taken": shot_date(sub.get(DATE_TAKEN) or exif.get(DATE_CHANGED), sub.get(OFFSET_TAKEN)),
        "camera": camera_name(exif.get(MAKE), exif.get(MODEL)),
        "exposure_time": positive(sub.get(EXPOSURE_TIME)),
        "f_number": positive(sub.get(F_NUMBER)),
        "focal_length": positive(sub.get(FOCAL_LENGTH)),
        "iso": positive(iso[0] if isinstance(iso, tuple) else iso),
    }


def exif_for_page(exif):
    """EXIF sent to a page: the date as written by the camera (its local time), to be shown as is."""
    taken = exif["taken"] and exif["taken"].replace(tzinfo=None).isoformat()
    return {**exif, "taken": taken}


def shot_date(taken, offset):
    """EXIF date, with its UTC offset when the camera wrote one (otherwise read as the PC's local time)."""
    try:
        date = datetime.strptime(text(taken), "%Y:%m:%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
    try:
        return date.replace(tzinfo=datetime.strptime(text(offset), "%z").tzinfo)
    except (ValueError, TypeError):
        return date


def camera_name(make, model):
    """"Canon EOS 5D", "SONY ILCE-7M3": the model often repeats the make."""
    make, model = text(make), text(model)
    if model.lower().startswith(make.lower()):
        return model or None
    return f"{make} {model}".strip() or None


def text(value):
    return "" if value is None else str(value).strip("\x00 ")


def positive(value):
    """EXIF number (often a fraction), or None when missing or meaningless (0, division by zero)."""
    try:
        number = float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return number if math.isfinite(number) and number > 0 else None
