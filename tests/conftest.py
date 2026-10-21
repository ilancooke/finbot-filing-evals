from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket

import pytest

from finbot_filing_evals.review.validation import load_label_schema


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def snapshot(filing: dict) -> None:
    keys = ("filing_id", "cik", "ticker", "company_name", "form_type", "filed_at", "primary_artifact_id", "artifacts")
    identity = {key: filing[key] for key in keys}
    identity["artifacts"] = sorted(identity["artifacts"], key=lambda artifact: artifact["artifact_id"])
    filing["snapshot_id"] = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not access the network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def make_dataset(tmp_path):
    def make(name="dataset"):
        root = tmp_path / name
        root.mkdir()
        case_paths = []
        for number, ticker, form in ((1, "DEMO", "8-K"), (2, "NEXT", "10-Q")):
            accession = f"{number:010d}-26-{number:06d}"
            case_id = f"{ticker.lower()}-{accession}"
            case_dir = root / "cases" / case_id
            docs_dir = case_dir / "documents"
            docs_dir.mkdir(parents=True)
            artifacts, documents = [], {}
            filenames = ("primary.htm", "release.htm") if number == 1 else ("quarter.htm",)
            for index, filename in enumerate(filenames):
                body = (
                    f"<html><head><style>body {{color:red}}</style></head><body>"
                    f"<h1>{ticker} {filename}</h1><p>Diluted EPS: 4.60</p>"
                    f"<script>window.forbidden = true;</script></body></html>"
                ).encode()
                path = docs_dir / filename
                path.write_bytes(body)
                artifact_id = f"{accession}/{filename}"
                artifacts.append(dict(artifact_id=artifact_id, filename=filename,
                                      s3_uri=f"s3://synthetic-fixture/{case_id}/{filename}",
                                      size_bytes=len(body), document_type=form if index == 0 else "EX-99.1",
                                      content_type="text/html"))
                documents[artifact_id] = dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(body).hexdigest())
            filing = dict(event_type="filing.ready", schema_version="1.0", filing_id=accession,
                          cik=f"{number:010d}", ticker=ticker, company_name=f"Fictional {ticker}",
                          form_type=form, filed_at="2026-10-15T10:00:00.000000Z",
                          ready_at="2026-10-15T10:01:00.000000Z", primary_artifact_id=artifacts[0]["artifact_id"],
                          artifacts=artifacts, extra_upstream_field={"retain": ["original"]})
            snapshot(filing)
            reported = [dict(value="4.60", currency="USD", period="Q3 2026", period_start=None, period_end="2026-09-30"),
                        dict(value="9.00", currency="USD", period="Nine months 2026", period_start="2026-01-01", period_end="2026-09-30"),
                        dict(value="29.43", currency="TWD", period="Q3 2026", period_start=None, period_end="2026-09-30")]
            if number == 2:
                reported = [dict(value="-1.20", currency="USD", period="Q3 2026", period_start="2026-07-01", period_end="2026-09-30")]
            case = dict(case_id=case_id, filing=filing, documents=documents,
                        labels=dict(reported_diluted_eps=reported, adjusted_diluted_eps=[]),
                        review=dict(status="unreviewed", notes=[f"Review note for {ticker}."]),
                        custom_case_metadata={"keep": True})
            save_json(case_dir / "case.json", case)
            case_paths.append((case_dir / "case.json").relative_to(root).as_posix())
        save_json(root / "labels.schema.json", load_label_schema())
        save_json(root / "dataset.json", dict(schema_version="earnings_eps.v1", dataset_id="synthetic-review",
                                              cases=case_paths, label_schema="labels.schema.json",
                                              case_count=2, document_count=3, observation_count=4,
                                              custom_dataset_metadata={"keep": [1, 2]}))
        return root
    return make


@pytest.fixture
def dataset_root(make_dataset):
    return make_dataset()


@pytest.fixture
def case_file(dataset_root):
    manifest = json.loads((dataset_root / "dataset.json").read_text())
    return dataset_root / manifest["cases"][0]


@pytest.fixture
def labels(case_file):
    return deepcopy(json.loads(case_file.read_text())["labels"])
