from datetime import datetime, timedelta

# Whitespace-delimited (tabs or aligned spaces) — a direct timestamp column
# must be one token with no internal space.
DEFAULT_COLUMNS = {"doy": "DOY", "time_sec": "TimeSec", "channel": "Channel", "timestamp": None}
DEFAULT_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"


def doy_to_timestamp(year, doy, time_sec):
    return datetime(year, 1, 1) + timedelta(days=int(doy) - 1, seconds=int(time_sec))


def _row_timestamp(row, year, columns, timestamp_format):
    ts_col = columns.get("timestamp")
    if ts_col:
        return datetime.strptime(row[ts_col], timestamp_format)
    return doy_to_timestamp(year, row[columns["doy"]], row[columns["time_sec"]])


def _row_sensor(row, channel_col):
    return str(int(row[channel_col])) if channel_col else ""


def parse_raw_pam(path, year, columns=DEFAULT_COLUMNS, timestamp_format=DEFAULT_TIMESTAMP_FORMAT):
    """Reads a raw logger file and returns (header, rows). Every raw column
    is passed through unfiltered except the channel/timestamp source
    columns, which are replaced by the renamed "sensor" / computed
    "timestamp" columns. Malformed rows are skipped, not raised."""
    with open(path, encoding="utf-8-sig") as f:
        lines = [line for line in f if line.strip()]
    if not lines:
        return ["timestamp", "sensor"], []

    raw_header = lines[0].split()
    channel_col = columns.get("channel")
    ts_col = columns.get("timestamp")
    passthrough_cols = [h for h in raw_header if h not in (channel_col, ts_col)]
    header = ["timestamp", "sensor", *passthrough_cols]

    rows = []
    for line in lines[1:]:
        values = line.split()
        if len(values) != len(raw_header):
            continue
        row = dict(zip(raw_header, values))
        try:
            sensor_value = _row_sensor(row, channel_col)
            timestamp = _row_timestamp(row, year, columns, timestamp_format)
        except (KeyError, ValueError):
            continue

        out = {"timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"), "sensor": sensor_value}
        out.update({col: row.get(col, "") for col in passthrough_cols})
        rows.append(out)
    return header, rows
