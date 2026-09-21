import os
import time

from encore.log_cleanup import delete_old_logs


def _touch_with_age(path, age_days: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("log line\n")
    old_time = time.time() - age_days * 86400
    os.utime(path, (old_time, old_time))


def test_returns_empty_list_when_logs_dir_does_not_exist(tmp_path):
    missing = tmp_path / "does-not-exist"

    assert delete_old_logs(missing) == []


def test_deletes_files_older_than_the_threshold_keeps_newer_ones(tmp_path):
    old_file = tmp_path / "dag_id" / "task_id" / "old.log"
    new_file = tmp_path / "dag_id" / "task_id" / "new.log"
    _touch_with_age(old_file, age_days=20)
    _touch_with_age(new_file, age_days=1)

    deleted = delete_old_logs(tmp_path, max_age_days=14)

    assert deleted == [old_file]
    assert not old_file.exists()
    assert new_file.exists()


def test_file_just_under_the_threshold_is_kept(tmp_path):
    just_under = tmp_path / "just_under.log"
    _touch_with_age(just_under, age_days=13.9)

    deleted = delete_old_logs(tmp_path, max_age_days=14)

    assert deleted == []
    assert just_under.exists()


def test_removes_directories_left_empty_after_deletion(tmp_path):
    old_file = tmp_path / "dag_id" / "task_id" / "old.log"
    _touch_with_age(old_file, age_days=30)

    delete_old_logs(tmp_path, max_age_days=14)

    assert not old_file.exists()
    assert not (tmp_path / "dag_id" / "task_id").exists()
    assert not (tmp_path / "dag_id").exists()
    assert tmp_path.exists()  # the root itself is never removed


def test_keeps_directory_that_still_has_a_recent_file(tmp_path):
    old_file = tmp_path / "dag_id" / "old.log"
    new_file = tmp_path / "dag_id" / "new.log"
    _touch_with_age(old_file, age_days=30)
    _touch_with_age(new_file, age_days=1)

    delete_old_logs(tmp_path, max_age_days=14)

    assert not old_file.exists()
    assert new_file.exists()
    assert (tmp_path / "dag_id").exists()


def test_default_threshold_is_7_days(tmp_path):
    borderline_old = tmp_path / "old.log"
    borderline_new = tmp_path / "new.log"
    _touch_with_age(borderline_old, age_days=8)
    _touch_with_age(borderline_new, age_days=6)

    deleted = delete_old_logs(tmp_path)  # no max_age_days passed

    assert deleted == [borderline_old]
    assert borderline_new.exists()
