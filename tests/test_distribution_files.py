from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DistributionFileTests(unittest.TestCase):
    def test_bootstrap_targets_public_release_repository(self):
        script = (ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("T3ND41/SmartDriveOrganizer", script)
        self.assertIn("SmartDriveOrganizer-windows-x64.zip", script)
        self.assertIn("SHA256SUMS.txt", script)

    def test_bootstrap_verifies_hash_before_install(self):
        script = (ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-FileHash", script)
        self.assertIn("$actualHash -ne $expectedHash", script)
        self.assertLess(script.index("$actualHash -ne $expectedHash"), script.index("Copy-Item -LiteralPath $sourceExe"))

    def test_bootstrap_is_per_user_and_does_not_elevate(self):
        script = (ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("$env:LOCALAPPDATA", script)
        self.assertNotIn("Start-Process powershell -Verb RunAs", script)
        self.assertNotIn("-Verb RunAs", script)

    def test_cloudflare_worker_serves_plain_text_at_root(self):
        worker = (ROOT / "cloudflare" / "worker.js").read_text(encoding="utf-8")
        self.assertIn('url.pathname !== "/"', worker)
        self.assertIn('"Content-Type": "text/plain; charset=utf-8"', worker)
        self.assertIn("raw.githubusercontent.com/T3ND41/SmartDriveOrganizer/main/install.ps1", worker)

    def test_release_workflow_builds_windows_binary_and_checksum_manifest(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("windows-latest", workflow)
        self.assertIn("pyinstaller", workflow)
        self.assertIn("SmartDriveOrganizer-windows-x64.zip", workflow)
        self.assertIn("SHA256SUMS.txt", workflow)
        self.assertIn("gh release create", workflow)

    def test_ci_runs_tests_on_windows_and_linux(self):
        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        self.assertIn("windows-latest", workflow)
        self.assertIn("ubuntu-latest", workflow)
        self.assertIn("unittest discover", workflow)

    def test_application_publisher_allowlist_includes_installer_and_release_infrastructure(self):
        from smart_drive_organizer.github_publish import collect_publishable_source_files

        files = collect_publishable_source_files(ROOT)
        required = {
            "install.ps1",
            "SECURITY.md",
            "REPOSITORY_SETUP.md",
            "INSTALLER_ENDPOINTS.txt",
            "VERSION.txt",
            "scripts/build-windows.ps1",
            "scripts/create-and-push-repository.ps1",
            "PUSH_TO_GITHUB.bat",
            ".github/workflows/tests.yml",
            ".github/workflows/release.yml",
            "cloudflare/worker.js",
            "cloudflare/wrangler.toml",
            "cloudflare/README.md",
        }
        self.assertTrue(required.issubset(files.keys()), sorted(required - files.keys()))

    def test_application_publisher_still_excludes_private_local_data(self):
        from smart_drive_organizer.github_publish import collect_publishable_source_files

        files = collect_publishable_source_files(ROOT)
        forbidden_fragments = ("github_publish_settings", "activity", "state.db", "private", "user_settings")
        self.assertFalse(any(any(fragment in path.lower() for fragment in forbidden_fragments) for path in files))

    def test_repository_setup_script_creates_public_repo_and_pushes_tag_safely(self):
        script = (ROOT / "scripts" / "create-and-push-repository.ps1").read_text(encoding="utf-8")
        self.assertIn("$Owner = 'T3ND41'", script)
        self.assertIn("$RepositoryName = 'SmartDriveOrganizer'", script)
        self.assertIn("$gitAddArgs = @(", script)
        self.assertIn("& git @gitAddArgs", script)
        self.assertNotIn("git -C $ProjectRoot add --all", script)
        self.assertIn("unexpectedStaged", script)
        self.assertIn("--public", script)
        self.assertIn("--source $ProjectRoot --remote origin --push", script)
        self.assertIn("refs/tags/$TargetTag", script)
        self.assertIn("never force-pushes", script.lower())
        self.assertNotIn("git push --force", script.lower())
        self.assertIn("authenticatedUser -ine $Owner", script)

    def test_repository_setup_launcher_targets_guided_powershell_script(self):
        launcher = (ROOT / "PUSH_TO_GITHUB.bat").read_text(encoding="utf-8")
        self.assertIn("scripts\\create-and-push-repository.ps1", launcher)
        self.assertIn("-ExecutionPolicy Bypass", launcher)


if __name__ == "__main__":
    unittest.main()
