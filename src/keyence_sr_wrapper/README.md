# keyence_sr_wrapper

ROS 2 driver for the Keyence SR-1000 barcode scanner over TCP (LON/LOFF
protocol).

## Node: `keyence_sr_node`

- **Service** `trigger_scan` (`std_srvs/Trigger`) — sends `LON`, waits for
  the CR-terminated response.
- **Parameters**: `scanner_ip`, `scanner_port`, `response_timeout_s`
  (default 30; the read path honors it dynamically, the connect handshake
  uses 3 s).
- **Topic**: publishes decoded barcodes to `<ns>/scanner/barcode`.
- **Diagnostics**: `keyence_sr_node: Scanner Connection` — reports OK only
  when the TCP stream is alive (peer-close detection via `MSG_PEEK`).

## Reconnection

A monotonic backoff timer reconnects after errors; the scan service and the
diagnostic timer share one mutually exclusive callback group.

## Testing

`pytest test/` — includes fake-TCP-server regressions for slow responses
(>3 s) and half-open connections.
