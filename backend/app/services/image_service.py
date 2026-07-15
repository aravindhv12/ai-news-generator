from PIL import Image, ImageDraw, ImageFont, ImageFilter
import httpx
from io import BytesIO
import os
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Bundled font paths (always available — committed to the repo under app/fonts/)
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_FONTS_DIR = os.path.join(_MODULE_DIR, "..", "fonts")

# System font fallbacks for local macOS development
_SYSTEM_FONT_FALLBACKS = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """
    Load Inter font at given size. Falls back gracefully to system fonts, then PIL default.
    """
    variant = "Inter-Bold.ttf" if bold else "Inter-Regular.ttf"
    candidates = [
        os.path.join(_FONTS_DIR, variant),
        os.path.join(os.path.dirname(_MODULE_DIR), "fonts", variant),
    ] + _SYSTEM_FONT_FALLBACKS

    for path in candidates:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            continue
    # Absolute last resort: PIL built-in bitmap
    return ImageFont.load_default()


class SocialCardGenerator:
    def __init__(self, output_dir: str = "output"):
        if os.getenv("VERCEL"):
            self.output_dir = "/tmp/output"
        else:
            self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    async def ensure_fonts(self):
        """No-op: fonts are now bundled in the repo. Kept for API compatibility."""
        bold_path = os.path.join(_FONTS_DIR, "Inter-Bold.ttf")
        reg_path = os.path.join(_FONTS_DIR, "Inter-Regular.ttf")
        if os.path.exists(bold_path) and os.path.exists(reg_path):
            logger.info("Bundled Inter fonts found and ready.")
        else:
            logger.warning("Bundled Inter fonts not found at %s — will fall back to system fonts.", _FONTS_DIR)

    async def download_image(self, url: str) -> Optional[Image.Image]:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=12.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return Image.open(BytesIO(resp.content))
        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
        return None

    def generate_card(self, article_image: Image.Image, headline: str, summary: str, post_id: str) -> str:
        """
        Generate a 1080×1080 full-bleed Instagram tech card with the bold headline
        embedded directly into the image using a dark gradient overlay and a
        semi-transparent frosted-glass pill behind the text.
        """
        W, H = 1080, 1080
        PAD = 72           # horizontal padding for text
        ACCENT = (0, 230, 118)        # vibrant green brand accent
        HEADLINE_COLOR = (255, 255, 255)  # white headline
        TAG_COLOR = ACCENT

        # ── 1. Fill canvas with full-bleed article image ──────────────────────
        base = article_image.convert("RGB")
        base = self._resize_and_crop(base, (W, H))
        card = base.convert("RGBA")

        # ── 2. Gradient overlay (transparent top → near-opaque bottom) ─────────
        gradient = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gradient)
        GRAD_START = 380          # gradient begins at Y=380 (top-third stays clean)
        for y in range(GRAD_START, H):
            t = (y - GRAD_START) / (H - GRAD_START)   # 0.0 → 1.0
            alpha = int(t * t * 230)                    # quadratic ease — punchy dark bottom
            gd.line([(0, y), (W, y)], fill=(8, 8, 12, alpha))
        card = Image.alpha_composite(card, gradient)

        draw = ImageDraw.Draw(card)

        # ── 3. Load fonts (bundled Inter, system fallback, PIL default) ────────
        font_tag   = _load_font(22, bold=True)
        font_head  = _load_font(56, bold=True)
        font_brand = _load_font(20, bold=False)

        # ── 4. Wrap headline ───────────────────────────────────────────────────
        max_text_w = W - PAD * 2
        wrapped = self._wrap_text(headline, font_head, max_text_w, max_lines=3)

        # ── 5. Measure text block height ──────────────────────────────────────
        # getbbox returns (left, top, right, bottom)
        lines = wrapped.split("\n")
        line_h = font_head.getbbox("Ag")[3] + 12   # line height + leading
        block_h = line_h * len(lines)

        TAG_TEXT = "⚡ TECH DIRECT"
        tag_h = font_tag.getbbox(TAG_TEXT)[3] + 8

        PILL_TOP    = H - PAD - block_h - tag_h - 60
        PILL_BOTTOM = H - PAD + 12

        # ── 6. Semi-transparent glassmorphism pill behind text ─────────────────
        pill_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pill_layer)
        RADIUS = 20
        pd.rounded_rectangle(
            [PAD - 20, PILL_TOP - 16, W - PAD + 20, PILL_BOTTOM],
            radius=RADIUS,
            fill=(0, 0, 0, 140)         # 55% opacity black pill
        )
        card = Image.alpha_composite(card, pill_layer)
        draw = ImageDraw.Draw(card)

        # ── 7. Draw category tag ───────────────────────────────────────────────
        tag_y = PILL_TOP
        draw.text((PAD, tag_y), TAG_TEXT, font=font_tag, fill=TAG_COLOR)

        # ── 8. Draw headline lines individually with colored first word ────────
        head_y = tag_y + tag_h + 10
        for i, line in enumerate(lines):
            words = line.split(" ", 1)
            x = PAD
            # First word of first line in accent color — rest in white
            if i == 0 and words:
                first_word = words[0]
                first_w = font_head.getbbox(first_word + " ")[2]
                draw.text((x, head_y), first_word + " ", font=font_head, fill=ACCENT)
                rest = words[1] if len(words) > 1 else ""
                if rest:
                    draw.text((x + first_w, head_y), rest, font=font_head, fill=HEADLINE_COLOR)
            else:
                draw.text((x, head_y), line, font=font_head, fill=HEADLINE_COLOR)
            head_y += line_h

        # ── 9. Brand label at bottom ───────────────────────────────────────────
        brand = settings.PROJECT_NAME.upper() if hasattr(settings, "PROJECT_NAME") else "TECH DIRECT"
        brand_y = H - PAD + 2
        draw.rectangle([PAD, brand_y + 6, PAD + 8, brand_y + 14], fill=ACCENT)
        draw.text((PAD + 18, brand_y), brand, font=font_brand, fill=(200, 200, 210))

        # ── 10. Save as valid RGB PNG ──────────────────────────────────────────
        output_path = os.path.join(self.output_dir, f"{post_id}.png")
        card.convert("RGB").save(output_path, format="PNG", optimize=False)
        logger.info(f"Card generated: {output_path}")
        return output_path

    def _resize_and_crop(self, img: Image.Image, size: tuple) -> Image.Image:
        tw, th = size
        iw, ih = img.size
        if iw / ih > tw / th:
            # wider than target → fit height, crop width
            scale = th / ih
            nw = int(iw * scale)
            img = img.resize((nw, th), Image.Resampling.LANCZOS)
            left = (nw - tw) // 2
            img = img.crop((left, 0, left + tw, th))
        else:
            # taller than target → fit width, crop height
            scale = tw / iw
            nh = int(ih * scale)
            img = img.resize((tw, nh), Image.Resampling.LANCZOS)
            top = (nh - th) // 2
            img = img.crop((0, top, tw, top + th))
        return img

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int = 3) -> str:
        words = text.split()
        lines = []
        current: list[str] = []

        for word in words:
            current.append(word)
            w = font.getbbox(" ".join(current))[2]
            if w > max_width:
                current.pop()
                if current:
                    lines.append(" ".join(current))
                current = [word]
            if len(lines) >= max_lines - 1:
                # dump remaining words onto last line
                remaining = " ".join(current + words[words.index(word) + 1:])
                lines.append(remaining)
                current = []
                break

        if current:
            lines.append(" ".join(current))

        return "\n".join(lines[:max_lines])


image_service = SocialCardGenerator()
