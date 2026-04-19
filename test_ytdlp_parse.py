"""测试 yt-dlp 对 B站 URL（含 query params）的解析结果"""
import subprocess
import json
import sys

url = "https://www.bilibili.com/video/BV12N9cBjEui/?spm_id_from=333.1007.tianma.2-2-5.c&vd_source=b9e05b1e056360f9193e01d3dac9325e"

ytdlp_exe = r"F:\PycharmProjects\YLCraft\backend\venv\Scripts\yt-dlp.exe"

cmd = [str(ytdlp_exe), "--dump-json", "--no-playlist", "--skip-download", "--quiet", url]
print(f"CMD: {' '.join(cmd)}")
print()

proc = subprocess.run(cmd, capture_output=True, timeout=60)
print(f"returncode: {proc.returncode}")
stdout = proc.stdout.decode("utf-8", errors="replace")
stderr = proc.stderr.decode("utf-8", errors="replace")

if proc.returncode != 0:
    print(f"STDERR: {stderr[:500]}")
    sys.exit(1)

try:
    data = json.loads(stdout)
    print(f"title: {data.get('title', '**EMPTY**')}")
    print(f"uploader: {data.get('uploader', '**EMPTY**')}")
    print(f"channel: {data.get('channel', '**EMPTY**')}")
    print(f"duration: {data.get('duration', '**EMPTY**')}")
    print(f"thumbnail: {data.get('thumbnail', '**EMPTY**')[:80]}")
    # first format url
    formats = data.get("formats", [])
    for f in formats[:3]:
        print(f"format[{f.get('format_id')}]: {f.get('url', '')[:80]}")
except json.JSONDecodeError as e:
    print(f"JSON ERROR: {e}")
    print(f"STDOUT (first 300): {stdout[:300]}")
