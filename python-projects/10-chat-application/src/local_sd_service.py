"""
Local Stable Diffusion Service using diffusers library
Simple alternative to Stable Diffusion WebUI
"""

import torch
from diffusers import StableDiffusionPipeline
import os
from pathlib import Path
import base64
from io import BytesIO

class LocalSDService:
    def __init__(self, model_id="stabilityai/stable-diffusion-2-1-base"):
        """
        Initialize the local Stable Diffusion service

        Args:
            model_id: HuggingFace model ID (default: SD 2.1 base, ~5GB)
        """
        self.model_id = model_id
        self.pipe = None
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"

        print(f"🎨 Local SD Service initializing on device: {self.device}")

    def load_model(self):
        """Load the Stable Diffusion model (downloads ~5GB on first run)"""
        if self.pipe is not None:
            return  # Already loaded

        print(f"📥 Loading Stable Diffusion model: {self.model_id}")
        print("   First run will download ~5GB model (takes 5-10 minutes)")

        try:
            # Load model with optimizations for Apple Silicon (MPS) or CPU
            if self.device == "mps":
                self.pipe = StableDiffusionPipeline.from_pretrained(
                    self.model_id,
                    torch_dtype=torch.float16,
                    variant="fp16"
                )
                self.pipe = self.pipe.to(self.device)
                # Enable attention slicing for memory efficiency
                self.pipe.enable_attention_slicing()
            else:
                # CPU mode
                self.pipe = StableDiffusionPipeline.from_pretrained(
                    self.model_id,
                    torch_dtype=torch.float32
                )
                self.pipe = self.pipe.to(self.device)

            print("✅ Model loaded successfully!")
            return True

        except Exception as e:
            print(f"❌ Failed to load model: {e}")
            return False

    def generate_image(self, prompt, width=512, height=512, steps=20):
        """
        Generate an image from a text prompt

        Args:
            prompt: Text description of the image
            width: Image width (default 512)
            height: Image height (default 512)
            steps: Number of inference steps (default 20, range 10-50)

        Returns:
            PIL Image object
        """
        if self.pipe is None:
            success = self.load_model()
            if not success:
                raise RuntimeError("Failed to load Stable Diffusion model")

        print(f"🎨 Generating image: '{prompt[:50]}...'")

        # Generate image
        with torch.inference_mode():
            result = self.pipe(
                prompt=prompt,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=7.5
            )

        image = result.images[0]
        print("✅ Image generated!")

        return image

    def is_available(self):
        """Check if the service is available"""
        try:
            import torch
            from diffusers import StableDiffusionPipeline
            return True
        except ImportError:
            return False

    def get_info(self):
        """Get service information"""
        return {
            "model": self.model_id,
            "device": self.device,
            "loaded": self.pipe is not None,
            "available": self.is_available()
        }


# Global instance (lazy loaded)
_service = None

def get_service():
    """Get or create the global SD service instance"""
    global _service
    if _service is None:
        _service = LocalSDService()
    return _service
