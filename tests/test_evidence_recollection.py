from autoairtest.verification.evidence_recollection import EvidenceRecollector


class FakePoco:
    def __init__(self):
        self.dumps = 0

    def dump(self):
        self.dumps += 1
        return {"status": "success", "visible_texts": ["A", "B"]}


class FakeAirtest:
    def __init__(self):
        self.snapshots = []

    def snapshot(self, filename):
        self.snapshots.append(filename)
        return {"status": "success", "filename": filename}


class FakeOCR:
    def recognize(self, image_path):
        return {"status": "success", "image_path": image_path, "texts": ["A", "B"]}


def test_evidence_recollector_refreshes_current_screen_evidence(tmp_path):
    recollector = EvidenceRecollector(poco=FakePoco(), airtest=FakeAirtest(), ocr=FakeOCR(), max_attempts=2)

    result = recollector.recollect(goal_id="v1", case_dir=tmp_path, attempt=1)

    assert result["status"] == "collected"
    assert result["action"] == "refresh_current_screen_evidence"
    assert (tmp_path / result["screenshot"]).exists() is False
    assert result["poco"]["visible_texts"] == ["A", "B"]
    assert result["ocr"]["texts"] == ["A", "B"]


def test_evidence_recollector_second_attempt_marks_visibility_adjustment(tmp_path):
    recollector = EvidenceRecollector(poco=FakePoco(), airtest=FakeAirtest(), ocr=FakeOCR(), max_attempts=2)

    result = recollector.recollect(goal_id="v1", case_dir=tmp_path, attempt=2)

    assert result["status"] == "collected"
    assert result["action"] == "visibility_adjustment"
    assert result["action_risk_level"] == "low"


def test_evidence_recollector_respects_budget(tmp_path):
    poco = FakePoco()
    recollector = EvidenceRecollector(poco=poco, airtest=FakeAirtest(), ocr=FakeOCR(), max_attempts=2)

    result = recollector.recollect(goal_id="v1", case_dir=tmp_path, attempt=3)

    assert result == {"status": "budget_exhausted", "attempt": 3, "max_attempts": 2}
    assert poco.dumps == 0
