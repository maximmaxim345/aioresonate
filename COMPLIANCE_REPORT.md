# SPEC.md Compliance Report - Metadata Role

This report documents inconsistencies between the SPEC.md specification and the implementation, focusing exclusively on the metadata role.

## 1. Client Library Fails to Merge Delta Updates

**Location**: `aioresonate/client/client.py:614-620`

**SPEC Requirement** (line 261):
> Only include fields that have changed. The client will merge these updates into existing state. Fields set to `null` should be cleared from the client's state.

**Issue**:
The client library does not merge delta updates for metadata. When receiving a `server/state` message with metadata, the client simply stores the raw payload and passes it directly to callbacks without any merging logic:

```python
async def _handle_server_state(self, payload: ServerStatePayload) -> None:
    self._server_state = payload  # Raw replacement, no merging
    await self._notify_controller_callback(payload)
    if payload.metadata is not None:
        await self._notify_metadata_callback(payload)
```

**Expected Behavior**:
The client should maintain a merged state where:
- Fields present in updates are merged into existing state
- Fields set to `null` clear the corresponding state
- Undefined fields (using `UndefinedField`) preserve existing state
- Callbacks receive the complete merged state, not just deltas

**Impact**:
Applications using the client library must implement their own merging logic, making the library harder to use correctly and increasing the risk of inconsistent state handling across different implementations.

---

## 2. CLI Ignores Multiple Metadata Fields

**Location**: `aioresonate/cli.py:54-78`

**SPEC Requirement** (lines 454-466):
The metadata object includes 13 fields: `timestamp`, `title`, `artist`, `album_artist`, `album`, `artwork_url`, `year`, `track`, `track_progress`, `track_duration`, `playback_speed`, `repeat`, `shuffle`.

**Issue**:
The CLI's `CLIState` class only tracks 5 of the 13 metadata fields:

```python
@dataclass
class CLIState:
    # ... other fields ...
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    track_progress: int | None = None
    track_duration: int | None = None
```

**Missing Fields**:
- `timestamp` - Required for track progress calculation
- `album_artist` - Album artist information
- `artwork_url` - URL to artwork image
- `year` - Release year
- `track` - Track number
- `playback_speed` - Playback speed multiplier
- `repeat` - Repeat mode ('off', 'one', 'all')
- `shuffle` - Shuffle state

The `update_metadata` method also only processes the 5 tracked fields:

```python
def update_metadata(self, metadata: SessionUpdateMetadata) -> bool:
    changed = False
    for attr in ("title", "artist", "album", "track_progress", "track_duration"):
        # Only handles 5 of 13 fields
        ...
```

**Impact**:
Users of the CLI cannot see important metadata such as album artist, track number, playback speed, repeat/shuffle modes, or release year. This provides an incomplete user experience compared to what the protocol supports.

---

## 3. CLI Does Not Implement Track Progress Calculation Formula

**Location**: `aioresonate/cli.py:89-92`

**SPEC Requirement** (line 450):
> Clients can calculate the current track position at any time using the last received values: `current_track_progress_ms = max(min(metadata.track_progress + (current_time - metadata.timestamp) * metadata.playback_speed / 1000000, metadata.track_duration), 0)`

**Issue**:
The CLI displays track progress directly without applying the specified formula:

```python
if self.track_duration:
    progress_s = (self.track_progress or 0) / 1000
    duration_s = self.track_duration / 1000
    lines.append(f"Progress: {progress_s:>5.1f} / {duration_s:>5.1f} s")
```

This implementation has three problems:
1. Does not store or use the `timestamp` field
2. Does not store or use the `playback_speed` field
3. Does not calculate current position using the formula

**Expected Behavior**:
The CLI should:
1. Store `timestamp` when metadata updates are received
2. Store `playback_speed` (or default to 1000 if not provided)
3. Calculate current progress using: `max(min(track_progress + (current_time - timestamp) * playback_speed / 1000000, track_duration), 0)`

**Impact**:
The displayed track progress becomes stale immediately after receiving an update. It only updates when the server sends a new metadata message, rather than continuously advancing in real-time as the spec intends. This results in a poor user experience where progress appears to jump forward in discrete steps rather than flowing smoothly.

---

## 4. CLI Does Not Implement Delta Update Merging

**Location**: `aioresonate/cli.py:68-78`

**SPEC Requirement** (line 261):
> Only include fields that have changed. The client will merge these updates into existing state. Fields set to `null` should be cleared from the client's state.

**Issue**:
While the CLI's `update_metadata` method does preserve existing values for undefined fields, it does not explicitly handle the case where a field is set to `null` to clear it:

```python
def update_metadata(self, metadata: SessionUpdateMetadata) -> bool:
    changed = False
    for attr in ("title", "artist", "album", "track_progress", "track_duration"):
        value = getattr(metadata, attr)
        if isinstance(value, UndefinedField):
            continue  # Preserves existing value
        if getattr(self, attr) != value:
            setattr(self, attr, value)  # Sets value, including None
            changed = True
    return changed
```

While this technically does set `None` values, the implementation lacks explicit handling for the clearing semantics described in the spec. The code doesn't distinguish between "field not sent" (UndefinedField) and "field explicitly cleared" (None).

**Expected Behavior**:
The implementation should explicitly document or demonstrate understanding that:
- `UndefinedField` means "don't change this field"
- `None` means "clear this field"

**Impact**:
Minor: The current implementation technically works correctly for basic cases, but the lack of explicit null-handling logic makes the code's intent unclear and could lead to bugs if the implementation is modified without understanding the delta update semantics.

---

## Summary Statistics

**Metadata Fields in SPEC**: 13 fields (timestamp, title, artist, album_artist, album, artwork_url, year, track, track_progress, track_duration, playback_speed, repeat, shuffle)

**Metadata Fields Handled by CLI**: 5 fields (title, artist, album, track_progress, track_duration)

**Missing Fields**: 8 fields (61.5% incomplete)

**Critical Missing Features**:
- Delta update merging in client library
- Track progress calculation formula
- Playback speed tracking
- Real-time progress updates
