"""The LLM provider seam: real Qwen (DashScope) vs. deterministic mock.

Swapping between them is a single env flag (``USE_MOCK_LLM``) — no code change. Agents call
``get_model()`` at construction time.
"""

from pydantic_ai.models import Model
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.alibaba import AlibabaProvider

from app.core.config import get_settings
from app.providers.mock_data import dispatch_mock


def get_model() -> Model:
    settings = get_settings()
    if settings.use_mock_llm:
        return FunctionModel(dispatch_mock)
    return OpenAIChatModel(
        settings.qwen_model,
        provider=AlibabaProvider(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        ),
        # Qwen3 runs in "thinking mode" by default, which rejects tool_choice=required
        # (used by PydanticAI's structured tool output). Disable it for deterministic
        # structured planning. See docs.qwencloud.com structured-output notes.
        settings=OpenAIChatModelSettings(extra_body={"enable_thinking": False}),
    )
