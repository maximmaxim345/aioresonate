"""Enhanced responsive Textual-based TUI for the Resonate CLI client."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from typing import TYPE_CHECKING, Any, ClassVar

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


class LayoutMode(Enum):
    """Responsive layout modes based on terminal width."""

    TINY = "tiny"  # < 60: Minimal essentials
    COMPACT = "compact"  # 60-80: Basic info
    STANDARD = "standard"  # 80-120: Normal with small album
    FULL = "full"  # > 120: All features


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

                yield Label("Delay Adjustment", classes="help-heading help-section")
                yield Label("  [          - Decrease delay -10ms", classes="help-row")
                yield Label("  ]          - Increase delay +10ms", classes="help-row")
                yield Label("  {          - Decrease delay -50ms", classes="help-row")
                yield Label("  }          - Increase delay +50ms", classes="help-row")

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

    def watch_status(self, _new_status: str) -> None:
        """Update CSS class when status changes."""
        self.remove_class("status-connected", "status-connecting", "status-disconnected")
        self.add_class(f"status-{self.status}")


class SyncInfoWidget(Static):
    """Widget displaying time sync information."""

    is_synchronized = reactive(False)  # noqa: FBT003
    offset_us = reactive(0.0)
    error_us = reactive(0)
    static_delay_ms = reactive(0.0)

    DEFAULT_CSS = """
    SyncInfoWidget {
        height: auto;
        width: 100%;
        border: solid $primary;
        padding: 0 1;
    }

    .sync-good {
        color: $success;
    }

    .sync-syncing {
        color: $warning;
    }
    """

    def render(self) -> str:
        """Render sync information."""
        if not self.is_synchronized:
            return "⏱ Syncing..."

        offset_ms = self.offset_us / 1000.0
        error_ms = self.error_us / 1000.0

        return (
            f"✓ Synced | Offset: {offset_ms:+.1f}ms "
            f"| Error: ±{error_ms:.1f}ms | Delay: {self.static_delay_ms:+.0f}ms"
        )

    def watch_is_synchronized(self, _new_sync: bool) -> None:  # noqa: FBT001
        """Update CSS when sync state changes."""
        self.remove_class("sync-good", "sync-syncing")
        if self.is_synchronized:
            self.add_class("sync-good")
        else:
            self.add_class("sync-syncing")


class CompactSyncInfo(Static):
    """Compact sync info for smaller screens."""

    is_synchronized = reactive(False)  # noqa: FBT003
    static_delay_ms = reactive(0.0)

    def render(self) -> str:
        """Render compact sync info."""
        sync_icon = "✓" if self.is_synchronized else "⏱"
        return f"{sync_icon} Delay: {self.static_delay_ms:+.0f}ms"


class DelayControlsWidget(Static):
    """Widget with delay adjustment buttons."""

    def __init__(self, on_adjust: Any, *args: Any, **kwargs: Any) -> None:
        """Initialize delay controls."""
        super().__init__(*args, **kwargs)
        self._on_adjust = on_adjust

    def compose(self) -> ComposeResult:
        """Compose delay control buttons."""
        with Horizontal(id="delay-buttons"):
            yield Button("-50ms [{", id="btn-delay-minus-50", variant="error")
            yield Button("-10ms [", id="btn-delay-minus-10", variant="warning")
            yield Label("Adjust Delay", id="delay-label")
            yield Button("+10ms ]", id="btn-delay-plus-10", variant="warning")
            yield Button("+50ms ]}", id="btn-delay-plus-50", variant="success")

    @on(Button.Pressed, "#btn-delay-minus-50")
    def on_delay_minus_50(self) -> None:
        """Decrease delay by 50ms."""
        if callable(self._on_adjust):
            self._on_adjust(-50)

    @on(Button.Pressed, "#btn-delay-minus-10")
    def on_delay_minus_10(self) -> None:
        """Decrease delay by 10ms."""
        if callable(self._on_adjust):
            self._on_adjust(-10)

    @on(Button.Pressed, "#btn-delay-plus-10")
    def on_delay_plus_10(self) -> None:
        """Increase delay by 10ms."""
        if callable(self._on_adjust):
            self._on_adjust(10)

    @on(Button.Pressed, "#btn-delay-plus-50")
    def on_delay_plus_50(self) -> None:
        """Increase delay by 50ms."""
        if callable(self._on_adjust):
            self._on_adjust(50)


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
            bar_width = max(0, min(100, self.volume))
            fill.styles.width = f"{bar_width}%"
        except (LookupError, RuntimeError):
            # Widgets not ready yet
            pass


class AlbumCoverWidget(Static):
    """Widget to display album cover art with responsive sizing."""

    is_loading = reactive(False)  # noqa: FBT003

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the album cover widget."""
        super().__init__(*args, **kwargs)
        self._image_widget: TextualImage | None = None  # type: ignore[valid-type]
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
            return

        if album_art is None:
            placeholder.display = True
            placeholder.update(self._placeholder_text)
            if self._image_widget is not None:
                self._image_widget.display = False  # type: ignore[unreachable]
            if self._loading_widget is not None:
                self._loading_widget.display = False
            return

        self.is_loading = True
        try:
            if self._loading_widget is None:
                self._loading_widget = LoadingIndicator()
                await self.mount(self._loading_widget)
            self._loading_widget.display = True
        except (LookupError, RuntimeError):
            pass

        try:
            image = Image.open(BytesIO(album_art.image_data))

            logger.debug(
                "Loading album art: format=%s, size=%s, mode=%s, data_len=%d",
                album_art.format,
                image.size,
                image.mode,
                len(album_art.image_data),
            )

            if self._image_widget is not None:
                await self._image_widget.remove()  # type: ignore[unreachable]
                self._image_widget = None

            self._image_widget = TextualImage(image)
            await self.mount(self._image_widget)

            placeholder.display = False
            if self._loading_widget is not None:
                self._loading_widget.display = False
            self._image_widget.display = True

            logger.info("Album art loaded successfully")

        except (OSError, ValueError, ImportError):
            logger.exception("Failed to load album art")

            error_msg = "Album art unavailable"
            placeholder.update(error_msg)
            placeholder.display = True
            if self._image_widget is not None:
                self._image_widget.display = False  # type: ignore[unreachable]
            if self._loading_widget is not None:
                self._loading_widget.display = False

        finally:
            self.is_loading = False


class SongProgressWidget(Static):
    """Widget to display song progress with a progress bar."""

    progress = reactive(0)
    duration = reactive(0)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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

            progress_pct = (self.progress / self.duration) * 100 if self.duration > 0 else 0
            progress_bar = self.query_one("#progress-bar", ProgressBar)
            progress_bar.update(progress=progress_pct)

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
        on_previous: Any,
        on_play_pause: Any,
        on_stop: Any,
        on_next: Any,
        *args: Any,
        **kwargs: Any,
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
    """Enhanced responsive Textual UI for Resonate CLI client."""

    CSS = """
    Screen {
        background: $surface;
    }

    /* Main container */
    #main-container {
        height: 1fr;
        width: 100%;
    }

    /* Tiny mode styles */
    .layout-tiny #album-cover-container,
    .layout-tiny #sync-info-full,
    .layout-tiny #volume-container,
    .layout-tiny #metadata-container,
    .layout-tiny #delay-controls {
        display: none;
    }

    /* Compact mode styles */
    .layout-compact #album-cover-container,
    .layout-compact #sync-info-full,
    .layout-compact #delay-controls {
        display: none;
    }

    /* Standard mode styles */
    .layout-standard #sync-info-full,
    .layout-standard #delay-controls {
        display: none;
    }

    .layout-standard #album-cover-container {
        width: 30;
    }

    /* Full mode styles */
    .layout-full #sync-info-compact {
        display: none;
    }

    .layout-full #album-cover-container {
        width: 50;
    }

    /* Layout containers */
    #content-area {
        height: 1fr;
        width: 100%;
        layout: horizontal;
    }

    #album-cover-container {
        height: 100%;
        border: solid $primary;
        content-align: center middle;
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

    #sync-container {
        height: auto;
        padding: 0 2;
        margin: 1 1 0 1;
    }

    #progress-container {
        height: auto;
        padding: 1 2;
        margin: 1 1;
    }

    #song-progress {
        height: auto;
        width: 100%;
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

    #delay-controls {
        height: auto;
        margin: 0 1;
    }

    #delay-buttons {
        height: 3;
        align: center middle;
    }

    #delay-buttons Button {
        margin: 0 1;
        min-width: 12;
    }

    #delay-label {
        text-align: center;
        content-align: center middle;
        width: auto;
        padding: 0 2;
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
        ("left_square_bracket", "delay_down_small", "-10ms"),
        ("right_square_bracket", "delay_up_small", "+10ms"),
        ("left_curly_bracket", "delay_down_large", "-50ms"),
        ("right_curly_bracket", "delay_up_large", "+50ms"),
        ("question_mark", "help", "Help"),
        ("q", "quit", "Quit"),
    ]

    # Reactive properties
    connected = reactive(False)  # noqa: FBT003
    layout_mode = reactive(LayoutMode.FULL)

    def __init__(
        self,
        client: ResonateClient,
        state: CLIState,
        *args: Any,
        **kwargs: Any,
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

                    # Sync information
                    with Container(id="sync-container"):
                        yield SyncInfoWidget(id="sync-info-full")
                        yield CompactSyncInfo(id="sync-info-compact")

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

                    # Delay adjustment controls
                    with Container(id="delay-controls"):
                        yield DelayControlsWidget(
                            on_adjust=self._handle_delay_adjust, id="delay-widget"
                        )

            # Status bar
            with Container(id="status-container"):
                yield Label("State: ", id="playback-state")

        yield Footer()

    def on_mount(self) -> None:
        """Start the periodic update task."""
        self._update_task = asyncio.create_task(self._periodic_update())
        self._update_layout_for_size()
        self.connected = True

    def on_resize(self, _event: Resize) -> None:
        """Handle terminal resize."""
        self._update_layout_for_size()

    def _update_layout_for_size(self) -> None:
        """Update layout based on terminal size."""
        terminal_width = self.size.width

        # Determine layout mode
        if terminal_width < 60:
            self.layout_mode = LayoutMode.TINY
        elif terminal_width < 80:
            self.layout_mode = LayoutMode.COMPACT
        elif terminal_width < 120:
            self.layout_mode = LayoutMode.STANDARD
        else:
            self.layout_mode = LayoutMode.FULL

    def watch_layout_mode(self, _new_mode: LayoutMode) -> None:
        """Update CSS classes when layout mode changes."""
        try:
            container = self.query_one("#main-container")
            container.remove_class(
                "layout-tiny", "layout-compact", "layout-standard", "layout-full"
            )
            container.add_class(f"layout-{self.layout_mode.value}")
            logger.debug("Switched to %s layout mode", self.layout_mode.value)
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
            await asyncio.sleep(0.2)
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

            # Update sync info
            sync_full = self.query_one("#sync-info-full", SyncInfoWidget)
            sync_full.is_synchronized = self._client.is_time_synchronized()
            sync_full.offset_us = self._client.sync_offset_us
            sync_full.error_us = self._client.sync_error_us
            sync_full.static_delay_ms = self._client.static_delay_ms

            sync_compact = self.query_one("#sync-info-compact", CompactSyncInfo)
            sync_compact.is_synchronized = self._client.is_time_synchronized()
            sync_compact.static_delay_ms = self._client.static_delay_ms

            # Update progress
            progress_widget = self.query_one("#song-progress", SongProgressWidget)
            progress_widget.progress = self._state.track_progress or 0
            progress_widget.duration = self._state.track_duration or 0

            # Update volume slider
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
            pass

    # Button handlers
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

    def _handle_delay_adjust(self, delta_ms: int) -> None:
        """Handle delay adjustment."""
        current = self._client.static_delay_ms
        new_delay = current + delta_ms
        self._client.set_static_delay_ms(new_delay)
        logger.info("Adjusted delay: %+d ms (now %.0f ms)", delta_ms, new_delay)

    # Keyboard actions
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

    def action_delay_down_small(self) -> None:
        """Decrease delay by 10ms."""
        self._handle_delay_adjust(-10)

    def action_delay_up_small(self) -> None:
        """Increase delay by 10ms."""
        self._handle_delay_adjust(10)

    def action_delay_down_large(self) -> None:
        """Decrease delay by 50ms."""
        self._handle_delay_adjust(-50)

    def action_delay_up_large(self) -> None:
        """Increase delay by 50ms."""
        self._handle_delay_adjust(50)

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
