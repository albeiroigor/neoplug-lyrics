import subprocess
import httpx
import re
from bisect import bisect_right


def get_active_player() -> str | None:
    try:
        output = subprocess.check_output(
            ["playerctl", "-a", "metadata", "--format", "{{playerName}}|{{status}}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None

    for line in output.splitlines():
        if "|" not in line:
            continue
        player, status = line.split("|", 1)
        if status == "Playing":
            return player
    return None


def clear_title(title):
    title = re.sub(r"[\(\[].*?[\)\]]", "", title)
    return title.strip()


def get_current_song(player: str | None = None) -> str | None:
    if player is None:
        player = get_active_player()
    if player is None:
        return None

    try:
        song = subprocess.check_output(
            ["playerctl", f"--player={player}", "metadata", "--format", "{{artist}}|{{title}}"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return song or None
    except subprocess.CalledProcessError:
        return None


async def fetch_lyrics(artist: str, title: str) -> dict[str, str | None] | None:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://lrclib.net/api/get",
                params={"artist_name": artist, "track_name": title},
                timeout=15,
            )
        except httpx.RequestError:
            return None
        if response.status_code != 200:
            return None
        data = response.json()
        if not data:
            return None
        return {"syncedLyrics": data.get("syncedLyrics"), "plainLyrics": data.get("plainLyrics")}


LRC_PATTERN = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")


def parse_lrc(raw_lyrics: str) -> list[tuple[float, str]]:
    lyrics = []
    for line in raw_lyrics.splitlines():
        match = LRC_PATTERN.match(line)
        if not match:
            continue
        minutes, seconds, text = match.groups()
        timestamp = int(minutes) * 60 + float(seconds)
        lyrics.append((timestamp, text.strip()))
    lyrics.sort(key=lambda item: item[0])
    return lyrics


def get_current_line(lyrics: list[tuple[float, str]], current_time: float) -> int:
    timestamps = [line[0] for line in lyrics]
    return max(0, bisect_right(timestamps, current_time) - 1)


def get_position(player: str | None = None) -> float | None:
    if player is None:
        player = get_active_player()
    if player is None:
        return None

    try:
        output = subprocess.check_output(
            ["playerctl", "--player", player, "position"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return float(output.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None

def get_duration(player: str | None = None) -> float | None:
    if player is None:
        player = get_active_player()
    if player is None:
        return None

    try:
        output = subprocess.check_output(
            ["playerctl", f"--player={player}", "metadata", "mpris:length"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return float(output) / 1_000_000 
    except (subprocess.CalledProcessError, ValueError):
        return None

def list_players() -> list[str]:
    try:
        output = subprocess.check_output(
            ["playerctl", "-l"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return []
    return [p.strip() for p in output.splitlines() if p.strip()]