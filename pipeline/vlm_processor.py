# pipeline/vlm_processor.py
import numpy as np

class VLMProcessor:
    def __init__(self, model_id: str = "llava-hf/llava-1.5-7b-hf", mock: bool = True):
        self.mock = mock
        self.model_id = model_id
        if not self.mock:
            import torch
            from transformers import pipeline
            # Initialize a VLM pipeline
            self.pipe = pipeline(
                "image-to-text",
                model=model_id,
                device=0 if torch.cuda.is_available() else -1,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
            )
        else:
            self.pipe = None

    def analyze_scene(self, img: np.ndarray, prompt: str) -> str:
        """
        Analyzes an image crop or full frame using a visual language query.
        """
        if self.mock:
            # High-fidelity mock responses based on standard retail prompt keywords
            prompt_lower = prompt.lower()
            if "customer" in prompt_lower or "person" in prompt_lower:
                return "The customer is browsing products on the main display shelf, holding a bottle."
            elif "shelf" in prompt_lower or "stock" in prompt_lower:
                return "The shelf is mostly stocked, but the front row of beverages is running low."
            elif "queue" in prompt_lower or "checkout" in prompt_lower:
                return "There are two customers in the checkout zone; cashier is actively scanning items."
            return f"[Mock VLM response for prompt: '{prompt}'] The scene shows a typical retail environment with active shoppers."
        
        # Real pipeline execution
        from PIL import Image
        pil_img = Image.fromarray(img)
        # Format prompt according to Llava format
        formatted_prompt = f"USER: <image>\n{prompt}\nASSISTANT:"
        outputs = self.pipe(pil_img, prompt=formatted_prompt, generate_kwargs={"max_new_tokens": 100})
        if outputs and len(outputs) > 0:
            return outputs[0].get("generated_text", "").split("ASSISTANT:")[-1].strip()
        return "No description generated."
