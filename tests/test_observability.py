from observability.events import CORPUS_FETCH_START, GT_PIPELINE_COMPLETE


def test_event_constants_are_stable():
    assert CORPUS_FETCH_START == "corpus.fetch.start"
    assert GT_PIPELINE_COMPLETE == "ground_truth.pipeline.complete"
