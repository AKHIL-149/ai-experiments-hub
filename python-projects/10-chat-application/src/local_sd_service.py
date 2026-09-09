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
    # Was stabilityai/stable-diffusion-2-1-base. Confirmed live: that repo
    # now returns HTTP 401 on HuggingFace even fully unauthenticated
    # (Stability AI gated it behind a license-acceptance step at some
    # point after this default was picked) - every fresh install hit a
    # hard failure on first use, not the "downloads ~5GB, 5-10 min" the
    # docs describe. CompVis/stable-diffusion-v1-4 confirmed still
    # publicly downloadable with no auth (HTTP 200, no login/license
    # gate) as of this fix.
    DEFAULT_MODEL_ID = "CompVis/stable-diffusion-v1-4"

    def __init__(self, model_id=None):
        """
        Initialize the local Stable Diffusion service

        Args:
            model_id: HuggingFace model ID (default: SD 1.4, ~4GB, no
                HF login required). Pass a gated model id (e.g. a
                stabilityai/* model) only if HF_TOKEN/HUGGING_FACE_HUB_TOKEN
                is set to a token whose account has accepted that model's
                license - otherwise loading it will fail.
        """
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.pipe = None
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.hf_token = os.getenv('HF_TOKEN') or os.getenv('HUGGING_FACE_HUB_TOKEN')

        print(f"🎨 Local SD Service initializing on device: {self.device}")

    def load_model(self):
        """Load the Stable Diffusion model (downloads ~4GB on first run)"""
        if self.pipe is not None:
            return  # Already loaded

        print(f"📥 Loading Stable Diffusion model: {self.model_id}")
        print("   First run will download ~4GB model (takes 5-10 minutes)")

        try:
            # Load model with optimizations for Apple Silicon (MPS) or CPU
            if self.device == "mps":
                self.pipe = StableDiffusionPipeline.from_pretrained(
                    self.model_id,
                    torch_dtype=torch.float16,
                    token=self.hf_token
                )
                self.pipe = self.pipe.to(self.device)
                # Enable attention slicing for memory efficiency
                self.pipe.enable_attention_slicing()
            else:
                # CPU mode
                self.pipe = StableDiffusionPipeline.from_pretrained(
                    self.model_id,
                    torch_dtype=torch.float32,
                    token=self.hf_token
                )
                self.pipe = self.pipe.to(self.device)

            print("✅ Model loaded successfully!")
            return True

        except Exception as e:
            # Surface the actual actionable cause instead of dumping the
            # library's raw wall of text - "401"/"gated"/"access to this
            # model" all show up in huggingface_hub's error message when
            # a model requires a logged-in, license-accepted account.
            error_text = str(e)
            if '401' in error_text or 'gated' in error_text.lower() or 'access to model' in error_text.lower():
                print(
                    f"❌ '{self.model_id}' requires a HuggingFace account that has "
                    "accepted its license. Set HF_TOKEN in .env to a token from "
                    "such an account, or use a non-gated model (the default, "
                    f"{self.DEFAULT_MODEL_ID}, doesn't require this)."
                )
            else:
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
