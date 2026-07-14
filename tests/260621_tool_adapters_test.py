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


def test_poco_adapter_clicks_short_resource_id_with_configured_package():
    selected_names = []

    class FakeNode:
        def click(self):
            return None

        def get_text(self):
            return ""

        def get_bounds(self):
            return [0, 0, 10, 10]

        def attr(self, name):
            return {"name": selected_names[-1]}.get(name)

    class FakeSelector:
        def __iter__(self):
            return iter([FakeNode()])

        def click(self):
            return None

    class FakePoco:
        def __call__(self, name=None, **kwargs):
            selected_names.append(name)
            return FakeSelector()

    adapter = PocoAdapter(poco=FakePoco(), app_package="com.example.securities")

    result = adapter.click_resource_id("id/backButton")

    assert result["status"] == "success"
    assert result["query"] == "com.example.securities:id/backButton"
    assert selected_names == ["com.example.securities:id/backButton"]


def test_poco_adapter_keeps_fully_qualified_resource_id_unchanged():
    selected_names = []

    class FakeSelector:
        def __iter__(self):
            return iter([self])

        def click(self):
            return None

        def get_text(self):
            return ""

        def get_bounds(self):
            return [0, 0, 10, 10]

        def attr(self, name):
            return None

    class FakePoco:
        def __call__(self, name=None, **kwargs):
            selected_names.append(name)
            return FakeSelector()

    adapter = PocoAdapter(poco=FakePoco())

    result = adapter.click_resource_id("com.vendor.app:id/backButton")

    assert result["status"] == "success"
    assert selected_names == ["com.vendor.app:id/backButton"]


def test_poco_adapter_reports_missing_package_for_short_resource_id():
    adapter = PocoAdapter(poco=object())

    result = adapter.click_resource_id("id/backButton")

    assert result["status"] == "unavailable"
    assert result["reason"] == "app package is required for short resource_id"


def test_poco_adapter_accepts_bare_resource_id_name():
    selected_names = []

    class FakeSelector:
        def __iter__(self):
            return iter([self])

        def click(self):
            return None

        def get_text(self):
            return ""

        def get_bounds(self):
            return [0, 0, 10, 10]

        def attr(self, name):
            return None

    class FakePoco:
        def __call__(self, name=None, **kwargs):
            selected_names.append(name)
            return FakeSelector()

    adapter = PocoAdapter(poco=FakePoco(), app_package="com.example.securities")

    result = adapter.click_resource_id("backButton")

    assert result["status"] == "success"
    assert selected_names == ["com.example.securities:id/backButton"]


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
