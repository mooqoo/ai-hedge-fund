"""Helper functions for LLM"""

import json
import os
import re
import subprocess
from pydantic import BaseModel
from src.llm.models import get_model, get_model_info
from src.utils.progress import progress
from src.graph.state import AgentState


def call_claude_subagent(
    prompt: any,
    pydantic_model: type[BaseModel],
    agent_name: str | None = None,
    max_retries: int = 3,
    default_factory=None,
) -> BaseModel:
    """
    Makes an LLM call by spawning a Claude subagent via the `claude -p` CLI.
    No LLM API key required — uses the local Claude Code installation.

    Args:
        prompt: A LangChain ChatPromptValue (with .messages), or any stringifiable object
        pydantic_model: The Pydantic model class to structure the output
        agent_name: Optional name for progress updates
        max_retries: Maximum number of retries (default: 3)
        default_factory: Optional factory function to create default response on failure

    Returns:
        An instance of the specified Pydantic model
    """
    # Extract text from a LangChain ChatPromptValue or plain string
    prompt_parts = []
    if hasattr(prompt, "messages"):
        for msg in prompt.messages:
            type_name = type(msg).__name__.replace("Message", "").upper()
            content = msg.content if hasattr(msg, "content") else str(msg)
            prompt_parts.append(f"[{type_name}]\n{content}")
    else:
        prompt_parts.append(str(prompt))

    full_prompt = "\n\n".join(prompt_parts)
    full_prompt += (
        "\n\nIMPORTANT: Respond with ONLY a valid JSON object. "
        "No markdown fences, no explanation, no extra text — just raw JSON."
    )

    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["claude", "-p", full_prompt],
                capture_output=True,
                text=True,
                timeout=120,
                env=os.environ.copy(),
            )

            if result.returncode != 0:
                raise Exception(
                    f"Claude CLI exited {result.returncode}: {result.stderr[:300]}"
                )

            response_text = result.stdout.strip()

            # 1. Try direct JSON parse
            parsed = None
            try:
                parsed = json.loads(response_text)
            except json.JSONDecodeError:
                pass

            # 2. Try extracting from ```json ... ``` block
            if parsed is None:
                parsed = extract_json_from_response(response_text)

            # 3. Last resort: grab the first {...} blob
            if parsed is None:
                match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if match:
                    try:
                        parsed = json.loads(match.group())
                    except json.JSONDecodeError:
                        pass

            if parsed is not None:
                return pydantic_model(**parsed)

            raise Exception(
                f"Could not parse JSON from Claude response: {response_text[:300]}"
            )

        except Exception as e:
            if agent_name:
                progress.update_status(
                    agent_name, None, f"Error - retry {attempt + 1}/{max_retries}"
                )
            print(f"[claude-subagent] attempt {attempt + 1}/{max_retries} failed: {e}")

            if attempt == max_retries - 1:
                print(f"[claude-subagent] all retries exhausted for {agent_name}")
                if default_factory:
                    return default_factory()
                return create_default_response(pydantic_model)

    return create_default_response(pydantic_model)


def call_llm(
    prompt: any,
    pydantic_model: type[BaseModel],
    agent_name: str | None = None,
    state: AgentState | None = None,
    max_retries: int = 3,
    default_factory=None,
) -> BaseModel:
    """
    Makes an LLM call with retry logic, handling both JSON supported and non-JSON supported models.

    Args:
        prompt: The prompt to send to the LLM
        pydantic_model: The Pydantic model class to structure the output
        agent_name: Optional name of the agent for progress updates and model config extraction
        state: Optional state object to extract agent-specific model configuration
        max_retries: Maximum number of retries (default: 3)
        default_factory: Optional factory function to create default response on failure

    Returns:
        An instance of the specified Pydantic model
    """

    # ── Claude subagent short-circuit ──────────────────────────────────────────
    if os.getenv("USE_CLAUDE_SUBAGENT", "").lower() in ("1", "true", "yes"):
        return call_claude_subagent(
            prompt=prompt,
            pydantic_model=pydantic_model,
            agent_name=agent_name,
            max_retries=max_retries,
            default_factory=default_factory,
        )
    # ──────────────────────────────────────────────────────────────────────────

    # Extract model configuration if state is provided and agent_name is available
    if state and agent_name:
        model_name, model_provider = get_agent_model_config(state, agent_name)
    else:
        # Use system defaults when no state or agent_name is provided
        model_name = "gpt-4.1"
        model_provider = "OPENAI"

    # Extract API keys from state if available
    api_keys = None
    if state:
        request = state.get("metadata", {}).get("request")
        if request and hasattr(request, 'api_keys'):
            api_keys = request.api_keys

    model_info = get_model_info(model_name, model_provider)
    llm = get_model(model_name, model_provider, api_keys)

    # For non-JSON support models, we can use structured output
    if not (model_info and not model_info.has_json_mode()):
        llm = llm.with_structured_output(
            pydantic_model,
            method="json_mode",
        )

    # Call the LLM with retries
    for attempt in range(max_retries):
        try:
            # Call the LLM
            result = llm.invoke(prompt)

            # For non-JSON support models, we need to extract and parse the JSON manually
            if model_info and not model_info.has_json_mode():
                parsed_result = extract_json_from_response(result.content)
                if parsed_result:
                    return pydantic_model(**parsed_result)
            else:
                return result

        except Exception as e:
            if agent_name:
                progress.update_status(agent_name, None, f"Error - retry {attempt + 1}/{max_retries}")

            if attempt == max_retries - 1:
                print(f"Error in LLM call after {max_retries} attempts: {e}")
                # Use default_factory if provided, otherwise create a basic default
                if default_factory:
                    return default_factory()
                return create_default_response(pydantic_model)

    # This should never be reached due to the retry logic above
    return create_default_response(pydantic_model)


def create_default_response(model_class: type[BaseModel]) -> BaseModel:
    """Creates a safe default response based on the model's fields."""
    default_values = {}
    for field_name, field in model_class.model_fields.items():
        if field.annotation == str:
            default_values[field_name] = "Error in analysis, using default"
        elif field.annotation == float:
            default_values[field_name] = 0.0
        elif field.annotation == int:
            default_values[field_name] = 0
        elif hasattr(field.annotation, "__origin__") and field.annotation.__origin__ == dict:
            default_values[field_name] = {}
        else:
            # For other types (like Literal), try to use the first allowed value
            if hasattr(field.annotation, "__args__"):
                default_values[field_name] = field.annotation.__args__[0]
            else:
                default_values[field_name] = None

    return model_class(**default_values)


def extract_json_from_response(content: str) -> dict | None:
    """Extracts JSON from markdown-formatted response."""
    try:
        json_start = content.find("```json")
        if json_start != -1:
            json_text = content[json_start + 7 :]  # Skip past ```json
            json_end = json_text.find("```")
            if json_end != -1:
                json_text = json_text[:json_end].strip()
                return json.loads(json_text)
    except Exception as e:
        print(f"Error extracting JSON from response: {e}")
    return None


def get_agent_model_config(state, agent_name):
    """
    Get model configuration for a specific agent from the state.
    Falls back to global model configuration if agent-specific config is not available.
    Always returns valid model_name and model_provider values.
    """
    request = state.get("metadata", {}).get("request")
    
    if request and hasattr(request, 'get_agent_model_config'):
        # Get agent-specific model configuration
        model_name, model_provider = request.get_agent_model_config(agent_name)
        # Ensure we have valid values
        if model_name and model_provider:
            return model_name, model_provider.value if hasattr(model_provider, 'value') else str(model_provider)
    
    # Fall back to global configuration (system defaults)
    model_name = state.get("metadata", {}).get("model_name") or "gpt-4.1"
    model_provider = state.get("metadata", {}).get("model_provider") or "OPENAI"
    
    # Convert enum to string if necessary
    if hasattr(model_provider, 'value'):
        model_provider = model_provider.value
    
    return model_name, model_provider
