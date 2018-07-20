import dateutil
from collections import namedtuple
RawRecord = namedtuple('RawRecord', ['timestamp', 'thread', 'message'])


def parse_log_line(line):
    parts = line.split(' - ')
    date = parts[0]
    thread = parts[1]
    message = parts[-1]
    if not message.startswith('QUEUE'):
        return
    parsed_date = float(dateutil.parser.parse(date).strftime('%s'))
    return RawRecord(parsed_date, thread, message)


def extract_queue_msg_from_log_lines(lines):
    messages = []
    for line in lines:
        parsed = parse_log_line(line)
        if parsed is not None:
            messages.apend(parsed)
    return messages


def scale_timestamps(messages, max_scale):
    min_val = min(messages, key=lambda x: x.timestamp).timestamp
    max_val = max(messages, key=lambda x: x.timestamp).timestamp
    val_range = float(max_val - min_val)
    return [
        RawRecord(timestamp=(r.timestamp - min_val) / val_range * max_scale,
                  thread=r.thread,
                  message=r.message) for r in messages
    ]


def group_messages_by_thread(messages):
    groups = {}
    for message in messages:
        groups.setdefault(message.thread, []).append(message)
    return groups
