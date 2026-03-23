"""Tests for Phase 4 Web UI Polish: WEBUI-01, WEBUI-02, WEBUI-03."""

import sys
import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

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
            "files_created": ["terraform/main.tf", "elasticsearch/cluster.yaml"],
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
            self.assertIn("output_summary", done)
            self.assertIn("validation_report", done)
            self.assertIn("generation", done["validation_report"])
            families = {item["family"] for item in done["output_summary"]["families"]}
            self.assertIn("infrastructure", families)
            self.assertIn("elastic", families)

    def test_stream_done_event_includes_remote_target_metadata(self):
        import backend_api
        mock_result = {
            "project_path": "/opt/projects/remote-proj",
            "addons_triggered": ["eck_deployment"],
            "files_created": ["README.md"],
            "effective_platform": "rke2",
            "target_type": "remote",
            "remote": {
                "enabled": True,
                "ok": True,
                "log": [],
                "host": "10.0.0.8",
                "user": "ubuntu",
                "port": "2222",
                "ssh_key_path": "/tmp/id_rsa",
                "project_dir": "/opt/projects/remote-proj",
                "base_dir": "/opt/projects",
            },
        }
        with patch("backend_api.initialize_project", return_value=mock_result), \
             patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist, \
             patch("backend_api.AUDIT_LOG"):
            mock_hist.add.return_value = {"id": "remote-id"}
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post("/api/create/stream", data={
                "name": "remote-proj",
                "target_dir": "/tmp",
                "target_type": "remote",
                "remote_host": "10.0.0.8",
                "remote_user": "ubuntu",
                "remote_port": "2222",
                "remote_ssh_key_path": "/tmp/id_rsa",
                "remote_base_dir": "/opt/projects",
            })
            self.assertEqual(resp.status_code, 200)
            events = self._parse_sse_events(resp.text)
            done = [e for e in events if e.get("step") == "done"][0]
            self.assertEqual(done["target_type"], "remote")
            self.assertEqual(done["remote"]["host"], "10.0.0.8")
            self.assertEqual(done["remote"]["port"], "2222")
            self.assertEqual(done["remote"]["project_dir"], "/opt/projects/remote-proj")

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


class TestSizingApi(unittest.TestCase):
    def test_presets_endpoint_returns_platforms_and_policy_profiles(self):
        import backend_api
        from fastapi.testclient import TestClient
        client = TestClient(backend_api.app)
        resp = client.get('/api/presets')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('platform_presets', data)
        self.assertIn('policy_profiles', data)
        self.assertIn('proxmox', data['platform_presets'])
        self.assertIn('restricted-managed', data['policy_profiles'])

    def test_preview_endpoint_returns_structured_preview(self):
        import backend_api
        preview = {
            "ok": True,
            "schema_version": "es-sizing-platform.v1",
            "platform_detected": "rke2",
            "warnings": [{"code": "derived_pool_disk", "severity": "warning", "message": "disk inferred"}],
            "fatal_error": None,
            "sizing_context_applied": True,
            "pools": [{"name": "hot_pool", "nodes": 1}],
        }
        addon_preview = {"primary_category": "elasticsearch", "priority_chain": "default", "addons": [{"name": "eck_deployment", "description": "ECK", "priority": 20, "areas": ["elasticsearch/"]}]}
        with patch("backend_api._parse_uploaded_sizing_file", new=AsyncMock(return_value=({"platform_detected": "rke2"}, "rke2", preview))), \
             patch("backend_api._build_addon_preview", return_value=addon_preview):
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post(
                "/api/sizing/preview",
                data={
                    "platform": "proxmox",
                    "enable_otel_collector": "true",
                    "description": "Rancher and Fleet managed",
                    "license_id": "UNLICENSED",
                    "confidentiality": "public",
                    "header_mode": "full",
                    "policy_profile": "apache-public",
                },
                files={"sizing_file": ("sizing.json", b"{}", "application/json")},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["platform_detected"], "rke2")
            self.assertEqual(data["effective_platform"], "proxmox")
            self.assertEqual(data["pools"][0]["name"], "hot_pool")
            self.assertTrue(any(item["code"] == "proxmox_rke2_bootstrap" for item in data["caveats"]))
            self.assertTrue(any(item["code"] == "rke2_otel_timing" for item in data["caveats"]))
            self.assertEqual(data["addon_preview"]["addons"][0]["name"], "eck_deployment")
            governance = data["governance_preview"]
            self.assertEqual(governance["policy_profile"], "apache-public")
            self.assertEqual(governance["license_policy"]["license_id"], "UNLICENSED")
            codes = {item["code"] for item in governance["validation"]["items"]}
            self.assertIn("public_unlicensed", codes)
            self.assertIn("missing_owner_metadata", codes)

    def test_create_rejects_fatal_sizing_error_by_default(self):
        import backend_api
        preview = {
            "ok": False,
            "warnings": [],
            "fatal_error": {"code": "invalid_json", "severity": "error", "message": "Invalid sizing file"},
            "sizing_context_applied": False,
        }
        with patch("backend_api._parse_uploaded_sizing_file", new=AsyncMock(return_value=(None, None, preview))):
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post(
                "/api/create",
                data={"name": "bad-sizing", "target_dir": "/tmp"},
                files={"sizing_file": ("bad.json", b"{}", "application/json")},
            )
            self.assertEqual(resp.status_code, 422)
            detail = resp.json()["detail"]
            self.assertEqual(detail["message"], "Invalid sizing file")
            self.assertFalse(detail["sizing_preview"]["sizing_context_applied"])

    def test_create_includes_platform_caveats_in_response(self):
        import backend_api
        preview = {
            "ok": True,
            "platform_detected": "openshift",
            "warnings": [],
            "fatal_error": None,
            "sizing_context_applied": True,
        }
        mock_result = {
            "project_path": "/tmp/with-caveats",
            "addons_triggered": [],
            "files_created": ["platform/openshift/route.yaml", "docs/OBSERVABILITY_ROLLOUT.md"],
        }
        addon_preview = {"primary_category": "elasticsearch", "priority_chain": "openshift_focused", "addons": [{"name": "platform_manifests", "description": "Platform", "priority": 15, "areas": ["platform/"]}]}
        with patch("backend_api._parse_uploaded_sizing_file", new=AsyncMock(return_value=({"platform_detected": "openshift"}, "openshift", preview))), \
             patch("backend_api._build_addon_preview", return_value=addon_preview), \
             patch("backend_api.initialize_project", return_value=mock_result), \
             patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist:
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post(
                "/api/create",
                data={
                    "name": "with-caveats",
                    "target_dir": "/tmp",
                    "platform": "openshift",
                    "use_terraform_iac": "true",
                    "enable_otel_collector": "true",
                    "description": "OpenShift delivery",
                    "license_id": "Apache-2.0",
                    "confidentiality": "internal",
                    "header_mode": "minimal",
                    "organization": "Platform Team",
                    "policy_profile": "restricted-managed",
                },
                files={"sizing_file": ("good.json", b"{}", "application/json")},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["sizing_preview"]["effective_platform"], "openshift")
            caveat_codes = {item["code"] for item in data["sizing_preview"]["caveats"]}
            self.assertIn("openshift_delivery_scope", caveat_codes)
            self.assertIn("openshift_iac_scope", caveat_codes)
            self.assertIn("openshift_otel_scc", caveat_codes)
            self.assertEqual(data["sizing_preview"]["addon_preview"]["addons"][0]["name"], "platform_manifests")
            self.assertEqual(data["governance_preview"]["policy_profile"], "restricted-managed")
            self.assertEqual(data["governance_preview"]["license_policy"]["license_id"], "Apache-2.0")
            self.assertTrue(data["validation_report"]["ok"])
            self.assertIn("generation", data["validation_report"])
            families = {item["family"] for item in data["output_summary"]["families"]}
            self.assertIn("platform", families)
            self.assertIn("automation", families)
            self.assertTrue(mock_hist.add.called)

    def test_create_can_continue_without_sizing(self):
        import backend_api
        preview = {
            "ok": False,
            "warnings": [],
            "fatal_error": {"code": "invalid_json", "severity": "error", "message": "Invalid sizing file"},
            "sizing_context_applied": False,
        }
        mock_result = {
            "project_path": "/tmp/continue-sizing",
            "addons_triggered": [],
            "files_created": [],
        }
        with patch("backend_api._parse_uploaded_sizing_file", new=AsyncMock(return_value=(None, None, preview))), \
             patch("backend_api.initialize_project", return_value=mock_result), \
             patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist:
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post(
                "/api/create",
                data={
                    "name": "continue-sizing",
                    "target_dir": "/tmp",
                    "platform": "proxmox",
                    "continue_without_sizing": "true",
                },
                files={"sizing_file": ("bad.json", b"{}", "application/json")},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertFalse(data["sizing_context_applied"])
            self.assertEqual(data["sizing_parse_error"]["message"], "Invalid sizing file")
            self.assertTrue(mock_hist.add.called)

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

    def test_stream_emits_platform_caveat_warning(self):
        import backend_api
        preview = {
            "ok": True,
            "platform_detected": "aks",
            "warnings": [],
            "fatal_error": None,
            "sizing_context_applied": True,
        }
        mock_result = {
            "project_path": "/tmp/aks-caveat-stream",
            "addons_triggered": [],
            "files_created": [],
            "effective_platform": "aks",
        }
        addon_preview = {"primary_category": "azure", "priority_chain": "azure_focused", "addons": [{"name": "terraform_aks", "description": "AKS", "priority": 12, "areas": ["terraform/"]}]}
        with patch("backend_api._parse_uploaded_sizing_file", new=AsyncMock(return_value=({"platform_detected": "aks"}, "aks", preview))), \
             patch("backend_api._build_addon_preview", return_value=addon_preview), \
             patch("backend_api.initialize_project", return_value=mock_result), \
             patch("backend_api.DEPLOYMENT_HISTORY") as mock_hist, \
             patch("backend_api.AUDIT_LOG"):
            mock_hist.add.return_value = {"id": "stream-id"}
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post(
                "/api/create/stream",
                data={
                    "name": "aks-caveat-stream",
                    "target_dir": "/tmp",
                    "platform": "aks",
                    "enable_otel_collector": "true",
                    "license_id": "UNLICENSED",
                    "confidentiality": "public",
                    "header_mode": "full",
                },
                files={"sizing_file": ("good.json", b"{}", "application/json")},
            )
            self.assertEqual(resp.status_code, 200)
            events = self._parse_sse_events(resp.text)
            caveat_events = [e for e in events if e.get("message") == "Platform caveats detected"]
            self.assertGreater(len(caveat_events), 0)
            caveat_codes = {item["code"] for item in caveat_events[0].get("caveats", [])}
            self.assertIn("aks_managed_cluster", caveat_codes)
            self.assertIn("aks_otel_overlap", caveat_codes)
            addon_events = [e for e in events if e.get("message") == "Addon plan computed"]
            self.assertGreater(len(addon_events), 0)
            self.assertEqual(addon_events[0]["addon_preview"]["addons"][0]["name"], "terraform_aks")
            governance_events = [e for e in events if e.get("message") == "Governance validation detected"]
            self.assertGreater(len(governance_events), 0)
            governance_codes = {item["code"] for item in governance_events[0]["governance_preview"]["validation"]["items"]}
            self.assertIn("public_unlicensed", governance_codes)

    def test_stream_fatal_sizing_error_emits_error_event(self):
        import backend_api
        preview = {
            "ok": False,
            "warnings": [],
            "fatal_error": {"code": "invalid_json", "severity": "error", "message": "Invalid sizing file"},
            "sizing_context_applied": False,
        }
        with patch("backend_api._parse_uploaded_sizing_file", new=AsyncMock(return_value=(None, None, preview))):
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post(
                "/api/create/stream",
                data={"name": "bad-stream", "target_dir": "/tmp"},
                files={"sizing_file": ("bad.json", b"{}", "application/json")},
            )
            self.assertEqual(resp.status_code, 200)
            events = self._parse_sse_events(resp.text)
            self.assertEqual(events[-1]["step"], "error")
            self.assertEqual(events[-1]["message"], "Invalid sizing file")


class TestProjectOperationsApi(unittest.TestCase):
    def test_open_remote_path_builds_zed_uri_with_port(self):
        import backend_api
        with patch('backend_api.shutil.which', return_value='/usr/bin/zed'), \
             patch('backend_api.subprocess.Popen') as mock_popen:
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post('/api/open-remote', data={
                'host': '10.0.0.8',
                'user': 'ubuntu',
                'port': '2222',
                'remote_path': '/opt/projects/remote proj',
                'tool': 'zed',
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['port'], '2222')
            self.assertIn('ssh://ubuntu@10.0.0.8:2222/opt/projects/remote%20proj', data['command'])
            mock_popen.assert_called_once()
            self.assertEqual(mock_popen.call_args[0][0], ['zed', 'ssh://ubuntu@10.0.0.8:2222/opt/projects/remote%20proj'])

    def test_project_operations_local_detects_artifacts_and_scripts(self):
        import backend_api
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'scripts').mkdir()
            (root / 'terraform').mkdir()
            for rel in ['project-initializer-manifest.json', 'project-initializer-operations.json', 'project-initializer-validation-report.json', 'LICENSE', 'NOTICE', 'GENERATED_BY.md', 'README.md', 'scripts/preflight-check.sh', 'terraform/main.tf']:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('echo ok\n', encoding='utf-8')
            entry = {
                'id': 'dep-local',
                'name': 'local-proj',
                'project_path': str(root),
                'target_type': 'local',
                'output_summary': {'total_files': 3, 'families': []},
                'validation_report': {'ok': True, 'items': []},
            }
            with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist:
                mock_hist.list.return_value = [entry]
                from fastapi.testclient import TestClient
                client = TestClient(backend_api.app)
                resp = client.get('/api/project/operations', params={'deployment_id': 'dep-local'})
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertEqual(data['target_type'], 'local')
                self.assertTrue(any(item['path'] == 'README.md' and item['exists'] for item in data['artifacts']))
                self.assertTrue(any(item['path'] == 'project-initializer-operations.json' and item['exists'] for item in data['artifacts']))
                self.assertIn('environment_diagnostics', data)
                self.assertIn('counts', data['environment_diagnostics'])
                self.assertIn('runbook_progress', data)
                self.assertIn('history_timeline', data)
                self.assertEqual(data['runbook_progress']['steps'][0]['key'], 'preflight-check')
                self.assertIn('docs_resolved', data['runbook_progress']['steps'][0])
                self.assertIn('suggested_command', data['runbook_progress']['steps'][0])
                self.assertIn('remediation', data['runbook_progress']['steps'][0])
                self.assertIn('next_command', data['runbook_progress'])
                script = next(item for item in data['scripts'] if item['key'] == 'preflight-check')
                self.assertTrue(script['exists'])
                self.assertTrue(script['ready'])
                self.assertIn('prerequisite_checks', script)
                self.assertIn('recommended_order', script)

    def test_project_operations_remote_uses_remote_project_dir(self):
        import backend_api
        entry = {
            'id': 'dep-remote',
            'name': 'remote-proj',
            'target_type': 'remote',
            'remote': {'host': '10.0.0.1', 'port': '22', 'user': 'ubuntu', 'ssh_key_path': '/tmp/id_rsa', 'project_dir': '/opt/projects/remote-proj'},
        }
        with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api._run_ssh_command') as mock_ssh:
            mock_hist.list.return_value = [entry]
            mock_ssh.return_value = {'ok': True, 'stdout': 'present', 'stderr': ''}
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.get('/api/project/operations', params={'deployment_id': 'dep-remote'})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['project_root'], '/opt/projects/remote-proj')
            self.assertTrue(mock_ssh.called)
            first_remote_cmd = mock_ssh.call_args_list[0][0][3]
            self.assertIn('/opt/projects/remote-proj', first_remote_cmd)
            self.assertIn('history_timeline', data)

    def test_project_artifact_preview_local_reads_text(self):
        import backend_api
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'docs').mkdir(parents=True)
            (root / 'docs' / 'DEPLOYMENT_ATTENTION.md').write_text('# Attention\nCheck prereqs\n', encoding='utf-8')
            entry = {'id': 'dep-preview-local', 'name': 'preview-local', 'project_path': str(root), 'target_type': 'local'}
            with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist:
                mock_hist.list.return_value = [entry]
                from fastapi.testclient import TestClient
                client = TestClient(backend_api.app)
                resp = client.get('/api/project/artifact-preview', params={'deployment_id': 'dep-preview-local', 'path': 'docs/DEPLOYMENT_ATTENTION.md'})
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertEqual(data['path'], 'docs/DEPLOYMENT_ATTENTION.md')
                self.assertIn('Check prereqs', data['content'])
                self.assertFalse(data['truncated'])

    def test_project_artifact_preview_rejects_traversal(self):
        import backend_api
        entry = {'id': 'dep-preview-bad', 'name': 'preview-bad', 'project_path': '/tmp/demo', 'target_type': 'local'}
        with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist:
            mock_hist.list.return_value = [entry]
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.get('/api/project/artifact-preview', params={'deployment_id': 'dep-preview-bad', 'path': '../secret.txt'})
            self.assertEqual(resp.status_code, 400)
            self.assertIn('invalid project-relative path', resp.json()['detail'])

    def test_project_diagnostics_local_reports_tools_and_actions(self):
        import backend_api
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            entry = {'id': 'dep-diag-local', 'name': 'diag-local', 'project_path': str(root), 'target_type': 'local', 'platform': 'aks'}
            with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, \
                 patch('backend_api.shutil.which', side_effect=lambda name: f'/usr/bin/{name}' if name in {'bash', 'python3', 'ssh', 'curl', 'kubectl', 'terraform'} else None), \
                 patch('backend_api._run_shell_command', return_value={'ok': True, 'command': 'kubectl config current-context', 'stdout': 'demo-context', 'stderr': ''}):
                mock_hist.list.return_value = [entry]
                from fastapi.testclient import TestClient
                client = TestClient(backend_api.app)
                resp = client.get('/api/project/diagnostics', params={'deployment_id': 'dep-diag-local'})
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertEqual(data['target_type'], 'local')
                self.assertIn('counts', data)
                names = {item['name'] for item in data['items']}
                self.assertIn('kubectl', names)
                self.assertIn('terraform', names)
                self.assertIn('kubeconfig', names)
                self.assertGreaterEqual(len(data['next_actions']), 1)

    def test_project_diagnostics_remote_reports_connectivity(self):
        import backend_api
        entry = {
            'id': 'dep-diag-remote',
            'name': 'diag-remote',
            'target_type': 'remote',
            'platform': 'openshift',
            'remote': {'host': '10.0.0.1', 'port': '22', 'user': 'ubuntu', 'ssh_key_path': '/tmp/id_rsa', 'project_dir': '/opt/projects/diag-remote'},
        }
        def fake_ssh(host, port, user, cmd, key):
            if 'echo connected' in cmd:
                return {'ok': True, 'stdout': 'connected', 'stderr': ''}
            if 'test -d' in cmd:
                return {'ok': True, 'stdout': 'present', 'stderr': ''}
            if 'command -v' in cmd:
                if 'kustomize' in cmd or 'oc' in cmd:
                    return {'ok': True, 'stdout': 'missing', 'stderr': ''}
                return {'ok': True, 'stdout': 'present', 'stderr': ''}
            if 'kubectl config current-context' in cmd:
                return {'ok': True, 'stdout': 'remote-context', 'stderr': ''}
            return {'ok': True, 'stdout': 'present', 'stderr': ''}
        with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api._run_ssh_command', side_effect=fake_ssh):
            mock_hist.list.return_value = [entry]
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.get('/api/project/diagnostics', params={'deployment_id': 'dep-diag-remote'})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['target_type'], 'remote')
            self.assertEqual(data['remote']['host'], '10.0.0.1')
            self.assertTrue(any(item['scope'] == 'connectivity' for item in data['items']))
            self.assertTrue(any(item['name'] == 'openshift_auth' for item in data['items']))
            self.assertGreaterEqual(data['counts']['warning'], 1)

    def test_project_validate_runs_safe_checks(self):
        import backend_api
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'scripts').mkdir()
            (root / 'terraform').mkdir()
            for rel in ['project-initializer-manifest.json', 'project-initializer-operations.json', 'project-initializer-validation-report.json', 'LICENSE', 'NOTICE', 'GENERATED_BY.md', 'README.md', 'scripts/preflight-check.sh', 'terraform/main.tf']:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#!/usr/bin/env bash\necho ok\n', encoding='utf-8')
            entry = {'id': 'dep-validate', 'name': 'validate-proj', 'project_path': str(root), 'target_type': 'local'}
            def fake_run(cmd, cwd, env=None):
                return {'ok': True, 'command': ' '.join(cmd), 'stdout': '', 'stderr': ''}
            with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api._run_shell_command', side_effect=fake_run), patch('backend_api.OPERATION_RUN_HISTORY') as mock_runs, patch('backend_api.AUDIT_LOG'):
                mock_hist.list.return_value = [entry]
                mock_runs.add.side_effect = lambda payload: {**payload, 'created_at': '2026-03-22T09:00:00Z'}
                from fastapi.testclient import TestClient
                client = TestClient(backend_api.app)
                resp = client.post('/api/project/validate', data={'deployment_id': 'dep-validate'})
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertIn('items', data)
                self.assertIn('counts', data)
                self.assertIn('run_record', data)
                self.assertTrue(any(item['scope'] == 'scripts' for item in data['items']))
                self.assertTrue(any(item['scope'] == 'prerequisites' for item in data['items']))
                self.assertTrue(all(item['classification'] in {'pass', 'warning', 'blocking'} for item in data['items']))
                self.assertEqual(data['run_record']['kind'], 'validation')

    def test_project_run_script_local_passes_script_arguments_as_environment(self):
        import backend_api
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'scripts').mkdir()
            for rel in ['project-initializer-operations.json', 'scripts/cluster-healthcheck.sh']:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#!/usr/bin/env bash\necho ok\n', encoding='utf-8')
            entry = {'id': 'dep-run-local', 'name': 'local-proj', 'project_path': str(root), 'target_type': 'local'}
            captured = {}
            def fake_run(cmd, cwd, env=None):
                captured['cmd'] = cmd
                captured['env'] = env or {}
                return {'ok': True, 'command': ' '.join(cmd), 'stdout': 'ok', 'stderr': ''}
            with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api._run_shell_command', side_effect=fake_run), patch('backend_api._evaluate_script_prerequisites', return_value=[]), patch('backend_api.OPERATION_RUN_HISTORY') as mock_runs, patch('backend_api.AUDIT_LOG'):
                mock_hist.list.return_value = [entry]
                mock_runs.list.return_value = []
                from fastapi.testclient import TestClient
                client = TestClient(backend_api.app)
                resp = client.post('/api/project/run-script', data={
                    'deployment_id': 'dep-run-local',
                    'script_key': 'cluster-healthcheck',
                    'script_arguments': json.dumps({'kubeconfig_path': '/tmp/demo-kubeconfig'}),
                })
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertIn('execution_context', data)
                self.assertEqual(data['execution_context']['arguments']['kubeconfig_path'], '/tmp/demo-kubeconfig')
                self.assertEqual(captured['env']['PI_ARG_KUBECONFIG_PATH'], '/tmp/demo-kubeconfig')
                self.assertTrue(data['sequencing']['out_of_order'])
                self.assertIn('preflight-check', data['sequencing']['warning'])
                self.assertIn('current_step', data['sequencing'])
                self.assertIn('remediation', data['sequencing']['current_step'])
                self.assertIn('next_command', data['sequencing'])

    def test_project_run_script_mutating_requires_confirmation_phrase(self):
        import backend_api
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'scripts').mkdir()
            for rel in ['project-initializer-operations.json', 'scripts/post-terraform-deploy.sh']:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#!/usr/bin/env bash\necho ok\n', encoding='utf-8')
            entry = {'id': 'dep-run-mutate', 'name': 'mutating-proj', 'project_path': str(root), 'target_type': 'local'}
            with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api._evaluate_script_prerequisites', return_value=[]), patch('backend_api.AUDIT_LOG'):
                mock_hist.list.return_value = [entry]
                from fastapi.testclient import TestClient
                client = TestClient(backend_api.app)
                bad = client.post('/api/project/run-script', data={
                    'deployment_id': 'dep-run-mutate',
                    'script_key': 'post-terraform-deploy',
                    'allow_mutating': 'true',
                    'confirmation_text': 'wrong',
                })
                self.assertEqual(bad.status_code, 400)
                self.assertIn("confirmation mismatch", bad.json()['detail'])

    def test_project_run_script_mirror_secrets_is_runnable_without_danger_confirmation(self):
        import backend_api
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'scripts').mkdir()
            for rel in ['project-initializer-operations.json', 'scripts/mirror-secrets.sh']:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#!/usr/bin/env bash\necho mirrored\n', encoding='utf-8')
            entry = {'id': 'dep-run-mirror', 'name': 'mirror-proj', 'project_path': str(root), 'target_type': 'local'}
            with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api._run_shell_command', return_value={'ok': True, 'command': 'bash scripts/mirror-secrets.sh', 'stdout': 'mirrored', 'stderr': ''}), patch('backend_api.AUDIT_LOG'), patch('backend_api.OPERATION_RUN_HISTORY') as mock_runs:
                mock_hist.list.return_value = [entry]
                mock_runs.list.return_value = []
                from fastapi.testclient import TestClient
                client = TestClient(backend_api.app)
                resp = client.post('/api/project/run-script', data={
                    'deployment_id': 'dep-run-mirror',
                    'script_key': 'mirror-secrets',
                })
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.json()['script']['safe'])
                self.assertFalse(resp.json()['script'].get('dangerous', False))

    def test_project_run_script_post_terraform_returns_chained_substeps(self):
        import backend_api
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'scripts').mkdir()
            for rel in ['project-initializer-operations.json', 'scripts/post-terraform-deploy.sh']:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#!/usr/bin/env bash\necho ok\n', encoding='utf-8')
            entry = {'id': 'dep-run-post', 'name': 'post-proj', 'project_path': str(root), 'target_type': 'local'}
            stdout = '\n'.join([
                '::pi-substep cluster-healthcheck ok',
                '::pi-substep mirror-secrets warning',
                '::pi-substep fleet-output ok',
                '::pi-substep import-dashboards skipped',
            ])
            with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, \
                 patch('backend_api._run_shell_command', return_value={'ok': True, 'command': 'bash scripts/post-terraform-deploy.sh', 'stdout': stdout, 'stderr': ''}), \
                 patch('backend_api._evaluate_script_prerequisites', return_value=[]), \
                 patch('backend_api.AUDIT_LOG'), \
                 patch('backend_api.OPERATION_RUN_HISTORY') as mock_runs:
                mock_hist.list.return_value = [entry]
                mock_runs.list.return_value = []
                from fastapi.testclient import TestClient
                client = TestClient(backend_api.app)
                resp = client.post('/api/project/run-script', data={
                    'deployment_id': 'dep-run-post',
                    'script_key': 'post-terraform-deploy',
                    'allow_mutating': 'true',
                    'confirmation_text': 'post-proj',
                })
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertEqual([item['key'] for item in data['substeps']], ['cluster-healthcheck', 'mirror-secrets', 'fleet-output', 'import-dashboards'])
                self.assertEqual(data['substeps'][1]['status'], 'warning')

    def test_flux_status_returns_cluster_summary(self):
        import backend_api
        entry = {'id': 'dep-status', 'name': 'demo', 'target_type': 'local'}
        def fake_run(cmd, cwd, env=None):
            rendered = ' '.join(cmd)
            if 'kustomization demo ' in rendered:
                return {'ok': True, 'stdout': 'True|ReconciliationSucceeded|ok', 'stderr': ''}
            if 'kustomization demo-infra ' in rendered:
                return {'ok': True, 'stdout': 'True|ReconciliationSucceeded|ok', 'stderr': ''}
            if 'kustomization demo-apps ' in rendered:
                return {'ok': True, 'stdout': 'False|Progressing|applying', 'stderr': ''}
            if 'kustomization demo-agents ' in rendered:
                return {'ok': True, 'stdout': 'Unknown||', 'stderr': ''}
            if 'statefulset' in rendered:
                return {'ok': True, 'stdout': '1/1', 'stderr': ''}
            if 'config current-context' in rendered:
                return {'ok': True, 'stdout': 'demo-admin', 'stderr': ''}
            if 'cluster-info' in rendered:
                return {'ok': True, 'stdout': 'Cluster API running', 'stderr': ''}
            if 'get nodes --no-headers' in rendered:
                return {'ok': True, 'stdout': 'cp-1 Ready control-plane\nworker-1 Ready worker', 'stderr': ''}
            return {'ok': True, 'stdout': '', 'stderr': ''}
        with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, \
             patch('backend_api._run_shell_command', side_effect=fake_run), \
             patch('backend_api._check_local_prerequisite', return_value={'name': 'kubeconfig', 'ok': True, 'detail': 'Using /tmp/demo-kubeconfig'}), \
             patch('backend_api.shutil.which', return_value='/usr/bin/kubectl'), \
             patch('backend_api.AUDIT_LOG'):
            mock_hist.list.return_value = [entry]
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.get('/api/flux-status', params={'deployment_id': 'dep-status'})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['kustomization_summary']['counts']['ready'], 2)
            self.assertEqual(data['kustomization_summary']['counts']['reconciling'], 1)
            self.assertEqual(data['cluster_summary']['status'], 'reconciling')
            self.assertTrue(data['access_summary']['kubeconfig']['ok'])
            self.assertEqual(data['access_summary']['kubectl_context']['detail'], 'demo-admin')
            self.assertEqual(data['access_summary']['nodes_ready']['detail'], '2/2 node(s) Ready')

    def test_flux_status_returns_remote_access_summary(self):
        import backend_api
        entry = {
            'id': 'dep-status-remote',
            'name': 'demo',
            'target_type': 'remote',
            'remote': {'host': '10.0.0.8', 'port': '2222', 'user': 'ubuntu', 'ssh_key_path': '/tmp/id_rsa', 'project_dir': '/opt/projects/demo'},
        }
        seen = []
        def fake_ssh(host, port, user, cmd, key):
            seen.append(cmd)
            if 'kustomization demo ' in cmd or 'kustomization demo-infra ' in cmd or 'kustomization demo-apps ' in cmd:
                return {'ok': True, 'stdout': 'True|ReconciliationSucceeded|ok', 'stderr': ''}
            if 'kustomization demo-agents ' in cmd:
                return {'ok': True, 'stdout': 'Unknown||', 'stderr': ''}
            if 'statefulset' in cmd:
                return {'ok': True, 'stdout': '1/1', 'stderr': ''}
            if 'test -f $HOME/.kube/demo' in cmd:
                return {'ok': True, 'stdout': '/home/ubuntu/.kube/demo', 'stderr': ''}
            if 'command -v kubectl' in cmd:
                return {'ok': True, 'stdout': 'present', 'stderr': ''}
            if 'kubectl config current-context' in cmd:
                return {'ok': True, 'stdout': 'remote-admin', 'stderr': ''}
            if 'kubectl cluster-info' in cmd:
                return {'ok': True, 'stdout': 'Cluster API reachable', 'stderr': ''}
            if 'kubectl get nodes --no-headers' in cmd:
                return {'ok': True, 'stdout': 'cp-1 Ready\nworker-1 Ready', 'stderr': ''}
            return {'ok': True, 'stdout': '', 'stderr': ''}
        with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api._run_ssh_command', side_effect=fake_ssh), patch('backend_api.AUDIT_LOG'):
            mock_hist.list.return_value = [entry]
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.get('/api/flux-status', params={'deployment_id': 'dep-status-remote'})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['access_summary']['mode'], 'remote-host')
            self.assertEqual(data['access_summary']['remote']['host'], '10.0.0.8')
            self.assertTrue(data['access_summary']['kubeconfig']['ok'])
            self.assertEqual(data['access_summary']['kubeconfig']['source'], 'remote-project-home')
            self.assertEqual(data['access_summary']['kubectl_context']['detail'], 'remote-admin')
            self.assertTrue(any('export KUBECONFIG=/home/ubuntu/.kube/demo; kubectl get kustomization demo -n flux-system' in cmd for cmd in seen))

    def test_check_local_prerequisite_prefers_project_scoped_kubeconfig(self):
        import backend_api
        entry = {'name': 'os-2', 'platform': 'rke2'}
        with patch.dict('backend_api.os.environ', {}, clear=True), \
             patch('backend_api.Path.exists', autospec=True) as mock_exists:
            def fake_exists(path_obj):
                return str(path_obj).endswith('/.kube/os-2')
            mock_exists.side_effect = fake_exists
            result = backend_api._check_local_prerequisite(entry, 'kubeconfig')
            self.assertTrue(result['ok'])
            self.assertIn('.kube/os-2', result['detail'])

    def test_check_remote_prerequisite_uses_project_scoped_kubeconfig(self):
        import backend_api
        entry = {
            'name': 'os-2',
            'platform': 'rke2',
            'target_type': 'remote',
            'remote': {'host': '10.0.0.8', 'port': '22', 'user': 'ubuntu', 'project_dir': '/opt/projects/os-2'},
        }
        captured = {}
        def fake_ssh(host, port, user, cmd, key):
            captured['cmd'] = cmd
            return {'ok': True, 'stdout': '/home/ubuntu/.kube/os-2', 'stderr': ''}
        with patch('backend_api._run_ssh_command', side_effect=fake_ssh):
            result = backend_api._check_remote_prerequisite(entry, 'kubeconfig')
            self.assertTrue(result['ok'])
            self.assertIn('.kube/os-2', result['detail'])
            self.assertIn('test -f $HOME/.kube/os-2', captured['cmd'])

    def test_project_run_script_remote_uses_generated_remote_path(self):
        import backend_api
        entry = {
            'id': 'dep-run-remote',
            'name': 'remote-proj',
            'target_type': 'remote',
            'remote': {'host': '10.0.0.1', 'port': '22', 'user': 'ubuntu', 'ssh_key_path': '/tmp/id_rsa', 'project_dir': '/opt/projects/remote-proj'},
        }
        def fake_ssh(host, port, user, cmd, key):
            if 'project-initializer-operations.json' in cmd:
                return {'ok': True, 'stdout': 'missing', 'stderr': ''}
            if 'scripts/preflight-check.sh' in cmd and 'test -f' in cmd:
                return {'ok': True, 'stdout': 'present', 'stderr': ''}
            if 'echo connected' in cmd:
                return {'ok': True, 'stdout': 'connected', 'stderr': ''}
            if 'test -d /opt/projects/remote-proj' in cmd:
                return {'ok': True, 'stdout': 'present', 'stderr': ''}
            if 'command -v bash' in cmd:
                return {'ok': True, 'stdout': 'present', 'stderr': ''}
            if 'bash ' in cmd:
                return {'ok': True, 'stdout': 'ok', 'stderr': ''}
            return {'ok': True, 'stdout': 'present', 'stderr': ''}
        diagnostics_ok = {
            'items': [
                {'name': 'ssh', 'ok': True, 'detail': 'connected'},
                {'name': 'project_root', 'ok': True, 'detail': 'present'},
            ],
            'counts': {'pass': 2, 'warning': 0, 'blocking': 0},
        }
        with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api._run_ssh_command', side_effect=fake_ssh) as mock_ssh, patch('backend_api._collect_project_diagnostics', return_value=diagnostics_ok), patch('backend_api.OPERATION_RUN_HISTORY') as mock_runs, patch('backend_api.AUDIT_LOG'):
            mock_hist.list.return_value = [entry]
            mock_runs.list.return_value = []
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post('/api/project/run-script', data={'deployment_id': 'dep-run-remote', 'script_key': 'preflight-check'})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['script']['key'], 'preflight-check')
            self.assertIn('run_record', data)
            self.assertFalse(data['sequencing']['out_of_order'])
            self.assertIn("ssh -p 22 ubuntu@10.0.0.1", data['sequencing']['next_command'])
            self.assertEqual(data['execution_context']['target_type'], 'remote')
            self.assertEqual(data['execution_context']['remote']['host'], '10.0.0.1')
            self.assertEqual(data['sequencing']['failure_classification'], '')
            remote_cmd = mock_ssh.call_args_list[-1][0][3]
            self.assertIn("cd /opt/projects/remote-proj", remote_cmd)
            self.assertIn('scripts/preflight-check.sh', remote_cmd)

    def test_project_run_script_remote_failure_is_classified(self):
        import backend_api
        entry = {
            'id': 'dep-run-remote-fail',
            'name': 'remote-proj',
            'target_type': 'remote',
            'remote': {'host': '10.0.0.2', 'port': '22', 'user': 'ubuntu', 'ssh_key_path': '/tmp/id_rsa', 'project_dir': '/opt/projects/remote-proj'},
        }
        def fake_ssh(host, port, user, cmd, key):
            if 'test -f' in cmd and 'project-initializer-operations.json' in cmd:
                return {'ok': True, 'stdout': 'missing', 'stderr': ''}
            if 'test -f' in cmd and 'scripts/preflight-check.sh' in cmd:
                return {'ok': True, 'stdout': 'present', 'stderr': ''}
            if 'echo connected' in cmd:
                return {'ok': True, 'stdout': 'connected', 'stderr': ''}
            if 'command -v bash' in cmd:
                return {'ok': True, 'stdout': 'present', 'stderr': ''}
            return {'ok': False, 'stdout': '', 'stderr': 'ssh: connect to host 10.0.0.2 port 22: Connection refused'}
        diagnostics_ok = {
            'items': [
                {'name': 'ssh', 'ok': True, 'detail': 'connected'},
                {'name': 'project_root', 'ok': True, 'detail': 'present'},
            ],
            'counts': {'pass': 2, 'warning': 0, 'blocking': 0},
        }
        with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api._run_ssh_command', side_effect=fake_ssh) as mock_ssh, patch('backend_api._collect_project_diagnostics', return_value=diagnostics_ok), patch('backend_api.OPERATION_RUN_HISTORY') as mock_runs, patch('backend_api.AUDIT_LOG'):
            mock_hist.list.return_value = [entry]
            mock_runs.list.return_value = []
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.post('/api/project/run-script', data={'deployment_id': 'dep-run-remote-fail', 'script_key': 'preflight-check'})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['sequencing']['failure_classification'], 'connectivity')

    def test_project_run_history_returns_entries(self):
        import backend_api
        entry = {'id': 'dep-history', 'name': 'history-proj', 'project_path': '/tmp/history-proj', 'target_type': 'local'}
        with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api.OPERATION_RUN_HISTORY') as mock_runs:
            mock_hist.list.return_value = [entry]
            mock_runs.list.return_value = [{'deployment_id': 'dep-history', 'script_key': 'preflight-check', 'ok': True}]
            from fastapi.testclient import TestClient
            client = TestClient(backend_api.app)
            resp = client.get('/api/project/run-history', params={'deployment_id': 'dep-history'})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(len(data['entries']), 1)
            self.assertEqual(data['entries'][0]['script_key'], 'preflight-check')

    def test_project_validate_includes_platform_readiness_checks(self):
        import backend_api
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'platform' / 'rke2').mkdir(parents=True)
            (root / 'scripts').mkdir()
            for rel in ['project-initializer-manifest.json', 'project-initializer-operations.json', 'project-initializer-validation-report.json', 'README.md', 'platform/rke2/cluster-config.yaml', 'scripts/bootstrap-rke2.sh']:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('kind: Config\n', encoding='utf-8')
            entry = {'id': 'dep-platform', 'name': 'platform-proj', 'project_path': str(root), 'target_type': 'local', 'platform': 'rke2'}
            with patch('backend_api.DEPLOYMENT_HISTORY') as mock_hist, patch('backend_api.AUDIT_LOG'):
                mock_hist.list.return_value = [entry]
                from fastapi.testclient import TestClient
                client = TestClient(backend_api.app)
                resp = client.post('/api/project/validate', data={'deployment_id': 'dep-platform'})
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertTrue(any(item['scope'] == 'platform' for item in data['items']))
                self.assertIn('counts', data)


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
