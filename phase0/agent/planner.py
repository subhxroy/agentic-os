import json
import os
import google.genai as genai
from google.genai import types

class PlanningEngine:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-3.5-flash"

    def generate_plan(self, goal: str, available_tools: list[str]) -> dict:
        prompt = f"""You are a planning engine. Break this goal into executable steps.

Goal: {goal}

Available tools: {', '.join(available_tools)}

Return a JSON plan like this:
{{
  "goal": "the original goal",
  "steps": [
    {{ "step": 1, "action": "description of action", "tool": "tool_name or null", "depends_on": [] }},
    {{ "step": 2, "action": "description", "tool": "tool_name or null", "depends_on": [1] }}
  ],
  "estimated_steps": 3
}}

Rules:
- Each step should be atomic (one action)
- Use tool names only if a specific tool is needed
- Keep steps in logical order
- Include dependency relationships"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=2048),
        )

        try:
            text = response.text
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception:
            pass

        return {"goal": goal, "steps": [{"step": 1, "action": goal, "tool": None, "depends_on": []}], "estimated_steps": 1}

    def should_plan(self, user_input: str) -> bool:
        complex_indicators = ["plan", "steps", "first.*then", "build.*deploy", "create.*and.*set"]
        import re
        for indicator in complex_indicators:
            if re.search(indicator, user_input, re.IGNORECASE):
                return True
        return False
