# Spec Compliance Analysis Report - Core Messages

This report documents inconsistencies between the SPEC.md specification and the implementation for **core messages** only.

## Message Structure Inconsistencies

### 1. `stream/end` Message Payload

**Specification (SPEC.md:299-307):**
- Line 62: "All messages have a `type` field identifying the message and a `payload` object containing message-specific data."
- Line 307: "No payload."

**Implementation (aioresonate/models/core.py:349-354):**
```python
@dataclass
class StreamEndMessage(ServerMessage):
    """Message sent by the server to end a stream."""
    type: Literal["stream/end"] = "stream/end"
```

**Inconsistency:**
The spec states that "all messages have a payload object" (line 62), but for `stream/end` it says "No payload" (line 307). The implementation has no `payload` field at all, resulting in JSON serialization as `{"type": "stream/end"}` rather than `{"type": "stream/end", "payload": {}}`.

This is ambiguous in the spec: does "No payload" mean:
- The message has no `payload` field (current implementation), or
- The message has an empty `payload` object?

The example message structure (lines 64-88) shows all messages with both `type` and `payload` fields, suggesting the latter interpretation would be more consistent.

## Message Organization Inconsistencies

### 2. `group/update` Message Location

**Specification (SPEC.md:185-318):**
- Line 185: "## Core messages"
- Line 188: "Every Resonate client and server must implement all messages in this section regardless of their specific roles."
- Lines 309-318: Defines `group/update` as part of Core messages section

**Implementation:**
- Core messages are defined in: `aioresonate/models/core.py`
- `GroupUpdateServerMessage` and `GroupUpdateServerPayload` are defined in: `aioresonate/models/controller.py:78-102`

**Inconsistency:**
The `group/update` message is specified as a core message that must be implemented by all clients regardless of roles (SPEC.md:188), but it's implemented in the controller module rather than the core module. While this may be an organizational choice, it contradicts the spec's structure where core messages should be in the core messages module.

## Field Naming Inconsistencies

### 3. Player Support Format Field Name

**Specification (SPEC.md:328):**
```
- `support_formats`: object[] - list of supported audio formats in priority order
```

**Implementation (aioresonate/models/player.py:48):**
```python
support_formats: list[SupportedAudioFormat]
```

**Note:** This is actually **consistent** - the implementation correctly uses `support_formats` (plural) matching the spec. No inconsistency found.

## Message Sequence Validation

### 4. Pre-Handshake Message Restriction

**Specification (SPEC.md:55-56, 225-226):**
- "Before this handshake is complete, no other messages should be sent."
- "Only after receiving this message should the client send any other messages"

**Implementation (aioresonate/server/client.py:449-455):**
```python
if (
    self._client_info is not None
    and not self._server_hello_sent
    and not isinstance(message, ClientHelloMessage)
):
    raise ValueError("Cannot send messages before receiving server/hello")
```

**Note:** The server implementation correctly enforces this restriction. No inconsistency found.

## Binary Message Handling

### 5. Binary Message Validation for Stream Absence

**Specification (SPEC.md:397-398, 526, 569):**
- "Binary messages should be rejected if there is no active stream."

**Implementation (aioresonate/server/client.py:384-396):**
```python
if msg.type == WSMsgType.BINARY:
    if not self._group.has_active_stream:
        self._logger.warning(
            "Received binary message from client with no active stream, rejecting"
        )
```

**Note:** The server correctly rejects binary messages when there's no active stream. No inconsistency found.

## Summary

**Total Inconsistencies Found: 2**

1. **Critical:** `stream/end` message structure is ambiguous in the spec - implementation omits payload field entirely rather than providing empty payload object
2. **Organizational:** `group/update` message is defined in controller module instead of core module, despite being specified as a core message

These inconsistencies should be resolved by either:
- Updating the spec to clarify the intended behavior, or
- Updating the implementation to match the spec's intent more clearly
