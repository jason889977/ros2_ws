# Aggregated health and counters for one camera pipeline
std_msgs/Header header
string camera_id
uint8 OK=0
uint8 WARN=1
uint8 ERROR=2
uint8 STALE=3
uint8 overall_level
string summary
uint32 active_components
uint32 warning_components
uint32 error_components
string[] component_names
string[] component_messages
string[] metric_names
string[] metric_values

# Production metrics
uint32 scan_count_total
uint32 keyence_scan_count
float64 scan_rate_per_minute
builtin_interfaces/Time last_scan_timestamp
float64 miss_scan_duration_s
