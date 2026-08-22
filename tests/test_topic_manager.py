"""Tests for TopicManager selection, history, and duplicate prevention."""

import pytest
from pathlib import Path
from src.topic_manager import TopicManager
from src.utils import save_json


@pytest.fixture
def temp_topic_env(tmp_path: Path):
    topics_path = tmp_path / "topics.json"
    history_path = tmp_path / "topic_history.json"

    initial_topics = [
        {"id": "t1", "title": "Topic One", "learning_objective": "Obj 1"},
        {"id": "t2", "title": "Topic Two", "learning_objective": "Obj 2"},
        {"id": "t3", "title": "Topic Three", "learning_objective": "Obj 3"}
    ]
    save_json(topics_path, initial_topics)
    save_json(history_path, {"used_topics": []})

    return TopicManager(topics_file=topics_path, history_file=history_path)


def test_select_first_topic(temp_topic_env):
    """Test selecting the first unused topic."""
    mgr = temp_topic_env
    selected = mgr.select_next_topic()
    assert selected["id"] == "t1"


def test_no_repeat_until_all_topics_used(temp_topic_env):
    """Test that used topics are not selected again until the catalog is exhausted."""
    mgr = temp_topic_env

    # Select and mark t1
    s1 = mgr.select_next_topic()
    assert s1["id"] == "t1"
    mgr.mark_topic_as_used(s1, "ep_01")

    # Next must be t2
    s2 = mgr.select_next_topic()
    assert s2["id"] == "t2"
    mgr.mark_topic_as_used(s2, "ep_02")

    # Next must be t3
    s3 = mgr.select_next_topic()
    assert s3["id"] == "t3"
    mgr.mark_topic_as_used(s3, "ep_03")

    # All topics used -> replenishment / cycle reset
    s4 = mgr.select_next_topic()
    assert s4 is not None
    assert "title" in s4


def test_forced_topic_selection(temp_topic_env):
    """Test forcing a specific topic title."""
    mgr = temp_topic_env
    forced = mgr.select_next_topic(forced_topic_title="Topic Three")
    assert forced["id"] == "t3"
    assert forced["title"] == "Topic Three"

    # Forcing an unlisted topic creates a clean custom topic object
    custom = mgr.select_next_topic(forced_topic_title="Dinosaurs and Volcanoes")
    assert custom["title"] == "Dinosaurs and Volcanoes"
    assert custom["id"].startswith("custom_")
