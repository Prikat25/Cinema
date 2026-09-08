"""Shared production tools used by CineSupervisor and its subagents."""

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

import clickhouse_connect

from app.config import (
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_SECURE,
    CLICKHOUSE_USER,
)

_client = None
_tables_initialized = False


def get_clickhouse_client():
    """Return a cached ClickHouse client configured from app.config."""
    global _client
    if _client is not None:
        return _client
    if not CLICKHOUSE_HOST:
        raise RuntimeError("CLICKHOUSE_HOST is not configured")
    _client = clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        username=CLICKHOUSE_USER or "default",
        password=CLICKHOUSE_PASSWORD or "",
        secure=CLICKHOUSE_SECURE,
        verify=False,
    )
    return _client


def ensure_clickhouse_tables(client=None):
    """Create required production tables once per process."""
    global _tables_initialized
    if _tables_initialized:
        return
    c = client or get_clickhouse_client()
    c.command("""
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
    """)
    c.command("""
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
    """)
    _tables_initialized = True

def list_scenes_from_clickhouse(project_id: str) -> list[dict[str, Any]]:
    """Return the current scene registry for a project without mutating it."""
    try:
        client = get_clickhouse_client()
        ensure_clickhouse_tables(client)
        result = client.query(
            """
            SELECT scene_number, location, time_of_day, characters, scene_data
            FROM script_scenes
            WHERE project_id = %(project_id)s
            ORDER BY scene_number
            """,
            parameters={"project_id": project_id},
        )
    except Exception:
        return []

    scenes = []
    for scene_number, location, time_of_day, characters, scene_data in result.result_rows:
        try:
            payload = json.loads(scene_data)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        scenes.append(
            {
                "project_id": project_id,
                "scene_number": scene_number,
                "location": location,
                "interior_exterior": payload.get("interior_exterior", "INT"),
                "time_of_day": time_of_day,
                "characters": characters,
                "shots": payload.get("shots", []),
                "props": [item.get("prop_name", str(item)) for item in payload.get("props_needed", [])],
                "wardrobe": [
                    item.get("costume_description", str(item))
                    for item in payload.get("wardrobe_needed", [])
                ],
            }
        )
    return scenes


def list_take_analyses_from_clickhouse(project_id: str) -> list[dict[str, Any]]:
    """Return persisted take analyses for a project without mutating them."""
    try:
        client = get_clickhouse_client()
        ensure_clickhouse_tables(client)
        result = client.query(
            """
            SELECT take_id, scene_number, shot_number, requirements_met, confidence, analysis_data
            FROM take_analyses
            WHERE project_id = %(project_id)s
            ORDER BY scene_number, shot_number, take_id
            """,
            parameters={"project_id": project_id},
        )
    except Exception:
        return []

    takes = []
    for take_id, scene_number, shot_number, requirements_met, confidence, analysis_data in result.result_rows:
        try:
            payload = json.loads(analysis_data)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        takes.append(
            {
                "take_id": take_id,
                "project_id": project_id,
                "scene_number": scene_number,
                "shot_number": shot_number,
                "media_path": payload.get("media_path", ""),
                "timecode_in": payload.get("timecode_in", "Unknown"),
                "timecode_out": payload.get("timecode_out", "Unknown"),
                "framing": payload.get("framing", "Unspecified"),
                "requirements_met": bool(requirements_met),
                "confidence": float(confidence),
                "actors": payload.get("detected_actors", payload.get("actors", [])),
                "props": payload.get("detected_props", payload.get("props", [])),
                "deviations": payload.get("deviations", []),
                "issues": payload.get("issues", []),
                "summary": payload.get("analysis_summary", payload.get("summary", "")),
            }
        )
    return takes

def seconds_to_smpte(seconds: float, fps: float = 24.0) -> str:
    """Convert seconds to HH:MM:SS:FF SMPTE timecode."""
    fps_int = max(1, int(round(fps)))
    total_frames = max(0, int(round(float(seconds) * fps)))
    frames = total_frames % fps_int
    total_seconds = total_frames // fps_int
    return f"{total_seconds // 3600:02d}:{(total_seconds // 60) % 60:02d}:{total_seconds % 60:02d}:{frames:02d}"


def smpte_to_seconds(timecode: str, fps: float = 24.0) -> float:
    """Convert HH:MM:SS:FF SMPTE timecode to seconds."""
    try:
        h, m, s, f = map(int, timecode.strip().split(":"))
        if min(h, m, s, f) < 0 or f >= int(round(fps)):
            return 0.0
        return (h * 3600) + (m * 60) + s + f / float(fps)
    except (ValueError, TypeError, AttributeError):
        return 0.0


def read_screenplay_file(file_path: str) -> dict:
    """Read a screenplay text file."""
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found at path: {file_path}"}
    try:
        content = path.read_text(encoding="utf-8")
        return {"status": "success", "file_path": str(path.resolve()), "screenplay_text": content, "char_count": len(content)}
    except Exception as exc:
        return {"status": "error", "message": f"Failed to read file {file_path}: {exc!s}"}


def read_media_metadata(file_path: str) -> dict:
    """Inspect video/audio metadata with ffprobe when available."""
    path = Path(file_path)
    if not path.exists():
        return {
            "status": "simulated_or_remote", "file_path": str(file_path), "filename": path.name,
            "extension": path.suffix.lower(), "size_bytes": 0, "duration_seconds": 45.0,
            "framerate": 24.0, "resolution": "3840x2160", "aspect_ratio": "16:9",
            "video_codec": "ProRes 422 HQ", "audio_codec": "Linear PCM", "audio_channels": 2,
            "sample_rate_hz": 48000, "timecode_start": "01:00:00:00", "timecode_end": "01:00:45:00",
        }

    metadata: dict[str, Any] = {
        "status": "success", "file_path": str(path.resolve()), "filename": path.name,
        "extension": path.suffix.lower(), "size_bytes": path.stat().st_size,
        "duration_seconds": 30.0, "framerate": 24.0, "resolution": "1920x1080",
        "aspect_ratio": "16:9", "video_codec": "h264", "audio_codec": "aac",
        "audio_channels": 2, "sample_rate_hz": 48000,
        "timecode_start": "01:00:00:00", "timecode_end": "01:00:30:00",
    }
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path.resolve())],
            capture_output=True, text=True, check=True,
        )
        probe = json.loads(result.stdout)
        fmt = probe.get("format", {})
        streams = probe.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        rate = video.get("r_frame_rate", "24/1")
        try:
            num, den = rate.split("/")
            fps = float(num) / float(den) if float(den) else 24.0
        except (ValueError, ZeroDivisionError):
            fps = 24.0
        duration = float(fmt.get("duration", metadata["duration_seconds"]))
        tc_start = fmt.get("tags", {}).get("timecode", video.get("tags", {}).get("timecode", "01:00:00:00"))
        metadata.update({
            "duration_seconds": duration, "framerate": round(fps, 3),
            "resolution": f"{video.get('width', 1920)}x{video.get('height', 1080)}",
            "aspect_ratio": video.get("display_aspect_ratio", "16:9"),
            "video_codec": video.get("codec_name", "unknown"), "audio_codec": audio.get("codec_name", "none"),
            "audio_channels": int(audio.get("channels", 2)), "sample_rate_hz": int(audio.get("sample_rate", 48000)),
            "timecode_start": tc_start, "timecode_end": seconds_to_smpte(smpte_to_seconds(tc_start, fps) + duration, fps),
        })
    except Exception:
        pass
    return metadata


def get_clip_timecode_range(media_path: str, start_seconds: Optional[float] = None, end_seconds: Optional[float] = None, base_timecode: str = "01:00:00:00", fps: float = 24.0) -> dict:
    """Calculate editorial in/out timecodes for a media clip."""
    start = max(0.0, float(start_seconds if start_seconds is not None else 0.0))
    end = float(end_seconds if end_seconds is not None else start + 10.0)
    if end <= start:
        end = start + 5.0
    duration = end - start
    base = smpte_to_seconds(base_timecode, fps)
    return {
        "status": "success", "media_path": media_path, "fps": fps,
        "start_seconds": start, "end_seconds": end, "duration_seconds": duration,
        "timecode_in": seconds_to_smpte(base + start, fps),
        "timecode_out": seconds_to_smpte(base + end, fps),
        "duration_timecode": seconds_to_smpte(duration, fps), "total_frames": int(round(duration * fps)),
    }


def _event_value(event: dict, *names: str, default=None):
    for name in names:
        value = event.get(name)
        if value not in (None, ""):
            return value
    return default


def format_edit_decision_list(events: list[dict], sequence_title: str = "EDITORIAL_ASSEMBLY", fps: float = 24.0) -> str:
    """Format editorial events as a CMX 3600 EDL.

    Accepts both backend names (src_in/src_out/rec_in/rec_out/editor_note)
    and Streamlit/UI names (source_in/source_out/record_in/record_out/comment).
    """
    lines = [f"TITLE: {sequence_title.upper()}", "FCM: NON-DROP FRAME", ""]
    record_seconds = smpte_to_seconds("01:00:00:00", fps)
    for idx, event in enumerate(events, start=1):
        reel = str(_event_value(event, "reel", "clip_reel", default="AX"))[:8].ljust(8)
        track = str(_event_value(event, "track", default="V"))[:4].ljust(4)
        transition_name = str(_event_value(event, "transition", default="C")).upper()
        transition = "D   024" if "DISSOLVE" in transition_name else "C"
        src_in = _event_value(event, "src_in", "in_point", "source_in", default="01:00:00:00")
        src_out = _event_value(event, "src_out", "out_point", "source_out", default="01:00:05:00")
        duration = smpte_to_seconds(src_out, fps) - smpte_to_seconds(src_in, fps)
        if duration <= 0:
            duration = 4.0
        rec_in = _event_value(event, "rec_in", "record_in", default=seconds_to_smpte(record_seconds, fps))
        rec_out = _event_value(event, "rec_out", "record_out", default=seconds_to_smpte(record_seconds + duration, fps))
        record_seconds += duration
        lines.append(f"{idx:03d}  {reel} {track} {transition:<5} {src_in} {src_out} {rec_in} {rec_out}")
        clip_name = _event_value(event, "clip_name", "media_path", "source_clip")
        if clip_name:
            lines.append(f"* FROM CLIP NAME: {Path(str(clip_name)).name}")
        note = _event_value(event, "editor_note", "event", "comment", "notes")
        if note:
            lines.append(f"* NOTE: {note}")
        lines.append("")
    return "\n".join(lines)


def _upsert(table: str, key_where: str, key_params: dict, update_sql: str, update_params: dict, columns: list[str], data: list[list[Any]]) -> dict:
    client = get_clickhouse_client()
    ensure_clickhouse_tables(client)
    result = client.query(f"SELECT count() FROM {table} WHERE {key_where}", parameters=key_params)
    exists = bool(result.result_rows and result.result_rows[0][0])
    if exists:
        try:
            client.command(update_sql, parameters=update_params, settings={"mutations_sync": "1"})
        except Exception:
            client.command(update_sql, parameters=update_params)
        return {"status": "success", "action": "updated"}
    client.insert(table=table, column_names=columns, data=data)
    return {"status": "success", "action": "inserted"}


def insert_scene_to_clickhouse(project_id: str, scene_number: int, location: str, time_of_day: str, characters: list[str], scene_data: str) -> dict:
    """Insert or update a screenplay scene in ClickHouse."""
    if isinstance(scene_data, dict):
        scene_data = json.dumps(scene_data)
    try:
        params = {"project_id": str(project_id), "scene_number": int(scene_number)}
        update_params = {**params, "location": str(location), "time_of_day": str(time_of_day), "characters": list(characters), "scene_data": str(scene_data)}
        result = _upsert(
            "script_scenes", "project_id = %(project_id)s AND scene_number = %(scene_number)s", params,
            "ALTER TABLE script_scenes UPDATE location=%(location)s, time_of_day=%(time_of_day)s, characters=%(characters)s, scene_data=%(scene_data)s WHERE project_id=%(project_id)s AND scene_number=%(scene_number)s",
            update_params,
            ["project_id", "scene_number", "location", "time_of_day", "characters", "scene_data"],
            [[str(project_id), int(scene_number), str(location), str(time_of_day), list(characters), str(scene_data)]],
        )
        return {**result, "project_id": project_id, "scene_number": scene_number, "message": f"Successfully {result['action']} scene {scene_number} for project '{project_id}'."}
    except Exception as exc:
        return {"status": "error", "message": f"Failed to insert or update scene in ClickHouse: {exc!s}"}


def insert_take_analysis_to_clickhouse(take_id: str, project_id: str, scene_number: int, shot_number: str, requirements_met: bool, confidence: float, analysis_data: str) -> dict:
    """Insert or update a take analysis in ClickHouse."""
    if isinstance(analysis_data, dict):
        analysis_data = json.dumps(analysis_data)
    try:
        params = {"take_id": str(take_id), "scene_number": int(scene_number)}
        update_params = {**params, "project_id": str(project_id), "shot_number": str(shot_number), "requirements_met": 1 if requirements_met else 0, "confidence": float(confidence), "analysis_data": str(analysis_data)}
        result = _upsert(
            "take_analyses", "take_id = %(take_id)s AND scene_number = %(scene_number)s", params,
            "ALTER TABLE take_analyses UPDATE project_id=%(project_id)s, shot_number=%(shot_number)s, requirements_met=%(requirements_met)s, confidence=%(confidence)s, analysis_data=%(analysis_data)s WHERE take_id=%(take_id)s AND scene_number=%(scene_number)s",
            update_params,
            ["take_id", "project_id", "scene_number", "shot_number", "requirements_met", "confidence", "analysis_data"],
            [[str(take_id), str(project_id), int(scene_number), str(shot_number), 1 if requirements_met else 0, float(confidence), str(analysis_data)]],
        )
        return {**result, "take_id": take_id, "project_id": project_id, "scene_number": scene_number, "message": f"Successfully {result['action']} take analysis '{take_id}'."}
    except Exception as exc:
        return {"status": "error", "message": f"Failed to insert or update take analysis in ClickHouse: {exc!s}"}


def parse_screenplay_with_gemini(raw_text: str, project_id: str = "the-cybernetic-courier") -> list[dict]:
    """Parse a screenplay with Gemini when configured, otherwise use the local parser."""
    if not raw_text or not raw_text.strip():
        return []
    from app.config import GOOGLE_API_KEY, PLANNER_MODEL
    if GOOGLE_API_KEY:
        try:
            from google import genai
            from google.genai import types
            response = genai.Client(api_key=GOOGLE_API_KEY).models.generate_content(
                model=PLANNER_MODEL,
                contents=f"Break this screenplay into production scenes and return a raw JSON array with scene_number, location, interior_exterior, time_of_day, characters, props, wardrobe, and shots.\n\nSCREENPLAY:\n{raw_text}",
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
            )
            parsed = json.loads(response.text.strip())
            if isinstance(parsed, list) and parsed:
                return _normalize_scenes(parsed, project_id)
        except Exception as exc:
            print(f"[parse_screenplay_with_gemini] Falling back to local parser: {exc}")
    return parse_screenplay_text(raw_text, project_id)


def _normalize_scenes(scenes: list[dict], project_id: str) -> list[dict]:
    results = []
    for idx, scene in enumerate(scenes, start=1):
        number = int(scene.get("scene_number", idx))
        chars = scene.get("characters") or ["Lead Actor"]
        props = scene.get("props") or ["Production Prop"]
        wardrobe = scene.get("wardrobe") or [f"{c}: Standard costume" for c in chars]
        shots = scene.get("shots") or [
            {"shot_number": f"{number}.1", "shot_type": "Establishing Wide", "requirements": "Atmospheric establishing coverage"},
            {"shot_number": f"{number}.2", "shot_type": "Medium Tracking", "requirements": "Character movement coverage"},
            {"shot_number": f"{number}.3", "shot_type": "Close-Up Hero", "requirements": "Key dramatic beat"},
        ]
        location = scene.get("location", f"SCENE {number}")
        results.append({
            "project_id": project_id, "scene_number": number, "location": location,
            "interior_exterior": scene.get("interior_exterior", "INT" if "INT" in location.upper() else "EXT"),
            "time_of_day": str(scene.get("time_of_day", "DAY")).upper(), "characters": chars,
            "shots": shots, "props": props, "wardrobe": wardrobe,
            "scene_data": json.dumps({"scene_number": number, "location": location, "characters_in_scene": chars, "shots": shots, "props_needed": [{"prop_name": p, "category": "Production Prop"} for p in props], "wardrobe_needed": [{"character_name": str(w).split(":")[0].strip(), "costume_description": str(w)} for w in wardrobe]}),
            "parsed_by": "Gemini",
        })
    return results


def parse_screenplay_text(raw_text: str, project_id: str = "the-cybernetic-courier") -> list[dict]:
    """Deterministically parse screenplay sluglines into scene records."""
    if not raw_text or not raw_text.strip():
        return []
    slug = re.compile(r"^(?:SCENE\s+(\d+)\s*[-–—:]\s*)?(INT\.|EXT\.|INT/EXT\.|EXT/INT\.)\s+(.+?)(?:\s+[-–—]\s*([A-Za-z0-9_\s]+))?$", re.I)
    scenes, current, content, counter = [], None, [], 1
    for line in raw_text.strip().splitlines():
        match = slug.match(line.strip())
        if match:
            if current:
                current["raw_content"] = "\n".join(content)
                scenes.append(current)
            explicit, ie, location, tod = match.groups()
            number = int(explicit) if explicit else counter
            counter = number + 1
            content = []
            current = {"project_id": project_id, "scene_number": number, "location": f"{ie} {location}".strip(), "interior_exterior": "INT" if "INT" in ie.upper() else "EXT", "time_of_day": (tod or "DAY").strip().upper(), "characters": [], "shots": [], "props": [], "wardrobe": []}
        elif current:
            content.append(line)
    if current:
        current["raw_content"] = "\n".join(content)
        scenes.append(current)

    known_chars = ["Neo", "Sarah", "Marcus", "Kira", "Detective Miller", "Enforcers", "Drone", "Courier"]
    prop_words = ["briefcase", "photograph", "flashlight", "crowbar", "plasma baton", "emp disruptor", "dossier", "coffee mug", "revolver", "terminal", "holoscreen", "tarp", "locker"]
    for scene in scenes:
        body = scene.get("raw_content", "")
        chars = {m.strip().title() for m in re.findall(r"^[ \t]*([A-Z][A-Z0-9_\- ]{2,20})[ \t]*$", body, re.M)}
        chars.update(c for c in known_chars if re.search(r"\b" + re.escape(c) + r"\b", body, re.I))
        chars -= {"Scene", "Int", "Ext", "Continuous", "Night", "Day", "Dusk", "Dawn", "Cut To:", "Fade In:", "Fade Out."}
        scene["characters"] = sorted(chars) or ["Lead Actor"]
        scene["props"] = sorted({p.title() for p in prop_words if re.search(r"\b" + re.escape(p) + r"\b", body, re.I)}) or ["Handheld Prop"]
        scene["wardrobe"] = [f"{c}: Standard production costume" for c in scene["characters"]]
        n = scene["scene_number"]
        scene["shots"] = [
            {"shot_number": f"{n}.1", "shot_type": "Establishing Wide", "requirements": f"Atmospheric environment shot of {scene['location']} ({scene['time_of_day']})"},
            {"shot_number": f"{n}.2", "shot_type": "Medium Tracking", "requirements": f"Character movement coverage for {', '.join(scene['characters'][:2])}"},
            {"shot_number": f"{n}.3", "shot_type": "Close-Up Hero", "requirements": "Key dramatic beat"},
        ]
        scene["scene_data"] = json.dumps({"scene_number": n, "location": scene["location"], "interior_exterior": scene["interior_exterior"], "time_of_day": scene["time_of_day"], "characters_in_scene": scene["characters"], "shots": scene["shots"], "props_needed": [{"prop_name": p, "category": "Production Prop"} for p in scene["props"]], "wardrobe_needed": [{"character_name": c, "costume_description": "Production costume"} for c in scene["characters"]]})
    return scenes


def compare_takes_split_screen(take_a: dict, take_b: dict) -> dict:
    """Compare two takes using objective production evidence."""
    def score(take: dict) -> float:
        return (
            (100 if take.get("requirements_met", False) else 30)
            + float(take.get("confidence", 0)) * 50
            - len(take.get("deviations", []) or []) * 15
            - len(take.get("issues", []) or []) * 20
        )
    score_a, score_b = score(take_a), score(take_b)
    winner = take_a if score_a >= score_b else take_b
    deck = "A" if winner is take_a else "B"
    return {
        "deck_a": take_a, "deck_b": take_b,
        "recommended_take_id": winner.get("take_id", f"DECK_{deck}"),
        "winning_deck": deck,
        "score_a": score_a, "score_b": score_b,
        "recommendation_rationale": "Selected from requirements compliance, confidence, deviations, and issues; creative preference remains with the filmmaker.",
        "cut_point_suggestion": f"Use {winner.get('take_id', 'selected take')} from {winner.get('timecode_in', '01:00:00:00')} to {winner.get('timecode_out', '01:00:30:00')}",
    }
