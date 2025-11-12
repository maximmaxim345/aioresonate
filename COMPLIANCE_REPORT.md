# SPEC.md Compliance Report

## Scope
This report focuses on inconsistencies between SPEC.md and the implementation for:
- mDNS service discovery and advertisement
- Connection establishment (both server-initiated and client-initiated)

## mDNS and Connection Establishment

### Missing: Client Implementation for Server-Initiated Connections

**Location:** N/A (missing implementation)

**Issue:** The specification requires that "Resonate Servers must support both methods" (SPEC.md:23) for connection establishment. While the server correctly implements discovery of clients via `_resonate._tcp.local.` (aioresonate/server/server.py:426), there is no client implementation that advertises this service.

**Details:**
- The server has code to discover clients using `_resonate._tcp.local.` mDNS service type (aioresonate/server/server.py:422-432)
- The CLI client (aioresonate/cli.py) only supports client-initiated connections by discovering `_resonate-server._tcp.local.`
- No client code exists to advertise `_resonate._tcp.local.` service
- The ResonateClient class (aioresonate/client/client.py) has no mDNS advertising capabilities

**Spec Reference:**
```
### Server Initiated Connections

Clients announce their presence via mDNS using:
- Service type: `_resonate._tcp.local.`
- Port: The port the Resonate client is listening on (recommended: `8927`)
- TXT record: `path` key specifying the WebSocket endpoint (recommended: `/resonate`)

The server discovers available clients through mDNS and connects to each client via WebSocket
using the advertised address and path.
```
(SPEC.md:25-32)

**Impact:** Server-initiated connection method is non-functional. Servers can discover clients, but no clients exist that advertise themselves for server-initiated connections.

---

### Inconsistency: Default Client ID Format Uses Hostname

**Location:** aioresonate/cli.py:598

**Issue:** The CLI generates a default client_id using `f"resonate-cli-{hostname}"` format. The spec states that `client_id` should "uniquely identifies the client for groups and de-duplication" (SPEC.md:64, 200) but provides no guidance on format or uniqueness guarantees.

**Details:**
- Multiple CLI instances on different machines with the same hostname would generate identical client IDs
- Hostname may not be unique across a network (e.g., multiple VMs, containers, or devices with default hostnames like "localhost")
- The spec requires client_id to be unique but doesn't specify how to ensure uniqueness

**Code:**
```python
client_id = args.id if args.id is not None else f"resonate-cli-{hostname}"
```
(aioresonate/cli.py:598)

**Spec Reference:**
```
- `client_id`: string - uniquely identifies the client for groups and de-duplication
```
(SPEC.md:64, 200)

**Impact:** Potential client ID collisions when multiple CLI instances run with the same hostname, leading to de-duplication issues or group management conflicts.

**Note:** While the spec requires uniqueness, it doesn't mandate any specific format or generation method. The current implementation satisfies the spec's letter but not necessarily its spirit regarding uniqueness guarantees.
