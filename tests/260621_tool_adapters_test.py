from autoairtest.tools.airtest_adapter import AirtestAdapter
from autoairtest.tools.ocr_adapter import OCRAdapter
from autoairtest.tools.poco_adapter import PocoAdapter


def test_airtest_adapter_uses_injected_api(tmp_path):
    calls = []

    class FakeApi:
        def connect_device(self, uri):
            calls.append(("connect", uri))
            return {"device": "ok"}

        def start_app(self, package, activity=None):
            calls.append(("start_app", package, activity))

        def snapshot(self, filename):
            calls.append(("snapshot", filename))
            tmp_path.joinpath("screen.png").write_bytes(b"png")

        def touch(self, target):
            calls.append(("touch", target))

        def swipe(self, start, end):
            calls.append(("swipe", start, end))

        def text(self, value):
            calls.append(("text", value))

        def keyevent(self, key):
            calls.append(("keyevent", key))

    adapter = AirtestAdapter(api=FakeApi(), device_uri="Android:///ABC123")

    assert adapter.connect()["status"] == "connected"
    assert adapter.start_app("com.example", ".Main")["status"] == "success"
    assert adapter.snapshot(str(tmp_path / "screen.png"))["status"] == "success"
    assert adapter.touch((10, 20))["status"] == "success"
    assert adapter.swipe((0, 0), (1, 1))["status"] == "success"
    assert adapter.text("600519")["status"] == "success"
    assert adapter.keyevent("BACK")["status"] == "success"
    assert calls[0] == ("connect", "Android:///ABC123")


def test_poco_adapter_normalizes_dump_and_clicks_injected_poco():
    clicked = []

    class FakeNode:
        def __init__(self, text):
            self._text = text

        def get_text(self):
            return self._text

        def get_bounds(self):
            return [0, 0, 10, 10]

        def attr(self, name):
            return {"name": "market-tab"}.get(name)

        def click(self):
            clicked.append(self._text)

    class FakeSelector:
        def __init__(self, nodes):
            self.nodes = nodes

        def __iter__(self):
            return iter(self.nodes)

        def click(self):
            self.nodes[0].click()

    class FakeHierarchy:
        def dump(self):
            return {"children": [{"payload": {"text": "行情"}, "children": [{"payload": {"text": "更多"}}]}]}

    class FakePoco:
        def agent(self):
            return self

        def hierarchy(self):
            return FakeHierarchy()

        def __call__(self, text=None, **kwargs):
            return FakeSelector([FakeNode(text or "行情")])

    adapter = PocoAdapter(poco=FakePoco())

    assert adapter.dump()["visible_texts"] == ["行情", "更多"]
    assert adapter.click("行情")["status"] == "success"
    assert clicked == ["行情"]


def test_ocr_adapter_keeps_unavailable_without_engine(tmp_path):
    result = OCRAdapter(engine=None).recognize(str(tmp_path / "missing.png"))

    assert result["status"] == "unavailable"
    assert result["texts"] == []


def test_ocr_adapter_normalizes_injected_engine_result(tmp_path):
    class FakeEngine:
        def recognize(self, image_path):
            return [("行情", [0, 0, 20, 10])]

    result = OCRAdapter(engine=FakeEngine()).recognize(str(tmp_path / "screen.png"))

    assert result["status"] == "success"
    assert result["texts"] == [{"text": "行情", "bounds": [0, 0, 20, 10]}]
