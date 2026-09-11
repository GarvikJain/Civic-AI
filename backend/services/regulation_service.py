"""Business logic for the Regulation RAG Assistant.

Will call ai_modules.regulation_rag once that module is built.
"""

from backend.schemas.common import MessageResponse


def get_status() -> MessageResponse:
    return MessageResponse(
        module="Regulation RAG Assistant",
        status="not_implemented",
        message="Retrieval, reranking and LLM answering will be added later.",
    )
