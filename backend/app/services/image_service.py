from PIL import Image, ImageDraw, ImageFont, ImageFilter
import httpx
from io import BytesIO
import os
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

class SocialCardGenerator:
    def __init__(self, output_dir: str = "output"):
        if os.getenv("VERCEL"):
            self.output_dir = "/tmp/output"
        else:
            self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Downloaded fonts directory
        self.font_dir = os.path.abspath(os.path.join(self.output_dir, "../fonts"))
        os.makedirs(self.font_dir, exist_ok=True)
        self.font_bold_path = os.path.join(self.font_dir, "Inter-Bold.ttf")
        self.font_regular_path = os.path.join(self.font_dir, "Inter-Regular.ttf")
        
        self.font_bold = self.font_bold_path
        self.font_regular = self.font_regular_path

    async def ensure_fonts(self):
        # Download fonts if they do not exist
        async with httpx.AsyncClient() as client:
            font_sources = [
                ("Inter-Bold.ttf", [
                    "https://github.com/google/fonts/raw/main/ofl/inter/static/Inter-Bold.ttf",
                    "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bslnt%2Cwght%5D.ttf"
                ]),
                ("Inter-Regular.ttf", [
                    "https://github.com/google/fonts/raw/main/ofl/inter/static/Inter-Regular.ttf",
                    "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bslnt%2Cwght%5D.ttf"
                ])
            ]
            for source_name, urls in font_sources:
                path = os.path.join(self.font_dir, source_name)
                if not os.path.exists(path):
                    for url in urls:
                        try:
                            logger.info(f"Downloading {source_name} from {url}...")
                            resp = await client.get(url, follow_redirects=True, timeout=15.0)
                            if resp.status_code == 200:
                                with open(path, "wb") as f:
                                    f.write(resp.content)
                                logger.info(f"Successfully downloaded {source_name}")
                                break
                        except Exception as e:
                            logger.error(f"Failed to download from {url}: {e}")

    async def download_image(self, url: str) -> Optional[Image.Image]:

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    return Image.open(BytesIO(resp.content))
        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
        return None

    def generate_card(self, article_image: Image.Image, headline: str, summary: str, post_id: str) -> str:
        # Standardized design tokens
        width, height = 1080, 1080
        padding = 90
        background_color = (10, 10, 12)   # Premium deep slate-black
        accent_color = (0, 255, 127)      # Neon green accent
        text_primary = (255, 255, 255)    # Clean white
        text_secondary = (160, 160, 170)  # Muted grey
        
        # Initialize card image
        card = Image.new('RGB', (width, height), color=background_color)
        
        # Top Image Area: 54% height
        img_h = int(height * 0.54)
        article_image = article_image.convert("RGB")
        article_image = self._resize_and_crop(article_image, (width, img_h))
        card.paste(article_image, (0, 0))
        
        # Bottom Text Area Drawing
        draw = ImageDraw.Draw(card)
        text_area_y = img_h
        
        # Draw text area background
        draw.rectangle([0, text_area_y, width, height], fill=background_color)
        
        # Load fonts with robust fallbacks
        font_bold_size = 48
        font_regular_size = 24
        
        font_h = None
        for p in [self.font_bold, "/System/Library/Fonts/HelveticaNeue.ttc", "/Library/Fonts/Arial.ttf"]:
            try:
                font_h = ImageFont.truetype(p, font_bold_size)
                break
            except:
                continue
        if not font_h:
            font_h = ImageFont.load_default()
            
        font_r = None
        for p in [self.font_regular, "/System/Library/Fonts/HelveticaNeue.ttc", "/Library/Fonts/Arial.ttf"]:
            try:
                font_r = ImageFont.truetype(p, font_regular_size)
                break
            except:
                continue
        if not font_r:
            font_r = ImageFont.load_default()
            
        # Draw Category Tag above headline
        tag_y = text_area_y + 45
        draw.text((padding, tag_y), "⚡ TECH DIRECT", font=font_r, fill=accent_color)
        
        # Draw Premium Headline (No summary/caption text for visual elegance and whitespace)
        headline_y = tag_y + 45
        wrapped_headline = self._wrap_text(headline, font_h, width - (padding * 2))
        draw.text((padding, headline_y), wrapped_headline, font=font_h, fill=text_primary, spacing=8)
        
        # Draw Minimalist Brand Accent Label at the bottom
        brand_y = height - 90
        brand_name = settings.PROJECT_NAME.upper()
        # Draw tiny accent green square
        draw.rectangle([padding, brand_y + 8, padding + 8, brand_y + 16], fill=accent_color)
        # Draw text next to the square
        draw.text((padding + 20, brand_y), brand_name, font=font_r, fill=text_secondary)
        
        output_path = os.path.join(self.output_dir, f"{post_id}.png")
        card.save(output_path)
        return output_path

    def _resize_and_crop(self, img, size):
        target_w, target_h = size
        img_w, img_h = img.size
        
        # Calculate scale
        img_ratio = img_w / img_h
        target_ratio = target_w / target_h
        
        if img_ratio > target_ratio:
            # Image is wider
            new_h = target_h
            new_w = int(img_ratio * target_h)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            left = (new_w - target_w) / 2
            img = img.crop((left, 0, left + target_w, target_h))
        else:
            # Image is taller or same
            new_w = target_w
            new_h = int(target_w / img_ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            top = (new_h - target_h) / 2
            img = img.crop((0, top, target_w, top + target_h))
            
        return img

    def _wrap_text(self, text, font, max_width):
        lines = []
        words = text.split()
        current_line = []
        
        for word in words:
            current_line.append(word)
            w = font.getbbox(" ".join(current_line))[2]
            if w > max_width:
                current_line.pop()
                lines.append(" ".join(current_line))
                current_line = [word]
        
        lines.append(" ".join(current_line))
        return "\n".join(lines)

image_service = SocialCardGenerator()
