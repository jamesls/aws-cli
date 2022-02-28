# Copyright 2014 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
import base64
import logging
from botocore.httpchecksum import CrtCrc32cChecksum

from awscli.customizations.s3.syncstrategy.base import SizeAndLastModifiedSync


LOG = logging.getLogger(__name__)


JMES_SYNC_ARG = {
    'name': 'jmes-sync', 'action': 'store_true',
    'help_text': 'A fast, content-based syncing algorithm.'}


class JMESSync(SizeAndLastModifiedSync):

    ARGUMENT = JMES_SYNC_ARG

    def __init__(self, sync_type):
        super(JMESSync, self).__init__(sync_type)
        self._client = None

    def register_strategy(self, session):
        self._client = session.create_client('s3')
        #session.set_stream_logger(
        #    'awscli.customizations.s3', log_level=logging.DEBUG)
        super(JMESSync, self).register_strategy(session)

    def determine_should_sync(self, src_file, dest_file):
        """Subclasses should implement this method.

        This function takes two ``FileStat`` objects (one from the source and
        one from the destination).  Then makes a decision on whether a given
        operation (e.g. a upload, copy, download) should be allowed
        to take place.

        The function currently raises a ``NotImplementedError``.  So this
        method must be overwritten when this class is subclassed.  Note
        that this method must return a Boolean as documented below.

        :type src_file: ``FileStat`` object
        :param src_file: A representation of the operation that is to be
            performed on a specific file existing in the source.  Note if
            the file does not exist at the source, ``src_file`` is None.

        :type dest_file: ``FileStat`` object
        :param dest_file: A representation of the operation that is to be
            performed on a specific file existing in the destination. Note if
            the file does not exist at the destination, ``dest_file`` is None.

        :rtype: Boolean
        :return: True if an operation based on the ``FileStat`` should be
            allowed to occur.
            False if if an operation based on the ``FileStat`` should not be
            allowed to occur. Note the operation being referred to depends on
            the ``sync_type`` of the sync strategy:

            'file_at_src_and_dest': refers to ``src_file``

            'file_not_at_dest': refers to ``src_file``

            'file_not_at_src': refers to ``dest_file``
        """
        # The file type we get has this info:
        #
        # {'compare_key': '.jmessync.py.swp',
        #  'dest': 'jamesls-test-sync/foo/jmessync.py',
        #  'dest_type': 's3',
        #  'last_update': datetime.datetime(2022, 2, 28, 14, 8, 42, 821268, tzinfo=tzlocal()),
        #  'operation_name': 'upload',
        #  'response_data': None,
        #  'size': 12288,
        #  'src': '/path/to/file/jmessync.py',
        #  'src_type': 'local'}

        # The dest_file for an upload has response data:
        #{'compare_key': '.jmessync.py.swp',
        # 'dest': '/Users/jamessar/Source/aws-cli/awscli/customizations/s3/syncstrategy/.jmessync.py.swp',
        # 'dest_type': 'local',
        # 'last_update': datetime.datetime(2022, 2, 28, 14, 8, 32, tzinfo=tzlocal()),
        # 'operation_name': '',
        # 'response_data': {'ChecksumAlgorithm': ['CRC32C'],
        #                   'ETag': '"dbfe767abb9e224fead3ac420cdcaff0"',
        #                   'Key': 'foo/.jmessync.py.swp',
        #                   'LastModified': datetime.datetime(2022, 2, 28, 14, 8, 32, tzinfo=tzlocal()),
        #                   'Size': 12288,
        #                   'StorageClass': 'STANDARD'},
        # 'size': 12288,
        # 'src': 'jamesls-test-sync/foo/.jmessync.py.swp',
        # 'src_type': 's3'}
        result = None
        operation = src_file.operation_name
        if operation == 'upload':
            result = self._handle_upload_check(src_file, dest_file)
        if result is None:
            LOG.debug(
                "Missing checksum data, falling back to default "
                "sync strategy.")
            return super(JMESSync, self).determine_should_sync(
                src_file, dest_file)
        else:
            LOG.debug("Checksum comparison: %s", result)
        return result

    def _handle_upload_check(self, src_file, dest_file):
        if dest_file.response_data.get('ChecksumAlgorithm', '') != ['CRC32C']:
            return None
        bucket, key = src_file.dest.split('/', 1)
        head_object_params = {
            'Bucket': bucket,
            'Key': key,
            'ChecksumMode': 'ENABLED',
        }
        response = self._client.head_object(**head_object_params)
        actual_checksum = base64.b64decode(response['ChecksumCRC32C'])
        local_checksum = self._compute_local_checksum(src_file.src)
        return not actual_checksum == local_checksum

    def _compute_local_checksum(self, filename):
        with open(filename, 'rb') as f:
            c = CrtCrc32cChecksum()
            c.update(f.read())
            return c.digest()
