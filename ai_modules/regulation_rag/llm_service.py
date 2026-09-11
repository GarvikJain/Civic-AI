"""Groq LLM service for grounded regulation answers.

The API key is read from configuration and never hard-coded. Only the citizen's
question and the retrieved regulation text are sent to Groq; no account data,
passwords or tokens are included.
"""

from ai_modules.regulation_rag.errors import LlmUnavailableError
from ai_modules.regulation_rag.reranker import RankedChunk

# The model writes this exact word when the context does not answer the
# question, which the pipeline turns into the insufficient-evidence reply.
INSUFFICIENT_MARKER = "INSUFFICIENT_EVIDENCE"

SYSTEM_PROMPT = f"""You are CivicAI, an assistant that answers citizens' \
questions about government regulations.

Follow these rules exactly:
1. Answer ONLY from the regulation context provided in the user message.
2. Never use outside knowledge, and never guess.
3. Never invent eligibility criteria, required documents, deadlines or fees.
4. Cite the scheme, circular reference and section you used, exactly as they \
appear in the context. Never invent a citation.
5. If the context does not contain the answer, reply with exactly \
{INSUFFICIENT_MARKER} and nothing else.
6. Keep the answer short, factual and easy for a citizen to understand.
"""

# Guard against sending an unreasonable amount of text to the LLM.
MAX_CHARS_PER_CHUNK = 1500


def _describe_source(metadata: dict) -> str:
    """A readable label for one evidence block, using only real metadata."""
    parts = []
    if metadata.get("scheme_name"):
        parts.append(f"Scheme: {metadata['scheme_name']}")
    if metadata.get("circular_reference"):
        parts.append(f"Circular: {metadata['circular_reference']}")
    if metadata.get("section"):
        parts.append(f"Section: {metadata['section']}")
    if metadata.get("source"):
        parts.append(f"Document: {metadata['source']}")
    return " | ".join(parts) if parts else "Unlabelled regulation extract"


def build_user_prompt(
    query: str, evidence: list[RankedChunk], graph_context: list[str]
) -> str:
    """Assemble the question, the regulation extracts and the graph facts."""
    blocks = []
    for position, ranked in enumerate(evidence, start=1):
        text = ranked.chunk.text[:MAX_CHARS_PER_CHUNK]
        blocks.append(
            f"[{position}] {_describe_source(ranked.chunk.metadata)}\n{text}"
        )

    sections = [f"Citizen question:\n{query}", "Regulation context:\n" + "\n\n".join(blocks)]
    if graph_context:
        sections.append(
            "Known relationships from the regulation knowledge graph:\n"
            + "\n".join(f"- {line}" for line in graph_context)
        )
    sections.append(
        "Answer the question using only the context above, and cite the "
        f"scheme, circular and section you used. If the context is not enough, "
        f"reply with exactly {INSUFFICIENT_MARKER}."
    )
    return "\n\n".join(sections)


class GroqLlmService:
    """Generates the final answer with Groq.

    Pass `client` to inject an already built client, or a stand-in for tests.
    """

    def __init__(self, api_key: str, model: str, client=None) -> None:
        self._api_key = api_key
        self.model = model
        self._client = client

    @property
    def client(self):
        """The Groq client, created on first use."""
        if self._client is None:
            if not self._api_key:
                raise LlmUnavailableError(
                    "GROQ_API_KEY is not configured. Add it to your .env file."
                )
            try:
                from groq import Groq
            except ImportError as error:
                raise LlmUnavailableError(
                    "The groq package is not installed. "
                    "Install it with: pip install -r requirements.txt"
                ) from error

            self._client = Groq(api_key=self._api_key)
        return self._client

    def generate_answer(
        self, query: str, evidence: list[RankedChunk], graph_context: list[str]
    ) -> str:
        """Ask Groq for an answer grounded in the evidence."""
        if not evidence:
            raise ValueError("generate_answer needs at least one evidence chunk")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_user_prompt(query, evidence, graph_context),
            },
        ]

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                # Low temperature keeps the answer close to the source text.
                temperature=0.1,
            )
        except Exception as error:
            # The error text is not shown to the citizen, so no key can leak.
            raise LlmUnavailableError(f"Groq request failed: {type(error).__name__}") from error

        return (completion.choices[0].message.content or "").strip()
