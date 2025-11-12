# SPEC.md Compliance Report

This report documents inconsistencies between the SPEC.md definitions section and the actual implementation.

## Inconsistencies Found

### 1. Resonate Group: Volume State Implementation

**SPEC.md Reference:** Line 16

**Specification States:**
> **Resonate Group** - Each group has the following states: list of member clients, volume, mute, and playback state

**Issue:**
The specification explicitly lists "volume" as one of the group's states. However, the implementation does not store volume as a group state. Instead, volume is calculated on-demand as the average of all player volumes.

**Implementation Location:** `aioresonate/server/group.py:1185-1192`

```python
@property
def volume(self) -> int:
    """Current group volume (0-100), calculated as average of player volumes."""
    players = self.players()
    if not players:
        return 100
    # Calculate average volume from all players
    total_volume = sum(player.volume for player in players)
    return round(total_volume / len(players))
```

**Analysis:**
The definition describes volume as a state that the group "has", implying it is an intrinsic property. The implementation derives this value from member clients rather than maintaining it as a group-level state.

---

### 2. Resonate Group: Minimum Client Requirement Not Enforced

**SPEC.md Reference:** Line 16

**Specification States:**
> **Resonate Group** - a group of clients. Each client belongs to exactly one group, and **every group has at least one client**.

**Issue:**
The specification mandates that "every group has at least one client". However, the implementation's group constructor accepts zero or more clients without validation.

**Implementation Location:** `aioresonate/server/group.py:178-190`

```python
def __init__(self, server: ResonateServer, *args: ResonateClient) -> None:
    """
    DO NOT CALL THIS CONSTRUCTOR. INTERNAL USE ONLY.

    Args:
        server: The ResonateServer instance this group belongs to.
        *args: Clients to add to this group.
    """
    self._clients = list(args)
    # ... rest of initialization
```

**Analysis:**
The constructor signature `*args: ResonateClient` allows zero clients to be passed. No validation enforces the "at least one client" requirement stated in the definition. An empty group can theoretically be created, violating the specification's constraint.

---

### 3. Binary Message Timestamp Data Type Mismatch

**SPEC.md Reference:** Lines 402, 529

**Specification States:**
> - Bytes 1-8: timestamp (big-endian **int64**) - server clock time in microseconds

The specification consistently refers to timestamps as "int64" (signed 64-bit integer) throughout the binary message format documentation.

**Issue:**
The implementation uses unsigned 64-bit integers (uint64) for binary message timestamps, not signed int64 as specified.

**Implementation Location:** `aioresonate/models/__init__.py:56`

```python
# Binary header (big-endian): message_type(1) + timestamp_us(8) = 9 bytes
BINARY_HEADER_FORMAT = ">BQ"
#                       ^^
#                       ||
#                       |+-- Q = unsigned long long (uint64)
#                       +--- B = unsigned char (uint8)
```

**Analysis:**
Python's struct format code "Q" represents an unsigned 64-bit integer (uint64), while "q" (lowercase) would represent a signed 64-bit integer (int64). The specification explicitly states "int64" in multiple locations, but the implementation uses the unsigned variant.

While timestamps are always positive in practice (representing microseconds since a monotonic clock origin), this is still a deviation from the specified data type.

---

## End of Report

All inconsistencies have been documented. This report focuses solely on deviations from the SPEC.md definitions section and does not include aspects that correctly follow the specification.
