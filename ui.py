from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ProgressBar, Select, Static
import asyncio

from core import (
    clear_title,
    fetch_lyrics,
    get_active_player,
    get_current_line,
    get_current_song,
    get_duration,
    get_position,
    list_players,
    parse_lrc,
    get_cached_lyrics,
    save_to_cache,
)

ACCENT_COLORS = [
    ("Rojo", "#cf0000"),
    ("Azul", "#007aff"),
    ("Verde", "#32d74b"),
    ("Amarillo", "#e8c101"),
    ("Morado", "#af52de"),
    ("Blanco", "#ffffff"),
]

LINE_OPTIONS = [3, 5, 7]

DEFAULT_ACCENT = "#ffffff"
DEFAULT_VISIBLE_LINES = 5

# Seccion de configuracion
class ConfigScreen(ModalScreen):
    BINDINGS = [
        Binding("s", "save", "Guardar"),
    ]

    def __init__(self, current_accent: str, current_lines: int, current_player: str | None):
        super().__init__()
        self.current_accent = current_accent
        self.current_lines = current_lines
        self.current_player = current_player

    def compose(self) -> ComposeResult:
        players = list_players()

        accent_options = [(name, hex_value) for name, hex_value in ACCENT_COLORS]
        lines_options = [(str(n), n) for n in LINE_OPTIONS]
        player_options = [("Auto (detectar)", "__auto__")] + [(p, p) for p in players]

        with Vertical(id="config_box"):
            yield Static("Color de acento")
            yield Select(
                accent_options,
                value=self.current_accent,
                id="accent_select",
                allow_blank=False,
            )

            yield Static("Lineas visibles")
            yield Select(
                lines_options,
                value=self.current_lines,
                id="line_select",
                allow_blank=False,
            )

            yield Static("Reproductor")
            yield Select(
                player_options,
                value=self.current_player or "__auto__",
                id="player_select",
                allow_blank=False,
            )

            yield Static("[dim]Presiona [b]s[/b] para guardar[/dim]", id="hint")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "accent_select":
            return
        self.query_one("#config_box").styles.border = ("round", Color.parse(str(event.value)))

    def action_save(self) -> None:
        accent = self.query_one("#accent_select", Select).value
        lines = self.query_one("#line_select", Select).value
        player_raw = self.query_one("#player_select", Select).value
        player = None if player_raw == "__auto__" else player_raw

        self.dismiss({"accent": accent, "visible_lines": lines, "manual_player": player})

# Logica de interfaz
class LyricsApp(App):
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        Binding("q", "quit", "Salir"),
        Binding("c", "open_config", "Config"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static("Esperando Reproduccion...", id="song_info")
            yield Static("", id="lyrics")
            yield ProgressBar(id="progress", total=100, show_eta=False)
            yield Static('NeoPlug Lyrics - press "c" to configure', id="brand")

    def on_mount(self) -> None:
        self.last_song = None
        self.current_player = None
        self.manual_player: str | None = None
        self.current_lyrics: list[tuple[float, str]] = []
        self.has_synced_lyrics = False
        self.last_line_index = -1
        self.duration: float | None = None
        self.accent = DEFAULT_ACCENT
        self.visible_lines = DEFAULT_VISIBLE_LINES

        self.info = self.query_one("#song_info", Static)
        self.lyrics_widget = self.query_one("#lyrics", Static)
        self.progress_bar = self.query_one("#progress", ProgressBar)

        self.set_interval(2.0, self.poll_song)
        self.set_interval(0.15, self.poll_position)

    def action_open_config(self) -> None:
        self.push_screen(
            ConfigScreen(self.accent, self.visible_lines, self.manual_player),
            callback=self.apply_config,
        )

    def apply_config(self, result: dict | None) -> None:
        if result is None:
            return

        self.accent = result["accent"]
        self.visible_lines = result["visible_lines"]
        self.manual_player = result["manual_player"]

        self.query_one("#box").styles.border = ("round", Color.parse(self.accent))
        bar_widget = self.progress_bar.query_one("Bar")
        bar_widget.styles.color = Color.parse(self.accent)

        self.last_line_index = -1
        self.update_display(center_index=None if not self.has_synced_lyrics else self.last_line_index)

    async def poll_song(self) -> None:
        player = self.manual_player or get_active_player()
        if player is None:
            self.current_player = None
            return
        self.current_player = player

        song = get_current_song(player)
        if not song or song == self.last_song:
            return
        self.last_song = song
        self.last_line_index = -1
        self.current_lyrics = []
        self.has_synced_lyrics = False

        artist, title = song.split("|", 1)
        title = clear_title(title)

        self.info.update(f"{artist} - {title}")
        self.lyrics_widget.update("Buscando letra...")
        await asyncio.sleep(0)

        self.duration = get_duration(player)
        self.progress_bar.update(total=self.duration or 100, progress=0)

        lyrics_data = get_cached_lyrics(artist, title)
        if lyrics_data is None:
            lyrics_data = await fetch_lyrics(artist, title)
            if lyrics_data:
                save_to_cache(artist, title, lyrics_data)

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

    async def poll_position(self) -> None:
        if self.current_player is None:
            return

        position = get_position(self.current_player)

        if position is not None and self.duration:
            self.progress_bar.update(total=self.duration, progress=position)

        if not self.has_synced_lyrics or not self.current_lyrics or position is None:
            return

        idx = get_current_line(self.current_lyrics, position)
        if idx == self.last_line_index:
            return
        self.last_line_index = idx
        self.update_display(center_index=idx)

    def update_display(self, center_index: int | None = None) -> None:
        if not self.current_lyrics:
            self.lyrics_widget.update("Letra no disponible")
            return

        total = len(self.current_lyrics)
        if center_index is None:
            start = 0
            end = min(self.visible_lines, total)
        else:
            start = max(0, center_index - self.visible_lines // 2)
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
                formatted.append(f"[bold {self.accent}]{line}[/bold {self.accent}]")
            else:
                formatted.append(line)

        self.lyrics_widget.update("\n".join(formatted))


if __name__ == "__main__":
    LyricsApp().run()
