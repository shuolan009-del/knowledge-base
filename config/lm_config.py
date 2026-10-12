# knowledge_base\config\lm_config.py

from dataclasses import dataclass
import os
from typing import TypeVar

from dotenv import load_dotenv

load_dotenv()

T = TypeVar("T")



@dataclass
class LLMConfig:
    base_url: str
    api_key : str
    vl_model: str
    llm_model: str
    llm_temperature: float
    item_model: T

lm_config = LLMConfig(
    base_url=os.getenv("OPENAI_API_BASE", ""),
    api_key=os.getenv("OPENAI_API_KEY", ""),
    vl_model=os.getenv("VL_MODEL", ""),
    llm_model=os.getenv("LLM_DEFAULT_MODEL", ""),
    llm_temperature=float(os.getenv("LLM_DEFAULT_TEMPERATURE", "0.7"))
    ,item_model=os.getenv("ITEM_MODEL")
)

