from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from smart_drive_organizer import github_publish as gh
from smart_drive_organizer.automation import topic_rules_path


class GitHubPublishTests(unittest.TestCase):
    def test_multiple_keyword_rules_export_without_local_absolute_destination(self):
        rules = [{
            "name": "Quotations",
            "keywords": ["QUO", "Quotation", "Quote", "RFQ"],
            "categories": ["Documents"],
            "match_mode": "contains",
            "destination": r"D:\Company Records\Quotations",
        }, {
            "name": "Relative Route",
            "keywords": ["supplier code"],
            "categories": ["Any"],
            "match_mode": "whole_phrase",
            "destination": "Shared/Supplier Records",
        }]
        payload = gh.build_published_rules_payload(rules)
        self.assertEqual(payload["rules"][0]["keywords"], ["QUO", "Quotation", "Quote", "RFQ"])
        self.assertNotIn("destination", payload["rules"][0])
        self.assertEqual(payload["rules"][1]["destination"], "Shared/Supplier Records")

    def test_prompt_after_rule_changes_is_enabled_by_default(self):
        self.assertTrue(gh.load_github_settings(path=Path("/path/that/does/not/exist"))["ask_after_rule_changes"])
        original = [{"name": "Quotations", "keywords": ["QUO"], "categories": ["Documents"], "match_mode": "contains"}]
        updated = [{"name": "Quotations", "keywords": ["QUO", "Quotation", "Quote"], "categories": ["Documents"], "match_mode": "contains"}]
        self.assertTrue(gh.should_offer_github_publish(original, updated, {"ask_after_rule_changes": True}))

    def test_prompt_after_rule_changes_is_not_shown_when_unchanged_or_disabled(self):
        rules = [{"name": "Quotations", "keywords": ["QUO", "Quotation"], "categories": ["Documents"], "match_mode": "contains"}]
        self.assertFalse(gh.should_offer_github_publish(rules, rules, {"ask_after_rule_changes": True}))
        changed = [{"name": "Quotations", "keywords": ["QUO", "Quotation", "Quote"], "categories": ["Documents"], "match_mode": "contains"}]
        self.assertFalse(gh.should_offer_github_publish(rules, changed, {"ask_after_rule_changes": False}))

    def test_publish_payload_keeps_multiple_keywords_but_excludes_personal_destination(self):
        rules = [{
            "name": "Quotations", "keywords": ["QUO", "Quotation", "Quote", "RFQ"],
            "categories": ["Documents"], "match_mode": "contains",
            "destination": r"D:\Private\Tendai\Quotations",
        }]
        payload = gh.build_published_rules_payload(rules)
        self.assertEqual(payload["rules"][0]["keywords"], ["QUO", "Quotation", "Quote", "RFQ"])
        self.assertNotIn("destination", payload["rules"][0])

    def test_github_publish_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "github_settings.json"
            value = {
                "repository_url": "https://github.com/example/sdo-test",
                "repository_path": temp,
                "author_name": "Tendai Mbewe",
                "author_email": "tendai@example.test",
                "ask_after_rule_changes": False,
            }
            gh.save_github_settings(value, path)
            self.assertEqual(gh.load_github_settings(path), value)

    def test_published_repository_rules_seed_new_local_user_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "appdata"
            published = root / "repo" / "config" / "published_topic_rules.json"
            published.parent.mkdir(parents=True)
            published.write_text(json.dumps({"schema_version": 1, "rules": [{
                "name": "Quotations", "keywords": ["QUO", "Quotation", "Quote"],
                "categories": ["Documents"], "match_mode": "contains",
            }]}), encoding="utf-8")
            local = topic_rules_path(app_dir, published)
            data = json.loads(local.read_text(encoding="utf-8"))
            self.assertEqual(data[0]["keywords"], ["QUO", "Quotation", "Quote"])

    def test_published_rules_merge_new_keywords_without_overriding_local_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "appdata"
            app_dir.mkdir()
            dest = root / "personal" / "quotations"
            (app_dir / "topic_rules.json").write_text(json.dumps([{
                "name": "Quotations", "keywords": ["QUO"], "categories": ["Documents"],
                "match_mode": "contains", "destination": str(dest),
            }]), encoding="utf-8")
            published = root / "repo" / "config" / "published_topic_rules.json"
            published.parent.mkdir(parents=True)
            published.write_text(json.dumps({"rules": [{
                "name": "Quotations", "keywords": ["Quotation", "Quote"],
                "categories": ["Documents"], "match_mode": "contains",
            }, {
                "name": "New Group", "keywords": ["new-group"], "categories": ["Any"],
            }]}), encoding="utf-8")
            local = topic_rules_path(app_dir, published)
            from smart_drive_organizer.classifier import load_topic_rules
            merged = load_topic_rules(local)
            quotations = next(item for item in merged if item["name"] == "Quotations")
            self.assertEqual(quotations["keywords"], ["QUO", "Quotation", "Quote"])
            self.assertEqual(quotations["destination"], str(dest))
            self.assertIn("New Group", {item["name"] for item in merged})


    def test_github_repository_url_accepts_https_and_ssh_forms(self):
        self.assertEqual(
            gh.github_repository_identity("https://github.com/Example/SmartDriveOrganizer.git"),
            ("example", "smartdriveorganizer"),
        )
        self.assertEqual(
            gh.github_repository_identity("git@github.com:Example/SmartDriveOrganizer.git"),
            ("example", "smartdriveorganizer"),
        )
        self.assertEqual(
            gh.github_repository_identity("ssh://git@github.com/Example/SmartDriveOrganizer"),
            ("example", "smartdriveorganizer"),
        )

    def test_github_repository_url_rejects_non_github_and_embedded_credentials(self):
        for value in (
            "https://gitlab.com/example/repo",
            "https://user:token@github.com/example/repo",
            "https://github.com/example/repo/tree/main",
            "https://github.com/example/repo?token=secret",
        ):
            with self.subTest(value=value), self.assertRaises(gh.GitHubPublishError):
                gh.normalize_github_repository_url(value)

    def test_default_repository_workspace_is_separate_and_derived_from_url(self):
        with tempfile.TemporaryDirectory() as temp:
            path = gh.default_repository_workspace_path(
                "https://github.com/Example/SmartDriveOrganizer", Path(temp)
            )
            self.assertEqual(path, Path(temp) / "example__smartdriveorganizer")

    def test_legacy_settings_migrate_repository_url_stored_in_old_path_field(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            path.write_text(json.dumps({"repository_path": "https://github.com/example/repo"}), encoding="utf-8")
            loaded = gh.load_github_settings(path)
            self.assertEqual(loaded["repository_url"], "https://github.com/example/repo")
            self.assertEqual(loaded["repository_path"], "")

    def test_source_publisher_allowlist_excludes_private_runtime_and_user_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "run.py").write_text("print('app')", encoding="utf-8")
            package = root / "smart_drive_organizer"
            package.mkdir()
            (package / "gui.py").write_text("# GUI", encoding="utf-8")
            config = root / "config"
            config.mkdir()
            (config / "topic_rules.example.json").write_text("{}", encoding="utf-8")
            (config / "keyword_rules.json").write_text("PERSONAL RULES", encoding="utf-8")
            (root / ".env").write_text("TOKEN=secret", encoding="utf-8")
            (root / "documents.pdf").write_bytes(b"not source")
            files = gh.collect_publishable_source_files(root)
            self.assertEqual(set(files), {"run.py", "smart_drive_organizer/gui.py", "config/topic_rules.example.json"})

    def test_source_publisher_blocks_common_credential_patterns(self):
        with self.assertRaises(gh.GitHubPublishError):
            gh._check_source_for_secrets("module.py", b'TOKEN = "' + b"ghp_" + b"abcdefghijklmnopqrstuvwxyz1234567890" + b'"')
        with self.assertRaises(gh.GitHubPublishError):
            gh._check_source_for_secrets("key.pem", b"-----BEGIN " + b"PRIVATE KEY-----")

    def test_connect_github_repository_clones_once_from_pasted_url(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._make_github_clone(root)
            workspace = root / "managed" / "checkout"
            real_git = gh._git
            calls = []

            def fake_git(args, cwd=None, timeout=45):
                calls.append(list(args))
                if args and args[0] == "clone":
                    clone_result = subprocess.run(["git", "clone", str(source), str(workspace)], capture_output=True, text=True)
                    subprocess.run(["git", "remote", "set-url", "origin", "https://github.com/example/sdo-test.git"], cwd=workspace, check=True)
                    return subprocess.CompletedProcess(["git", *args], clone_result.returncode, clone_result.stdout, clone_result.stderr)
                return real_git(args, cwd=cwd, timeout=timeout)

            with patch.object(gh, "_git", side_effect=fake_git):
                first = gh.connect_github_repository("https://github.com/example/sdo-test", workspace)
                second = gh.connect_github_repository("https://github.com/example/sdo-test", workspace)
            self.assertEqual(first["branch"], "main")
            self.assertEqual(second["path"], first["path"])
            self.assertEqual(sum(1 for call in calls if call and call[0] == "clone"), 1)


    def test_connect_github_repository_prepares_empty_repository_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bare = root / "empty.git"
            subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True, check=True)
            workspace = root / "managed" / "empty-checkout"
            real_git = gh._git

            def fake_git(args, cwd=None, timeout=45):
                if args and args[0] == "clone":
                    clone_result = subprocess.run(["git", "clone", str(bare), str(workspace)], capture_output=True, text=True)
                    subprocess.run(
                        ["git", "remote", "set-url", "origin", "https://github.com/example/empty-repo.git"],
                        cwd=workspace, check=True,
                    )
                    return subprocess.CompletedProcess(["git", *args], clone_result.returncode, clone_result.stdout, clone_result.stderr)
                return real_git(args, cwd=cwd, timeout=timeout)

            with patch.object(gh, "_git", side_effect=fake_git):
                info = gh.connect_github_repository("https://github.com/example/empty-repo", workspace)
            self.assertIn(info["branch"], {"main", "master"})
            self.assertTrue((workspace / ".git").is_dir())

    def test_application_source_preview_and_publish_only_allowlisted_changed_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self._make_github_clone(root)
            source = root / "source"
            (source / "smart_drive_organizer").mkdir(parents=True)
            (source / "run.py").write_text("print('new app')\n", encoding="utf-8")
            (source / "smart_drive_organizer" / "gui.py").write_text("# updated GUI\n", encoding="utf-8")
            (source / "config").mkdir()
            (source / "config" / "keyword_rules.json").write_text("PRIVATE\n", encoding="utf-8")
            real_git = gh._git
            calls = []

            def fake_git(args, cwd=None, timeout=45):
                calls.append(list(args))
                if args and args[0] == "ls-remote":
                    return subprocess.CompletedProcess(["git", *args], 0, "", "")
                if args and args[0] == "push":
                    return subprocess.CompletedProcess(["git", *args], 0, "pushed", "")
                return real_git(args, cwd=cwd, timeout=timeout)

            with patch.object(gh, "_git", side_effect=fake_git):
                preview = gh.preview_application_update_to_github(repo, source)
                self.assertEqual(preview["added"], ["run.py", "smart_drive_organizer/gui.py"])
                self.assertNotIn("config/keyword_rules.json", preview["added"])
                result = gh.publish_application_update_to_github(repo, source)
            self.assertEqual(result["status"], "pushed")
            changed = subprocess.run(
                ["git", "show", "--pretty=format:", "--name-only", "HEAD"],
                cwd=repo, capture_output=True, text=True, check=True,
            ).stdout.splitlines()
            self.assertEqual(set(changed), {"run.py", "smart_drive_organizer/gui.py"})
            self.assertFalse((repo / "config" / "keyword_rules.json").exists())
            self.assertTrue(any(call and call[0] == "push" for call in calls))

    def test_source_preview_refuses_to_publish_when_repository_has_unrelated_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self._make_github_clone(root)
            (repo / "private-work.txt").write_text("do not publish", encoding="utf-8")
            source = root / "source"
            source.mkdir()
            (source / "run.py").write_text("print('ok')", encoding="utf-8")
            with self.assertRaisesRegex(gh.GitHubPublishError, "other uncommitted changes"):
                gh.preview_application_update_to_github(repo, source)

    def _make_github_clone(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=repo, check=True)
        (repo / "README.md").write_text("test repository\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/example/sdo-test.git"], cwd=repo, check=True)
        return repo

    def test_inspect_github_repo_requires_github_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self._make_github_clone(Path(temp))
            info = gh.inspect_github_repository(repo)
            self.assertEqual(info["branch"], "main")
            self.assertIn("github.com", info["remote"])
            subprocess.run(["git", "remote", "set-url", "origin", "https://gitlab.com/example/sdo-test.git"], cwd=repo, check=True)
            with self.assertRaises(gh.GitHubPublishError):
                gh.inspect_github_repository(repo)

    def test_publish_commits_only_shared_rule_config_and_pushes(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self._make_github_clone(Path(temp))
            real_git = gh._git
            calls: list[list[str]] = []

            def fake_git(args, cwd=None, timeout=45):
                calls.append(list(args))
                if args and args[0] == "ls-remote":
                    return subprocess.CompletedProcess(["git", *args], 0, "", "")
                if args and args[0] == "push":
                    return subprocess.CompletedProcess(["git", *args], 0, "", "")
                return real_git(args, cwd=cwd, timeout=timeout)

            rules = [{"name": "Quotations", "keywords": ["QUO", "Quotation", "Quote"], "categories": ["Documents"], "match_mode": "contains", "destination": r"D:\private\records"}]
            with patch.object(gh, "_git", side_effect=fake_git):
                result = gh.publish_topic_rules_to_github(repo, rules)
            self.assertEqual(result["status"], "pushed")
            self.assertTrue((repo / "config" / "published_topic_rules.json").is_file())
            committed = subprocess.run(["git", "show", "HEAD:config/published_topic_rules.json"], cwd=repo, capture_output=True, text=True, check=True).stdout
            payload = json.loads(committed)
            self.assertEqual(payload["rules"][0]["keywords"], ["QUO", "Quotation", "Quote"])
            self.assertNotIn("destination", payload["rules"][0])
            changed_paths = subprocess.run(["git", "show", "--pretty=format:", "--name-only", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.splitlines()
            self.assertEqual(changed_paths, ["config/published_topic_rules.json"])
            self.assertTrue(any(call and call[0] == "push" for call in calls))

    def test_publish_refuses_to_mix_other_uncommitted_repo_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self._make_github_clone(Path(temp))
            (repo / "my-work.txt").write_text("not part of organizer publishing", encoding="utf-8")
            with self.assertRaisesRegex(gh.GitHubPublishError, "other uncommitted changes"):
                gh.publish_topic_rules_to_github(repo, [{"name": "Quotations", "keywords": ["QUO"]}])


if __name__ == "__main__":
    unittest.main()
