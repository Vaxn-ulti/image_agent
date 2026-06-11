from pathlib import Path


def test_rag_metadata_audit_passes_for_curated_rag_docs():
    from app.scripts.audit_rag_metadata import audit_rag_metadata

    repo_root = Path(__file__).resolve().parents[3]

    result = audit_rag_metadata(root=repo_root, strict=True)

    assert result["ok"] is True
    assert result["summary_counts"]["workflow"] == 4
    assert result["summary_counts"]["vendor"] >= 20
    assert result["summary_counts"]["contract"] >= 4
    assert result["summary_counts"]["safety"] >= 2
    assert result["missing_fields_by_file"] == {}
    assert result["invalid_fields_by_file"] == {}
    assert result["vendor_provenance_issues"] == []
    assert result["raw_sources_indexed"] is False


def test_rag_metadata_audit_reports_missing_required_fields(tmp_path):
    from app.scripts.audit_rag_metadata import audit_rag_metadata

    vendor = tmp_path / "docs" / "rag" / "vendor"
    vendor.mkdir(parents=True)
    (vendor / "example.md").write_text(
        "---\n"
        "status: curated_summary\n"
        "---\n"
        "# Example\n",
        encoding="utf-8",
    )
    raw_root = vendor / "raw-sources"
    raw_root.mkdir()
    (raw_root / "manifest.json").write_text('{"sources":[]}', encoding="utf-8")

    result = audit_rag_metadata(root=tmp_path, strict=True)

    assert result["ok"] is False
    assert result["missing_fields_by_file"] == {
        "docs/rag/vendor/example.md": ["raw_source_ids", "source_type", "source_url"]
    }


def test_rag_metadata_audit_reports_vendor_source_url_drift(tmp_path):
    from app.scripts.audit_rag_metadata import audit_rag_metadata

    vendor = tmp_path / "docs" / "rag" / "vendor"
    vendor.mkdir(parents=True)
    (vendor / "example.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://example.org/docs?api_key=sk-test-secret\n"
        "raw_source_ids: official_example\n"
        "status: curated_summary\n"
        "---\n"
        "# Example\n",
        encoding="utf-8",
    )
    raw_root = vendor / "raw-sources"
    raw_root.mkdir()
    (raw_root / "manifest.json").write_text(
        '{"sources":[{"id":"official_example","vendor_doc":"example.md","url":"https://example.org/docs"}]}',
        encoding="utf-8",
    )

    result = audit_rag_metadata(root=tmp_path, strict=True)

    assert result["ok"] is False
    assert result["vendor_provenance_issues"] == [
        "docs/rag/vendor/example.md: source_url must match manifest URLs for raw_source_ids"
    ]
