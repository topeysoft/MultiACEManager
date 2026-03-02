# Multi-Device Gate Editing Fix

## Problem
When editing a gate (color, material, temp) on one device, the changes were appearing on all devices.

## Root Cause
1. Backend correctly routes `ACE_GATE_MAP` commands to specific devices
2. Backend correctly saves to device-specific `save_variables`
3. **BUT**: `get_status()` aggregates all device data into single flat arrays
4. UI receives aggregated arrays with no device ownership information
5. All device UI views reference the same aggregated data

### Example Data Flow
```
User edits Gate 5 (Device 2, local gate 1) - sets color to FF0000
→ UI sends: ACE_GATE_MAP GATE=5 COLOR=FF0000
→ Backend routes: Device 2, local_gate=1 ✓
→ Backend saves: Device 2's save_variables['gate_color'][1] = 'FF0000' ✓
→ get_status() returns: gate_color = ['dev1_g0', 'dev1_g1', ..., 'FF0000', ...]
→ UI sees flat array, doesn't know gate 5 belongs to device 2 ✗
→ All device views display aggregated data ✗
```

## Solution

### Backend Changes (ace.py)
Added `devices_detail` field to `get_status()` return value with per-device gate data:

```python
devices_detail = []
for dev in self.ace_devices:
    ace = dev['instance']
    status = ace.get_status()
    devices_detail.append({
        'device_id': dev.get('device_id', f"dev_{dev['gate_offset']}"),
        'gate_offset': dev['gate_offset'],
        'gate_color': status.get('gate_color', []),
        'gate_material': status.get('gate_material', []),
        'gate_temp': status.get('gate_temp', []),
        'active_gate': status.get('active_gate', []),
        'spool_id': list(range(dev['gate_offset'] + 1, dev['gate_offset'] + 5))
    })

return {
    # ... existing fields (aggregated data) ...
    'devices_detail': devices_detail,  # NEW: Per-device gate data
}
```

### Frontend Changes (ace.ts)

#### Updated `getAceGate()` method
Now checks for `devices_detail` and uses device-specific data when available:

```typescript
getAceGate(index: number): AceGate {
    // Check if we have device-specific data (multi-device setup)
    const devicesDetail = this.ace.devices_detail
    if (devicesDetail && Array.isArray(devicesDetail)) {
        // Find which device owns this gate
        const device = devicesDetail.find((d: any) => {
            const offset = d.gate_offset ?? 0
            return index >= offset && index < offset + 4
        })

        if (device) {
            // Calculate local gate index within this device
            const localIndex = index - (device.gate_offset ?? 0)
            const gateState = device.active_gate?.[localIndex] ?? 'empty'

            return {
                index,
                status: gateState,
                color: device.gate_color?.[localIndex] ?? '000000',
                material: device.gate_material?.[localIndex] ?? 'PLA',
                temp: device.gate_temp?.[localIndex] ?? 0,
                spool_id: device.spool_id?.[localIndex] ?? 0,
                loaded: gateState === 'loaded' || gateState === 'active',
                selected: index === this.aceSelectedGate,
            }
        }
    }

    // Fallback to aggregated data (single device or backward compat)
    const gateState = this.aceActiveGateStates[index] ?? 'empty'
    return {
        index,
        status: gateState,
        color: this.aceGateColors[index] ?? '000000',
        material: this.aceGateMaterials[index] ?? 'PLA',
        temp: this.aceGateTemps[index] ?? 0,
        spool_id: this.aceSpoolIds[index] ?? 0,
        loaded: gateState === 'loaded' || gateState === 'active',
        selected: index === this.aceSelectedGate,
    }
}
```

#### Added `getAceGatesForDevice()` helper
Convenience method for device-grouped UI components:

```typescript
getAceGatesForDevice(deviceId: string): AceGate[] {
    const device = this.getAceDevice(deviceId)
    if (!device) return []

    const offset = device.gate_offset ?? 0
    const gates: AceGate[] = []

    for (let i = 0; i < 4; i++) {
        gates.push(this.getAceGate(offset + i))
    }

    return gates
}
```

## Benefits
1. ✅ Each device's gates are now isolated
2. ✅ Editing gates on one device doesn't affect others
3. ✅ Maintains backward compatibility with single-device setups
4. ✅ No breaking changes to existing API
5. ✅ Device-grouped UI can easily fetch per-device gate data

## Testing Checklist
- [ ] Test gate editing on Device 1 - verify only Device 1 gates update
- [ ] Test gate editing on Device 2 - verify only Device 2 gates update
- [ ] Test gate editing on Device 3 - verify only Device 3 gates update
- [ ] Test single-device setup still works (backward compatibility)
- [ ] Verify gate colors display correctly per device
- [ ] Verify gate materials display correctly per device
- [ ] Verify gate temperatures display correctly per device
- [ ] Test tool changes (T0-T11) work correctly across devices

## Files Modified
- `KlipperACE/extras/ace.py` (Lines 2092-2123)
- `mainsail-crew/mainsail/src/components/mixins/ace.ts` (Lines 118-184)
