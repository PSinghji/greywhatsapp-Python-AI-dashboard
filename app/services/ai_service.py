# app/services/ai_service.py
import os
import json
import logging
from openai import AsyncOpenAI
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def get_best_device_for_task(self, available_devices: list, task_type: str = "standard_message") -> str:
        """
        Asks the LLM to choose the best device based on current metrics.
        Returns the chosen deviceId. If AI fails, falls back to the first available.
        """
        if not available_devices:
            return None
            
        if not self.client:
            logger.warning("[AI Service] No OpenAI key found. Falling back to random/first selection.")
            return available_devices[0]["deviceId"]

        # 1. Prepare the telemetry data for the AI to analyze
        telemetry = []
        for d in available_devices:
            telemetry.append({
                "deviceId": d["deviceId"],
                "battery": d.get("batteryLevel", 100),
                "isCharging": d.get("isCharging", False),
                "failed_tasks": d.get("tasksFailedCount", 0),
                "free_memory_mb": d.get("freeMemoryMB", 1000)
            })

        # 2. Craft the prompt for the AI
        system_prompt = (
            "You are an intelligent routing agent for an Android device farm. "
            "Your job is to select the most reliable device for an upcoming task. "
            "Rules for selection:\n"
            "1. Prioritize devices that are charging or have high battery (>20%).\n"
            "2. Avoid devices with a high number of failed tasks.\n"
            "3. Ensure the device has enough free memory (>100MB).\n"
            "Respond ONLY with a raw JSON object containing the chosen device ID like this: "
            '{"chosenDeviceId": "the_id", "reason": "brief explanation"}'
        )
        
        user_prompt = f"Here are the available devices: {json.dumps(telemetry)}"

        # 3. Call the AI
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini", # Fast and cheap model for routing
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={ "type": "json_object" },
                temperature=0.2 # Keep it analytical, not creative
            )
            
            # 4. Parse the AI's decision
            result_text = response.choices[0].message.content
            ai_decision = json.loads(result_text)
            
            chosen_id = ai_decision.get("chosenDeviceId")
            logger.info(f"[AI Router] Selected {chosen_id}. Reason: {ai_decision.get('reason')}")
            
            return chosen_id
            
        except Exception as e:
            logger.error(f"[AI Router] AI Decision failed, falling back. Error: {e}")
            return available_devices[0]["deviceId"]
        


    async def generate_message_variations(self, base_message: dict, count: int = 3) -> list:
        """
        Takes a base message dictionary and generates AI variations of its text content.
        Preserves the original media/buttons.
        """
        if not self.client or not base_message.get("content"):
            return [base_message]

        system_prompt = (
            "You are an expert WhatsApp marketing copywriter specializing in anti-spam techniques. "
            "Your task is to rewrite the provided message into multiple distinct variations. "
            "RULES: "
            "1. Keep the exact core meaning, tone, and call-to-action the same. "
            "2. Change the sentence structure, greetings, and vocabulary to be unique. "
            "3. If there are placeholders (like {name}), KEEP THEM exactly as they are. "
            f"Provide exactly {count} variations. "
            "Respond ONLY with a JSON object containing a 'variations' array of strings, like this: "
            '{"variations": ["Variation 1", "Variation 2", "Variation 3"]}'
        )

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": base_message["content"]}
                ],
                response_format={ "type": "json_object" },
                temperature=0.7 # Higher temperature for creative variations
            )
            
            result_text = response.choices[0].message.content
            ai_data = json.loads(result_text)
            
            variations = ai_data.get("variations", [])
            
            # Construct the new message dictionaries, copying media/buttons from the base
            expanded_messages = []
            for var_text in variations:
                new_msg = base_message.copy()
                new_msg["content"] = var_text
                expanded_messages.append(new_msg)
                
            # Always include the original message just in case
            expanded_messages.append(base_message)
            
            logger.info(f"[AI Copywriter] Generated {len(variations)} variations for message.")
            return expanded_messages
            
        except Exception as e:
            logger.error(f"[AI Copywriter] Failed to generate variations: {e}")
            return [base_message]