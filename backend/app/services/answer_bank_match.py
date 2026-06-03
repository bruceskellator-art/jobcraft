"""Answer bank similarity matching service.

APPROVED-ONLY SAFETY RULE
--------------------------
find_similar_answer MUST NEVER return an unapproved answer.

Two guards enforce this:
1. index_approved_answer only indexes answers whose approved flag is True
   at call time. The payload carries approved=True to make the intent
   explicit in stored metadata.
2. find_similar_answer fetches the live AnswerBank row from the database
   after a vector search and re-checks answer.approved before returning.
   This prevents stale index entries from surfacing answers that were
   later de-approved.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.answer_bank import AnswerBank
from app.embeddings.base import EmbeddingClient
from app.repositories.answer_bank import AnswerBankRepository
from app.services.embed_pipeline import COLLECTION_ANSWER_BANK
from app.vectorstore.base import VectorPoint, VectorStore


async def index_approved_answer(
    embed: EmbeddingClient,
    store: VectorStore,
    answer: AnswerBank,
) -> None:
    """Embed the question text and upsert the point into the answer bank collection.

    Only call this for approved answers. The payload records approved=True
    and both user_id and answer_id so the vector can be filtered and
    resolved back to the database row on lookup.
    """
    await store.ensure_collection(COLLECTION_ANSWER_BANK, embed.dim)

    vectors = await embed.embed([answer.question])
    point = VectorPoint(
        id=str(answer.id),
        vector=vectors[0],
        payload={
            "user_id": str(answer.user_id),
            "answer_id": str(answer.id),
            "approved": True,
        },
    )
    await store.upsert(COLLECTION_ANSWER_BANK, [point])


async def find_similar_answer(
    session: AsyncSession,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    question: str,
    *,
    threshold: float = 0.85,
) -> AnswerBank | None:
    """Return the best approved answer for a similar question, or None.

    Steps:
    1. Embed the incoming question.
    2. Search the answer bank collection filtered to this user.
    3. Take the top result.  If its cosine score is below threshold → None.
    4. Re-fetch the live database row and re-verify answer.approved.
       This double-check ensures that answers de-approved after indexing
       are never surfaced (the approved-only safety rule).

    Returns None when no similar approved answer is found or when the
    threshold is not met.
    """
    await store.ensure_collection(COLLECTION_ANSWER_BANK, embed.dim)

    vectors = await embed.embed([question])
    results = await store.search(
        COLLECTION_ANSWER_BANK,
        vectors[0],
        top_k=1,
        payload_filter={"user_id": str(user_id)},
    )

    if not results:
        return None

    best = results[0]
    if best.score < threshold:
        return None

    answer_id_str = best.payload.get("answer_id")
    if answer_id_str is None:
        return None

    repo = AnswerBankRepository(session)
    answer = await repo.get(uuid.UUID(answer_id_str))

    # Re-verify approval status from the live row (approved-only safety rule).
    if answer is None or not answer.approved:
        return None

    return answer
