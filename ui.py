from textual.app import App, ComposeResult
from textual.widgets import Static, ProgressBar, RadioSet, RadioButton, Button
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.color import Color
from core import (
    get_active_player, get_current_song, clear_title, fetch_lyrics,
    parse_lrc, get_position, get_current_line, get_duration, list_players,
)

ACCENT_COLORS = [
    ("Rojo", "#cf0000"),
    ("Azul", "#007aff"),
    ("Verde", "#32d74b"),
    ("Amarillo", "#e8c101"),
    ("Morado", "#af52de"),
]

LINE_OPTIONS = [3, 5, 7]


class ConfigScreen(ModalScreen):
    CSS = """
    ConfigScreen {
        align: center middle;
    }
    #config_box {
        width: 44;
        height: auto;
        padding: 1 2;
        background: $panel;
        border: round $primary;
    }
    #config_box Static {
        margin-top: 1;
        text-style: bold;
    }
    """

    def __init__(self, current_accent: str, current_lines: int, current_player: str | None):
        super().__init__()
        self.current_accent = current_accent
        self.current_lines = current_lines
        self.current_player = current_player

    def compose(self) -> ComposeResult:
        players = list_players()
        with Vertical(id="config_box"):
            yield Static("Color de acento")
            with RadioSet(id="accent_set"):
                for name, hex_value in ACCENT_COLORS:
                    yield RadioButton(name, value=(hex_value == self.current_accent), name=hex_value)

            yield Static("Lineas visibles")
            with RadioSet(id="lines_set"):
                for n in LINE_OPTIONS:
                    yield RadioButton(str(n), value=(n == self.current_lines), name=str(n))

            yield Static("Reproductor")
            with RadioSet(id="player_set"):
                yield RadioButton("Auto (detectar)", value=(self.current_player is None), name="__auto__")
                for player in players:
                    yield RadioButton(player, value=(player == self.current_player), name=player)

            yield Button("Guardar", id="save_button", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        accent = self._selected_name("accent_set") or self.current_accent
        lines_raw = self._selected_name("lines_set")
        lines = int(lines_raw) if lines_raw else self.current_lines
        player_raw = self._selected_name("player_set")
        player = None if player_raw in (None, "__auto__") else player_raw

        self.dismiss({"accent": accent, "visible_lines": lines, "manual_player": player})

    def _selected_name(self, radioset_id: str) -> str | None:
        radio_set = self.query_one(f"#{radioset_id}", RadioSet)
        if radio_set.pressed_button is None:
            return None
        return str(radio_set.pressed_button.name)


class LyricsApp(App):
    BINDINGS = [
        Binding("q", "quit", "Salir"),
        Binding("c", "open_config", "Config"),
    ]

    CSS = """
    $bg-dark: #000000;
    $bg-card: #000000;
    $text-light: #f5f5f7;
    $text-dim: #86868b;

    Screen {
        background: $bg-dark;
        align: center middle;
    }

    #box {
        width: 60;
        height: 18;
        padding: 1 2;
        background: $bg-card;
        border: round #ff2d55;
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

    #progress {
        width: 100%;
        height: 1;
        margin-top: 1;
    }

    #progress Bar {
        width: 1fr;
    }
    #progress Bar > .bar--bar {
        color: #939292;
        background: $surface
    }
    #progress Bar > .bar--complete {
        color: #f3f3f3;
    }
    #brand {
        height: 1;
        content-align: left bottom;
        color: $text-dim;
        text-style: italic;
        margin: 0;
    }

    ScrollBar {
        background: transparent;
        width: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Static("Esperando Reproduccion...", id="song_info")
            yield Static("", id="lyrics")
            yield ProgressBar(id="progress", total=100, show_eta=False)
            yield Static(f"NeoPlug Lyrics - press \"c\" to configure", id="brand")

    def on_mount(self) -> None:
        self.last_song = None
        self.current_player = None
        self.manual_player: str | None = None
        self.current_lyrics: list[tuple[float, str]] = []
        self.has_synced_lyrics = False
        self.last_line_index = -1
        self.duration: float | None = None
        self.accent = "#FFFFFF"
        self.visible_lines = 5

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
        artist, title = song.split("|", 1)
        title = clear_title(title)

        self.info.update(f"{artist} - {title}")
        self.lyrics_widget.update("Buscando letra...")

        self.duration = get_duration(player)
        self.progress_bar.update(total=self.duration or 100, progress=0)

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


if __name__ == "__main__":
    LyricsApp().run()