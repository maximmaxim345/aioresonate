# SPEC.md Compliance Analysis - Model Comments

## Inconsistencies Found

### player.py:88 - PlayerCommandPayload.command

**Location:** `aioresonate/models/player.py:88`

**Comment in code:**
```python
command: PlayerCommand
"""Command - must be 'volume' or 'mute'."""
```

**SPEC.md states (line 370):**
> `command`: 'volume' | 'mute' - must be one of the values listed in `supported_commands` in the [`player_support`](#client--server-clienthello-player-support-object) object in the [`client/hello`](#client--server-clienthello) message

**Issue:**
The comment states that the command "must be 'volume' or 'mute'" without mentioning the requirement that it must be one of the values from the client's `supported_commands` list. This omission could lead to misunderstanding about server behavior - the server should only send commands that the client declared support for in its `client/hello` message. While technically accurate about the possible values, the comment omits the critical constraint about checking against the client's declared capabilities.

**Recommendation:**
Update the comment to: "Command - must be one of the values listed in supported_commands ('volume' or 'mute')."

---

### metadata.py:34 - SessionUpdateMetadata.track_progress

**Location:** `aioresonate/models/metadata.py:34`

**Comment in code:**
```python
track_progress: int | None | UndefinedField = field(default_factory=undefined_field)
"""Track progress in milliseconds."""
```

**SPEC.md states (line 461):**
> `track_progress?`: integer | null - current playback position in milliseconds (since start of track, at the given `timestamp`)

**Issue:**
The comment defines track_progress as "Track progress in milliseconds" but omits the important clarification that this is measured "since start of track, at the given timestamp". The timestamp reference is crucial for understanding how to calculate current position, as documented in the SPEC at line 450: "Clients can calculate the current track position at any time using the last received values: `current_track_progress_ms = max(min(metadata.track_progress + (current_time - metadata.timestamp) * metadata.playback_speed / 1000000, metadata.track_duration), 0)`"

**Recommendation:**
Update the comment to: "Track progress in milliseconds (since start of track, at the given timestamp)."

---

### player.py:70 - PlayerStatePayload.state

**Location:** `aioresonate/models/player.py:70`

**Comment in code:**
```python
state: PlayerStateType
"""State of the player - synchronized or error."""
```

**SPEC.md states (line 345):**
> `state`: 'synchronized' | 'error' - state of the player, should always be `synchronized` unless there is an error preventing current or future playback (unable to keep up, issues keeping the clock in sync, etc)

**Issue:**
The comment simply states "State of the player - synchronized or error" without explaining when each state should be used. The SPEC provides important guidance that the state "should always be synchronized unless there is an error preventing current or future playback". This context is important for implementers to understand when to set the error state.

**Recommendation:**
Update the comment to: "State of the player - should always be 'synchronized' unless there is an error preventing current or future playback."
