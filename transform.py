from datetime import datetime, timedelta

# Raw PAM logger output is whitespace-delimited (tabs, or space-aligned
# columns depending on the exporting software) — no field ever contains
# internal whitespace, so a plain str.split() is a delimiter-agnostic parser
# that works either way. This means a direct-timestamp column (see
# _row_timestamp below) must itself be one whitespace-free token.

# Default raw column names for the fields the parser needs structurally:
# channel/probe id, plus either (doy, time_sec) or a direct timestamp
# column. Overridable via config.yaml's pam.columns if the logger software
# ever renames them, or uses a timestamp column instead of DOY+TimeSec —
# nothing here needs to change for that.
DEFAULT_COLUMNS = {"doy": "DOY", "time_sec": "TimeSec", "channel": "Channel", "timestamp": None}
DEFAULT_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"


def doy_to_timestamp(year, doy, time_sec):
    return datetime(year, 1, 1) + timedelta(days=int(doy) - 1, seconds=int(time_sec))


def output_header(variables):
    # "sensor" (not "channel") matches CHANNEL_COLUMN in
    # dashboard/backend/sensor_ingest.py and server/db_writer.py — the
    # ingest pipeline groups multi-channel sensors (e.g. AS7341) into one
    # sensor_type using this exact column name.
    return ["timestamp", "sensor", *variables]


def _row_timestamp(row, year, columns, timestamp_format):
    """A row's timestamp comes from either a single pre-formatted column
    (columns["timestamp"] set) or a DOY+TimeSec pair — whichever the config
    points at. Raises KeyError/ValueError on a malformed row; the caller
    treats that as "skip this row", not a hard failure."""
    ts_col = columns.get("timestamp")
    if ts_col:
        return datetime.strptime(row[ts_col], timestamp_format)
    return doy_to_timestamp(year, row[columns["doy"]], row[columns["time_sec"]])


def parse_raw_pam(path, channels, year, variables, columns=DEFAULT_COLUMNS, timestamp_format=DEFAULT_TIMESTAMP_FORMAT):
    """Reads a raw PAM logger file and returns dict rows restricted to
    `channels`, with only `variables` plus a computed timestamp and a
    renamed "sensor" column. Rows that don't parse cleanly (mid-write
    truncation, unexpected channel values) are skipped rather than raising,
    since this runs against a file the logger may still be appending to.

    variables: which raw columns to keep in the output — this list *is*
    what ends up selectable on the dashboard, so a deployment with a
    different variable set only needs a config change, not a code change.
    columns: maps the structural fields above to their actual column names
    in the raw file, for loggers that name them differently or that log a
    single timestamp column instead of DOY+TimeSec (see _row_timestamp).
    year: only consulted in DOY+TimeSec mode — ignored when columns
    ["timestamp"] is set, since that column is already a full date.
    """
    with open(path, encoding="utf-8-sig") as f:
        lines = [line for line in f if line.strip()]
    if not lines:
        return []

    header = lines[0].split()
    channel_col = columns["channel"]

    rows = []
    for line in lines[1:]:
        values = line.split()
        if len(values) != len(header):
            continue
        row = dict(zip(header, values))
        try:
            channel = int(row[channel_col])
        except (KeyError, ValueError):
            continue
        if channel not in channels:
            continue
        try:
            timestamp = _row_timestamp(row, year, columns, timestamp_format)
        except (KeyError, ValueError):
            continue

        out = {"timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"), "sensor": str(channel)}
        out.update({var: row.get(var, "") for var in variables})
        rows.append(out)
    return rows
