from __future__ import annotations

import abc
import dataclasses
import logging
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import dataiku
import PIL.Image
import torch

from ai_art.constants import HUGGING_FACE_BASE_URL

if TYPE_CHECKING:
    from typing import Optional


def resolve_model_repo(config):
    """Resolve the model_repo param to an absolute URL

    config (mapping): Config params of the recipe

    Returns the URL of the model repo
    """
    model_repo_path = config["model_repo"]
    if model_repo_path == "CUSTOM":
        model_repo_path = config.get("custom_model_repo")
        if not model_repo_path:
            raise ValueError("undefined parameter: Custom model repo")

    model_repo = urljoin(HUGGING_FACE_BASE_URL, model_repo_path)
    return model_repo


@dataclasses.dataclass
class _BaseParams(abc.ABC):
    """Base params class that defines the shared params"""

    weights_path: str
    image_folder: dataiku.Folder
    prompt: str
    image_count: int
    batch_size: int
    filename_prefix: str
    device_id: Optional[str]
    clear_folder: bool
    use_autocast: bool
    torch_dtype: Optional[torch.dtype]
    enable_attention_slicing: bool
    num_inference_steps: int
    guidance_scale: float

    @classmethod
    def from_config(
        cls, recipe_config, weights_folder_name, image_folder_name
    ):
        kwargs = cls._init_kwargs_from_config(
            recipe_config, weights_folder_name, image_folder_name
        )
        return cls(**kwargs)

    @staticmethod
    def _init_kwargs_from_config(
        recipe_config, weights_folder_name, image_folder_name
    ):
        logging.info("Recipe config: %r", recipe_config)
        logging.info("Weights folder: %r", weights_folder_name)
        logging.info("Image folder: %r", image_folder_name)

        weights_folder = dataiku.Folder(weights_folder_name)
        image_folder = dataiku.Folder(image_folder_name)

        # TODO: figure out if there's a better way to store the weights.
        # The current method only works if the folder is on the local
        # FS.
        # https://huggingface.co/docs/diffusers/v0.3.0/en/api/diffusion_pipeline#diffusers.DiffusionPipeline.from_pretrained
        weights_path = weights_folder.get_path()

        device = recipe_config["device"]
        if device == "auto":
            device_id = None
        else:
            device_id = device

        use_half_precision = recipe_config["use_half_precision"]
        if use_half_precision:
            torch_dtype = torch.float16
        else:
            # Use the default dtype of the model (float32)
            torch_dtype = None

        return {
            "weights_path": weights_path,
            "image_folder": image_folder,
            "prompt": recipe_config["prompt"],
            "image_count": int(recipe_config["image_count"]),
            "batch_size": int(recipe_config["batch_size"]),
            "filename_prefix": recipe_config["filename_prefix"],
            "device_id": device_id,
            "clear_folder": recipe_config["clear_folder"],
            "use_autocast": recipe_config["use_autocast"],
            "torch_dtype": torch_dtype,
            "enable_attention_slicing": recipe_config[
                "enable_attention_slicing"
            ],
            "num_inference_steps": int(recipe_config["num_inference_steps"]),
            "guidance_scale": recipe_config["guidance_scale"],
        }


@dataclasses.dataclass
class TextToImageParams(_BaseParams):
    image_height: int
    image_width: int

    @classmethod
    def _init_kwargs_from_config(
        cls, recipe_config, weights_folder_name, image_folder_name
    ):
        # Get the shared kwargs from the parent class
        kwargs = super()._init_kwargs_from_config(
            recipe_config, weights_folder_name, image_folder_name
        )

        additional_kwargs = {
            "image_height": int(recipe_config["image_height"]),
            "image_width": int(recipe_config["image_width"]),
        }
        kwargs.update(additional_kwargs)

        return kwargs


@dataclasses.dataclass
class TextGuidedImageToImageParams(_BaseParams):
    base_image: PIL.Image.Image
    strength: float

    @classmethod
    def from_config(
        cls,
        recipe_config,
        weights_folder_name,
        image_folder_name,
        base_image_folder_name,
    ):
        kwargs = cls._init_kwargs_from_config(
            recipe_config,
            weights_folder_name,
            image_folder_name,
            base_image_folder_name,
        )
        return cls(**kwargs)

    @classmethod
    def _init_kwargs_from_config(
        cls,
        recipe_config,
        weights_folder_name,
        image_folder_name,
        base_image_folder_name,
    ):
        # Get the shared kwargs from the parent class
        kwargs = super()._init_kwargs_from_config(
            recipe_config, weights_folder_name, image_folder_name
        )

        logging.info("Base image folder: %r", base_image_folder_name)
        base_image_folder = dataiku.Folder(base_image_folder_name)

        base_image_path = recipe_config["base_image_path"]
        logging.info("Opening base image: %r", base_image_path)
        base_image = cls._open_base_image(base_image_folder, base_image_path)

        additional_kwargs = {
            "base_image": base_image,
            "strength": recipe_config["strength"],
        }
        kwargs.update(additional_kwargs)

        return kwargs

    @staticmethod
    def _open_base_image(folder, image_path):
        """Open image from a Dataiku folder to use with Stable Diffusion

        Returns a PIL image
        """
        with folder.get_download_stream(image_path) as file:
            image = PIL.Image.open(file)

        # Convert the image to RGB per the Diffusers documentation
        # https://huggingface.co/docs/diffusers/using-diffusers/img2img
        if image.mode != "RGB":
            image = image.convert("RGB")

        return image
