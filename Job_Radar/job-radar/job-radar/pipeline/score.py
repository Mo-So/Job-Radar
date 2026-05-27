"""Compute fit % between the master CV and each job description.

Uses `sentence-transformers/all-MiniLM-L6-v2`: 22M params, ~90MB, CPU-friendly.
Free and runs entirely inside the GitHub Actions runner. The model is cached
between runs so cold-start cost is paid once.

Cosine similarity on normalized embeddings sits roughly in [0.1, 0.7] for
this kind of CV-vs-job comparison. We linearly stretch [0.10, 0.65] -> [0, 100]
so the score lines up with intuitive ranking — a 0 means "essentially
unrelated", an 85+ means "very strong semantic overlap".
"""

from typing import List
from sentence_transformers import SentenceTransformer, util

from pipeline.normalize import Job

_MODEL = None
_RAW_MIN = 0.10  # below this we call it 0
_RAW_MAX = 0.65  # at this and above we call it 100


def _load_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _MODEL


def _rescale(cos_sim: float) -> float:
    """Map cosine similarity to a 0-100 fit score."""
    if cos_sim <= _RAW_MIN:
        return 0.0
    if cos_sim >= _RAW_MAX:
        return 100.0
    return round((cos_sim - _RAW_MIN) / (_RAW_MAX - _RAW_MIN) * 100, 1)


def score_jobs(cv_text: str, jobs: List[Job]) -> List[Job]:
    """Set `fit_score` on each Job (0-100) and sort in-place by score desc."""
    if not jobs:
        return jobs

    model = _load_model()

    # Combine title + first 2000 chars of description for matching.
    job_texts = [f"{j.title}. {j.description[:2000]}" for j in jobs]

    cv_emb = model.encode(cv_text, convert_to_tensor=True, normalize_embeddings=True)
    job_embs = model.encode(
        job_texts,
        convert_to_tensor=True,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    )

    sims = util.cos_sim(cv_emb, job_embs).squeeze(0).cpu().tolist()
    for job, s in zip(jobs, sims):
        job.fit_score = _rescale(s)

    jobs.sort(key=lambda j: j.fit_score, reverse=True)
    return jobs
