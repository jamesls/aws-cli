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
import threading
from io import StringIO

from botocore.hooks import HierarchicalEmitter

from awscli.customizations.exceptions import ParamValidationError
from awscli.customizations.s3.tracer import (
    S3TransferTracer,
    get_current_s3_transfer_tracer,
    parse_s3_trace_config,
    scoped_s3_transfer_tracer,
)
from awscli.customizations.s3.bucketlister import (
    BucketLister,
    ThreadedBucketLister,
)
from awscli.testutils import mock, unittest


class TestParseS3TraceConfig(unittest.TestCase):
    def test_parses_trace_env_var(self):
        config = parse_s3_trace_config(
            {'AWS_CLI_S3_TRACE': 'normal,out=/tmp/trace.jsonl'}
        )
        self.assertEqual(config.mode, 'normal')
        self.assertEqual(config.output_path, '/tmp/trace.jsonl')

    def test_rejects_removed_trace_modes(self):
        with self.assertRaises(ParamValidationError):
            parse_s3_trace_config({'AWS_CLI_S3_TRACE': 'noop_handoff'})

    def test_rejects_invalid_value(self):
        with self.assertRaises(ParamValidationError):
            parse_s3_trace_config({'AWS_CLI_S3_TRACE': 'out=/tmp/x.jsonl'})


class TestS3TransferTracer(unittest.TestCase):
    def setUp(self):
        self.output_file = StringIO()
        self.stderr = StringIO()
        self.source_client = mock.Mock()
        self.source_client.meta.events = mock.Mock()
        self.transfer_client = mock.Mock()
        self.transfer_client.meta.events = mock.Mock()

    def test_records_summary_metrics(self):
        ms = 1000000
        time_values = iter(
            [
                0 * ms,
                10 * ms,
                40 * ms,
                50 * ms,
                60 * ms,
                65 * ms,
                100 * ms,
                120 * ms,
                150 * ms,
                160 * ms,
                170 * ms,
                175 * ms,
                200 * ms,
                210 * ms,
                220 * ms,
            ]
        )
        trace_config = parse_s3_trace_config(
            {'AWS_CLI_S3_TRACE': 'normal,out=/tmp/trace.jsonl'}
        )
        tracer = S3TransferTracer(
            trace_config=trace_config,
            command_name='cp',
            parameters={'src': 's3://bucket/prefix/'},
            source_client=self.source_client,
            output_file=self.output_file,
            output_path='/tmp/trace.jsonl',
            stderr=self.stderr,
            time_fn=lambda: next(time_values),
        )

        tracer._on_before_call_list_objects_v2(
            model=None,
            params={'query_string': {'max-keys': '1000'}},
            request_signer=None,
            context={},
        )
        tracer._on_before_parse_list_objects_v2(
            operation_model=None,
            response_dict={},
            customized_response_dict={},
        )
        tracer._on_after_call_list_objects_v2(
            http_response=None,
            parsed={},
            model=None,
            context={},
        )
        page_one = tracer.record_page_available(
            object_count=2,
            is_truncated=True,
            next_continuation_token_present=True,
        )
        tracer.record_page_first_object_yielded(page_one)
        tracer.record_page_last_object_resumed(page_one)

        tracer._on_before_call_list_objects_v2(
            model=None,
            params={
                'query_string': {
                    'continuation-token': 'token',
                    'max-keys': '1000',
                }
            },
            request_signer=None,
            context={},
        )
        tracer._on_before_parse_list_objects_v2(
            operation_model=None,
            response_dict={},
            customized_response_dict={},
        )
        tracer._on_after_call_list_objects_v2(
            http_response=None,
            parsed={},
            model=None,
            context={},
        )
        page_two = tracer.record_page_available(
            object_count=1,
            is_truncated=False,
            next_continuation_token_present=False,
        )
        tracer.record_page_first_object_yielded(page_two)
        tracer.record_page_last_object_resumed(page_two)
        tracer.close()

        output_lines = [
            line for line in self.output_file.getvalue().splitlines() if line
        ]
        self.assertIn('command_summary', output_lines[-1])
        summary_output = self.stderr.getvalue()
        self.assertIn('S3 trace summary', summary_output)
        self.assertIn('avg request latency: 30.0ms', summary_output)
        self.assertIn('avg parse overhead: 10.0ms', summary_output)
        self.assertIn('avg page drain: 35.0ms', summary_output)
        self.assertIn('avg inter-request gap: 80.0ms', summary_output)
        self.assertNotIn('handoff wait', summary_output)

    def test_inter_request_gap_uses_response_body_ready_timestamp(self):
        ms = 1000000
        time_values = iter(
            [
                0 * ms,
                10 * ms,
                20 * ms,
                30 * ms,
                60 * ms,
                70 * ms,
                80 * ms,
                90 * ms,
                100 * ms,
                110 * ms,
                120 * ms,
                130 * ms,
                140 * ms,
            ]
        )
        trace_config = parse_s3_trace_config(
            {'AWS_CLI_S3_TRACE': 'normal,out=/tmp/trace.jsonl'}
        )
        tracer = S3TransferTracer(
            trace_config=trace_config,
            command_name='cp',
            parameters={'src': 's3://bucket/prefix/'},
            source_client=self.source_client,
            output_file=self.output_file,
            output_path='/tmp/trace.jsonl',
            stderr=self.stderr,
            time_fn=lambda: next(time_values),
        )

        tracer._on_before_call_list_objects_v2(
            model=None,
            params={'query_string': {'max-keys': '1000'}},
            request_signer=None,
            context={},
        )
        tracer._on_before_parse_list_objects_v2(
            operation_model=None,
            response_dict={},
            customized_response_dict={},
        )
        tracer._on_before_call_list_objects_v2(
            model=None,
            params={
                'query_string': {
                    'continuation-token': 'token',
                    'max-keys': '1000',
                }
            },
            request_signer=None,
            context={},
        )
        tracer._on_after_call_list_objects_v2(
            http_response=None,
            parsed={},
            model=None,
            context={},
        )
        page_one = tracer.record_page_available(
            object_count=2,
            is_truncated=True,
            next_continuation_token_present=True,
            request_seq=1,
        )
        tracer.record_page_first_object_yielded(page_one)
        tracer.record_page_last_object_resumed(page_one)
        tracer._on_before_parse_list_objects_v2(
            operation_model=None,
            response_dict={},
            customized_response_dict={},
        )
        tracer._on_after_call_list_objects_v2(
            http_response=None,
            parsed={},
            model=None,
            context={},
        )

        summary = tracer.build_summary()
        self.assertEqual(summary['avg_inter_request_gap_ns'], 10 * ms)
        self.assertEqual(summary['avg_post_drain_gap_ns'], -60 * ms)
        tracer.close()

    def test_registers_and_unregisters_botocore_hooks_for_both_clients(self):
        trace_config = parse_s3_trace_config(
            {'AWS_CLI_S3_TRACE': 'normal,out=/tmp/trace.jsonl'}
        )
        tracer = S3TransferTracer(
            trace_config=trace_config,
            command_name='cp',
            parameters={'src': 's3://bucket/prefix/'},
            source_client=self.source_client,
            transfer_client=self.transfer_client,
            output_file=self.output_file,
            output_path='/tmp/trace.jsonl',
            stderr=self.stderr,
            time_fn=lambda: 0,
        )
        self.assertEqual(self.source_client.meta.events.register.call_count, 3)
        self.assertEqual(self.transfer_client.meta.events.register.call_count, 3)
        tracer.close()
        self.assertEqual(
            self.source_client.meta.events.unregister.call_count, 3
        )
        self.assertEqual(
            self.transfer_client.meta.events.unregister.call_count, 3
        )

    def test_deduplicates_clients_that_share_the_same_emitter(self):
        trace_config = parse_s3_trace_config(
            {'AWS_CLI_S3_TRACE': 'normal,out=/tmp/trace.jsonl'}
        )
        tracer = S3TransferTracer(
            trace_config=trace_config,
            command_name='cp',
            parameters={'src': 's3://bucket/prefix/'},
            source_client=self.source_client,
            transfer_client=self.transfer_client,
            clients=[
                self.source_client,
                self.transfer_client,
                self.source_client,
            ],
            output_file=self.output_file,
            output_path='/tmp/trace.jsonl',
            stderr=self.stderr,
            time_fn=lambda: 0,
        )

        self.assertEqual(self.source_client.meta.events.register.call_count, 3)
        self.assertEqual(self.transfer_client.meta.events.register.call_count, 3)
        tracer.close()

    def test_same_event_emitter_uses_unique_id_to_avoid_double_registration(
        self,
    ):
        trace_config = parse_s3_trace_config(
            {'AWS_CLI_S3_TRACE': 'normal,out=/tmp/trace.jsonl'}
        )
        emitter = HierarchicalEmitter()
        self.source_client.meta.events = emitter
        self.transfer_client.meta.events = emitter
        tracer = S3TransferTracer(
            trace_config=trace_config,
            command_name='cp',
            parameters={'src': 's3://bucket/prefix/'},
            source_client=self.source_client,
            transfer_client=self.transfer_client,
            output_file=self.output_file,
            output_path='/tmp/trace.jsonl',
            stderr=self.stderr,
            time_fn=lambda: 0,
        )

        emitter.emit(
            'before-call.s3.ListObjectsV2',
            model=None,
            params={'query_string': {}},
            request_signer=None,
            context={},
        )

        self.assertEqual(tracer._next_request_seq, 1)

    def test_overlapping_responses_use_request_identity_not_fifo_order(self):
        trace_config = parse_s3_trace_config(
            {'AWS_CLI_S3_TRACE': 'normal,out=/tmp/trace.jsonl'}
        )
        next_timestamp = 0
        timestamp_lock = threading.Lock()

        def time_fn():
            nonlocal next_timestamp
            with timestamp_lock:
                next_timestamp += 1
                return next_timestamp

        tracer = S3TransferTracer(
            trace_config=trace_config,
            command_name='cp',
            parameters={'src': 's3://bucket/prefix/'},
            source_client=self.source_client,
            output_file=self.output_file,
            output_path='/tmp/trace.jsonl',
            stderr=self.stderr,
            time_fn=time_fn,
        )
        request_one_started = threading.Event()
        request_two_finished = threading.Event()
        worker_errors = []

        def request_one():
            try:
                tracer._on_before_call_list_objects_v2(
                    model=None,
                    params={'query_string': {}},
                    request_signer=None,
                    context={},
                )
                request_one_started.set()
                request_two_finished.wait(timeout=1)
                tracer._on_before_parse_list_objects_v2(
                    operation_model=None,
                    response_dict={},
                    customized_response_dict={},
                )
                tracer._on_after_call_list_objects_v2(
                    http_response=None,
                    parsed={},
                    model=None,
                    context={},
                )
            except Exception as error:
                worker_errors.append(error)

        def request_two():
            try:
                request_one_started.wait(timeout=1)
                tracer._on_before_call_list_objects_v2(
                    model=None,
                    params={'query_string': {'continuation-token': 'token'}},
                    request_signer=None,
                    context={},
                )
                tracer._on_before_parse_list_objects_v2(
                    operation_model=None,
                    response_dict={},
                    customized_response_dict={},
                )
                tracer._on_after_call_list_objects_v2(
                    http_response=None,
                    parsed={},
                    model=None,
                    context={},
                )
                request_two_finished.set()
            except Exception as error:
                worker_errors.append(error)

        request_one_thread = threading.Thread(target=request_one)
        request_two_thread = threading.Thread(target=request_two)
        request_one_thread.start()
        request_two_thread.start()
        request_one_thread.join(timeout=1)
        request_two_thread.join(timeout=1)

        self.assertFalse(request_one_thread.is_alive())
        self.assertFalse(request_two_thread.is_alive())
        self.assertEqual(worker_errors, [])
        self.assertLess(
            tracer._requests[2]['list_body_ready'],
            tracer._requests[1]['list_body_ready'],
        )
        self.assertLess(
            tracer._requests[2]['list_parse_done'],
            tracer._requests[1]['list_parse_done'],
        )


class TestScopedS3TransferTracer(unittest.TestCase):
    def test_scoped_tracer_sets_and_resets_current_tracer(self):
        tracer = object()

        self.assertIsNone(get_current_s3_transfer_tracer())
        with scoped_s3_transfer_tracer(tracer):
            self.assertIs(get_current_s3_transfer_tracer(), tracer)
        self.assertIsNone(get_current_s3_transfer_tracer())


class TestBucketListerTracing(unittest.TestCase):
    def test_bucket_lister_records_page_events_with_active_tracer(self):
        client = mock.Mock()
        paginator = client.get_paginator.return_value
        paginator.paginate.return_value = [
            {
                'Contents': [
                    {
                        'Key': 'example.txt',
                        'LastModified': 'timestamp',
                        'Size': 1,
                    }
                ],
                'IsTruncated': True,
                'NextContinuationToken': 'token',
            }
        ]
        tracer = mock.Mock()
        tracer.record_page_available.return_value = 3

        with scoped_s3_transfer_tracer(tracer):
            results = list(
                BucketLister(
                    client,
                    date_parser=lambda value, tzinfo: 'parsed',
                ).list_objects(bucket='bucket')
            )

        self.assertEqual(
            results,
            [
                (
                    'bucket/example.txt',
                    {
                        'Key': 'example.txt',
                        'LastModified': 'parsed',
                        'Size': 1,
                    },
                )
            ],
        )
        tracer.record_page_available.assert_called_once_with(
            object_count=1,
            is_truncated=True,
            next_continuation_token_present=True,
            request_seq=None,
        )
        tracer.record_page_first_object_yielded.assert_called_once_with(3)
        tracer.record_page_last_object_resumed.assert_called_once_with(3)

    def test_bucket_lister_records_first_yield_after_preparing_object(self):
        events = []
        tracer = mock.Mock()

        def parse_timestamp(value, tzinfo):
            events.append(('parsed', value, tzinfo is lister._local_tz))
            return 'parsed'

        tracer.record_page_first_object_yielded.side_effect = (
            lambda page_index: events.append(('first_yield', page_index))
        )
        lister = BucketLister(mock.Mock(), date_parser=parse_timestamp)

        iterator = lister._yield_page_contents(
            bucket='bucket',
            contents=[
                {
                    'Key': 'example.txt',
                    'LastModified': 'timestamp',
                    'Size': 1,
                }
            ],
            page_index=3,
            tracer=tracer,
        )

        item = next(iterator)
        events.append(('consumer_received', item[0], item[1]['LastModified']))

        self.assertEqual(
            item,
            (
                'bucket/example.txt',
                {
                    'Key': 'example.txt',
                    'LastModified': 'parsed',
                    'Size': 1,
                },
            ),
        )
        self.assertEqual(
            events,
            [
                ('parsed', 'timestamp', True),
                ('first_yield', 3),
                ('consumer_received', 'bucket/example.txt', 'parsed'),
            ],
        )
        tracer.record_page_last_object_resumed.assert_not_called()

        with self.assertRaises(StopIteration):
            next(iterator)

        tracer.record_page_last_object_resumed.assert_called_once_with(3)


class TestThreadedBucketListerTracing(unittest.TestCase):
    def test_records_page_events_with_active_tracer(self):
        client = mock.Mock()
        client.list_objects_v2.side_effect = [
            {
                'Contents': [
                    {
                        'Key': 'example.txt',
                        'LastModified': 'timestamp',
                        'Size': 1,
                    }
                ],
                'IsTruncated': True,
                'NextContinuationToken': 'token',
            },
            {
                'Contents': [],
                'IsTruncated': False,
            },
        ]
        tracer = mock.Mock()
        tracer.record_page_available.return_value = 3
        tracer.current_thread_request_seq.return_value = None

        with scoped_s3_transfer_tracer(tracer):
            results = list(
                ThreadedBucketLister(
                    client, date_parser=lambda value, tzinfo: 'parsed'
                ).list_objects(bucket='bucket')
            )

        self.assertEqual(
            results,
            [
                (
                    'bucket/example.txt',
                    {
                        'Key': 'example.txt',
                        'LastModified': 'parsed',
                        'Size': 1,
                    },
                )
            ],
        )
        self.assertEqual(
            tracer.record_page_available.call_args_list,
            [
                mock.call(
                    object_count=1,
                    is_truncated=True,
                    next_continuation_token_present=True,
                    request_seq=1,
                ),
                mock.call(
                    object_count=0,
                    is_truncated=False,
                    next_continuation_token_present=False,
                    request_seq=2,
                ),
            ],
        )
        tracer.record_page_first_object_yielded.assert_called_once_with(3)
        tracer.record_page_last_object_resumed.assert_called_once_with(3)


if __name__ == "__main__":
    unittest.main()
