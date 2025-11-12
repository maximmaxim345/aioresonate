# Spec Compliance Report: Message Ordering

This report documents inconsistencies between SPEC.md and the implementation regarding message ordering requirements.

## Scope
This analysis focuses exclusively on order checking of incoming messages, specifically:
- `client/hello` must be the first message from client to server
- `server/hello` must be sent by server after receiving `client/hello`
- No other messages should be sent before the handshake is complete
- Clients should wait to receive `server/hello` before sending additional messages

## Inconsistencies Found

### 1. Server Error Message Misleading (server/client.py:455)

**Location:** `/aioresonate/server/client.py:455`

**Spec Requirement:**
> "Only after receiving this message should the client send any other messages" (SPEC.md:225-226)

**Issue:**
The error message states "Cannot send messages before receiving server/hello" but the server is checking whether it has **sent** `server/hello`, not whether the client has **received** it.

**Code:**
```python
if (
    self._client_info is not None
    and not self._server_hello_sent
    and not isinstance(message, ClientHelloMessage)
):
    raise ValueError("Cannot send messages before receiving server/hello")
```

**Impact:** The error message describes the problem from the client's perspective ("before receiving") but the check is from the server's perspective ("before sending"). While functionally correct due to WebSocket message ordering guarantees, the error message is misleading and could confuse developers debugging connection issues.

---

### 2. Server Signals Events Before Sending server/hello (server/client.py:477)

**Location:** `/aioresonate/server/client.py:477`

**Spec Requirement:**
> "Before this handshake is complete, no other messages should be sent." (SPEC.md:56)

**Issue:**
The server calls `_handle_client_connect(self)` which signals `ClientAddedEvent` **before** sending `server/hello`. If event handlers registered with the server send messages to the client in response to `ClientAddedEvent`, those messages would violate the spec by being sent before the handshake completes.

**Code Sequence (lines 459-486):**
```python
case ClientHelloMessage(client_info):
    # ... initialization code ...
    self._handle_client_connect(self)          # Line 477: Signals ClientAddedEvent
    self._logger.debug("Sending server/hello in response to client/hello")
    self.send_message(                          # Lines 479-485: Send server/hello
        ServerHelloMessage(
            payload=ServerHelloPayload(
                server_id=self._server.id, name=self._server.name, version=1
            )
        )
    )
    self._server_hello_sent = True            # Line 486
```

**Impact:** Currently, no event handlers exist in the codebase that would send messages in response to `ClientAddedEvent`. However, this represents a spec violation waiting to happen - any future code that adds event listeners and sends messages to clients during `ClientAddedEvent` handling would cause messages to be sent before `server/hello`, breaking the handshake protocol.

**Recommended Fix:** Signal `ClientAddedEvent` after sending `server/hello` and setting `_server_hello_sent = True`.

---

### 3. Client Drops Binary Messages Without Proper Rejection (client/client.py:631)

**Location:** `/aioresonate/client/client.py:631`

**Spec Requirement:**
> "Binary messages should be rejected if there is no active stream." (SPEC.md:398, 526)

**Issue:**
The client implementation drops binary messages when there is no active stream with only a debug-level log, rather than properly "rejecting" them as specified.

**Code:**
```python
async def _handle_audio_chunk(self, timestamp_us: int, payload: bytes) -> None:
    """Handle incoming audio chunk and notify callback."""
    if self._audio_chunk_callback is None:
        return
    if self._current_pcm_format is None:
        logger.debug("Dropping audio chunk without format")  # Line 631
        return
```

**Comparison with Server:**
The server implementation logs a warning when receiving binary messages without an active stream:
```python
if not self._group.has_active_stream:
    self._logger.warning(
        "Received binary message from client with no active stream, rejecting"
    )
```

**Impact:** Binary messages received out-of-order or before stream initialization are silently dropped with debug-level logging. The spec's use of "rejected" suggests a more visible error handling approach (warning/error level logging or connection termination).

**Recommended Fix:** Change the log level from `debug` to `warning` to match the server's behavior and better align with the spec's "rejected" terminology.

---

## Implementation Strengths

The following aspects of message ordering are correctly implemented:

- Client correctly sends `client/hello` as the first message (client/client.py:298)
- Client correctly waits for `server/hello` before sending other messages (client/client.py:300-304)
- Server correctly validates that `client/hello` is the first message received (server/client.py:446-447)
- Server correctly sends `server/hello` immediately after receiving `client/hello`
- WebSocket message ordering guarantees are properly relied upon for handshake synchronization
