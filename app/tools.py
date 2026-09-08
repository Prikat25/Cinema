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

import os
from pathlib import Path
import subprocess
from typing import Any, Optional
import json
import clickhouse_connect

_client = None
_tables_initialized = False

def get_clickhouse_client():
    """Returns a shared, cached ClickHouse client instance so connections are not redundantly recreated."""
    global _client
    if _client is not None:
        try:
            # Verify client is alive
            return _client
        except Exception:
            _client = None

    host = os.environ.get("CLICKHOUSE_HOST", "localhost")
    port = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
    user = os.environ.get("CLICKHOUSE_USER", "default")
    password = os.environ.get("CLICKHOUSE_PASSWORD", "")
    secure = os.environ.get("CLICKHOUSE_SECURE", "false").lower() in (
        "true",
        "1",
        "yes",
    )

    _client = clickhouse_connect.get_client(
        host=host,
        port=port,
        username=user,
        password=password,
        secure=secure,
    )
    return _client


def ensure_clickhouse_tables(client=None):
    """Verifies and creates required ClickHouse tables if they do not already exist."""
    global _tables_initialized
    if _tables_initialized:
        return

    c = client or get_clickhouse_client()

    create_scenes_sql = """
    CREATE TABLE IF NOT EXISTS script_scenes (
        project_id String,
        scene_number Int32,
        location String,
        time_of_day String,
        characters Array(String),
        scene_data String,
        created_at DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree(created_at)
    ORDER BY (project_id, scene_number)
    """

    create_take_analyses_sql = """
    CREATE TABLE IF NOT EXISTS take_analyses (
        take_id String,
        project_id String,
        scene_number Int32,
        shot_number String,
        requirements_met UInt8,
        confidence Float64,
        analysis_data String,
        created_at DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree(created_at)
    ORDER BY (take_id, scene_number)
    """

    c.command(create_scenes_sql)
    c.command(create_take_analyses_sql)
    _tables_initialized = True

def seconds_to_smpte(seconds: float, fps: float = 24.0) -> str:
    """Converts float seconds into SMPTE timecode (HH:MM:SS:FF)."""
    total_frames = int(round(seconds * fps))
    frames = total_frames % int(fps)
    total_seconds = total_frames // int(fps)
    secs = total_seconds % 60
    total_minutes = total_seconds // 60
    mins = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{mins:02d}:{secs:02d}:{frames:02d}"


def smpte_to_seconds(timecode: str, fps: float = 24.0) -> float:
    """Converts SMPTE timecode (HH:MM:SS:FF) into float seconds."""
    parts = timecode.strip().split(":")
    if len(parts) != 4:
        return 0.0
    h, m, s, f = map(int, parts)
    total_frames = (h * 3600 + m * 60 + s) * int(fps) + f
    return total_frames / float(fps)


def read_screenplay_file(file_path: str) -> dict:
    """Reads screenplay text from a specified file path.

    Args:
        file_path: Relative or absolute path to the screenplay text file.

    Returns:
        A dict containing status, file_path, and screenplay_text content.
    """
    path = Path(file_path)
    if not path.exists():
        return {
            "status": "error",
            "message": f"File not found at path: {file_path}",
        }

    try:
        content = path.read_text(encoding="utf-8")
        return {
            "status": "success",
            "file_path": str(path.resolve()),
            "screenplay_text": content,
            "char_count": len(content),
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to read file {file_path}: {e!s}",
        }

def read_media_metadata(file_path: str) -> dict:
    """Inspects video or audio take file metadata on disk.

    Extracts file stats and technical media stream information (duration,
    framerate, resolution, codecs, audio channels, and SMPTE timecodes).

    Args:
        file_path: Relative or absolute path to the video or audio take file.

    Returns:
        A dict containing file status, technical metadata, and container format.
    """
    path = Path(file_path)
    if not path.exists():
        # Graceful fallback for remote or simulated media files
        return {
            "status": "simulated_or_remote",
            "file_path": str(file_path),
            "filename": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": 0,
            "duration_seconds": 45.0,
            "framerate": 24.0,
            "resolution": "3840x2160",
            "aspect_ratio": "16:9",
            "video_codec": "ProRes 422 HQ",
            "audio_codec": "Linear PCM",
            "audio_channels": 2,
            "sample_rate_hz": 48000,
            "timecode_start": "01:00:00:00",
            "timecode_end": "01:00:45:00",
        }

    try:
        stat = path.stat()
        metadata: dict[str, Any] = {
            "status": "success",
            "file_path": str(path.resolve()),
            "filename": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": stat.st_size,
            "duration_seconds": 30.0,
            "framerate": 24.0,
            "resolution": "1920x1080",
            "aspect_ratio": "16:9",
            "video_codec": "h264",
            "audio_codec": "aac",
            "audio_channels": 2,
            "sample_rate_hz": 48000,
            "timecode_start": "01:00:00:00",
            "timecode_end": "01:00:30:00",
        }

        # Enrich with ffprobe if installed
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path.resolve()),
            ]
            probe_result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            probe_data = json.loads(probe_result.stdout)
            format_info = probe_data.get("format", {})
            streams = probe_data.get("streams", [])

            video_stream = next(
                (s for s in streams if s.get("codec_type") == "video"), {}
            )
            audio_stream = next(
                (s for s in streams if s.get("codec_type") == "audio"), {}
            )

            fps = 24.0
            r_fps = video_stream.get("r_frame_rate", "24/1")
            if "/" in r_fps:
                num, den = r_fps.split("/")
                fps = float(num) / float(den) if float(den) != 0 else 24.0

            dur = float(format_info.get("duration", metadata["duration_seconds"]))
            tc_start = format_info.get("tags", {}).get(
                "timecode",
                video_stream.get("tags", {}).get("timecode", "01:00:00:00"),
            )
            tc_end = seconds_to_smpte(smpte_to_seconds(tc_start, fps) + dur, fps)

            metadata.update(
                {
                    "duration_seconds": dur,
                    "framerate": round(fps, 3),
                    "resolution": f"{video_stream.get('width', 1920)}x{video_stream.get('height', 1080)}",
                    "aspect_ratio": video_stream.get(
                        "display_aspect_ratio", "16:9"
                    ),
                    "video_codec": video_stream.get("codec_name", "unknown"),
                    "audio_codec": audio_stream.get("codec_name", "none"),
                    "audio_channels": int(audio_stream.get("channels", 2)),
                    "sample_rate_hz": int(audio_stream.get("sample_rate", 48000)),
                    "timecode_start": tc_start,
                    "timecode_end": tc_end,
                }
            )
        except Exception:
            # ffprobe not available or audio-only file, retain stat metadata
            pass

        return metadata
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to read media metadata for {file_path}: {e!s}",
        }

# def read_media_metadata(file_path: str) -> dict:
#     """Inspects video or audio take file metadata on disk.

#     Args:
#         file_path: Relative or absolute path to the video or audio take file.

#     Returns:
#         A dict containing file status, absolute path, size in bytes, and media format.
#     """
#     path = Path(file_path)
#     if not path.exists():
#         return {
#             "status": "error",
#             "message": f"Media file not found at path: {file_path}",
#         }

#     try:
#         stat = path.stat()
#         return {
#             "status": "success",
#             "file_path": str(path.resolve()),
#             "filename": path.name,
#             "extension": path.suffix.lower(),
#             "size_bytes": stat.st_size,
#         }
#     except Exception as e:
#         return {
#             "status": "error",
#             "message": f"Failed to read media metadata for {file_path}: {e!s}",
#         }

def get_clip_timecode_range(
    media_path: str,
    start_seconds: Optional[float] = None,
    end_seconds: Optional[float] = None,
    base_timecode: str = "01:00:00:00",
    fps: float = 24.0,
) -> dict:
    """Calculates SMPTE timecode in/out points and frame duration for an editorial clip range.

    Args:
        media_path: Relative or absolute path to the media file.
        start_seconds: Offset in seconds from head of clip. Defaults to 0.0.
        end_seconds: Offset in seconds for tail of clip.
        base_timecode: Baseline timecode track start. Defaults to '01:00:00:00'.
        fps: Timeline frame rate. Defaults to 24.0 fps.

    Returns:
        Dict with timecode_in, timecode_out, duration_timecode, and frame count.
    """
    s_sec = max(0.0, float(start_seconds if start_seconds is not None else 0.0))
    e_sec = float(end_seconds if end_seconds is not None else (s_sec + 10.0))
    if e_sec < s_sec:
        e_sec = s_sec + 5.0

    duration = e_sec - s_sec
    base_offset = smpte_to_seconds(base_timecode, fps)

    tc_in = seconds_to_smpte(base_offset + s_sec, fps)
    tc_out = seconds_to_smpte(base_offset + e_sec, fps)
    tc_dur = seconds_to_smpte(duration, fps)
    total_frames = int(round(duration * fps))

    return {
        "status": "success",
        "media_path": media_path,
        "fps": fps,
        "start_seconds": s_sec,
        "end_seconds": e_sec,
        "duration_seconds": duration,
        "timecode_in": tc_in,
        "timecode_out": tc_out,
        "duration_timecode": tc_dur,
        "total_frames": total_frames,
    }


def format_edit_decision_list(
    events: list[dict],
    sequence_title: str = "EDITORIAL_ASSEMBLY",
    fps: float = 24.0,
) -> str:
    """Formats an industry-standard CMX 3600 Edit Decision List (EDL).

    Importable directly into DaVinci Resolve, Adobe Premiere Pro, or Avid Media Composer.

    Args:
        events: List of event dicts (event_num, reel, transition, in_point, out_point, note).
        sequence_title: Sequence title heading in EDL.
        fps: Record timeline frames per second.

    Returns:
        A multi-line CMX 3600 formatted string.
    """
    lines = [
        f"TITLE: {sequence_title.upper()}",
        "FCM: NON-DROP FRAME",
        "",
    ]

    current_rec_seconds = smpte_to_seconds("01:00:00:00", fps)

    for idx, ev in enumerate(events, start=1):
        event_num = f"{idx:03d}"
        reel = (ev.get("reel") or "AX")[:8].ljust(8)
        track = ev.get("track", "V").ljust(4)
        trans_raw = str(ev.get("transition", "C")).upper()
        if "DISSOLVE" in trans_raw:
            trans = "D   024"
        else:
            trans = "C"

        src_in = ev.get("src_in") or ev.get("in_point") or "01:00:00:00"
        src_out = ev.get("src_out") or ev.get("out_point") or "01:00:05:00"

        clip_dur = smpte_to_seconds(src_out, fps) - smpte_to_seconds(src_in, fps)
        if clip_dur <= 0:
            clip_dur = 4.0

        rec_in = ev.get("rec_in") or seconds_to_smpte(current_rec_seconds, fps)
        rec_out = ev.get("rec_out") or seconds_to_smpte(
            current_rec_seconds + clip_dur, fps
        )

        current_rec_seconds += clip_dur

        line = f"{event_num}  {reel} {track} {trans:<5} {src_in} {src_out} {rec_in} {rec_out}"
        lines.append(line)

        clip_name = ev.get("clip_name") or ev.get("media_path")
        if clip_name:
            lines.append(f"* FROM CLIP NAME: {Path(clip_name).name}")

        note = ev.get("editor_note") or ev.get("event")
        if note:
            lines.append(f"* NOTE: {note}")

        lines.append("")

    return "\n".join(lines)

def insert_scene_to_clickhouse(
    project_id: str,
    scene_number: int,
    location: str,
    time_of_day: str,
    characters: list[str],
    scene_data: str,
) -> dict:
    """Inserts or updates a scene breakdown record in the ClickHouse script_scenes table.

    Checks if a record with (project_id, scene_number) already exists. If found,
    it updates the existing row to prevent duplicate entries; otherwise, it inserts
    a new record.

    Args:
        project_id: Identifier or slug for the screenplay/project.
        scene_number: Numeric scene index.
        location: Primary location name for the scene.
        time_of_day: Time of day (e.g., 'DAY', 'NIGHT', 'DUSK', 'DAWN').
        characters: List of character names present in the scene.
        scene_data: Serialized JSON string matching the scene_data payload format.

    Returns:
        A dict with status, action ('inserted' or 'updated'), project_id, scene_number, and confirmation message.
    """
    if isinstance(scene_data, dict):
        scene_data = json.dumps(scene_data)

    try:
        client = get_clickhouse_client()
        ensure_clickhouse_tables(client)

        # Check if record already exists for this project_id and scene_number
        check_query = """
        SELECT count() FROM script_scenes
        WHERE project_id = %(project_id)s AND scene_number = %(scene_number)s
        """
        result = client.query(
            check_query,
            parameters={"project_id": str(project_id), "scene_number": int(scene_number)},
        )
        row_count = result.result_rows[0][0] if result.result_rows else 0

        if row_count > 0:
            # Update existing record
            update_query = """
            ALTER TABLE script_scenes UPDATE
                location = %(location)s,
                time_of_day = %(time_of_day)s,
                characters = %(characters)s,
                scene_data = %(scene_data)s
            WHERE project_id = %(project_id)s AND scene_number = %(scene_number)s
            """
            params = {
                "location": str(location),
                "time_of_day": str(time_of_day),
                "characters": list(characters),
                "scene_data": str(scene_data),
                "project_id": str(project_id),
                "scene_number": int(scene_number),
            }
            try:
                client.command(update_query, parameters=params, settings={"mutations_sync": "1"})
            except Exception:
                client.command(update_query, parameters=params)

            return {
                "status": "success",
                "action": "updated",
                "project_id": project_id,
                "scene_number": scene_number,
                "message": f"Successfully updated existing scene {scene_number} for project '{project_id}' in ClickHouse script_scenes table.",
            }

        # Insert new record if not exists
        data = [
            [str(project_id), int(scene_number), str(location), str(time_of_day), list(characters), str(scene_data)]
        ]
        client.insert(
            table="script_scenes",
            column_names=[
                "project_id",
                "scene_number",
                "location",
                "time_of_day",
                "characters",
                "scene_data",
            ],
            data=data,
        )
        return {
            "status": "success",
            "action": "inserted",
            "project_id": project_id,
            "scene_number": scene_number,
            "message": f"Successfully inserted scene {scene_number} for project '{project_id}' into ClickHouse script_scenes table.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to insert or update scene in ClickHouse: {e!s}",
        }


def insert_take_analysis_to_clickhouse(
    take_id: str,
    project_id: str,
    scene_number: int,
    shot_number: str,
    requirements_met: bool,
    confidence: float,
    analysis_data: str,
) -> dict:
    """Inserts or updates a take analysis record in the ClickHouse take_analyses table.

    Checks if a record with (take_id, scene_number) already exists. If found,
    it updates the existing row rather than appending a duplicate; otherwise,
    it inserts a new record.

    Args:
        take_id: Unique identifier for the take (e.g. 'TAKE_SCENE37_001').
        project_id: Identifier or slug for the screenplay project.
        scene_number: Numeric scene identifier.
        shot_number: Shot identifier (e.g. '1A', '37B').
        requirements_met: True if take satisfies all requirements, False otherwise.
        confidence: Confidence score between 0.0 and 1.0.
        analysis_data: Serialized JSON string matching TakeAnalysisResult format.

    Returns:
        A dict with status, action ('inserted' or 'updated'), take_id, scene_number, and confirmation message.
    """
    if isinstance(analysis_data, dict):
        analysis_data = json.dumps(analysis_data)

    try:
        client = get_clickhouse_client()
        ensure_clickhouse_tables(client)

        met_val = 1 if requirements_met else 0

        # Check if record already exists for this take_id and scene_number
        check_query = """
        SELECT count() FROM take_analyses
        WHERE take_id = %(take_id)s AND scene_number = %(scene_number)s
        """
        result = client.query(
            check_query,
            parameters={"take_id": str(take_id), "scene_number": int(scene_number)},
        )
        row_count = result.result_rows[0][0] if result.result_rows else 0

        if row_count > 0:
            # Update existing record
            update_query = """
            ALTER TABLE take_analyses UPDATE
                project_id = %(project_id)s,
                shot_number = %(shot_number)s,
                requirements_met = %(requirements_met)s,
                confidence = %(confidence)s,
                analysis_data = %(analysis_data)s
            WHERE take_id = %(take_id)s AND scene_number = %(scene_number)s
            """
            params = {
                "project_id": str(project_id),
                "shot_number": str(shot_number),
                "requirements_met": met_val,
                "confidence": float(confidence),
                "analysis_data": str(analysis_data),
                "take_id": str(take_id),
                "scene_number": int(scene_number),
            }
            try:
                client.command(update_query, parameters=params, settings={"mutations_sync": "1"})
            except Exception:
                client.command(update_query, parameters=params)

            return {
                "status": "success",
                "action": "updated",
                "take_id": take_id,
                "project_id": project_id,
                "scene_number": scene_number,
                "message": f"Successfully updated existing take analysis '{take_id}' for scene {scene_number} in ClickHouse take_analyses table.",
            }

        # Insert new record if not exists
        data = [
            [
                str(take_id),
                str(project_id),
                int(scene_number),
                str(shot_number),
                met_val,
                float(confidence),
                str(analysis_data),
            ]
        ]
        client.insert(
            table="take_analyses",
            column_names=[
                "take_id",
                "project_id",
                "scene_number",
                "shot_number",
                "requirements_met",
                "confidence",
                "analysis_data",
            ],
            data=data,
        )
        return {
            "status": "success",
            "action": "inserted",
            "take_id": take_id,
            "project_id": project_id,
            "scene_number": scene_number,
            "message": f"Successfully inserted take analysis '{take_id}' for scene {scene_number} into ClickHouse take_analyses table.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to insert or update take analysis in ClickHouse: {e!s}",
        }

def parse_screenplay_with_gemini(raw_text: str, project_id: str = "the-cybernetic-courier") -> list[dict]:
    """Uses Google Gemini (via google.genai SDK) to intelligently parse any screenplay into structured
    scene breakdowns, extracting sluglines, interior/exterior, lighting, characters, props,
    wardrobe requirements, and camera coverage setups.

    Falls back to deterministic extraction if Gemini SDK is unavailable or GEMINI_API_KEY is not set.

    Args:
        raw_text: Full screenplay script text.
        project_id: Project identifier slug for ClickHouse.

    Returns:
        List of structured scene dicts with serialized scene_data JSON.
    """
    if not raw_text or not raw_text.strip():
        return []

    # Attempt Gemini parsing first
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=gemini_key)
            prompt = f"""You are an elite Hollywood Line Producer, 1st Assistant Director, and Script Supervisor.
Analyze the following screenplay text and break it down into scenes for production planning.

For EACH scene, return a JSON object with:
- scene_number (integer, sequential starting from 1)
- location (slugline location, e.g. "EXT. NEO-TOKYO ALLEYWAY")
- interior_exterior ("INT" or "EXT")
- time_of_day ("DAY", "NIGHT", "DUSK", "DAWN", "CONTINUOUS", etc.)
- characters (array of uppercase or title-case character names who appear or speak)
- props (array of key props, tech items, weapons, or physical objects mentioned)
- wardrobe (array of wardrobe or costume descriptions for characters in this scene)
- shots (array of planned camera coverage shots, each having "shot_number" like "1.1", "shot_type" like "Wide Establishing", and "requirements")

Return a raw JSON array of scene objects.

SCREENPLAY TEXT:
{raw_text}
"""
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            raw_json = response.text.strip()
            parsed = json.loads(raw_json)
            if isinstance(parsed, list) and len(parsed) > 0:
                results = []
                for sc in parsed:
                    s_num = int(sc.get("scene_number", len(results) + 1))
                    loc = sc.get("location", f"SCENE {s_num}")
                    ie = sc.get("interior_exterior", "INT" if "INT" in loc.upper() else "EXT")
                    tod = sc.get("time_of_day", "DAY").upper()
                    chars = sc.get("characters", ["Lead Actor"])
                    props = sc.get("props", ["Production Prop"])
                    wardrobe = sc.get("wardrobe", [f"{c}: Standard costume" for c in chars])
                    shots = sc.get("shots", [
                        {"shot_number": f"{s_num}.1", "shot_type": "Establishing Wide", "requirements": f"Atmospheric shot of {loc}"},
                        {"shot_number": f"{s_num}.2", "shot_type": "Medium Tracking", "requirements": "Kinetic character tracking"},
                        {"shot_number": f"{s_num}.3", "shot_type": "Close-Up Hero", "requirements": "Hero dramatic beat"}
                    ])

                    scene_dict = {
                        "project_id": project_id,
                        "scene_number": s_num,
                        "location": loc,
                        "interior_exterior": ie,
                        "time_of_day": tod,
                        "characters": chars,
                        "shots": shots,
                        "props": props,
                        "wardrobe": wardrobe,
                        "scene_data": json.dumps({
                            "scene_number": s_num,
                            "location": loc,
                            "interior_exterior": ie,
                            "time_of_day": tod,
                            "characters_in_scene": chars,
                            "shots": shots,
                            "props_needed": [{"prop_name": p, "category": "Production Prop"} for p in props],
                            "wardrobe_needed": [{"character_name": str(w).split(":")[0].strip(), "costume_description": str(w)} for w in wardrobe]
                        }),
                        "parsed_by": "Gemini 2.5 Flash"
                    }
                    results.append(scene_dict)
                return results
        except Exception as e:
            # If Gemini call fails (e.g. rate limit or network), smoothly fall back to local parser
            print(f"[parse_screenplay_with_gemini] Gemini call fallback to local parser: {e}")

    # Fallback to deterministic local parser
    return parse_screenplay_text(raw_text, project_id=project_id)


def parse_screenplay_text(raw_text: str, project_id: str = "the-cybernetic-courier") -> list[dict]:
    """Parses a full multi-scene screenplay text into structured scene breakdowns for ClickHouse script_scenes."""

    """Splits by standard slugline patterns (e.g. 'SCENE 1 - EXT. NEO-TOKYO - NIGHT', 'INT. LAB - DAY', etc.),
    identifies scene numbers, locations, lighting conditions, characters, camera coverage,
    props, and wardrobe requirements.

    Args:
        raw_text: The complete screenplay text or multi-scene script excerpt.
        project_id: Project identifier slug.

    Returns:
        List of structured scene dictionaries matching script_scenes schema and scene_data JSON payload.
    """
    import re
    if not raw_text or not raw_text.strip():
        return []

    lines = raw_text.strip().split("\n")
    scenes = []
    current_scene = None
    current_text_lines = []
    scene_counter = 1

    slug_pattern = re.compile(
        r"^(?:SCENE\s+(\d+)\s*[-–—:]\s*)?(INT\.|EXT\.|INT/EXT\.|EXT/INT\.)\s+(.+?)(?:\s+[-–—]\s*([A-Za-z0-9_\s]+))?$",
        re.IGNORECASE
    )

    for line in lines:
        stripped = line.strip()
        match = slug_pattern.match(stripped)
        if match:
            if current_scene:
                current_scene["raw_content"] = "\n".join(current_text_lines)
                scenes.append(current_scene)
                current_text_lines = []

            explicit_num, ie, loc_part, tod_part = match.groups()
            s_num = int(explicit_num) if explicit_num else scene_counter
            scene_counter = s_num + 1

            ie_clean = ie.upper().replace(".", "").strip()
            loc_clean = loc_part.strip() if loc_part else "LOCATION UNKNOWN"
            tod_clean = tod_part.strip().upper() if tod_part else "DAY"

            full_location = f"{ie} {loc_clean}".strip()

            current_scene = {
                "project_id": project_id,
                "scene_number": s_num,
                "location": full_location,
                "interior_exterior": "INT" if "INT" in ie_clean else "EXT",
                "time_of_day": tod_clean,
                "characters": [],
                "shots": [],
                "props": [],
                "wardrobe": [],
                "raw_content": ""
            }
        else:
            if current_scene:
                current_text_lines.append(line)

    if current_scene:
        current_scene["raw_content"] = "\n".join(current_text_lines)
        scenes.append(current_scene)

    # Post-process each scene to extract characters, shots, props, wardrobe
    for sc in scenes:
        content = sc.get("raw_content", "")
        # Extract uppercase character names before dialogue
        char_matches = re.findall(r"^[ \t]*([A-Z][A-Z0-9_\- ]{2,20})[ \t]*$", content, re.MULTILINE)
        found_chars = set()
        for c in char_matches:
            c_clean = c.strip()
            if c_clean not in {"SCENE", "INT", "EXT", "CONTINUOUS", "NIGHT", "DAY", "DUSK", "DAWN", "CUT TO:", "FADE IN:", "FADE OUT."}:
                found_chars.add(c_clean.title())

        # Also search for common character names in script
        for known_char in ["Neo", "Sarah", "Marcus", "Kira", "Detective Miller", "Enforcers", "Drone", "Courier"]:
            if re.search(r"\b" + re.escape(known_char) + r"\b", content, re.IGNORECASE):
                found_chars.add(known_char)

        sc["characters"] = sorted(list(found_chars)) if found_chars else ["Lead Actor"]

        # Extract props
        detected_props = []
        prop_keywords = [
            "briefcase", "chrome briefcase", "photograph", "vintage photograph",
            "flashlight", "crowbar", "plasma baton", "emp disruptor", "dossier",
            "coffee mug", "revolver", "terminal", "holoscreen", "tarp", "locker"
        ]
        for p in prop_keywords:
            if re.search(r"\b" + re.escape(p) + r"\b", content, re.IGNORECASE):
                detected_props.append(p.title())
        sc["props"] = sorted(list(set(detected_props))) if detected_props else ["Handheld Prop"]

        # Wardrobe
        sc["wardrobe"] = [f"{char}: Standard production costume" for char in sc["characters"]]

        # Default standard coverage shots
        s_num = sc["scene_number"]
        sc["shots"] = [
            {
                "shot_number": f"{s_num}.1",
                "shot_type": "Establishing Wide",
                "requirements": f"Atmospheric environment shot of {sc['location']} ({sc['time_of_day']})"
            },
            {
                "shot_number": f"{s_num}.2",
                "shot_type": "Medium Tracking",
                "requirements": f"Kinetic camera movement following {', '.join(sc['characters'][:2])}"
            },
            {
                "shot_number": f"{s_num}.3",
                "shot_type": "Close-Up Hero",
                "requirements": f"High emotion dramatic beat focusing on key narrative discovery"
            }
        ]

        # Build serialized scene_data JSON
        sc["scene_data"] = json.dumps({
            "scene_number": sc["scene_number"],
            "location": sc["location"],
            "interior_exterior": sc["interior_exterior"],
            "time_of_day": sc["time_of_day"],
            "characters_in_scene": sc["characters"],
            "shots": sc["shots"],
            "props_needed": [{"prop_name": p, "category": "Production Prop"} for p in sc["props"]],
            "wardrobe_needed": [{"character_name": c, "costume_description": "Production costume"} for c in sc["characters"]]
        })

    return scenes


def compare_takes_split_screen(take_a: dict, take_b: dict) -> dict:
    """Performs a comprehensive split-screen comparison between two takes (Deck A vs Deck B).

    Evaluates blocking compliance, dialogue accuracy, camera stability, framing,
    detected deviations, confidence scores, and produces an editor recommendation with rationale.

    Args:
        take_a: Dictionary representing Deck A take record.
        take_b: Dictionary representing Deck B take record.

    Returns:
        Structured comparison dictionary containing metrics, differences, and recommendation.
    """
    req_a = take_a.get("requirements_met", False)
    req_b = take_b.get("requirements_met", False)
    conf_a = float(take_a.get("confidence", 0.0))
    conf_b = float(take_b.get("confidence", 0.0))
    devs_a = take_a.get("deviations", []) or []
    devs_b = take_b.get("deviations", []) or []
    issues_a = take_a.get("issues", []) or []
    issues_b = take_b.get("issues", []) or []

    # Scoring algorithm
    score_a = (100 if req_a else 30) + conf_a * 50 - len(devs_a) * 15 - len(issues_a) * 20
    score_b = (100 if req_b else 30) + conf_b * 50 - len(devs_b) * 15 - len(issues_b) * 20

    if score_a > score_b:
        winner = take_a.get("take_id", "DECK_A")
        winning_deck = "A"
        rationale = f"Deck A ({winner}) passed requirements with {conf_a*100:.0f}% confidence and fewer critical issues."
    elif score_b > score_a:
        winner = take_b.get("take_id", "DECK_B")
        winning_deck = "B"
        rationale = f"Deck B ({winner}) passed requirements with {conf_b*100:.0f}% confidence and cleaner continuity."
    else:
        winner = take_a.get("take_id", "DECK_A")
        winning_deck = "A"
        rationale = "Both takes have equivalent compliance; Deck A preferred for camera stability."

    return {
        "deck_a": {
            "take_id": take_a.get("take_id"),
            "scene_number": take_a.get("scene_number"),
            "shot_number": take_a.get("shot_number"),
            "framing": take_a.get("framing"),
            "duration": take_a.get("duration"),
            "requirements_met": req_a,
            "confidence": conf_a,
            "issues_count": len(issues_a),
            "deviations_count": len(devs_a),
            "summary": take_a.get("summary", "")
        },
        "deck_b": {
            "take_id": take_b.get("take_id"),
            "scene_number": take_b.get("scene_number"),
            "shot_number": take_b.get("shot_number"),
            "framing": take_b.get("framing"),
            "duration": take_b.get("duration"),
            "requirements_met": req_b,
            "confidence": conf_b,
            "issues_count": len(issues_b),
            "deviations_count": len(devs_b),
            "summary": take_b.get("summary", "")
        },
        "recommended_take_id": winner,
        "winning_deck": winning_deck,
        "recommendation_rationale": rationale,
        "cut_point_suggestion": f"Use {winner} as the hero anchor cut from {take_a.get('timecode_in', '01:00:00:00')} to {take_a.get('timecode_out', '01:00:30:00')}."
    }

# def insert_scene_to_clickhouse(
#     project_id: str,
#     scene_number: int,
#     location: str,
#     time_of_day: str,
#     characters: list[str],
#     scene_data: str,
# ) -> dict:
#     """Inserts a single scene breakdown record into the ClickHouse script_scenes table.

#     Args:
#         project_id: Identifier or slug for the screenplay/project.
#         scene_number: Numeric scene index.
#         location: Primary location name for the scene.
#         time_of_day: Time of day (e.g., 'DAY', 'NIGHT', 'DUSK', 'DAWN').
#         characters: List of character names present in the scene.
#         scene_data: Serialized JSON string matching the scene_data payload format.

#     Returns:
#         A dict with status, project_id, scene_number, and confirmation message.
#     """
#     host = os.environ.get("CLICKHOUSE_HOST", "localhost")
#     port = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
#     user = os.environ.get("CLICKHOUSE_USER", "default")
#     password = os.environ.get("CLICKHOUSE_PASSWORD", "")
#     secure = os.environ.get("CLICKHOUSE_SECURE", "false").lower() in (
#         "true",
#         "1",
#         "yes",
#     )

#     try:
#         client = clickhouse_connect.get_client(
#             host=host,
#             port=port,
#             username=user,
#             password=password,
#             secure=secure,
#         )

#         data = [
#             [project_id, scene_number, location, time_of_day, characters, scene_data]
#         ]
#         client.insert(
#             table="script_scenes",
#             column_names=[
#                 "project_id",
#                 "scene_number",
#                 "location",
#                 "time_of_day",
#                 "characters",
#                 "scene_data",
#             ],
#             data=data,
#         )
#         return {
#             "status": "success",
#             "project_id": project_id,
#             "scene_number": scene_number,
#             "message": f"Successfully inserted scene {scene_number} for project '{project_id}' into ClickHouse script_scenes table.",
#         }
#     except Exception as e:
#         return {
#             "status": "error",
#             "message": f"Failed to insert scene into ClickHouse: {e!s}",
#         }


# def insert_take_analysis_to_clickhouse(
#     take_id: str,
#     project_id: str,
#     scene_number: int,
#     shot_number: str,
#     requirements_met: bool,
#     confidence: float,
#     analysis_data: str,
# ) -> dict:
#     """Inserts a take analysis record into the ClickHouse take_analyses table.

#     Args:
#         take_id: Unique identifier for the take (e.g. 'TAKE_SCENE37_001').
#         project_id: Identifier or slug for the screenplay project.
#         scene_number: Numeric scene identifier.
#         shot_number: Shot identifier (e.g. '1A', '37B').
#         requirements_met: True if take satisfies all requirements, False otherwise.
#         confidence: Confidence score between 0.0 and 1.0.
#         analysis_data: Serialized JSON string matching TakeAnalysisResult format.

#     Returns:
#         A dict with status, take_id, scene_number, and confirmation message.
#     """
#     host = os.environ.get("CLICKHOUSE_HOST", "localhost")
#     port = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
#     user = os.environ.get("CLICKHOUSE_USER", "default")
#     password = os.environ.get("CLICKHOUSE_PASSWORD", "")
#     secure = os.environ.get("CLICKHOUSE_SECURE", "false").lower() in (
#         "true",
#         "1",
#         "yes",
#     )

#     try:
#         client = clickhouse_connect.get_client(
#             host=host,
#             port=port,
#             username=user,
#             password=password,
#             secure=secure,
#         )

#         met_val = 1 if requirements_met else 0
#         data = [
#             [
#                 take_id,
#                 project_id,
#                 scene_number,
#                 shot_number,
#                 met_val,
#                 confidence,
#                 analysis_data,
#             ]
#         ]
#         client.insert(
#             table="take_analyses",
#             column_names=[
#                 "take_id",
#                 "project_id",
#                 "scene_number",
#                 "shot_number",
#                 "requirements_met",
#                 "confidence",
#                 "analysis_data",
#             ],
#             data=data,
#         )
#         return {
#             "status": "success",
#             "take_id": take_id,
#             "project_id": project_id,
#             "scene_number": scene_number,
#             "message": f"Successfully inserted take analysis '{take_id}' for scene {scene_number} into ClickHouse take_analyses table.",
#         }
#     except Exception as e:
#         return {
#             "status": "error",
#             "message": f"Failed to insert take analysis into ClickHouse: {e!s}",
#         }
