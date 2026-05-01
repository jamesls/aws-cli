# Copyright 2026 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
import json
import math
import os
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from awscli.customizations.exceptions import ParamValidationError


TRACE_ENV_VAR = 'AWS_CLI_S3_TRACE'
TRACE_VERSION = 1
NORMAL_MODE = 'normal'
SUPPORTED_MODES = [NORMAL_MODE]
DEFAULT_TRACE_BUFFER_SIZE = 100
_CURRENT_S3_TRANSFER_TRACER = ContextVar(
    'awscli_s3_transfer_tracer', default=None
)

# (stderr label, summary field) rows rendered by _write_summary_to_stderr.
_STDERR_METRIC_ROWS = [
    ('avg request latency', 'avg_request_latency_ns'),
    ('p95 request latency', 'p95_request_latency_ns'),
    ('avg parse overhead', 'avg_parse_overhead_ns'),
    ('p95 parse overhead', 'p95_parse_overhead_ns'),
    ('avg page drain', 'avg_page_drain_ns'),
    ('p95 page drain', 'p95_page_drain_ns'),
    ('avg inter-request gap', 'avg_inter_request_gap_ns'),
    ('p95 inter-request gap', 'p95_inter_request_gap_ns'),
]


class S3TraceConfig:
    def __init__(self, mode, output_path=None):
        self.mode = mode
        self.output_path = output_path


def parse_s3_trace_config(env=None):
    if env is None:
        env = os.environ
    raw_value = env.get(TRACE_ENV_VAR)
    if raw_value is None:
        return None
    return _parse_trace_value(raw_value)


def create_s3_transfer_tracer(
    trace_config,
    command_name,
    parameters,
    source_client,
    transfer_client=None,
    clients=None,
    output_file=None,
    stderr=None,
    time_fn=None,
    thread_id_fn=None,
):
    if trace_config is None:
        return None

    resolved_output_path = trace_config.output_path
    opened_output_file = output_file
    should_close_output_file = False
    if opened_output_file is None:
        if resolved_output_path is None:
            file_descriptor, resolved_output_path = tempfile.mkstemp(
                prefix='aws-s3-trace-', suffix='.jsonl'
            )
            opened_output_file = os.fdopen(file_descriptor, 'w')
        else:
            opened_output_file = open(resolved_output_path, 'w')
        should_close_output_file = True

    return S3TransferTracer(
        trace_config=trace_config,
        command_name=command_name,
        parameters=parameters,
        source_client=source_client,
        transfer_client=transfer_client,
        clients=clients,
        output_file=opened_output_file,
        output_path=resolved_output_path,
        should_close_output_file=should_close_output_file,
        stderr=stderr,
        time_fn=time_fn,
        thread_id_fn=thread_id_fn,
    )


def get_current_s3_transfer_tracer():
    return _CURRENT_S3_TRANSFER_TRACER.get()


@contextmanager
def scoped_s3_transfer_tracer(tracer):
    if tracer is None:
        yield None
        return

    token = _CURRENT_S3_TRANSFER_TRACER.set(tracer)
    try:
        yield tracer
    finally:
        _CURRENT_S3_TRANSFER_TRACER.reset(token)


class S3TransferTracer:
    def __init__(
        self,
        trace_config,
        command_name,
        parameters,
        source_client,
        output_file,
        output_path,
        should_close_output_file=False,
        stderr=None,
        time_fn=None,
        thread_id_fn=None,
        transfer_client=None,
        clients=None,
    ):
        self._trace_config = trace_config
        self._output_file = output_file
        self._output_path = output_path
        self._should_close_output_file = should_close_output_file
        self._stderr = stderr
        self._time_fn = time_fn or time.monotonic_ns
        self._thread_id_fn = thread_id_fn or threading.get_ident
        self._trace_buffer_size = DEFAULT_TRACE_BUFFER_SIZE
        self._trace_buffer = []

        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._thread_local = threading.local()
        self._closed = False
        self._command_id = uuid.uuid4().hex
        self._command_start_ns = self._time_fn()

        bucket, prefix = _extract_bucket_and_prefix(parameters)
        self._common_fields = {
            'bucket': bucket,
            'command_id': self._command_id,
            'mode': self._trace_config.mode,
            'operation': command_name,
            'prefix': prefix,
            'trace_version': TRACE_VERSION,
        }

        self._next_request_seq = 0
        self._next_page_index = 0
        self._requests = {}
        self._pages = {}
        self._registered_event_handlers = []
        if clients is None:
            clients = [source_client, transfer_client]
        self._register_clients(clients)

    @property
    def mode(self):
        return self._trace_config.mode

    @property
    def output_path(self):
        return self._output_path

    def current_thread_request_seq(self):
        """Return the request_seq most recently started on this thread."""
        return getattr(self._thread_local, 'current_request_seq', None)

    def record_page_available(
        self,
        object_count,
        is_truncated,
        next_continuation_token_present,
        request_seq=None,
    ):
        if request_seq is None:
            request_seq = self.current_thread_request_seq()
        with self._state_lock:
            self._next_page_index += 1
            page_index = self._next_page_index
        event = self._emit_event(
            'page_available',
            object_count=object_count,
            is_truncated=is_truncated,
            next_continuation_token_present=next_continuation_token_present,
            page_index=page_index,
            request_seq=request_seq,
        )
        with self._state_lock:
            self._pages[page_index] = {
                'object_count': object_count,
                'page_available': event['ts_ns'],
                'request_seq': request_seq,
            }
        return page_index

    def record_page_first_object_yielded(self, page_index):
        self._record_page_iteration_event(
            'page_first_object_yielded', page_index
        )

    def record_page_last_object_resumed(self, page_index):
        self._record_page_iteration_event(
            'page_last_object_resumed', page_index
        )

    def _record_page_iteration_event(self, event_name, page_index):
        event = self._emit_event(
            event_name,
            page_index=page_index,
            request_seq=self._get_page_request_seq(page_index),
        )
        with self._state_lock:
            page_record = self._pages.setdefault(page_index, {})
            page_record[event_name] = event['ts_ns']

    def build_summary(self):
        total_time_ns = self._time_fn() - self._command_start_ns

        series = {
            'request_latency': [],
            'parse_overhead': [],
            'page_drain': [],
            'first_yield_delay': [],
            'inter_request_gap': [],
            'post_drain_gap': [],
        }

        for seq in sorted(self._requests):
            record = self._requests[seq]
            start = record.get('list_request_start')
            body_ready = record.get('list_body_ready')
            parse_done = record.get('list_parse_done')
            if start is not None and body_ready is not None:
                series['request_latency'].append(body_ready - start)
            if body_ready is not None and parse_done is not None:
                series['parse_overhead'].append(parse_done - body_ready)

        for page_index in sorted(self._pages):
            record = self._pages[page_index]
            available = record.get('page_available')
            first_yield = record.get('page_first_object_yielded')
            last_resumed = record.get('page_last_object_resumed')
            if available is not None and first_yield is not None:
                series['first_yield_delay'].append(first_yield - available)
            if available is not None and last_resumed is not None:
                series['page_drain'].append(last_resumed - available)

            request_seq = record.get('request_seq')
            if request_seq is None:
                continue
            current_request = self._requests.get(request_seq)
            next_request = self._requests.get(request_seq + 1)
            if current_request is None or next_request is None:
                continue
            body_ready = current_request.get('list_body_ready')
            next_start = next_request.get('list_request_start')
            if next_start is None or body_ready is None:
                continue
            series['inter_request_gap'].append(next_start - body_ready)
            if last_resumed is not None:
                series['post_drain_gap'].append(next_start - last_resumed)

        summary = {
            'list_requests': len(self._requests),
            'objects': sum(
                page.get('object_count', 0) for page in self._pages.values()
            ),
            'pages': len(self._pages),
            'total_time_ns': total_time_ns,
        }
        for name, values in series.items():
            summary['avg_%s_ns' % name] = _average(values)
            summary['p95_%s_ns' % name] = _p95(values)
        return summary

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            summary = self.build_summary()
            self._emit_event('command_summary', **summary)
            self._flush_trace_buffer()
            self._write_summary_to_stderr(summary)
        finally:
            self._unregister_event_handlers()
            if self._should_close_output_file:
                self._output_file.close()

    def _get_page_request_seq(self, page_index):
        with self._state_lock:
            return self._pages.get(page_index, {}).get('request_seq')

    def _register_clients(self, clients):
        seen_emitters = set()
        handlers = [
            (
                'before-call.s3.ListObjectsV2',
                self._on_before_call_list_objects_v2,
                'awscli-s3trace-before-call-%s' % self._command_id,
            ),
            (
                'before-parse.s3.ListObjectsV2',
                self._on_before_parse_list_objects_v2,
                'awscli-s3trace-before-parse-%s' % self._command_id,
            ),
            (
                'after-call.s3.ListObjectsV2',
                self._on_after_call_list_objects_v2,
                'awscli-s3trace-after-call-%s' % self._command_id,
            ),
        ]
        for client in clients:
            if client is None:
                continue
            emitter = client.meta.events
            emitter_id = id(emitter)
            if emitter_id in seen_emitters:
                continue
            seen_emitters.add(emitter_id)
            for event_name, handler, unique_id in handlers:
                emitter.register(event_name, handler, unique_id=unique_id)
                self._registered_event_handlers.append(
                    (emitter, event_name, handler, unique_id)
                )

    def _unregister_event_handlers(self):
        for emitter, event_name, handler, unique_id in (
            self._registered_event_handlers
        ):
            emitter.unregister(event_name, handler, unique_id=unique_id)

    def _on_before_call_list_objects_v2(self, params, **kwargs):
        del kwargs
        with self._state_lock:
            self._next_request_seq += 1
            request_seq = self._next_request_seq
        self._thread_local.current_request_seq = request_seq
        query_string = params.get('query_string') or {}
        event = self._emit_event(
            'list_request_start',
            continuation_token_present=(
                query_string.get('continuation-token') is not None
            ),
            max_keys=query_string.get('max-keys'),
            request_seq=request_seq,
        )
        with self._state_lock:
            self._requests[request_seq] = {
                'list_request_start': event['ts_ns'],
            }

    def _on_before_parse_list_objects_v2(self, **kwargs):
        del kwargs
        request_seq = self.current_thread_request_seq()
        event = self._emit_event('list_body_ready', request_seq=request_seq)
        if request_seq is not None:
            with self._state_lock:
                record = self._requests.setdefault(request_seq, {})
                record['list_body_ready'] = event['ts_ns']

    def _on_after_call_list_objects_v2(self, **kwargs):
        del kwargs
        request_seq = self.current_thread_request_seq()
        event = self._emit_event('list_parse_done', request_seq=request_seq)
        if request_seq is not None:
            with self._state_lock:
                record = self._requests.setdefault(request_seq, {})
                record['list_parse_done'] = event['ts_ns']

    def _emit_event(self, event_name, **fields):
        event = {
            'event': event_name,
            'thread_id': self._thread_id_fn(),
            'ts_ns': self._time_fn(),
        }
        event.update(self._common_fields)
        event.update(fields)
        payload = json.dumps(event) + '\n'
        with self._lock:
            self._trace_buffer.append(payload)
            if len(self._trace_buffer) >= self._trace_buffer_size:
                self._flush_trace_buffer_locked()
        return event

    def _flush_trace_buffer(self):
        with self._lock:
            self._flush_trace_buffer_locked()

    def _flush_trace_buffer_locked(self):
        if not self._trace_buffer:
            return
        self._output_file.write(''.join(self._trace_buffer))
        self._output_file.flush()
        self._trace_buffer = []

    def _write_summary_to_stderr(self, summary):
        stderr = self._stderr if self._stderr is not None else sys.stderr
        lines = [
            'S3 trace summary',
            'mode: %s' % self.mode,
            'trace file: %s' % self._output_path,
            'pages: %s' % summary['pages'],
            'objects: %s' % summary['objects'],
            'list requests: %s' % summary['list_requests'],
            'total time: %s' % _format_duration(summary['total_time_ns']),
        ]
        for label, field in _STDERR_METRIC_ROWS:
            lines.append(
                '%s: %s' % (label, _format_duration(summary[field]))
            )
        stderr.write('\n'.join(lines))
        stderr.write('\n')
        stderr.flush()


def _extract_bucket_and_prefix(parameters):
    for key in ('src', 'dest'):
        path = parameters.get(key)
        if path is None or not path.startswith('s3://'):
            continue
        bucket, _, prefix = path[5:].partition('/')
        return bucket, prefix
    return None, None


def _average(values):
    if not values:
        return None
    return float(sum(values)) / len(values)


def _p95(values):
    if not values:
        return None
    sorted_values = sorted(values)
    index = int(math.ceil(len(sorted_values) * 0.95)) - 1
    return sorted_values[index]


def _format_duration(duration_ns):
    if duration_ns is None:
        return 'n/a'
    duration_ms = float(duration_ns) / 1000000
    if duration_ms >= 1000:
        return '%.2fs' % (duration_ms / 1000)
    return '%.1fms' % duration_ms


def _parse_trace_value(raw_value):
    if raw_value == '':
        raise _create_invalid_value_error(raw_value)

    output_path = None
    mode = None
    seen_keys = set()
    for index, raw_token in enumerate(raw_value.split(',')):
        token = raw_token.strip()
        if token == '':
            raise _create_invalid_value_error(raw_value)
        if index == 0:
            if '=' in token:
                raise _create_invalid_value_error(raw_value)
            mode = token
            continue

        if '=' not in token:
            raise _create_invalid_value_error(raw_value)
        key, value = token.split('=', 1)
        if key == '' or value == '' or key in seen_keys:
            raise _create_invalid_value_error(raw_value)
        seen_keys.add(key)
        if key != 'out':
            raise _create_invalid_value_error(raw_value)
        output_path = value

    if mode not in SUPPORTED_MODES:
        raise _create_invalid_value_error(raw_value)
    return S3TraceConfig(mode=mode, output_path=output_path)


def _create_invalid_value_error(raw_value):
    return ParamValidationError(
        'Invalid %s value: %r\n'
        'Expected: <mode>[,out=<path>]\n'
        'Supported modes: %s'
        % (TRACE_ENV_VAR, raw_value, ', '.join(SUPPORTED_MODES))
    )
