# SPEC.md Compliance Report - Controller Role

This report documents inconsistencies between the SPEC.md specification and the implementation for the **controller role**. It focuses exclusively on deviations from the specification and does not include summaries or items that comply with the spec.

## 1. PAUSED State Never Used

**Severity:** High
**Location:** `aioresonate/server/group.py`

The specification defines three playback states in `group/update` messages (SPEC.md:315):
- `'playing'`
- `'paused'`
- `'stopped'`

**Issue:** The implementation never sets or reports `PlaybackStateType.PAUSED`. The `ResonateGroup._current_state` field only transitions between `PLAYING` (line 290) and `STOPPED` (line 848). There is no code path that sets the state to `PAUSED`.

**Impact:**
- Clients with the controller role never receive `playback_state: 'paused'` in `group/update` messages
- The pause functionality is incomplete - while the group signals `PAUSE` commands as events, it doesn't track paused state
- Controller clients cannot distinguish between stopped and paused states

## 2. Incorrect Playback State Logic

**Severity:** Medium
**Location:** `aioresonate/server/group.py:307-311`, `1307-1312`

In `_send_group_update_to_clients()` and `add_client()`, the code uses:

```python
playback_state = (
    PlaybackStateType.PLAYING
    if self._current_state == PlaybackStateType.PLAYING
    else PlaybackStateType.PAUSED
)
```

**Issue:** This logic incorrectly assumes that any non-PLAYING state is PAUSED. If `_current_state` is `STOPPED`, the message would still send `playback_state: 'paused'`.

**Impact:** When a controller client joins a group in STOPPED state via `add_client()`, it receives `playback_state: 'paused'` instead of the correct `playback_state: 'stopped'`.

## 3. Hardcoded Supported Commands

**Severity:** Medium
**Location:** `aioresonate/server/group.py:1088-1131`, `aioresonate/server/controller.py:46-55`

The specification states that `supported_commands` should be a "subset of" the defined commands (SPEC.md:438), implying these should be based on actual capabilities.

**Issue:** The implementation returns hardcoded command lists based solely on playback state:
- `group.py:1093-1096` always includes `VOLUME`, `MUTE`, and `SWITCH` regardless of actual capabilities
- State-dependent commands (PLAY/PAUSE/STOP, etc.) are added based on playback state alone
- TODO comments at `group.py:1090` and `controller.py:48` indicate this should be dynamic

**Impact:**
- The server reports commands as "supported" even if the underlying music library doesn't support them
- No mechanism for the application to declare which commands are actually supported
- Clients may send commands that cannot be fulfilled

## 4. Switch Command Marked as Untested

**Severity:** Low
**Location:** `aioresonate/server/controller.py:59`

The specification defines the SWITCH command behavior for cycling through groups (SPEC.md:422-431).

**Issue:** The implementation includes a TODO comment: "this is untested, who knows if it works as described in the spec"

**Impact:**
- Implementation correctness is uncertain
- The switch command logic may not properly implement the spec's requirements for cycling through groups

## 5. Controller State Not Sent in All Cases

**Severity:** Low
**Location:** `aioresonate/server/group.py:349-365`

The specification requires `server/state` with controller payload to be sent to clients with the controller role (SPEC.md:264).

**Issue:** The `_send_controller_state_to_clients()` method only sends updates when the volume changes (lines 352-354), using an optimization that checks `self._last_sent_volume`.

**Impact:**
- If only the `muted` state changes (without volume change), and the rounded volume is the same, controller clients may not receive the update
- If `supported_commands` changes (e.g., due to playback state transition), controller clients may not be notified unless volume also changes

## 6. CLI Missing Command Implementations

**Severity:** Low
**Location:** `aioresonate/cli.py:735-846`

The specification defines controller commands including `repeat_off`, `repeat_one`, `repeat_all`, `shuffle`, `unshuffle`, and `switch` (SPEC.md:418).

**Issue:** The CLI's `CommandHandler` does not provide user interface commands for:
- REPEAT_OFF, REPEAT_ONE, REPEAT_ALL
- SHUFFLE, UNSHUFFLE
- SWITCH

**Impact:**
- CLI users cannot exercise these controller commands even though:
  - The models support them
  - The server reports them as supported (in PLAYING/PAUSED states)
  - The client library can send them via `send_group_command()`

## Summary

The controller role implementation has the following critical gaps:

1. **PAUSED state is defined but never used** - most significant issue
2. **Playback state logic is incorrect for STOPPED state**
3. **Supported commands are hardcoded instead of capability-based**
4. **Switch command is untested**
5. **Controller state updates may be missed when only mute or supported_commands change**
6. **CLI doesn't expose all specified controller commands**
