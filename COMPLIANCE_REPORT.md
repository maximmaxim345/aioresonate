# SPEC.md Compliance Report - Artwork Role

This report documents inconsistencies between SPEC.md and the implementation for the **artwork role** only.

## Client Implementation (aioresonate/client/client.py)

### 1. Missing Binary Message Handling for Artwork

**Location:** `aioresonate/client/client.py:506-522`

**Issue:** The client only handles `BinaryMessageType.AUDIO_CHUNK` (type 0) and ignores all other binary message types, including artwork channels.

**Spec Reference:** SPEC.md lines 525-540 specify that artwork binary messages use types 4-7 for channels 0-3.

**Current Implementation:**
```python
if message_type is BinaryMessageType.AUDIO_CHUNK:
    await self._handle_audio_chunk(header.timestamp_us, payload[BINARY_HEADER_SIZE:])
else:
    logger.debug("Ignoring unsupported binary message type: %s", message_type)
```

**Expected:** Client should handle `BinaryMessageType.ARTWORK_CHANNEL_0` through `ARTWORK_CHANNEL_3` (types 4-7) when the artwork role is supported.

### 2. Missing Artwork Payload Processing in stream/start

**Location:** `aioresonate/client/client.py:551-576`

**Issue:** The `_handle_stream_start` method only processes the `player` payload from `StreamStartMessage` and ignores the `artwork` payload.

**Spec Reference:** SPEC.md lines 502-511 specify that `stream/start` messages include an `artwork` object for clients with the artwork role.

**Current Implementation:**
```python
async def _handle_stream_start(self, message: StreamStartMessage) -> None:
    logger.info("Stream started")
    player = message.payload.player
    if player is None:
        logger.warning("Stream start message missing player payload")
        return
    # ... only handles player payload
```

**Expected:** Client should process `message.payload.artwork` when the artwork role is supported, storing the channel configurations.

### 3. Missing Artwork Callback Mechanism

**Location:** `aioresonate/client/client.py`

**Issue:** The client has no callback mechanism for artwork data, unlike audio chunks which have `set_audio_chunk_listener()` and `_audio_chunk_callback`.

**Spec Reference:** SPEC.md lines 525-540 specify that clients receive artwork as binary messages that should be displayed at specific timestamps.

**Expected:** Client should provide:
- A callback setter like `set_artwork_listener(callback)`
- A callback invoked with `(channel: int, timestamp_us: int, image_data: bytes, format: PictureFormat)`

### 4. Missing stream/request-format for Artwork

**Location:** `aioresonate/client/client.py`

**Issue:** The client has no method to send `stream/request-format` messages for artwork, even though the models exist in `aioresonate/models/artwork.py:115-138`.

**Spec Reference:** SPEC.md lines 487-500 specify that clients can request artwork format changes via `stream/request-format` messages.

**Expected:** Client should provide a method like:
```python
async def request_artwork_format(
    self,
    channel: int,
    *,
    source: ArtworkSource | None = None,
    format: PictureFormat | None = None,
    media_width: int | None = None,
    media_height: int | None = None,
) -> None
```

### 5. Missing stream/update Handling for Artwork

**Location:** `aioresonate/client/client.py:578-602`

**Issue:** The `_handle_stream_update` method only processes player updates and ignores artwork updates.

**Spec Reference:** SPEC.md lines 514-522 specify that `stream/update` messages can contain artwork channel configuration updates.

**Current Implementation:**
```python
async def _handle_stream_update(self, message: StreamUpdateMessage) -> None:
    player_update = message.payload.player
    if player_update is None:
        return
    # ... only handles player updates
```

**Expected:** Client should also process `message.payload.artwork` to update channel configurations when artwork role is supported.

## Server Implementation (aioresonate/server/group.py)

### 6. Artwork Not Sent on Stream Start

**Location:** `aioresonate/server/group.py:214-303` (`play_media`) and `aioresonate/server/group.py:634-683` (`_send_stream_start_msg`)

**Issue:** When `play_media()` is called, the server sends `stream/start` messages to artwork clients with channel configurations, but does not send the actual artwork images even if they were previously set via `set_media_art()`. Artwork is only sent when `set_media_art()` is called while a stream is active.

**Spec Reference:** While SPEC.md line 526 states "Binary messages should be rejected if there is no active stream," the typical usage pattern would be to set artwork before starting playback. The current implementation requires calling `set_media_art()` after `play_media()` for clients to receive artwork.

**Current Behavior:**
1. Call `set_media_art(image)` - artwork is stored in `_current_media_art` but not sent (no active stream)
2. Call `play_media()` - sends `stream/start` with artwork channel configs, initializes `_client_artwork_state`, but doesn't send stored artwork
3. Must call `set_media_art(image)` again to actually send the artwork to clients

**Expected Behavior:** After `play_media()` initializes the stream and `_client_artwork_state`, it should send any artwork that was previously stored in `_current_media_art` to the clients.

**Comparison:** The metadata role sends metadata automatically in `_send_group_update_to_clients()` during `play_media()`, creating an inconsistent behavior pattern between roles.

## Models (aioresonate/models/artwork.py)

No inconsistencies found. The models correctly implement the SPEC.md definitions for:
- `ClientHelloArtworkSupport` (SPEC.md lines 472-483)
- `StreamStartArtwork` (SPEC.md lines 502-511)
- `StreamUpdateArtwork` (SPEC.md lines 514-522)
- `StreamRequestFormatArtwork` (SPEC.md lines 487-500)
- Binary message types (SPEC.md lines 94-99)
