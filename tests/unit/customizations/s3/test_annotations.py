from nose.tools import assert_equal
from awscli.annotations import parse_log_line
from awscli.annotations import extract_queue_msg_from_log_lines
from awscli.annotations import scale_timestamps
from awscli.annotations import group_messages_by_thread
from awscli.annotations import RawRecord


def time_record(timestamp):
    return RawRecord(timestamp, 'thread-1', 'foo')


def test_convert_line_to_record():
    message = (
        '2013-09-10 16:00:08,940 - Thread-7 - '
        'awscli.customizations.s3.executer - DEBUG - QUEUE-GET'
    )
    assert_equal(parse_log_line(message), RawRecord(
        timestamp=1378854008.0,
        thread='Thread-7',
        message='QUEUE-GET',
    ))


def test_returns_none_when_not_queue_msg():
    message = (
        '2013-09-10 16:00:08,940 - Thread-7 - '
        'awscli.customizations.s3.executer - DEBUG - Something else'
    )
    assert_equal(parse_log_line(message), None)


def test_can_normalize_timestamps():
    messages = [
        time_record(50),
        time_record(60),
        time_record(75),
        time_record(80),
    ]
    new_messages = scale_timestamps(messages, max_scale=100)
    assert_equal(new_messages, [
        time_record(0),
        time_record((10 / 30.0) * 100),
        time_record((25 / 30.0) * 100),
        time_record(100),
    ])


def test_can_group_records_by_thread():
    messages = [
        RawRecord(0, 'thread-1', 'foo'),
        RawRecord(0, 'thread-2', 'foo'),
        RawRecord(0, 'thread-1', 'foo'),
        RawRecord(0, 'thread-1', 'foo'),
        RawRecord(0, 'thread-3', 'foo'),
    ]
    grouped = group_messages_by_thread(messages)
    assert_equal(grouped, {
        'thread-1': [RawRecord(0, 'thread-1', 'foo'),
                     RawRecord(0, 'thread-1', 'foo'),
                     RawRecord(0, 'thread-1', 'foo')],
        'thread-2': [RawRecord(0, 'thread-2', 'foo')],
        'thread-3': [RawRecord(0, 'thread-3', 'foo')]
    })
