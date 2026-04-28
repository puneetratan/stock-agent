"""AWS Bedrock LLM factory — returns cached CrewAI LLM instances per agent role."""

import os
from functools import lru_cache

import yaml
from crewai import LLM


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=10)
def get_llm(agent_name: str) -> LLM:
    """
    Returns the correct Bedrock LLM for each agent via CrewAI's LLM class.
    CrewAI uses LiteLLM under the hood — Bedrock models use the 'bedrock/' prefix.

    Usage:
        haiku  = get_llm("market")        → Claude Haiku
        sonnet = get_llm("fundamentals")  → Claude Sonnet
    """
    config = _load_config()
    model_id = config["models"][agent_name]
    region = os.environ.get("AWS_REGION", "us-east-1")

    # ARNs must use the converse route; plain model IDs use the standard bedrock/ prefix
    if model_id.startswith("arn:"):
        model = f"bedrock/converse/{model_id}"
    elif not model_id.startswith("bedrock/"):
        model = f"bedrock/{model_id}"
    else:
        model = model_id

    return LLM(
        model=model,
        temperature=0.1,
        max_tokens=4096,
        aws_region_name=region,
    )
