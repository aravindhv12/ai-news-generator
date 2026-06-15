import httpx
import json
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL

    async def generate_completion(self, prompt: str, system_prompt: str = "") -> str:
        logger.info(f"Querying Ollama with model: {self.model}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "system": system_prompt,
                        "stream": False
                    },
                    timeout=60.0
                )
                if response.status_code == 200:
                    return response.json().get("response", "").strip()
                else:
                    logger.error(f"Ollama error: {response.text}")
                    return ""
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            return ""

    async def rank_news(self, title: str, summary: str) -> float:
        """
        Ranks a news story from 0 to 10 based on importance.
        """
        system = "You are an expert news editor. Rate the importance of the following tech news on a scale of 0 to 10. Return ONLY the number."
        prompt = f"Title: {title}\nSummary: {summary}"
        
        result = await self.generate_completion(prompt, system)
        try:
            # Try to extract the first number found in the response
            import re
            match = re.search(r"(\d+\.?\d*)", result)
            if match:
                return float(match.group(1))
            return 5.0 # Default fallback
        except:
            return 5.0

    async def generate_post_content(self, title: str, content: str):
        """
        Generates headline, caption (20-25 words) and hashtags.
        """
        system = """
        You are a world-class social media copywriter for a premium tech news platform.
        Tasks:
        1. Write a compelling headline (max 10 words).
        2. Write a highly engaging caption that MUST be EXACTLY 20 to 25 words long.
           The caption must follow this exact 3-part structure:
           - Part 1: A strong, hooky first sentence (the hook).
           - Part 2: A useful, value-packed tech insight (the insight).
           - Part 3: A natural, soft call-to-action (the soft CTA).
        3. Provide 3 to 5 highly relevant tech hashtags.

        CRITICAL STYLE GUIDELINES:
        - NEVER use generic AI words (e.g., "delve", "testament", "revolutionize", "tapestry", "moreover").
        - Avoid generic motivational text or repetitive phrasing.
        - Ensure the language is natural, concise, professional, and social-media ready.

        You MUST return the output ONLY as a raw JSON object with the following keys:
        {
            "headline": "...",
            "caption": "...",
            "hashtags": ["#Tag1", "#Tag2", ...]
        }
        Do not wrap it in markdown block quotes or add any conversational filler.
        """
        prompt = f"Article Title: {title}\nArticle Content: {content}"
        
        result = await self.generate_completion(prompt, system)
        try:
            # Attempt to parse json
            start = result.find("{")
            end = result.rfind("}") + 1
            if start != -1 and end != -1:
                parsed = json.loads(result[start:end])
                # Ensure caption exists and headline is mapped correctly
                if "caption" in parsed and "summary" not in parsed:
                    parsed["summary"] = parsed["caption"]
                elif "summary" in parsed and "caption" not in parsed:
                    parsed["caption"] = parsed["summary"]
                return parsed
            return None
        except Exception as e:
            logger.error(f"JSON Parsing error in content generation: {e}")
            return None

    async def generate_batch_posts(self, stories: list) -> list:
        """
        Generates headlines and captions for multiple stories in a single AI call to optimize credits.
        """
        if not stories:
            return []
            
        system = """
        You are a premium social media copywriter. Generate social media posts for the given list of articles.
        For each article, write:
        1. A headline (max 10 words).
        2. An engaging caption (EXACTLY 20 to 25 words long) following this exact 3-part structure:
           - Part 1: A strong, hooky first sentence (the hook).
           - Part 2: A useful, value-packed tech insight (the insight).
           - Part 3: A natural, soft call-to-action (the soft CTA).
        3. 3 to 5 highly relevant tech hashtags.

        CRITICAL STYLE GUIDELINES:
        - NEVER use generic AI words (e.g., "delve", "testament", "revolutionize", "tapestry", "moreover").
        - Ensure language is natural, concise, professional, and social-media ready.

        You MUST return the output ONLY as a raw JSON object with the following key:
        {
            "posts": [
                {
                    "news_id": "...",
                    "headline": "...",
                    "caption": "...",
                    "hashtags": ["#Tag1", "#Tag2", ...]
                },
                ...
            ]
        }
        Do not wrap it in markdown block quotes or add any conversational filler.
        """
        
        prompt_parts = []
        for idx, story in enumerate(stories):
            prompt_parts.append(
                f"Article {idx + 1} (news_id: {story['id']}):\n"
                f"Title: {story['title']}\n"
                f"Content: {story['content'] or ''}\n"
            )
        prompt = "\n".join(prompt_parts)
        
        result = await self.generate_completion(prompt, system)
        try:
            start = result.find("{")
            end = result.rfind("}") + 1
            if start != -1 and end != -1:
                parsed = json.loads(result[start:end])
                posts_list = parsed.get("posts", [])
                # Normalize key names for safety
                for p in posts_list:
                    if "caption" in p and "summary" not in p:
                        p["summary"] = p["caption"]
                    elif "summary" in p and "caption" not in p:
                        p["caption"] = p["summary"]
                return posts_list
            return []
        except Exception as e:
            logger.error(f"JSON Parsing error in batch generation: {e}")
            return []

ai_service = AIService()
