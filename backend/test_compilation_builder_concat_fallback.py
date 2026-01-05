import os
import shutil
import subprocess
import tempfile

import pytest


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg/ffprobe not available")
def test_concat_fallback_filter_complex_succeeds_when_demuxer_would_fail():
    """
    Regression: concat demuxer requires identical stream params. We intentionally build
    two clips with different resolutions so the demuxer would fail, and assert that
    our filter_complex fallback succeeds.
    """
    from compilation_builder import CompilationBuilder

    with tempfile.TemporaryDirectory() as td:
        b = CompilationBuilder(storage_dir=td, output_dir=td)

        clip_a = os.path.join(td, "a_640x360.mp4")
        clip_b = os.path.join(td, "b_1920x1080.mp4")
        out = os.path.join(td, "out.mp4")
        audio = os.path.join(td, "audio.m4a")

        assert b.create_color_clip(duration_sec=1.0, output_file=clip_a, resolution="640x360")
        assert b.create_color_clip(duration_sec=1.0, output_file=clip_b, resolution="1920x1080")

        # 2s silent audio (required by concatenate_clips; it refuses silent output)
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            "2",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            audio,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr[:500]
        assert os.path.exists(audio) and os.path.getsize(audio) > 0

        ok = b.concatenate_clips(
            [clip_a, clip_b],
            out,
            target_fps=30,
            resolution="1920x1080",
            audio_file=audio,
        )
        assert ok is True
        assert os.path.exists(out) and os.path.getsize(out) > 0




