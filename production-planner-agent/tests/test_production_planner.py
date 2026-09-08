# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json

from app.agent import app, root_agent
from app.schemas import (
    PropDetail,
    SceneDataPayload,
    ScriptSceneRecord,
    ShotDetail,
    WardrobeDetail,
)
from app.tools import insert_scene_to_clickhouse, read_screenplay_file


def test_agent_and_app_initialization():
    """Verify that root_agent and app are properly configured."""
    assert root_agent.name == "production_planner_agent"
    assert app.name == "app"
    tool_names = [
        getattr(t, "name", getattr(t, "__name__", type(t).__name__))
        for t in root_agent.tools
    ]
    assert "read_screenplay_file" in tool_names
    assert "insert_scene_to_clickhouse" in tool_names
    assert "McpToolset" in tool_names


def test_scene_data_and_clickhouse_record_schemas():
    """Verify Pydantic models for scene_data and script_scenes ClickHouse table."""
    shot = ShotDetail(
        shot_number="1A",
        shot_type="Wide Shot",
        camera_movement="Pan Left",
        shot_requirements="Rain machine, neon practical lighting",
    )
    prop = PropDetail(
        prop_name="Glowing Chrome Briefcase",
        category="Tech/Prop",
    )
    wardrobe = WardrobeDetail(
        character_name="NEO",
        costume_description="Reflective cybernetic jacket",
    )

    payload = SceneDataPayload(
        scene_number=1,
        location="NEO-TOKYO ALLEYWAY",
        interior_exterior="EXT",
        time_of_day="DUSK",
        characters_in_scene=["NEO", "ENFORCERS"],
        shots=[shot],
        props_needed=[prop],
        wardrobe_needed=[wardrobe],
    )

    record = ScriptSceneRecord(
        project_id="the-cybernetic-courier",
        scene_number=payload.scene_number,
        location=payload.location,
        time_of_day=payload.time_of_day,
        characters=payload.characters_in_scene,
        scene_data=json.dumps(payload.model_dump()),
    )

    assert record.project_id == "the-cybernetic-courier"
    assert record.scene_number == 1
    assert record.time_of_day == "DUSK"
    assert "NEO" in record.characters
    assert "Rain machine" in record.scene_data


def test_read_screenplay_file_tool(tmp_path):
    """Test reading screenplay text using read_screenplay_file tool."""
    sample_script = tmp_path / "sample_screenplay.txt"
    sample_script.write_text(
        "EXT. NEO-TOKYO ALLEYWAY - DUSK\nNeo runs from enforcers.", encoding="utf-8"
    )

    read_res = read_screenplay_file(str(sample_script))
    assert read_res["status"] == "success"
    assert "NEO-TOKYO ALLEYWAY" in read_res["screenplay_text"]


def test_insert_scene_to_clickhouse_tool_signature():
    """Verify insert_scene_to_clickhouse tool function signature and docstring."""
    assert callable(insert_scene_to_clickhouse)
    assert insert_scene_to_clickhouse.__name__ == "insert_scene_to_clickhouse"
    doc_str = insert_scene_to_clickhouse.__doc__ or ""
    assert "script_scenes" in doc_str
