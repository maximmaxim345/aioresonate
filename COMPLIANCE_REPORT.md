# SPEC.md Compliance Report

**Scope:** Stream lifetime and state
**Date:** 2025-11-12

This report documents inconsistencies between SPEC.md and the implementation in models, server, and client/CLI.

## Stream Lifetime Inconsistencies

### 1. Binary Messages Not Rejected Without Active Stream

**Specification:** (Lines 398, 526, 569)
> "Binary messages should be rejected if there is no active stream."

**Implementation:**
- **File:** `aioresonate/client/client.py:626-632`
- The client implementation checks if `_current_pcm_format` is None and silently drops the message with a debug log
- Binary messages are not "rejected" - they are simply dropped
- The check uses `_current_pcm_format` instead of the stream state marker `_current_player`

**Impact:**
- Binary messages arriving before stream/start or after stream/end are not properly rejected
- No error feedback to the server about protocol violations
- Inconsistent state checking (format vs. player stream state)

---

### 2. Metadata Clients Incorrectly Receive stream/start

**Specification:** (Line 272)
> Stream/start message structure with role-specific payloads for player, artwork, and visualizer only

**Implementation:**
- **File:** `aioresonate/server/group.py:287-288`
- The server sends stream/start to both METADATA and VISUALIZER clients
- Metadata role has no stream/start message defined in the specification

**Client Behavior:**
- **File:** `aioresonate/client/client.py:554-556`
- Client logs warning "Stream start message missing player payload" when receiving stream/start without player payload
- Returns early without processing

**Impact:**
- Protocol violation: metadata clients receive messages they shouldn't according to spec
- Unnecessary message transmission
- Client logs spurious warnings for normal operation

---

### 3. Metadata Clients Incorrectly Receive stream/end

**Specification:** (Lines 299-306)
> "Clients with the `player` role should stop playback and clear buffers."
> "Clients with the `visualizer` role should stop visualizing and clear buffers."

No mention of metadata role for stream/end.

**Implementation:**
- **File:** `aioresonate/server/group.py:760-761`
- The `_cleanup_streaming_resources` method sends stream/end to ALL clients without role filtering

**Impact:**
- Protocol violation: metadata clients receive stream/end messages
- Metadata clients process stream/end (clearing `_current_player` which they never set)
- Specification only defines stream/end behavior for player and visualizer roles

---

## State Management Inconsistencies

### 4. No Initial group/update After Handshake

**Specification:** (Sequence diagram, Lines 147-148)
> The sequence diagram shows group/update being sent after server/hello in the normal flow

**Implementation:**
- **File:** `aioresonate/server/client.py:477-486`
- After client/hello is received, server/hello is sent
- No group/update message is sent at this point
- Clients only receive group/update when:
  - Added to a group via `add_client()` (group.py:1320-1321)
  - Group playback state changes
  - Stream operations occur

**Impact:**
- New clients don't immediately know their group_id, group_name, or playback_state
- Clients in solo groups never receive initial group information until state changes
- Deviates from the expected message flow shown in the sequence diagram

---

### 5. No Server Enforcement of Initial client/state Requirement

**Specification:** (Lines 244-246)
> "Must be sent immediately after receiving [`server/hello`](#server--client-serverhello) for roles that report state (such as `player`), and whenever any state changes thereafter."

**Implementation:**
- **Client:** `aioresonate/client/client.py:306-312` correctly sends initial client/state for player role
- **Server:** No enforcement or tracking of whether initial state was received
- **File:** `aioresonate/server/client.py:498-500` processes client/state but doesn't verify it was sent first

**Impact:**
- Server accepts operations from players without ever receiving their initial state
- Player volume and mute state may be unknown to server until first update
- No protocol violation detection for clients that don't send initial state

---

## Additional Observations

### Binary Message Handling During Stream Transitions

**Context:**
- The spec requires binary messages to be rejected without an active stream
- Stream state transitions: stream/start → (active stream) → stream/end

**Client Implementation:**
- `_current_player` is set in `_handle_stream_start()` (client.py:568-574)
- `_current_player` is cleared in `_handle_stream_end()` (client.py:606)
- Binary audio chunks check `_current_pcm_format` not `_current_player` (client.py:630)

**Race Condition:**
- If stream/end arrives before all binary messages are processed, subsequent binary messages should be rejected
- Current implementation only checks PCM format, which may be set independently
- Proper check should be: `if self._current_player is None: reject/raise error`

---

### stream/update Sent During Reconfiguration

**Specification:** (Line 295)
> "Response: [`stream/update`](#server--client-streamupdate) with the new format for the requested role(s)."

**Implementation:**
- **File:** `aioresonate/server/group.py:395-403`
- During streamer reconfiguration, stream/start is sent instead of stream/update
- Comment at line 400: "Send stream/start messages to affected players"

**Analysis:**
- When players are reconfigured during active streaming, they receive stream/start
- According to the spec, format changes during streaming should use stream/update
- However, stream/start contains the complete format specification needed
- This may be intentional for complete reconfiguration, but differs from stream/request-format flow

---

## Summary

**Total Inconsistencies Found:** 5

**By Category:**
- Stream lifetime: 3 issues
- State management: 2 issues

**By Severity:**
- Protocol violations (messages sent to wrong roles): 2
- Missing enforcement (spec requirements not validated): 2
- Implementation details (wrong state checks): 1
