"""Textual-based TUI for the Resonate CLI client."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, ClassVar

from PIL import Image
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Label, ProgressBar, Static
from textual_image.widget import Image as TextualImage

if TYPE_CHECKING:
    from aioresonate.cli import CLIState
    from aioresonate.client import ResonateClient

from aioresonate.models.types import MediaCommand, PlaybackStateType


@dataclass
class AlbumArt:
    """Holds album art image data."""

    image_data: bytes
    format: str


class AlbumCoverWidget(Static):
    """Widget to display album cover art."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize the album cover widget."""
        super().__init__(*args, **kwargs)
        self._image_widget: TextualImage | None = None
        self._placeholder_text = "No Album Art"

    def compose(self) -> ComposeResult:
        """Compose the initial UI."""
        yield Label(self._placeholder_text, id="album-placeholder")

    async def update_album_art(self, album_art: AlbumArt | None) -> None:
        """Update the displayed album art."""
        try:
            placeholder = self.query_one("#album-placeholder", Label)
        except (LookupError, RuntimeError):
            # Widget not ready yet
            return

        if album_art is None:
            placeholder.display = True
            placeholder.update(self._placeholder_text)
            if self._image_widget is not None:
                self._image_widget.display = False
            return

        try:
            # Load image using PIL
            image = Image.open(BytesIO(album_art.image_data))

            # Remove old image widget if it exists
            if self._image_widget is not None:
                await self._image_widget.remove()
                self._image_widget = None

            # Create new image widget
            self._image_widget = TextualImage(image)
            await self.mount(self._image_widget)

            # Hide placeholder
            placeholder.display = False
            self._image_widget.display = True

        except (OSError, ValueError) as e:
            placeholder.update(f"Error: {e}")
            placeholder.display = True
            if self._image_widget is not None:
                self._image_widget.display = False


class SongProgressWidget(Static):
    """Widget to display song progress with a progress bar."""

    progress = reactive(0.0)
    duration = reactive(0.0)

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize the song progress widget."""
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        """Compose the progress widget."""
        with Vertical():
            yield ProgressBar(total=100, show_eta=False, id="progress-bar")
            yield Label("0:00 / 0:00", id="progress-time")

    def update_progress(self, progress_seconds: int | None, duration_seconds: int | None) -> None:
        """Update the progress bar and time display."""
        if duration_seconds is None or duration_seconds == 0:
            self.progress = 0.0
            self.duration = 0.0
            progress_bar = self.query_one("#progress-bar", ProgressBar)
            progress_bar.update(progress=0)
            time_label = self.query_one("#progress-time", Label)
            time_label.update("0:00 / 0:00")
            return

        progress = progress_seconds or 0
        self.progress = float(progress)
        self.duration = float(duration_seconds)

        # Update progress bar (percentage)
        progress_pct = (progress / duration_seconds) * 100 if duration_seconds > 0 else 0
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_bar.update(progress=progress_pct)

        # Update time label
        progress_str = self._format_time(progress)
        duration_str = self._format_time(duration_seconds)
        time_label = self.query_one("#progress-time", Label)
        time_label.update(f"{progress_str} / {duration_str}")

    def _format_time(self, seconds: int) -> str:
        """Format seconds as M:SS."""
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"


class ControlButtonsWidget(Static):
    """Widget with playback control buttons."""

    def __init__(
        self,
        on_previous: object,
        on_play_pause: object,
        on_stop: object,
        on_next: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        """Initialize control buttons."""
        super().__init__(*args, **kwargs)
        self._on_previous = on_previous
        self._on_play_pause = on_play_pause
        self._on_stop = on_stop
        self._on_next = on_next

    def compose(self) -> ComposeResult:
        """Compose the control buttons."""
        with Horizontal(id="control-buttons"):
            yield Button("⏮ Prev", id="btn-prev", variant="primary")
            yield Button("▶ Play", id="btn-play-pause", variant="success")
            yield Button("⏹ Stop", id="btn-stop", variant="warning")
            yield Button("⏭ Next", id="btn-next", variant="primary")

    @on(Button.Pressed, "#btn-prev")
    def on_previous_pressed(self) -> None:
        """Handle previous button press."""
        if callable(self._on_previous):
            self._on_previous()

    @on(Button.Pressed, "#btn-play-pause")
    def on_play_pause_pressed(self) -> None:
        """Handle play/pause button press."""
        if callable(self._on_play_pause):
            self._on_play_pause()

    @on(Button.Pressed, "#btn-stop")
    def on_stop_pressed(self) -> None:
        """Handle stop button press."""
        if callable(self._on_stop):
            self._on_stop()

    @on(Button.Pressed, "#btn-next")
    def on_next_pressed(self) -> None:
        """Handle next button press."""
        if callable(self._on_next):
            self._on_next()

    def update_play_pause_button(self, is_playing: bool) -> None:  # noqa: FBT001
        """Update the play/pause button label based on playback state."""
        button = self.query_one("#btn-play-pause", Button)
        if is_playing:
            button.label = "⏸ Pause"
        else:
            button.label = "▶ Play"


class ResonateTUI(App[None]):
    """Textual UI for Resonate CLI client."""

    CSS = """
    #album-cover-container {
        height: 20;
        width: 40;
        border: solid green;
        padding: 1;
    }

    #metadata-container {
        height: auto;
        padding: 1;
        border: solid blue;
    }

    #progress-container {
        height: auto;
        padding: 1;
    }

    #control-buttons {
        height: auto;
        align: center middle;
        padding: 1;
    }

    #status-container {
        height: auto;
        padding: 1;
        border: solid yellow;
    }

    Button {
        margin: 0 1;
    }

    #progress-bar {
        width: 100%;
    }

    #progress-time {
        text-align: center;
        width: 100%;
    }
    """

    BINDINGS: ClassVar = [
        ("p", "play", "Play"),
        ("space", "play_pause", "Play/Pause"),
        ("s", "stop", "Stop"),
        ("n", "next", "Next"),
        ("b", "previous", "Previous"),
        ("plus", "volume_up", "Vol+"),
        ("minus", "volume_down", "Vol-"),
        ("m", "mute", "Mute"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        client: ResonateClient,
        state: CLIState,
        *args: object,
        **kwargs: object,
    ) -> None:
        """Initialize the Resonate TUI."""
        super().__init__(*args, **kwargs)
        self._client = client
        self._state = state
        self._last_album_art: AlbumArt | None = None
        self._update_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        """Compose the main UI layout."""
        yield Header()

        with Container(id="main-container"):
            with Horizontal():
                # Left side: Album cover
                with Vertical(id="album-cover-container"):
                    yield AlbumCoverWidget(id="album-cover")

                # Right side: Metadata and controls
                with Vertical():
                    # Song metadata
                    with Vertical(id="metadata-container"):
                        yield Label("Title: ", id="song-title")
                        yield Label("Artist: ", id="song-artist")
                        yield Label("Album: ", id="song-album")

                    # Progress bar
                    with Vertical(id="progress-container"):
                        yield SongProgressWidget(id="song-progress")

                    # Control buttons
                    yield ControlButtonsWidget(
                        on_previous=self._handle_previous,
                        on_play_pause=self._handle_play_pause,
                        on_stop=self._handle_stop,
                        on_next=self._handle_next,
                        id="controls",
                    )

            # Status bar
            with Vertical(id="status-container"):
                yield Label("Volume: ", id="volume-status")
                yield Label("State: ", id="playback-state")

        yield Footer()

    def on_mount(self) -> None:
        """Start the periodic update task."""
        self._update_task = asyncio.create_task(self._periodic_update())

    async def on_unmount(self) -> None:
        """Clean up the update task."""
        if self._update_task:
            self._update_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._update_task

    async def _periodic_update(self) -> None:
        """Periodically update the UI from the state."""
        while True:
            await asyncio.sleep(0.5)
            await self.update_ui()

    async def update_ui(self) -> None:
        """Update all UI elements based on current state."""
        try:
            # Update metadata
            title_label = self.query_one("#song-title", Label)
            title_label.update(f"Title: {self._state.title or 'Unknown'}")

            artist_label = self.query_one("#song-artist", Label)
            artist_label.update(f"Artist: {self._state.artist or 'Unknown'}")

            album_label = self.query_one("#song-album", Label)
            album_label.update(f"Album: {self._state.album or 'Unknown'}")

            # Update progress
            progress_widget = self.query_one("#song-progress", SongProgressWidget)
            progress_widget.update_progress(self._state.track_progress, self._state.track_duration)

            # Update volume
            volume_label = self.query_one("#volume-status", Label)
            mute_str = " (muted)" if self._state.muted else ""
            volume = self._state.volume if self._state.volume is not None else 0
            volume_label.update(f"Volume: {volume}%{mute_str}")

            # Update playback state
            state_label = self.query_one("#playback-state", Label)
            state = self._state.playback_state.value if self._state.playback_state else "unknown"
            state_label.update(f"State: {state}")

            # Update play/pause button
            controls = self.query_one("#controls", ControlButtonsWidget)
            is_playing = self._state.playback_state == PlaybackStateType.PLAYING
            controls.update_play_pause_button(is_playing)

            # Update album art if changed
            if self._state.album_art != self._last_album_art:
                self._last_album_art = self._state.album_art
                album_cover = self.query_one("#album-cover", AlbumCoverWidget)
                await album_cover.update_album_art(self._state.album_art)
        except (LookupError, RuntimeError):
            # Widgets not ready yet during initialization
            pass

    # Button handlers
    # Note: Fire-and-forget tasks are intentional for UI handlers (RUF006)
    def _handle_previous(self) -> None:
        """Handle previous button."""
        _ = asyncio.create_task(self._send_command(MediaCommand.PREVIOUS))  # noqa: RUF006

    def _handle_play_pause(self) -> None:
        """Handle play/pause button."""
        if self._state.playback_state == PlaybackStateType.PLAYING:
            _ = asyncio.create_task(self._send_command(MediaCommand.PAUSE))  # noqa: RUF006
        else:
            _ = asyncio.create_task(self._send_command(MediaCommand.PLAY))  # noqa: RUF006

    def _handle_stop(self) -> None:
        """Handle stop button."""
        _ = asyncio.create_task(self._send_command(MediaCommand.STOP))  # noqa: RUF006

    def _handle_next(self) -> None:
        """Handle next button."""
        _ = asyncio.create_task(self._send_command(MediaCommand.NEXT))  # noqa: RUF006

    # Keyboard actions
    # Note: Fire-and-forget tasks are intentional for UI handlers (RUF006)
    def action_play(self) -> None:
        """Play action."""
        _ = asyncio.create_task(self._send_command(MediaCommand.PLAY))  # noqa: RUF006

    def action_play_pause(self) -> None:
        """Play/pause action."""
        self._handle_play_pause()

    def action_stop(self) -> None:
        """Stop action."""
        _ = asyncio.create_task(self._send_command(MediaCommand.STOP))  # noqa: RUF006

    def action_next(self) -> None:
        """Next track action."""
        _ = asyncio.create_task(self._send_command(MediaCommand.NEXT))  # noqa: RUF006

    def action_previous(self) -> None:
        """Previous track action."""
        _ = asyncio.create_task(self._send_command(MediaCommand.PREVIOUS))  # noqa: RUF006

    def action_volume_up(self) -> None:
        """Increase volume."""
        _ = asyncio.create_task(self._change_volume(5))  # noqa: RUF006

    def action_volume_down(self) -> None:
        """Decrease volume."""
        _ = asyncio.create_task(self._change_volume(-5))  # noqa: RUF006

    def action_mute(self) -> None:
        """Toggle mute."""
        _ = asyncio.create_task(self._toggle_mute())  # noqa: RUF006

    async def _send_command(self, command: MediaCommand) -> None:
        """Send a media command to the server."""
        if command not in self._state.supported_commands:
            return
        await self._client.send_group_command(command)

    async def _change_volume(self, delta: int) -> None:
        """Change volume by delta."""
        if MediaCommand.VOLUME not in self._state.supported_commands:
            return
        current = self._state.volume if self._state.volume is not None else 50
        target = max(0, min(100, current + delta))
        await self._client.send_group_command(MediaCommand.VOLUME, volume=target)

    async def _toggle_mute(self) -> None:
        """Toggle mute state."""
        if MediaCommand.MUTE not in self._state.supported_commands:
            return
        target = not bool(self._state.muted)
        await self._client.send_group_command(MediaCommand.MUTE, mute=target)
