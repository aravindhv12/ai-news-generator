from PIL import Image, ImageDraw, ImageFont, ImageFilter
import httpx
from io import BytesIO
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class SocialCardGenerator:
    def __init__(self, output_dir: str = "output"):
        if os.getenv("VERCEL"):
            self.output_dir = "/tmp/output"
        else:
            self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        # In production, these fonts should be in an assets folder
        self.font_bold = "/System/Library/Fonts/HelveticaNeue.ttc" # Mac default
        self.font_regular = "/System/Library/Fonts/HelveticaNeue.ttc"

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
        padding = 80
        background_color = (15, 15, 17) # Premium near-black
        accent_color = (0, 255, 127)    # Neon green accent
        text_primary = (255, 255, 255)  # Clean white
        text_secondary = (160, 160, 170) # Muted grey
        
        # Initialize card image
        card = Image.new('RGB', (width, height), color=background_color)
        
        # Standardized Top Image Area: Exactly 55% height
        img_h = int(height * 0.55)
        article_image = article_image.convert("RGB")
        article_image = self._resize_and_crop(article_image, (width, img_h))
        card.paste(article_image, (0, 0))
        
        # Bottom Text Area Drawing
        draw = ImageDraw.Draw(card)
        text_area_y = img_h
        
        # Draw text area background
        draw.rectangle([0, text_area_y, width, height], fill=background_color)
        
        # Load fonts using standard fallback checks
        try:
            font_h = ImageFont.truetype(self.font_bold, 44)
        except:
            font_h = ImageFont.load_default()
            
        try:
            font_s = ImageFont.truetype(self.font_regular, 28)
        except:
            font_s = ImageFont.load_default()
            
        # Draw Headline
        headline_y = text_area_y + 50
        wrapped_headline = self._wrap_text(headline, font_h, width - (padding * 2))
        draw.text((padding, headline_y), wrapped_headline, font=font_h, fill=text_primary)
        
        # Draw Caption/Summary
        # Calculate headline height to position summary dynamically
        h_lines = wrapped_headline.count('\n') + 1
        summary_y = headline_y + (h_lines * 55) + 30
        wrapped_summary = self._wrap_text(summary, font_s, width - (padding * 2))
        draw.text((padding, summary_y), wrapped_summary, font=font_s, fill=text_secondary)
        
        # Draw Brand Accent Label (aligned to bottom)
        brand_y = height - 90
        draw.text((padding, brand_y), "GUESS", font=font_h, fill=accent_color)
        
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
