from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Vertical
from core import (get_active_player, get_current_song, clear_title, fetch_lyrics, parse_lrc, get_position, get_current_line)


class LyricsApp(App):
    CSS = """
    $primary: #660f01;
    $secondary: #007aff;
    $bg-dark: #0f0f0f;
    $bg-card: #1c1c1e;
    $text-light: #f5f5f7;
    $text-dim: #86868b;

    Screen {
        background: $bg-dark;
        align: center middle;
    }

    #box {
        width: 60;
        height: 15;
        padding: 1 2;
        background: $bg-card;
        border: round $primary;
    }

    #song_info {
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: $text-light;
        padding: 0 1;
        margin-bottom: 1;
    }

    #lyrics {
        height: 1fr;
        overflow-y: auto;
        content-align: center middle;
        color: $text-dim;
        padding: 1 0;
        text-align: center;
    }

    ScrollBar {
        background: transparent;
        width: 1;
    }

    ScrollBar > .thumb {
        background: $secondary;
    }
    """
    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static("Esperando Reproduccion...", id="song_info")
            yield Static("", id="lyrics")

    def on_mount(self) -> None:
        self.last_song = None
        self.current_player = None
        self.current_lyrics: list[tuple[float, str]] = []
        self.has_synced_lyrics = False
        self.last_line_index = -1
        self.info = self.query_one("#song_info", Static)
        self.lyrics_widget = self.query_one("#lyrics", Static)
        self.visible_lines = 5
        self.set_interval(2.0, self.poll_song)
        self.set_interval(0.15, self.poll_position)

    async def poll_song(self) -> None:
        player = get_active_player()
        if player is None:
            self.current_player = None
            return
        self.current_player = player

        song = get_current_song(player)
        if not song or song == self.last_song:
            return
        self.last_song = song
        self.last_line_index = -1
        artist, title = song.split("|", 1)
        title = clear_title(title)

        self.info.update(f"{artist} - {title}")
        self.lyrics_widget.update("Buscando letra...")

        lyrics_data = await fetch_lyrics(artist, title)

        if not lyrics_data:
            self.current_lyrics = []
            self.has_synced_lyrics = False
            self.lyrics_widget.update("No se encontro la letra.")
            return

        synced_lyrics = lyrics_data.get("syncedLyrics")
        if synced_lyrics:
            self.current_lyrics = parse_lrc(synced_lyrics)
            self.has_synced_lyrics = True
        else:
            self.has_synced_lyrics = False
            plain = lyrics_data.get("plainLyrics")
            self.current_lyrics = [(0.0, line) for line in plain.split("\n")] if plain else []
        self.update_display(center_index=None)

    def update_display(self, center_index=None):
        if not self.current_lyrics:
            self.lyrics_widget.update("Letra no disponible")
            return
        total = len(self.current_lyrics)
        if center_index is None:
            start = 0
            end = min(self.visible_lines, total)
        else:
            start = max(0, center_index - 2)
            end = min(total, start + self.visible_lines)

            if end - start < self.visible_lines:
                start = max(0, end - self.visible_lines)

        lines = [self.current_lyrics[i][1] for i in range(start, end)]
        while len(lines) < self.visible_lines:
            lines.append("")

        formatted = []
        for i, line in enumerate(lines):
            real_index = start + i
            if center_index is not None and real_index == center_index:
                formatted.append(f"[bold #ff2d55]{line}[/bold #ff2d55]")
            else:
                formatted.append(line)
        self.lyrics_widget.update("\n".join(formatted))


    async def poll_position(self) -> None:
        if not self.has_synced_lyrics:
            return
        if self.current_player is None:
            return
        if not self.current_lyrics:
            return
        position = get_position(self.current_player)
        if position is None:
            return
        idx = get_current_line(self.current_lyrics, position)
        if idx == self.last_line_index:
            return
        self.last_line_index = idx
        self.update_display(center_index=idx)


if __name__ == "__main__":
    LyricsApp().run()
