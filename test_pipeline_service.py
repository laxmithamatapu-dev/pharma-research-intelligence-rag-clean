import contextlib
import http.client
import io
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

with contextlib.redirect_stdout(io.StringIO()):
    import app
    import serve


class PipelineTests(unittest.TestCase):

    def make_pipeline(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return app.Pipeline(mode="paper_first")

    def test_abstention_skips_generation(self):
        pipeline = self.make_pipeline()
        evidence = mock.Mock(chunks=[], abstained=True, telemetry={"abstained": True})
        with mock.patch.object(app, "retrieve_evidence", return_value=evidence), \
                mock.patch.object(pipeline.generator, "generate") as generate, \
                mock.patch.object(app, "save_debug_run", return_value="artifact.json"), \
                contextlib.redirect_stdout(io.StringIO()):
            result = pipeline.answer("What is the mechanism of action of teprotumumab?")
        generate.assert_not_called()
        self.assertTrue(result["abstained"])
        self.assertEqual(result["answer"], app.ABSTENTION_ANSWER)
        self.assertIsNone(result["error"])

    def test_failure_is_recorded_not_raised(self):
        pipeline = self.make_pipeline()
        with mock.patch.object(app, "retrieve_evidence", side_effect=RuntimeError("chroma unavailable")), \
                mock.patch.object(app, "save_debug_run", return_value="artifact.json") as save, \
                contextlib.redirect_stdout(io.StringIO()):
            result = pipeline.answer("Any question?")
        self.assertEqual(result["error"], "RuntimeError: chroma unavailable")
        self.assertEqual(save.call_args.kwargs["error"], "RuntimeError: chroma unavailable")
        self.assertIsNone(result["answer"])

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(SystemExit):
            app.Pipeline(mode="hybrid")


class ServiceTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        pipeline = mock.Mock()
        pipeline.mode = "paper_first"
        pipeline.generator.model_name = "qwen2.5:7b"
        pipeline.answer.side_effect = lambda question: {
            "question": question, "answer": "ok [E1]", "error": None, "references": [], "abstained": False,
        }
        cls.service = serve.Service(pipeline, PROJECT_ROOT / "logs" / "test_service.log")
        cls.server = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(cls.service))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    def test_health(self):
        status, payload = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["retrieval_mode"], "paper_first")

    def test_ask_returns_pipeline_result(self):
        status, payload = self.request("POST", "/ask", json.dumps({"question": "  Which biomarker?  "}))
        self.assertEqual(status, 200)
        self.assertEqual(payload["question"], "Which biomarker?")
        self.assertEqual(payload["answer"], "ok [E1]")

    def test_ui_page_is_served(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("text/html", response.getheader("Content-Type"))
        self.assertIn('id="question"', body)

    def test_bad_requests_are_rejected(self):
        self.assertEqual(self.request("POST", "/ask", "not json")[0], 400)
        self.assertEqual(self.request("POST", "/ask", json.dumps({"question": ""}))[0], 400)
        self.assertEqual(self.request("POST", "/ask", json.dumps({"question": "x" * 2001}))[0], 400)
        self.assertEqual(self.request("GET", "/nothing")[0], 404)


if __name__ == "__main__":
    unittest.main()
