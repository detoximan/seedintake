import argparse
import io
import unittest
from unittest.mock import patch

from seed_pipeline.cli import run_smoke


class SeedPipelineCliTests(unittest.TestCase):
    def test_smoke_uses_env_driven_github_storage(self) -> None:
        args = argparse.Namespace(
            case="../../test_cases/seed_intake/text_seed_input.md",
            dry_run=False,
            live_google=False,
            mock_google_fail_step=None,
            telegram_message_id=None,
            telegram_user_id=None,
            received_at="2026-04-27T10:00:00+04:00",
            material=None,
            comment="",
            source_url=None,
        )

        with (
            patch.dict(
                "os.environ",
                {
                    "SEED_MARKDOWN_STORAGE": "github",
                    "SEED_GOOGLE_WORKSPACE": "mock",
                    "GITHUB_REPOSITORY": "pashamal/seedintake",
                },
                clear=True,
            ),
            patch("sys.stderr", new=io.StringIO()),
        ):
            exit_code = run_smoke(args)

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
