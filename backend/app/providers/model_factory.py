"""The LLM provider seam: real Qwen (DashScope) vs. deterministic mock.

Swapping between them is a single env flag (``USE_MOCK_LLM``) — no code change. Agents call
``get_model()`` at construction time.
"""

from pydantic_ai.models import Model
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.alibaba import AlibabaProvider

from app.core.config import get_settings
from app.providers.mock_data import dispatch_mock, dispatch_mock_stream


def get_model(model_name: str | None = None) -> Model:
    """Construct the LLM for an agent. ``model_name`` overrides the default ``qwen_model``
    (e.g. the ScriptAgent routes to the flagship ``qwen_script_model``); the mock path is
    deterministic and ignores the model id, so offline tests are unaffected by overrides.
    """
    settings = get_settings()
    if settings.use_mock_llm:
        # stream_function lets agent.iter()/node.stream() work in mock mode (the director
        # SSE path); .run() still uses the non-streaming dispatch_mock.
        return FunctionModel(dispatch_mock, stream_function=dispatch_mock_stream)
    return OpenAIChatModel(
        model_name or settings.qwen_model,
        provider=AlibabaProvider(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        ),
        # Qwen3 runs in "thinking mode" by default, which rejects tool_choice=required
        # (used by PydanticAI's structured tool output). Disable it for deterministic
        # structured planning. See docs.qwencloud.com structured-output notes.
        settings=OpenAIChatModelSettings(extra_body={"enable_thinking": False}),
    )
