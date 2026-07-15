import httpx
import json
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self._is_online = None

    async def check_online(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/", timeout=1.5)
                is_ok = resp.status_code == 200
                self._is_online = is_ok
                return is_ok
        except Exception:
            self._is_online = False
            return False

    async def generate_completion(self, prompt: str, system_prompt: str = "") -> str:
        # If we already checked and Ollama is offline, bypass the HTTP request immediately
        if self._is_online is False:
            logger.warning("Bypassing Ollama query: AI Service is offline.")
            return ""

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
                    timeout=8.0
                )
                if response.status_code == 200:
                    self._is_online = True
                    return response.json().get("response", "").strip()
                else:
                    logger.error(f"Ollama error: {response.text}")
                    return ""
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            self._is_online = False
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
        1. Write a compelling, premium headline (MUST be between 10 and 15 words) that instantly conveys the core news of the story without requiring further context.
        2. Write a highly engaging, Instagram-ready caption that MUST be between 100 and 120 words maximum.
           The caption must follow this structure:
           - An engaging hook sentence relevant only to the article's topic.
           - A value-packed tech insight/summary of the post.
           - A natural, soft call-to-action (CTA).
           - Integrate appropriate emojis naturally.
        3. Provide 5 to 10 highly relevant tech hashtags.

        CRITICAL STYLE GUIDELINES:
        - The caption MUST be detailed, informative, and Instagram-ready.
        - The total word count of the caption MUST be between 100 and 120 words.
        - NEVER use generic AI words (e.g., "delve", "testament", "revolutionize", "tapestry", "moreover").
        - The caption and CTA MUST NOT end with a question (e.g., do NOT write 'What are your thoughts?', 'How will you prepare?', or similar questions). Use a concise, professional closing statement.
        - Emojis should be integrated in the caption text.
        - Ensure the content is relevant to the generated post only, with no generic or random content.

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
        1. A compelling, premium headline (MUST be between 10 and 15 words) that instantly conveys the core news of the story without requiring further context.
        2. An engaging, Instagram-ready caption that MUST be between 100 and 120 words maximum.
           The caption must follow this structure:
           - An engaging hook sentence relevant only to the article's topic.
           - A value-packed tech insight/summary of the post.
           - A natural, soft call-to-action (CTA).
           - Integrate appropriate emojis naturally.
        3. 5 to 10 highly relevant tech hashtags.

        CRITICAL STYLE GUIDELINES:
        - The caption MUST be detailed, informative, and Instagram-ready.
        - The total word count of the caption MUST be between 100 and 120 words.
        - NEVER use generic AI words (e.g., "delve", "testament", "revolutionize", "tapestry", "moreover").
        - The caption and CTA MUST NOT end with a question (e.g., do NOT write 'What are your thoughts?', 'How will you prepare?', or similar questions). Use a concise, professional closing statement.
        - Emojis should be integrated in the caption text.
        - Ensure the content is relevant to the generated post only, with no generic or random content.

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
