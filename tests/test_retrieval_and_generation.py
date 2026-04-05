from backend.rag.generator import ComplianceGenerator, GenerationContext
from backend.rag.retriever import ComplianceRetriever, RetrievalResult


class _StubVectorStore:
    def query_naac_requirements(self, query_text: str, n_results: int = 5, criterion_filter: str | None = None):
        return {
            "documents": [
                "Criterion 2 expects course outcomes and program outcomes to be documented clearly.",
                "The institution should maintain curriculum and syllabus updates for audit review.",
                "Departments must track offered courses across the review period.",
            ],
            "metadatas": [
                {"source_file": "naac.pdf", "section_header": "Criterion 2", "criterion": "2"},
                {"source_file": "naac.pdf", "section_header": "Curriculum", "criterion": "1"},
                {"source_file": "naac.pdf", "section_header": "Courses", "criterion": "1"},
            ],
            "distances": [0.41, 0.46, 0.49],
        }

    def query_mvsr_evidence(self, query_text: str, n_results: int = 5, category_filter: str | None = None):
        return {
            "documents": [
                "MVSR offered multiple undergraduate and postgraduate courses during the review period.",
                "Course-wise intake is documented in the SSR tables.",
            ],
            "metadatas": [
                {"source_file": "mvsr.pdf", "section_header": "Courses Offered", "document_title": "MVSR SSR"},
                {"source_file": "mvsr.pdf", "section_header": "Intake", "document_title": "MVSR SSR"},
            ],
            "distances": [0.45, 0.48],
        }


class _StubLLMClient:
    def generate_compliance_response(self, *args, **kwargs):
        raise AssertionError("LLM should not be called when no context is available")


def test_retriever_preserves_top_candidates_when_threshold_filters_everything():
    retriever = ComplianceRetriever(
        chroma_store=_StubVectorStore(),
        similarity_threshold=0.95,
    )

    naac_results, mvsr_results = retriever.retrieve_compliance_context(
        "How many courses were offered?"
    )

    assert naac_results.used_threshold_fallback is True
    assert mvsr_results.used_threshold_fallback is True
    assert len(naac_results.documents) == 3
    assert len(mvsr_results.documents) == 2
    assert naac_results.retrieval_notes
    assert "No results met the configured similarity threshold" in naac_results.retrieval_notes[0]


def test_generator_returns_deterministic_empty_context_response_without_llm():
    generator = ComplianceGenerator(llm_client=_StubLLMClient())
    context = GenerationContext(
        user_query="How many courses were offered?",
        naac_results=RetrievalResult([], [], [], "naac_requirement"),
        mvsr_results=RetrievalResult([], [], [], "mvsr_evidence"),
        additional_context={"debug_trace_id": ""},
    )

    response = generator.generate_compliance_response(context)

    assert response["status"] == "Insufficient Evidence"
    assert response["query_processed"] is False
    assert "no usable chunks were selected" in response["compliance_analysis"].lower()
