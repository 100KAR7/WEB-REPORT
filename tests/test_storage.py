from service.storage import RunStore


def test_run_store_lifecycle(tmp_path) -> None:
    db_path = tmp_path / "app.db"
    store = RunStore(str(db_path))

    run_id = store.create_run("https://example.com", {"format": "json"})
    store.mark_running(run_id)
    store.mark_completed(run_id, {"report_path": "output/report.json"})

    run = store.get_run(run_id)
    assert run is not None
    assert run["status"] == "completed"
    assert run["result"]["report_path"] == "output/report.json"
