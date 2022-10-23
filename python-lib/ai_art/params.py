from __future__ import annotations

import abc
import dataclasses
import logging
import pathlib
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import torch

from ai_art.constants import HUGGING_FACE_BASE_URL
from ai_art.folder import get_file_path_or_temp
from ai_art.image import open_base_image, resize_image

if TYPE_CHECKING:
    import tempfile
    from typing import Optional

    import dataiku
    import PIL.Image


def resolve_model_repo(config):
    """Resolve the model_repo param to an absolute URL

    :param config: Recipe config
    :type config: Mapping[str, Any]

    :raises ValueError: `model_repo` is set to "CUSTOM", but
        `custom_model_repo` isn't defined

    :return: URL of the model repo
    :rtype: str
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

    weights_folder: dataiku.Folder
    weights_path: pathlib.Path
    temp_weights_dir: Optional[tempfile.TemporaryDirectory]
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
    random_seed: Optional[int]
    num_inference_steps: int
    guidance_scale: float

    @classmethod
    def from_config(cls, recipe_config, weights_folder, image_folder):
        """Create a params instance from the recipe config

        :param recipe_config: Recipe config
        :type recipe_config: Mapping[str, Any]
        :param weights_folder: Input weights_folder
        :type weights_folder: dataiku.Folder
        :param image_folder: Output image_folder
        :type image_folder: dataiku.Folder

        Subclasses should override this class only if they add
        additional input/output roles

        :return: Created params instance
        :rtype: Self
        """
        kwargs = cls._init_kwargs_from_config(
            recipe_config, weights_folder, image_folder
        )
        return cls(**kwargs)

    @staticmethod
    def _init_kwargs_from_config(recipe_config, weights_folder, image_folder):
        """Create the kwargs used by `from_config` to init the instance

        :param recipe_config: Recipe config
        :type recipe_config: Mapping[str, Any]
        :param weights_folder: Input weights_folder
        :type weights_folder: dataiku.Folder
        :param image_folder: Output image_folder
        :type image_folder: dataiku.Folder

        Subclasses should override this method if they add new
        parameters. Be sure to call the parent method

        :return: kwargs that will be passed to `__init__()`
        :rtype: dict[str, Any]
        """
        logging.info("Recipe config: %r", recipe_config)
        logging.info("Weights folder: %r", weights_folder.name)
        logging.info("Image folder: %r", image_folder.name)

        weights_path, temp_weights_dir = get_file_path_or_temp(weights_folder)

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

        random_seed = recipe_config.get("random_seed")
        if random_seed:
            random_seed = int(random_seed)
        else:
            # Set random_seed to `None` if the value is `0`
            random_seed = None

        return {
            "weights_folder": weights_folder,
            "weights_path": pathlib.Path(weights_path),
            "temp_weights_dir": temp_weights_dir,
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
            "random_seed": random_seed,
            "num_inference_steps": int(recipe_config["num_inference_steps"]),
            "guidance_scale": recipe_config["guidance_scale"],
        }


@dataclasses.dataclass
class TextToImageParams(_BaseParams):
    """Params used by the Text-to-Image recipe"""

    image_height: int
    image_width: int

    @classmethod
    def _init_kwargs_from_config(
        cls, recipe_config, weights_folder, image_folder
    ):
        # Get the shared kwargs from the parent class
        kwargs = super()._init_kwargs_from_config(
            recipe_config, weights_folder, image_folder
        )

        additional_kwargs = {
            "image_height": int(recipe_config["image_height"]),
            "image_width": int(recipe_config["image_width"]),
        }
        kwargs.update(additional_kwargs)

        return kwargs


@dataclasses.dataclass
class TextGuidedImageToImageParams(_BaseParams):
    """Params used by the Text-Guided Image-to-Image recipe"""

    base_image: PIL.Image.Image
    strength: float

    @classmethod
    def from_config(
        cls,
        recipe_config,
        weights_folder,
        image_folder,
        base_image_folder,
    ):
        """
        :param base_image_folder: Input base_image_folder
        :type base_image_folder: dataiku.Folder
        """
        kwargs = cls._init_kwargs_from_config(
            recipe_config,
            weights_folder,
            image_folder,
            base_image_folder,
        )
        return cls(**kwargs)

    @classmethod
    def _init_kwargs_from_config(
        cls,
        recipe_config,
        weights_folder,
        image_folder,
        base_image_folder,
    ):
        # Get the shared kwargs from the parent class
        kwargs = super()._init_kwargs_from_config(
            recipe_config, weights_folder, image_folder
        )

        logging.info("Base image folder: %r", base_image_folder.name)

        base_image_path = recipe_config["base_image_path"]
        logging.info("Opening base image: %r", base_image_path)
        base_image = open_base_image(base_image_folder, base_image_path)

        # The Hugging Face models work best with 512x512 images, as
        # described in this article:
        # https://huggingface.co/blog/stable_diffusion
        if recipe_config["resize_base_image"]:
            base_image = resize_image(base_image, min_size=512)

        additional_kwargs = {
            "base_image": base_image,
            "strength": recipe_config["strength"],
        }
        kwargs.update(additional_kwargs)

        return kwargs
