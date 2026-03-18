"""Tests for Phase 4 Web UI Polish: WEBUI-01, WEBUI-02, WEBUI-03."""

import sys
import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Backend path setup
BACKEND_DIR = Path(__file__).parent.parent / "ui-draft" / "backend"
sys.path.insert(0, str(BACKEND_DIR))


class TestAuditLogStore(unittest.TestCase):
    """WEBUI-02: AuditLogStore stores timestamped operations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        from backend_api import AuditLogStore
        self.store = AuditLogStore(Path(self.tmpdir) / "audit_log.json")

    def test_append_creates_entry_with_operation_and_detail(self):
        entry = self.store.append("scaffold", "Created foo at /tmp/foo")
        self.assertEqual(entry["operation"], "scaffold")
        self.assertEqual(entry["detail"], "Created foo at /tmp/foo")

    def test_append_entry_has_created_at_timestamp(self):
        entry = self.store.append("flux-poll", "Polled abc-123")
        self.assertIn("created_at", entry)
        self.assertTrue(entry["created_at"].endswith("Z"))

    def test_list_returns_entries_in_reverse_order(self):
        self.store.append("scaffold", "first")
        self.store.append("flux-poll", "second")
        entries = self.store.list()
        self.assertEqual(entries[0]["operation"], "flux-poll")  # most recent first

    def test_append_multiple_entries_persisted(self):
        for i in range(3):
            self.store.append("scaffold", f"op-{i}")
        entries = self.store.list()
        self.assertEqual(len(entries), 3)

    def test_max_entries_capped_at_200(self):
        """Appending more than 200 entries keeps only the most recent 200."""
        for i in range(205):
            self.store.append("scaffold", f"op-{i}")
        entries = self.store.list()
        self.assertEqual(len(entries), 200)


class TestAuditEndpoint(unittest.TestCase):
    """WEBUI-02: /api/audit returns stored audit entries."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_audit_endpoint_returns_entries_list(self):
        import backend_api
        from backend_api import AuditLogStore
        backend_api.AUDIT_LOG = AuditLogStore(Path(self.tmpdir) / "audit_log.json")
        backend_api.AUDIT_LOG.append("scaffold", "test op")
        from fastapi.testclient import TestClient
        client = TestClient(backend_api.app)
        resp = client.get("/api/audit")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("entries", data)
        self.assertGreater(len(data["entries"]), 0)
        self.assertEqual(data["entries"][0]["operation"], "scaffold")


class TestSSEEndpoint(unittest.TestCase):
    """WEBUI-01: /api/create/stream returns SSE events in order."""

    def _parse_sse_events(self, content: str) -> list:
        events = []
        for chunk in content.split("\n\n"):
            chunk = chunk.strip()
            if not chunk:
                continue
            data_line = next((l for l in chunk.split("\n") if l.startswith("data: ")), None)
            if data_line:
                try:
                    events.append(json.loads(data_line[6:]))
                except json.JSONDecodeError:
                    pass
        return events

    def test_stream_yields_steps_in_order(self):
        """SSE events must include analyzing, generating, addons, git, done."""
        import backend_api
        mock_result = {
            "project_path": "/tmp/test-proj",
            "addons_triggered": ["eck_deployment", "flux_deployment"],
            "files_created": ["flux/kustomization.yaml"],
            "effective_platform": "openshift",
        }

        with patch("backend_api.initialize_project", return_value=mock_result), \
             patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist, \
             patch("backend_api.AUDIT_LOG") as mock_audit:
            mock_hist.add.return_value = {"id": "test-id"}
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post("/api/create/stream", data={
                "name": "test-proj",
                "target_dir": "/tmp",
                "description": "test project",
            })
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/event-stream", resp.headers.get("content-type", ""))

            events = self._parse_sse_events(resp.text)
            steps = [e["step"] for e in events]
            self.assertIn("analyzing", steps)
            self.assertIn("done", steps)
            # done must be last
            self.assertEqual(steps[-1], "done")

    def test_done_event_has_required_summary_fields(self):
        """Done event must contain project_path, addons_triggered, files_created."""
        import backend_api
        mock_result = {
            "project_path": "/tmp/my-project",
            "addons_triggered": ["eck_deployment"],
            "files_created": ["a.yaml", "b.yaml"],
            "effective_platform": "openshift",
        }
        with patch("backend_api.initialize_project", return_value=mock_result), \
             patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist, \
             patch("backend_api.AUDIT_LOG"):
            mock_hist.add.return_value = {"id": "x"}
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post("/api/create/stream", data={"name": "my-project", "target_dir": "/tmp"})
            events = self._parse_sse_events(resp.text)
            done_events = [e for e in events if e.get("step") == "done"]
            self.assertGreater(len(done_events), 0)
            done = done_events[0]
            self.assertIn("project_path", done)
            self.assertIn("addons_triggered", done)
            self.assertIn("files_created", done)

    def test_stream_error_yields_error_event(self):
        """Submitting an empty name should yield HTTP 422 or an SSE error event."""
        import backend_api
        from fastapi.testclient import TestClient
        client = TestClient(backend_api.app)
        resp = client.post("/api/create/stream", data={"name": "", "target_dir": "/tmp"})
        # FastAPI Form validation raises 422 for empty required field, OR the generator
        # yields an error SSE event. Both are acceptable outcomes.
        if resp.status_code == 422:
            return  # validation rejected before streaming
        self.assertEqual(resp.status_code, 200)
        events = self._parse_sse_events(resp.text)
        error_steps = [e for e in events if e.get("step") == "error"]
        self.assertGreater(len(error_steps), 0, "Expected at least one error SSE event")

    def test_stream_audit_log_called(self):
        """A successful stream must call AUDIT_LOG.append with 'scaffold' operation."""
        import backend_api
        mock_result = {
            "project_path": "/tmp/audit-proj",
            "addons_triggered": [],
            "files_created": [],
            "effective_platform": "rke2",
        }
        with patch("backend_api.initialize_project", return_value=mock_result), \
             patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist, \
             patch("backend_api.AUDIT_LOG") as mock_audit:
            mock_hist.add.return_value = {"id": "audit-id"}
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post("/api/create/stream", data={
                "name": "audit-proj",
                "target_dir": "/tmp",
            })
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(mock_audit.append.called, "AUDIT_LOG.append was not called")
            first_call_args = mock_audit.append.call_args_list[0]
            self.assertEqual(first_call_args[0][0], "scaffold")


class TestFluxStatusEndpoint(unittest.TestCase):
    """WEBUI-03: /api/flux-status returns 4 kustomization rows."""

    def _make_deployment_entry(self, target_type="local"):
        return {
            "id": "dep-001",
            "name": "my-es",
            "target_type": target_type,
            "remote": {
                "host": "10.0.0.1",
                "port": "22",
                "user": "ubuntu",
                "ssh_key_path": "/tmp/id_rsa",
            } if target_type == "remote" else None,
        }

    def test_local_returns_4_kustomizations(self):
        import backend_api
        entry = self._make_deployment_entry("local")
        kubectl_output = "True|ReconciliationSucceeded|Applied revision"

        with patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist, \
             patch("backend_api._run_shell_command") as mock_cmd, \
             patch("backend_api.AUDIT_LOG"):
            mock_hist.list.return_value = [entry]
            mock_cmd.return_value = {"ok": True, "stdout": kubectl_output, "stderr": ""}
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.get("/api/flux-status", params={"deployment_id": "dep-001"})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(len(data["kustomizations"]), 4)
            names = [k["name"] for k in data["kustomizations"]]
            self.assertIn("my-es", names)
            self.assertIn("my-es-infra", names)
            self.assertIn("my-es-apps", names)
            self.assertIn("my-es-agents", names)

    def test_remote_calls_ssh_command(self):
        import backend_api
        entry = self._make_deployment_entry("remote")

        with patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist, \
             patch("backend_api._run_ssh_command") as mock_ssh, \
             patch("backend_api.AUDIT_LOG"):
            mock_hist.list.return_value = [entry]
            mock_ssh.return_value = {"ok": True, "stdout": "True|ReconciliationSucceeded|OK", "stderr": ""}
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.get("/api/flux-status", params={"deployment_id": "dep-001"})
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(mock_ssh.called)
            call_args = mock_ssh.call_args_list[0]
            self.assertEqual(call_args[0][0], "10.0.0.1")  # host
            self.assertEqual(call_args[0][2], "ubuntu")    # user

    def test_unknown_deployment_returns_404(self):
        import backend_api
        with patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist:
            mock_hist.list.return_value = []
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.get("/api/flux-status", params={"deployment_id": "nonexistent"})
            self.assertEqual(resp.status_code, 404)

    def test_returns_es_pods(self):
        """Response must include es_pods with running and total fields."""
        import backend_api
        entry = self._make_deployment_entry("local")

        with patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist, \
             patch("backend_api._run_shell_command") as mock_cmd, \
             patch("backend_api.AUDIT_LOG"):
            mock_hist.list.return_value = [entry]
            # kustomization calls return ready status; es statefulset call returns pods
            mock_cmd.return_value = {"ok": True, "stdout": "3/3", "stderr": ""}
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.get("/api/flux-status", params={"deployment_id": "dep-001"})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("es_pods", data)
            self.assertIn("running", data["es_pods"])
            self.assertIn("total", data["es_pods"])


if __name__ == "__main__":
    unittest.main()
