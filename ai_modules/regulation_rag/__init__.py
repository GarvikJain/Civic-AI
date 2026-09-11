"""Regulation RAG Assistant (not implemented yet).

Planned pipeline:
1. Split regulation documents into chunks.
2. Embed the chunks with sentence-transformers and store them in ChromaDB.
3. Retrieve candidates for a question and reorder them with a cross-encoder.
4. Expand context using a NetworkX knowledge graph of related regulations.
5. Generate the final answer with the Groq LLM.
"""
