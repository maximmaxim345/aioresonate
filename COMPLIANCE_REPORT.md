# Resonate Protocol Compliance Report: Player Role

**Analysis Scope**: Player role implementation (models, server, client/CLI)
**Specification Version**: As defined in SPEC.md on branch feat/update-spec
**Date**: 2025-11-12

This report documents inconsistencies between the SPEC.md specification and the actual implementation for the player role. Only non-compliant items are listed.

---

## Critical Issues

### 1. Client Does Not Handle `server/command` Messages

**Specification Reference**: [Server → Client: `server/command`](SPEC.md#server--client-servercommand)

**Issue**: The client implementation (`aioresonate/client/client.py`) does not include a handler for `ServerCommandMessage` in its message processing logic.

**Location**: `aioresonate/client/client.py:488-504`

**Details**:
- The client's `_handle_json_message()` method has a match statement that handles various server messages
- `ServerCommandMessage` is not included in the match cases
- This means volume and mute commands sent from the server to player clients are silently ignored
- Players cannot respond to server-initiated volume/mute control

**Expected Behavior**:
The client should handle `server/command` messages containing player commands (volume/mute) and:
1. Update the internal volume/mute state
2. Apply the changes to the audio output
3. Send a `client/state` update back to the server (see Issue #2)

**Spec Quote**:
> Request the player to perform an action, e.g., change volume or mute state.
>
> - `player`: object
>   - `command`: 'volume' | 'mute' - must be one of the values listed in `supported_commands`
>   - `volume?`: integer - volume range 0-100, only set if `command` is `volume`
>   - `mute?`: boolean - true to mute, false to unmute, only set if `command` is `mute`

---

### 2. Client Does Not Send State Updates After Server Commands

**Specification Reference**: [Client → Server: `client/state` player object](SPEC.md#client--server-clientstate-player-object)

**Issue**: The client does not send `client/state` updates after receiving `server/command` messages.

**Location**: `aioresonate/client/client.py` (missing implementation)

**Details**:
- This issue is directly related to Issue #1 (client not handling server/command)
- Even if server commands were handled, there's no code to send state updates after applying them
- The spec explicitly requires state updates when volume/mute changes occur via server commands

**Expected Behavior**:
After receiving and processing a `server/command` with player commands, the client should send a `client/state` message with the updated player state (volume/muted).

**Spec Quote**:
> State updates must be sent whenever any state changes, including when the volume was changed through a `server/command` or via device controls.

---

## Server Implementation Issues

### 3. Server Does Not Validate `supported_commands` Before Sending Commands

**Specification Reference**: [Server → Client: `server/command` player object](SPEC.md#server--client-servercommand-player-object)

**Issue**: The server's `PlayerClient.set_volume()` and `mute()`/`unmute()` methods do not check if the player actually supports these commands before sending them.

**Location**: `aioresonate/server/player.py:49-89`

**Details**:
- The `PlayerClient` class has `set_volume()`, `mute()`, and `unmute()` methods
- These methods directly send `ServerCommandMessage` without checking `supported_commands`
- The spec requires that commands "must be one of the values listed in `supported_commands`"
- A player might not support volume or mute commands (e.g., hardware players with fixed volume)

**Expected Behavior**:
Before sending a command, the server should check if the command type is in the player's `supported_commands` list (from `ClientHelloPlayerSupport`). If not supported, the server should either:
- Raise an error/exception
- Log a warning and skip the command
- Return a failure indicator to the caller

**Spec Quote**:
> `command`: 'volume' | 'mute' - must be one of the values listed in `supported_commands` in the [`player_support`](#client--server-clienthello-player-support-object) object in the [`client/hello`](#client--server-clienthello) message

---

## Model/Protocol Message Issues

### 4. StreamEndMessage Has No Payload Field Definition

**Specification Reference**: [Server → Client: `stream/end`](SPEC.md#server--client-streamend)

**Issue**: The `StreamEndMessage` model definition does not explicitly document that it has no payload.

**Location**: `aioresonate/models/core.py:348-354`

**Details**:
- The `StreamEndMessage` class is defined with only a `type` field
- While this is technically correct per the spec ("No payload"), the model could be clearer
- Other message types have explicit payload fields even when optional
- This inconsistency could cause confusion for developers

**Note**: This is a minor documentation/style issue rather than a functional bug. The implementation is technically compliant since the spec says "No payload," but the model could be more explicit.

**Current Implementation**:
```python
@dataclass
class StreamEndMessage(ServerMessage):
    """Message sent by the server to end a stream."""

    type: Literal["stream/end"] = "stream/end"
```

**Suggested Improvement** (for clarity):
Add a comment or docstring explicitly stating "This message has no payload per the Resonate protocol specification."

---

## Client/Server Behavior Inconsistencies

### 5. Client Accepts Binary Messages Without Explicit Stream Check

**Specification Reference**: [Server → Client: Audio Chunks (Binary)](SPEC.md#server--client-audio-chunks-binary)

**Issue**: While the client effectively rejects binary messages without an active stream, it does so implicitly rather than with an explicit check.

**Location**: `aioresonate/client/client.py:506-522` and `aioresonate/client/client.py:626-632`

**Details**:
- The spec states: "Binary messages should be rejected if there is no active stream"
- The server explicitly checks for this condition (server/client.py:387-396)
- The client only checks if `_current_pcm_format is None` in `_handle_audio_chunk()`
- This works in practice but relies on implementation details rather than explicit stream state
- If future roles (artwork, visualizer) are added, this pattern may not work

**Current Behavior**:
```python
async def _handle_audio_chunk(self, timestamp_us: int, payload: bytes) -> None:
    if self._audio_chunk_callback is None:
        return
    if self._current_pcm_format is None:
        logger.debug("Dropping audio chunk without format")
        return
```

**Expected Behavior**:
The client should have an explicit `has_active_stream` flag or check in `_handle_binary_message()` before processing any binary message, similar to the server's implementation.

**Spec Quote**:
> Binary messages should be rejected if there is no active stream.

---

## Summary

**Total Issues Found**: 5 (3 critical, 2 minor)

**Critical Issues Requiring Code Changes**:
1. Client missing `server/command` message handler
2. Client missing state update after server commands
3. Server not validating `supported_commands` before sending commands

**Minor Issues** (style/documentation):
4. StreamEndMessage payload field documentation
5. Client implicit stream state checking

**Recommendation**: Address the three critical issues before considering the player role implementation spec-compliant. Issues #1 and #2 break a fundamental client-server interaction pattern, while Issue #3 could cause runtime errors with certain player types.
