"""Enhanced Textual-based TUI for the Resonate CLI client."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, ClassVar

from PIL import Image
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.events import Key, Resize
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    LoadingIndicator,
    ProgressBar,
    Static,
)
from textual_image.widget import Image as TextualImage

if TYPE_CHECKING:
    from aioresonate.cli import CLIState
    from aioresonate.client import ResonateClient

from aioresonate.models.types import MediaCommand, PlaybackStateType

logger = logging.getLogger(__name__)


@dataclass
class AlbumArt:
    """Holds album art image data."""

    image_data: bytes
    format: str


class HelpScreen(ModalScreen[None]):
    """Modal screen showing keyboard shortcuts and help."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-dialog {
        width: 80;
        height: auto;
        max-height: 30;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #help-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #help-content {
        height: auto;
        max-height: 20;
    }

    .help-section {
        margin-top: 1;
    }

    .help-heading {
        text-style: bold;
        color: $primary;
    }

    .help-row {
        margin-left: 2;
    }

    #help-close-btn {
        width: 100%;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the help dialog."""
        with Container(id="help-dialog"):
            yield Label("Resonate TUI - Keyboard Shortcuts", id="help-title")
            with VerticalScroll(id="help-content"):
                yield Label("Playback Controls", classes="help-heading help-section")
                yield Label("  p          - Play", classes="help-row")
                yield Label("  Space      - Play/Pause toggle", classes="help-row")
                yield Label("  s          - Stop", classes="help-row")
                yield Label("  n          - Next track", classes="help-row")
                yield Label("  b          - Previous track", classes="help-row")

                yield Label("Volume Controls", classes="help-heading help-section")
                yield Label("  +/-        - Volume up/down (5%)", classes="help-row")
                yield Label("  m          - Toggle mute", classes="help-row")

                yield Label("Interface", classes="help-heading help-section")
                yield Label("  ?          - Show this help", classes="help-row")
                yield Label("  q          - Quit", classes="help-row")
                yield Label("  Esc        - Close dialog", classes="help-row")

            yield Button("Close", id="help-close-btn", variant="primary")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss()

    def on_key(self, event: object) -> None:
        """Handle key press to close."""
        if isinstance(event, Key) and event.key == "escape":
            self.dismiss()


class ConnectionStatus(Static):
    """Widget showing connection status."""

    status = reactive("disconnected")

    DEFAULT_CSS = """
    ConnectionStatus {
        width: auto;
        height: 1;
        padding: 0 1;
    }

    .status-connected {
        color: $success;
    }

    .status-connecting {
        color: $warning;
    }

    .status-disconnected {
        color: $error;
    }
    """

    def render(self) -> str:
        """Render the connection status."""
        if self.status == "connected":
            return "● Connected"
        if self.status == "connecting":
            return "◌ Connecting..."
        return "○ Disconnected"

    def watch_status(self, new_status: str) -> None:
        """Update CSS class when status changes."""
        self.remove_class("status-connected", "status-connecting", "status-disconnected")
        self.add_class(f"status-{new_status}")


class VolumeSlider(Static):
    """Visual volume slider widget."""

    volume = reactive(50)
    muted = reactive(False)  # noqa: FBT003

    DEFAULT_CSS = """
    VolumeSlider {
        width: 100%;
        height: 3;
        padding: 0 1;
    }

    #volume-bar-container {
        width: 100%;
        height: 1;
        background: $panel;
        border: tall $primary;
    }

    #volume-bar-fill {
        height: 1;
        background: $primary;
    }

    #volume-label {
        text-align: center;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the volume slider."""
        yield Label("", id="volume-label")
        with Container(id="volume-bar-container"):
            yield Static("", id="volume-bar-fill")

    def watch_volume(self, _new_volume: int) -> None:
        """Update the visual bar when volume changes."""
        self._update_display()

    def watch_muted(self, _new_muted: bool) -> None:  # noqa: FBT001
        """Update display when mute state changes."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the volume bar and label."""
        try:
            label = self.query_one("#volume-label", Label)
            mute_str = " (MUTED)" if self.muted else ""
            label.update(f"Volume: {self.volume}%{mute_str}")

            fill = self.query_one("#volume-bar-fill", Static)
            # Calculate width as percentage
            bar_width = max(0, min(100, self.volume))
            fill.styles.width = f"{bar_width}%"
        except (LookupError, RuntimeError):
            # Widgets not ready yet
            pass


class AlbumCoverWidget(Static):
    """Widget to display album cover art with responsive sizing."""

    is_loading = reactive(False)  # noqa: FBT003

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize the album cover widget."""
        super().__init__(*args, **kwargs)
        self._image_widget: TextualImage | None = None
        self._loading_widget: LoadingIndicator | None = None
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
            if self._loading_widget is not None:
                self._loading_widget.display = False
            return

        # Show loading indicator
        self.is_loading = True
        try:
            if self._loading_widget is None:
                self._loading_widget = LoadingIndicator()
                await self.mount(self._loading_widget)
            self._loading_widget.display = True
        except (LookupError, RuntimeError):
            pass

        try:
            # Load image using PIL
            image = Image.open(BytesIO(album_art.image_data))

            logger.debug(
                "Loading album art: format=%s, size=%s, mode=%s, data_len=%d",
                album_art.format,
                image.size,
                image.mode,
                len(album_art.image_data),
            )

            # Remove old image widget if it exists
            if self._image_widget is not None:
                await self._image_widget.remove()
                self._image_widget = None

            # Create new image widget with the PIL image
            self._image_widget = TextualImage(image)
            await self.mount(self._image_widget)

            # Hide placeholder and loading
            placeholder.display = False
            if self._loading_widget is not None:
                self._loading_widget.display = False
            self._image_widget.display = True

            logger.info("Album art loaded successfully")

        except (OSError, ValueError, ImportError) as e:
            # Show user-friendly error
            logger.exception("Failed to load album art")

            # Determine user-friendly message
            if isinstance(e, FileNotFoundError):
                error_msg = "Album art not available"
            elif isinstance(e, ImportError):
                error_msg = "Image library not available"
            else:
                error_msg = "Could not display album art"

            placeholder.update(error_msg)
            placeholder.display = True
            if self._image_widget is not None:
                self._image_widget.display = False
            if self._loading_widget is not None:
                self._loading_widget.display = False

        finally:
            self.is_loading = False


class SongProgressWidget(Static):
    """Widget to display song progress with a progress bar."""

    progress = reactive(0)
    duration = reactive(0)

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize the song progress widget."""
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        """Compose the progress widget."""
        yield ProgressBar(total=100, show_eta=False, id="progress-bar")
        yield Label("0:00 / 0:00", id="progress-time")

    def watch_progress(self, _new_progress: int) -> None:
        """Update display when progress changes."""
        self._update_display()

    def watch_duration(self, _new_duration: int) -> None:
        """Update display when duration changes."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the progress bar and time label."""
        try:
            if self.duration == 0:
                progress_bar = self.query_one("#progress-bar", ProgressBar)
                progress_bar.update(progress=0)
                time_label = self.query_one("#progress-time", Label)
                time_label.update("0:00 / 0:00")
                return

            # Update progress bar (percentage)
            progress_pct = (self.progress / self.duration) * 100 if self.duration > 0 else 0
            progress_bar = self.query_one("#progress-bar", ProgressBar)
            progress_bar.update(progress=progress_pct)

            # Update time label
            progress_str = self._format_time(self.progress)
            duration_str = self._format_time(self.duration)
            time_label = self.query_one("#progress-time", Label)
            time_label.update(f"{progress_str} / {duration_str}")
        except (LookupError, RuntimeError):
            pass

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
        try:
            button = self.query_one("#btn-play-pause", Button)
            if is_playing:
                button.label = "⏸ Pause"
            else:
                button.label = "▶ Play"
        except (LookupError, RuntimeError):
            pass


class ResonateTUI(App[None]):
    """Enhanced Textual UI for Resonate CLI client."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 1fr;
        width: 100%;
        layout: vertical;
    }

    #content-area {
        height: 1fr;
        width: 100%;
        layout: horizontal;
    }

    #album-cover-container {
        width: auto;
        height: 100%;
        border: solid $primary;
        content-align: center middle;
    }

    #album-cover-container.hidden {
        display: none;
    }

    #album-cover {
        width: 100%;
        height: 100%;
        content-align: center middle;
    }

    #right-panel {
        width: 1fr;
        height: 100%;
        layout: vertical;
    }

    #metadata-container {
        height: auto;
        border: solid $accent;
        padding: 1 2;
        margin: 0 1;
    }

    #progress-container {
        height: auto;
        padding: 1 2;
        margin: 1 1;
    }

    #song-progress {
        height: auto;
        width: 100%;
        layout: vertical;
    }

    #volume-container {
        height: auto;
        padding: 0 2;
        margin: 0 1;
    }

    #controls {
        height: auto;
        margin: 1 1;
    }

    #control-buttons {
        height: 3;
        align: center middle;
    }

    #status-container {
        height: auto;
        border: solid $warning;
        padding: 1 2;
        margin: 1 0 0 0;
    }

    Button {
        margin: 0 1;
        min-width: 10;
    }

    #progress-bar {
        width: 100%;
        margin: 0 0 1 0;
    }

    #progress-time {
        text-align: center;
        width: 100%;
    }

    Label {
        width: 100%;
    }

    #album-placeholder {
        text-align: center;
        content-align: center middle;
    }

    ConnectionStatus {
        dock: top;
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
        ("question_mark", "help", "Help"),
        ("q", "quit", "Quit"),
    ]

    # Reactive properties for better state management
    connected = reactive(False)  # noqa: FBT003
    mini_mode = reactive(False)  # noqa: FBT003

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
        self._album_width = 50

    def compose(self) -> ComposeResult:
        """Compose the main UI layout."""
        yield Header()
        yield ConnectionStatus(id="connection-status")

        with Container(id="main-container"):
            with Horizontal(id="content-area"):
                # Left side: Album cover
                with Container(id="album-cover-container"):
                    yield AlbumCoverWidget(id="album-cover")

                # Right side: Metadata and controls
                with Vertical(id="right-panel"):
                    # Song metadata
                    with Container(id="metadata-container"):
                        yield Label("Title: ", id="song-title")
                        yield Label("Artist: ", id="song-artist")
                        yield Label("Album: ", id="song-album")

                    # Progress bar
                    with Container(id="progress-container"):
                        yield SongProgressWidget(id="song-progress")

                    # Volume slider
                    with Container(id="volume-container"):
                        yield VolumeSlider(id="volume-slider")

                    # Control buttons
                    yield ControlButtonsWidget(
                        on_previous=self._handle_previous,
                        on_play_pause=self._handle_play_pause,
                        on_stop=self._handle_stop,
                        on_next=self._handle_next,
                        id="controls",
                    )

            # Status bar
            with Container(id="status-container"):
                yield Label("State: ", id="playback-state")

        yield Footer()

    def on_mount(self) -> None:
        """Start the periodic update task."""
        self._update_task = asyncio.create_task(self._periodic_update())
        self._update_layout_for_size()
        self.connected = True  # Assume connected on mount

    def on_resize(self, _event: Resize) -> None:
        """Handle terminal resize."""
        self._update_layout_for_size()

    def _update_layout_for_size(self) -> None:
        """Update layout based on terminal size."""
        try:
            terminal_width = self.size.width

            # Determine album cover visibility and width
            album_container = self.query_one("#album-cover-container")

            if terminal_width < 60:
                # Mini mode - hide album art
                album_container.add_class("hidden")
                self.mini_mode = True
            elif terminal_width < 100:
                # Medium mode - small album art
                album_container.remove_class("hidden")
                album_container.styles.width = 30
                self.mini_mode = False
            else:
                # Full mode - large album art
                album_container.remove_class("hidden")
                album_container.styles.width = 50
                self.mini_mode = False

        except (LookupError, RuntimeError):
            pass

    async def on_unmount(self) -> None:
        """Clean up the update task."""
        if self._update_task:
            self._update_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._update_task

    async def _periodic_update(self) -> None:
        """Periodically update the UI from the state."""
        while True:
            await asyncio.sleep(0.2)  # Faster updates
            await self.update_ui()

    async def update_ui(self) -> None:
        """Update all UI elements based on current state using reactive properties."""
        try:
            # Update metadata
            title_label = self.query_one("#song-title", Label)
            title_label.update(f"Title: {self._state.title or 'Unknown'}")

            artist_label = self.query_one("#song-artist", Label)
            artist_label.update(f"Artist: {self._state.artist or 'Unknown'}")

            album_label = self.query_one("#song-album", Label)
            album_label.update(f"Album: {self._state.album or 'Unknown'}")

            # Update progress using reactive properties
            progress_widget = self.query_one("#song-progress", SongProgressWidget)
            progress_widget.progress = self._state.track_progress or 0
            progress_widget.duration = self._state.track_duration or 0

            # Update volume slider using reactive properties
            volume_slider = self.query_one("#volume-slider", VolumeSlider)
            volume_slider.volume = self._state.volume if self._state.volume is not None else 0
            volume_slider.muted = self._state.muted or False

            # Update playback state
            state_label = self.query_one("#playback-state", Label)
            state = self._state.playback_state.value if self._state.playback_state else "unknown"
            state_label.update(f"State: {state}")

            # Update play/pause button
            controls = self.query_one("#controls", ControlButtonsWidget)
            is_playing = self._state.playback_state == PlaybackStateType.PLAYING
            controls.update_play_pause_button(is_playing)

            # Update album art if changed
            if self._state.album_art is not self._last_album_art:
                logger.debug(
                    "Album art changed: old=%s, new=%s",
                    self._last_album_art is not None,
                    self._state.album_art is not None,
                )
                self._last_album_art = self._state.album_art
                album_cover = self.query_one("#album-cover", AlbumCoverWidget)
                await album_cover.update_album_art(self._state.album_art)

            # Update connection status
            connection_status = self.query_one("#connection-status", ConnectionStatus)
            connection_status.status = "connected" if self.connected else "disconnected"

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

    def action_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())

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
