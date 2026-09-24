"""QR εντύπου τιμολογίου — SVG χωρίς εξωτερική υπηρεσία."""

from __future__ import annotations

import base64
import io

try:
    import qrcode
    from qrcode.image.svg import SvgPathImage
except ImportError:
    qrcode = None
    SvgPathImage = None


def qr_svg_data_uri(text: str) -> str:
    payload = str(text or "").strip()
    if not payload or qrcode is None or SvgPathImage is None:
        return ""
    try:
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=1,
        )
        qr.add_data(payload)
        qr.make(fit=True)
        image = qr.make_image(image_factory=SvgPathImage)
        buf = io.BytesIO()
        image.save(buf)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"
    except Exception:
        return ""
