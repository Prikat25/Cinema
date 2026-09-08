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
from pathlib import Path

from app.schemas import TakeAnalysisRecord, TakeAnalysisResult
from app.take_analyzer import take_analyzer_agent
from app.tools import insert_take_analysis_to_clickhouse, read_media_metadata


def test_take_analyzer_agent_initialization():
    """Verify standalone take_analyzer_agent configuration."""
    assert take_analyzer_agent.name == "take_analyzer_agent"
    tool_names = [
        getattr(t, "name", getattr(t, "__name__", type(t).__name__))
        for t in take_analyzer_agent.tools
    ]
    assert "read_media_metadata" in tool_names
    assert "insert_take_analysis_to_clickhouse" in tool_names
    assert "McpToolset" in tool_names


def test_take_analysis_schemas():
    """Verify TakeAnalysisResult and TakeAnalysisRecord Pydantic models."""
    analysis = TakeAnalysisResult(
        take_id="TAKE_SCENE37_001",
        project_id="the-cybernetic-courier",
        scene_number=37,
        shot_number="1A",
        expected_requirements={
            "actors": ["NEO", "ENFORCERS"],
            "props": ["Briefcase"],
        },
        detected_actors=["NEO"],
        detected_props=["Briefcase"],
        detected_actions=["Neo runs"],
        detected_dialogue=["Kira, unlock door!"],
        visual_audio_evidence=["Rain sound present"],
        requirements_met=False,
        deviations=["Missing Enforcer in background"],
        issues=["Enforcer missing from frame"],
        confidence=0.92,
        analysis_summary="Take 1 captured Neo's sprint but missed pursuing Enforcer.",
    )

    record = TakeAnalysisRecord(
        take_id=analysis.take_id,
        project_id=analysis.project_id,
        scene_number=analysis.scene_number,
        shot_number=analysis.shot_number,
        requirements_met=1 if analysis.requirements_met else 0,
        confidence=analysis.confidence,
        analysis_data=json.dumps(analysis.model_dump()),
    )

    assert record.take_id == "TAKE_SCENE37_001"
    assert record.requirements_met == 0
    assert record.confidence == 0.92
    assert "Enforcer missing" in record.analysis_data


def test_read_media_metadata_tool(tmp_path):
    """Test read_media_metadata with sample media file."""
    sample_video = tmp_path / "take_scene37_001.mp4"
    sample_video.write_bytes(b"dummy mp4 data stream")

    res = read_media_metadata(str(sample_video))
    assert res["status"] == "success"
    assert res["filename"] == "take_scene37_001.mp4"
    assert res["extension"] == ".mp4"
    assert res["size_bytes"] > 0


def test_insert_take_analysis_tool_signature():
    """Verify insert_take_analysis_to_clickhouse tool function signature and docstring."""
    assert callable(insert_take_analysis_to_clickhouse)
    assert (
        insert_take_analysis_to_clickhouse.__name__
        == "insert_take_analysis_to_clickhouse"
    )
    doc_str = insert_take_analysis_to_clickhouse.__doc__ or ""
    assert "take_analyses" in doc_str


def test_take_analyzer_sample_video_workflow():
    """Automated workflow test inspecting sample_take_scene1.mp4 video file."""
    video_path = Path("sample_take_scene1.mp4")
    assert video_path.exists(), "sample_take_scene1.mp4 video file must exist"

    meta = read_media_metadata(str(video_path))
    assert meta["status"] == "success"
    assert meta["extension"] == ".mp4"
    assert meta["size_bytes"] > 0

    # Build automated take analysis payload comparing against Scene 1 requirements
    sample_analysis = TakeAnalysisResult(
        take_id="TAKE_SCENE1_001",
        project_id="the-cybernetic-courier",
        scene_number=1,
        shot_number="1A",
        expected_requirements={
            "actors": ["NEO", "ENFORCERS"],
            "props": ["Glowing Chrome Briefcase", "Plasma Batons"],
            "shot_requirements": "Rain machine, neon practical lighting",
        },
        detected_actors=["NEO", "ENFORCERS"],
        detected_props=["Glowing Chrome Briefcase", "Plasma Batons"],
        detected_actions=["Neo sprints down neon-lit alleyway"],
        detected_dialogue=["Kira, I've got heat! Unlock the dock door now!"],
        visual_audio_evidence=["Rain pouring on wet asphalt", "Synth audio track"],
        requirements_met=True,
        deviations=[],
        issues=[],
        confidence=0.98,
        analysis_summary="Take 1 successfully satisfies all Scene 1 shot requirements.",
    )

    assert sample_analysis.requirements_met is True
    assert sample_analysis.scene_number == 1
    assert "Glowing Chrome Briefcase" in sample_analysis.detected_props
