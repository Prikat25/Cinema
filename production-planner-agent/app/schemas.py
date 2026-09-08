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

from pydantic import BaseModel, Field


class ShotDetail(BaseModel):
    shot_number: str = Field(description="Identifier for the shot (e.g., '1A', '2B').")
    shot_type: str = Field(
        description="Type of shot (e.g., 'Wide Shot', 'Medium Close-Up', 'Extreme Close-Up')."
    )
    camera_movement: str = Field(
        description="Camera movement (e.g., 'Pan Left', 'Static', 'Steadicam Tracking', 'Dolly In')."
    )
    shot_requirements: str = Field(
        description="Specific camera, lighting, practical FX, or stunt requirements."
    )


class PropDetail(BaseModel):
    prop_name: str = Field(description="Name or description of the prop item.")
    category: str = Field(
        description="Category of prop (e.g., 'Tech/Prop', 'Weapon', 'Furniture', 'Set Dressing')."
    )


class WardrobeDetail(BaseModel):
    character_name: str = Field(description="Character wearing the costume/wardrobe.")
    costume_description: str = Field(
        description="Description of wardrobe, costume, or makeup requirements."
    )


class SceneDataPayload(BaseModel):
    scene_number: int = Field(description="Numeric scene identifier (e.g., 1, 2).")
    location: str = Field(
        description="Primary location name (e.g., 'NEO-TOKYO ALLEYWAY')."
    )
    interior_exterior: str = Field(
        description="Environment type: 'INT', 'EXT', or 'INT/EXT'."
    )
    time_of_day: str = Field(
        description="Time of day (e.g., 'DAY', 'NIGHT', 'DUSK', 'DAWN')."
    )
    characters_in_scene: list[str] = Field(
        default_factory=list, description="List of characters present in the scene."
    )
    shots: list[ShotDetail] = Field(
        default_factory=list, description="Shot list for filming this scene."
    )
    props_needed: list[PropDetail] = Field(
        default_factory=list, description="Props required for this scene."
    )
    wardrobe_needed: list[WardrobeDetail] = Field(
        default_factory=list,
        description="Wardrobe and costume requirements for this scene.",
    )


class ScriptSceneRecord(BaseModel):
    project_id: str = Field(description="Unique project or screenplay identifier.")
    scene_number: int = Field(description="Scene number matching primary key.")
    location: str = Field(description="Scene location name.")
    time_of_day: str = Field(description="Time of day.")
    characters: list[str] = Field(description="Array of character names.")
    scene_data: str = Field(description="JSON serialized string of SceneDataPayload.")


class TakeAnalysisResult(BaseModel):
    take_id: str = Field(description="Unique identifier for the video/audio take.")
    project_id: str = Field(description="Project or screenplay slug identifier.")
    scene_number: int = Field(description="Numeric scene identifier.")
    shot_number: str = Field(description="Shot identifier (e.g. '1A', '37B').")
    expected_requirements: dict = Field(
        default_factory=dict,
        description="Expected scene/shot requirements pulled from ClickHouse script_scenes.",
    )
    detected_actors: list[str] = Field(
        default_factory=list,
        description="Actors/characters detected visually or audibly in media.",
    )
    detected_props: list[str] = Field(
        default_factory=list, description="Props detected visually in media."
    )
    detected_actions: list[str] = Field(
        default_factory=list, description="Actions and motion beats detected in media."
    )
    detected_dialogue: list[str] = Field(
        default_factory=list, description="Dialogue spoken in media."
    )
    visual_audio_evidence: list[str] = Field(
        default_factory=list,
        description="Visual, acoustic, and environmental evidence notes.",
    )
    requirements_met: bool = Field(
        description="True if take satisfies expected scene/shot requirements; False if major issues exist."
    )
    deviations: list[str] = Field(
        default_factory=list,
        description="List of specific deviations from the expected scene requirements.",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Technical, performance, audio, or visual issues detected.",
    )
    confidence: float = Field(
        description="Confidence score for the analysis between 0.0 and 1.0."
    )
    analysis_summary: str = Field(
        description="Comprehensive summary comparing the take against the production plan."
    )


class TakeAnalysisRecord(BaseModel):
    take_id: str = Field(description="Unique take identifier.")
    project_id: str = Field(description="Project slug identifier.")
    scene_number: int = Field(description="Scene number.")
    shot_number: str = Field(description="Shot identifier.")
    requirements_met: int = Field(description="1 if requirements met, 0 otherwise.")
    confidence: float = Field(description="Confidence score.")
    analysis_data: str = Field(
        description="JSON serialized string of TakeAnalysisResult."
    )
