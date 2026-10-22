"""Command-line entry point for document EPS evaluation and run comparison."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from uuid import uuid4

from ..review.config import resolve_dataset_root
from ..review.errors import ReviewError
from .reports import compare
from .runner import run


def main(argv=None):
    parser = argparse.ArgumentParser(description='Evaluate an EPS extractor against human-reviewed filings.')
    commands = parser.add_subparsers(dest='action', required=True)
    execute = commands.add_parser('run', help='Freeze reviewed inputs, extract and score, or score saved predictions')
    execute.add_argument('--dataset-root', type=Path)
    execute.add_argument('--config', type=Path, required=True, help='Extractor JSON configuration')
    execute.add_argument('--predictions', type=Path, help='Score saved responses without invoking the extractor')
    execute.add_argument('--output', type=Path, help='New run directory; default: FINBOT_DATA_ROOT/filing-evals/runs/<id>')
    comparison = commands.add_parser('compare', help='Print a Markdown comparison of compatible saved runs')
    comparison.add_argument('baseline', type=Path)
    comparison.add_argument('candidate', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == 'compare':
            print(compare(args.baseline, args.candidate))
            return 0
        output = args.output
        if output is None:
            shared = os.environ.get('FINBOT_DATA_ROOT', '').strip()
            if not shared:
                raise ReviewError('Set FINBOT_DATA_ROOT or supply --output for evaluation results.')
            run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
            output = Path(shared) / 'filing-evals/runs' / run_id
        manifest, results = run(resolve_dataset_root(args.dataset_root), output, args.config,
                                predictions=args.predictions, progress=lambda message: print(message, file=sys.stderr))
        summary = results['summary']
        print(f"{manifest['status']}: {summary['correct']} correct, {summary['incorrect']} incorrect, "
              f"{summary['missing']} missing, {summary['extra']} extra; "
              f"{summary['exact_cases']}/{summary['case_count']} exact filings.")
        print(f"Report: {output.expanduser().resolve() / 'REPORT.md'}")
        return 1 if summary['extraction_errors'] else 0
    except (ReviewError, OSError, ImportError, UnicodeError) as error:
        print(f'Evaluation error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
