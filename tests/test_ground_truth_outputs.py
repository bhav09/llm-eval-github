import json
from pathlib import Path

from ground_truth.pipeline import write_ground_truth_outputs


def test_write_ground_truth_outputs_serializes_datetimes(tmp_path: Path, sample_issue):
    from ground_truth.pipeline import GroundTruthRecord, run_pipeline
    from ground_truth.adjudicator import MockAdjudicator

    result = run_pipeline([sample_issue], adjudicator=MockAdjudicator())
    write_ground_truth_outputs(tmp_path, result)
    assert (tmp_path / "labels.json").exists()
    assert (tmp_path / "ambiguous_queue.json").exists()
    queue = json.loads((tmp_path / "ambiguous_queue.json").read_text(encoding="utf-8"))
    assert isinstance(queue, list)
